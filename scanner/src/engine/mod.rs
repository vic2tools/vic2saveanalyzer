// The report engine: a whole run, from the saves to the report, once the
// analyzer's Python has read the mod.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
//     vic2scan report SPEC.json [--dump FOLDER]
//
// SPEC is what `engine.spec` writes: the saves in report order, how each is
// read, how each nation is finished, and where the report goes. The mod
// folder is named there too (`mod_path`), and read here (`modread`) on a
// thread of its own while the saves are.
//
// Every save is read on every core (`prepare`, pass one), the campaign's
// inventions are settled, every save is finished (`finish`, pass two), and
// the campaign is walked in date order into the tables and the page.
//
// Anything Python would have read another way -- a file the scanner turns
// down, a mod rule the engine does not copy -- ends the run with status 3
// before anything is written, and the analyzer reads the campaign itself.

pub mod cache;
pub mod dates;
pub mod dump;
pub mod explain;
pub mod finish;
pub mod mapflags;
pub mod market;
pub mod model;
pub mod modread;
pub mod out;
pub mod walk;
pub mod report;
pub mod rules;
pub mod tables;
pub mod wars;

use crate::country::{read_country, Country, Tables};
use finish::{Pre, Spec, Spent};
use crate::jsonr::{self, J};
use model::Save;
use crate::pickle::{FxMap, FxSet};
use crate::province::{read_province, top_level_blocks, Interner, PopulationRules, Scan};
use rules::{Decline, Mod, D};
use crate::text::{latin1, tag_bytes, to_int_b, trim_b, unquote_b};
use std::io::{Read, Write};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc;

pub const DECLINED: i32 = 3;

/// Phase times, when `VIC2_ENGINE_TIMES` is set: appended to the file it
/// names, or on stderr when it names none (`1`).
pub fn phase(what: &str) {
    use std::sync::OnceLock;
    static START: OnceLock<std::time::Instant> = OnceLock::new();
    static TO: OnceLock<Option<String>> = OnceLock::new();
    let start = START.get_or_init(std::time::Instant::now);
    if let Some(to) = TO.get_or_init(|| std::env::var("VIC2_ENGINE_TIMES").ok()) {
        let line = format!("[{:8.3}] {}\n", start.elapsed().as_secs_f64(), what);
        if to == "1" {
            eprint!("{}", line);
        } else if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(to) {
            let _ = f.write_all(line.as_bytes());
        }
    }
}

/// How a save is read (`readsave.Reading`, and the scanner's lists).
pub struct Reading {
    pub pop_types: Vec<Vec<u8>>,
    pub mob_types: Vec<Vec<u8>>,
    pub reform_keys: Vec<String>,
    pub army_techs: Vec<String>,
    pub navy_techs: Vec<String>,
    pub population_groups: FxMap<i64, i64>,
}

pub struct Run {
    pub files: Vec<String>,
    pub out: String,
    pub reading: Reading,
    pub spec: Spec,
    pub no_html: bool,
    pub split: bool,
    pub map_scale: i64,
    pub quiet: bool,
    pub jobs: Option<i64>,
    pub cross: Option<String>,
    /// The mod folder, read here (`modread`); or, for the checks that hand
    /// the engine a mod Python read, `mod_file`, that mod as JSON.
    pub mod_path: Option<String>,
    /// `mod_reader.mod_signature` of it, which keys the read kept for the
    /// next run; None when Python did not work it out.
    pub mod_signature: Option<String>,
    pub mod_file: Option<String>,
    /// Whether a host reads `@progress` and the rest: Python, which starts
    /// the engine with a spec (`engine.spec`), does.
    pub protocol: bool,
    /// Whether a save the scanner refuses is skipped here in Python's words
    /// (`analyze`, which prints what the run says itself) rather than the
    /// run handed back (Python hosting the engine, which reads only its
    /// stdout).
    pub own_refusals: bool,
    /// One of the four diagnostics, answered instead of the report.
    pub ask: Option<explain::Ask>,
    pub tech_lines: J,
    pub tables: tables::Tables,
    pub store: cache::Store,
    /// What besides the file decides what pass one makes of it, for the
    /// cache's key: the reading and the settings `prepare` takes.
    pub context: String,
    /// The reading alone, which is what Python keys a read save by.
    pub reading_context: String,
}

fn bytes_list(v: &J) -> Vec<Vec<u8>> {
    v.list().iter().map(|x| x.str().chars().map(|c| c as u32 as u8).collect()).collect()
}

fn string_list(v: &J) -> Vec<String> {
    v.list().iter().map(|x| x.str().to_string()).collect()
}

/// The parts of the spec that decide what pass one makes of a save, as one
/// short digest: the reading, and what `prepare` is told.
fn reading_context_of(j: &J) -> String {
    let mut text = String::new();
    j.at("reading").write(&mut text);
    let (mut a, mut b) = (0xcbf2_9ce4_8422_2325u64, 0x9e37_79b9_7f4a_7c15u64);
    for &c in text.as_bytes() {
        a = (a ^ c as u64).wrapping_mul(0x0000_0100_0000_01b3);
        b = (b.rotate_left(5) ^ c as u64).wrapping_mul(0x51_7c_c1_b7_27_22_0a_95);
    }
    format!("{:016x}{:016x}", a, b)
}

fn context_of(j: &J) -> String {
    let mut text = String::new();
    j.at("reading").write(&mut text);
    text.push('|');
    let f = j.at("finish");
    for key in ["pop_per_regiment", "mob_types", "include_occupied", "player_nations", "wanted",
                "min_pop"] {
        f.at(key).write(&mut text);
        text.push('|');
    }
    j.at("head").write(&mut text);
    text.push('|');
    j.at("tables").at("strata").write(&mut text);
    let (mut a, mut b) = (0xcbf2_9ce4_8422_2325u64, 0x9e37_79b9_7f4a_7c15u64);
    for &c in text.as_bytes() {
        a = (a ^ c as u64).wrapping_mul(0x0000_0100_0000_01b3);
        b = (b.rotate_left(5) ^ c as u64).wrapping_mul(0x51_7c_c1_b7_27_22_0a_95);
    }
    format!("{:016x}{:016x}", a, b)
}

fn parse_run(j: &J) -> Run {
    let pop_columns = string_list(j.at("pop_columns"));
    let tables = tables::Tables::from_spec(j, &pop_columns);
    let r = j.at("reading");
    let f = j.at("finish");
    let h = j.at("head");
    let mut tech_group = FxMap::default();
    for branch in ["army", "navy"] {
        for line in j.at("tech_lines").at(branch).list() {
            let name = line.list()[0].str();
            for tech in line.list()[1].list() {
                tech_group.insert(tech.str().to_string(), (branch.to_string(), name.to_string()));
            }
        }
    }
    Run {
        files: string_list(j.at("files")),
        out: j.at("out").str().to_string(),
        reading: Reading {
            pop_types: bytes_list(r.at("pop_types")),
            mob_types: bytes_list(r.at("mob_types")),
            reform_keys: string_list(r.at("reform_keys")),
            army_techs: string_list(r.at("army_techs")),
            navy_techs: string_list(r.at("navy_techs")),
            population_groups: r.at("population_groups").list().iter()
                .map(|p| (p.list()[0].int(), p.list()[1].int())).collect(),
        },
        spec: Spec {

            pop_per_regiment: f.at("pop_per_regiment").int(),
            mob_types: string_list(f.at("mob_types")).into_iter().collect(),
            include_occupied: f.at("include_occupied").truthy(),
            player_nations: if f.at("player_nations").is_null() { None }
                            else { Some(string_list(f.at("player_nations"))) },
            wanted: if f.at("wanted").is_null() { None }
                    else { Some(string_list(f.at("wanted")).into_iter().collect()) },
            min_pop: f.at("min_pop").int(),
            columns: tables.per_save[0].1.clone(),
            strata: tables.strata.clone(),
            regions: h.at("province_regions").list().iter()
                .map(|p| (p.list()[0].int(), p.list()[1].str().to_string())).collect(),
            defines: h.at("defines").pairs().iter().map(|(k, v)| (k.clone(), v.float())).collect(),
            tech_group,
        },
        no_html: j.at("no_html").truthy(),
        split: j.at("split").truthy(),
        map_scale: j.at("map_scale").int().max(1),
        quiet: j.at("quiet").truthy(),
        jobs: if j.at("jobs").is_null() { None } else { Some(j.at("jobs").int()) },
        cross: j.at("cross").as_str().map(|s| s.to_string()),
        mod_path: j.at("mod_path").as_str().map(|s| s.to_string()),
        mod_signature: j.at("mod_signature").as_str().map(|s| s.to_string()),
        mod_file: j.at("mod_file").as_str().map(|s| s.to_string()),
        protocol: j.at("protocol").truthy(),
        own_refusals: j.at("own_refusals").truthy(),
        ask: explain::Ask::from_json(j.at("diagnose")),
        tech_lines: j.at("tech_lines").clone(),
        tables,
        store: cache::Store {
            dir: j.at("cache").at("dir").str().to_string(),
            version: j.at("cache").at("version").str().to_string(),
            on: j.at("cache").at("on").truthy(),
        },
        context: context_of(j),
        reading_context: reading_context_of(j),
    }
}

// ------------------------------------------------------------ one save

/// `os.path.basename`, as the analyzer names a save.
pub fn basename(path: &str) -> &str {
    let cut: &[char] = if cfg!(windows) { &['/', '\\', ':'] } else { &['/'] };
    match path.rfind(cut) {
        Some(i) => &path[i + 1..],
        None => path,
    }
}

fn stamp(path: &str) -> Option<(u64, std::time::SystemTime)> {
    let m = std::fs::metadata(path).ok()?;
    Some((m.len(), m.modified().ok()?))
}

/// A save's bytes: mapped where that is known to work here, read into a
/// buffer the thread keeps otherwise.
///
/// Reading copies the whole file out of the page cache, and sixteen threads
/// copying 34 MB each were what a campaign's reading was bound by (kernel
/// time grew with every thread added, and the reading stopped getting
/// faster at eight). A mapping shares the cache's own pages.
pub enum Bytes<'a> {
    Buffer(&'a [u8]),
    #[cfg(target_os = "linux")]
    Mapped(mapped::Map),
}

impl std::ops::Deref for Bytes<'_> {
    type Target = [u8];
    fn deref(&self) -> &[u8] {
        match self {
            Bytes::Buffer(b) => b,
            #[cfg(target_os = "linux")]
            Bytes::Mapped(m) => m.bytes(),
        }
    }
}

#[cfg(target_os = "linux")]
pub mod mapped {
    use std::os::raw::{c_int, c_long, c_void};
    use std::os::unix::io::AsRawFd;
    extern "C" {
        fn mmap(addr: *mut c_void, len: usize, prot: c_int, flags: c_int, fd: c_int,
                off: c_long) -> *mut c_void;
        fn munmap(addr: *mut c_void, len: usize) -> c_int;
        fn madvise(addr: *mut c_void, len: usize, advice: c_int) -> c_int;
    }
    const PROT_READ: c_int = 1;
    const MAP_PRIVATE: c_int = 2;
    const MAP_POPULATE: c_int = 0x8000;
    const MADV_SEQUENTIAL: c_int = 2;

    pub struct Map {
        ptr: *mut c_void,
        len: usize,
    }

    unsafe impl Send for Map {}

    impl Map {
        pub fn open(file: &std::fs::File, len: usize) -> Option<Map> {
            if len == 0 {
                return None;
            }
            let ptr = unsafe {
                mmap(std::ptr::null_mut(), len, PROT_READ, MAP_PRIVATE | MAP_POPULATE,
                     file.as_raw_fd(), 0)
            };
            if ptr as isize == -1 {
                return None;
            }
            unsafe { madvise(ptr, len, MADV_SEQUENTIAL) };
            Some(Map { ptr, len })
        }

        pub fn bytes(&self) -> &[u8] {
            unsafe { std::slice::from_raw_parts(self.ptr as *const u8, self.len) }
        }
    }

    impl Drop for Map {
        fn drop(&mut self) {
            unsafe { munmap(self.ptr, self.len) };
        }
    }
}

fn load<'a>(path: &str, raw: &'a mut Vec<u8>) -> std::io::Result<Bytes<'a>> {
    let mut f = std::fs::File::open(path)?;
    #[cfg(target_os = "linux")]
    {
        let len = f.metadata()?.len() as usize;
        if std::env::var_os("VIC2_ENGINE_READ").is_none() {
            if let Some(m) = mapped::Map::open(&f, len) {
                return Ok(Bytes::Mapped(m));
            }
        }
    }
    raw.clear();
    f.read_to_end(raw)?;
    Ok(Bytes::Buffer(&raw[..]))
}

/// A save not read: skipped with Python's sentence, the way the Python
/// skips a file it refuses, or the run handed back.
pub enum Refused {
    Skip(String),
    Back(String),
}

/// `str(OSError)`: `[Errno 2] No such file or directory: '/the/path'`.
pub fn os_error_text(e: &std::io::Error, path: &str) -> String {
    let text = e.to_string();
    let strerror = match text.rfind(" (os error ") {
        Some(i) => text[..i].to_string(),
        None => text,
    };
    #[cfg(windows)]
    let (errno, strerror) = match e.raw_os_error() {
        // The C runtime's numbers and words, which are what Python's open()
        // raises with, for the Windows errors a file open meets.
        Some(2) | Some(3) => (2, "No such file or directory".to_string()),
        Some(5) | Some(32) | Some(33) => (13, "Permission denied".to_string()),
        Some(n) => (n, strerror),
        None => (0, strerror),
    };
    #[cfg(not(windows))]
    let errno = e.raw_os_error().unwrap_or(0);
    format!("[Errno {}] {}: {}", errno, strerror, crate::engine::modread::py_repr(path))
}

/// One save read whole, the way `--record` reads it: read again once if it
/// changed while it was read, as Python does, and refused in Python's words
/// if it changes again.
pub fn read_save(path: &str, reading: &Reading, raw: &mut Vec<u8>) -> Result<Save, Refused> {
    match read_once(path, reading, raw, false) {
        Err(Refused::Back(why)) if why == CHANGED => match read_once(path, reading, raw, true) {
            Err(Refused::Back(why)) if why == CHANGED => Err(Refused::Skip(format!(
                "{} changed while it was being read. It is probably the file the game is writing \
                 to right now; read the copies the keeper makes instead.", path))),
            other => other,
        },
        other => other,
    }
}

const CHANGED: &str = "changed while it was being read";

fn read_once(path: &str, reading: &Reading, raw: &mut Vec<u8>, again: bool) -> Result<Save, Refused> {
    let before = stamp(path);
    // A second read is a plain one: a file that changes under a mapping
    // can take the process down with it.
    let raw = if again {
        std::fs::read(path).map(|v| {
            *raw = v;
            Bytes::Buffer(&raw[..])
        })
    } else {
        load(path, raw)
    }.map_err(|e| Refused::Skip(os_error_text(&e, path)))?;
    if stamp(path) != before {
        return Err(Refused::Back(CHANGED.into()));
    }
    // `_refuse_unless_whole`, in its order and its words.
    if raw.starts_with(b"PK") {
        return Err(Refused::Skip(format!(
            "{} is a zip archive. Extract it, or re-save the game in debug mode to get plaintext.",
            path)));
    }
    let head = &raw[..raw.len().min(4096)];
    let has = |needle: &[u8]| head.windows(needle.len()).any(|w| w == needle);
    if !(has(b"date=") || has(b"date =")) {
        return Err(Refused::Skip(format!(
            "{} does not look like a plaintext Vic2 save (no `date=` in the header). If it is \
             binary, launch Victoria 2 in debug mode and re-save.", path)));
    }
    let tail = &raw[raw.len().saturating_sub(256)..];
    let end = tail.iter().rposition(|c| !b" \t\n\r\x0b\x0c".contains(c));
    if end.map(|i| tail[i]) != Some(b'}') {
        return Err(Refused::Skip(format!(
            "{} stops part-way through, so it was cut short: the game crashed while writing it, \
             or is writing it right now. If this is the game's own save folder, read the copies \
             the keeper makes instead.", path)));
    }
    let text: &[u8] = &raw[..];
    let mut scan = Scan {
        world_pop: 0,
        owners: Vec::new(),
        nations: FxMap::default(),
        pop_ids: Vec::new(),
        pop_kinds: Vec::new(),
        words: Interner::default(),
        seen: Vec::new(),
    };
    let tables = Tables {
        army_techs: &reading.army_techs,
        navy_techs: &reading.navy_techs,
        reform_keys: &reading.reform_keys,
    };
    let (blocks, date, player, countries) = match top_level_blocks(text) {
        Some(blocks) => {
            let (date, player, countries) = read_flat(text, &blocks, reading, &tables, &mut scan);
            (blocks, date, player, countries)
        }
        // Not the game's layout: Python walks it a token at a time, and so
        // does this.
        None => {
            let w = walk::read(text, &reading.pop_types, &reading.mob_types, &tables, &mut scan,
                               &reading.population_groups)
                .map_err(|why| Refused::Back(format!("{}: {}", path, why)))?;
            (w.blocks, w.date, w.player, w.countries)
        }
    };
    let rest = model::read_rest(text, &blocks)
        .map_err(|_| Refused::Back(format!("{}: the wars or the market hold something only Python reads", path)))?;
    let save = model::build(basename(path).to_string(), date, player, &scan, &countries, rest)
        .map_err(|_| Refused::Back(format!("{}: the record could not be built", path)))?;
    // Again after the scan, not only after the read: a mapped file is read
    // as it is scanned, and one the game rewrote meanwhile would be half of
    // each. Python reads it again, and says so if it changes a second time.
    if stamp(path) != before {
        return Err(Refused::Back(CHANGED.into()));
    }
    Ok(save)
}

/// The date, the player and the countries of a save laid out the game's
/// way, its provinces folded into `scan`.
fn read_flat(text: &[u8], blocks: &[(&[u8], usize, usize)], reading: &Reading, tables: &Tables,
             scan: &mut Scan) -> (String, String, Vec<Country>) {
    let mut date = String::new();
    let mut player = String::new();
    let head_end = blocks.first().map(|b| b.1).unwrap_or(0).min(text.len());
    for line in text[..head_end].split(|&c| c == b'\n').take(40) {
        if let Some(eq) = line.iter().position(|&c| c == b'=') {
            let k = trim_b(&line[..eq]);
            let v = unquote_b(trim_b(&line[eq + 1..]));
            if k == b"date" && date.is_empty() {
                date = latin1(v);
            } else if k == b"player" && player.is_empty() {
                player = latin1(v);
            }
        }
    }
    let mut countries: Vec<Country> = Vec::new();
    let mut rules: FxMap<Vec<u8>, PopulationRules> = FxMap::default();
    let mut referenced_pops = FxSet::default();
    for (key, at, stop) in blocks {
        if tag_bytes(key) {
            let chunk = latin1(&text[*at..(*stop).min(text.len())]);
            let tag = latin1(key);
            let country = read_country(&chunk, 0, chunk.len(), &tag, tables);
            let rule = rules.entry(key.to_vec()).or_default();
            let bytes = |s: &str| s.chars().map(|c| c as u8).collect::<Vec<_>>();
            rule.accepted.extend(country.accepted_cultures.iter().map(|s| bytes(s)));
            for (name, value) in &country.scalars {
                if name == "primary_culture" && !value.is_empty() {
                    rule.accepted.insert(bytes(value));
                }
            }
            rule.colonial.extend(&country.colonial_provinces);
            referenced_pops.extend(&country.regiment_pops);
            countries.push(country);
        }
    }
    for (key, at, stop) in blocks {
        if !key.is_empty() && key.iter().all(|c| c.is_ascii_digit()) {
            read_province(text, *at, *stop, to_int_b(key), &reading.pop_types,
                          &reading.mob_types, scan, &rules, &referenced_pops,
                          &reading.population_groups);
        }
    }
    (date, player, countries)
}

// ------------------------------------------------------------ the pool

/// `readfolder.worker_count`: cores bar one, the saves left, and memory.
pub fn worker_count(jobs: usize, biggest: u64, asked: Option<i64>) -> usize {
    if let Some(a) = asked {
        return (a.max(1) as usize).min(jobs).max(1);
    }
    let cores = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1)
        .saturating_sub(1).max(1);
    let mut room = jobs;
    if let Some(spare) = spare_memory() {
        room = ((spare as f64 * 0.6) as u64 / (biggest * 3).max(1)).max(1) as usize;
    }
    cores.min(jobs).min(room).max(1)
}

#[cfg(target_os = "linux")]
fn spare_memory() -> Option<u64> {
    // `os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")`: free
    // pages, which /proc/meminfo calls MemFree.
    let text = std::fs::read_to_string("/proc/meminfo").ok()?;
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("MemFree:") {
            let kb: u64 = rest.trim().trim_end_matches("kB").trim().parse().ok()?;
            return Some(kb * 1024);
        }
    }
    None
}

#[cfg(windows)]
fn spare_memory() -> Option<u64> {
    #[repr(C)]
    struct Status {
        length: u32,
        load: u32,
        total_phys: u64,
        avail_phys: u64,
        total_page: u64,
        avail_page: u64,
        total_virtual: u64,
        avail_virtual: u64,
        avail_extended: u64,
    }
    extern "system" {
        fn GlobalMemoryStatusEx(status: *mut Status) -> i32;
    }
    let mut s = Status { length: std::mem::size_of::<Status>() as u32, load: 0, total_phys: 0,
                         avail_phys: 0, total_page: 0, avail_page: 0, total_virtual: 0,
                         avail_virtual: 0, avail_extended: 0 };
    if unsafe { GlobalMemoryStatusEx(&mut s) } != 0 { Some(s.avail_phys) } else { None }
}

#[cfg(not(any(target_os = "linux", windows)))]
fn spare_memory() -> Option<u64> {
    None
}

/// Run `job` over `0..n` on `workers` threads, handing each answer to
/// `take` in index order as soon as it and everything before it are done.
pub fn in_order<T: Send, F, G>(n: usize, workers: usize, job: F, mut take: G)
where
    F: Fn(usize) -> T + Sync,
    G: FnMut(usize, T),
{
    if workers <= 1 || n <= 1 {
        for i in 0..n {
            take(i, job(i));
        }
        return;
    }
    let next = AtomicUsize::new(0);
    let (tx, rx) = mpsc::channel::<(usize, T)>();
    std::thread::scope(|s| {
        for _ in 0..workers.min(n) {
            let tx = tx.clone();
            let (next, job) = (&next, &job);
            s.spawn(move || loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= n {
                    break;
                }
                if tx.send((i, job(i))).is_err() {
                    break;
                }
            });
        }
        drop(tx);
        let mut waiting: FxMap<usize, T> = FxMap::default();
        let mut due = 0;
        for (i, v) in rx {
            waiting.insert(i, v);
            while let Some(v) = waiting.remove(&due) {
                take(due, v);
                due += 1;
            }
        }
    });
}

/// A line in the file `VIC2_FRONT_LOG` names, for the checks that need to
/// know whether a run was made here or handed back.
pub fn front_log(line: &str) {
    if let Some(path) = std::env::var_os("VIC2_FRONT_LOG") {
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
            let _ = writeln!(f, "{}", line);
        }
    }
}

/// A line for the host to read: progress, and the like.
pub fn say(line: &str) {
    out::protocol(line);
}

/// Hand the run back. What it has said so far is dropped with it when it
/// was being held (`out`); the checks that require the engine see why.
pub fn decline(why: &str) -> ! {
    front_log(&format!("handed back: {}", why));
    if std::env::var_os("VIC2_ENGINE_REQUIRED").is_some() {
        eprintln!("engine: {}", why);
    } else if out::say_declines() {
        // Python hosting the engine keeps its stderr for when it fails.
        crate::errln!("engine: {}", why);
    }
    std::process::exit(DECLINED);
}

/// The mod: read from its folder -- or from what the last run kept of the
/// same files -- or from the JSON a check wrote of the one Python read.
fn load_mod(mod_path: &Option<String>, signature: &Option<String>, mod_file: &Option<String>,
            store: &cache::Store) -> D<Mod> {
    let j = match (mod_path, mod_file) {
        (_, Some(file)) => {
            let text = std::fs::read_to_string(file)
                .unwrap_or_else(|e| decline(&format!("cannot read the mod export {}: {}", file, e)));
            jsonr::parse(&text).unwrap_or_else(|e| decline(&format!("mod export: {}", e)))
        }
        (Some(path), None) => {
            let slot = cache::mod_slot(store, path, signature.as_deref());
            match slot.as_ref().and_then(cache::mod_load) {
                Some(j) => j,
                None => {
                    let j = read_mod(path)?;
                    if let Some(slot) = &slot {
                        cache::mod_store(slot, &j);
                    }
                    j
                }
            }
        }
        (None, None) => decline("no mod was named"),
    };
    Mod::from_json(&j)
}

/// The mod folder read (`modread`).
fn read_mod(path: &str) -> D<J> {
    // Its patterns go a frame deeper for each way a step of a repeat
    // could end; a stack of its own gives them room.
    let path = path.to_string();
    let got = std::thread::Builder::new().stack_size(256 << 20)
        .spawn(move || modread::export(&path))
        .unwrap_or_else(|e| decline(&format!("cannot start the mod reader: {}", e)))
        .join();
    match got {
        Ok(got) => got,
        Err(_) => decline("the mod reader stopped"),
    }
}

/// `vic2scan bench-engine SPEC N`: the first N saves read one at a time,
/// timing reading, scanning, building the record and preparing it.
pub fn bench(args: &[String]) {
    let text = std::fs::read_to_string(&args[2]).unwrap();
    let run = parse_run(&jsonr::parse(&text).unwrap());
    let n: usize = args.get(3).and_then(|a| a.parse().ok()).unwrap_or(10);
    let mut raw = Vec::new();
    let (mut t_read, mut t_prep) = (0.0, 0.0);
    for f in run.files.iter().take(n) {
        let t = std::time::Instant::now();
        let save = read_save(f, &run.reading, &mut raw).unwrap_or_else(|_| panic!("{} was not read", f));
        t_read += t.elapsed().as_secs_f64();
        let t = std::time::Instant::now();
        let tags = keys_of(&save);
        let pre = finish::prepare(save.meta, save.nations, tags, &run.spec);
        t_prep += t.elapsed().as_secs_f64();
        std::hint::black_box(pre);
    }
    let k = n as f64 / 1000.0;
    eprintln!("per save: read+scan+build {:.1} ms, prepare {:.1} ms", t_read / k, t_prep / k);
    // And the parts of a read, one at a time.
    let mut t = [0.0f64; 6];
    for f in run.files.iter().take(n) {
        let c = std::time::Instant::now();
        let raw = std::fs::read(f).unwrap();
        t[0] += c.elapsed().as_secs_f64();
        let c = std::time::Instant::now();
        let blocks = top_level_blocks(&raw).unwrap();
        t[1] += c.elapsed().as_secs_f64();
        let c = std::time::Instant::now();
        let tables = Tables { army_techs: &run.reading.army_techs, navy_techs: &run.reading.navy_techs,
                              reform_keys: &run.reading.reform_keys };
        let mut countries = Vec::new();
        let mut rules: FxMap<Vec<u8>, PopulationRules> = FxMap::default();
        let mut referenced = FxSet::default();
        for (key, at, stop) in &blocks {
            if tag_bytes(key) {
                let chunk = latin1(&raw[*at..(*stop).min(raw.len())]);
                let country = read_country(&chunk, 0, chunk.len(), &latin1(key), &tables);
                let rule = rules.entry(key.to_vec()).or_default();
                rule.accepted.extend(country.accepted_cultures.iter().map(|s| s.as_bytes().to_vec()));
                rule.colonial.extend(&country.colonial_provinces);
                referenced.extend(&country.regiment_pops);
                countries.push(country);
            }
        }
        t[2] += c.elapsed().as_secs_f64();
        let c = std::time::Instant::now();
        let mut scan = Scan { world_pop: 0, owners: Vec::new(), nations: FxMap::default(),
                              pop_ids: Vec::new(), pop_kinds: Vec::new(),
                              words: Interner::default(), seen: Vec::new() };
        for (key, at, stop) in &blocks {
            if !key.is_empty() && key.iter().all(|c| c.is_ascii_digit()) {
                read_province(&raw, *at, *stop, to_int_b(key), &run.reading.pop_types,
                              &run.reading.mob_types, &mut scan, &rules, &referenced,
                              &run.reading.population_groups);
            }
        }
        t[3] += c.elapsed().as_secs_f64();
        let c = std::time::Instant::now();
        let rest = model::read_rest(&raw, &blocks).unwrap();
        t[4] += c.elapsed().as_secs_f64();
        let c = std::time::Instant::now();
        let save = model::build(String::new(), String::new(), String::new(), &scan, &countries, rest);
        std::hint::black_box(save.ok());
        t[5] += c.elapsed().as_secs_f64();
    }
    eprintln!("per save: file {:.1}, blocks {:.1}, countries {:.1}, provinces {:.1}, wars+market {:.1}, record {:.1} ms",
              t[0] / k, t[1] / k, t[2] / k, t[3] / k, t[4] / k, t[5] / k);
}

pub fn main(args: &[String]) {
    if args.len() < 3 {
        eprintln!("usage: vic2scan report SPEC.json [--dump FOLDER]");
        std::process::exit(2);
    }
    let text = std::fs::read_to_string(&args[2]).unwrap_or_else(|e| {
        eprintln!("cannot read {}: {}", args[2], e);
        std::process::exit(2);
    });
    let spec_j = jsonr::parse(&text).unwrap_or_else(|e| {
        eprintln!("{}: {}", args[2], e);
        std::process::exit(2);
    });
    let dump = args.iter().position(|a| a == "--dump").and_then(|i| args.get(i + 1)).cloned();
    run_spec(&spec_j, dump);
}

/// A run as `engine.spec` declares it. None when `dump` was asked for
/// instead of the report; a run handed back never returns.
pub fn run_spec(spec_j: &J, dump: Option<String>) -> Option<report::Outcome> {
    phase("start");
    let run = parse_run(spec_j);
    out::set_protocol(run.protocol);
    let n = run.files.len();
    let biggest = run.files.iter().filter_map(|f| std::fs::metadata(f).ok()).map(|m| m.len())
        .max().unwrap_or(0);
    let workers = worker_count(n, biggest, run.jobs);

    // Pass one: every save read and prepared, on every core. A verbose run
    // says so as the invention pass did, a save at a time in date order.
    let verbose = !run.quiet;
    let slots: Vec<Option<(String, String)>> =
        run.files.iter().map(|f| run.store.slot(f, &run.context)).collect();
    // As the Python's invention pass says it: nothing when it found the
    // campaign read before, and otherwise a line a save, after "Reading N"
    // for the saves it had not read under this reading.
    let marks: Vec<Option<String>> =
        run.files.iter().map(|f| run.store.read_marker(f, &run.reading_context)).collect();
    let todo = marks.iter().filter(|m| m.as_ref().is_none_or(|m| !std::path::Path::new(m).is_file())).count();
    let campaign = run.store.campaign_marker(&run.files, &run.reading_context);
    let campaign_read = campaign.as_ref().is_some_and(|c| std::path::Path::new(c).is_file());
    let say_each = verbose && !campaign_read;
    if say_each && todo > 0 {
        crate::outln!("Reading {} save(s) on {} cores.", todo, workers);
    }
    // The mod, and the map's bitmap it names, read on a thread of their own
    // while the saves are: the mod arrives while they are being read, and
    // the bitmap is twelve million pixels nothing else needs until the page.
    let mod_job = {
        let (mod_path, mod_file) = (run.mod_path.clone(), run.mod_file.clone());
        let (signature, store) = (run.mod_signature.clone(), run.store.clone());
        let (scale, want_map) = (run.map_scale, !run.no_html);
        std::thread::spawn(move || {
            let mut m = load_mod(&mod_path, &signature, &mod_file, &store)?;
            if want_map {
                m.raster = Some(crate::engine::mapflags::province_raster(&m.map_bmp, &m.map_csv, scale));
            }
            Ok(m)
        })
    };
    let mut pres: Vec<Option<Pre>> = (0..n).map(|_| None).collect();
    let mut failed: Option<String> = None;
    let mut skipped: Vec<String> = Vec::new();
    let mut done = 0usize;
    thread_local!(static RAW: std::cell::RefCell<Vec<u8>> = const { std::cell::RefCell::new(Vec::new()) });
    in_order(n, workers, |i| {
        if let Some(slot) = &slots[i] {
            if let Some(pre) = run.store.load(slot) {
                return Ok((pre, true));
            }
        }
        RAW.with(|raw| {
            let mut raw = raw.borrow_mut();
            let got = read_save(&run.files[i], &run.reading, &mut raw);
            // A worker holds a save's worth of buffer between saves, not a
            // campaign's: let an outsized one go.
            if raw.capacity() > 96 << 20 {
                *raw = Vec::new();
            }
            got.map_err(|refused| match refused {
                Refused::Skip(why) if run.own_refusals => Refused::Skip(why),
                Refused::Skip(why) | Refused::Back(why) => Refused::Back(why),
            }).map(|save| {
                let tags = keys_of(&save);
                let pre = finish::prepare(save.meta, save.nations, tags, &run.spec);
                if let Some(slot) = &slots[i] {
                    run.store.store(slot, &pre);
                }
                (pre, false)
            })
        })
    }, |i, got| {
        match got {
            Ok((pre, cached)) => {
                done += 1;
                if say_each && failed.is_none() {
                    if cached && workers <= 1 {
                        crate::outln!("  {} ... cached, {}", basename(&run.files[i]), pre.meta.date);
                    } else if workers > 1 {
                        crate::outln!("  [{}/{}] {} ... {}", done, n, basename(&run.files[i]), pre.meta.date);
                    } else {
                        let months: FxSet<&str> = pre.meta.market.as_ref()
                            .map(|m| m.history.iter().map(|h| h.0.as_str()).collect())
                            .unwrap_or_default();
                        let extra = if months.is_empty() { String::new() }
                                    else { format!(", {} months of prices", months.len()) };
                        crate::outln!("  reading {} ... {}, {} nations{}", basename(&run.files[i]),
                                 pre.meta.date, pre.nations.len(), extra);
                    }
                }
                say(&format!("@progress {} {}", done, n));
                pres[i] = Some(pre);
            }
            Err(Refused::Skip(why)) => {
                // `parse_saves_stream`: the file is named and passed over.
                // Read one at a time, the Python had already begun the
                // line that says so, and it is left unfinished.
                if say_each && failed.is_none() && workers <= 1 {
                    crate::engine::out::write(true, format!("  reading {} ...", basename(&run.files[i])));
                }
                let line = format!("  skipped {}: {}", basename(&run.files[i]), why);
                if !campaign_read {
                    crate::errln!("{}", line);
                }
                skipped.push(line);
            }
            Err(Refused::Back(why)) => {
                if failed.is_none() {
                    failed = Some(why);
                }
            }
        }
    });
    if let Some(why) = failed {
        decline(&why);
    }
    // The saves that were read, and where they sit among the files.
    let kept: Vec<usize> = (0..n).filter(|&i| pres[i].is_some()).collect();
    for &i in &kept {
        if let Some(m) = &marks[i] {
            run.store.mark(m);
        }
    }
    if let Some(c) = &campaign {
        run.store.mark(c);
    }
    let files: Vec<String> = kept.iter().map(|&i| run.files[i].clone()).collect();
    let pres: Vec<Pre> = pres.into_iter().flatten().collect();
    let n = pres.len();
    phase("pass one: saves read and prepared");

    // The campaign's inventions, settled against the mod.
    let mut m = match mod_job.join().unwrap_or_else(|_| decline("the mod could not be read")) {
        Ok(m) => m,
        // A mod Python raises over is refused when Python asks for it,
        // which is now, with every save read once.
        Err(d) => match modread::raised_sentence(&d) {
            Some(sentence) if run.own_refusals => {
                out::release();
                return Some(report::Outcome { html: None, refused: Vec::new(),
                                              run_error: Some(sentence.to_string()) });
            }
            _ => decline(&format!("the mod: {}", d.0.trim_start_matches('\u{1}'))),
        },
    };
    let held: Vec<&[rules::Held]> = pres.iter().map(|p| p.held.as_slice()).collect();
    phase("mod loaded");
    let live = rules::settle_campaign(&mut m, &held);
    phase("inventions settled");
    if verbose {
        crate::engine::report::say_mod(&m, &live, &held, &files);
    }
    // The second pass read every file again, and named each refused one
    // again as it went past.
    for line in &skipped {
        crate::errln!("{}", line);
    }
    if pres.is_empty() {
        out::release();
        return Some(report::Outcome { html: None, refused: Vec::new(),
                                      run_error: Some("No saves could be read.".into()) });
    }
    // A diagnostic is answered off the campaign as it stands, and ends the
    // run: no report, no tables.
    if let Some(ask) = &run.ask {
        let said = explain::answer(ask, &m, &live, &pres, &files, &run.reading);
        return Some(report::Outcome { html: None, refused: Vec::new(), run_error: said.err() });
    }

    // Pass two: every save finished.
    let mut spent: Vec<Option<Spent>> = (0..n).map(|_| None).collect();
    let mut declined: Option<String> = None;
    let pres: Vec<std::sync::Mutex<Option<Pre>>> =
        pres.into_iter().map(|p| std::sync::Mutex::new(Some(p))).collect();
    in_order(n, workers, |i| {
        let pre = pres[i].lock().unwrap().take().unwrap();
        finish::finish(pre, &run.spec, &m, Some(&live))
    }, |i, got| match got {
        Ok(s) => spent[i] = Some(s),
        Err(Decline(why)) => {
            if declined.is_none() {
                declined = Some(why);
            }
        }
    });
    if let Some(why) = declined {
        decline(&why);
    }
    let spent: Vec<Spent> = spent.into_iter().map(|s| s.unwrap()).collect();
    phase("pass two: saves finished");
    if let Some(folder) = dump {
        crate::engine::dump::write(&folder, &spent, &m, &live);
        return None;
    }
    // Nothing from here on hands the run back.
    out::release();
    Some(crate::engine::report::run(&run, &m, &live, spent))
}

/// The keys a save's nations are held under: the owner tags the provinces
/// named, which `model::build` kept in `Nation.key`.
fn keys_of(save: &Save) -> Vec<String> {
    save.nations.iter().map(|n| n.key.clone()).collect()
}

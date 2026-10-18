// One save, read: its bytes mapped or buffered, the text scanned by the
// fast readers or walked token by token, and what refuses it, in the words a
// run says.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::save::country::{read_country, Country, Tables};
use crate::engine::{model, Reading};
use crate::engine::model::Save;
use crate::util::fx::{FxMap, FxSet};
use crate::save::province::{read_province, top_level_blocks, PopulationRules, Scan};
use crate::save::text::{latin1, tag_bytes, to_int_b, trim_b, unquote_b};
use std::io::Read;

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

impl Bytes<'_> {
    /// Whether the file was cut short while it was mapped (`mapped`).
    fn faulted(&self) -> bool {
        match self {
            Bytes::Buffer(_) => false,
            #[cfg(target_os = "linux")]
            Bytes::Mapped(m) => m.faulted(),
        }
    }
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
    //! A save mapped rather than read, and kept safe from the one thing a
    //! mapping cannot survive on its own: the file cut short while it is
    //! being scanned -- the game rewriting an autosave in the folder being
    //! read. Touching a page past the new end raises SIGBUS, which kills the
    //! process. Every live mapping is listed where a SIGBUS handler can see
    //! it; a fault inside one gets a page of zeros mapped over the page that
    //! went, the mapping is marked, and the read that owns it is then treated
    //! as a file changed under a read -- read again, into a buffer. A fault
    //! anywhere else is left to kill the process as it always would.
    use std::os::raw::{c_int, c_long, c_void};
    use std::os::unix::io::AsRawFd;
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

    extern "C" {
        fn mmap(addr: *mut c_void, len: usize, prot: c_int, flags: c_int, fd: c_int,
                off: c_long) -> *mut c_void;
        fn munmap(addr: *mut c_void, len: usize) -> c_int;
        fn madvise(addr: *mut c_void, len: usize, advice: c_int) -> c_int;
        fn sigaction(sig: c_int, act: *const SigAction, old: *mut SigAction) -> c_int;
        fn sysconf(name: c_int) -> c_long;
    }
    const PROT_READ: c_int = 1;
    const MAP_PRIVATE: c_int = 2;
    const MAP_FIXED: c_int = 0x10;
    const MAP_ANONYMOUS: c_int = 0x20;
    const MAP_POPULATE: c_int = 0x8000;
    const MADV_SEQUENTIAL: c_int = 2;
    const SIGBUS: c_int = 7;
    const SA_SIGINFO: c_int = 4;
    const SC_PAGESIZE: c_int = 30;
    /// Where `si_addr` sits in a `siginfo_t`: after three ints, aligned.
    const SI_ADDR: usize = if cfg!(target_pointer_width = "64") { 16 } else { 12 };

    /// glibc's `struct sigaction`, on Linux.
    #[repr(C)]
    struct SigAction {
        handler: usize,
        mask: [u64; 16],
        flags: c_int,
        restorer: usize,
    }

    /// The live mappings, as (start, length) and whether one has faulted.
    /// A thread reads one save at a time, so a slot a thread is plenty; a
    /// mapping with no free slot is not made, and the save is read instead.
    const SLOTS: usize = 256;
    static START: [AtomicUsize; SLOTS] = [const { AtomicUsize::new(0) }; SLOTS];
    static LEN: [AtomicUsize; SLOTS] = [const { AtomicUsize::new(0) }; SLOTS];
    static FAULTED: [AtomicBool; SLOTS] = [const { AtomicBool::new(false) }; SLOTS];
    static PAGE: AtomicUsize = AtomicUsize::new(4096);

    extern "C" fn on_sigbus(_sig: c_int, info: *mut c_void, _ctx: *mut c_void) {
        let addr = unsafe { *((info as *const u8).add(SI_ADDR) as *const usize) };
        for i in 0..SLOTS {
            let start = START[i].load(Ordering::Acquire);
            let len = LEN[i].load(Ordering::Acquire);
            if start != 0 && addr >= start && addr < start + len {
                let page = PAGE.load(Ordering::Relaxed);
                let at = addr & !(page - 1);
                let got = unsafe {
                    mmap(at as *mut c_void, page, PROT_READ,
                         MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0)
                };
                if got as isize != -1 {
                    FAULTED[i].store(true, Ordering::Release);
                    return;
                }
            }
        }
        // Not one of ours: back to the default, and the fault, met again,
        // ends the process as it would have.
        let default = SigAction { handler: 0, mask: [0; 16], flags: 0, restorer: 0 };
        unsafe { sigaction(SIGBUS, &default, std::ptr::null_mut()) };
    }

    fn install() {
        static ONCE: std::sync::Once = std::sync::Once::new();
        ONCE.call_once(|| {
            let page = unsafe { sysconf(SC_PAGESIZE) };
            if page > 0 {
                PAGE.store(page as usize, Ordering::Relaxed);
            }
            let handler: extern "C" fn(c_int, *mut c_void, *mut c_void) = on_sigbus;
            let act = SigAction { handler: handler as usize, mask: [0; 16], flags: SA_SIGINFO,
                                  restorer: 0 };
            unsafe { sigaction(SIGBUS, &act, std::ptr::null_mut()) };
        });
    }

    pub struct Map {
        ptr: *mut c_void,
        len: usize,
        slot: usize,
    }

    unsafe impl Send for Map {}

    impl Map {
        pub fn open(file: &std::fs::File, len: usize) -> Option<Map> {
            if len == 0 {
                return None;
            }
            install();
            // A slot first: a mapping the handler cannot see is not made.
            let slot = (0..SLOTS).find(|&i| {
                LEN[i].compare_exchange(0, usize::MAX, Ordering::AcqRel, Ordering::Relaxed).is_ok()
            })?;
            let ptr = unsafe {
                mmap(std::ptr::null_mut(), len, PROT_READ, MAP_PRIVATE | MAP_POPULATE,
                     file.as_raw_fd(), 0)
            };
            if ptr as isize == -1 {
                LEN[slot].store(0, Ordering::Release);
                return None;
            }
            FAULTED[slot].store(false, Ordering::Release);
            START[slot].store(ptr as usize, Ordering::Release);
            LEN[slot].store(len, Ordering::Release);
            unsafe { madvise(ptr, len, MADV_SEQUENTIAL) };
            Some(Map { ptr, len, slot })
        }

        pub fn bytes(&self) -> &[u8] {
            unsafe { std::slice::from_raw_parts(self.ptr as *const u8, self.len) }
        }

        /// Whether the file was cut short under the mapping, so that some of
        /// what was read is zeros standing in for pages that went.
        pub fn faulted(&self) -> bool {
            FAULTED[self.slot].load(Ordering::Acquire)
        }
    }

    impl Drop for Map {
        fn drop(&mut self) {
            // Out of the list before the pages go, then the slot freed.
            START[self.slot].store(0, Ordering::Release);
            unsafe { munmap(self.ptr, self.len) };
            FAULTED[self.slot].store(false, Ordering::Release);
            LEN[self.slot].store(0, Ordering::Release);
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::io::Write;

        #[test]
        fn a_file_cut_short_under_the_mapping_is_survived_and_said() {
            let path = std::env::temp_dir().join(format!("vic2map{}", std::process::id()));
            let mut f = std::fs::File::create(&path).unwrap();
            f.write_all(&vec![b'x'; 64 * 1024]).unwrap();
            drop(f);
            let f = std::fs::File::open(&path).unwrap();
            let m = Map::open(&f, 64 * 1024).unwrap();
            assert_eq!(m.bytes()[40000], b'x');
            assert!(!m.faulted());
            std::fs::OpenOptions::new().write(true).open(&path).unwrap().set_len(0).unwrap();
            // Past the new end: SIGBUS without the handler.
            let tail: u64 = m.bytes()[8192..].iter().map(|&b| b as u64).sum();
            assert_eq!(tail, 0);
            assert!(m.faulted());
            drop(m);
            std::fs::remove_file(&path).unwrap();
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

/// A save not read: skipped, in the sentence the run says of it, or
/// something the run stops over.
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
    format!("[Errno {}] {}: {}", errno, strerror, crate::py::repr::str_repr(path))
}

/// One save read whole: read again once if it
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
    // A second read is a plain one: the first may have been cut short under
    // its mapping (`mapped`), and this one is read whole into a buffer.
    let raw = if again {
        std::fs::read(path).map(|v| {
            *raw = v;
            Bytes::Buffer(&raw[..])
        })
    } else {
        load(path, raw)
    }.map_err(|e| Refused::Skip(os_error_text(&e, path)))?;
    let got = read_bytes(path, reading, &raw, before);
    // A file cut short under its mapping was read partly as zeros, whatever
    // the read made of them: it is a file changed under a read, and read again.
    if raw.faulted() {
        return Err(Refused::Back(CHANGED.into()));
    }
    got
}

/// The rest of `read_once`, on the bytes as loaded.
fn read_bytes(path: &str, reading: &Reading, raw: &[u8],
              before: Option<(u64, std::time::SystemTime)>) -> Result<Save, Refused> {
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
        // Not the game's layout: walked a token at a time, as the Python
        // that this replaced walked it.
        None => {
            let w = crate::save::walk::read(text, &reading.pop_types, &reading.mob_types, &tables, &mut scan,
                               &reading.population_groups)
                .map_err(|why| Refused::Back(format!("{}: {}", path, why)))?;
            (w.blocks, w.date, w.player, w.countries)
        }
    };
    let rest = model::read_rest(text, &blocks)
        .map_err(|_| Refused::Back(format!("{}: the wars or the market hold something it cannot make out", path)))?;
    let save = model::build(crate::py::path::basename(path), date, player, &scan, &countries, rest)
        .map_err(|_| Refused::Back(format!("{}: the record could not be built", path)))?;
    // Again after the scan, not only after the read: a mapped file is read
    // as it is scanned, and one the game rewrote meanwhile would be half of
    // each. It is read again (`read_save`), and stops the run if it changes
    // a second time.
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
            let chunk = &text[*at..(*stop).min(text.len())];
            let tag = latin1(key);
            let country = read_country(chunk, 0, chunk.len(), &tag, tables);
            let rule = rules.entry(key.to_vec()).or_default();
            rule.accepted.extend(country.accepted_cultures.iter().copied());
            for (name, value) in &country.scalars {
                if name == "primary_culture" && !value.is_empty() {
                    rule.accepted.insert(crate::save::names::intern_str(value));
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

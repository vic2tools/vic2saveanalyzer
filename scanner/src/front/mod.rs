// A run of the analyzer, as `vic2_analyzer.main` makes it, in Rust.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
//     vic2scan analyze --run RUN.json [--refused FILE]
//
// RUN is the `run.Run` Python's command line made (`dataclasses.asdict`).
// From it this does what `_main` does for an ordinary report: finds the
// saves, settles the game and the mod, takes the stamp and answers "nothing
// has changed" when it can, reads the mod's head, puts the saves in date
// order, and runs the engine (`engine::run_spec`) -- printing what Python
// printed, in its words, and refusing what it refused.
//
// What it does not do yet it hands back (status 3) before saying anything:
// the diagnostics, `--cross`, `--peek`, `--verify`, and whatever the engine
// hands back. Everything said is held (`engine::out`) until the run can no
// longer be handed back, so the Python that then does the run says it all
// once.

pub mod pypath;

use crate::engine::modread;
use crate::engine::out;
use crate::jsonr::J;
use crate::md5::Md5;
use pypath::{abspath, basename, isdir, join};

/// A run refused, in the sentence Python gives (`run.RunError`).
pub struct RunError(pub String);

type R<T> = Result<T, RunError>;

fn refuse<T>(why: impl Into<String>) -> R<T> {
    Err(RunError(why.into()))
}

/// Hand the run back to Python, having said nothing.
fn hand_back(why: &str) -> ! {
    crate::engine::decline(why)
}

/// The settings of a run (`run.Run`).
pub struct Args {
    pub saves: String,
    pub out: String,
    pub tags: Option<Vec<String>>,
    pub mod_path: Option<String>,
    pub check_inventions: bool,
    pub inventions: Option<String>,
    pub explain_mob: Option<String>,
    pub mob_rate: f64,
    pub pop_per_regiment: Option<i64>,
    pub mob_types: Option<Vec<String>>,
    pub mob_include_occupied: bool,
    pub jobs: Option<i64>,
    pub no_cache: bool,
    pub map_scale: i64,
    pub player_nations: Option<Vec<String>>,
    pub explain_mob_pool: Option<String>,
    pub min_pop: i64,
    pub no_html: bool,
    pub rebuild: bool,
    pub split: bool,
    pub peek: bool,
    pub verify: bool,
    pub cross: bool,
    pub campaign_mod: Vec<(String, String)>,
    pub primary: Option<String>,
    pub game_root: Option<String>,
    pub quiet: bool,
}

fn opt_str(v: &J) -> Option<String> {
    v.as_str().map(|s| s.to_string())
}

fn opt_list(v: &J) -> Option<Vec<String>> {
    match v {
        J::List(x) => Some(x.iter().map(|e| e.str().to_string()).collect()),
        _ => None,
    }
}

fn opt_int(v: &J) -> Option<i64> {
    match v {
        J::Int(i) => Some(*i),
        _ => None,
    }
}

impl Args {
    /// A Run as `dataclasses.asdict` wrote it.
    pub fn from_json(j: &J) -> Args {
        Args {
            saves: j.at("saves").str().to_string(),
            out: j.at("out").str().to_string(),
            tags: opt_list(j.at("tags")),
            mod_path: opt_str(j.at("mod_path")),
            check_inventions: j.at("check_inventions").truthy(),
            inventions: opt_str(j.at("inventions")),
            explain_mob: opt_str(j.at("explain_mob")),
            mob_rate: j.at("mob_rate").float(),
            pop_per_regiment: opt_int(j.at("pop_per_regiment")),
            mob_types: opt_list(j.at("mob_types")),
            mob_include_occupied: j.at("mob_include_occupied").truthy(),
            jobs: opt_int(j.at("jobs")),
            no_cache: j.at("no_cache").truthy(),
            map_scale: j.at("map_scale").int(),
            player_nations: opt_list(j.at("player_nations")),
            explain_mob_pool: opt_str(j.at("explain_mob_pool")),
            min_pop: j.at("min_pop").int(),
            no_html: j.at("no_html").truthy(),
            rebuild: j.at("rebuild").truthy(),
            split: j.at("split").truthy(),
            peek: j.at("peek").truthy(),
            verify: j.at("verify").truthy(),
            cross: j.at("cross").truthy(),
            campaign_mod: j.at("campaign_mod").list().iter()
                .map(|p| (p.list()[0].str().to_string(), p.list()[1].str().to_string())).collect(),
            primary: opt_str(j.at("primary")),
            game_root: opt_str(j.at("game_root")),
            quiet: j.at("quiet").truthy(),
        }
    }

    /// `explain.asked`: one of the four diagnostics.
    fn asked(&self) -> bool {
        self.explain_mob.is_some() || self.explain_mob_pool.is_some() || self.inventions.is_some()
            || self.check_inventions
    }
}

// ------------------------------------------------------------ the saves

/// `_saves_in`: (the saves path, the .v2 files directly in it).
fn saves_in(args: &Args) -> R<(String, Vec<String>)> {
    let saves_path = pypath::expanduser(&pypath::expandvars(&args.saves));
    if !pypath::exists(&saves_path) {
        return refuse(format!(
            "Path not found: {}\nIf you used ~ in PowerShell, try $HOME instead, or give the full \
             path starting with C:\\Users\\...", saves_path));
    }
    if !isdir(&saves_path) {
        return Ok((saves_path.clone(), vec![saves_path]));
    }
    let names = match std::fs::read_dir(&saves_path) {
        Ok(rd) => rd,
        Err(e) => hand_back(&format!("cannot list {}: {}", saves_path, e)),
    };
    let mut files = Vec::new();
    for e in names {
        let name = match e.ok().and_then(|e| e.file_name().into_string().ok()) {
            Some(n) => n,
            None => hand_back("a file name among the saves is not text"),
        };
        if name.to_lowercase().ends_with(".v2") {
            files.push(join(&saves_path, &name));
        }
    }
    files.sort();
    if files.is_empty() && !args.cross {
        return refuse(format!(
            "No .v2 files in {}\nPoint this at the folder that holds your saves, not at a single save.",
            saves_path));
    }
    Ok((saves_path, files))
}

// ------------------------------------------------------ game and mod

/// `settle_game`: (the folder to read as the mod, the install it runs on).
fn settle_game(mod_path: Option<&str>, game_root: Option<&str>) -> R<(String, String)> {
    let mut game = None;
    if let Some(root) = game_root.filter(|r| !r.is_empty()) {
        let g = abspath(&pypath::expanduser(&pypath::expandvars(root)));
        if !modread::is_install(&g) {
            return refuse(format!(
                "{} is not a Victoria II install: there is no map/default.map in it. Point \
                 --game-root at the folder the game is installed in, the one holding map/, gfx/ \
                 and mod/.", root));
        }
        game = Some(g);
    }
    let mod_path = match mod_path.filter(|m| !m.is_empty()) {
        None => {
            return match game {
                None => refuse("Say where Victoria II is installed, with --game-root. The report is \
                                read on the game's own rules, or on a mod's when --mod-path names one \
                                inside the game's mod folder."),
                Some(g) => Ok((game_root.unwrap().to_string(), g)),
            };
        }
        Some(m) => m,
    };
    let m = abspath(&pypath::expanduser(&pypath::expandvars(mod_path)));
    let home = if modread::is_install(&m) { Some(m.clone()) } else { modread::base_game_path(&m) };
    let home = match home {
        Some(h) => h,
        None => return refuse(format!(
            "{} is not in a Victoria II install's mod folder. Put the mod -- its folder and its \
             .mod file -- in the mod folder of the game it runs on, where the game loads it from, \
             and point --mod-path at it there.", mod_path)),
    };
    if let Some(g) = &game {
        let same = pypath::normcase(&pypath::realpath(&home)) == pypath::normcase(&pypath::realpath(g));
        if !same {
            return refuse(format!(
                "{} is in the mod folder of {}, not of {}. Point --game-root at the install the mod \
                 is in, or leave it out.", mod_path, home, game_root.unwrap()));
        }
    }
    Ok((mod_path.to_string(), home))
}

/// `mod_reader._mod_root`.
fn mod_root(path: &str) -> String {
    abspath(&pypath::expanduser(&pypath::expandvars(path)))
}

/// `mod_signature`: every file of the mod and of the game folders it
/// inherits from, by path, size and time.
fn mod_signature(mod_path: Option<&str>) -> String {
    let path = match mod_path.filter(|m| !m.is_empty()) {
        None => return "no-mod".into(),
        Some(p) => mod_root(p),
    };
    let mut roots = vec![path.clone()];
    if let Some(base) = modread::base_game_path(&path) {
        for folder in ["common", "decisions", "gfx/flags", "inventions", "localisation", "map",
                       "poptypes", "technologies", "units"] {
            roots.push(join(&base, folder));
        }
    }
    let mut digest = Md5::new();
    for root in &roots {
        digest.update(root.as_bytes());
        sign_folder(&mut digest, root, "");
    }
    digest.hexdigest()
}

/// `vic2scan mod-signature PATH`: `mod_signature`, for holding to Python's.
pub fn signature_main(argv: &[String]) -> ! {
    println!("{}", mod_signature(argv.get(2).map(|s| s.as_str())));
    std::process::exit(0);
}

/// Nanoseconds since 1970, as `st_mtime_ns` gives them.
fn mtime_ns(m: &std::fs::Metadata) -> i128 {
    match m.modified() {
        Ok(t) => match t.duration_since(std::time::UNIX_EPOCH) {
            Ok(d) => d.as_nanos() as i128,
            Err(e) => -(e.duration().as_nanos() as i128),
        },
        Err(_) => 0,
    }
}

fn sign_folder(digest: &mut Md5, folder: &str, under: &str) {
    let rd = match std::fs::read_dir(folder) {
        Ok(rd) => rd,
        Err(_) => return,
    };
    let (mut files, mut folders) = (Vec::new(), Vec::new());
    for e in rd.flatten() {
        let name = e.file_name().to_string_lossy().to_string();
        let path = join(folder, &name);
        let link = e.file_type().map(|t| t.is_symlink()).unwrap_or(false);
        // `DirEntry.is_dir()` follows a link; `DirEntry.stat()` does too.
        let meta = if link { std::fs::metadata(&path) } else { e.metadata() };
        let is_dir = meta.as_ref().map(|m| m.is_dir()).unwrap_or(false);
        if is_dir {
            folders.push((name, link));
        } else {
            files.push((name, meta.ok()));
        }
    }
    files.sort_by(|a, b| a.0.cmp(&b.0));
    for (name, meta) in files {
        if let Some(m) = meta {
            digest.update(format!("{}|{}|{}\n", join(under, &name), m.len(), mtime_ns(&m)).as_bytes());
        }
    }
    folders.sort_by(|a, b| a.0.cmp(&b.0));
    for (name, link) in folders {
        if !link {
            sign_folder(digest, &join(folder, &name), &join(under, &name));
        }
    }
}

// ------------------------------------------------------------- the stamp

const STAMP_FILE: &str = "report.stamp";

/// The report's stamp: every save, this build, the mod's files and every
/// setting that changes a number in the report. Not Python's stamp -- that
/// one hashes the Python -- but the same things, by the same rule.
fn report_stamp(files: &[String], args: &Args, world: &str) -> String {
    let mut digest = Md5::new();
    let mut sorted: Vec<&String> = files.iter().collect();
    sorted.sort();
    for path in sorted {
        let m = match std::fs::metadata(path) {
            Ok(m) => m,
            Err(_) => return String::new(),
        };
        digest.update(format!("{}|{}|{}\n", abspath(path), m.len(), mtime_ns(&m)).as_bytes());
    }
    digest.update(format!("engine={}", env!("VIC2_BUILD_ID")).as_bytes());
    digest.update(format!("world={}", world).as_bytes());
    // `run.REPORTED`, in its order.
    let mut settings = String::new();
    let list = |v: &Option<Vec<String>>| match v {
        None => J::Null,
        Some(x) => J::List(x.iter().map(|s| J::Str(s.clone())).collect()),
    };
    let text = |v: &Option<String>| v.as_ref().map_or(J::Null, |s| J::Str(s.clone()));
    for (name, value) in [
        ("tags", list(&args.tags)),
        ("mod_path", text(&args.mod_path)),
        ("mob_rate", J::Float(args.mob_rate)),
        ("pop_per_regiment", args.pop_per_regiment.map_or(J::Null, J::Int)),
        ("mob_types", list(&args.mob_types)),
        ("mob_include_occupied", J::Bool(args.mob_include_occupied)),
        ("map_scale", J::Int(args.map_scale)),
        ("player_nations", list(&args.player_nations)),
        ("min_pop", J::Int(args.min_pop)),
        ("no_html", J::Bool(args.no_html)),
        ("split", J::Bool(args.split)),
        ("cross", J::Bool(args.cross)),
        ("campaign_mod", J::List(args.campaign_mod.iter()
            .map(|(a, b)| J::List(vec![J::Str(a.clone()), J::Str(b.clone())])).collect())),
        ("primary", text(&args.primary)),
        ("game_root", text(&args.game_root)),
    ] {
        settings.push_str(name);
        settings.push('=');
        value.write(&mut settings);
        settings.push('\n');
    }
    digest.update(settings.as_bytes());
    digest.hexdigest()
}

fn stamp_matches(outdir: &str, stamp: &str) -> bool {
    if stamp.is_empty() {
        return false;
    }
    let report = join(outdir, "report.html");
    match std::fs::metadata(&report) {
        Ok(m) if m.is_file() && m.len() > 0 => {}
        _ => return false,
    }
    match std::fs::read(join(outdir, STAMP_FILE)) {
        Ok(b) => match String::from_utf8(b) {
            Ok(s) => s.trim_matches(crate::pyfmt::py_space_char) == stamp,
            Err(_) => false,
        },
        Err(_) => false,
    }
}

fn write_stamp(outdir: &str, stamp: &str) {
    if stamp.is_empty() {
        return;
    }
    let _ = std::fs::create_dir_all(outdir);
    let _ = std::fs::write(join(outdir, STAMP_FILE), stamp);
}

fn forget_stamp(outdir: &str) {
    let _ = std::fs::remove_file(join(outdir, STAMP_FILE));
}

// ------------------------------------------------------------- the dates

/// A date's number, compared as Python compares ints: by length once the
/// leading zeros are gone, then digit by digit.
#[derive(PartialEq, Eq, PartialOrd, Ord, Clone)]
struct Whole(usize, String);

fn whole(p: &str) -> Option<Whole> {
    if p.is_empty() || !p.bytes().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let t = p.trim_start_matches('0');
    Some(Whole(t.len(), t.to_string()))
}

/// `savehead.sort_key`: (0, y, m, d), or after every date for none.
fn sort_key(date: &str) -> (u8, Option<[Whole; 3]>) {
    let parts: Vec<&str> = date.split('.').collect();
    if parts.len() == 3 {
        if let (Some(y), Some(m), Some(d)) = (whole(parts[0]), whole(parts[1]), whole(parts[2])) {
            return (0, Some([y, m, d]));
        }
    }
    (1, None)
}

/// `savehead.date_of`: `date\s*=\s*"([\d.]+)"` in the first 4 KB.
fn date_of(path: &str) -> String {
    use std::io::Read;
    let mut head = vec![0u8; 4096];
    let n = match std::fs::File::open(path) {
        Ok(mut f) => {
            let mut got = 0;
            loop {
                match f.read(&mut head[got..]) {
                    Ok(0) => break,
                    Ok(k) => {
                        got += k;
                        if got == head.len() {
                            break;
                        }
                    }
                    Err(_) => return String::new(),
                }
            }
            got
        }
        Err(_) => return String::new(),
    };
    let b = &head[..n];
    let ws = |c: u8| matches!(c, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c);
    let mut from = 0;
    while let Some(off) = b[from..].windows(4).position(|w| w == b"date") {
        let mut i = from + off + 4;
        while i < b.len() && ws(b[i]) {
            i += 1;
        }
        if i < b.len() && b[i] == b'=' {
            i += 1;
            while i < b.len() && ws(b[i]) {
                i += 1;
            }
            if i < b.len() && b[i] == b'"' {
                let start = i + 1;
                let mut j = start;
                while j < b.len() && (b[j].is_ascii_digit() || b[j] == b'.') {
                    j += 1;
                }
                if j > start && j < b.len() && b[j] == b'"' {
                    return String::from_utf8_lossy(&b[start..j]).to_string();
                }
            }
        }
        from += off + 1;
    }
    String::new()
}

/// `dates_of`: every save's date, the files opened side by side.
fn dates_of(files: &[String]) -> Vec<String> {
    let mut out = vec![String::new(); files.len()];
    let threads = files.len().clamp(1, 16);
    let next = std::sync::atomic::AtomicUsize::new(0);
    let slots: Vec<std::sync::Mutex<String>> = files.iter().map(|_| std::sync::Mutex::new(String::new())).collect();
    std::thread::scope(|s| {
        for _ in 0..threads {
            s.spawn(|| loop {
                let i = next.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                if i >= files.len() {
                    break;
                }
                *slots[i].lock().unwrap() = date_of(&files[i]);
            });
        }
    });
    for (i, slot) in slots.into_iter().enumerate() {
        out[i] = slot.into_inner().unwrap();
    }
    out
}

/// `in_date_order` and `one_per_date`: the saves oldest first, one a
/// date, the later-named file kept, and a note for every date that had more.
fn in_date_order(files: Vec<String>, dates: Vec<String>) -> Vec<String> {
    let mut both: Vec<(String, String)> = files.into_iter().zip(dates).collect();
    both.sort_by(|a, b| (sort_key(&a.1), &a.0).cmp(&(sort_key(&b.1), &b.0)));
    let mut kept: Vec<String> = Vec::new();
    let mut keys = Vec::new();
    let mut clash: Vec<(String, Vec<String>)> = Vec::new();
    for (path, date) in both {
        let key = sort_key(&date);
        if !kept.is_empty() && key.0 == 0 && Some(&key) == keys.last() {
            let last = kept.last().unwrap().clone();
            match clash.iter_mut().find(|(d, _)| *d == date) {
                Some((_, same)) => same.push(path.clone()),
                None => clash.push((date.clone(), vec![last, path.clone()])),
            }
            *kept.last_mut().unwrap() = path;
            continue;
        }
        kept.push(path);
        keys.push(key);
    }
    for (date, same) in clash {
        let names: Vec<String> = same.iter().map(|p| basename(p)).collect();
        crate::errln!("note: {} are all dated {}, so only {} is read. Saves from two games in one \
                       folder? Keep each game in a folder of its own.",
                      names.join(", "), date, basename(same.last().unwrap()));
    }
    kept
}

// ------------------------------------------------------ fixed tables

const VANILLA_POP_TYPES: [&str; 12] = ["aristocrats", "artisans", "bureaucrats", "capitalists",
    "clergymen", "clerks", "craftsmen", "farmers", "labourers", "officers", "slaves", "soldiers"];
const MOBILIZABLE_TYPES: [&str; 3] = ["craftsmen", "farmers", "labourers"];
const POP_SIZE_PER_REGIMENT: i64 = 3000;

/// `tech_groups.ARMY_LINES` and `NAVY_LINES`.
pub const ARMY_LINES: [(&str, [&str; 5]); 5] = [
    ("Doctrine", ["post_napoleonic_thought", "strategic_mobility", "point_defense_system",
                  "deep_defense_system", "infiltration"]),
    ("Small arms", ["flintlock_rifles", "muzzle_loaded_rifles", "breech_loaded_rifles",
                    "machine_guns", "bolt_action_rifles"]),
    ("Artillery", ["bronze_muzzle_loaded_artillery", "iron_muzzle_loaded_artillery",
                   "iron_breech_loaded_artillery", "steel_breech_loaded_artillery",
                   "indirect_artillery_fire"]),
    ("Military science", ["military_staff_system", "military_plans", "military_statistics",
                          "military_logistics", "military_directionism"]),
    ("Leadership", ["army_command_principle", "army_professionalism", "army_decision_making",
                    "army_risk_management", "army_nco_training"]),
];
pub const NAVY_LINES: [(&str, [&str; 5]); 5] = [
    ("Naval doctrine", ["post_nelsonian_thought", "battleship_column_doctrine",
                        "raider_group_doctrine", "blue_and_brown_water_schools",
                        "high_sea_battle_fleet"]),
    ("Hulls", ["clipper_design", "steamers", "iron_steamers", "steel_steamers",
               "steam_turbine_ships"]),
    ("Naval engineering", ["naval_design_bureaus", "fire_control_systems", "weapon_platforms",
                           "main_armament", "advanced_naval_design"]),
    ("Naval science", ["alphabetic_flag_signaling", "naval_plans", "naval_statistics",
                       "naval_logistics", "naval_directionism"]),
    ("Naval leadership", ["the_command_principle", "naval_professionalism",
                          "naval_decision_making", "naval_risk_management", "naval_nco_training"]),
];

fn lines_json(lines: &[(&str, [&str; 5]); 5]) -> J {
    J::List(lines.iter().map(|(name, techs)| {
        J::List(vec![J::Str(name.to_string()),
                     J::List(techs.iter().map(|t| J::Str(t.to_string())).collect())])
    }).collect())
}

fn techs_json(lines: &[(&str, [&str; 5]); 5]) -> J {
    let mut all: Vec<&str> = lines.iter().flat_map(|(_, t)| t.iter().copied()).collect();
    all.sort();
    J::List(all.into_iter().map(|t| J::Str(t.to_string())).collect())
}

fn strs(v: &[String]) -> J {
    J::List(v.iter().map(|s| J::Str(s.clone())).collect())
}

// ------------------------------------------------------------- the run

/// `vic2scan analyze --run RUN.json`.
pub fn main(argv: &[String]) -> ! {
    out::hold();
    out::set_protocol(false);
    let args = match (argv.get(2).map(|s| s.as_str()), argv.get(3)) {
        (Some("--run"), Some(file)) => {
            let text = std::fs::read_to_string(file)
                .unwrap_or_else(|e| hand_back(&format!("cannot read {}: {}", file, e)));
            let j = crate::jsonr::parse(&text).unwrap_or_else(|e| hand_back(&format!("{}: {}", file, e)));
            Args::from_json(&j)
        }
        _ => hand_back("usage: vic2scan analyze --run RUN.json"),
    };
    // A host that wants a refusal as its own (`--refused FILE`: Python,
    // which raises it as the `RunError` it always raised) gets the sentence
    // in that file and status 4; otherwise it is said, and the status is 1.
    let refused_to = argv.iter().position(|a| a == "--refused").and_then(|i| argv.get(i + 1));
    let code = match run(args) {
        Ok(code) => code,
        Err(RunError(why)) => match refused_to {
            Some(file) => match std::fs::write(file, why.as_bytes()) {
                Ok(()) => 4,
                Err(_) => {
                    crate::errln!("{}", why);
                    1
                }
            },
            None => {
                crate::errln!("{}", why);
                1
            }
        },
    };
    crate::engine::front_log(&format!("done: status {}", code));
    out::release();
    std::process::exit(code);
}

fn run(mut args: Args) -> R<i32> {
    let (_saves_path, files) = saves_in(&args)?;
    if args.peek {
        hand_back("--peek is read in Python");
    }
    if args.cross {
        hand_back("--cross is read in Python");
    }
    if args.verify {
        hand_back("--verify is read in Python");
    }

    // `_on_the_game`.
    let (mod_path, game) = settle_game(args.mod_path.as_deref(), args.game_root.as_deref())?;
    let settled = format!("Victoria II at {}, {}", game,
        if modread::is_install(&mod_path) { "unmodded.".to_string() }
        else { format!("with {}.", basename(&pypath::normpath(&mod_path))) });
    args.mod_path = Some(mod_path);

    if let Err(e) = std::fs::create_dir_all(&args.out) {
        let text = e.to_string();
        let strerror = match text.rfind(" (os error ") {
            Some(i) => text[..i].to_string(),
            None => text,
        };
        return refuse(format!("Cannot write to {}\n{}. Choose somewhere else with --out.",
                              args.out, strerror));
    }
    let verbose = !args.quiet;
    if verbose {
        crate::outln!("Found {} save(s).", files.len());
        crate::outln!("{}", settled);
    }

    let signature = mod_signature(args.mod_path.as_deref());
    let stamp = report_stamp(&files, &args, &signature);
    if !(args.rebuild || args.no_html || args.asked()) && stamp_matches(&args.out, &stamp) {
        if verbose {
            crate::outln!("Nothing has changed since this was built. Opening it as it is.\n\nWrote:\n  {}",
                          join(&args.out, "report.html"));
        }
        return Ok(0);
    }
    if args.asked() {
        hand_back("the diagnostics are read in Python");
    }

    // `_mod_head`: what reading a save needs of the mod.
    let root = mod_root(args.mod_path.as_deref().unwrap());
    match modread::has_rules(&root) {
        Ok(true) => {}
        Ok(false) => return refuse(format!(
            "{} has no technologies/ or inventions/ folder. Point --mod-path at the folder that \
             contains them (the mod root, or the Victoria 2 install folder for vanilla).", root)),
        Err(e) => match modread::raised_sentence(&e) {
            Some(sentence) => return refuse(sentence),
            None => hand_back(&e.0),
        },
    }
    let head = match modread::head(&root) {
        Ok(h) => h,
        Err(e) => match modread::raised_sentence(&e) {
            Some(sentence) => return refuse(sentence),
            None => hand_back(&e.0),
        },
    };

    // `mod_defaults`: the regiment size and the mobilizable pops, the
    // mod's unless the command line said.
    let pop_per_regiment = match args.pop_per_regiment {
        Some(n) => n,
        None => match head.defines.get(&b"POP_SIZE_PER_REGIMENT".to_vec()) {
            Some(v) if v.is_finite() && v.abs() < 9.0e18 => v.trunc() as i64,
            Some(_) => hand_back("POP_SIZE_PER_REGIMENT is not a number an int can hold"),
            None => POP_SIZE_PER_REGIMENT,
        },
    };
    let mob_types: Vec<String> = match &args.mob_types {
        Some(t) => t.clone(),
        None => {
            let mut from_mod: Vec<String> = head.strata.iter()
                .filter(|(name, layer)| layer.as_slice() == b"poor"
                        && name.as_str() != "soldiers" && name.as_str() != "slaves")
                .map(|(name, _)| name.clone()).collect();
            if from_mod.is_empty() {
                from_mod = MOBILIZABLE_TYPES.iter().map(|s| s.to_string()).collect();
            }
            from_mod.sort();
            from_mod
        }
    };
    if verbose {
        let mut extra: Vec<&String> = head.strata.keys()
            .filter(|n| !VANILLA_POP_TYPES.contains(&n.as_str())).collect();
        extra.sort();
        crate::outln!("defines.lua: POP_SIZE_PER_REGIMENT={}", pop_per_regiment);
        crate::outln!("poptypes/: mobilizable = {}{}", mob_types.join(" "),
            if extra.is_empty() { String::new() } else {
                format!("; mod-only pop types read: {}",
                        extra.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(" "))
            });
    }

    // `reading_for`.
    let mut pop_types: Vec<String> = VANILLA_POP_TYPES.iter().map(|s| s.to_string()).collect();
    for name in head.strata.keys() {
        if !name.is_empty() && !pop_types.contains(name) {
            pop_types.push(name.clone());
        }
    }
    pop_types.sort();
    let mut reading_mob = mob_types.clone();
    reading_mob.sort();
    let reform_keys: Vec<String> = head.reform_names.iter().map(|r| modread::l1(r)).collect();
    let mut regions: Vec<(i64, String)> = head.province_regions.iter()
        .map(|(p, r)| (*p, modread::l1(r))).collect();
    regions.sort();
    let mut representatives: Vec<(String, i64)> = Vec::new();
    let mut groups = Vec::new();
    for (pid, region) in &regions {
        if region.is_empty() {
            continue;
        }
        let rep = match representatives.iter().find(|(r, _)| r == region) {
            Some((_, p)) => *p,
            None => {
                representatives.push((region.clone(), *pid));
                *pid
            }
        };
        groups.push(J::List(vec![J::Int(*pid), J::Int(rep)]));
    }

    let dates = dates_of(&files);
    let files = in_date_order(files, dates);
    let wanted = args.tags.as_ref().filter(|t| !t.is_empty()).map(|t| {
        let mut w = t.clone();
        w.sort();
        w.dedup();
        w
    });

    forget_stamp(&args.out);
    let mut finish_mob = mob_types.clone();
    finish_mob.sort();
    finish_mob.dedup();
    let spec = J::Obj(vec![
        ("files".into(), strs(&files)),
        ("out".into(), J::Str(args.out.clone())),
        ("reading".into(), J::Obj(vec![
            ("pop_types".into(), strs(&pop_types)),
            ("mob_types".into(), strs(&reading_mob)),
            ("reform_keys".into(), strs(&reform_keys)),
            ("population_groups".into(), J::List(groups)),
            ("army_techs".into(), techs_json(&ARMY_LINES)),
            ("navy_techs".into(), techs_json(&NAVY_LINES)),
        ])),
        ("finish".into(), J::Obj(vec![
            ("rate".into(), J::Float(args.mob_rate)),
            ("pop_per_regiment".into(), J::Int(pop_per_regiment)),
            ("mob_types".into(), strs(&finish_mob)),
            ("include_occupied".into(), J::Bool(args.mob_include_occupied)),
            ("player_nations".into(), match &args.player_nations {
                None => J::Null,
                Some(p) => {
                    let mut p = p.clone();
                    p.sort();
                    p.dedup();
                    strs(&p)
                }
            }),
            ("wanted".into(), wanted.as_ref().map_or(J::Null, |w| strs(w))),
            ("min_pop".into(), J::Int(args.min_pop)),
        ])),
        ("head".into(), J::Obj(vec![
            ("defines".into(), J::Obj(head.defines.iter()
                .map(|(k, v)| (modread::l1(k), J::Float(*v))).collect())),
            ("province_regions".into(), J::List(head.province_regions.iter()
                .map(|(p, r)| J::List(vec![J::Int(*p), J::Str(modread::l1(r))])).collect())),
        ])),
        ("tech_lines".into(), J::Obj(vec![("army".into(), lines_json(&ARMY_LINES)),
                                          ("navy".into(), lines_json(&NAVY_LINES))])),
        ("pop_columns".into(), strs(&pop_types)),
        ("no_html".into(), J::Bool(args.no_html)),
        ("split".into(), J::Bool(args.split)),
        ("map_scale".into(), J::Int(args.map_scale)),
        ("quiet".into(), J::Bool(args.quiet)),
        ("jobs".into(), args.jobs.map_or(J::Null, J::Int)),
        ("cross".into(), J::Null),
        ("cache".into(), J::Obj(vec![
            ("dir".into(), J::Str(join(&pypath::gettempdir(), "vic2_analyzer_cache"))),
            ("version".into(), J::Str(env!("VIC2_BUILD_ID").to_string())),
            ("on".into(), J::Bool(!args.no_cache)),
        ])),
        ("mod_path".into(), J::Str(root.clone())),
        ("mod_signature".into(), J::Str(signature.clone())),
        ("protocol".into(), J::Bool(false)),
        ("own_refusals".into(), J::Bool(true)),
    ]);
    let done = crate::engine::run_spec(&spec, None).expect("a report run returns what it wrote");
    if let Some(sentence) = done.run_error {
        return refuse(sentence);
    }
    if done.html.is_some() && done.refused.is_empty() {
        write_stamp(&args.out, &stamp);
    }
    if !done.refused.is_empty() {
        let names: Vec<String> = done.refused.iter().map(|p| basename(p)).collect();
        return refuse(format!(
            "\nCould not write {}: open in another program -- on Windows a table open in Excel is \
             locked -- or not writable here. Close it and run again.{}",
            names.join(", "),
            if done.html.is_some() { " The report itself was written." } else { "" }));
    }
    Ok(0)
}

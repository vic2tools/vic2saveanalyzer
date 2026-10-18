// The report engine: a whole run, from the saves to the report.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The spec is what the front end (`front`) makes of a run: the saves in
// report order, how each is read, how each nation is finished, and where the
// report goes. The mod folder is named there too (`mod_path`), and read here
// (`modread`) on a thread of its own while the saves are.
//
// Every save is read on every core (`prepare`, pass one), the campaign's
// inventions are settled, every save is finished (`finish`, pass two), and
// the campaign is walked in date order into the tables and the page.
//
// Anything it cannot read at all -- a number past what an int holds, a block
// where a list belongs -- stops the run with a sentence (`decline`).

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
pub mod pool;
pub mod readsave;
pub mod report;
pub mod rules;
pub mod tables;
pub mod wars;

use finish::{Pre, Spec, Spent};
use crate::py::json::J;
use model::Save;
use crate::util::fx::{FxMap, FxSet};
use rules::{Decline, Mod, D};
use std::io::Write;
use pool::{in_order, worker_count};
use crate::py::path::basename;
use readsave::{read_save, Refused};

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

/// A run, as the front end settles it: the saves in report order, how each
/// is read and finished, and where the report goes.
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
    /// The `--cross` comparison, as the page carries it.
    pub cross: Option<String>,
    /// The mod folder, read here (`modread`).
    pub mod_path: Option<String>,
    /// The mod's signature, which keys the read kept for the next run;
    /// None when the front did not work it out (a `--cross` run).
    pub mod_signature: Option<String>,
    /// One of the four diagnostics, answered instead of the report.
    pub ask: Option<explain::Ask>,
    /// One campaign of a `--cross` run: read once, quietly, for its rows.
    pub cross_part: bool,
    pub tech_lines: J,
    pub tables: tables::Tables,
    pub store: cache::Store,
    /// What besides the file decides what pass one makes of it, for the
    /// cache's key: the reading and the settings `prepare` takes.
    pub context: String,
    /// The reading alone, which keys the "read before" markers.
    pub reading_context: String,
}

/// The cache's names for what decides what pass one makes of a save:
/// (the reading and what `prepare` is told, the reading alone). Maps and
/// sets are written in sorted order, so the same settings give the same
/// names on every run.
pub fn contexts(reading: &Reading, spec: &Spec) -> (String, String) {
    let mut groups: Vec<(i64, i64)> = reading.population_groups.iter().map(|(a, b)| (*a, *b)).collect();
    groups.sort();
    let read = format!("{:?}|{:?}|{:?}|{:?}|{:?}|{:?}", reading.pop_types, reading.mob_types,
                       reading.reform_keys, groups, reading.army_techs, reading.navy_techs);
    let mut mob: Vec<&str> = spec.mob_types.iter().map(|s| crate::save::names::text(*s)).collect();
    mob.sort();
    let wanted = spec.wanted.as_ref().map(|w| {
        let mut w: Vec<&String> = w.iter().collect();
        w.sort();
        w
    });
    let mut defines: Vec<(&String, u64)> = spec.defines.iter().map(|(k, v)| (k, v.to_bits())).collect();
    defines.sort();
    let mut regions: Vec<(&i64, &String)> = spec.regions.iter().collect();
    regions.sort();
    let whole = format!("{}|{}|{:?}|{}|{:?}|{:?}|{}|{:?}|{:?}", read, spec.pop_per_regiment, mob,
                        spec.include_occupied, spec.player_nations, wanted, spec.min_pop,
                        defines, regions);
    let name = |text: &str| {
        let mut h = crate::util::hash::TwoLane::new();
        h.update(text.as_bytes());
        h.hex()
    };
    (name(&whole), name(&read))
}

/// A line for the host to read: progress, and the like.
pub fn say(line: &str) {
    out::protocol(line);
}

/// Stop the run over something it cannot read: a number past what an int
/// holds, a block where a list belongs -- input the Python this replaced
/// would have crashed on too. Said as a sentence, and the run ends with
/// status 1, the status of every other run that does not finish.
pub fn decline(why: &str) -> ! {
    crate::errln!("Stopped: {}. This is something the analyzer cannot read; if it came from a \
                   save or a mod the game itself loads, please report it with that file.", why);
    std::process::exit(1);
}

/// The mod: read from its folder, or from what the last run kept of the
/// same files.
fn load_mod(mod_path: &Option<String>, signature: &Option<String>,
            store: &cache::Store) -> D<Mod> {
    let j = match mod_path {
        Some(path) => {
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
        None => decline("no mod was named"),
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

/// `vic2scan bench-engine RUN.json N`: the first N saves read one at a time,
/// by the run's own readers, timing the read and the preparing.
pub fn bench(run: &Run, n: usize) {
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
}

/// A run as the front end settles it. A run handed back never returns.
pub fn run(run: Run) -> report::Outcome {
    phase("start");
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
    // Which saves had no marker when the run began: only those are marked
    // after (a marker that is there is empty, and writing it again only costs
    // a file operation a save, on the one thread that is waiting).
    let unmarked: Vec<bool> = marks.iter()
        .map(|m| m.as_ref().is_none_or(|m| !std::path::Path::new(m).is_file())).collect();
    let todo = unmarked.iter().filter(|&&u| u).count();
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
        let mod_path = run.mod_path.clone();
        let (signature, store) = (run.mod_signature.clone(), run.store.clone());
        let (scale, want_map) = (run.map_scale, !run.no_html);
        std::thread::spawn(move || {
            let m = load_mod(&mod_path, &signature, &store)?;
            let raster = want_map
                .then(|| crate::engine::mapflags::province_raster(&m.map_bmp, &m.map_csv, scale));
            Ok::<_, Decline>((m, raster))
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
            got.map(|save| {
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
                        let months: FxSet<crate::save::names::Sym> = pre.meta.market.as_ref()
                            .map(|m| m.history.iter().map(|h| h.0).collect())
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
        if let (Some(m), true) = (&marks[i], unmarked[i]) {
            run.store.mark(m);
        }
    }
    // Python's campaign entry is made by the invention pass of a report,
    // which one campaign of a comparison does not have.
    if let Some(c) = campaign.as_ref().filter(|_| !run.cross_part) {
        run.store.mark(c);
    }
    let files: Vec<String> = kept.iter().map(|&i| run.files[i].clone()).collect();
    let pres: Vec<Pre> = pres.into_iter().flatten().collect();
    let n = pres.len();
    phase("pass one: saves read and prepared");

    // The campaign's inventions, settled against the mod.
    let (m, raster) = match mod_job.join().unwrap_or_else(|_| decline("the mod could not be read")) {
        Ok(m) => m,
        // A mod Python raises over is refused when Python asks for it,
        // which is now, with every save read once.
        Err(d) => match d.raised() {
            Some(sentence) => {
                return report::Outcome { html: None, refused: Vec::new(),
                                         run_error: Some(sentence.to_string()),
                                         cross_part: None };
            }
            None => decline(&format!("the mod: {}", d.text())),
        },
    };
    let held: Vec<&[finish::PreNation]> = pres.iter().map(|p| p.nations.as_slice()).collect();
    phase("mod loaded");
    let (m, live) = rules::settle_campaign(m, &held, &run.spec.tech_group, raster);
    phase("inventions settled");
    if verbose {
        crate::engine::report::say_mod(&m, &live, &held, &files);
    }
    // The second pass read every file again, and named each refused one
    // again as it went past. A campaign of a comparison is read once.
    if !run.cross_part {
        for line in &skipped {
            crate::errln!("{}", line);
        }
    }
    if pres.is_empty() && run.cross_part {
        return report::Outcome { html: None, refused: Vec::new(), run_error: None,
                                 cross_part: None };
    }
    if pres.is_empty() {
            return report::Outcome { html: None, refused: Vec::new(),
                                 run_error: Some("No saves could be read.".into()), cross_part: None };
    }
    // A diagnostic is answered off the campaign as it stands, and ends the
    // run: no report, no tables.
    if let Some(ask) = &run.ask {
        let said = explain::answer(ask, &run.spec, &m, &live, &pres, &files, &run.reading);
        return report::Outcome { html: None, refused: Vec::new(), run_error: said.err(),
                                 cross_part: None };
    }

    // What `--cross` names each nation by: every nation of every save, in
    // order, with its government.
    let held_names: Vec<(String, String)> = if run.cross_part {
        pres.iter().flat_map(|p| p.nations.iter()
            .map(|n| (n.tag.clone(), n.nat.government.clone()))).collect()
    } else { Vec::new() };

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
        Err(d) => {
            if declined.is_none() {
                declined = Some(d.text().to_string());
            }
        }
    });
    if let Some(why) = declined {
        decline(&why);
    }
    let spent: Vec<Spent> = spent.into_iter().map(|s| s.unwrap()).collect();
    phase("pass two: saves finished");
    if run.cross_part {
        return report::Outcome { html: None, refused: Vec::new(), run_error: None,
                                 cross_part: Some(cross_part(&run, &m, &held_names, &spent)) };
    }
    let done = crate::engine::report::run(&run, &m, spent);
    // As the campaign in `report::run`: the process ends with this run. A
    // campaign of a `--cross` run, one of several, is freed as it returns.
    std::mem::forget((run, m, live));
    done
}

/// One campaign of a `--cross` run, as `campaign_rows` and `run_cross`
/// keep it.
fn cross_part(run: &Run, m: &Mod, held: &[(String, String)], spent: &[Spent]) -> report::CrossPart {
    let keys: Vec<&str> = run.tables.metrics.iter().map(|k| k.0.as_str()).collect();
    let mut rows = Vec::new();
    for s in spent {
        for r in &s.rows {
            rows.push((r.date.clone(), r.key.clone(), keys.iter().map(|k| r.get(k).float()).collect()));
        }
    }
    // The nations the mod names other than by their tags.
    let mut names = Vec::new();
    for (tag, government) in held {
        let label = report::name_for(tag, government, m);
        if label != *tag {
            names.push((tag.clone(), label));
        }
    }
    report::CrossPart { rows, names }
}

/// The keys a save's nations are held under: the owner tags the provinces
/// named, which `model::build` kept in `Nation.key`.
fn keys_of(save: &Save) -> Vec<String> {
    save.nations.iter().map(|n| n.key.clone()).collect()
}

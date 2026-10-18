// The campaign walked into the tables and the page: `walk_campaign`,
// `build_html`, `report.build_report`, `write_outputs` and `_say_summary`.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The payload is written straight out as JSON, in the order Python built
// its dicts, rather than built as a tree first: it is thirty megabytes on a
// long campaign, and the order of every key is part of what is compared.

use crate::save::country::Stack;
use crate::engine::dates::{date_key, year_fraction};
use crate::engine::dump::{int_keyed, obj};
use crate::engine::{say, Run};
use crate::engine::finish::{escape_angles, Kept, Profile, Row, Spent, Val};
use crate::engine::tables::Tables;
use crate::py::json::J;
use crate::engine::mapflags;
use crate::engine::market::{self, PriceRow, SnapRow};
use crate::engine::model::Meta;
use crate::save::names::{self, Sym};
use crate::util::omap::OMap;
use crate::util::fx::{FxMap, FxSet};
use crate::py::fmt::{push_csv_field, push_int, push_json_float, push_json_str, round};
use crate::engine::rules::{self, Mod};
use crate::engine::wars::{self, Book, Mapping};
use std::io::Write;

mod csv;
mod map;
mod say;
mod sections;

pub use say::{say_mod, thousands};
pub(crate) use say::unreadable;
pub use sections::{gain_series, growth_series};
use csv::*;
use map::*;
use say::*;
use sections::*;

/// A save as the rest of the run keeps it: `(meta, nations)` trimmed.
pub struct Kept1 {
    pub meta: Meta,
    pub nations: Vec<Kept>,
    pub chunk: String,
}

/// {tag: {date: value}}, in first-appearance order.
type ByTag<V> = OMap<String, OMap<String, V>>;

/// `walk_campaign`'s answer.
struct Campaign {
    rows: Vec<Row>,
    ships: ByTag<Vec<(Sym, i64)>>,
    crews: ByTag<Vec<(Sym, f64)>>,
    brigades: ByTag<Vec<(Sym, i64)>>,
    techs: ByTag<Vec<String>>,
    pops: ByTag<Vec<(Sym, i64)>>,
    cultures: ByTag<Vec<(String, i64, i64)>>,
    text: [Vec<String>; 6],
    naval_profiles: Vec<Profile>,
    naval_of: ByTag<usize>,
    supply: OMap<String, OMap<String, OMap<String, f64>>>,
    parsed: Vec<Kept1>,
    book: Book,
}

fn add_table<V>(table: &mut ByTag<V>, date: &str, part: Vec<(String, V)>) {
    for (tag, v) in part {
        table.entry(tag, OMap::new).set(date.to_string(), v);
    }
}

fn walk(mut spent: Vec<Spent>) -> Campaign {
    // The war book takes only the wars, oldest save first, and nothing else
    // takes them: it is folded on a thread of its own beside the rest.
    let wars: Vec<Vec<crate::engine::model::War>> =
        spent.iter_mut().map(|s| std::mem::take(&mut s.meta.wars)).collect();
    std::thread::scope(|scope| {
        let book = scope.spawn(move || {
            let mut book = Book::default();
            for w in &wars {
                book.fold_save(w);
            }
            // Nothing needs the records once they are folded, and freeing
            // them (millions of small allocations) is slower than the rest
            // of the walk: a thread nothing joins does it, and the process
            // may end first, which only skips the work.
            std::thread::spawn(move || drop(wars));
            book
        });
        let mut c = walk_tables(spent);
        c.book = book.join().unwrap();
        c
    })
}

fn walk_tables(spent: Vec<Spent>) -> Campaign {
    let mut c = Campaign {
        rows: Vec::new(), ships: OMap::new(), crews: OMap::new(), brigades: OMap::new(),
        techs: OMap::new(), pops: OMap::new(), cultures: OMap::new(),
        text: Default::default(), naval_profiles: Vec::new(), naval_of: OMap::new(),
        supply: OMap::new(), parsed: Vec::new(), book: Book::default(),
    };
    let mut naval_index: FxMap<String, usize> = FxMap::default();
    for s in spent {
        let date = s.meta.date.clone();
        c.rows.extend(s.rows);
        add_table(&mut c.ships, &date, s.tables.ships);
        add_table(&mut c.crews, &date, s.tables.crews);
        add_table(&mut c.brigades, &date, s.tables.brigades);
        add_table(&mut c.techs, &date, s.tables.techs);
        add_table(&mut c.pops, &date, s.tables.pops);
        add_table(&mut c.cultures, &date, s.tables.cultures);
        for (i, t) in s.text.into_iter().enumerate() {
            c.text[i].push(t);
        }
        for (tag, key, profile) in s.naval {
            let n = c.naval_profiles.len();
            let idx = *naval_index.entry(key).or_insert_with(|| n);
            if idx == n {
                c.naval_profiles.push(profile);
            }
            c.naval_of.entry(tag, OMap::new).set(date.clone(), idx);
        }
        for (good, tag, amount) in s.supply {
            c.supply.entry(good, OMap::new).entry(date.clone(), OMap::new).set(tag, amount);
        }
        let meta = s.meta;
        c.parsed.push(Kept1 { meta, nations: s.nations, chunk: s.chunk });
    }
    c
}

/// What a run left on disk: the report, if one was built, and the tables
/// that could not be written.
pub struct Outcome {
    pub html: Option<String>,
    pub refused: Vec<String>,
    /// The run refused, in the sentence Python raises: every save refused,
    /// a mod Python cannot read.
    pub run_error: Option<String>,
    /// One campaign of a `--cross` run, read for the comparison.
    pub cross_part: Option<CrossPart>,
}

/// What `run_cross` keeps of one campaign: its finished rows as (date, the
/// nation's key, each metric's value), and the names its nations go by.
pub struct CrossPart {
    pub rows: Vec<(String, String, Vec<Option<f64>>)>,
    /// (tag, name) where the mod's localisation names a nation other than
    /// by its tag, in the order the saves give them.
    pub names: Vec<(String, String)>,
}

pub fn run(run: &Run, m: &Mod, spent: Vec<Spent>) -> Outcome {
    let c = walk(spent);
    crate::engine::phase("walked");
    let metas: Vec<&Meta> = c.parsed.iter().map(|k| &k.meta).collect();
    let prices = market::merge_prices(&metas, &run.tables);
    let snaps = market::snapshot_rows(&metas, &run.tables);
    let out = &run.out;
    let _ = std::fs::create_dir_all(out);
    let mut html_path: Option<String> = None;
    let mut tables: (Vec<String>, Vec<String>, Vec<String>) = (Vec::new(), Vec::new(), Vec::new());
    let mut page_failed: Option<String> = None;
    std::thread::scope(|s| {
        let csv = s.spawn(|| write_outputs(out, &c, &prices, &snaps, &run.tables));
        if !run.no_html {
            match page(run, m, &c, &prices, &snaps) {
                Ok(p) => {
                    say(&format!("@ready {}", p));
                    html_path = Some(p);
                }
                Err(why) => page_failed = Some(why),
            }
        }
        tables = csv.join().unwrap();
        crate::engine::phase("tables written");
    });
    let (mut paths, refused, mut failed) = tables;
    if let Some(why) = page_failed {
        failed.insert(0, why);
    }
    if !failed.is_empty() {
        for line in &failed {
            crate::errln!("{}", line);
        }
        std::process::exit(1);
    }
    if let Some(h) = &html_path {
        paths.insert(0, h.clone());
    }
    if !run.quiet {
        say_summary(&c, &prices, &paths);
    }
    let _ = std::io::stdout().flush();
    say(&format!("@done html={} refused={}", html_path.is_some() as i32,
                 refused.iter().map(|p| crate::py::path::basename(p))
                     .collect::<Vec<_>>().join("\t")));
    // The process ends with this run, and the system takes its memory back
    // whole: freeing the campaign a string at a time first cost ~0.3 s.
    std::mem::forget((c, prices, snaps));
    Outcome { html: html_path, refused, run_error: None, cross_part: None }
}

/// `build_html` and `build_report`: the page, written; its path.
fn page(run: &Run, m: &Mod, c: &Campaign, prices: &[PriceRow], snaps: &[SnapRow])
        -> Result<String, String> {
    let t = &run.tables;
    let rows = &c.rows;
    let mut dates: Vec<String> = Vec::new();
    let mut seen: FxSet<&str> = FxSet::default();
    for r in rows {
        if seen.insert(&r.date) {
            dates.push(r.date.clone());
        }
    }
    dates.sort_by(|a, b| year_fraction(a).partial_cmp(&year_fraction(b)).unwrap_or(std::cmp::Ordering::Equal));
    let mut tags: Vec<String> = rows.iter().map(|r| r.facts.tag.clone()).collect();
    tags.sort();
    tags.dedup();

    // The payload's sections do not depend on one another, so each is
    // made on a thread of its own and they are laid end to end after, in
    // the order Python's dict holds them.
    let (built, map, (great_powers, flags), succession_json, series_facts, tables, (market, price_ends)) =
        std::thread::scope(|s| {
            let wars_job = s.spawn(|| {
                let mapping = Mapping { province_names: &m.province_names,
                                        province_regions: &m.province_regions,
                                        state_names: &m.state_names, unit_kinds: &m.unit_kinds };
                let owners: Vec<(String, Vec<(i64, Sym)>)> = c.parsed.iter()
                    .map(|k| (k.meta.date.clone(),
                              k.meta.province_owner.iter().map(|(p, o, _)| (*p, *o)).collect()))
                    .collect();
                wars::build(&c.book, &owners, &mapping)
            });
            // A run that makes a page decodes the map beside the mod (`engine::run`).
            let raster = m.raster.as_ref().expect("the map is decoded for every page");
            let map_job = s.spawn(move || build_map(m, raster, &c.parsed, run.map_scale));
            let flags_job = s.spawn(|| flags_for(m, &c.parsed, &c.book));
            let succession_job = s.spawn(|| succession(&c.parsed, m));
            let series_job = s.spawn(|| section_series_facts(run, rows, &dates, &tags));
            let tables_job = s.spawn(|| section_tables(run, c));
            let market_job = s.spawn(|| section_market(run, m, c, prices, snaps, &dates));
            (wars_job.join().unwrap(), map_job.join().unwrap(), flags_job.join().unwrap(),
             succession_job.join().unwrap(), series_job.join().unwrap(),
             tables_job.join().unwrap(), market_job.join().unwrap())
        });
    crate::engine::phase("payload sections made");
    let war_tags = wars::war_tags(&built);
    // `nation_names`: every nation of every save, the later government winning.
    let mut tag_names: FxMap<String, String> = FxMap::default();
    if !m.localisation.is_empty() {
        for k in &c.parsed {
            for n in &k.nations {
                tag_names.insert(n.tag.clone(), name_for(&n.tag, &n.government, m));
            }
        }
        for t in &war_tags {
            if !tag_names.contains_key(t) {
                tag_names.insert(t.clone(), name_for(t, "", m));
            }
        }
    }
    if let Some(mp) = &map {
        if mp.derived > 0 && !run.quiet {
            crate::outln!("map/positions.txt anchors no army counter for {} of the provinces holding \
                      troops; those markers sit at the middle of the province instead.", mp.derived);
        }
    }

    let mut p = String::with_capacity(series_facts.len() + tables.len() + market.len() + (8 << 20));

    p.push_str("{\"dates\":");
    str_array(&mut p, dates.iter());
    p.push_str(",\"years\":");
    float_array(&mut p, dates.iter().map(|d| year_fraction(d)));
    p.push_str(",\"tags\":");
    str_array(&mut p, tags.iter());
    // `_names_shown`
    p.push_str(",\"tagNames\":{");
    let mut shown: FxSet<&str> = FxSet::default();
    for (i, t) in tags.iter().enumerate() {
        if i > 0 {
            p.push(',');
        }
        push_json_str(&mut p, t);
        p.push(':');
        push_json_str(&mut p, tag_names.get(t).map(|s| s.as_str()).unwrap_or(t));
        shown.insert(t);
    }
    for t in &war_tags {
        if !shown.contains(t.as_str()) {
            if let Some(n) = tag_names.get(t) {
                if !tags.is_empty() || shown.len() > 0 {
                    p.push(',');
                }
                push_json_str(&mut p, t);
                p.push(':');
                push_json_str(&mut p, n);
                shown.insert(t);
            }
        }
    }
    p.push_str("},\"cultureNames\":");
    m.culture_names.write(&mut p);
    p.push_str(",\"names\":");
    m.display_names.write(&mut p);
    p.push_str(&series_facts);
    p.push_str(&tables);
    p.push_str(",\"map\":");
    let mut chunks_text = "[]".to_string();
    match &map {
        None => p.push_str("null"),
        Some(mp) => {
            let (a, b) = mp.json.split_once("\u{0}CHUNKS\u{0}").unwrap();
            p.push_str(a);
            if run.split {
                p.push_str(",\"populationStateChunks\":");
                p.push_str(&mp.chunks);
            } else if mp.chunks == "[]" {
                // `_state_chunks` leaves an empty list where it was.
                p.push_str(",\"populationStateChunks\":[]");
            } else {
                chunks_text = escape_angles(&mp.chunks);
            }
            p.push_str(b);
        }
    }
    p.push_str(",\"basePrices\":");
    m.base_prices.write(&mut p);
    p.push_str(",\"greatPowers\":");
    p.push_str(&great_powers);
    p.push_str(",\"flags\":");
    p.push_str(&flags);
    p.push_str(",\"technology\":");
    m.technology.write(&mut p);
    p.push_str(",\"wars\":[");
    for (i, w) in built.iter().enumerate() {
        if i > 0 {
            p.push(',');
        }
        p.push_str(&w.json);
    }
    p.push_str("],\"succession\":");
    p.push_str(&succession_json);
    p.push_str(&market);
    p.push_str(",\"growthSpan\":");
    push_json_float(&mut p, t.growth_span);
    p.push_str(",\"cross\":");
    match &run.cross {
        Some(x) if x != "null" && x != "{}" && x != "[]" && !x.is_empty() => p.push_str(x),
        _ => p.push_str("null"),
    }
    p.push('}');

    let span = if dates.is_empty() { "—".to_string() }
               else { html_escape(&format!("{} – {}", dates[0], dates[dates.len() - 1])) };
    let price_span = match &price_ends {
        None => "no price data".to_string(),
        Some((a, b)) => html_escape(&format!("{} – {}", a, b)),
    };
    let fill = |html: String| -> String {
        html.replace("__SAVECOUNT__", &dates.len().to_string())
            .replace("__NATIONCOUNT__", &tags.len().to_string())
            .replace("__SPAN__", &span)
            .replace("__PRICESPAN__", &price_span)
    };
    std::fs::create_dir_all(&run.out).ok();
    if std::env::var_os("VIC2_ENGINE_PAYLOAD").is_some() {
        std::fs::write(std::path::Path::new(&run.out).join("payload.json"), escape_angles(&p)).ok();
    }
    crate::engine::phase("payload assembled");
    let packed = pack_bytes(&p);
    crate::engine::phase("payload gzipped");
    let html = if run.split {
        let data_name = "report.data.gz";
        std::fs::write(std::path::Path::new(&run.out).join(data_name), &packed)
            .map_err(|e| format!("cannot write {}: {}", data_name, e))?;
        fill(t.template.replace("__DATA__", "").replace("__DATAURL__", data_name)
             .replace("__STATES__", "[]"))
    } else {
        let html = fill(t.template.clone()).replace("__DATAURL__", "")
            .replace("__STATES__", &chunks_text);
        let mut b64 = String::with_capacity(packed.len() * 4 / 3 + 4);
        crate::util::deflate::base64_into(&mut b64, &packed);
        html.replace("__DATA__", &b64)
    };
    let path = std::path::Path::new(&run.out).join("report.html");
    crate::engine::phase("page filled");
    std::fs::write(&path, html.as_bytes())
        .map_err(|e| format!("cannot write {}: {}", path.display(), e))?;
    Ok(path.to_string_lossy().to_string())
}

/// `pack_bytes`: the payload's `<` and `>` made look-alikes, gzipped on
/// every core.
fn pack_bytes(payload: &str) -> Vec<u8> {
    let raw = escape_angles(payload);
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1).clamp(1, 16);
    crate::util::deflate::gzip_parallel(raw.as_bytes(), threads)
}


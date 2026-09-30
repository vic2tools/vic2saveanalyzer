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

use crate::engine::dates::{date_key, year_fraction};
use crate::engine::dump::{int_keyed, obj};
use crate::engine::{say, Run};
use crate::engine::finish::{escape_angles, Kept, Profile, Row, Spent, Val};
use crate::engine::tables::Tables;
use crate::jsonr::J;
use crate::engine::mapflags;
use crate::engine::market::{self, PriceRow, SnapRow};
use crate::engine::model::Meta;
use crate::omap::OMap;
use crate::pickle::{FxMap, FxSet};
use crate::pyfmt::{push_csv_field, push_int, push_json_float, push_json_str, round};
use crate::engine::rules::{self, Mod};
use crate::engine::wars::{self, Book, Mapping};
use std::io::Write;










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
    ships: ByTag<Vec<(String, i64)>>,
    crews: ByTag<Vec<(String, f64)>>,
    brigades: ByTag<Vec<(String, i64)>>,
    techs: ByTag<Vec<String>>,
    pops: ByTag<Vec<(String, i64)>>,
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

// ------------------------------------------------------------ the map

struct MapOut {
    json: String,
    chunks: String,
    derived: usize,
}

/// `build_map`, less its state chunks, which travel beside the payload.
fn build_map(m: &Mod, parsed: &[Kept1], scale: i64) -> Option<MapOut> {
    if m.path.is_empty() {
        return None;
    }
    let decoded;
    let (width, height, runs) = match &m.raster {
        Some((w, h, r)) => (*w, *h, r),
        None => {
            decoded = mapflags::province_raster(&m.map_bmp, &m.map_csv, scale);
            (decoded.0, decoded.1, &decoded.2)
        }
    };
    if width == 0 {
        return None;
    }
    let full_height = height * scale;
    let garrisoned: FxSet<i64> = parsed.iter()
        .flat_map(|k| k.nations.iter())
        .flat_map(|n| n.units_at.keys().copied())
        .filter(|&p| p > 0)
        .collect();
    let mut spots: OMap<i64, [f64; 2]> = OMap::new();
    for (pid, x, y) in &m.positions {
        if !garrisoned.contains(pid) {
            continue;
        }
        spots.set(*pid, [round(x / scale as f64, 1), round((full_height as f64 - y) / scale as f64, 1)]);
    }
    let unanchored: FxSet<i64> = garrisoned.iter().copied().filter(|p| !spots.contains_key(p)).collect();
    let anchors = mapflags::province_anchors(width, runs, &unanchored);
    for (pid, xy) in anchors.iter() {
        spots.set(*pid, *xy);
    }
    let derived = unanchored.iter().filter(|p| spots.contains_key(*p)).count();

    crate::engine::phase("map: raster decoded, spots placed");
    let mut tagset: Vec<String> = {
        let seen: FxSet<&str> = parsed.iter()
            .flat_map(|k| k.meta.province_owner.iter())
            .flat_map(|(_, o, c)| [o.as_str(), c.as_str()])
            .collect();
        seen.into_iter().map(|t| t.to_string()).collect()
    };
    tagset.sort();
    let index: FxMap<&str, usize> = tagset.iter().enumerate().map(|(i, t)| (t.as_str(), i)).collect();

    let mut j = String::with_capacity(4 << 20);
    j.push_str("{\"w\":");
    push_int(&mut j, width);
    j.push_str(",\"h\":");
    push_int(&mut j, height);
    j.push_str(",\"scale\":");
    push_int(&mut j, scale);
    j.push_str(",\"derived\":");
    push_int(&mut j, derived as i64);
    j.push_str(",\"runs\":");
    push_json_str(&mut j, &mapflags::raster_text(runs));
    j.push_str(",\"tags\":");
    j.push('[');
    for (i, t) in tagset.iter().enumerate() {
        if i > 0 {
            j.push(',');
        }
        push_json_str(&mut j, t);
    }
    j.push_str("],\"colours\":");
    obj(&mut j, tagset.iter().filter_map(|t| m.colours.get(t).map(|c| (t.as_str(), c))),
        |o, c| push_json_str(o, c));
    j.push_str(",\"sea\":[");
    for (i, s) in m.sea.iter().enumerate() {
        if i > 0 {
            j.push(',');
        }
        push_int(&mut j, *s);
    }
    j.push_str("],\"spots\":");
    int_keyed(&mut j, &spots, |o, xy| {
        o.push('[');
        push_json_float(o, xy[0]);
        o.push(',');
        push_json_float(o, xy[1]);
        o.push(']');
    });
    j.push_str(",\"names\":");
    let names: OMap<i64, &String> = m.province_names.iter()
        .filter(|(p, _)| spots.contains_key(*p)).map(|(p, n)| (*p, n)).collect();
    int_keyed(&mut j, &names, |o, n| push_json_str(o, n));

    j.push_str(",\"owners\":[");
    // Province ids are small and dense, so each save's ledger is an array
    // by id: a later line for the same province wins, as in a dict, and
    // walking the ids in order is the sort.
    let top = parsed.iter().flat_map(|k| k.meta.province_owner.iter())
        .map(|(p, _, _)| *p).filter(|p| *p >= 0).max().unwrap_or(0) as usize;
    let mut previous: Vec<i32> = vec![-1; top + 1];
    let mut previous_any = false;
    let mut held: Vec<i32> = vec![-1; top + 1];
    let mut occ: Vec<i32> = vec![-1; top + 1];
    for (si, k) in parsed.iter().enumerate() {
        held.iter_mut().for_each(|h| *h = -1);
        occ.iter_mut().for_each(|h| *h = -1);
        let mut any = false;
        for (p, o, c) in &k.meta.province_owner {
            if *p < 0 {
                continue;
            }
            held[*p as usize] = index[o.as_str()] as i32;
            occ[*p as usize] = if c != o { index[c.as_str()] as i32 } else { -1 };
            any = true;
        }
        if si > 0 {
            j.push(',');
        }
        j.push_str("{\"date\":");
        push_json_str(&mut j, &k.meta.date);
        j.push_str(",\"base\":");
        j.push_str(if previous_any { "false" } else { "true" });
        j.push_str(",\"set\":\"");
        let mut first = true;
        for (pid, &h) in held.iter().enumerate() {
            if h >= 0 && previous[pid] != h {
                if !first {
                    j.push(',');
                }
                first = false;
                push_int(&mut j, pid as i64);
                j.push(':');
                push_int(&mut j, h as i64);
            }
        }
        j.push_str("\",\"clear\":\"");
        let mut first = true;
        for (pid, &h) in held.iter().enumerate() {
            if h < 0 && previous[pid] >= 0 {
                if !first {
                    j.push(',');
                }
                first = false;
                push_int(&mut j, pid as i64);
            }
        }
        j.push_str("\",\"occ\":\"");
        let mut first = true;
        for (pid, &c) in occ.iter().enumerate() {
            if c >= 0 {
                if !first {
                    j.push(',');
                }
                first = false;
                push_int(&mut j, pid as i64);
                j.push(':');
                push_int(&mut j, c as i64);
            }
        }
        j.push_str("\"}");
        std::mem::swap(&mut previous, &mut held);
        previous_any = any;
    }
    crate::engine::phase("map: owners");
    j.push_str("],\"capitals\":{");
    for (si, k) in parsed.iter().enumerate() {
        if si > 0 {
            j.push(',');
        }
        push_json_str(&mut j, &k.meta.date);
        j.push(':');
        obj(&mut j, k.nations.iter().filter(|n| !n.capital.is_empty())
            .map(|n| (n.tag.as_str(), &n.capital)), |o, c| push_json_str(o, c));
    }
    j.push_str("},\"populationStates\":{");
    for (si, k) in parsed.iter().enumerate() {
        if si > 0 {
            j.push(',');
        }
        push_json_str(&mut j, &k.meta.date);
        j.push_str(":{}");
    }
    j.push('}');
    // The state chunks: kept apart for the page, spliced in for `--split`.
    let mut chunks = String::from("[");
    for (si, k) in parsed.iter().enumerate() {
        if si > 0 {
            chunks.push(',');
        }
        chunks.push('[');
        push_json_str(&mut chunks, &k.meta.date);
        chunks.push(',');
        push_json_str(&mut chunks, &k.chunk);
        chunks.push(']');
    }
    chunks.push(']');
    j.push_str("\u{0}CHUNKS\u{0}");
    j.push_str(",\"provinceRegions\":");
    int_keyed(&mut j, &m.province_regions, |o, r| push_json_str(o, r));
    j.push_str(",\"stateNames\":");
    m.state_names_j.write(&mut j);
    crate::engine::phase("map: capitals");
    j.push_str(",\"armies\":{");
    for (si, k) in parsed.iter().enumerate() {
        if si > 0 {
            j.push(',');
        }
        push_json_str(&mut j, &k.meta.date);
        j.push(':');
        let mut here: OMap<i64, String> = OMap::new();
        for nat in &k.nations {
            for (pid, types) in nat.units_at.iter() {
                if *pid <= 0 {
                    continue;
                }
                let total: i64 = types.values().sum();
                if total == 0 {
                    continue;
                }
                let empty = OMap::new();
                let men = nat.men_at.get(pid).unwrap_or(&empty);
                let mut ranked: Vec<(&String, &i64)> = types.iter().collect();
                ranked.sort_by(|a, b| b.1.cmp(a.1));
                let mut e = String::from("[");
                push_int(&mut e, index.get(nat.tag.as_str()).map(|i| *i as i64).unwrap_or(-1));
                e.push(',');
                push_int(&mut e, total);
                e.push(',');
                push_json_str(&mut e, &ranked.iter().map(|(t, n)| format!("{}:{}", t, n))
                    .collect::<Vec<_>>().join(";"));
                e.push(',');
                push_int(&mut e, men.values().sum());
                e.push(',');
                push_json_str(&mut e, &ranked.iter()
                    .map(|(t, _)| format!("{}:{}", t, men.get(t.as_str()).copied().unwrap_or(0)))
                    .collect::<Vec<_>>().join(";"));
                e.push(']');
                let slot = here.entry(*pid, String::new);
                if !slot.is_empty() {
                    slot.push(',');
                }
                slot.push_str(&e);
            }
        }
        int_keyed(&mut j, &here, |o, v| {
            o.push('[');
            o.push_str(v);
            o.push(']');
        });
    }
    j.push_str("},\"regimentSize\":");
    let size = match m.define("POP_SIZE_PER_REGIMENT") {
        Some(v) if v != 0.0 => v as i64,
        _ => 3000,
    };
    push_int(&mut j, size);
    j.push('}');
    Some(MapOut { json: j, chunks, derived })
}

// ------------------------------------------------------------ the rest

/// `build_succession(parsed, formations)`.
fn succession(parsed: &[Kept1], m: &Mod) -> String {
    struct Ledger<'a> {
        date: &'a str,
        book: &'a [(i64, String, String)],
        owners: FxSet<&'a str>,
        home: FxMap<&'a str, (&'a str, FxSet<&'a str>)>,
    }
    let ledgers: Vec<Ledger> = parsed.iter().map(|k| {
        let owners = k.meta.province_owner.iter().map(|(_, o, _)| o.as_str())
            .filter(|o| !o.is_empty()).collect();
        let home = k.nations.iter().map(|n| {
            let mut acc: FxSet<&str> = n.accepted_cultures.iter().map(|s| s.as_str()).collect();
            acc.insert(n.primary_culture.as_str());
            (n.tag.as_str(), (n.primary_culture.as_str(), acc))
        }).collect();
        Ledger { date: &k.meta.date, book: &k.meta.province_owner, owners, home }
    }).collect();
    let holdings = |book: &[(i64, String, String)], tags: &[&str]| -> FxMap<String, FxSet<i64>> {
        let mut held: FxMap<String, FxSet<i64>> = tags.iter().map(|t| (t.to_string(), FxSet::default())).collect();
        for (pid, o, _) in book {
            if let Some(s) = held.get_mut(o.as_str()) {
                s.insert(*pid);
            }
        }
        held
    };
    let mut out = String::from("{");
    let mut first = true;
    for pair in ledgers.windows(2) {
        let (was, now_l) = (&pair[0], &pair[1]);
        let mut appeared: Vec<&str> = now_l.owners.iter().filter(|o| !was.owners.contains(*o)).copied().collect();
        if appeared.is_empty() {
            continue;
        }
        appeared.sort();
        let mut vanished: Vec<&str> = was.owners.iter().filter(|o| !now_l.owners.contains(*o)).copied().collect();
        vanished.sort();
        let now = holdings(now_l.book, &appeared);
        let before = holdings(was.book, &vanished);
        for tag in &appeared {
            let land = &now[*tag];
            if land.is_empty() {
                continue;
            }
            let empty = FxSet::default();
            let accepts = now_l.home.get(tag).map(|h| &h.1).unwrap_or(&empty);
            let declared = m.formations.get(*tag);
            let mut came: Vec<(String, f64, i64)> = Vec::new();
            for old in &vanished {
                let shared = before[*old].intersection(land).count();
                if shared == 0 {
                    continue;
                }
                if (shared as f64) / (before[*old].len() as f64) < 0.5 {
                    continue;
                }
                let by_decision = declared.is_some_and(|d| d.contains(*old));
                let mine = was.home.get(old).map(|h| h.0).unwrap_or("");
                if !by_decision && (mine.is_empty() || !accepts.contains(mine)) {
                    continue;
                }
                came.push((old.to_string(), round(shared as f64 / land.len() as f64, 4),
                           by_decision as i64));
            }
            if !came.is_empty() {
                came.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
                if !first {
                    out.push(',');
                }
                first = false;
                push_json_str(&mut out, tag);
                out.push_str(":{\"date\":");
                push_json_str(&mut out, now_l.date);
                out.push_str(",\"from\":[");
                for (i, (t, share, d)) in came.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    out.push('[');
                    push_json_str(&mut out, t);
                    out.push(',');
                    push_json_float(&mut out, *share);
                    out.push(',');
                    push_int(&mut out, *d);
                    out.push(']');
                }
                out.push_str("]}");
            }
        }
    }
    out.push('}');
    out
}

/// `name_for(tag, government, localisation)`.
fn name_for(tag: &str, government: &str, m: &Mod) -> String {
    if !government.is_empty() {
        if let Some(s) = m.localisation.get(&format!("{}_{}", tag, government)) {
            if !s.is_empty() {
                return s.clone();
            }
        }
    }
    match m.localisation.get(tag) {
        Some(s) if !s.is_empty() => s.clone(),
        _ => tag.to_string(),
    }
}

/// `flags_for(mod, parsed, war_book)`: (greatPowers JSON, flags JSON).
fn flags_for(m: &Mod, parsed: &[Kept1], book: &Book) -> (String, String) {
    if m.country_order.is_empty() {
        return ("{}".into(), "{}".into());
    }
    let mut flags: OMap<String, String> = OMap::new();
    let mut tried: FxSet<String> = FxSet::default();
    let mut gp = String::from("{");
    let mut first = true;
    for k in parsed {
        let picks = rules::great_powers(&k.meta, m);
        if picks.is_empty() {
            continue;
        }
        let mut row = String::from("[");
        for (i, tag) in picks.iter().enumerate() {
            let gov = k.nations.iter().find(|n| &n.tag == tag).map(|n| n.government.as_str()).unwrap_or("");
            let suffix = mapflags::flag_suffixes(gov, &m.flag_styles)[0];
            let key = format!("{}|{}", tag, if suffix.is_empty() { "base" } else { suffix });
            if !flags.contains_key(&key) && tried.insert(key.clone()) {
                if let Some(uri) = mapflags::flag_image(&m.flag_roots, tag, gov, &m.flag_styles) {
                    flags.set(key.clone(), uri);
                }
            }
            if i > 0 {
                row.push(',');
            }
            row.push('[');
            push_json_str(&mut row, tag);
            row.push(',');
            push_json_str(&mut row, &key);
            row.push(']');
        }
        row.push(']');
        if !first {
            gp.push(',');
        }
        first = false;
        push_json_str(&mut gp, &k.meta.date);
        gp.push(':');
        gp.push_str(&row);
    }
    gp.push('}');
    for tag in wars::fighters(book) {
        let key = format!("{}|", tag);
        if !flags.contains_key(&key) {
            if let Some(uri) = mapflags::flag_image(&m.flag_roots, &tag, "", &m.flag_styles) {
                flags.set(key, uri);
            }
        }
    }
    let mut fj = String::new();
    obj(&mut fj, flags.iter().map(|(k, v)| (k.as_str(), v)), |o, v| push_json_str(o, v));
    (gp, fj)
}

fn growth_series(readings: &[(&str, Option<f64>)], span: f64) -> OMap<String, f64> {
    let mut out = OMap::new();
    let mut anchor: Option<(&str, f64)> = None;
    for &(date, value) in readings {
        let value = match value {
            Some(v) if v > 0.0 => v,
            _ => continue,
        };
        if let Some((adate, avalue)) = anchor {
            let gap = year_fraction(date) - year_fraction(adate);
            if gap >= span {
                out.set(date.to_string(),
                        round(((value / avalue).powf(1.0 / gap) - 1.0) * 100.0, 4));
                anchor = Some((date, value));
            }
            continue;
        }
        anchor = Some((date, value));
    }
    out
}

fn gain_series(readings: &[(&str, Option<f64>)]) -> OMap<String, f64> {
    let mut out = OMap::new();
    let mut last: Option<f64> = None;
    for &(date, value) in readings {
        let value = match value {
            Some(v) => v,
            None => continue,
        };
        if let Some(l) = last {
            out.set(date.to_string(), round(value - l, 4));
        }
        last = Some(value);
    }
    out
}

fn str_array(out: &mut String, v: impl Iterator<Item = impl AsRef<str>>) {
    out.push('[');
    for (i, s) in v.enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_str(out, s.as_ref());
    }
    out.push(']');
}

fn float_array(out: &mut String, v: impl Iterator<Item = f64>) {
    out.push('[');
    for (i, x) in v.enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_float(out, x);
    }
    out.push(']');
}

/// `html.escape(s)`.
fn html_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#x27;"),
            c => out.push(c),
        }
    }
    out
}

/// One CSV file: its heading, then `body`. False when it could not be
/// opened for writing (a table open in Excel, on Windows).
fn write_table(path: &std::path::Path, columns: &[&str], body: impl FnOnce(&mut dyn Write) -> std::io::Result<()>) -> Result<(), std::io::Error> {
    let f = std::fs::File::create(path)?;
    let mut w = std::io::BufWriter::with_capacity(1 << 20, f);
    let mut head = String::new();
    for (i, c) in columns.iter().enumerate() {
        if i > 0 {
            head.push(',');
        }
        push_csv_field(&mut head, c);
    }
    head.push_str("\r\n");
    w.write_all(head.as_bytes())?;
    body(&mut w)?;
    w.flush()
}

/// Every CSV table: (the paths written, the paths refused).
fn write_outputs(out: &str, c: &Campaign, prices: &[PriceRow], snaps: &[SnapRow],
                 t: &Tables) -> (Vec<String>, Vec<String>) {
    let mut paths = Vec::new();
    let mut refused = Vec::new();
    // `per_save[:1] + [prices, snapshot] + per_save[1:]`, as `write_outputs` orders them.
    let mut order: Vec<(usize, &str, &Vec<String>)> = vec![(0, &t.per_save[0].0, &t.per_save[0].1),
        (100, "prices.csv", &t.price_columns), (101, "market_snapshot.csv", &t.snapshot_columns)];
    for (k, (name, cols)) in t.per_save.iter().enumerate().skip(1) {
        order.push((k, name, cols));
    }
    for (k, name, cols) in order {
        let refs: Vec<&str> = cols.iter().map(|s| s.as_str()).collect();
        let path = std::path::Path::new(out).join(name);
        let got = write_table(&path, &refs, |w| {
            match k {
                100 => {
                    let mut s = String::with_capacity(1 << 20);
                    for (d, y, g, cat, p) in prices {
                        let vals = [Val::S(d), Val::S(y), Val::S(g), Val::S(cat), Val::F(*p)];
                        line(&mut s, &vals);
                        if s.len() > 1 << 20 {
                            w.write_all(s.as_bytes())?;
                            s.clear();
                        }
                    }
                    w.write_all(s.as_bytes())
                }
                101 => {
                    let mut s = String::with_capacity(1 << 20);
                    for r in snaps {
                        let vals = [Val::S(&r.date), Val::S(&r.year), Val::S(&r.good),
                                    Val::S(r.category), Val::F(r.price), Val::F(r.world_pool),
                                    Val::F(r.supply), Val::F(r.demand), Val::F(r.real_demand),
                                    Val::F(r.actual_sold), Val::I(r.discovered)];
                        line(&mut s, &vals);
                    }
                    w.write_all(s.as_bytes())
                }
                k => {
                    for chunk in &c.text[k] {
                        w.write_all(chunk.as_bytes())?;
                    }
                    Ok(())
                }
            }
        });
        let shown = path.to_string_lossy().to_string();
        match got {
            Ok(()) => paths.push(shown),
            Err(e) if e.kind() == std::io::ErrorKind::PermissionDenied => refused.push(shown),
            Err(e) => {
                crate::errln!("cannot write {}: {}", shown, e);
                std::process::exit(1);
            }
        }
    }
    (paths, refused)
}

fn line(out: &mut String, vals: &[Val]) {
    for (i, v) in vals.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        v.push_csv(out);
    }
    out.push_str("\r\n");
}

/// `_say_mod`, once the inventions are settled.
pub fn say_mod(m: &Mod, live: &FxSet<String>, held: &[&[rules::Held]], files: &[String]) {
    let seq = &m.invention_sequence;
    match m.index_base {
        None => crate::outln!("\nInvention indices could not be decoded from {} inventions; falling back \
                          to requirement matching, which overstates unlucky nations.", seq.len()),
        Some(base) => {
            let every: Vec<&rules::Held> = held.iter().flat_map(|h| h.iter()).collect();
            let (bad, total) = rules::violations(m, &rules::holdings(&every), base);
            crate::outln!("\nInvention indices decoded against {} inventions (base {}): {} of {} \
                      nation-invention pairs are unreachable ({:.1}%).", seq.len(), base, bad, total,
                     bad as f64 / total as f64 * 100.0);
            let top = seq.len() as i64 + base - 1;
            let mut odd: Vec<(String, usize, i64, i64, i64)> = Vec::new();
            let mut seen = 0i64;
            for (nations, file) in held.iter().zip(files) {
                let mut past: FxSet<i64> = FxSet::default();
                let mut lost = 0i64;
                for nat in nations.iter() {
                    for idx in &nat.invention_ids {
                        seen += 1;
                        if *idx > top {
                            past.insert(*idx);
                            lost += 1;
                        }
                    }
                }
                if !past.is_empty() {
                    let name = crate::engine::basename(file).to_string();
                    let lo = *past.iter().min().unwrap();
                    let hi = *past.iter().max().unwrap();
                    odd.retain(|o| o.0 != name);
                    odd.push((name, past.len(), lost, lo, hi));
                }
            }
            if !odd.is_empty() {
                let lost: i64 = odd.iter().map(|o| o.2).sum();
                crate::outln!("  {} of {} saves name inventions past the end of that array, so {} of {} \
                          holdings ({:.1}%) cannot be read:", odd.len(), held.len(), lost, seen,
                         lost as f64 / seen as f64 * 100.0);
                odd.sort_by(|a, b| a.0.cmp(&b.0));
                for (name, count, gone, lo, hi) in &odd {
                    crate::outln!("    {}: {} indices, {}..{} ({} holdings)", name, count, lo, hi, gone);
                }
                crate::outln!("  Those saves were written by a different build than --mod-path -- \
                          another version of the mod, or one over the top of it. Their ship stats \
                          and mobilisation size are short by whatever those inventions grant; the \
                          rest of the campaign is unaffected.");
            }
        }
    }
    let rules_ = &m.invention_rules;
    crate::outln!("\nMod scan: {} techs ({} grant mobilisation_size), {} inventions grant it ({} \
              obtainable), {} event modifiers, {} triggered modifiers.", m.tech_count,
             m.tech_mob.len(), rules_.len(), live.len(), m.event_mob.len(),
             m.triggered_mob.iter().filter(|t| t.size != 0.0).count());
    let skipped: Vec<&str> = m.triggered_mob.iter()
        .filter(|t| t.size != 0.0 && unreadable(&t.trigger, m))
        .map(|t| t.name.as_str()).collect();
    if !skipped.is_empty() {
        crate::outln!("  triggered modifiers left out, because their trigger asks something this cannot \
                  answer: {}", skipped.join(", "));
    }
    let mut techs: Vec<(&String, &f64)> = m.tech_mob.iter().collect();
    techs.sort_by(|a, b| a.0.cmp(b.0));
    for (t, v) in techs {
        crate::outln!("  tech       {:<44} +{:.3}", t, v);
    }
    let mut names: Vec<&String> = rules_.keys().collect();
    names.sort();
    for n in names {
        let mark = if live.contains(n.as_str()) { "" } else { "   (unobtainable)" };
        crate::outln!("  invention  {:<44} +{:.3}{}", n, rules_.get(n.as_str()).unwrap().size, mark);
    }
}

/// `modrules._unreadable`.
pub(crate) fn unreadable(trigger: &J, m: &Mod) -> bool {
    if !matches!(trigger, J::Obj(_)) {
        return false;
    }
    let known = |k: &str| matches!(k, "civilized" | "war" | "exists" | "is_greater_power" | "ai"
        | "tag" | "government" | "primary_culture" | "nationalvalue" | "revanchism" | "badboy"
        | "prestige" | "war_exhaustion" | "plurality" | "money" | "total_pops" | "year"
        | "capital" | "owns" | "is_culture_group" | "invention" | "technology"
        | "has_country_flag" | "has_country_modifier") || m.reform_names.contains(k);
    for (key, value) in trigger.pairs() {
        if key.starts_with('_') {
            continue;
        }
        let parts: Vec<&J> = match value {
            J::List(v) => v.iter().collect(),
            one => vec![one],
        };
        for value in parts {
            if key == "AND" || key == "OR" || key == "NOT" {
                if !matches!(value, J::Obj(_)) || unreadable(value, m) {
                    return true;
                }
            } else if key == "capital_scope" {
                if !matches!(value, J::Obj(_)) {
                    return true;
                }
                for (name, inner) in value.pairs() {
                    if name.starts_with('_') {
                        continue;
                    }
                    let n = match inner { J::List(v) => v.len(), _ => 1 };
                    for _ in 0..n {
                        if !matches!(name.as_str(), "AND" | "OR" | "NOT" | "continent" | "province_id") {
                            return true;
                        }
                    }
                }
            } else if !known(key) {
                return true;
            }
        }
    }
    false
}

pub fn thousands(n: i64) -> String {
    let s = n.unsigned_abs().to_string();
    let mut out = String::new();
    for (i, c) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    if n < 0 { format!("-{}", out) } else { out }
}

fn say_summary(c: &Campaign, prices: &[PriceRow], paths: &[String]) {
    crate::outln!("\n{} nation-rows across {} saves.", c.rows.len(), c.parsed.len());
    if !prices.is_empty() {
        let mut months: Vec<&String> = Vec::new();
        let mut seen: FxSet<&String> = FxSet::default();
        for r in prices {
            if seen.insert(&r.0) {
                months.push(&r.0);
            }
        }
        months.sort_by(|a, b| date_key(a).cmp(&date_key(b)));
        let goods: FxSet<&String> = prices.iter().map(|r| &r.2).collect();
        crate::outln!("{} dated price points, {} to {}, {} goods.", months.len(), months[0],
                 months[months.len() - 1], goods.len());
    }
    let latest = &c.parsed[c.parsed.len() - 1].meta.date;
    let mut latest_rows: Vec<&Row> = c.rows.iter().filter(|r| &r.date == latest).collect();
    latest_rows.sort_by(|a, b| b.nat.total_pop.cmp(&a.nat.total_pop));
    crate::outln!("\nLargest nations at {}:", latest);
    crate::outln!("  {:<5}{:>12}{:>9}{:>7}{:>7}{:>7}", "tag", "pop", "accept%", "lit", "brig", "ships");
    for r in latest_rows.iter().take(8) {
        crate::outln!("  {:<5}{:>12}{:>9.1}{:>6.1}%{:>7}{:>7}", r.nat.tag, thousands(r.nat.total_pop),
                 r.accepted_pct, r.avg_literacy * 100.0, r.nat.brigades, r.nat.ships);
    }
    crate::outln!("\nComputed mobilisation sizes at {} (check these against the in-game military panel):",
             latest);
    for r in latest_rows.iter().take(10) {
        crate::outln!("  {}: {:.2}%", r.nat.tag, r.mobilisation_size * 100.0);
    }
    crate::outln!("\nWrote:");
    for p in paths {
        crate::outln!("  {}", p);
    }
}

/// What a run left on disk: the report, if one was built, and the tables
/// that could not be written.
pub struct Outcome {
    pub html: Option<String>,
    pub refused: Vec<String>,
    /// The run refused, in the sentence Python raises: every save refused,
    /// a mod Python cannot read.
    pub run_error: Option<String>,
}

pub fn run(run: &Run, m: &Mod, live: &FxSet<String>, spent: Vec<Spent>) -> Outcome {
    let c = walk(spent);
    crate::engine::phase("walked");
    let metas: Vec<&Meta> = c.parsed.iter().map(|k| &k.meta).collect();
    let prices = market::merge_prices(&metas, &run.tables);
    let snaps = market::snapshot_rows(&metas, &run.tables);
    let out = &run.out;
    let _ = std::fs::create_dir_all(out);
    let mut html_path: Option<String> = None;
    let mut tables: (Vec<String>, Vec<String>) = (Vec::new(), Vec::new());
    std::thread::scope(|s| {
        let csv = s.spawn(|| write_outputs(out, &c, &prices, &snaps, &run.tables));
        if !run.no_html {
            html_path = Some(page(run, m, &c, &prices, &snaps));
            say(&format!("@ready {}", html_path.as_ref().unwrap()));
        }
        tables = csv.join().unwrap();
        crate::engine::phase("tables written");
    });
    let _ = live;
    let (mut paths, refused) = tables;
    if let Some(h) = &html_path {
        paths.insert(0, h.clone());
    }
    if !run.quiet {
        say_summary(&c, &prices, &paths);
    }
    let _ = std::io::stdout().flush();
    say(&format!("@done html={} refused={}", html_path.is_some() as i32,
                 refused.iter().map(|p| crate::engine::basename(p).to_string())
                     .collect::<Vec<_>>().join("\t")));
    Outcome { html: html_path, refused, run_error: None }
}

/// `build_html` and `build_report`: the page, written; its path.
fn page(run: &Run, m: &Mod, c: &Campaign, prices: &[PriceRow], snaps: &[SnapRow]) -> String {
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
    let mut tags: Vec<String> = rows.iter().map(|r| r.nat.tag.clone()).collect();
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
                let owners: Vec<(String, Vec<(i64, String)>)> = c.parsed.iter()
                    .map(|k| (k.meta.date.clone(),
                              k.meta.province_owner.iter().map(|(p, o, _)| (*p, o.clone())).collect()))
                    .collect();
                wars::build(&c.book, &owners, &mapping)
            });
            let map_job = s.spawn(|| build_map(m, &c.parsed, run.map_scale));
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
            .unwrap_or_else(|e| { crate::errln!("cannot write {}: {}", data_name, e); std::process::exit(1); });
        fill(t.template.replace("__DATA__", "").replace("__DATAURL__", data_name)
             .replace("__STATES__", "[]"))
    } else {
        let html = fill(t.template.clone()).replace("__DATAURL__", "")
            .replace("__STATES__", &chunks_text);
        let mut b64 = String::with_capacity(packed.len() * 4 / 3 + 4);
        crate::deflate::base64_into(&mut b64, &packed);
        html.replace("__DATA__", &b64)
    };
    let path = std::path::Path::new(&run.out).join("report.html");
    crate::engine::phase("page filled");
    std::fs::write(&path, html.as_bytes())
        .unwrap_or_else(|e| { crate::errln!("cannot write {}: {}", path.display(), e); std::process::exit(1); });
    path.to_string_lossy().to_string()
}

/// `metrics` to `factKeys`: the measures, their columns and the facts.
fn section_series_facts(run: &Run, rows: &[Row], dates: &[String], tags: &[String]) -> String {
    let t = &run.tables;
    let metric_keys: Vec<&str> = if rows.is_empty() { Vec::new() }
                                 else { t.metrics.iter().map(|m| m.0.as_str()).collect() };
    // series[tag][key][date]
    let mut series: FxMap<&str, Vec<OMap<String, f64>>> = tags.iter()
        .map(|t| (t.as_str(), (0..metric_keys.len()).map(|_| OMap::new()).collect())).collect();
    for r in rows {
        let slot = series.get_mut(r.nat.tag.as_str()).unwrap();
        for (i, key) in metric_keys.iter().enumerate() {
            if let Some(v) = r.get(key).float() {
                slot[i].set(r.date.clone(), v);
            }
        }
    }
    let mut growth_keys: Vec<&str> = Vec::new();
    let mut extra: FxMap<&str, Vec<OMap<String, f64>>> = tags.iter().map(|t| (t.as_str(), Vec::new())).collect();
    let gains: FxSet<&str> = t.gain.iter().map(|g| g.0.as_str()).collect();
    let span = t.growth_span;
    for (key, source, _) in t.growth.iter().chain(t.gain.iter()) {
        let (key, source) = (key.as_str(), source.as_str());
        let si = match metric_keys.iter().position(|k| *k == source) {
            Some(i) => i,
            None => continue,
        };
        growth_keys.push(key);
        let is_gain = gains.contains(key);
        for t in tags.iter() {
            let have = &series[t.as_str()][si];
            let readings: Vec<(&str, Option<f64>)> = dates.iter()
                .map(|d| (d.as_str(), have.get(d.as_str()).copied())).collect();
            let got = if is_gain { gain_series(&readings) } else { growth_series(&readings, span) };
            extra.get_mut(t.as_str()).unwrap().push(got);
        }
    }
    let mut p = String::with_capacity(8 << 20);
    p.push_str(",");
    p.push_str("\"metrics\":[");
    let mut first = true;
    let mut sep = |p: &mut String| {
        if !first {
            p.push(',');
        }
        first = false;
    };
    for (key, label, fmt) in t.metrics.iter() {
        if metric_keys.contains(&key.as_str()) {
            sep(&mut p);
            p.push_str("{\"key\":");
            push_json_str(&mut p, key);
            p.push_str(",\"label\":");
            push_json_str(&mut p, label);
            p.push_str(",\"fmt\":");
            push_json_str(&mut p, fmt);
            p.push('}');
        }
    }
    for (key, _, label) in t.growth.iter() {
        if growth_keys.contains(&key.as_str()) {
            sep(&mut p);
            p.push_str("{\"key\":");
            push_json_str(&mut p, key);
            p.push_str(",\"label\":");
            push_json_str(&mut p, label);
            p.push_str(",\"fmt\":\"percent\",\"rate\":1}");
        }
    }
    for (key, _, label) in t.gain.iter() {
        if growth_keys.contains(&key.as_str()) {
            sep(&mut p);
            p.push_str("{\"key\":");
            push_json_str(&mut p, key);
            p.push_str(",\"label\":");
            push_json_str(&mut p, label);
            p.push_str(",\"fmt\":\"count\",\"delta\":1}");
        }
    }
    p.push_str("],\"series\":{");
    for (ti, t) in tags.iter().enumerate() {
        if ti > 0 {
            p.push(',');
        }
        push_json_str(&mut p, t);
        p.push_str(":{");
        let cols = series[t.as_str()].iter().zip(metric_keys.iter())
            .chain(extra[t.as_str()].iter().zip(growth_keys.iter()));
        for (ki, (dated, key)) in cols.enumerate() {
            if ki > 0 {
                p.push(',');
            }
            push_json_str(&mut p, key);
            p.push_str(":[");
            for (di, d) in dates.iter().enumerate() {
                if di > 0 {
                    p.push(',');
                }
                match dated.get(d.as_str()) {
                    Some(v) => push_json_float(&mut p, *v),
                    None => p.push_str("null"),
                }
            }
            p.push(']');
        }
        p.push('}');
    }
    p.push('}');
    // facts, thinned of what series holds.
    const FACTS: [(&str, char); 30] = [
        ("total_pop", 'i'), ("accepted_pop", 'i'), ("accepted_pct", 'f'), ("avg_literacy", 'f'),
        ("avg_literacy_stated", 'f'), ("life_unmet", 'i'), ("life_unmet_pct", 'f'),
        ("starving", 'i'), ("starving_pct", 'f'), ("avg_militancy", 'f'),
        ("avg_consciousness", 'f'), ("brigades", 'i'), ("regular_brigades", 'i'),
        ("mobilized_brigades", 'i'), ("mobilizing", 'i'), ("brigade_cap", 'i'),
        ("mobilization_pool", 'i'), ("mobilization_brigades", 'i'), ("mobilisation_size", 'f'),
        ("is_mobilized", 'i'), ("ships", 'i'), ("factory_levels", 'i'), ("provinces", 'i'),
        ("prestige", 'f'), ("primary_culture", 's'), ("is_player", 'i'),
        ("soldiers_noncolonial", 'i'), ("techs", 'i'), ("army_techs", 'i'), ("navy_techs", 'i'),
    ];
    let held: FxSet<&str> = if tags.is_empty() { FxSet::default() }
        else { metric_keys.iter().chain(growth_keys.iter()).copied().collect() };
    let mut taken: Vec<&str> = if rows.is_empty() { Vec::new() }
        else { FACTS.iter().map(|f| f.0).filter(|k| held.contains(k)).collect() };
    taken.sort();
    p.push_str(",\"facts\":{");
    let mut by_date: OMap<&str, Vec<&Row>> = OMap::new();
    for r in rows {
        by_date.entry(r.date.as_str(), Vec::new).push(r);
    }
    for (di, (date, rs)) in by_date.iter().enumerate() {
        if di > 0 {
            p.push(',');
        }
        push_json_str(&mut p, date);
        p.push_str(":{");
        // A tag met twice in one save keeps its first place and its last row.
        let mut per_tag: OMap<&str, &Row> = OMap::new();
        for r in rs {
            per_tag.set(r.nat.tag.as_str(), r);
        }
        for (ti, (tag, r)) in per_tag.iter().enumerate() {
            if ti > 0 {
                p.push(',');
            }
            push_json_str(&mut p, tag);
            p.push_str(":{");
            let mut firstk = true;
            for (key, kind) in FACTS.iter() {
                if taken.contains(key) {
                    continue;
                }
                if !firstk {
                    p.push(',');
                }
                firstk = false;
                push_json_str(&mut p, key);
                p.push(':');
                let v = r.get(key);
                match kind {
                    'i' => {
                        let f = if v.truthy() { v.float().unwrap_or(0.0) } else { 0.0 };
                        push_int(&mut p, f.trunc() as i64);
                    }
                    'f' => {
                        let f = if v.truthy() { v.float().unwrap_or(0.0) } else { 0.0 };
                        push_json_float(&mut p, f);
                    }
                    _ => match v {
                        Val::S(s) => push_json_str(&mut p, s),
                        _ => p.push_str("\"\""),
                    },
                }
            }
            p.push('}');
        }
        p.push('}');
    }
    p.push_str("},\"factKeys\":");
    str_array(&mut p, taken.iter());
    p
}

/// `ships` to `colours`: the per-nation tables.
fn section_tables(run: &Run, c: &Campaign) -> String {
    let t = &run.tables;
    let mut p = String::with_capacity(8 << 20);
    // the per-nation tables
    let date_map_i = |p: &mut String, t: &ByTag<Vec<(String, i64)>>| {
        obj(p, t.iter().map(|(k, v)| (k.as_str(), v)), |o, by| {
            obj(o, by.iter().map(|(d, v)| (d.as_str(), v)), |o, v| {
                obj(o, v.iter().map(|(k, n)| (k.as_str(), *n)), |o, n| push_int(o, n))
            })
        });
    };
    p.push_str(",\"ships\":");
    date_map_i(&mut p, &c.ships);
    p.push_str(",\"crews\":");
    obj(&mut p, c.crews.iter().map(|(k, v)| (k.as_str(), v)), |o, by| {
        obj(o, by.iter().map(|(d, v)| (d.as_str(), v)), |o, v| {
            obj(o, v.iter().map(|(k, n)| (k.as_str(), *n)), |o, n| push_json_float(o, n))
        })
    });
    let types_of = |t: &ByTag<Vec<(String, i64)>>| -> Vec<String> {
        let mut v: Vec<String> = t.values().flat_map(|by| by.values())
            .flat_map(|h| h.iter().map(|(k, _)| k.clone())).collect();
        v.sort();
        v.dedup();
        v
    };
    p.push_str(",\"shipTypes\":");
    str_array(&mut p, types_of(&c.ships).iter());
    p.push_str(",\"brigades\":");
    date_map_i(&mut p, &c.brigades);
    p.push_str(",\"regimentTypes\":");
    str_array(&mut p, types_of(&c.brigades).iter());
    let mut tech_order: Vec<String> = Vec::new();
    let mut tech_meta: Vec<(String, String)> = Vec::new();
    for branch in ["army", "navy"] {
        for l in run.tech_lines.at(branch).list() {
            let name = l.list()[0].str();
            for t in l.list()[1].list() {
                tech_order.push(t.str().to_string());
                tech_meta.push((branch.to_string(), name.to_string()));
            }
        }
    }
    let known: FxSet<String> = tech_order.iter().cloned().collect();
    let mut extra_techs: Vec<String> = c.techs.values().flat_map(|by| by.values())
        .flat_map(|names| names.iter().cloned()).filter(|t| !known.contains(t)).collect();
    extra_techs.sort();
    extra_techs.dedup();
    for t in extra_techs {
        tech_order.push(t);
        tech_meta.push(("other".into(), "Other".into()));
    }
    let tech_index: FxMap<&str, usize> = tech_order.iter().enumerate().map(|(i, t)| (t.as_str(), i)).collect();
    p.push_str(",\"techOrder\":");
    str_array(&mut p, tech_order.iter());
    p.push_str(",\"techMeta\":[");
    for (i, (b, l)) in tech_meta.iter().enumerate() {
        if i > 0 {
            p.push(',');
        }
        p.push('[');
        push_json_str(&mut p, b);
        p.push(',');
        push_json_str(&mut p, l);
        p.push(']');
    }
    p.push_str("],\"techsBy\":{");
    let mut firstt = true;
    for (tag, by) in c.techs.iter() {
        let mut dated = String::new();
        let mut firstd = true;
        for (d, names) in by.iter() {
            let mut held: Vec<usize> = names.iter().filter_map(|t| tech_index.get(t.as_str()).copied()).collect();
            if held.is_empty() {
                continue;
            }
            held.sort();
            if !firstd {
                dated.push(',');
            }
            firstd = false;
            push_json_str(&mut dated, d);
            dated.push_str(":[");
            for (i, h) in held.iter().enumerate() {
                if i > 0 {
                    dated.push(',');
                }
                push_int(&mut dated, *h as i64);
            }
            dated.push(']');
        }
        if firstd {
            continue;
        }
        if !firstt {
            p.push(',');
        }
        firstt = false;
        push_json_str(&mut p, tag);
        p.push_str(":{");
        p.push_str(&dated);
        p.push('}');
    }
    p.push_str("},\"worldPop\":");
    obj(&mut p, c.parsed.iter().filter(|k| !k.meta.date.is_empty())
        .map(|k| (k.meta.date.as_str(), k.meta.world_pop)), |o, v| push_int(o, v));
    p.push_str(",\"pops\":");
    date_map_i(&mut p, &c.pops);
    p.push_str(",\"popTypes\":");
    str_array(&mut p, types_of(&c.pops).iter());
    p.push_str(",\"cultures\":");
    obj(&mut p, c.cultures.iter().map(|(k, v)| (k.as_str(), v)), |o, by| {
        obj(o, by.iter().map(|(d, v)| (d.as_str(), v)), |o, v| {
            o.push('[');
            for (i, (cu, n, a)) in v.iter().enumerate() {
                if i > 0 {
                    o.push(',');
                }
                o.push('[');
                push_json_str(o, cu);
                o.push(',');
                push_int(o, *n);
                o.push(',');
                push_int(o, *a);
                o.push(']');
            }
            o.push(']');
        })
    });
    p.push_str(",\"colours\":");
    str_array(&mut p, t.colours.iter());
    p
}

/// `priceDates` to `supply`: the market; and the first and last price dates.
fn section_market(run: &Run, m: &Mod, c: &Campaign, prices: &[PriceRow], snaps: &[SnapRow],
                  dates: &[String]) -> (String, Option<(String, String)>) {
    let t = &run.tables;
    let mut p = String::with_capacity(8 << 20);
    let mut price_dates: Vec<&str> = Vec::new();
    let mut pseen: FxSet<&str> = FxSet::default();
    let mut goods_meta: OMap<&str, &str> = OMap::new();
    let mut by_good: OMap<&str, FxMap<&str, f64>> = OMap::new();
    for (d, _y, g, cat, price) in prices {
        if pseen.insert(d) {
            price_dates.push(d);
        }
        goods_meta.entry(g.as_str(), || cat);
        by_good.entry(g.as_str(), FxMap::default).insert(d.as_str(), *price);
    }
    price_dates.sort_by(|a, b| year_fraction(a).partial_cmp(&year_fraction(b)).unwrap_or(std::cmp::Ordering::Equal));
    p.push_str(",\"priceDates\":");
    str_array(&mut p, price_dates.iter());
    p.push_str(",\"priceYears\":");
    float_array(&mut p, price_dates.iter().map(|d| year_fraction(d)));
    p.push_str(",\"prices\":");
    obj(&mut p, by_good.iter().map(|(g, by)| (*g, by)), |o, by| {
        o.push('[');
        for (i, d) in price_dates.iter().enumerate() {
            if i > 0 {
                o.push(',');
            }
            match by.get(d) {
                Some(v) => push_json_float(o, *v),
                None => o.push_str("null"),
            }
        }
        o.push(']');
    });
    let mut goods: Vec<&str> = by_good.keys().copied().collect();
    goods.sort();
    p.push_str(",\"goods\":");
    str_array(&mut p, goods.iter());
    p.push_str(",\"goodCategory\":");
    obj(&mut p, goods_meta.iter().map(|(g, c)| (*g, *c)), |o, c| push_json_str(o, c));
    p.push_str(",\"categoryLabels\":");
    obj(&mut p, t.category_labels.iter().map(|(k, v)| (k.as_str(), v)), |o, v| push_json_str(o, v));
    p.push_str(",\"movement\":");
    obj(&mut p, by_good.iter().map(|(g, by)| (*g, by)), |o, by| {
        let vals: Vec<f64> = price_dates.iter().filter_map(|d| by.get(d).copied()).collect();
        let v = if vals.len() >= 2 && vals[0] != 0.0 {
            (vals[vals.len() - 1] - vals[0]).abs() / vals[0]
        } else {
            0.0
        };
        push_json_float(o, v);
    });
    p.push_str(",\"snapshot\":{");
    let mut snap_dates: OMap<&str, ()> = OMap::new();
    let mut by_date: OMap<&str, OMap<&str, &SnapRow>> = OMap::new();
    for r in snaps {
        by_date.entry(r.date.as_str(), OMap::new).set(r.good.as_str(), r);
        snap_dates.set(r.date.as_str(), ());
    }
    for (di, (d, goods)) in by_date.iter().enumerate() {
        if di > 0 {
            p.push(',');
        }
        push_json_str(&mut p, d);
        p.push(':');
        obj(&mut p, goods.iter().map(|(g, r)| (*g, *r)), |o, r| {
            o.push_str("{\"price\":");
            push_json_float(o, r.price);
            o.push_str(",\"supply\":");
            push_json_float(o, r.supply);
            o.push_str(",\"demand\":");
            push_json_float(o, r.real_demand);
            o.push_str(",\"actual_sold\":");
            push_json_float(o, r.actual_sold);
            o.push_str(",\"pegged\":");
            push_int(o, (r.demand > 1e9) as i64);
            o.push_str(",\"discovered\":");
            push_int(o, r.discovered);
            o.push('}');
        });
    }
    p.push('}');
    let mut sd: Vec<&str> = snap_dates.keys().copied().collect();
    sd.sort_by(|a, b| year_fraction(a).partial_cmp(&year_fraction(b)).unwrap_or(std::cmp::Ordering::Equal));
    p.push_str(",\"snapshotDates\":");
    str_array(&mut p, sd.iter());
    p.push_str(",\"naval\":");
    if c.naval_profiles.is_empty() {
        p.push_str("null");
    } else {
        p.push_str("{\"profiles\":[");
        for (i, prof) in c.naval_profiles.iter().enumerate() {
            if i > 0 {
                p.push(',');
            }
            obj(&mut p, prof.iter().map(|(n, st, h)| (n.as_str(), (st, h))), |o, (st, h)| {
                o.push('{');
                for (k, key) in rules::SHIP_KEYS.iter().enumerate() {
                    push_json_str(o, key);
                    o.push(':');
                    push_json_float(o, st[k]);
                    o.push(',');
                }
                o.push_str("\"heavy\":");
                push_int(o, *h);
                o.push('}');
            });
        }
        p.push_str("],\"of\":");
        obj(&mut p, c.naval_of.iter().map(|(t, by)| (t.as_str(), by)), |o, by| {
            obj(o, by.iter().map(|(d, i)| (d.as_str(), *i)), |o, i| push_int(o, i as i64))
        });
        p.push_str(",\"exact\":");
        p.push_str(if m.index_base.is_some() { "true" } else { "false" });
        p.push('}');
    }
    // `_trim_supply`
    p.push_str(",\"supply\":{");
    let keep: FxSet<&str> = dates.iter().map(|d| d.as_str()).collect();
    let mut firstg = true;
    for (good, by_date) in c.supply.iter() {
        let mut rowsj = String::new();
        let mut firstd = true;
        for (d, by_tag) in by_date.iter() {
            if !keep.contains(d.as_str()) {
                continue;
            }
            let total = crate::pyfmt::py_sum(by_tag.values().copied()).unwrap_or(0.0);
            if total <= 0.0 {
                continue;
            }
            let mut top: Vec<(&String, &f64)> = by_tag.iter().collect();
            top.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap_or(std::cmp::Ordering::Equal));
            top.truncate(t.supply_named);
            if !firstd {
                rowsj.push(',');
            }
            firstd = false;
            push_json_str(&mut rowsj, d);
            rowsj.push_str(":{\"t\":");
            push_json_float(&mut rowsj, round(total, 2));
            rowsj.push_str(",\"n\":[");
            for (i, (t, a)) in top.iter().enumerate() {
                if i > 0 {
                    rowsj.push(',');
                }
                rowsj.push('[');
                push_json_str(&mut rowsj, t);
                rowsj.push(',');
                push_json_float(&mut rowsj, round(**a, 2));
                rowsj.push(']');
            }
            rowsj.push_str("]}");
        }
        if firstd {
            continue;
        }
        if !firstg {
            p.push(',');
        }
        firstg = false;
        push_json_str(&mut p, good);
        p.push_str(":{");
        p.push_str(&rowsj);
        p.push('}');
    }
    p.push('}');
    let ends = if price_dates.is_empty() { None }
               else { Some((price_dates[0].to_string(), price_dates[price_dates.len() - 1].to_string())) };
    (p, ends)
}


/// `pack_bytes`: the payload's `<` and `>` made look-alikes, gzipped on
/// every core.
fn pack_bytes(payload: &str) -> Vec<u8> {
    let raw = escape_angles(payload);
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1).clamp(1, 16);
    crate::deflate::gzip_parallel(raw.as_bytes(), threads)
}


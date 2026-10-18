// The page's payload, section by section: the measures, the tables, the
// market, the successions, and the JSON pieces they are written with.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;

/// `build_succession(parsed, formations)`.
pub(super) fn succession(parsed: &[Kept1], m: &Mod) -> String {
    struct Ledger<'a> {
        date: &'a str,
        book: &'a [(i64, Sym, Sym)],
        owners: FxSet<Sym>,
        home: FxMap<&'a str, (&'a str, FxSet<&'a str>)>,
    }
    let ledgers: Vec<Ledger> = parsed.iter().map(|k| {
        let owners = k.meta.province_owner.iter().map(|(_, o, _)| *o)
            .filter(|o| !o.is_empty()).collect();
        let home = k.nations.iter().map(|n| {
            let mut acc: FxSet<&str> = n.accepted_cultures.iter().map(|s| names::text(*s)).collect();
            acc.insert(names::text(n.primary_culture));
            (n.tag.as_str(), (names::text(n.primary_culture), acc))
        }).collect();
        Ledger { date: &k.meta.date, book: &k.meta.province_owner, owners, home }
    }).collect();
    let holdings = |book: &[(i64, Sym, Sym)], tags: &[Sym]| -> FxMap<Sym, FxSet<i64>> {
        let mut held: FxMap<Sym, FxSet<i64>> = tags.iter().map(|t| (*t, FxSet::default())).collect();
        for (pid, o, _) in book {
            if let Some(s) = held.get_mut(o) {
                s.insert(*pid);
            }
        }
        held
    };
    let mut out = String::from("{");
    let mut first = true;
    for pair in ledgers.windows(2) {
        let (was, now_l) = (&pair[0], &pair[1]);
        let mut appeared: Vec<Sym> = now_l.owners.iter().filter(|o| !was.owners.contains(*o)).copied().collect();
        if appeared.is_empty() {
            continue;
        }
        appeared.sort_by(|a, b| names::cmp(*a, *b));
        let mut vanished: Vec<Sym> = was.owners.iter().filter(|o| !now_l.owners.contains(*o)).copied().collect();
        vanished.sort_by(|a, b| names::cmp(*a, *b));
        let now = holdings(now_l.book, &appeared);
        let before = holdings(was.book, &vanished);
        for tag in &appeared {
            let land = &now[tag];
            let tag_text = names::text(*tag);
            if land.is_empty() {
                continue;
            }
            let empty = FxSet::default();
            let accepts = now_l.home.get(tag_text).map(|h| &h.1).unwrap_or(&empty);
            let declared = m.formations.get(tag_text);
            let mut came: Vec<(String, f64, i64)> = Vec::new();
            for old in &vanished {
                let shared = before[old].intersection(land).count();
                if shared == 0 {
                    continue;
                }
                if (shared as f64) / (before[old].len() as f64) < 0.5 {
                    continue;
                }
                let old_text = names::text(*old);
                let by_decision = declared.is_some_and(|d| d.contains(old_text));
                let mine = was.home.get(old_text).map(|h| h.0).unwrap_or("");
                if !by_decision && (mine.is_empty() || !accepts.contains(mine)) {
                    continue;
                }
                came.push((old_text.to_string(), round(shared as f64 / land.len() as f64, 4),
                           by_decision as i64));
            }
            if !came.is_empty() {
                came.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
                if !first {
                    out.push(',');
                }
                first = false;
                push_json_str(&mut out, tag_text);
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
pub(crate) fn name_for(tag: &str, government: &str, m: &Mod) -> String {
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

pub fn growth_series(readings: &[(&str, Option<f64>)], span: f64) -> OMap<String, f64> {
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

pub fn gain_series(readings: &[(&str, Option<f64>)]) -> OMap<String, f64> {
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

pub(super) fn str_array(out: &mut String, v: impl Iterator<Item = impl AsRef<str>>) {
    out.push('[');
    for (i, s) in v.enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_str(out, s.as_ref());
    }
    out.push(']');
}

pub(super) fn float_array(out: &mut String, v: impl Iterator<Item = f64>) {
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
pub(super) fn html_escape(s: &str) -> String {
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
/// `metrics` to `factKeys`: the measures, their columns and the facts.
pub(super) fn section_series_facts(run: &Run, rows: &[Row], dates: &[String], tags: &[String]) -> String {
    let t = &run.tables;
    let metric_keys: Vec<&str> = if rows.is_empty() { Vec::new() }
                                 else { t.metrics.iter().map(|m| m.0.as_str()).collect() };
    // series[tag][key][date]
    let mut series: FxMap<&str, Vec<OMap<String, f64>>> = tags.iter()
        .map(|t| (t.as_str(), (0..metric_keys.len()).map(|_| OMap::new()).collect())).collect();
    for r in rows {
        let slot = series.get_mut(r.facts.tag.as_str()).unwrap();
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
            per_tag.set(r.facts.tag.as_str(), r);
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
pub(super) fn section_tables(run: &Run, c: &Campaign) -> String {
    let t = &run.tables;
    let mut p = String::with_capacity(8 << 20);
    // the per-nation tables
    let date_map_i = |p: &mut String, t: &ByTag<Vec<(Sym, i64)>>| {
        obj(p, t.iter().map(|(k, v)| (k.as_str(), v)), |o, by| {
            obj(o, by.iter().map(|(d, v)| (d.as_str(), v)), |o, v| {
                obj(o, v.iter().map(|(k, n)| (names::text(*k), *n)), |o, n| push_int(o, n))
            })
        });
    };
    p.push_str(",\"ships\":");
    date_map_i(&mut p, &c.ships);
    p.push_str(",\"crews\":");
    obj(&mut p, c.crews.iter().map(|(k, v)| (k.as_str(), v)), |o, by| {
        obj(o, by.iter().map(|(d, v)| (d.as_str(), v)), |o, v| {
            obj(o, v.iter().map(|(k, n)| (names::text(*k), *n)), |o, n| push_json_float(o, n))
        })
    });
    let types_of = |t: &ByTag<Vec<(Sym, i64)>>| -> Vec<String> {
        let mut v: Vec<Sym> = t.values().flat_map(|by| by.values())
            .flat_map(|h| h.iter().map(|(k, _)| *k)).collect();
        v.sort_by(|a, b| names::cmp(*a, *b));
        v.dedup();
        v.into_iter().map(|s| names::text(s).to_string()).collect()
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
pub(super) fn section_market(run: &Run, m: &Rules, c: &Campaign, prices: &[PriceRow], snaps: &[SnapRow],
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
            let total = crate::py::fmt::py_sum(by_tag.values().copied()).unwrap_or(0.0);
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

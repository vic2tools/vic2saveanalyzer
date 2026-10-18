// The page's map and flags: provinces by owner over the campaign, the
// nations' flags, and the great powers' cards.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;

pub(super) struct MapOut {
    pub(super) json: String,
    pub(super) chunks: String,
    pub(super) derived: usize,
}

/// `build_map`, less its state chunks, which travel beside the payload.
pub(super) fn build_map(m: &Mod, raster: &(i64, i64, Vec<(i64, i64)>), parsed: &[Kept1], scale: i64)
             -> Option<MapOut> {
    if m.path.is_empty() {
        return None;
    }
    let (width, height, runs) = (raster.0, raster.1, &raster.2);
    if width == 0 {
        return None;
    }
    let full_height = height * scale;
    let garrisoned: FxSet<i64> = parsed.iter()
        .flat_map(|k| k.nations.iter())
        .flat_map(|n| n.units_at.iter().map(|s| s.pid))
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
    let mut tagset: Vec<Sym> = {
        let seen: FxSet<Sym> = parsed.iter()
            .flat_map(|k| k.meta.province_owner.iter())
            .flat_map(|(_, o, c)| [*o, *c])
            .collect();
        seen.into_iter().collect()
    };
    tagset.sort_by(|a, b| names::cmp(*a, *b));
    let by_sym: FxMap<Sym, usize> = tagset.iter().enumerate().map(|(i, t)| (*t, i)).collect();
    let index: FxMap<&str, usize> = tagset.iter().enumerate().map(|(i, t)| (names::text(*t), i)).collect();

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
        push_json_str(&mut j, names::text(*t));
    }
    j.push_str("],\"colours\":");
    obj(&mut j, tagset.iter().filter_map(|t| {
            let t = names::text(*t);
            m.colours.get(t).map(|c| (t, c))
        }),
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
            held[*p as usize] = by_sym[o] as i32;
            occ[*p as usize] = if c != o { by_sym[c] as i32 } else { -1 };
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
            for types in Stack::provinces(&nat.units_at) {
                let pid = &types[0].pid;
                if *pid <= 0 {
                    continue;
                }
                let total: i64 = types.iter().map(|s| s.n).sum();
                if total == 0 {
                    continue;
                }
                let mut ranked: Vec<&Stack> = types.iter().collect();
                ranked.sort_by(|a, b| b.n.cmp(&a.n));
                let mut e = String::from("[");
                push_int(&mut e, index.get(nat.tag.as_str()).map(|i| *i as i64).unwrap_or(-1));
                e.push(',');
                push_int(&mut e, total);
                e.push(',');
                push_json_str(&mut e, &ranked.iter()
                    .map(|s| format!("{}:{}", names::text(s.kind), s.n))
                    .collect::<Vec<_>>().join(";"));
                e.push(',');
                push_int(&mut e, types.iter().map(|s| s.men).sum());
                e.push(',');
                push_json_str(&mut e, &ranked.iter()
                    .map(|s| format!("{}:{}", names::text(s.kind), s.men))
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
/// `flags_for(mod, parsed, war_book)`: (greatPowers JSON, flags JSON).
pub(super) fn flags_for(m: &Mod, parsed: &[Kept1], book: &Book) -> (String, String) {
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

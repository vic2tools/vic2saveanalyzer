// --cross, the reading: each campaign read under its mod, and the nations
// two or more of them share compared, measure by measure, in the block the
// report carries.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::{refuse, Args, R};
use super::stop;
use super::survey::Surveyed;
use crate::py::json::J;
use std::collections::BTreeSet;

/// `run_cross`: (the comparison as the page carries it, the primary
/// campaign's saves, its mod).
pub fn run_cross(parent: &str, found: &[Surveyed], args: &Args, verbose: bool)
                 -> R<(Option<String>, Vec<String>, Option<String>)> {
    let mut results: Vec<(String, String, Vec<(String, String, Vec<Option<f64>>)>)> = Vec::new();
    let mut names: Vec<(String, String)> = Vec::new();
    let mut primary: Option<(&Surveyed, Vec<String>)> = None;
    for e in found {
        let mod_path = match &e.mod_path {
            Some(m) => m,
            None => {
                if verbose {
                    crate::outln!("  skipping {}: no mod in {} explains its saves", e.name,
                                  args.game_root.as_deref().unwrap_or("None"));
                }
                continue;
            }
        };
        // `load_mod` raises out of `run_cross` rather than refusing: that
        // much is Python's to say.
        let set = match super::setup(args, mod_path) {
            Ok(s) => s,
            Err(super::Settle::Refuse(why)) | Err(super::Settle::Stop(why)) => stop(&why),
        };
        let dates = super::dates_of(&e.files);
        let files = super::in_date_order(e.files.clone(), dates);
        if verbose {
            crate::outln!("Reading {} ({} saves) under {}", e.name, files.len(), e.mod_label.as_deref().unwrap_or(""));
        }
        let mut part = super::run_for(args, &set, &files);
        part.quiet = true;
        part.cross_part = true;
        let done = crate::engine::run(part);
        if let Some(why) = done.run_error {
            return refuse(format!("{}: {}", e.name, why));
        }
        let part = match done.cross_part {
            Some(p) => p,
            None => continue,
        };
        results.push((e.name.clone(), e.mod_label.clone().unwrap_or_default(), part.rows));
        for (tag, label) in part.names {
            if !names.iter().any(|(t, _)| *t == tag) {
                names.push((tag, label));
            }
        }
        match &args.primary {
            Some(p) => {
                if e.name.to_lowercase() == p.to_lowercase() {
                    primary = Some((e, files));
                }
            }
            None => {
                if primary.as_ref().is_none_or(|(_, f)| files.len() > f.len()) {
                    primary = Some((e, files));
                }
            }
        }
    }
    if let (Some(p), None, false) = (&args.primary, &primary, results.is_empty()) {
        let known: Vec<&str> = results.iter().map(|r| r.0.as_str()).collect();
        return refuse(format!("No campaign called {} under {}. There is: {}",
                              crate::py::repr::str_repr(p), parent, known.join(", ")));
    }
    let (entry, files) = match primary {
        Some(p) if !results.is_empty() => p,
        _ => return Ok((None, Vec::new(), args.mod_path.clone())),
    };
    let (payload, campaigns, tags) = series_payload(&results, &names);
    if verbose {
        crate::outln!("Cross-campaign: {} campaigns, {} nations in two or more of them.", campaigns, tags);
        crate::outln!("The rest of the report is {}{}.", entry.name,
                      if args.primary.is_some() { "" } else { " (the most saves; --primary picks another)" });
    }
    let mut text = String::new();
    payload.write(&mut text);
    Ok((Some(text), files, entry.mod_path.clone()))
}

/// `series_payload(results, names)`: the block the report carries, and how
/// many campaigns and shared nations it holds.
#[allow(clippy::type_complexity)]
fn series_payload(results: &[(String, String, Vec<(String, String, Vec<Option<f64>>)>)],
                  names: &[(String, String)]) -> (J, usize, usize) {
    use crate::engine::dates::year_fraction;
    use crate::py::fmt::round;
    let tables = crate::engine::tables::Tables::new(&[]);
    let metrics = &tables.metrics;
    let mut seen: Vec<(String, BTreeSet<&str>)> = Vec::new();
    for (name, _m, rows) in results {
        for (_d, tag, _v) in rows {
            match seen.iter_mut().find(|(t, _)| t == tag) {
                Some(slot) => {
                    slot.1.insert(name);
                }
                None => {
                    let mut s = BTreeSet::new();
                    s.insert(name.as_str());
                    seen.push((tag.clone(), s));
                }
            }
        }
    }
    let mut shared: Vec<String> = seen.iter().filter(|(_, w)| w.len() >= 2).map(|(t, _)| t.clone()).collect();
    shared.sort();
    let keep: BTreeSet<&str> = shared.iter().map(|s| s.as_str()).collect();
    let mut used: BTreeSet<String> = BTreeSet::new();
    let mut campaigns = Vec::new();
    let mut series = Vec::new();
    for (name, label, rows) in results {
        // `sorted({dates}, key=year_fraction)`: a set, so its order before
        // the sort is Python's hash order; dates that tie on the key keep it.
        // No two real dates tie, and every save of a campaign has its own.
        let mut dates: Vec<&str> = Vec::new();
        for (d, _, _) in rows {
            if !dates.contains(&d.as_str()) {
                dates.push(d);
            }
        }
        dates.sort_by(|a, b| year_fraction(a).partial_cmp(&year_fraction(b)).unwrap());
        let start = dates.first().map(|d| year_fraction(d)).unwrap_or(0.0);
        // {tag: {key: {date: value}}}
        let mut by_tag: Vec<(String, Vec<(String, crate::util::omap::OMap<String, f64>)>)> = Vec::new();
        for (date, tag, values) in rows {
            if !keep.contains(tag.as_str()) {
                continue;
            }
            let i = match by_tag.iter().position(|(t, _)| t == tag) {
                Some(i) => i,
                None => {
                    by_tag.push((tag.clone(), Vec::new()));
                    by_tag.len() - 1
                }
            };
            for (k, (key, _l, _f)) in metrics.iter().enumerate() {
                if let Some(v) = values[k] {
                    let slot = &mut by_tag[i].1;
                    let j = match slot.iter().position(|(n, _)| n == key) {
                        Some(j) => j,
                        None => {
                            slot.push((key.clone(), crate::util::omap::OMap::new()));
                            slot.len() - 1
                        }
                    };
                    slot[j].1.set(date.clone(), v);
                }
            }
        }
        for (_tag, slot) in by_tag.iter_mut() {
            for (key, source, _l) in tables.growth.iter() {
                if let Some(src) = slot.iter().find(|(n, _)| n == source).map(|(_, m)| m) {
                    let readings: Vec<(&str, Option<f64>)> = dates.iter().map(|d| (*d, src.get(*d).copied())).collect();
                    let got = crate::engine::report::growth_series(&readings, tables.growth_span);
                    set_slot(slot, key, got);
                }
            }
            for (key, source, _l) in tables.gain.iter() {
                if let Some(src) = slot.iter().find(|(n, _)| n == source).map(|(_, m)| m) {
                    let readings: Vec<(&str, Option<f64>)> = dates.iter().map(|d| (*d, src.get(*d).copied())).collect();
                    let got = crate::engine::report::gain_series(&readings);
                    set_slot(slot, key, got);
                }
            }
        }
        let mut block = Vec::new();
        for (tag, slot) in &by_tag {
            let mut inner = Vec::new();
            for (key, dated) in slot {
                if dated.is_empty() {
                    continue;
                }
                used.insert(key.clone());
                let mut ds: Vec<(&String, &f64)> = dated.iter().collect();
                ds.sort_by(|a, b| year_fraction(a.0).partial_cmp(&year_fraction(b.0)).unwrap());
                inner.push((key.clone(), J::List(ds.iter().map(|(d, v)| {
                    let y = year_fraction(d);
                    J::List(vec![J::Float(round(y, 3)), J::Float(round(y - start, 3)), J::Float(round(**v, 4))])
                }).collect())));
            }
            if !inner.is_empty() {
                block.push((tag.clone(), J::Obj(inner)));
            }
        }
        campaigns.push(J::Obj(vec![
            ("name".into(), J::Str(name.clone())),
            ("mod".into(), J::Str(if label.is_empty() { "unmatched".into() } else { label.clone() })),
            ("saves".into(), J::Int(dates.len() as i64)),
            ("from".into(), J::Float(round(start, 3))),
            ("to".into(), match dates.last() {
                Some(d) => J::Float(round(year_fraction(d), 3)),
                None => J::Null,
            }),
            ("dates".into(), J::List(dates.iter().map(|d| {
                J::List(vec![J::Float(round(year_fraction(d), 3)), J::Str(d.to_string())])
            }).collect())),
        ]));
        series.push(J::Obj(block));
    }
    const RULEBOUND: [&str; 3] = ["mobilization_pool", "mobilization_brigades", "mobilisation_size"];
    let mut out_metrics = Vec::new();
    for (key, label, fmt) in metrics {
        if used.contains(key) {
            out_metrics.push(J::Obj(vec![
                ("key".into(), J::Str(key.clone())),
                ("label".into(), J::Str(label.clone())),
                ("fmt".into(), J::Str(fmt.clone())),
                ("rulebound".into(), J::Bool(RULEBOUND.contains(&key.as_str()))),
            ]));
        }
    }
    for (key, _s, label) in &tables.growth {
        if used.contains(key) {
            out_metrics.push(J::Obj(vec![
                ("key".into(), J::Str(key.clone())),
                ("label".into(), J::Str(label.clone())),
                ("fmt".into(), J::Str("percent".into())),
                ("rate".into(), J::Int(1)),
                ("rulebound".into(), J::Bool(false)),
            ]));
        }
    }
    for (key, _s, label) in &tables.gain {
        if used.contains(key) {
            out_metrics.push(J::Obj(vec![
                ("key".into(), J::Str(key.clone())),
                ("label".into(), J::Str(label.clone())),
                ("fmt".into(), J::Str("count".into())),
                ("delta".into(), J::Int(1)),
                ("rulebound".into(), J::Bool(false)),
            ]));
        }
    }
    let n_campaigns = campaigns.len();
    let n_tags = shared.len();
    let tag_names = J::Obj(shared.iter().map(|t| {
        let label = names.iter().find(|(n, _)| n == t).map(|(_, l)| l.clone()).unwrap_or_else(|| t.clone());
        (t.clone(), J::Str(label))
    }).collect());
    (J::Obj(vec![
        ("campaigns".into(), J::List(campaigns)),
        ("tags".into(), J::List(shared.iter().map(|t| J::Str(t.clone())).collect())),
        ("tagNames".into(), tag_names),
        ("metrics".into(), J::List(out_metrics)),
        ("series".into(), J::List(series)),
    ]), n_campaigns, n_tags)
}

fn set_slot(slot: &mut Vec<(String, crate::util::omap::OMap<String, f64>)>, key: &str,
            value: crate::util::omap::OMap<String, f64>) {
    match slot.iter_mut().find(|(n, _)| n == key) {
        Some(s) => s.1 = value,
        None => slot.push((key.to_string(), value)),
    }
}

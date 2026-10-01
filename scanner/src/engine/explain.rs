// The four questions a run answers about one campaign instead of writing its
// report: `--explain-mob`, `--explain-mob-pool`, `--inventions` and
// `--check-inventions`, as `explain.explain` asks and answers them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// They come where the report would: every save read, the inventions settled,
// the mod said. Python answers them off the campaign it kept --
// the last save whole for the three about one nation, every nation's
// technologies and invention indices for `--check-inventions` -- and so do
// these, the last save read again whole where one nation is asked about.
// Err is the `RunError` Python raises, in its words.

use crate::engine::finish::Pre;
use crate::engine::model::Nation;
use crate::engine::rules::{self, Mod};
use crate::engine::{read_save, Reading, Refused};
use crate::jsonr::J;
use crate::pickle::FxSet;

/// What was asked, and the settings the answers read.
pub struct Ask {
    pub kind: String,
    pub tag: String,
    pub pop_per_regiment: i64,
    pub mob_types: Vec<String>,
    pub include_occupied: bool,
}

impl Ask {
    pub fn from_json(j: &J) -> Option<Ask> {
        if j.is_null() {
            return None;
        }
        Some(Ask {
            kind: j.at("kind").str().to_string(),
            tag: j.at("tag").str().to_string(),
            pop_per_regiment: j.at("pop_per_regiment").int(),
            mob_types: j.at("mob_types").list().iter().map(|t| t.str().to_string()).collect(),
            include_occupied: j.at("include_occupied").truthy(),
        })
    }
}

fn right(text: &str, width: usize) -> String {
    let n = text.chars().count();
    if n >= width { text.to_string() } else { format!("{}{}", " ".repeat(width - n), text) }
}

fn left(text: &str, width: usize) -> String {
    let n = text.chars().count();
    if n >= width { text.to_string() } else { format!("{}{}", text, " ".repeat(width - n)) }
}

fn commas(n: i64) -> String {
    crate::engine::report::thousands(n)
}

/// `f"{x:,.0f}"`.
fn commas_f0(x: f64) -> String {
    let s = format!("{:.0}", x);
    let (neg, digits) = match s.strip_prefix('-') {
        Some(d) => (true, d),
        None => (false, s.as_str()),
    };
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    if neg { format!("-{}", out) } else { out }
}

/// The last save, read again whole, and the nation asked about in it.
fn last_nation(pres: &[Pre], files: &[String], reading: &Reading, tag: &str)
               -> Result<(Nation, bool), String> {
    let last = pres.last().unwrap();
    let file = files.last().unwrap();
    let mut raw = Vec::new();
    let save = match read_save(file, reading, &mut raw) {
        Ok(s) => s,
        Err(Refused::Skip(why)) | Err(Refused::Back(why)) => crate::engine::decline(&why),
    };
    let nat = match save.nations.into_iter().find(|n| n.key == tag) {
        Some(n) => n,
        None => return Err(format!("{} is not in {}.", tag, last.meta.file)),
    };
    // `is_player` is set on the nations a run keeps, and on no others.
    let player = last.nations.iter().any(|p| p.tag == tag && p.kept && p.is_player);
    Ok((nat, player))
}

/// `explain(args, mod, live, parsed)`, for the one that was asked.
#[allow(clippy::too_many_arguments)]
pub fn answer(ask: &Ask, m: &Mod, live: &FxSet<String>, pres: &[Pre], files: &[String],
              reading: &Reading) -> Result<(), String> {
    let tag = ask.tag.to_uppercase();
    match ask.kind.as_str() {
        "explain_mob_pool" => explain_mob_pool(ask, &tag, m, live, pres, files, reading),
        "check_inventions" => check_inventions(m, pres),
        "inventions" => inventions(&tag, m, pres, files, reading),
        _ => explain_mob(&tag, m, live, pres, files, reading),
    }
}

fn explain_mob(tag: &str, m: &Mod, live: &FxSet<String>, pres: &[Pre], files: &[String],
               reading: &Reading) -> Result<(), String> {
    let (nat, player) = last_nation(pres, files, reading, tag)?;
    let meta = &pres.last().unwrap().meta;
    let world = rules::save_world(meta, m);
    let mut parts = rules::breakdown(&nat, m, Some(live), Some(&world), player)
        .unwrap_or_else(|d| crate::engine::decline(&d.0));
    parts.sort_by(|a, b| a.0.cmp(b.0).then(b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal)));
    crate::outln!("\nMobilisation size for {} at {}:", tag, meta.date);
    let mut total = 0.0;
    for (kind, name, value) in &parts {
        total += value;
        crate::outln!("  {}{} {:+.2}%", left(kind, 19), left(name, 46), value * 100.0);
    }
    if total < 0.0 {
        // The report floors a negative sum at nought, as the game does, and
        // this explains the report's number: the sum first, then that.
        crate::outln!("  {}{} {}%", left("", 19), left("sum", 46), right(&format!("{:.2}", total * 100.0), 6));
        crate::outln!("  {}{} {}%", left("", 19), left("TOTAL, floored at nought", 46), right("0.00", 6));
    } else {
        crate::outln!("  {}{} {}%", left("", 19), left("TOTAL", 46), right(&format!("{:.2}", total * 100.0), 6));
    }
    crate::outln!("\n{} has {} techs and {} active inventions; {} sources grant it mobilisation size.",
                  tag, nat.tech_list.len(), nat.invention_ids.len(), parts.len());
    let skipped: Vec<&str> = m.triggered_mob.iter()
        .filter(|t| t.size != 0.0 && crate::engine::report::unreadable(&t.trigger, m))
        .map(|t| t.name.as_str()).collect();
    if !skipped.is_empty() {
        crate::outln!("Left out, because their trigger asks something this cannot answer: {}.",
                      skipped.join(", "));
    }
    crate::outln!("Invention indices in save run {}..{}; the mod defines {} inventions, {} of which \
                   grant mobilisation size.",
                  nat.invention_ids.iter().min().copied().unwrap_or(0),
                  nat.invention_ids.iter().max().copied().unwrap_or(0),
                  m.invention_sequence.len(), m.invention_rules.len());
    Ok(())
}

/// `brigades_from_clusters`, over sizes in save order.
fn brigades(sizes: &[i64], rate: f64, ppr: i64) -> i64 {
    let (mut total, mut pool) = (0i64, 0.0f64);
    let ppr = ppr as f64;
    for &size in sizes {
        let manpower = size as f64 * rate;
        if manpower <= 0.0 {
            continue;
        }
        if manpower >= ppr {
            total += crate::pyfmt::floordiv(manpower, ppr) as i64;
            pool = 0.0;
        } else {
            pool += manpower;
            if pool >= ppr {
                total += 1;
                pool = 0.0;
            }
        }
    }
    total
}

#[allow(clippy::too_many_arguments)]
fn explain_mob_pool(ask: &Ask, tag: &str, m: &Mod, live: &FxSet<String>, pres: &[Pre],
                    files: &[String], reading: &Reading) -> Result<(), String> {
    let (nat, player) = last_nation(pres, files, reading, tag)?;
    let meta = &pres.last().unwrap().meta;
    let world = rules::save_world(meta, m);
    let rate = rules::rate_for(&nat, m, Some(live), Some(&world), player)
        .unwrap_or_else(|d| crate::engine::decline(&d.0));
    let mob_types: FxSet<&str> = ask.mob_types.iter().map(|s| s.as_str()).collect();
    let occ = ask.include_occupied;
    // `mobilization_clusters`, and the same buckets per province and type.
    let mut per_pop: Vec<(i64, i64)> = Vec::new();
    let mut pool = 0i64;
    for (poptype, culture, size, pid) in &nat.mobilizable_pops {
        if !mob_types.contains(poptype.as_str()) || !nat.accepts(culture) {
            continue;
        }
        if nat.colonial_provinces.contains(pid) || (!occ && nat.occupied_provinces.contains(pid)) {
            continue;
        }
        pool += size;
        per_pop.push((*pid, *size));
    }
    let entries = per_pop.len();
    let mut per_pt: Vec<(i64, String, i64)> = Vec::new();
    {
        for (poptype, culture, size, pid) in &nat.mobilizable_pops {
            if !mob_types.contains(poptype.as_str()) || !nat.accepts(culture) {
                continue;
            }
            if nat.colonial_provinces.contains(pid) || (!occ && nat.occupied_provinces.contains(pid)) {
                continue;
            }
            match per_pt.iter_mut().find(|(p, t, _)| p == pid && t == poptype) {
                Some(slot) => slot.2 += size,
                None => per_pt.push((*pid, poptype.clone(), *size)),
            }
        }
    }
    // What was held out, and why.
    let mut dropped: Vec<(&str, i64)> = Vec::new();
    let mut drop = |why: &'static str, n: i64| match dropped.iter_mut().find(|(w, _)| *w == why) {
        Some(slot) => slot.1 += n,
        None => dropped.push((why, n)),
    };
    if nat.mob_excluded_culture != 0 {
        drop("non-accepted culture", nat.mob_excluded_culture);
    }
    for (poptype, culture, size, pid) in &nat.mobilizable_pops {
        if !mob_types.contains(poptype.as_str()) {
            continue;
        }
        if !nat.accepts(culture) {
            drop("non-accepted culture", *size);
        } else if !occ && nat.occupied_provinces.contains(pid) {
            drop("occupied province", *size);
        } else if nat.colonial_provinces.contains(pid) {
            drop("colonial province", *size);
        }
    }
    let ppr = ask.pop_per_regiment;
    crate::outln!("\nMobilization pool for {} at {} ({})", tag, meta.date,
                  crate::engine::basename(&meta.file));
    crate::outln!("  primary culture   {}", nat.primary_culture);
    let mut accepted = nat.accepted_cultures.clone();
    accepted.sort();
    let joined = accepted.join(" ");
    crate::outln!("  accepted cultures {}", if joined.is_empty() { "(none)".to_string() } else { joined });
    let mut types: Vec<&str> = mob_types.iter().copied().collect();
    types.sort();
    crate::outln!("  pop types counted {}", types.join(" "));
    crate::outln!("  mobilisation size {:.2}%   POP_SIZE_PER_REGIMENT {}", rate * 100.0, ppr);
    crate::outln!("\n  eligible population   {} in {} pop entries, {} province/type slots",
                  right(&commas(pool), 12), entries, per_pt.len());
    if entries > 0 {
        crate::outln!("  cultural split        {:.2} pop entries per province/type slot",
                      entries as f64 / per_pt.len().max(1) as f64);
    }
    let mut order: Vec<&(&str, i64)> = dropped.iter().collect();
    order.sort_by(|a, b| b.1.cmp(&a.1));
    for (reason, size) in order {
        crate::outln!("  excluded: {} {}", left(reason, 20), right(&commas(*size), 12));
    }
    let per_pop_n = brigades(&per_pop.iter().map(|p| p.1).collect::<Vec<_>>(), rate, ppr);
    let per_pt_n = brigades(&per_pt.iter().map(|p| p.2).collect::<Vec<_>>(), rate, ppr);
    let untruncated = pool as f64 * rate / ppr as f64;
    crate::outln!("\n  ceiling, grouped per pop               {}", right(&per_pop_n.to_string(), 6));
    crate::outln!("  ceiling, grouped per province and type {}   ({}{})", right(&per_pt_n.to_string(), 6),
                  if per_pt_n >= per_pop_n { "+" } else { "" }, per_pt_n - per_pop_n);
    crate::outln!("  no truncation at all                   {}", right(&format!("{:.0}", untruncated), 6));
    crate::outln!("  standing brigades                      {}  ({} of them mobilized, {} queued)",
                  right(&nat.brigades.to_string(), 6), nat.mobilized_brigades, nat.mobilizing);
    crate::outln!("\n  Compare the two ceilings against the in-game military panel.");
    let mut biggest: Vec<&(i64, String, i64)> = per_pt.iter().collect();
    biggest.sort_by(|a, b| b.2.cmp(&a.2));
    biggest.truncate(10);
    if !biggest.is_empty() {
        crate::outln!("\n  largest province/type slots");
        crate::outln!("    {} {} {}", right("prov", 6), right("manpower", 10), right("brigades", 8));
        for (pid, _t, size) in biggest {
            let manpower = *size as f64 * rate;
            crate::outln!("    {} {} {}", right(&pid.to_string(), 6), right(&commas_f0(manpower), 10),
                          right(&(crate::pyfmt::floordiv(manpower, ppr as f64) as i64).to_string(), 8));
        }
    }
    Ok(())
}

/// `index_holdings(parsed)`: {index: [(tag, its technologies)]} for every
/// index held at least eight times.
fn index_holdings(pres: &[Pre]) -> Vec<(i64, Vec<FxSet<&str>>)> {
    let mut out: Vec<(i64, Vec<FxSet<&str>>)> = Vec::new();
    let mut at: crate::pickle::FxMap<i64, usize> = crate::pickle::FxMap::default();
    for pre in pres {
        for h in &pre.held {
            if h.tech_list.is_empty() {
                continue;
            }
            let techs: FxSet<&str> = h.tech_list.iter().map(|s| s.as_str()).collect();
            for idx in &h.invention_ids {
                let i = *at.entry(*idx).or_insert_with(|| {
                    out.push((*idx, Vec::new()));
                    out.len() - 1
                });
                out[i].1.push(techs.clone());
            }
        }
    }
    out.retain(|(_, rows)| rows.len() >= 8);
    out
}

/// `alignment_score`: (settled, granted, suspect, unjudged, ungated, detail).
fn alignment_score(m: &Mod, holdings: &[(i64, Vec<FxSet<&str>>)], base: i64)
                   -> ([i64; 5], Vec<(i64, i64, i64)>) {
    let seq = &m.invention_sequence;
    let mut counts = [0i64; 5];
    let mut detail = Vec::new();
    let mut sorted: Vec<&(i64, Vec<FxSet<&str>>)> = holdings.iter().collect();
    sorted.sort_by_key(|h| h.0);
    for (idx, rows) in sorted {
        let j = idx - base;
        if !(0 <= j && (j as usize) < seq.len()) || seq[j as usize].techs.is_empty() {
            counts[3] += 1;
            continue;
        }
        let needs = &seq[j as usize].techs;
        if !m.technologies.is_empty() && !needs.iter().all(|t| m.technologies.contains(t)) {
            counts[4] += 1;
            continue;
        }
        let have = rows.iter().filter(|techs| needs.iter().all(|t| techs.contains(t.as_str()))).count() as i64;
        let share = have as f64 / rows.len() as f64;
        if share >= 0.95 {
            counts[0] += 1;
        } else if share >= 0.5 {
            counts[1] += 1;
            detail.push((*idx, have, rows.len() as i64 - have));
        } else {
            counts[2] += 1;
            detail.push((*idx, have, rows.len() as i64 - have));
        }
    }
    (counts, detail)
}

fn check_inventions(m: &Mod, pres: &[Pre]) -> Result<(), String> {
    let holdings = index_holdings(pres);
    let seq = &m.invention_sequence;
    crate::outln!("\nChecking {} inventions against {} saves.", seq.len(), pres.len());
    let base = match m.index_base {
        Some(b) => b,
        None => return Err("  the indices did not decode at all, so there is nothing to check.".into()),
    };
    if holdings.len() < 40 {
        crate::outln!("  only {} indices are held often enough to say anything about. Run this on a \
                       whole campaign.", holdings.len());
    }
    crate::outln!("  {} indices held often enough to judge\n", holdings.len());
    crate::outln!("  {}{}{}{}{}", left("offset", 10), right("confirmed", 11), right("granted", 10),
                  right("suspect", 10), right("unjudged", 10));
    let mut table: Vec<(i64, i64, i64, i64, Vec<(i64, i64, i64)>)> = Vec::new();
    for shift in [-2i64, -1, 0, 1, 2] {
        let (c, detail) = alignment_score(m, &holdings, base + shift);
        let label = if shift == 0 { "as used".to_string() } else { format!("{:+}", shift) };
        crate::outln!("  {}{}{}{}{}{}", left(&label, 10), right(&c[0].to_string(), 11),
                      right(&c[1].to_string(), 10), right(&c[2].to_string(), 10),
                      right(&(c[3] + c[4]).to_string(), 10),
                      if shift == 0 { "   <-- the decode in use" } else { "" });
        table.push((shift, c[0], c[1], c[2], detail));
    }
    // `ungated_inventions`.
    let mut loose: Vec<(&str, Vec<&str>)> = Vec::new();
    if !m.technologies.is_empty() {
        for entry in seq {
            let mut missing: Vec<&str> = entry.techs.iter().filter(|t| !m.technologies.contains(*t))
                .map(|t| t.as_str()).collect();
            missing.sort();
            missing.dedup();
            if !missing.is_empty() {
                match loose.iter_mut().find(|(n, _)| *n == entry.name) {
                    Some(slot) => slot.1 = missing,
                    None => loose.push((entry.name.as_str(), missing)),
                }
            }
        }
    }
    if !loose.is_empty() {
        crate::outln!("\n  {} invention(s) in this mod are gated on a technology it never defines, so \
                       the gate never closes and every nation has them from the start. They are left \
                       out of the count above:", loose.len());
        loose.sort_by(|a, b| a.0.cmp(b.0));
        for (name, missing) in &loose {
            crate::outln!("    {} asks for {}", left(name, 40), missing.join(" "));
        }
    }
    let (_s, good, granted, bad, detail) = table.iter().find(|t| t.0 == 0).unwrap();
    let judged = good + granted + bad;
    let mut best = table[0].0;
    let mut best_good = table[0].1;
    for t in &table[1..] {
        if t.1 > best_good {
            best = t.0;
            best_good = t.1;
        }
    }
    crate::outln!();
    if best != 0 {
        crate::outln!("  Offset {:+} confirms more indices than the one in use. The base is probably wrong.",
                      best);
    } else if *bad == 0 {
        let one = *granted == 1;
        let tail = if *granted == 0 { String::new() } else {
            format!(" {} of them {} held by a few nations that could not have researched {}, which is \
                     the engine granting inventions outside the tech tree.", granted,
                    if one { "is" } else { "are" }, if one { "it" } else { "them" })
        };
        crate::outln!("  Every index the saves can judge sits where the array says it does.{}\n  The \
                       decode is right: who holds which invention is exact.", tail);
    } else {
        crate::outln!("  {} of {} indices are held mostly by nations that could not have researched \
                       them. That is what a misaligned stretch of the array looks like, and it is worth \
                       reading the list below before trusting anything taken off an invention.",
                      bad, judged);
    }
    if !detail.is_empty() {
        crate::outln!("\n  {}  {} {}  needs", right("index", 6), left("invention", 38), right("holders", 16));
        for (idx, have, lack) in detail.iter().take(26) {
            let entry = &seq[(idx - base) as usize];
            let flag = if have >= lack { "" } else { "  <-- suspect" };
            let mut techs: Vec<&str> = entry.techs.iter().map(|t| t.as_str()).collect();
            techs.sort();
            crate::outln!("  {}  {} {} with {} without  {}{}", right(&idx.to_string(), 6),
                          left(&entry.name, 38), right(&have.to_string(), 6), right(&lack.to_string(), 4),
                          techs.join(" "), flag);
        }
        if detail.len() > 26 {
            crate::outln!("  ... and {} more", detail.len() - 26);
        }
    }
    Ok(())
}

fn inventions(tag: &str, m: &Mod, pres: &[Pre], files: &[String], reading: &Reading)
              -> Result<(), String> {
    let (nat, _player) = last_nation(pres, files, reading, tag)?;
    let meta = &pres.last().unwrap().meta;
    let seq = &m.invention_sequence;
    let where_ = crate::engine::modread::invention_files(&m.path)
        .unwrap_or_else(|d| crate::engine::decline(&d.0));
    let mut held = nat.invention_ids.clone();
    held.sort();
    crate::outln!("\n{} at {} in {}", tag, meta.date, meta.file);
    crate::outln!("the mod rebuilds {} inventions; this save names {} of them, indices {}..{}",
                  seq.len(), held.len(), held.first().copied().unwrap_or(0),
                  held.last().copied().unwrap_or(0));
    let base = match m.index_base {
        Some(b) => b,
        None => return Err("  indices could not be decoded for this install, so there is nothing to \
                            print.".into()),
    };
    crate::outln!("decoded with base {}\n", base);
    let techs: FxSet<&str> = nat.tech_list.iter().map(|s| s.as_str()).collect();
    let mut shown = 0;
    let mut last_file: Option<String> = None;
    for idx in held {
        let j = idx - base;
        if !(0 <= j && (j as usize) < seq.len()) {
            crate::outln!("  {}  *** past the end of the array -- this save is from a different build ***",
                          right(&idx.to_string(), 4));
            continue;
        }
        let entry = &seq[j as usize];
        let fname = where_.get(&entry.name).cloned().unwrap_or_else(|| "?".to_string());
        if last_file.as_deref() != Some(fname.as_str()) {
            crate::outln!("  -- {}", fname);
            last_file = Some(fname);
        }
        let mut gates: Vec<&str> = entry.techs.iter().map(|t| t.as_str()).collect();
        gates.sort();
        let gates = if gates.is_empty() { "(no technology)".to_string() } else { gates.join(" ") };
        let has = if entry.techs.iter().all(|t| techs.contains(t.as_str())) { "" }
                  else { "   <-- the nation does not have that technology" };
        crate::outln!("  {}  {} {}{}", right(&idx.to_string(), 4), left(&entry.name, 42), gates, has);
        shown += 1;
    }
    crate::outln!("\n{} decoded. Compare against the technology screen: every invention shown as \
                   discovered there should appear here, and nothing else should.", shown);
    Ok(())
}

// What a run says about the mod and the campaign once it has read them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;

/// `_say_mod`, once the inventions are settled.
pub fn say_mod(m: &Rules, live: &FxSet<String>, held: &[&[crate::engine::finish::PreNation]], files: &[String]) {
    let seq = &m.invention_sequence;
    match m.index_base {
        None => crate::outln!("\nInvention indices could not be decoded from {} inventions; falling back \
                          to requirement matching, which overstates unlucky nations.", seq.len()),
        Some(base) => {
            let every: Vec<&crate::engine::finish::PreNation> = held.iter().flat_map(|h| h.iter()).collect();
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
                for pn in nations.iter() {
                    for idx in &pn.nat.invention_ids {
                        seen += 1;
                        if *idx > top {
                            past.insert(*idx);
                            lost += 1;
                        }
                    }
                }
                if !past.is_empty() {
                    let name = crate::py::path::basename(file);
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
        .filter(|t| t.size != 0.0 && rules::unreadable(&t.trigger, m))
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

pub(super) fn say_summary(c: &Campaign, prices: &[PriceRow], paths: &[String]) {
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
    latest_rows.sort_by(|a, b| b.facts.total_pop.cmp(&a.facts.total_pop));
    crate::outln!("\nLargest nations at {}:", latest);
    crate::outln!("  {:<5}{:>12}{:>9}{:>7}{:>7}{:>7}", "tag", "pop", "accept%", "lit", "brig", "ships");
    for r in latest_rows.iter().take(8) {
        crate::outln!("  {:<5}{:>12}{:>9.1}{:>6.1}%{:>7}{:>7}", r.facts.tag, thousands(r.facts.total_pop),
                 r.accepted_pct, r.avg_literacy * 100.0, r.facts.brigades, r.facts.ships);
    }
    crate::outln!("\nComputed mobilisation sizes at {} (check these against the in-game military panel):",
             latest);
    for r in latest_rows.iter().take(10) {
        crate::outln!("  {}: {:.2}%", r.facts.tag, r.mobilisation_size * 100.0);
    }
    crate::outln!("\nWrote:");
    for p in paths {
        crate::outln!("  {}", p);
    }
}

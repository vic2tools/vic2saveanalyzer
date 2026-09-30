// Every war in a campaign, put together from the saves it passes through:
// `wars.py`, fold for fold.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::engine::dates::year_fraction;
use crate::engine::model::{Battle, FirstGoal, Goal, Side, War};
use crate::omap::OMap;
use crate::pickle::{FxMap, FxSet};
use crate::pyfmt::{push_int, push_json_str};

type Name = (String, String, String);
pub type Key = (String, String, String, usize);
type BattleKey = (String, i64, i64, i64, usize);

/// One war as the book holds it.
pub struct Held {
    pub name: String,
    pub original_attacker: String,
    pub original_defender: String,
    pub active: bool,
    pub start: String,
    pub end: String,
    pub attackers: Vec<String>,
    pub defenders: Vec<String>,
    pub goal: FirstGoal,
    pub join_dates: OMap<(String, bool), String>,
    pub leave_dates: OMap<(String, bool), String>,
    pub goalbook: OMap<(String, String, i64, String), Goal>,
    pub battles: OMap<BattleKey, Battle>,
}

#[derive(Default)]
pub struct Book {
    pub wars: FxMap<Key, Held>,
    pub order: Vec<Key>,
    /// name -> [key, first, last]
    index: FxMap<Name, Vec<(Key, Option<f64>, Option<f64>)>>,
    last_folded: FxMap<Name, War>,
}

fn war_name(w: &War) -> Name {
    (w.name.clone(), w.original_attacker.clone(), w.original_defender.clone())
}

/// `_war_span`: (first, last), last infinite while the war is being fought.
fn span(w: &War) -> Option<(f64, f64)> {
    if w.start.is_empty() {
        return None;
    }
    let first = year_fraction(&w.start);
    if w.active {
        return Some((first, f64::INFINITY));
    }
    let last = if !w.end.is_empty() { year_fraction(&w.end) } else { first };
    Some((first, if last > first { last } else { first }))
}

fn sorted_union(a: &[String], b: &[String]) -> Vec<String> {
    let mut v: Vec<String> = a.iter().chain(b.iter()).cloned().collect();
    v.sort();
    v.dedup();
    v
}

impl Book {
    /// `fold_packed_wars` for one save's wars: a record the same as the last
    /// one folded under its name is passed over, as the bytes were compared.
    pub fn fold_save(&mut self, wars: &[War]) {
        for w in wars {
            let name = war_name(w);
            if self.last_folded.get(&name) == Some(w) {
                continue;
            }
            self.fold(w);
            self.last_folded.insert(name, w.clone());
        }
    }

    /// `fold_wars` for one record.
    fn fold(&mut self, war: &War) {
        let name = war_name(war);
        let sp = span(war);
        let slot = self.index.entry(name.clone()).or_default();
        let mut found: Option<usize> = None;
        for (i, entry) in slot.iter().enumerate() {
            let top = entry.2.unwrap_or(f64::INFINITY);
            let hit = match (sp, entry.1) {
                (None, _) | (_, None) => true,
                (Some((a, b)), Some(first)) => first <= b && a <= top,
            };
            if hit {
                found = Some(i);
                break;
            }
        }
        let at = match found {
            None => {
                let key: Key = (name.0.clone(), name.1.clone(), name.2.clone(), slot.len());
                self.wars.insert(key.clone(), Held {
                    name: war.name.clone(),
                    original_attacker: war.original_attacker.clone(),
                    original_defender: war.original_defender.clone(),
                    active: war.active,
                    start: war.start.clone(),
                    end: war.end.clone(),
                    attackers: war.attackers.clone(),
                    defenders: war.defenders.clone(),
                    goal: war.goal.clone(),
                    join_dates: OMap::new(),
                    leave_dates: OMap::new(),
                    goalbook: OMap::new(),
                    battles: OMap::new(),
                });
                self.order.push(key.clone());
                let last = match sp {
                    Some((_, b)) if b != f64::INFINITY => Some(b),
                    _ => None,
                };
                slot.push((key, sp.map(|s| s.0), last));
                slot.len() - 1
            }
            Some(i) => {
                if let Some((a, b)) = sp {
                    let e = &mut slot[i];
                    if e.1.is_none() || a < e.1.unwrap() {
                        e.1 = Some(a);
                    }
                    if b != f64::INFINITY && (e.2.is_none() || b > e.2.unwrap()) {
                        e.2 = Some(b);
                    }
                }
                i
            }
        };
        let key = slot[at].0.clone();
        let held = self.wars.get_mut(&key).unwrap();
        if !war.end.is_empty() && held.end.is_empty() {
            held.end = war.end.clone();
        }
        if !war.start.is_empty()
            && (held.start.is_empty() || year_fraction(&war.start) < year_fraction(&held.start)) {
            held.start = war.start.clone();
        }
        if !war.active {
            held.active = false;
        }
        held.attackers = sorted_union(&held.attackers, &war.attackers);
        held.defenders = sorted_union(&held.defenders, &war.defenders);
        for (d, w, a) in &war.joins {
            if d.is_empty() {
                continue;
            }
            let k = (w.clone(), *a);
            let replace = match held.join_dates.get(&k) {
                None => true,
                Some(old) => year_fraction(d) < year_fraction(old),
            };
            if replace {
                held.join_dates.set(k, d.clone());
            }
        }
        for (d, w, a) in &war.leaves {
            if d.is_empty() {
                continue;
            }
            let k = (w.clone(), *a);
            let replace = match held.leave_dates.get(&k) {
                None => true,
                Some(old) => year_fraction(d) > year_fraction(old),
            };
            if replace {
                held.leave_dates.set(k, d.clone());
            }
        }
        for g in &war.goals {
            let gk = (g.actor.clone(), g.receiver.clone(), g.province, g.casus_belli.clone());
            if !held.goalbook.contains_key(&gk) || g.fulfilled {
                held.goalbook.set(gk, g.clone());
            }
        }
        let mut seen: FxMap<(String, i64, i64, i64), usize> = FxMap::default();
        for b in &war.battles {
            let base = (b.name.clone(), b.location,
                        b.attacker.as_ref().map_or(0, |s| s.losses),
                        b.defender.as_ref().map_or(0, |s| s.losses));
            let n = seen.entry(base.clone()).or_insert(0);
            *n += 1;
            let bk: BattleKey = (base.0, base.1, base.2, base.3, *n);
            match held.battles.get_mut(&bk) {
                None => held.battles.set(bk, b.clone()),
                Some(there) => {
                    if b.date.is_some() && there.date.is_none() {
                        there.date = b.date.clone();
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------ the tab

/// A goal as `build_wars` reads it: one caught by a save, or the war's
/// first, which has no `added` and no `fulfilled`.
struct AnyGoal<'a> {
    casus_belli: &'a str,
    actor: &'a str,
    receiver: &'a str,
    province: i64,
    added: &'a str,
    fulfilled: Option<bool>,
}

pub struct Mapping<'a> {
    pub province_names: &'a OMap<i64, String>,
    pub province_regions: &'a OMap<i64, String>,
    pub state_names: &'a OMap<String, String>,
    pub unit_kinds: &'a FxMap<String, String>,
}

fn state_label(region: Option<&str>, pid: i64, m: &Mapping) -> String {
    if let Some(r) = region {
        if let Some(named) = m.state_names.get(r) {
            if !named.is_empty() {
                return named.clone();
            }
        }
    }
    if let Some(p) = m.province_names.get(&pid) {
        if !p.is_empty() {
            return format!("{} Region", p);
        }
    }
    region.unwrap_or("").to_string()
}

fn units(side: &Option<Side>) -> String {
    let s = match side {
        Some(s) if !s.units.is_empty() => s,
        _ => return String::new(),
    };
    let mut v: Vec<(&String, &i64)> = s.units.iter().collect();
    v.sort_by(|a, b| b.1.cmp(a.1));
    v.iter().map(|(k, n)| format!("{}:{}", k, n)).collect::<Vec<_>>().join(";")
}

fn at_sea(b: &Battle, kinds: &FxMap<String, String>) -> bool {
    for side in [&b.attacker, &b.defender] {
        if let Some(s) = side {
            for (unit, _) in s.units.iter() {
                match kinds.get(unit).map(|k| k.as_str()) {
                    Some("naval") => return true,
                    Some("land") => return false,
                    _ => {}
                }
            }
        }
    }
    false
}

/// `_ledger_at`: province ownership at the save just before (or after) a date.
fn ledger_at<'a>(books: &'a [(String, FxMap<i64, String>)], when_each: &[f64], date: &str,
                 before: bool) -> Option<&'a FxMap<i64, String>> {
    if books.is_empty() {
        return None;
    }
    let when = year_fraction(date);
    if before {
        // bisect_right - 1
        let at = when_each.partition_point(|&x| x <= when) as i64 - 1;
        Some(&books[at.max(0) as usize].1)
    } else {
        let at = when_each.partition_point(|&x| x < when);
        Some(&books[at.min(books.len() - 1)].1)
    }
}

fn which(tag: &str, att: &FxSet<&str>, dfd: &FxSet<&str>) -> i64 {
    let (here, there) = (att.contains(tag), dfd.contains(tag));
    if here && !there { 1 } else if there && !here { -1 } else { 0 }
}

fn side_losses(battles: &[&Battle], attackers: &[String], defenders: &[String]) -> [i64; 3] {
    let att: FxSet<&str> = attackers.iter().map(|s| s.as_str()).collect();
    let dfd: FxSet<&str> = defenders.iter().map(|s| s.as_str()).collect();
    let mut totals = [0i64; 3];
    for b in battles {
        let pair = [&b.attacker, &b.defender];
        let country = |s: &Option<Side>| s.as_ref().map(|x| x.country.clone()).unwrap_or_default();
        let mut marks = [which(&country(pair[0]), &att, &dfd), which(&country(pair[1]), &att, &dfd)];
        if marks[0] == 0 && marks[1] != 0 {
            marks[0] = -marks[1];
        }
        if marks[1] == 0 && marks[0] != 0 {
            marks[1] = -marks[0];
        }
        for (side, mark) in pair.iter().zip(marks) {
            let i = if mark > 0 { 0 } else if mark < 0 { 1 } else { 2 };
            totals[i] += side.as_ref().map_or(0, |s| s.losses);
        }
    }
    totals
}

struct Party {
    tag: String,
    joined: String,
    original: bool,
    leads: bool,
    left: Option<String>,
}

fn participants(tags: &[String], join_dates: &OMap<(String, bool), String>, attacking: bool,
                original_tag: &str, start: &str, leave_dates: &OMap<(String, bool), String>,
                end: &str) -> Vec<Party> {
    let cutoff = if start.is_empty() { None } else { Some(year_fraction(start) + 1.0 / 12.0) };
    let mut out = Vec::new();
    for tag in tags {
        let key = (tag.clone(), attacking);
        let joined = join_dates.get(&key).cloned().unwrap_or_default();
        let original = tag == original_tag || joined.is_empty() || cutoff.is_none()
            || year_fraction(&joined) <= cutoff.unwrap();
        let gone = leave_dates.get(&key).cloned().unwrap_or_default();
        let mut left = None;
        if !gone.is_empty() && gone != end {
            let after_start = joined.is_empty() || year_fraction(&gone) >= year_fraction(&joined);
            let before_end = end.is_empty() || year_fraction(&gone) < year_fraction(end);
            if after_start && before_end {
                left = Some(gone);
            }
        }
        out.push(Party { tag: tag.clone(), joined, original, leads: tag == original_tag, left });
    }
    out.sort_by(|a, b| {
        let ka = (!a.original, if a.joined.is_empty() { 0.0 } else { year_fraction(&a.joined) });
        let kb = (!b.original, if b.joined.is_empty() { 0.0 } else { year_fraction(&b.joined) });
        ka.0.cmp(&kb.0)
            .then(ka.1.partial_cmp(&kb.1).unwrap_or(std::cmp::Ordering::Equal))
            .then(a.tag.cmp(&b.tag))
    });
    out
}

fn push_parties(out: &mut String, parties: &[Party]) {
    out.push('[');
    for (i, p) in parties.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str("{\"tag\":");
        push_json_str(out, &p.tag);
        out.push_str(",\"joined\":");
        push_json_str(out, &p.joined);
        out.push_str(",\"original\":");
        out.push_str(if p.original { "true" } else { "false" });
        if p.leads {
            out.push_str(",\"leads\":true");
        }
        if let Some(l) = &p.left {
            out.push_str(",\"left\":");
            push_json_str(out, l);
        }
        out.push('}');
    }
    out.push(']');
}

fn push_strs(out: &mut String, v: &[String]) {
    out.push('[');
    for (i, s) in v.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_str(out, s);
    }
    out.push(']');
}

/// One war of the tab, as JSON, and the tags it names (`war_tags`).
pub struct Built {
    pub start_key: f64,
    pub json: String,
    pub tags: Vec<String>,
}

/// `build_wars`: every war in the campaign, as the Wars tab's JSON objects,
/// sorted by start. `saves` is (date, province owners) in walk order.
pub fn build(book: &Book, saves: &[(String, Vec<(i64, String)>)], m: &Mapping) -> Vec<Built> {
    // Date order, stable: a save's year fraction.
    let mut ordered: Vec<&(String, Vec<(i64, String)>)> = saves.iter().collect();
    ordered.sort_by(|a, b| year_fraction(&a.0).partial_cmp(&year_fraction(&b.0))
        .unwrap_or(std::cmp::Ordering::Equal));
    let books: Vec<(String, FxMap<i64, String>)> = ordered.iter()
        .map(|(d, owners)| (d.clone(), owners.iter().cloned().collect())).collect();
    let mut state_provinces: FxMap<&str, Vec<i64>> = FxMap::default();
    for (pid, state) in m.province_regions.iter() {
        state_provinces.entry(state.as_str()).or_default().push(*pid);
    }
    let ledger_dates: Vec<f64> = books.iter().map(|(d, _)| year_fraction(d)).collect();
    let empty: FxMap<i64, String> = FxMap::default();

    let mut out = Vec::new();
    for key in &book.order {
        let war = &book.wars[key];
        let mut battles: Vec<&Battle> = war.battles.values().collect();
        let bkey = |b: &Battle| match &b.date {
            Some(d) if !d.is_empty() => year_fraction(d),
            _ => 9999.0,
        };
        battles.sort_by(|a, b| bkey(a).partial_cmp(&bkey(b)).unwrap_or(std::cmp::Ordering::Equal)
            .then(a.name.cmp(&b.name)));
        // `max(..., key=year_fraction, default="")`: the first of equals.
        let mut last_battle = String::new();
        let mut best = f64::NEG_INFINITY;
        for b in &battles {
            if let Some(d) = &b.date {
                if d.is_empty() {
                    continue;
                }
                let y = year_fraction(d);
                if last_battle.is_empty() && best == f64::NEG_INFINITY || y > best {
                    best = y;
                    last_battle = d.clone();
                }
            }
        }
        let mut end = war.end.clone();
        if !end.is_empty() && !last_battle.is_empty()
            && year_fraction(&last_battle) > year_fraction(&end) {
            end = last_battle.clone();
        }
        let atk: i64 = battles.iter().map(|b| b.attacker.as_ref().map_or(0, |s| s.losses)).sum();
        let dfd: i64 = battles.iter().map(|b| b.defender.as_ref().map_or(0, |s| s.losses)).sum();
        let attackers = if war.attackers.is_empty() { vec![war.original_attacker.clone()] }
                        else { war.attackers.clone() };
        let defenders = if war.defenders.is_empty() { vec![war.original_defender.clone()] }
                        else { war.defenders.clone() };
        let by_side = side_losses(&battles, &attackers, &defenders);
        let mut listed: Vec<AnyGoal> = war.goalbook.values().map(|g| AnyGoal {
            casus_belli: &g.casus_belli, actor: &g.actor, receiver: &g.receiver,
            province: g.province, added: &g.added, fulfilled: Some(g.fulfilled),
        }).collect();
        if listed.is_empty() && !war.goal.actor.is_empty() {
            listed.push(AnyGoal { casus_belli: &war.goal.casus_belli, actor: &war.goal.actor,
                                  receiver: &war.goal.receiver, province: war.goal.province,
                                  added: "", fulfilled: None });
        }
        let has_start = !war.start.is_empty();
        let mut before: &FxMap<i64, String> = if has_start {
            ledger_at(&books, &ledger_dates, &war.start, true).unwrap_or(&empty)
        } else { &empty };
        if !end.is_empty() && !ledger_dates.is_empty() && ledger_dates[0] >= year_fraction(&end) {
            before = &empty;
        }
        let after: &FxMap<i64, String> = if has_start {
            let when = if !end.is_empty() { end.as_str() } else { war.start.as_str() };
            ledger_at(&books, &ledger_dates, when, false).unwrap_or(&empty)
        } else { &empty };
        let mut goals_json = String::from("[");
        let mut transfers: Vec<(String, String, String, String, usize, usize)> = Vec::new();
        let (mut checkable, mut won) = (0usize, 0usize);
        let mut tags: Vec<String> = Vec::new();
        for (gi, g) in listed.iter().enumerate() {
            let state = m.province_regions.get(&g.province).map(|s| s.as_str());
            let wanted: Vec<i64> = match state {
                Some(st) if !st.is_empty() => state_provinces.get(st).cloned().unwrap_or_default(),
                _ => if g.province != 0 { vec![g.province] } else { vec![] },
            };
            let took: Vec<i64> = wanted.iter().copied().filter(|p| {
                before.get(p).map(|o| o.as_str()) == Some(g.receiver)
                    && after.get(p).map(|o| o.as_str()) == Some(g.actor)
            }).collect();
            let had = wanted.iter().filter(|p| before.get(p).map(|o| o.as_str()) == Some(g.receiver)).count();
            let met = had > 0 && took.len() == had;
            let part = !took.is_empty() && took.len() < had;
            if had > 0 {
                checkable += 1;
                if met || part {
                    won += 1;
                }
            }
            if gi > 0 {
                goals_json.push(',');
            }
            goals_json.push_str("{\"cb\":");
            push_json_str(&mut goals_json, g.casus_belli);
            goals_json.push_str(",\"actor\":");
            push_json_str(&mut goals_json, g.actor);
            goals_json.push_str(",\"receiver\":");
            push_json_str(&mut goals_json, g.receiver);
            goals_json.push_str(",\"state\":");
            push_json_str(&mut goals_json, &state_label(state, g.province, m));
            goals_json.push_str(",\"added\":");
            push_json_str(&mut goals_json, g.added);
            goals_json.push_str(",\"took\":");
            push_int(&mut goals_json, took.len() as i64);
            goals_json.push_str(",\"of\":");
            push_int(&mut goals_json, had as i64);
            goals_json.push_str(",\"met\":");
            goals_json.push_str(if met { "true" } else { "false" });
            goals_json.push_str(",\"part\":");
            goals_json.push_str(if part { "true" } else { "false" });
            goals_json.push_str(",\"sieged\":");
            goals_json.push_str(match g.fulfilled { Some(true) => "true", Some(false) => "false",
                                                     None => "null" });
            goals_json.push_str(",\"checkable\":");
            goals_json.push_str(if had > 0 { "true" } else { "false" });
            goals_json.push('}');
            tags.push(g.actor.to_string());
            tags.push(g.receiver.to_string());
            if !took.is_empty() {
                transfers.push((state.unwrap_or("").to_string(), state_label(state, took[0], m),
                                g.receiver.to_string(), g.actor.to_string(), took.len(), had));
            }
        }
        goals_json.push(']');
        let outcome = if checkable > 0 { format!("{} of {} taken", won, checkable) } else { String::new() };

        let mut j = String::with_capacity(4096);
        j.push_str("{\"name\":");
        push_json_str(&mut j, &war.name);
        j.push_str(",\"start\":");
        push_json_str(&mut j, &war.start);
        j.push_str(",\"end\":");
        push_json_str(&mut j, &end);
        j.push_str(",\"active\":");
        j.push_str(if war.active { "true" } else { "false" });
        j.push_str(",\"attackers\":");
        push_strs(&mut j, &attackers);
        j.push_str(",\"defenders\":");
        push_strs(&mut j, &defenders);
        j.push_str(",\"attacker_parties\":");
        push_parties(&mut j, &participants(&attackers, &war.join_dates, true, &war.original_attacker,
                                           &war.start, &war.leave_dates, &end));
        j.push_str(",\"defender_parties\":");
        push_parties(&mut j, &participants(&defenders, &war.join_dates, false,
                                           &war.original_defender, &war.start,
                                           &war.leave_dates, &end));
        j.push_str(",\"goal\":{\"casus_belli\":");
        push_json_str(&mut j, &war.goal.casus_belli);
        j.push_str(",\"actor\":");
        push_json_str(&mut j, &war.goal.actor);
        j.push_str(",\"receiver\":");
        push_json_str(&mut j, &war.goal.receiver);
        j.push_str(",\"province\":");
        push_int(&mut j, war.goal.province);
        j.push_str("},\"losses\":[");
        push_int(&mut j, atk);
        j.push(',');
        push_int(&mut j, dfd);
        j.push_str("],\"side_losses\":[");
        push_int(&mut j, by_side[0]);
        j.push(',');
        push_int(&mut j, by_side[1]);
        j.push(',');
        push_int(&mut j, by_side[2]);
        j.push_str("],\"outcome\":");
        push_json_str(&mut j, &outcome);
        j.push_str(",\"goals\":");
        j.push_str(&goals_json);
        j.push_str(",\"dated\":");
        push_int(&mut j, battles.iter().filter(|b| b.date.as_ref().is_some_and(|d| !d.is_empty())).count() as i64);
        j.push_str(",\"battles\":[");
        for (i, b) in battles.iter().enumerate() {
            if i > 0 {
                j.push(',');
            }
            j.push_str("{\"sea\":");
            j.push_str(if at_sea(b, m.unit_kinds) { "true" } else { "false" });
            j.push_str(",\"name\":");
            push_json_str(&mut j, &b.name);
            j.push_str(",\"province\":");
            push_int(&mut j, b.location);
            j.push_str(",\"date\":");
            push_json_str(&mut j, b.date.as_deref().unwrap_or(""));
            j.push_str(",\"won\":");
            j.push_str(if b.attacker_won { "true" } else { "false" });
            for (label, side) in [(",\"a\":[", &b.attacker), (",\"d\":[", &b.defender)] {
                j.push_str(label);
                let (c, l, n) = match side {
                    Some(s) => (s.country.as_str(), s.leader.as_str(), s.losses),
                    None => ("", "", 0),
                };
                push_json_str(&mut j, c);
                j.push(',');
                push_json_str(&mut j, l);
                j.push(',');
                push_int(&mut j, n);
                j.push(',');
                push_json_str(&mut j, &units(side));
                j.push(']');
                tags.push(c.to_string());
            }
            j.push('}');
        }
        j.push_str("],\"transfers\":[");
        for (i, t) in transfers.iter().enumerate() {
            if i > 0 {
                j.push(',');
            }
            j.push('[');
            push_json_str(&mut j, &t.0);
            j.push(',');
            push_json_str(&mut j, &t.1);
            j.push(',');
            push_json_str(&mut j, &t.2);
            j.push(',');
            push_json_str(&mut j, &t.3);
            j.push(',');
            push_int(&mut j, t.4 as i64);
            j.push(',');
            push_int(&mut j, t.5 as i64);
            j.push(']');
            tags.push(t.2.clone());
            tags.push(t.3.clone());
        }
        j.push_str("]}");
        tags.extend(attackers.iter().cloned());
        tags.extend(defenders.iter().cloned());
        let start_key = if war.start.is_empty() { 9999.0 } else { year_fraction(&war.start) };
        out.push(Built { start_key, json: j, tags });
    }
    out.sort_by(|a, b| a.start_key.partial_cmp(&b.start_key).unwrap_or(std::cmp::Ordering::Equal));
    out
}

/// `war_tags(wars)`, sorted.
pub fn war_tags(built: &[Built]) -> Vec<String> {
    let mut v: Vec<String> = built.iter().flat_map(|b| b.tags.iter().cloned())
        .filter(|t| !t.is_empty() && t != "---").collect();
    v.sort();
    v.dedup();
    v
}

/// Every nation the book names as fighting (`flags_for`'s fighters), sorted.
pub fn fighters(book: &Book) -> Vec<String> {
    let mut v: Vec<String> = Vec::new();
    for held in book.wars.values() {
        v.extend(held.attackers.iter().cloned());
        v.extend(held.defenders.iter().cloned());
        for b in held.battles.values() {
            for side in [&b.attacker, &b.defender] {
                if let Some(s) = side {
                    if !s.country.is_empty() {
                        v.push(s.country.clone());
                    }
                }
            }
        }
    }
    v.retain(|t| !t.is_empty() && t != "---");
    v.sort();
    v.dedup();
    v
}


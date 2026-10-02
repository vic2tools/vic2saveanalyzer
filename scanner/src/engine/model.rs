// One save as the report engine holds it: typed, in the analyzer's order.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// A save's `(meta, nations)` as the analyzer's Python reader built them,
// as Rust structs, fold for fold: the same fields, filled by the same rules,
// in the same order. Where Python's
// record holds an int in one save and a float in another -- a nation with no
// naval base keeps the blank record's `0`, one with a base gets `47.0` --
// the field is a `Num`, because the tables print the two differently.

use crate::clause::{self, Tree, V};
use crate::country::Country;
use crate::omap::OMap;
use crate::fx::{FxMap, FxSet};
use crate::province::Scan;
use crate::pyfmt::Num;
use crate::text::latin1;

pub type R<T> = Result<T, ()>;

#[derive(Clone, Debug, PartialEq)]
pub struct Side {
    pub country: String,
    pub leader: String,
    pub losses: i64,
    pub units: OMap<String, i64>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Battle {
    pub name: String,
    pub location: i64,
    pub date: Option<String>,
    pub attacker_won: bool,
    pub attacker: Option<Side>,
    pub defender: Option<Side>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Goal {
    pub casus_belli: String,
    pub actor: String,
    pub receiver: String,
    pub province: i64,
    pub added: String,
    pub fulfilled: bool,
}

/// `original_wargoal`: the four fields `read_war` keeps of it.
#[derive(Clone, Debug, PartialEq, Default)]
pub struct FirstGoal {
    pub casus_belli: String,
    pub actor: String,
    pub receiver: String,
    pub province: i64,
}

/// `readwar.read_war`'s dict.
#[derive(Clone, Debug, PartialEq)]
pub struct War {
    pub name: String,
    pub active: bool,
    pub start: String,
    pub end: String,
    pub original_attacker: String,
    pub original_defender: String,
    pub attackers: Vec<String>,
    pub defenders: Vec<String>,
    pub fighting: Vec<String>,
    /// (date, tag, on the attacking side)
    pub joins: Vec<(String, String, bool)>,
    pub leaves: Vec<(String, String, bool)>,
    pub goals: Vec<Goal>,
    pub goal: FirstGoal,
    pub battles: Vec<Battle>,
}

/// `readsave.read_worldmarket`'s dict, the parts anything reads.
#[derive(Clone, Debug, Default)]
pub struct Market {
    pub current: OMap<String, f64>,
    pub history: Vec<(String, String, f64)>,
    /// world_pool, supply, demand, real_demand, actual_sold,
    /// actual_sold_world, discovered -- in that order.
    pub snapshot: [OMap<String, f64>; 7],
}

/// What a save says that is not one nation's: the meta dict.
#[derive(Clone, Debug, Default)]
pub struct Meta {
    pub file: String,
    pub date: String,
    pub player: String,
    pub world_pop: i64,
    /// (province, owner, controller), in the order the file lists them.
    pub province_owner: Vec<(i64, String, String)>,
    pub great_nations: Vec<i64>,
    pub wars: Vec<War>,
    pub market: Option<Market>,
}

/// One population group of a nation: `population_by_state`'s row.
#[derive(Clone, Debug)]
pub struct Group {
    pub group: i64,
    pub size: i64,
    pub literate: f64,
    pub types: Vec<(String, i64)>,
    pub cultures: Vec<(String, i64)>,
    pub provinces: i64,
}

/// `nation.blank_nation()`, filled.
#[derive(Clone, Debug, Default)]
pub struct Nation {
    /// The key the save's dict holds it under: the owner tag the provinces
    /// name. `tag` is the record's own field, from its country block.
    pub key: String,
    pub tag: String,
    pub primary_culture: String,
    pub accepted_cultures: Vec<String>,
    pub civilized: String,
    pub government: String,
    pub capital: String,
    pub nationalvalue: String,
    pub prestige: f64,
    pub infamy: f64,
    pub treasury: f64,
    pub tax_base: f64,
    pub war_exhaustion: f64,
    pub plurality: f64,
    pub research_points: f64,
    pub revanchism: f64,
    pub ruling_party: Num,
    pub techs: i64,
    pub brigades: i64,
    pub armies: i64,
    pub ships: i64,
    pub navies: i64,
    pub ships_by_type: OMap<String, i64>,
    pub ship_crew: OMap<String, f64>,
    pub regiments_by_type: OMap<String, i64>,
    pub units_at: OMap<i64, OMap<String, i64>>,
    pub men_at: OMap<i64, OMap<String, i64>>,
    pub mobilized_brigades: i64,
    pub regular_brigades: i64,
    pub mobilizing: i64,
    pub is_mobilized: i64,
    pub tech_list: Vec<String>,
    pub invention_ids: Vec<i64>,
    pub modifiers: Vec<String>,
    pub country_flags: FxSet<String>,
    pub reforms: OMap<String, String>,
    pub human: bool,
    pub army_techs: i64,
    pub navy_techs: i64,
    pub factory_count: i64,
    pub factory_levels: i64,
    pub states: i64,
    pub provinces: i64,
    pub naval_base_levels: Num,
    pub max_naval_base: Num,
    pub ports: i64,
    pub fort_levels: Num,
    pub railroad_levels: Num,
    pub total_pop: i64,
    pub pop_by_type: OMap<String, i64>,
    pub pop_by_culture: OMap<String, i64>,
    pub life_unmet: i64,
    pub starving: i64,
    pub soldiers_noncolonial: i64,
    pub pop_noncolonial: i64,
    pub literacy_noncolonial: f64,
    pub soldier_pops_at: Vec<(i64, Vec<i64>)>,
    pub core_provinces: FxSet<i64>,
    pub colonial_level: FxMap<i64, i64>,
    pub province_colonial: FxMap<i64, i64>,
    pub population_by_state: Vec<Group>,
    pub goods_supply: OMap<String, f64>,
    /// (pop type, culture, size, province), in save order.
    pub mobilizable_pops: Vec<(String, String, i64, i64)>,
    pub mob_excluded_culture: i64,
    pub colonial_provinces: FxSet<i64>,
    pub province_state: FxMap<i64, i64>,
    pub occupied_provinces: FxSet<i64>,
    pub literacy_weighted: f64,
    pub con_weighted: f64,
    pub mil_weighted: f64,
    pub money_total: f64,
}

impl Default for Num {
    fn default() -> Self {
        Num::I(0)
    }
}

impl Nation {
    fn blank() -> Nation {
        Nation::default()
    }

    /// The primary culture and every accepted one (`accepted_cultures_of`).
    pub fn accepts(&self, culture: &str) -> bool {
        (!self.primary_culture.is_empty() && self.primary_culture == culture)
            || self.accepted_cultures.iter().any(|c| c == culture)
    }
}

// ------------------------------------------------------------------ folds

fn fold_provinces(nat: &mut Nation, n: &crate::province::Nation, names: &[Vec<u8>]) {
    nat.provinces += n.provinces;
    nat.ports += n.ports;
    nat.total_pop += n.total_pop;
    nat.life_unmet += n.life_unmet;
    nat.starving += n.starving;
    // `_add_if`: only a value Python calls true.
    if n.naval_base_levels != 0.0 {
        nat.naval_base_levels = nat.naval_base_levels.add(Num::F(n.naval_base_levels));
    }
    // `_highest`.
    if Num::F(n.max_naval_base).gt(nat.max_naval_base) {
        nat.max_naval_base = Num::F(n.max_naval_base);
    }
    nat.fort_levels = nat.fort_levels.add(Num::F(n.fort_levels));
    nat.railroad_levels = nat.railroad_levels.add(Num::F(n.railroad_levels));
    nat.literacy_weighted += n.literacy_weighted;
    nat.con_weighted += n.con_weighted;
    nat.mil_weighted += n.mil_weighted;
    nat.money_total += n.money_total;
    nat.core_provinces.extend(n.cores.iter().copied());
    nat.occupied_provinces.extend(n.occupied.iter().copied());
    for (pid, flag) in &n.colonial {
        nat.province_colonial.insert(*pid, *flag);
    }
    for (k, t) in n.pop_by_type.order.iter().zip(&n.pop_by_type.total) {
        *nat.pop_by_type.entry(latin1(k), || 0) += t;
    }
    for (k, t) in n.pop_by_culture.order.iter().zip(&n.pop_by_culture.total) {
        *nat.pop_by_culture.entry(latin1(k), || 0) += t;
    }
    // `_population_rows`: the field replaced, one row a group.
    nat.population_by_state = n.population_order.iter().map(|group| {
        let st = &n.population_by_state[group];
        let pairs = |c: &crate::province::Counter| -> Vec<(String, i64)> {
            // A dict built from pairs: a name met twice keeps its first place
            // and its last value, which a Counter never gives it anyway.
            c.order.iter().zip(&c.total).map(|(k, t)| (latin1(k), *t)).collect()
        };
        Group { group: *group, size: st.total, literate: st.literate, types: pairs(&st.types),
                cultures: pairs(&st.cultures), provinces: st.provinces }
    }).collect();
    nat.soldiers_noncolonial += n.soldiers_noncolonial;
    nat.pop_noncolonial += n.pop_noncolonial;
    nat.literacy_noncolonial += n.literacy_noncolonial;
    nat.mob_excluded_culture += n.mob_excluded_culture;
    let mut at: Vec<&i64> = n.soldier_pops_at.keys().collect();
    at.sort();
    for pid in at {
        match nat.soldier_pops_at.iter_mut().find(|(p, _)| p == pid) {
            Some((_, v)) => v.extend(&n.soldier_pops_at[pid]),
            None => nat.soldier_pops_at.push((*pid, n.soldier_pops_at[pid].clone())),
        }
    }
    let name = |i: u32| latin1(&names[i as usize]);
    nat.mobilizable_pops.extend(n.mobilizable.iter()
        .map(|(kind, culture, size, pid)| (name(*kind), name(*culture), *size, *pid)));
}

fn fold_country(nat: &mut Nation, c: &Country) {
    nat.tag = c.tag.clone();
    for (name, value) in &c.scalars {
        let v = value.clone();
        match name.as_str() {
            "nationalvalue" => nat.nationalvalue = v,
            "primary_culture" => nat.primary_culture = v,
            "civilized" => nat.civilized = v,
            "government" => nat.government = v,
            "capital" => nat.capital = v,
            _ => {}
        }
    }
    for (name, value) in &c.numerics {
        let v = *value;
        match name.as_str() {
            "prestige" => nat.prestige = v,
            "infamy" => nat.infamy = v,
            "treasury" => nat.treasury = v,
            "tax_base" => nat.tax_base = v,
            "war_exhaustion" => nat.war_exhaustion = v,
            "revanchism" => nat.revanchism = v,
            "plurality" => nat.plurality = v,
            "research_points" => nat.research_points = v,
            "ruling_party" => nat.ruling_party = Num::F(v),
            _ => {}
        }
    }
    nat.is_mobilized = c.is_mobilized;
    nat.human = c.human;
    for (k, v) in &c.reforms {
        nat.reforms.set(k.clone(), v.clone());
    }
    if !c.accepted_cultures.is_empty() {
        nat.accepted_cultures = c.accepted_cultures.clone();
    }
    if !c.country_flags.is_empty() {
        nat.country_flags = c.country_flags.iter().cloned().collect();
    }
    nat.modifiers.extend(c.modifiers.iter().cloned());
    if !c.goods_supply.is_empty() {
        let mut m = OMap::new();
        for (g, v) in &c.goods_supply {
            m.set(g.clone(), *v);
        }
        nat.goods_supply = m;
    }
    if !c.invention_ids.is_empty() {
        nat.invention_ids = c.invention_ids.clone();
    }
    nat.mobilizing += c.mobilizing;
    nat.states += c.states;
    for (a, b) in &c.province_state {
        nat.province_state.insert(*a, *b);
    }
    nat.colonial_provinces.extend(c.colonial_provinces.iter().copied());
    for (a, b) in &c.colonial_level {
        nat.colonial_level.insert(*a, *b);
    }
    nat.factory_count += c.factory_count;
    nat.factory_levels += c.factory_levels;
    nat.techs += c.techs;
    nat.tech_list.extend(c.tech_list.iter().cloned());
    nat.army_techs += c.army_techs;
    nat.navy_techs += c.navy_techs;
    nat.brigades += c.brigades;
    nat.armies += c.armies;
    nat.navies += c.navies;
    nat.ships += c.ships;
    for (t, n) in &c.regiments_by_type {
        *nat.regiments_by_type.entry(t.clone(), || 0) += n;
    }
    for (t, n) in &c.ships_by_type {
        *nat.ships_by_type.entry(t.clone(), || 0) += n;
    }
    for (t, n) in &c.ship_crew {
        *nat.ship_crew.entry(t.clone(), || 0.0) += n;
    }
    for (target, rows) in [(&mut nat.units_at, &c.units_at), (&mut nat.men_at, &c.men_at)] {
        for (pid, items) in rows {
            let counter = target.entry(*pid, OMap::new);
            for (kind, n) in items {
                *counter.entry(kind.clone(), || 0) += n;
            }
        }
    }
}

/// What `read_rest` found: the wars, the market, the great power list.
pub struct Rest {
    pub wars: Vec<War>,
    pub market: Option<Market>,
    pub great: Vec<i64>,
}

/// One save, as the engine keeps it: its meta and its nations holding land
/// or people, in the order the provinces first named them.
pub struct Save {
    pub meta: Meta,
    pub nations: Vec<Nation>,
}

/// `readsave.analyze_save`'s answer, from the scanner's own reading.
pub fn build(file: String, date: String, player: String, scan: &Scan, countries: &[Country],
             rest: Rest) -> R<Save> {
    let mut order: Vec<Vec<u8>> = Vec::new();
    let mut nations: FxMap<Vec<u8>, Nation> = FxMap::default();
    for tag in &scan.seen {
        let scanned = &scan.nations[tag.as_slice()];
        if !(scanned.provinces > 0 || scanned.total_pop > 0) {
            continue;
        }
        let nat = nations.entry(tag.clone()).or_insert_with(|| {
            order.push(tag.clone());
            Nation::blank()
        });
        fold_provinces(nat, scanned, &scan.words.names);
    }
    for c in countries {
        let key: Vec<u8> = c.tag.chars().map(|ch| ch as u32 as u8).collect();
        if let Some(nat) = nations.get_mut(&key) {
            fold_country(nat, c);
        }
    }
    // `_settle`: a regiment is regular unless its pop is known and is not a
    // soldier.
    let mut registry: FxMap<i64, bool> = FxMap::default();
    registry.reserve(scan.pop_ids.len());
    for (id, kind) in scan.pop_ids.iter().zip(&scan.pop_kinds) {
        let name = scan.words.names.get(*kind as usize).ok_or(())?;
        registry.insert(*id, name.as_slice() == b"soldiers");
    }
    let mut live = Vec::with_capacity(order.len());
    for tag in &order {
        let mut nat = nations.remove(tag).ok_or(())?;
        nat.key = latin1(tag);
        for c in countries {
            // The tag as latin-1 bytes, as `tag` is: its UTF-8 differs for
            // any letter past ASCII.
            if c.tag.chars().map(|ch| ch as u32 as u8).eq(tag.iter().copied()) {
                for pid in &c.regiment_pops {
                    match registry.get(pid) {
                        None | Some(true) => nat.regular_brigades += 1,
                        Some(false) => nat.mobilized_brigades += 1,
                    }
                }
            }
        }
        if nat.provinces > 0 || nat.total_pop > 0 {
            live.push(nat);
        }
    }
    let meta = Meta {
        file,
        date,
        player,
        world_pop: scan.world_pop,
        province_owner: scan.owners.iter()
            .map(|(pid, o, h)| (*pid, latin1(o), latin1(h))).collect(),
        great_nations: rest.great,
        wars: rest.wars,
        market: rest.market,
    };
    Ok(Save { meta, nations: live })
}

// ------------------------------------------------------- wars and market

fn s(b: &[u8]) -> String {
    latin1(b)
}

fn side(v: Option<&V>) -> R<Option<Side>> {
    let block = match v {
        Some(V::Dict(d)) => d,
        _ => return Ok(None),
    };
    let mut units = OMap::new();
    for (key, val) in &block.pairs {
        if key == b"country" || key == b"leader" || key == b"losses" || key.first() == Some(&b'_') {
            continue;
        }
        let n = clause::unwrap_overflow(clause::to_int(Some(val), 0)?);
        if n != 0 {
            units.set(s(key), n);
        }
    }
    Ok(Some(Side {
        country: s(&clause::name(block.get(b"country"))?),
        leader: s(&clause::name(block.get(b"leader"))?),
        losses: clause::unwrap_overflow(clause::to_int(block.get(b"losses"), 0)?),
        units,
    }))
}

fn battle(raw: &V, when: Option<&[u8]>, out: &mut Vec<Battle>) -> R<()> {
    let raw = match raw {
        V::Dict(d) => d,
        _ => return Ok(()),
    };
    out.push(Battle {
        name: s(&clause::name(raw.get(b"name"))?),
        location: clause::to_int(raw.get(b"location"), 0)?,
        date: when.map(s),
        attacker_won: clause::yes(raw.get(b"result"))?,
        attacker: side(raw.get(b"attacker"))?,
        defender: side(raw.get(b"defender"))?,
    });
    Ok(())
}

fn sorted_names(mut v: Vec<Vec<u8>>) -> Vec<String> {
    v.sort();
    v.dedup();
    v.iter().map(|x| s(x)).collect()
}

/// `readwar.read_war(block, active)`, or None for a block that is not a dict.
pub fn read_war(v: &V, active: bool) -> R<Option<War>> {
    let block = match v {
        V::Dict(d) => d,
        _ => return Ok(None),
    };
    let empty = Tree::default();
    let history = match block.get(b"history") {
        Some(V::Dict(d)) => d,
        _ => &empty,
    };
    let mut joined: Vec<(Vec<u8>, Vec<u8>, bool)> = Vec::new();
    let mut left: Vec<(Vec<u8>, Vec<u8>, bool)> = Vec::new();
    let mut battles: Vec<Battle> = Vec::new();
    let mut battle_dates: Vec<Vec<u8>> = Vec::new();
    for (key, value) in &history.pairs {
        if key == b"battle" {
            for raw in clause::as_list(Some(value)) {
                battle(raw, None, &mut battles)?;
            }
            continue;
        }
        if !clause::dated(key)? {
            continue;
        }
        for entry in clause::as_list(Some(value)) {
            let entry = match entry {
                V::Dict(d) => d,
                _ => continue,
            };
            for (what, who) in &entry.pairs {
                if what == b"battle" {
                    for raw in clause::as_list(Some(who)) {
                        let before = battles.len();
                        battle(raw, Some(key), &mut battles)?;
                        if battles.len() > before {
                            battle_dates.push(key.clone());
                        }
                    }
                } else if what == b"add_attacker" || what == b"add_defender" {
                    joined.push((key.clone(), clause::name(Some(who))?, what == b"add_attacker"));
                } else if what == b"rem_attacker" || what == b"rem_defender" {
                    left.push((key.clone(), clause::name(Some(who))?, what == b"rem_attacker"));
                }
            }
        }
    }
    let mut goals = Vec::new();
    for raw in clause::as_list(block.get(b"war_goal")) {
        let raw = match raw {
            V::Dict(d) => d,
            _ => continue,
        };
        let g = Goal {
            casus_belli: s(&clause::name(raw.get(b"casus_belli"))?),
            actor: s(&clause::name(raw.get(b"actor"))?),
            receiver: s(&clause::name(raw.get(b"receiver"))?),
            province: clause::to_int(raw.get(b"state_province_id"), 0)?,
            added: s(&clause::name(raw.get(b"date"))?),
            fulfilled: clause::yes(raw.get(b"is_fulfilled"))?,
        };
        if !g.actor.is_empty() || !g.receiver.is_empty() {
            goals.push(g);
        }
    }
    let empty_goal = Tree::default();
    let first = match block.get(b"original_wargoal") {
        Some(V::Dict(d)) => d,
        _ => &empty_goal,
    };
    let dates: Vec<&Vec<u8>> = joined.iter().map(|j| &j.0)
        .chain(left.iter().map(|l| &l.0))
        .chain(battle_dates.iter())
        .collect();
    let pick = |want_max: bool| -> Vec<u8> {
        let mut best: Option<&Vec<u8>> = None;
        for d in &dates {
            let better = match best {
                None => true,
                Some(b) if want_max => clause::date_key(d) > clause::date_key(b),
                Some(b) => clause::date_key(d) < clause::date_key(b),
            };
            if better {
                best = Some(d);
            }
        }
        best.cloned().unwrap_or_default()
    };
    let start = if dates.is_empty() { Vec::new() } else { pick(false) };
    let end = if !dates.is_empty() && !active { pick(true) } else { Vec::new() };
    let mut fighting = Vec::new();
    for side_key in [&b"attacker"[..], &b"defender"[..]] {
        for tag in clause::as_list(block.get(side_key)) {
            fighting.push(clause::name(Some(tag))?);
        }
    }
    let event = |list: &Vec<(Vec<u8>, Vec<u8>, bool)>| -> Vec<(String, String, bool)> {
        list.iter().map(|(d, w, a)| (s(d), s(w), *a)).collect()
    };
    let one_side = |attacking: bool| -> Vec<Vec<u8>> {
        joined.iter().filter(|j| j.2 == attacking).map(|j| j.1.clone()).collect()
    };
    Ok(Some(War {
        name: s(&clause::name(block.get(b"name"))?),
        active,
        start: s(&start),
        end: s(&end),
        original_attacker: s(&clause::name(block.get(b"original_attacker"))?),
        original_defender: s(&clause::name(block.get(b"original_defender"))?),
        attackers: sorted_names(one_side(true)),
        defenders: sorted_names(one_side(false)),
        fighting: sorted_names(fighting),
        joins: event(&joined),
        leaves: event(&left),
        goals,
        goal: FirstGoal {
            casus_belli: s(&clause::name(first.get(b"casus_belli"))?),
            actor: s(&clause::name(first.get(b"actor"))?),
            receiver: s(&clause::name(first.get(b"receiver"))?),
            province: clause::to_int(first.get(b"state_province_id"), 0)?,
        },
        battles,
    }))
}

fn numeric(block: &Tree, key: &[u8]) -> R<OMap<String, f64>> {
    let mut out = OMap::new();
    if let Some(V::Dict(sub)) = block.get(key) {
        for (k2, v) in &sub.pairs {
            if k2.first() == Some(&b'_') {
                continue;
            }
            if let V::Str(_) = v {
                out.set(s(k2), clause::to_float(Some(v), 0.0)?);
            }
        }
    }
    Ok(out)
}

/// `readsave.read_worldmarket(block, save_date)`.
pub fn read_worldmarket(block: &Tree) -> R<Market> {
    let current = numeric(block, b"price_pool")?;
    let history_blocks: Vec<&Tree> = clause::as_list(block.get(b"price_history"))
        .into_iter()
        .filter_map(|v| match v { V::Dict(d) => Some(d), _ => None })
        .collect();
    let last_update = match block.get(b"price_history_last_update") {
        Some(V::Str(x)) => clause::unquote(x).to_vec(),
        _ => Vec::new(),
    };
    let mut history = Vec::new();
    let count = history_blocks.len() as i64;
    for (idx, snap) in history_blocks.iter().enumerate() {
        let stamp = if last_update.is_empty() {
            Vec::new()
        } else {
            clause::shift_months(&last_update, count - 1 - idx as i64)?
        };
        if stamp.is_empty() {
            continue;
        }
        let stamp = s(&stamp);
        for (good, price) in &snap.pairs {
            if good.first() == Some(&b'_') {
                continue;
            }
            if let V::Str(_) = price {
                history.push((stamp.clone(), s(good), clause::to_float(Some(price), 0.0)?));
            }
        }
    }
    let keys: [&[u8]; 7] = [b"worldmarket_pool", b"supply_pool", b"demand", b"real_demand",
                            b"actual_sold", b"actual_sold_world", b"discovered_goods"];
    let mut snapshot: [OMap<String, f64>; 7] = Default::default();
    for (i, key) in keys.iter().enumerate() {
        snapshot[i] = numeric(block, key)?;
    }
    Ok(Market { current, history, snapshot })
}

/// The wars, the market and the great power list out of the save's
/// top-level blocks, each parsed as a generic tree (`clause`).
pub fn read_rest(text: &[u8], blocks: &[(&[u8], usize, usize)]) -> R<Rest> {
    let mut wars = Vec::new();
    let mut market = None;
    let mut seen_market = false;
    let mut great = Vec::new();
    for (key, at, stop) in blocks {
        let key = *key;
        let wanted = key == b"active_war" || key == b"previous_war" || key == b"great_nations"
            || (key == b"worldmarket" && !seen_market);
        if !wanted {
            continue;
        }
        let tree = clause::parse_span(&text[*at..(*stop).min(text.len())]);
        if key == b"great_nations" {
            great = clause::great_nations(&tree)?;
        } else if key == b"worldmarket" {
            seen_market = true;
            if let V::Dict(block) = &tree {
                market = Some(read_worldmarket(block)?);
            }
        } else if let Some(war) = read_war(&tree, key == b"active_war")? {
            wars.push(war);
        }
    }
    Ok(Rest { wars, market, great })
}

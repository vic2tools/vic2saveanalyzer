// What a mod's rules are worth to one nation: `modrules.py`, and the parts
// of `mod_reader.py` that ask a campaign's saves about the mod.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The mod itself is read by the analyzer's Python (`mod_reader`) and handed
// over as JSON (`engine.export_mod`); this holds it and answers the same
// questions `modrules` answers, in the same order, with the same arithmetic.
// A sum here is added in the order Python's `sum` adds it, because float
// addition is not associative and the mobilisation size is printed to five
// places.

use crate::py::json::J;
use crate::engine::finish::PreNation;
use crate::engine::model::{Meta, Nation};
use crate::save::names::{self, Sym};
use crate::util::omap::OMap;
use crate::util::fx::{FxMap, FxSet};
use crate::py::fmt::{py_float, py_sum, trunc_int};

/// Why a mod or a save could not be read.
#[derive(Debug)]
pub enum Decline {
    /// A refusal in words: the sentence a run is refused with, as Python's
    /// analyzer raised it (a mod with no rules, a file it cannot open).
    Raised(String),
    /// Something no mod or save the game loads should hold: the run stops
    /// over it (`engine::decline`).
    Unreadable(String),
}

impl Decline {
    /// The sentence, when this is a refusal in words.
    pub fn raised(&self) -> Option<&str> {
        match self {
            Decline::Raised(s) => Some(s),
            Decline::Unreadable(_) => None,
        }
    }

    pub fn text(&self) -> &str {
        match self {
            Decline::Raised(s) | Decline::Unreadable(s) => s,
        }
    }
}

pub type D<T> = Result<T, Decline>;

pub struct Invention {
    pub name: String,
    pub size: f64,
    pub techs: Vec<String>,
    pub tags: Vec<String>,
}

pub struct Rule {
    pub size: f64,
    pub techs: Vec<String>,
    pub tags: Vec<String>,
    pub requires: Vec<String>,
    pub base: Option<f64>,
    pub blockers: Vec<(f64, String)>,
}

pub struct Ship {
    pub name: String,
    /// hull, gun_power, evasion, torpedo_attack, score -- as floats.
    pub stats: [f64; 5],
    pub heavy: i64,
}

pub const SHIP_KEYS: [&str; 5] = ["hull", "gun_power", "evasion", "torpedo_attack", "score"];

/// {ship or "navy_base": {stat: delta}}, in the mod's order.
pub type Changes = Vec<(String, Vec<(String, f64)>)>;

pub struct NavalEffect {
    pub effects: Changes,
    pub techs: Vec<String>,
    pub tags: Vec<String>,
}

pub struct Triggered {
    pub name: String,
    pub size: f64,
    pub impact: f64,
    pub trigger: J,
}

/// `mod_reader.Mod`, the fields the engine reads.
pub struct Mod {
    pub path: String,
    pub invention_sequence: Vec<Invention>,
    pub party_policies: Vec<String>,
    pub localisation: FxMap<String, String>,
    pub base_prices: J,
    pub country_order: Vec<String>,
    pub formations: FxMap<String, FxSet<String>>,
    pub culture_names: J,
    pub display_names: J,
    pub province_names: OMap<i64, String>,
    pub province_regions: OMap<i64, String>,
    pub state_names: OMap<String, String>,
    pub state_names_j: J,
    pub unit_kinds: FxMap<String, String>,
    pub naval_units: Vec<Ship>,
    pub naval_effects: OMap<String, NavalEffect>,
    pub naval_tech_effects: FxMap<String, Changes>,
    pub technology: J,
    pub mob_impacts: FxMap<String, f64>,
    pub modifier_impacts: FxMap<String, f64>,
    pub reform_mob: FxMap<(String, String), f64>,
    pub reform_names: FxSet<String>,
    pub static_mob: FxMap<String, f64>,
    pub triggered_mob: Vec<Triggered>,
    pub culture_groups: FxMap<String, String>,
    pub continents: FxMap<i64, String>,
    pub defines: FxMap<String, f64>,
    pub strata: FxMap<String, String>,
    pub invention_rules: OMap<String, Rule>,
    pub event_mob: FxMap<String, f64>,
    pub tech_mob: FxMap<String, f64>,
    pub nv_mob: FxMap<String, f64>,
    pub tech_count: i64,
    /// Every technology the mod defines (`--check-inventions`).
    pub technologies: FxSet<String>,
    /// What the map and the flags need of the mod's files, worked out by
    /// the Python that read it.
    pub colours: FxMap<String, String>,
    pub sea: Vec<i64>,
    pub positions: Vec<(i64, f64, f64)>,
    pub flag_styles: FxMap<String, (String, bool)>,
    pub flag_roots: Vec<String>,
    pub map_bmp: String,
    pub map_csv: String,
    /// Settled against the campaign (`decode_indices`); None is "cannot".
    pub index_base: Option<i64>,
    /// The map's bitmap as (width, height, runs), when it was decoded ahead.
    pub raster: Option<(i64, i64, Vec<(i64, i64)>)>,
    /// The rates' lookups as tables indexed by name, made once the campaign
    /// is settled (`Dense::build`); None until then.
    pub dense: Option<Dense>,
}

impl Mod {
    /// The dense tables. A run makes them before anything asks for a rate.
    pub fn dense(&self) -> &Dense {
        self.dense.as_ref().expect("the mod's dense tables are made after the campaign is settled")
    }
}

/// What the rates look up per nation, as vectors indexed by `Sym::index`.
/// A name interned after the build is past the end: the mod does not name it.
pub struct Dense {
    tech_mob: Vec<f64>,
    event_mob: Vec<f64>,
    nv_mob: Vec<f64>,
    modifier_impact: Vec<f64>,
    reform_mob: FxMap<(Sym, Sym), f64>,
    /// Per tech, 1 + the index into `groups`; 0 when it has none.
    tech_group: Vec<u32>,
    groups: Vec<(String, String)>,
    /// Per tech, 1 + the index into `naval_changes`.
    naval_tech: Vec<u32>,
    naval_changes: Vec<Changes>,
}

fn dense_floats(map: &FxMap<String, f64>) -> Vec<f64> {
    let at: Vec<(usize, f64)> = map.iter().map(|(k, v)| (names::intern_str(k).index(), *v)).collect();
    let mut out = vec![0.0; names::len()];
    for (i, v) in at {
        out[i] = v;
    }
    out
}

fn dense_at(v: &[f64], s: Sym) -> f64 {
    v.get(s.index()).copied().unwrap_or(0.0)
}

impl Dense {
    /// `tech_group` is the run's tech -> (branch, line).
    pub fn build(m: &Mod, tech_group: &FxMap<String, (String, String)>) -> Dense {
        let mut groups: Vec<(String, String)> = Vec::new();
        let mut group_at: Vec<(usize, u32)> = Vec::new();
        for (tech, g) in tech_group {
            let k = match groups.iter().position(|x| x == g) {
                Some(k) => k,
                None => { groups.push(g.clone()); groups.len() - 1 }
            };
            group_at.push((names::intern_str(tech).index(), k as u32 + 1));
        }
        let mut naval_changes: Vec<Changes> = Vec::new();
        let mut naval_at: Vec<(usize, u32)> = Vec::new();
        for (tech, changes) in &m.naval_tech_effects {
            naval_changes.push(changes.clone());
            naval_at.push((names::intern_str(tech).index(), naval_changes.len() as u32));
        }
        let reform_mob: FxMap<(Sym, Sym), f64> = m.reform_mob.iter()
            .map(|((r, o), v)| ((names::intern_str(r), names::intern_str(o)), *v)).collect();
        let (tech_mob, event_mob, nv_mob, modifier_impact) = (
            dense_floats(&m.tech_mob), dense_floats(&m.event_mob), dense_floats(&m.nv_mob),
            dense_floats(&m.modifier_impacts));
        let mut tech_group_dense = vec![0u32; names::len()];
        for (i, k) in group_at {
            tech_group_dense[i] = k;
        }
        let mut naval_tech = vec![0u32; names::len()];
        for (i, k) in naval_at {
            naval_tech[i] = k;
        }
        Dense { tech_mob, event_mob, nv_mob, modifier_impact, reform_mob,
                tech_group: tech_group_dense, groups, naval_tech, naval_changes }
    }

    pub fn tech_mob(&self, s: Sym) -> f64 { dense_at(&self.tech_mob, s) }
    pub fn event_mob(&self, s: Sym) -> f64 { dense_at(&self.event_mob, s) }
    pub fn nv_mob(&self, s: Sym) -> f64 { dense_at(&self.nv_mob, s) }
    pub fn modifier_impact(&self, s: Sym) -> f64 { dense_at(&self.modifier_impact, s) }
    pub fn reform_mob(&self, reform: Sym, option: Sym) -> f64 {
        self.reform_mob.get(&(reform, option)).copied().unwrap_or(0.0)
    }

    /// `tech_groups.TECH_GROUP[tech]`: (branch, line).
    pub fn tech_group(&self, s: Sym) -> Option<(&str, &str)> {
        match self.tech_group.get(s.index()).copied().unwrap_or(0) {
            0 => None,
            k => { let g = &self.groups[k as usize - 1]; Some((g.0.as_str(), g.1.as_str())) }
        }
    }

    pub fn naval_tech(&self, s: Sym) -> Option<&Changes> {
        match self.naval_tech.get(s.index()).copied().unwrap_or(0) {
            0 => None,
            k => Some(&self.naval_changes[k as usize - 1]),
        }
    }
}

impl Mod {
    pub fn define(&self, key: &str) -> Option<f64> {
        self.defines.get(key).copied()
    }
}

/// `str(value)` of a trigger's value as Python has it: the text, or the
/// repr of a list or a block (`['a', 'b']`), which is what a condition
/// holding a list where one value belongs is judged by.
fn str_j(v: &J) -> String {
    fn repr(v: &J, out: &mut String) {
        match v {
            J::Str(s) => out.push_str(&crate::engine::modread::py_repr(s)),
            J::List(x) => {
                out.push('[');
                for (i, e) in x.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    repr(e, out);
                }
                out.push(']');
            }
            J::Obj(pairs) => {
                out.push('{');
                for (i, (k, e)) in pairs.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    out.push_str(&crate::engine::modread::py_repr(k));
                    out.push_str(": ");
                    repr(e, out);
                }
                out.push('}');
            }
            other => {
                let mut t = String::new();
                other.write(&mut t);
                out.push_str(&t);
            }
        }
    }
    match v {
        J::Str(s) => s.clone(),
        other => {
            let mut out = String::new();
            repr(other, &mut out);
            out
        }
    }
}

// ------------------------------------------------------------- triggers

/// What one save says about everybody (`save_world`).
pub struct World {
    pub year: i64,
    pub great_powers: FxSet<String>,
    pub at_war: FxSet<Sym>,
}

/// `modrules.great_powers(meta, mod)`.
pub fn great_powers(meta: &Meta, m: &Mod) -> Vec<String> {
    let order = &m.country_order;
    meta.great_nations.iter()
        .filter(|&&i| 0 < i && i <= order.len() as i64)
        .map(|&i| order[(i - 1) as usize].clone())
        .collect()
}

pub fn save_world(meta: &Meta, m: &Mod) -> World {
    let mut at_war = FxSet::default();
    for war in &meta.wars {
        if !war.active {
            continue;
        }
        if !war.fighting.is_empty() {
            at_war.extend(war.fighting.iter().copied());
        } else {
            at_war.extend(war.attackers.iter().copied());
            at_war.extend(war.defenders.iter().copied());
        }
    }
    let head = meta.date.split('.').next().unwrap_or("");
    let year = if !head.is_empty() && head.chars().all(|c| c.is_ascii_digit()) {
        head.parse::<i64>().unwrap_or(0)
    } else {
        0
    };
    World {
        year,
        great_powers: great_powers(meta, m).into_iter().collect(),
        at_war,
    }
}

/// Python's three-valued answers.
type T = Option<bool>;

fn all(results: &[T]) -> T {
    if results.iter().any(|r| *r == Some(false)) {
        return Some(false);
    }
    if results.iter().any(|r| r.is_none()) { None } else { Some(true) }
}

fn any(results: &[T]) -> T {
    if results.iter().any(|r| *r == Some(true)) {
        return Some(true);
    }
    if results.iter().any(|r| r.is_none()) { None } else { Some(false) }
}

/// `_conditions`: a block as single-condition pairs.
fn conditions(block: &J) -> Vec<(&str, &J)> {
    let mut out = Vec::new();
    for (key, value) in block.pairs() {
        if key.starts_with('_') {
            continue;
        }
        match value {
            J::List(v) => out.extend(v.iter().map(|x| (key.as_str(), x))),
            one => out.push((key.as_str(), one)),
        }
    }
    out
}

fn unquote(s: &str) -> &str {
    crate::save::text::unquote(s)
}

/// `to_int(text, default)`: `int(float(text))`, its ValueError the default
/// (`int(nan)` is one). Infinity is an OverflowError, which Python let out.
fn to_int(text: &str, default: i64) -> D<i64> {
    match py_float(text) {
        None => Ok(default),
        Some(f) if f.is_nan() => Ok(default),
        Some(f) => trunc_int(f).ok_or_else(|| Decline::Unreadable("int() of infinity in a trigger".into())),
    }
}

/// `to_int(nat.get("capital"), -1)`: the capital is a string of the save's.
fn capital(nat: &Nation) -> D<i64> {
    to_int(&nat.capital, -1)
}

pub struct Asker<'a> {
    pub m: &'a Mod,
    pub world: Option<&'a World>,
    /// The inventions a nation holds, by name; made the first time a trigger asks.
    pub inventions: std::cell::OnceCell<Option<FxSet<&'a str>>>,
    pub is_player: bool,
}

impl<'a> Asker<'a> {
    /// `_trigger_ok`.
    pub fn trigger_ok(&self, trigger: &J, nat: &Nation) -> D<T> {
        if !matches!(trigger, J::Obj(_)) {
            return Ok(Some(true));
        }
        let mut answers = Vec::new();
        for (k, v) in conditions(trigger) {
            answers.push(self.condition_ok(k, v, nat)?);
        }
        Ok(all(&answers))
    }

    fn condition_ok(&self, key: &str, value: &J, nat: &Nation) -> D<T> {
        if key == "AND" || key == "OR" || key == "NOT" {
            if !matches!(value, J::Obj(_)) {
                return Ok(None);
            }
            let mut answers = Vec::new();
            for (k, v) in conditions(value) {
                answers.push(self.condition_ok(k, v, nat)?);
            }
            return Ok(match key {
                "OR" => any(&answers),
                "AND" => all(&answers),
                _ => all(&answers.iter().map(|a| a.map(|b| !b)).collect::<Vec<_>>()),
            });
        }
        if key == "capital_scope" {
            return self.province_ok(value, capital(nat)?);
        }
        let raw = match value {
            J::Obj(_) => return Ok(None),
            other => str_j(other),
        };
        let text = unquote(&raw);
        let m = self.m;
        match key {
            "civilized" | "war" | "exists" | "is_greater_power" | "ai" => {
                let want = text.to_lowercase() == "yes";
                let got = match key {
                    "ai" => !self.is_player,
                    "exists" => {
                        let t = text.to_lowercase();
                        if t != "yes" && t != "no" {
                            return Ok(None);
                        }
                        true
                    }
                    "war" => match self.world {
                        None => return Ok(None),
                        Some(w) => w.at_war.contains(&names::intern_str(&nat.tag)),
                    },
                    "is_greater_power" => match self.world {
                        None => return Ok(None),
                        Some(w) => w.great_powers.contains(&nat.tag),
                    },
                    _ => nat.civilized.to_lowercase() == "yes",
                };
                return Ok(Some(got == want));
            }
            "tag" => return Ok(Some(text == nat.tag)),
            "government" => return Ok(Some(text == nat.government)),
            "primary_culture" => return Ok(Some(text == names::text(nat.primary_culture))),
            "nationalvalue" => return Ok(Some(text == names::text(nat.nationalvalue))),
            "revanchism" | "badboy" | "prestige" | "war_exhaustion" | "plurality" | "money"
            | "total_pops" => {
                let have = match key {
                    "revanchism" => nat.revanchism,
                    "badboy" => nat.infamy,
                    "prestige" => nat.prestige,
                    "war_exhaustion" => nat.war_exhaustion,
                    "plurality" => nat.plurality,
                    "money" => nat.treasury,
                    _ => nat.total_pop as f64,
                };
                return Ok(Some(have >= py_float(text).unwrap_or(0.0)));
            }
            _ => {}
        }
        if key == "year" {
            return match self.world {
                Some(w) if w.year != 0 => Ok(Some(w.year >= to_int(text, 0)?)),
                _ => Ok(None),
            };
        }
        if key == "capital" {
            return Ok(Some(capital(nat)? == to_int(text, -2)?));
        }
        if key == "owns" {
            // Python compares the ledger's (owner, controller) pair with the
            // tag, which is never equal: `owns` never holds there, so it
            // never holds here.
            return match self.world {
                None => Ok(None),
                Some(_) => {
                    to_int(text, -1)?;
                    Ok(Some(false))
                }
            };
        }
        if key == "is_culture_group" {
            if m.culture_groups.is_empty() {
                return Ok(None);
            }
            return Ok(Some(m.culture_groups.get(names::text(nat.primary_culture)).map(|g| g.as_str())
                           == Some(text)));
        }
        if key == "invention" {
            return Ok(self.inventions.get_or_init(|| held_inventions(nat, self.m))
                          .as_ref().map(|held| held.contains(text)));
        }
        if key == "technology" {
            return Ok(Some(nat.tech_list.iter().any(|t| names::text(*t) == text)));
        }
        if key == "has_country_flag" {
            return Ok(Some(nat.country_flags.contains(text)));
        }
        if key == "has_country_modifier" {
            return Ok(Some(nat.modifiers.iter().any(|t| names::text(*t) == text)));
        }
        if m.reform_names.contains(key) {
            return Ok(Some(nat.reforms.iter().find(|(k, _)| names::text(**k) == key)
                           .map(|(_, v)| names::text(*v)) == Some(text)));
        }
        Ok(None)
    }

    fn province_ok(&self, trigger: &J, pid: i64) -> D<T> {
        if !matches!(trigger, J::Obj(_)) {
            return Ok(None);
        }
        let mut answers = Vec::new();
        for (k, v) in conditions(trigger) {
            answers.push(self.province_condition(k, v, pid)?);
        }
        Ok(all(&answers))
    }

    fn province_condition(&self, key: &str, value: &J, pid: i64) -> D<T> {
        if key == "AND" || key == "OR" || key == "NOT" {
            if !matches!(value, J::Obj(_)) {
                return Ok(None);
            }
            let mut answers = Vec::new();
            for (k, v) in conditions(value) {
                answers.push(self.province_condition(k, v, pid)?);
            }
            return Ok(match key {
                "OR" => any(&answers),
                "AND" => all(&answers),
                _ => all(&answers.iter().map(|a| a.map(|b| !b)).collect::<Vec<_>>()),
            });
        }
        if matches!(value, J::Obj(_)) {
            return Ok(None);
        }
        if key == "continent" {
            return Ok(match self.m.continents.get(&pid) {
                Some(w) if !w.is_empty() => Some(*w == unquote(&str_j(value))),
                _ => None,
            });
        }
        if key == "province_id" {
            // `to_int(value, -2)`: a list is a TypeError, and the default.
            return Ok(Some(match value {
                J::Str(s) => pid == to_int(s, -2)?,
                _ => pid == -2,
            }));
        }
        Ok(None)
    }
}

// ------------------------------------------------------------ the rates

/// `held_inventions`: the names a nation's indices decode to, or None.
pub fn held_inventions<'a>(nat: &Nation, m: &'a Mod) -> Option<FxSet<&'a str>> {
    let base = m.index_base?;
    let seq = &m.invention_sequence;
    let mut out = FxSet::default();
    for idx in &nat.invention_ids {
        let j = idx - base;
        if 0 <= j && (j as usize) < seq.len() {
            out.insert(seq[j as usize].name.as_str());
        }
    }
    Some(out)
}

fn subset(need: &[String], have: &FxSet<String>) -> bool {
    need.iter().all(|t| have.contains(t))
}

/// `breakdown(...)`: every contribution, as (kind, name, value).
pub fn breakdown(nat: &Nation, m: &Mod, live: Option<&FxSet<String>>, world: Option<&World>,
                 is_player: bool) -> D<Vec<(&'static str, String, f64)>> {
    let mut parts = Vec::new();
    let d = m.dense();
    for tech in &nat.tech_list {
        let v = d.tech_mob(*tech);
        if v != 0.0 {
            parts.push(("tech", names::text(*tech).to_string(), v));
        }
    }
    let inventions = std::cell::OnceCell::new();
    match m.index_base {
        Some(base) => {
            let seq = &m.invention_sequence;
            for idx in &nat.invention_ids {
                let j = idx - base;
                if 0 <= j && (j as usize) < seq.len() && seq[j as usize].size != 0.0 {
                    let e = &seq[j as usize];
                    parts.push(("invention", e.name.clone(), e.size));
                }
            }
        }
        None => {
            let techs: FxSet<String> = nat.tech_list.iter().map(|t| names::text(*t).to_string()).collect();
            for (name, rule) in m.invention_rules.iter() {
                if let Some(live) = live {
                    if !live.contains(name) {
                        continue;
                    }
                }
                if !subset(&rule.techs, &techs) {
                    continue;
                }
                if !rule.tags.is_empty() && !rule.tags.iter().any(|t| *t == nat.tag) {
                    continue;
                }
                parts.push(("invention", name.clone(), rule.size));
            }
        }
    }
    let v = d.nv_mob(nat.nationalvalue);
    if v != 0.0 {
        parts.push(("national value", names::text(nat.nationalvalue).to_string(), v));
    }
    for name in &nat.modifiers {
        let v = d.event_mob(*name);
        if v != 0.0 {
            parts.push(("event modifier", names::text(*name).to_string(), v));
        }
    }
    for (reform, option) in nat.reforms.iter() {
        let v = d.reform_mob(*reform, *option);
        if v != 0.0 {
            parts.push(("reform", format!("{} = {}", names::text(*reform), names::text(*option)), v));
        }
    }
    if nat.civilized.to_lowercase() == "no" {
        let v = m.static_mob.get("unciv_nation").copied().unwrap_or(0.0);
        if v != 0.0 {
            parts.push(("uncivilized", "unciv_nation".into(), v));
        }
    }
    let asker = Asker { m, world, inventions, is_player };
    for t in &m.triggered_mob {
        if t.size == 0.0 {
            continue;
        }
        if asker.trigger_ok(&t.trigger, nat)? == Some(true) {
            parts.push(("triggered modifier", t.name.clone(), t.size));
        }
    }
    Ok(parts)
}

/// `rate_for`: the sum, floored at zero -- `max(0.0, sum(...))`, where an
/// empty sum is the int 0 and `max` keeps the first of equals: 0.0.
pub fn rate_for(nat: &Nation, m: &Mod, live: Option<&FxSet<String>>, world: Option<&World>,
                is_player: bool) -> D<f64> {
    let parts = breakdown(nat, m, live, world, is_player)?;
    let total = py_sum(parts.iter().map(|p| p.2)).unwrap_or(0.0);
    Ok(if total > 0.0 { total } else { 0.0 })
}

/// `impact_for`.
pub fn impact_for(nat: &Nation, m: &Mod, world: Option<&World>, is_player: bool) -> D<f64> {
    let inventions = std::cell::OnceCell::new();
    let mut total = 0.0;
    let d = m.dense();
    for name in &nat.modifiers {
        total += d.modifier_impact(*name);
    }
    let asker = Asker { m, world, inventions, is_player };
    for t in &m.triggered_mob {
        if t.impact == 0.0 {
            continue;
        }
        if asker.trigger_ok(&t.trigger, nat)? == Some(true) {
            total += t.impact;
        }
    }
    Ok(total)
}

// ------------------------------------------------------------ the fleet

/// `naval_profile`: {ship: [hull, gun_power, evasion, torpedo_attack,
/// score], heavy}, in the mod's order.
pub fn naval_profile(nat: &Nation, m: &Mod) -> Vec<(String, [f64; 5], i64)> {
    let mut out: Vec<(String, [f64; 5], i64)> =
        m.naval_units.iter().map(|s| (s.name.clone(), s.stats, s.heavy)).collect();
    if out.is_empty() {
        return out;
    }
    let apply = |out: &mut Vec<(String, [f64; 5], i64)>, changes: &Changes| {
        for (who, deltas) in changes {
            let targets: Vec<usize> = if who == "navy_base" {
                (0..out.len()).collect()
            } else {
                out.iter().position(|(n, _, _)| n == who).into_iter().collect()
            };
            for i in targets {
                for (stat, delta) in deltas {
                    let key = if stat == "supply_consumption_score" { "score" } else { stat };
                    if let Some(k) = SHIP_KEYS.iter().position(|s| *s == key) {
                        out[i].1[k] += delta;
                    }
                }
            }
        }
    };
    for tech in &nat.tech_list {
        if let Some(ch) = m.dense().naval_tech(*tech) {
            apply(&mut out, ch);
        }
    }
    let held: Vec<String> = match m.index_base {
        Some(base) => {
            let seq = &m.invention_sequence;
            nat.invention_ids.iter()
                .filter(|&&i| 0 <= i - base && ((i - base) as usize) < seq.len())
                .map(|&i| seq[(i - base) as usize].name.clone())
                .collect()
        }
        None => {
            let techs: FxSet<String> = nat.tech_list.iter().map(|t| names::text(*t).to_string()).collect();
            m.naval_effects.iter()
                .filter(|(_, r)| subset(&r.techs, &techs)
                        && (r.tags.is_empty() || r.tags.iter().any(|t| *t == nat.tag)))
                .map(|(n, _)| n.clone())
                .collect()
        }
    };
    for name in &held {
        if let Some(rule) = m.naval_effects.get(name) {
            apply(&mut out, &rule.effects);
        }
    }
    let floor = |v: f64| if v > 0.0 { v } else { 0.0 };
    for (_, s, _) in out.iter_mut() {
        s[1] = floor(s[1]);
        s[0] = floor(s[0]);
        s[3] = floor(s[3]);
        let e = floor(s[2]);
        s[2] = if e < 0.95 { e } else { 0.95 };
    }
    out
}

// ------------------------------------------------------------ settling

/// `attainable_inventions(mod, all_nations)`.
pub fn attainable_inventions(m: &Mod, all: &OMap<&str, FxSet<&str>>) -> FxSet<String> {
    let rules = &m.invention_rules;
    let mut live: OMap<String, bool> = OMap::new();
    for (name, rule) in rules.iter() {
        let eligible = all.iter().any(|(tag, techs)| {
            rule.techs.iter().all(|t| techs.contains(t.as_str()))
                && (rule.tags.is_empty() || rule.tags.iter().any(|t| t == tag))
        });
        live.set(name.clone(), eligible);
    }
    for _ in 0..rules.len() + 1 {
        let mut changed = false;
        for (name, rule) in rules.iter() {
            if !*live.get(name).unwrap() {
                continue;
            }
            if rule.requires.iter().any(|r| !live.get(r).copied().unwrap_or(false)) {
                live.set(name.clone(), false);
                changed = true;
                continue;
            }
            let base = match rule.base {
                Some(b) => b,
                None => continue,
            };
            let dead: Vec<f64> = rule.blockers.iter()
                .filter(|(_, blocked)| !live.get(blocked).copied().unwrap_or(true))
                .map(|(f, _)| *f)
                .collect();
            if dead.is_empty() {
                continue;
            }
            // `base + sum(dead)`: the sum first, as Python's `sum` adds.
            let s = py_sum(dead.iter().copied()).unwrap_or(0.0);
            if base + s <= 0.0 {
                live.set(name.clone(), false);
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }
    live.iter().filter(|(_, ok)| **ok).map(|(n, _)| n.clone()).collect()
}

/// `_holdings`: each distinct (tag, technologies, ids), counted.
pub fn holdings<'a>(every: &[&'a PreNation]) -> Vec<(i64, FxSet<&'a str>, &'a str, &'a [i64])> {
    let mut seen: FxMap<(&str, &[Sym], &[i64]), i64> = FxMap::default();
    for pn in every {
        *seen.entry((pn.nat.tag.as_str(), pn.nat.tech_list.as_slice(),
                     pn.nat.invention_ids.as_slice())).or_insert(0) += 1;
    }
    // The totals are sums of counts, so the order they are met in is no
    // matter: a hash map where Python kept a dict.
    seen.into_iter().map(|((tag, techs, ids), count)| {
        (count, techs.iter().map(|t| names::text(*t)).collect(), tag, ids)
    }).collect()
}

/// `_violations`: (bad, total).
pub fn violations(m: &Mod, holdings: &[(i64, FxSet<&str>, &str, &[i64])], base: i64) -> (i64, i64) {
    let seq = &m.invention_sequence;
    let (mut bad, mut total) = (0i64, 0i64);
    for (count, techs, tag, ids) in holdings {
        for idx in ids.iter() {
            total += count;
            let j = idx - base;
            if j < 0 || j as usize >= seq.len() {
                bad += count;
                continue;
            }
            let rule = &seq[j as usize];
            if !rule.techs.iter().all(|t| techs.contains(t.as_str()))
                || (!rule.tags.is_empty() && !rule.tags.iter().any(|t| t == tag)) {
                bad += count;
            }
        }
    }
    (bad, total)
}

/// `index_base_for`.
pub fn index_base_for(m: &Mod, every: &[&PreNation]) -> Option<i64> {
    let h = holdings(every);
    let (mut best, mut best_rate) = (None, 1.0f64);
    for base in [1i64, 0] {
        let (bad, total) = violations(m, &h, base);
        if total == 0 {
            return None;
        }
        let rate = bad as f64 / total as f64;
        if rate < best_rate {
            best = Some(base);
            best_rate = rate;
        }
    }
    if best_rate <= 0.05 { best } else { None }
}

/// `settle_campaign`: the live inventions; the base is written onto `m`.
pub fn settle_campaign(m: &mut Mod, saves: &[&[PreNation]]) -> FxSet<String> {
    let mut all_techs: OMap<&str, FxSet<&str>> = OMap::new();
    let mut every: Vec<&PreNation> = Vec::new();
    for nations in saves {
        for pn in nations.iter() {
            every.push(pn);
            all_techs.entry(pn.tag.as_str(), FxSet::default)
                .extend(pn.nat.tech_list.iter().map(|t| names::text(*t)));
        }
    }
    let live = attainable_inventions(m, &all_techs);
    m.index_base = index_base_for(m, &every);
    live
}

#[cfg(test)]
mod tests {
    use super::Decline;

    #[test]
    fn a_raised_decline_is_said_as_its_sentence() {
        let d = Decline::Raised("No mod was named.".into());
        assert_eq!(d.raised(), Some("No mod was named."));
        assert_eq!(d.text(), "No mod was named.");
    }

    #[test]
    fn an_unreadable_decline_is_never_said_as_a_refusal() {
        let d = Decline::Unreadable("int() of infinity in a trigger".into());
        assert_eq!(d.raised(), None);
        assert_eq!(d.text(), "int() of infinity in a trigger");
    }
}

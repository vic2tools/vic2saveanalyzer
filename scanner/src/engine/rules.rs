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

use crate::jsonr::J;
use crate::engine::model::{Meta, Nation};
use crate::omap::OMap;
use crate::pickle::{FxMap, FxSet};
use crate::pyfmt::{py_float, py_sum, trunc_int};

/// Something Python would have raised over, which the engine does not copy:
/// the run is handed back to Python, which does what it always did.
#[derive(Debug)]
pub struct Decline(pub String);

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
}

fn strings(v: &J) -> Vec<String> {
    v.list().iter().map(|x| x.str().to_string()).collect()
}

fn floats(v: &J) -> FxMap<String, f64> {
    v.pairs().iter().map(|(k, x)| (k.clone(), x.float())).collect()
}

fn texts(v: &J) -> FxMap<String, String> {
    v.pairs().iter().map(|(k, x)| (k.clone(), x.str().to_string())).collect()
}

fn changes(v: &J) -> Changes {
    v.pairs().iter().map(|(who, deltas)| {
        (who.clone(), deltas.pairs().iter().map(|(k, x)| (k.clone(), x.float())).collect())
    }).collect()
}

impl Mod {
    pub fn from_json(j: &J) -> D<Mod> {
        let bad = |what: &str| Decline(format!("the mod export has no {}", what));
        if !matches!(j, J::Obj(_)) {
            return Err(bad("object"));
        }
        let invention_sequence = j.at("invention_sequence").list().iter().map(|e| {
            let e = e.list();
            Invention { name: e[0].str().to_string(), size: e[1].float(),
                        techs: strings(&e[2]), tags: strings(&e[3]) }
        }).collect();
        let mut formations: FxMap<String, FxSet<String>> = FxMap::default();
        for (tag, v) in j.at("formations").pairs() {
            formations.insert(tag.clone(), strings(v).into_iter().collect());
        }
        let pid_pairs = |key: &str| -> OMap<i64, String> {
            j.at(key).list().iter().map(|p| {
                let p = p.list();
                (p[0].int(), p[1].str().to_string())
            }).collect()
        };
        let naval_units = j.at("naval_units").pairs().iter().map(|(name, st)| {
            let mut stats = [0.0; 5];
            for (i, k) in SHIP_KEYS.iter().enumerate() {
                stats[i] = st.at(k).float();
            }
            Ship { name: name.clone(), stats, heavy: st.at("heavy").int() }
        }).collect();
        let naval_effects = j.at("naval_effects").pairs().iter().map(|(name, e)| {
            (name.clone(), NavalEffect { effects: changes(e.at("effects")),
                                         techs: strings(e.at("techs")),
                                         tags: strings(e.at("tags")) })
        }).collect();
        let naval_tech_effects = j.at("naval_tech_effects").pairs().iter()
            .map(|(name, e)| (name.clone(), changes(e))).collect();
        let reform_mob = j.at("reform_mob").list().iter().map(|r| {
            let r = r.list();
            ((r[0].str().to_string(), r[1].str().to_string()), r[2].float())
        }).collect();
        let triggered_mob = j.at("triggered_mob").list().iter().map(|t| {
            let t = t.list();
            Triggered { name: t[0].str().to_string(), size: t[1].float(), impact: t[2].float(),
                        trigger: t[3].clone() }
        }).collect();
        let invention_rules = j.at("invention_rules").pairs().iter().map(|(name, r)| {
            (name.clone(), Rule {
                size: r.at("size").float(),
                techs: strings(r.at("techs")),
                tags: strings(r.at("tags")),
                requires: strings(r.at("requires")),
                base: if r.at("base").is_null() { None } else { Some(r.at("base").float()) },
                blockers: r.at("blockers").list().iter()
                    .map(|b| (b.list()[0].float(), b.list()[1].str().to_string())).collect(),
            })
        }).collect();
        let flag_styles = j.at("flag_styles").pairs().iter().map(|(g, v)| {
            (g.clone(), (v.list()[0].str().to_string(), v.list()[1].truthy()))
        }).collect();
        let m = Mod {
            path: j.at("path").str().to_string(),
            invention_sequence,
            party_policies: strings(j.at("party_policies")),
            localisation: texts(j.at("localisation")),
            base_prices: j.at("base_prices").clone(),
            country_order: strings(j.at("country_order")),
            formations,
            culture_names: j.at("culture_names").clone(),
            display_names: j.at("display_names").clone(),
            province_names: pid_pairs("province_names"),
            province_regions: pid_pairs("province_regions"),
            state_names: j.at("state_names").pairs().iter()
                .map(|(k, v)| (k.clone(), v.str().to_string())).collect(),
            state_names_j: j.at("state_names").clone(),
            unit_kinds: texts(j.at("unit_kinds")),
            naval_units,
            naval_effects,
            naval_tech_effects,
            technology: j.at("technology").clone(),
            mob_impacts: floats(j.at("mob_impacts")),
            modifier_impacts: floats(j.at("modifier_impacts")),
            reform_mob,
            reform_names: strings(j.at("reform_names")).into_iter().collect(),
            static_mob: floats(j.at("static_mob")),
            triggered_mob,
            culture_groups: texts(j.at("culture_groups")),
            continents: pid_pairs("continents").into_iter_pairs().collect(),
            defines: floats(j.at("defines")),
            strata: texts(j.at("strata")),
            invention_rules,
            event_mob: floats(j.at("event_mob")),
            tech_mob: floats(j.at("tech_mob")),
            nv_mob: floats(j.at("nv_mob")),
            tech_count: j.at("tech_count").int(),
            colours: texts(j.at("colours")),
            sea: j.at("sea").list().iter().map(|x| x.int()).collect(),
            positions: j.at("positions").list().iter().map(|p| {
                let p = p.list();
                (p[0].int(), p[1].float(), p[2].float())
            }).collect(),
            flag_styles,
            flag_roots: strings(j.at("flag_roots")),
            map_bmp: j.at("map_bmp").str().to_string(),
            map_csv: j.at("map_csv").str().to_string(),
            index_base: None,
        };
        for t in &m.triggered_mob {
            refuse_unjudgeable(&t.trigger)?;
        }
        Ok(m)
    }

    pub fn define(&self, key: &str) -> Option<f64> {
        self.defines.get(key).copied()
    }
}

/// A trigger whose condition holds a list where one value belongs -- a
/// repeated key whose values are themselves lists -- is one Python would
/// judge by the repr of that list. No mod writes one; the engine hands such
/// a run back rather than guess at the repr.
fn refuse_unjudgeable(trigger: &J) -> D<()> {
    if let J::Obj(pairs) = trigger {
        for (key, value) in pairs {
            if key.starts_with('_') {
                continue;
            }
            let parts: Vec<&J> = match value {
                J::List(v) => v.iter().collect(),
                one => vec![one],
            };
            for p in parts {
                match p {
                    J::List(_) => return Err(Decline(format!(
                        "a triggered modifier's condition `{}` holds a list", key))),
                    J::Obj(_) => refuse_unjudgeable(p)?,
                    _ => {}
                }
            }
        }
    }
    Ok(())
}

// ------------------------------------------------------------- triggers

/// What one save says about everybody (`save_world`).
pub struct World {
    pub year: i64,
    pub great_powers: FxSet<String>,
    pub at_war: FxSet<String>,
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
            at_war.extend(war.fighting.iter().cloned());
        } else {
            at_war.extend(war.attackers.iter().cloned());
            at_war.extend(war.defenders.iter().cloned());
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
    crate::text::unquote(s)
}

/// `to_int(text, default)`: `int(float(text))`, its ValueError the default
/// (`int(nan)` is one). Infinity is an OverflowError, which Python let out.
fn to_int(text: &str, default: i64) -> D<i64> {
    match py_float(text) {
        None => Ok(default),
        Some(f) if f.is_nan() => Ok(default),
        Some(f) => trunc_int(f).ok_or_else(|| Decline("int() of infinity in a trigger".into())),
    }
}

/// `to_int(nat.get("capital"), -1)`: the capital is a string of the save's.
fn capital(nat: &Nation) -> D<i64> {
    to_int(&nat.capital, -1)
}

pub struct Asker<'a> {
    pub m: &'a Mod,
    pub world: Option<&'a World>,
    pub inventions: Option<&'a FxSet<String>>,
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
            J::Str(s) => s.as_str(),
            // Refused at load (`refuse_unjudgeable`).
            _ => return Ok(None),
        };
        let text = unquote(raw);
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
                        Some(w) => w.at_war.contains(&nat.tag),
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
            "primary_culture" => return Ok(Some(text == nat.primary_culture)),
            "nationalvalue" => return Ok(Some(text == nat.nationalvalue)),
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
            return Ok(Some(m.culture_groups.get(&nat.primary_culture).map(|g| g.as_str())
                           == Some(text)));
        }
        if key == "invention" {
            return Ok(self.inventions.map(|held| held.contains(text)));
        }
        if key == "technology" {
            return Ok(Some(nat.tech_list.iter().any(|t| t == text)));
        }
        if key == "has_country_flag" {
            return Ok(Some(nat.country_flags.contains(text)));
        }
        if key == "has_country_modifier" {
            return Ok(Some(nat.modifiers.iter().any(|t| t == text)));
        }
        if m.reform_names.contains(key) {
            return Ok(Some(nat.reforms.get(key).map(|s| s.as_str()) == Some(text)));
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
        let raw = match value {
            J::Str(s) => s.as_str(),
            _ => return Ok(None),
        };
        if key == "continent" {
            return Ok(match self.m.continents.get(&pid) {
                Some(w) if !w.is_empty() => Some(w == unquote(raw)),
                _ => None,
            });
        }
        if key == "province_id" {
            return Ok(Some(pid == to_int(raw, -2)?));
        }
        Ok(None)
    }
}

// ------------------------------------------------------------ the rates

/// `held_inventions`: the names a nation's indices decode to, or None.
pub fn held_inventions(nat: &Nation, m: &Mod) -> Option<FxSet<String>> {
    let base = m.index_base?;
    let seq = &m.invention_sequence;
    let mut out = FxSet::default();
    for idx in &nat.invention_ids {
        let j = idx - base;
        if 0 <= j && (j as usize) < seq.len() {
            out.insert(seq[j as usize].name.clone());
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
    for tech in &nat.tech_list {
        let v = m.tech_mob.get(tech).copied().unwrap_or(0.0);
        if v != 0.0 {
            parts.push(("tech", tech.clone(), v));
        }
    }
    let inventions = held_inventions(nat, m);
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
            let techs: FxSet<String> = nat.tech_list.iter().cloned().collect();
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
    let v = m.nv_mob.get(&nat.nationalvalue).copied().unwrap_or(0.0);
    if v != 0.0 {
        parts.push(("national value", nat.nationalvalue.clone(), v));
    }
    for name in &nat.modifiers {
        let v = m.event_mob.get(name).copied().unwrap_or(0.0);
        if v != 0.0 {
            parts.push(("event modifier", name.clone(), v));
        }
    }
    for (reform, option) in nat.reforms.iter() {
        let v = m.reform_mob.get(&(reform.clone(), option.clone())).copied().unwrap_or(0.0);
        if v != 0.0 {
            parts.push(("reform", format!("{} = {}", reform, option), v));
        }
    }
    if nat.civilized.to_lowercase() == "no" {
        let v = m.static_mob.get("unciv_nation").copied().unwrap_or(0.0);
        if v != 0.0 {
            parts.push(("uncivilized", "unciv_nation".into(), v));
        }
    }
    let asker = Asker { m, world, inventions: inventions.as_ref(), is_player };
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
    let inventions = held_inventions(nat, m);
    let mut total = 0.0;
    for name in &nat.modifiers {
        total += m.modifier_impacts.get(name).copied().unwrap_or(0.0);
    }
    let asker = Asker { m, world, inventions: inventions.as_ref(), is_player };
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
        if let Some(ch) = m.naval_tech_effects.get(tech) {
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
            let techs: FxSet<String> = nat.tech_list.iter().cloned().collect();
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

/// One nation of one save, as the invention pass keeps it.
pub struct Held {
    pub tag: String,
    pub record_tag: String,
    pub tech_list: Vec<String>,
    pub invention_ids: Vec<i64>,
}

/// `attainable_inventions(mod, all_nations)`.
pub fn attainable_inventions(m: &Mod, all: &OMap<String, FxSet<String>>) -> FxSet<String> {
    let rules = &m.invention_rules;
    let mut live: OMap<String, bool> = OMap::new();
    for (name, rule) in rules.iter() {
        let eligible = all.iter().any(|(tag, techs)| {
            subset(&rule.techs, techs) && (rule.tags.is_empty() || rule.tags.contains(tag))
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
pub fn holdings(every: &[&Held]) -> Vec<(i64, FxSet<String>, String, Vec<i64>)> {
    let mut seen: OMap<(String, Vec<String>, Vec<i64>), i64> = OMap::new();
    for nat in every {
        let key = (nat.record_tag.clone(), nat.tech_list.clone(), nat.invention_ids.clone());
        *seen.entry(key, || 0) += 1;
    }
    seen.into_iter_pairs().map(|((tag, techs, ids), count)| {
        (count, techs.into_iter().collect(), tag, ids)
    }).collect()
}

/// `_violations`: (bad, total).
pub fn violations(m: &Mod, holdings: &[(i64, FxSet<String>, String, Vec<i64>)], base: i64) -> (i64, i64) {
    let seq = &m.invention_sequence;
    let (mut bad, mut total) = (0i64, 0i64);
    for (count, techs, tag, ids) in holdings {
        for idx in ids {
            total += count;
            let j = idx - base;
            if j < 0 || j as usize >= seq.len() {
                bad += count;
                continue;
            }
            let rule = &seq[j as usize];
            if !subset(&rule.techs, techs) || (!rule.tags.is_empty() && !rule.tags.contains(tag)) {
                bad += count;
            }
        }
    }
    (bad, total)
}

/// `index_base_for`.
pub fn index_base_for(m: &Mod, every: &[&Held]) -> Option<i64> {
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
pub fn settle_campaign(m: &mut Mod, saves: &[Vec<Held>]) -> FxSet<String> {
    let mut all_techs: OMap<String, FxSet<String>> = OMap::new();
    let mut every: Vec<&Held> = Vec::new();
    for nations in saves {
        for nat in nations {
            every.push(nat);
            all_techs.entry(nat.tag.clone(), FxSet::default).extend(nat.tech_list.iter().cloned());
        }
    }
    let live = attainable_inventions(m, &all_techs);
    m.index_base = index_base_for(m, &every);
    live
}

// What a nation comes to once its save is read, and what one save puts into
// the tables: `finishing.py`, `spending.py` and `state_history.py`.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Python finished a save in one go, in the worker that read it, once the
// campaign's inventions had been settled -- which needed every save read
// once already. Here a save is read once: everything that does not depend on
// the settled inventions is worked out as it is read (`prepare`: who is
// kept, who is playing, the mobilisation buckets, the brigade cap, the state
// snapshot), the big per-province tables are dropped, and what depends on
// the inventions -- the mobilisation size and everything counted from it,
// the cap, the ships -- is finished after (`finish`).

use crate::deflate;
use crate::country::{Ship, Stack};
use crate::engine::model::{Meta, Nation};
use crate::names::{self, Sym};
use crate::omap::OMap;
use crate::fx::{FxMap, FxSet};
use crate::pyfmt::{floordiv, push_csv_field, push_float, push_int, push_json_float,
                   push_json_str, round, trunc_int, Num};
use crate::engine::rules::{impact_for, naval_profile, rate_for, save_world, Mod, World, D};

/// `finishing.Finish`, and the few things of the run the tables need.
/// Its `rate` is not here: it is the rate a run with no mod uses, and the
/// engine is handed only runs with one.
pub struct Spec {
    pub pop_per_regiment: i64,
    pub mob_types: FxSet<Sym>,
    pub include_occupied: bool,
    pub player_nations: Option<Vec<String>>,
    pub wanted: Option<FxSet<String>>,
    pub min_pop: i64,
    /// The mod's regions (`ModHead.province_regions`), for the snapshots.
    pub regions: FxMap<i64, String>,
    /// The mod's defines (`ModHead.defines`), for the brigade cap.
    pub defines: FxMap<String, f64>,
    /// tech -> (branch, line), `tech_groups.TECH_GROUP`.
    pub tech_group: FxMap<String, (String, String)>,
    /// The main table's columns, `spending.nation_columns(pop_columns)`.
    pub columns: Vec<String>,
    /// `readsave.STRATA`: the vanilla pop types of each stratum.
    pub strata: Vec<(String, Vec<String>)>,
}

impl Spec {
    /// `kept_by`: whether this run measures this nation.
    pub fn keeps(&self, tag: &str, nat: &Nation) -> bool {
        let wanted = match &self.wanted {
            Some(w) if !w.is_empty() => w.contains(tag),
            _ => true,
        };
        wanted && nat.total_pop >= self.min_pop
    }
}

/// One nation of a save, read and prepared.
pub struct PreNation {
    /// The key the save's dict holds it under.
    pub tag: String,
    pub nat: Nation,
    pub kept: bool,
    pub is_player: bool,
    /// Sizes of the mobilizable pops, in save order (`mobilization_clusters`).
    pub buckets: Vec<i64>,
    pub pool: i64,
    pub entries: i64,
    pub cap_rule: i64,
}

/// One save, read and prepared.
pub struct Pre {
    pub meta: Meta,
    pub nations: Vec<PreNation>,
    /// The state snapshot, packed as the page carries it.
    pub chunk: String,
}

/// `players_in(meta, nations, told)`.
fn players(meta: &Meta, nations: &[(String, Nation)], told: &Option<Vec<String>>) -> FxSet<String> {
    if let Some(t) = told {
        return t.iter().cloned().collect();
    }
    let played: FxSet<String> = nations.iter().filter(|(_, n)| n.human)
        .map(|(t, _)| t.clone()).collect();
    if !played.is_empty() {
        return played;
    }
    let mut out = FxSet::default();
    if !meta.player.is_empty() {
        out.insert(meta.player.clone());
    }
    out
}

/// `define or default`, as `float(defines.get(k) or d)`.
fn define_or(defines: &FxMap<String, f64>, key: &str, default: f64) -> f64 {
    match defines.get(key) {
        Some(v) if *v != 0.0 => *v,
        _ => default,
    }
}

/// `finishing.brigade_cap`.
fn brigade_cap(nat: &Nation, defines: &FxMap<String, f64>, ppr: i64) -> i64 {
    let floor = match defines.get("POP_MIN_SIZE_FOR_REGIMENT") {
        Some(v) if *v != 0.0 => trunc_int(*v).unwrap_or(0),
        _ => 1000,
    };
    let colony = define_or(defines, "POP_MIN_SIZE_FOR_REGIMENT_COLONY_MULTIPLIER", 1.0);
    let noncore = define_or(defines, "POP_MIN_SIZE_FOR_REGIMENT_NONCORE_MULTIPLIER", 1.0);
    let protect = define_or(defines, "POP_MIN_SIZE_FOR_REGIMENT_PROTECTORATE_MULTIPLIER", 1.0);
    let mut total = 0i64;
    for (pid, sizes) in &nat.soldier_pops_at {
        let own = nat.province_colonial.get(pid).copied().unwrap_or(0);
        let level = if own != 0 {
            own
        } else if nat.colonial_provinces.contains(pid) {
            nat.colonial_level.get(pid).copied().unwrap_or(2)
        } else {
            0
        };
        let mult = if level != 0 {
            if level == 1 { protect } else { colony }
        } else if !nat.core_provinces.contains(pid) {
            noncore
        } else {
            1.0
        };
        let step = ppr as f64 * mult;
        for &size in sizes {
            if size >= floor {
                total += 1 + trunc_int(floordiv(size as f64, step)).unwrap_or(0);
            }
        }
    }
    total
}

// --------------------------------------------------------- the snapshots

/// `state_history.Snapshot`.
#[derive(Default)]
pub struct Snapshot {
    words: OMap<Sym, usize>,
    layouts: OMap<(Vec<usize>, Vec<usize>), usize>,
    nations: Vec<(String, String)>,
}

impl Snapshot {
    fn word(&mut self, value: Sym) -> usize {
        let n = self.words.len();
        *self.words.entry(value, || n)
    }

    fn add(&mut self, tag: &str, nat: &Nation, regions: &FxMap<i64, String>) {
        let mut rows = String::from("[");
        for (i, g) in nat.population_by_state.iter().enumerate() {
            let region = match regions.get(&g.group) {
                Some(r) if !r.is_empty() => names::intern_str(r),
                _ => names::intern_str(&format!("province:{}", g.group)),
            };
            let types: Vec<usize> = g.types.iter().map(|(t, _)| self.word(*t)).collect();
            let cultures: Vec<usize> = g.cultures.iter()
                .map(|(c, _)| 2 * self.word(*c) + nat.accepts(*c) as usize).collect();
            let n = self.layouts.len();
            let index = *self.layouts.entry((types, cultures), || n);
            let region_word = self.word(region);
            if i > 0 {
                rows.push(',');
            }
            rows.push('[');
            push_int(&mut rows, region_word as i64);
            rows.push(',');
            push_int(&mut rows, g.size);
            rows.push(',');
            if g.size != 0 {
                push_json_float(&mut rows, round(g.literate / g.size as f64, 6));
            } else {
                rows.push_str("null");
            }
            rows.push(',');
            push_int(&mut rows, g.provinces);
            rows.push(',');
            push_int(&mut rows, index as i64);
            rows.push_str(",[");
            for (k, (_, c)) in g.types.iter().chain(g.cultures.iter()).enumerate() {
                if k > 0 {
                    rows.push(',');
                }
                push_int(&mut rows, *c);
            }
            rows.push_str("]]");
        }
        rows.push(']');
        match self.nations.iter_mut().find(|(t, _)| t == tag) {
            Some(slot) => slot.1 = rows,
            None => self.nations.push((tag.to_string(), rows)),
        }
    }

    /// `pack()`: JSON, `<`/`>` turned into look-alikes, gzipped, base64. Level
    /// 5, not the 6 the Python used: 45% quicker for 0.8% more bytes, and the
    /// chunk is most of what a worker does outside reading (INTERNALS.md).
    pub fn pack(&self) -> String {
        let mut raw = String::from("[[");
        for (i, w) in self.words.keys().enumerate() {
            if i > 0 {
                raw.push(',');
            }
            push_json_str(&mut raw, names::text(*w));
        }
        raw.push_str("],[");
        for (i, (types, cultures)) in self.layouts.keys().enumerate() {
            if i > 0 {
                raw.push(',');
            }
            raw.push_str("[[");
            for (k, t) in types.iter().enumerate() {
                if k > 0 {
                    raw.push(',');
                }
                push_int(&mut raw, *t as i64);
            }
            raw.push_str("],[");
            for (k, c) in cultures.iter().enumerate() {
                if k > 0 {
                    raw.push(',');
                }
                push_int(&mut raw, *c as i64);
            }
            raw.push_str("]]");
        }
        raw.push_str("],{");
        for (i, (tag, rows)) in self.nations.iter().enumerate() {
            if i > 0 {
                raw.push(',');
            }
            push_json_str(&mut raw, tag);
            raw.push(':');
            raw.push_str(rows);
        }
        raw.push_str("}]");
        let raw = escape_angles(&raw);
        deflate::base64(&deflate::gzip_level(raw.as_bytes(), &deflate::LEVEL5))
    }
}

/// The payload's name escaping: every `<` and `>` a look-alike.
pub fn escape_angles(s: &str) -> String {
    if !s.contains(['<', '>']) {
        return s.to_string();
    }
    s.replace('<', "\\u2039").replace('>', "\\u203a")
}

// ------------------------------------------------------------- pass one

/// Everything about one save that does not wait for the inventions.
pub fn prepare(meta: Meta, nations: Vec<Nation>, keys: Vec<String>, spec: &Spec) -> Pre {
    let pairs: Vec<(String, Nation)> = keys.into_iter().zip(nations).collect();
    let playing = players(&meta, &pairs, &spec.player_nations);
    let mut snapshot = Snapshot::default();
    let mut out = Vec::with_capacity(pairs.len());
    for (tag, mut nat) in pairs {
        let kept = spec.keeps(&tag, &nat);
        let mut pre = PreNation { tag: tag.clone(), nat: Nation::default(), kept,
                                  is_player: false, buckets: Vec::new(), pool: 0, entries: 0,
                                  cap_rule: 0 };
        if kept {
            pre.is_player = playing.contains(&tag);
            // `mobilization_clusters`.
            for (poptype, culture, size, pid) in &nat.mobilizable_pops {
                if !spec.mob_types.contains(poptype) || !nat.accepts(*culture) {
                    continue;
                }
                if nat.colonial_provinces.contains(pid)
                    || (!spec.include_occupied && nat.occupied_provinces.contains(pid)) {
                    continue;
                }
                pre.pool += size;
                pre.buckets.push(*size);
            }
            pre.entries = pre.buckets.len() as i64;
            pre.cap_rule = brigade_cap(&nat, &spec.defines, spec.pop_per_regiment);
            snapshot.add(&tag, &nat, &spec.regions);
        }
        // What finishing spends, let go now rather than carried.
        nat.mobilizable_pops = Vec::new();
        nat.population_by_state = Vec::new();
        nat.soldier_pops_at = Vec::new();
        nat.colonial_level = FxMap::default();
        nat.province_colonial = FxMap::default();
        nat.core_provinces = FxSet::default();
        nat.occupied_provinces = FxSet::default();
        nat.colonial_provinces = FxSet::default();
        pre.nat = nat;
        out.push(pre);
    }
    Pre { meta, nations: out, chunk: snapshot.pack() }
}

// ------------------------------------------------------------- pass two

/// A value of a row, as the tables print it.
#[derive(Clone, Copy)]
pub enum Val<'a> {
    S(&'a str),
    I(i64),
    F(f64),
    N(Num),
    B(bool),
}

impl Val<'_> {
    pub fn push_csv(&self, out: &mut String) {
        match self {
            Val::S(s) => push_csv_field(out, s),
            Val::I(i) => push_int(out, *i),
            Val::F(f) => push_float(out, *f),
            Val::N(n) => n.push_repr(out),
            Val::B(b) => out.push_str(if *b { "True" } else { "False" }),
        }
    }

    /// `float(val)`.
    pub fn float(&self) -> Option<f64> {
        match self {
            Val::S(s) => crate::pyfmt::py_float(s),
            Val::I(i) => Some(*i as f64),
            Val::F(f) => Some(*f),
            Val::N(n) => Some(n.as_f64()),
            Val::B(b) => Some(*b as i64 as f64),
        }
    }

    /// Python's truth of the value, for `row.get(k) or 0`.
    pub fn truthy(&self) -> bool {
        match self {
            Val::S(s) => !s.is_empty(),
            Val::I(i) => *i != 0,
            Val::F(f) => *f != 0.0,
            Val::N(n) => n.truthy(),
            Val::B(b) => *b,
        }
    }
}


/// A finished nation's row of the main table: `spending.save_rows`'s dict.
pub struct Row {
    /// The key the save's dict holds the nation under.
    pub key: String,
    pub date: String,
    pub year: String,
    pub is_player: bool,
    pub facts: RowFacts,
    pub accepted_pop: i64,
    pub accepted_pct: f64,
    pub primary_culture_pop: i64,
    pub avg_literacy: f64,
    pub avg_literacy_stated: f64,
    pub avg_consciousness: f64,
    pub avg_militancy: f64,
    pub brigade_cap: i64,
    pub mobilisation_size: f64,
    pub mobilization_pool: i64,
    pub mobilization_pops: i64,
    pub mobilization_brigades: i64,
    pub mobilization_cap: i64,
    pub mobilization_available: i64,
    pub mobilization_remaining: i64,
    pub war_policy: String,
    pub pop_poor: i64,
    pub pop_middle: i64,
    pub pop_rich: i64,
    pub soldiers_noncolonial_pct: f64,
    pub life_unmet_pct: f64,
    pub starving_pct: f64,
    pub accepted_cultures: String,
}

/// What `Row::get` reads of a finished nation, and nothing else: the rest of
/// the `Nation` is let go when the row is made.
pub struct RowFacts {
    pub tag: String,
    pub primary_culture: Sym,
    pub civilized: String,
    pub provinces: i64,
    pub states: i64,
    pub total_pop: i64,
    pub pop_noncolonial: i64,
    pub brigades: i64,
    pub regular_brigades: i64,
    pub mobilized_brigades: i64,
    pub mobilizing: i64,
    pub is_mobilized: i64,
    pub armies: i64,
    pub ships: i64,
    pub navies: i64,
    pub factory_count: i64,
    pub factory_levels: i64,
    pub ports: i64,
    pub naval_base_levels: Num,
    pub max_naval_base: Num,
    pub railroad_levels: Num,
    pub fort_levels: Num,
    pub techs: i64,
    pub army_techs: i64,
    pub navy_techs: i64,
    pub prestige: f64,
    pub infamy: f64,
    pub treasury: f64,
    pub tax_base: f64,
    pub research_points: f64,
    pub war_exhaustion: f64,
    pub plurality: f64,
    pub soldiers_noncolonial: i64,
    pub life_unmet: i64,
    pub starving: i64,
    pub pop_by_type: OMap<Sym, i64>,
}

impl RowFacts {
    /// The facts, moved (or copied, for the scalars) out of `nat`.
    fn take(nat: &mut Nation) -> RowFacts {
        RowFacts {
            tag: std::mem::take(&mut nat.tag),
            primary_culture: nat.primary_culture,
            civilized: std::mem::take(&mut nat.civilized),
            provinces: nat.provinces,
            states: nat.states,
            total_pop: nat.total_pop,
            pop_noncolonial: nat.pop_noncolonial,
            brigades: nat.brigades,
            regular_brigades: nat.regular_brigades,
            mobilized_brigades: nat.mobilized_brigades,
            mobilizing: nat.mobilizing,
            is_mobilized: nat.is_mobilized,
            armies: nat.armies,
            ships: nat.ships,
            navies: nat.navies,
            factory_count: nat.factory_count,
            factory_levels: nat.factory_levels,
            ports: nat.ports,
            naval_base_levels: nat.naval_base_levels,
            max_naval_base: nat.max_naval_base,
            railroad_levels: nat.railroad_levels,
            fort_levels: nat.fort_levels,
            techs: nat.techs,
            army_techs: nat.army_techs,
            navy_techs: nat.navy_techs,
            prestige: nat.prestige,
            infamy: nat.infamy,
            treasury: nat.treasury,
            tax_base: nat.tax_base,
            research_points: nat.research_points,
            war_exhaustion: nat.war_exhaustion,
            plurality: nat.plurality,
            soldiers_noncolonial: nat.soldiers_noncolonial,
            life_unmet: nat.life_unmet,
            starving: nat.starving,
            pop_by_type: std::mem::take(&mut nat.pop_by_type),
        }
    }
}

impl Row {
    /// `row[col]`, for a column of `spending.BASE_COLUMNS` or a `pop_<type>`.
    pub fn get(&self, col: &str) -> Val<'_> {
        let n = &self.facts;
        match col {
            "date" => Val::S(&self.date),
            "year" => Val::S(&self.year),
            "tag" => Val::S(&n.tag),
            "is_player" => Val::B(self.is_player),
            "primary_culture" => Val::S(names::text(n.primary_culture)),
            "civilized" => Val::S(&n.civilized),
            "provinces" => Val::I(n.provinces),
            "states" => Val::I(n.states),
            "total_pop" => Val::I(n.total_pop),
            "accepted_pop" => Val::I(self.accepted_pop),
            "accepted_pct" => Val::F(self.accepted_pct),
            "primary_culture_pop" => Val::I(self.primary_culture_pop),
            "avg_literacy" => Val::F(self.avg_literacy),
            "avg_literacy_stated" => Val::F(self.avg_literacy_stated),
            "pop_noncolonial" => Val::I(n.pop_noncolonial),
            "avg_consciousness" => Val::F(self.avg_consciousness),
            "avg_militancy" => Val::F(self.avg_militancy),
            "brigades" => Val::I(n.brigades),
            "regular_brigades" => Val::I(n.regular_brigades),
            "mobilized_brigades" => Val::I(n.mobilized_brigades),
            "mobilizing" => Val::I(n.mobilizing),
            "brigade_cap" => Val::I(self.brigade_cap),
            "is_mobilized" => Val::I(n.is_mobilized),
            "armies" => Val::I(n.armies),
            "ships" => Val::I(n.ships),
            "navies" => Val::I(n.navies),
            "factory_count" => Val::I(n.factory_count),
            "factory_levels" => Val::I(n.factory_levels),
            "ports" => Val::I(n.ports),
            "naval_base_levels" => Val::N(n.naval_base_levels),
            "max_naval_base" => Val::N(n.max_naval_base),
            "railroad_levels" => Val::N(n.railroad_levels),
            "fort_levels" => Val::N(n.fort_levels),
            "mobilisation_size" => Val::F(self.mobilisation_size),
            "mobilization_pool" => Val::I(self.mobilization_pool),
            "mobilization_pops" => Val::I(self.mobilization_pops),
            "mobilization_brigades" => Val::I(self.mobilization_brigades),
            "mobilization_cap" => Val::I(self.mobilization_cap),
            "mobilization_available" => Val::I(self.mobilization_available),
            "mobilization_remaining" => Val::I(self.mobilization_remaining),
            "war_policy" => Val::S(&self.war_policy),
            "techs" => Val::I(n.techs),
            "army_techs" => Val::I(n.army_techs),
            "navy_techs" => Val::I(n.navy_techs),
            "prestige" => Val::F(n.prestige),
            "infamy" => Val::F(n.infamy),
            "treasury" => Val::F(n.treasury),
            "tax_base" => Val::F(n.tax_base),
            "research_points" => Val::F(n.research_points),
            "war_exhaustion" => Val::F(n.war_exhaustion),
            "plurality" => Val::F(n.plurality),
            "pop_poor" => Val::I(self.pop_poor),
            "pop_middle" => Val::I(self.pop_middle),
            "pop_rich" => Val::I(self.pop_rich),
            "soldiers_noncolonial" => Val::I(n.soldiers_noncolonial),
            "soldiers_noncolonial_pct" => Val::F(self.soldiers_noncolonial_pct),
            "life_unmet" => Val::I(n.life_unmet),
            "life_unmet_pct" => Val::F(self.life_unmet_pct),
            "starving" => Val::I(n.starving),
            "starving_pct" => Val::F(self.starving_pct),
            "accepted_cultures" => Val::S(&self.accepted_cultures),
            _ => match col.strip_prefix("pop_") {
                Some(t) => Val::I(n.pop_by_type.get(&names::intern_str(t)).copied().unwrap_or(0)),
                None => Val::S(""),
            },
        }
    }
}

/// One save's share of the payload's per-nation tables (`PerNation`).
#[derive(Default)]
pub struct PerNation {
    pub ships: Vec<(String, Vec<(Sym, i64)>)>,
    pub crews: Vec<(String, Vec<(Sym, f64)>)>,
    pub brigades: Vec<(String, Vec<(Sym, i64)>)>,
    pub techs: Vec<(String, Vec<String>)>,
    pub pops: Vec<(String, Vec<(Sym, i64)>)>,
    pub cultures: Vec<(String, Vec<(String, i64, i64)>)>,
}

/// What survives of a nation for the rest of the run (`KEEP_NATION`).
pub struct Kept {
    pub tag: String,
    pub units_at: Vec<Stack>,
    pub primary_culture: Sym,
    pub accepted_cultures: Vec<Sym>,
    pub government: String,
    pub capital: String,
}

/// One naval profile: [(ship, stats, heavy)].
pub type Profile = Vec<(String, [f64; 5], i64)>;

/// A save spent: `spending.Spent` and `SaveRows` together.
pub struct Spent {
    pub meta: Meta,
    pub nations: Vec<Kept>,
    pub chunk: String,
    pub rows: Vec<Row>,
    pub tables: PerNation,
    /// (tag, key, profile)
    pub naval: Vec<(String, String, Profile)>,
    /// (good, tag, amount)
    pub supply: Vec<(String, String, f64)>,
    /// The six tables' CSV text, in `PER_SAVE` order.
    pub text: [String; 6],
}

/// `json.dumps(profile, sort_keys=True)`: the key a profile is known by.
fn profile_key(p: &Profile) -> String {
    let mut ships: Vec<&(String, [f64; 5], i64)> = p.iter().collect();
    ships.sort_by(|a, b| a.0.cmp(&b.0));
    // Sorted stat names: evasion, gun_power, heavy, hull, score, torpedo_attack.
    let mut out = String::from("{");
    for (i, (name, s, heavy)) in ships.iter().enumerate() {
        if i > 0 {
            out.push_str(", ");
        }
        push_json_str(&mut out, name);
        out.push_str(": {\"evasion\": ");
        push_json_float(&mut out, s[2]);
        out.push_str(", \"gun_power\": ");
        push_json_float(&mut out, s[1]);
        out.push_str(", \"heavy\": ");
        push_int(&mut out, *heavy);
        out.push_str(", \"hull\": ");
        push_json_float(&mut out, s[0]);
        out.push_str(", \"score\": ");
        push_json_float(&mut out, s[4]);
        out.push_str(", \"torpedo_attack\": ");
        push_json_float(&mut out, s[3]);
        out.push('}');
    }
    out.push('}');
    out
}

fn csv_line(out: &mut String, vals: &[Val]) {
    for (i, v) in vals.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        v.push_csv(out);
    }
    out.push_str("\r\n");
}

/// The rest of finishing, and `save_rows`: one prepared save spent.
pub fn finish(pre: Pre, spec: &Spec, m: &Mod, live: Option<&FxSet<String>>) -> D<Spent> {
    let Pre { meta, nations, chunk, .. } = pre;
    let world: World = save_world(&meta, m);
    let date = meta.date.clone();
    let year = date.split('.').next().unwrap_or("").to_string();
    let mut rows = Vec::new();
    let mut tables = PerNation::default();
    let mut naval = Vec::new();
    let mut supply = Vec::new();
    let mut text: [String; 6] = Default::default();
    let mut kept_out = Vec::with_capacity(nations.len());
    let columns = &spec.columns;

    for pre in nations {
        let PreNation { tag, mut nat, kept, is_player, buckets, pool, entries, cap_rule } = pre;
        if !kept {
            kept_out.push(trim(&tag, &mut nat));
            continue;
        }
        let rate = rate_for(&nat, m, live, Some(&world), is_player)?;
        let ppr = spec.pop_per_regiment;
        // `brigades_from_clusters`.
        let mut brigades = 0i64;
        let mut pooled = 0.0f64;
        for &size in &buckets {
            let manpower = size as f64 * rate;
            if manpower <= 0.0 {
                continue;
            }
            if manpower >= ppr as f64 {
                brigades += trunc_int(floordiv(manpower, ppr as f64)).unwrap_or(0);
                pooled = 0.0;
            } else {
                pooled += manpower;
                if pooled >= ppr as f64 {
                    brigades += 1;
                    pooled = 0.0;
                }
            }
        }
        let total = nat.total_pop;
        let pct = |part: i64, digits: u32| -> f64 {
            if total != 0 { round(100.0 * part as f64 / total as f64, digits) } else { 0.0 }
        };
        let accepted_pop: i64 = nat.pop_by_culture.iter()
            .filter(|(c, _)| nat.accepts(**c)).map(|(_, s)| *s).sum();
        let primary_pop = nat.pop_by_culture.get(&nat.primary_culture).copied().unwrap_or(0);
        let mut policy = String::new();
        let mut cap = 0i64;
        let index = trunc_int(if nat.ruling_party.truthy() { nat.ruling_party.as_f64() } else { 0.0 })
            .unwrap_or(0) - 1;
        if 0 <= index && (index as usize) < m.party_policies.len() {
            policy = m.party_policies[index as usize].clone();
        }
        if let Some(impact) = m.mob_impacts.get(&policy) {
            let impact = impact + impact_for(&nat, m, Some(&world), is_player)?;
            let floor = trunc_int(match m.define("MIN_MOBILIZE_LIMIT") {
                Some(v) => v,
                None => 3.0,
            }).unwrap_or(0);
            let standing = nat.regular_brigades.max(floor);
            cap = trunc_int(standing as f64 * (1.0 + impact)).unwrap_or(0);
        }
        let layers = &m.strata;
        let stratum = |name: &str| -> i64 {
            let vanilla: &[String] = spec.strata.iter().find(|(n, _)| n == name)
                .map(|(_, v)| v.as_slice()).unwrap_or(&[]);
            if !layers.is_empty() {
                nat.pop_by_type.iter()
                    .filter(|(t, _)| layers.get(names::text(**t)).map(|s| s.as_str()) == Some(name))
                    .map(|(_, s)| *s).sum()
            } else {
                vanilla.iter().map(|t| nat.pop_by_type.get(&names::intern_str(t)).copied().unwrap_or(0)).sum()
            }
        };
        let mut accepted: Vec<&str> = nat.accepted_cultures.iter().map(|s| names::text(*s)).collect();
        accepted.sort();
        let head = [Val::S(&date), Val::S(&year), Val::S(&tag)];

        // ships_by_type.csv, and the payload's ships and crews.
        let mut ship_types: Vec<&Ship> = nat.ships_by_type.iter().collect();
        ship_types.sort_by(|a, b| names::cmp(a.kind, b.kind));
        let (mut count_of, mut crew_of) = (Vec::new(), Vec::new());
        for ship in ship_types {
            let effective = Num::F(round(ship.crew, 3));
            csv_line(&mut text[1], &[head[0], head[1], head[2], Val::S(names::text(ship.kind)),
                                     Val::I(ship.count), Val::N(effective)]);
            count_of.push((ship.kind, ship.count));
            let e = effective.as_f64();
            if (e - ship.count as f64).abs() > 0.005 {
                crew_of.push((ship.kind, round(e, 2)));
            }
        }
        if !count_of.is_empty() {
            tables.ships.push((tag.clone(), count_of));
        }
        if !crew_of.is_empty() {
            tables.crews.push((tag.clone(), crew_of));
        }
        if nat.ships != 0 {
            let profile = naval_profile(&nat, m);
            naval.push((tag.clone(), profile_key(&profile), profile));
        }
        for (good, amount) in nat.goods_supply.iter() {
            supply.push((good.clone(), tag.clone(), *amount));
        }
        let mut regiments: Vec<&(Sym, i64)> = nat.regiments_by_type.iter().collect();
        regiments.sort_by(|a, b| names::cmp(a.0, b.0));
        let mut held = Vec::new();
        for &(rtype, count) in regiments {
            csv_line(&mut text[2], &[head[0], head[1], head[2], Val::S(names::text(rtype)),
                                     Val::I(count)]);
            held.push((rtype, count));
        }
        if !held.is_empty() {
            tables.brigades.push((tag.clone(), held));
        }
        let mut techs: Vec<Sym> = nat.tech_list.clone();
        techs.sort_by(|a, b| names::cmp(*a, *b));
        let dense = m.dense();
        let mut names: Vec<String> = Vec::with_capacity(techs.len());
        for tech in &techs {
            let (branch, line) = dense.tech_group(*tech).unwrap_or(("other", "Other"));
            let tech = names::text(*tech);
            csv_line(&mut text[3], &[head[0], head[1], head[2], Val::S(tech), Val::S(branch),
                                     Val::S(line)]);
            names.push(tech.to_string());
        }
        if !names.is_empty() {
            tables.techs.push((tag.clone(), names));
        }
        let mut pops: Vec<(&Sym, &i64)> = nat.pop_by_type.iter().collect();
        pops.sort_by(|a, b| names::cmp(*a.0, *b.0));
        let mut held = Vec::new();
        for (ptype, size) in pops {
            csv_line(&mut text[4], &[head[0], head[1], head[2], Val::S(names::text(*ptype)),
                                     Val::I(*size)]);
            held.push((*ptype, *size));
        }
        if !held.is_empty() {
            tables.pops.push((tag.clone(), held));
        }
        // Largest first; a stable sort, so equal sizes keep the save's order.
        let mut cultures: Vec<(&Sym, &i64)> = nat.pop_by_culture.iter().collect();
        cultures.sort_by(|a, b| b.1.cmp(a.1));
        let accepted_set = |c: Sym| nat.accepted_cultures.contains(&c)
            || nat.primary_culture == c;
        let mut largest = Vec::new();
        for (culture, size) in cultures {
            let acc = accepted_set(*culture) as i64;
            let culture = names::text(*culture);
            csv_line(&mut text[5], &[head[0], head[1], head[2], Val::S(culture), Val::I(*size),
                                     Val::I(acc)]);
            largest.push((culture.to_string(), *size, acc));
        }
        if !largest.is_empty() {
            tables.cultures.push((tag.clone(), largest));
        }
        let row = Row {
            key: tag.clone(),
            date: date.clone(),
            year: year.clone(),
            is_player,
            accepted_pop,
            accepted_pct: pct(accepted_pop, 2),
            primary_culture_pop: primary_pop,
            avg_literacy: if total != 0 { round(nat.literacy_weighted / total as f64, 5) } else { 0.0 },
            avg_literacy_stated: if nat.pop_noncolonial != 0 {
                round(nat.literacy_noncolonial / nat.pop_noncolonial as f64, 5)
            } else { 0.0 },
            avg_consciousness: if total != 0 { round(nat.con_weighted / total as f64, 4) } else { 0.0 },
            avg_militancy: if total != 0 { round(nat.mil_weighted / total as f64, 4) } else { 0.0 },
            brigade_cap: cap_rule.max(nat.regular_brigades),
            mobilisation_size: round(rate, 5),
            mobilization_pool: pool,
            mobilization_pops: entries,
            mobilization_brigades: brigades,
            mobilization_cap: cap,
            mobilization_available: if cap != 0 { brigades.min(cap) } else { brigades },
            mobilization_remaining: (brigades - nat.mobilized_brigades - nat.mobilizing).max(0),
            war_policy: policy,
            pop_poor: stratum("poor"),
            pop_middle: stratum("middle"),
            pop_rich: stratum("rich"),
            soldiers_noncolonial_pct: pct(nat.soldiers_noncolonial, 3),
            life_unmet_pct: pct(nat.life_unmet, 3),
            starving_pct: pct(nat.starving, 3),
            accepted_cultures: accepted.join(";"),
            facts: RowFacts::take(&mut nat),
        };
        let vals: Vec<Val> = columns.iter().map(|c| row.get(c)).collect();
        csv_line(&mut text[0], &vals);
        kept_out.push(trim(&tag, &mut nat));
        rows.push(row);
    }
    Ok(Spent { meta, nations: kept_out, chunk, rows, tables, naval, supply, text })
}

/// `nat`'s units, cultures, government and capital, moved out of it.
fn trim(tag: &str, nat: &mut Nation) -> Kept {
    Kept {
        tag: tag.to_string(),
        units_at: std::mem::take(&mut nat.units_at),
        primary_culture: nat.primary_culture,
        accepted_cultures: std::mem::take(&mut nat.accepted_cultures),
        government: std::mem::take(&mut nat.government),
        capital: std::mem::take(&mut nat.capital),
    }
}


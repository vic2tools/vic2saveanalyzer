// A save's `(meta, nations)`, built as the analyzer's Python builds it.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// What `readsave.analyze_save` returns when this scanner answers in JSON:
// every nation a `nation.blank_nation()`, its provinces folded in by
// `nation.fold_provinces`, its country blocks by `nation.fold_country`, its
// regiments settled by `readsave._settle`, and only the nations holding
// land or people kept. The rules are the ones in `nation.SCANNED_PROVINCES`
// and `SCANNED_COUNTRY`, applied here to the same numbers with the same
// types -- an int where the JSON would have held an int, a float where it
// would have held a float -- so the two ways of reading a save give records
// equal field for field and type for type. `testkit/readboth.py` holds them
// to that, and to Python's own reader, on every save it is given.

use crate::clause::{self, V};
use crate::country::Country;
use crate::pickle::{
    add, greater, text, truthy, Factory, Fixed, FxMap, Key, OMap, OSet, Pickler, Str, P,
};
use crate::province::Scan;
use std::sync::OnceLock;

type R<T> = Result<T, ()>;

/// `nation.blank_nation()`'s keys, in its order. `testkit/record.py` checks
/// this list against the Python one.
const FIELDS: [&str; 73] = [
    "primary_culture", "accepted_cultures", "civilized", "government", "capital",
    "prestige", "infamy", "treasury", "tax_base", "war_exhaustion", "plurality",
    "research_points", "techs", "brigades", "armies", "ships", "navies",
    "ships_by_type", "ship_crew", "regiments_by_type", "regiment_pops", "units_at",
    "men_at", "mobilized_brigades", "regular_brigades", "mobilizing", "is_mobilized",
    "tech_list", "invention_ids", "nationalvalue", "tag", "modifiers", "revanchism",
    "ruling_party", "war_policy", "country_flags", "reforms", "human", "is_player",
    "army_techs", "navy_techs", "factory_count", "factory_levels", "states",
    "provinces", "naval_base_levels", "max_naval_base", "ports", "fort_levels",
    "railroad_levels", "total_pop", "pop_by_type", "pop_by_culture", "life_unmet",
    "starving", "soldiers_noncolonial", "pop_noncolonial", "literacy_noncolonial",
    "soldier_pops_at", "core_provinces", "colonial_level", "province_colonial",
    "population_by_state", "goods_supply", "mobilizable_pops", "mob_excluded_culture",
    "colonial_provinces", "province_state", "occupied_provinces", "literacy_weighted",
    "con_weighted", "mil_weighted", "money_total",
];

/// What each of `FIELDS` starts as.
fn blank() -> Fixed {
    let dd = |f| P::DefaultDict(f, OMap::new());
    let vals = FIELDS.iter().map(|name| match *name {
        "primary_culture" | "civilized" | "government" | "capital" | "nationalvalue"
        | "tag" | "war_policy" => P::Str(empty()),
        "accepted_cultures" | "regiment_pops" | "tech_list" | "invention_ids"
        | "modifiers" | "mobilizable_pops" => P::List(Vec::new()),
        "prestige" | "infamy" | "treasury" | "tax_base" | "war_exhaustion" | "plurality"
        | "research_points" | "revanchism" | "literacy_noncolonial" | "literacy_weighted"
        | "con_weighted" | "mil_weighted" | "money_total" => P::Float(0.0),
        "ships_by_type" | "regiments_by_type" | "pop_by_type" | "pop_by_culture" => {
            dd(Factory::Int)
        }
        "ship_crew" => dd(Factory::Float),
        "units_at" | "men_at" => dd(Factory::Counter),
        "soldier_pops_at" => dd(Factory::List),
        "country_flags" | "core_provinces" | "colonial_provinces" | "occupied_provinces" => {
            P::Set(OSet::default())
        }
        "reforms" | "colonial_level" | "province_colonial" | "population_by_state"
        | "goods_supply" | "province_state" => P::Dict(OMap::new()),
        "human" | "is_player" => P::Bool(false),
        _ => P::Int(0),
    }).collect();
    Fixed { names: &FIELDS, vals, extra: OMap::new() }
}

fn empty() -> Str {
    thread_local!(static EMPTY: Str = text(b""));
    EMPTY.with(|e| e.clone())
}

fn index() -> &'static FxMap<&'static str, usize> {
    static INDEX: OnceLock<FxMap<&'static str, usize>> = OnceLock::new();
    INDEX.get_or_init(|| FIELDS.iter().enumerate().map(|(i, n)| (*n, i)).collect())
}

/// The field, by name: `nat[name]`.
fn field<'a>(nat: &'a mut Fixed, name: &str) -> R<&'a mut P> {
    match index().get(name) {
        Some(&i) => Ok(&mut nat.vals[i]),
        None => Err(()),
    }
}

/// `nat[name] = v`, for a name a country block brings: one outside the
/// blank record goes on the end, as a new key would.
fn put(nat: &mut Fixed, name: &str, v: P) {
    match index().get(name) {
        Some(&i) => nat.vals[i] = v,
        None => nat.extra.set(Key::S(text(name.as_bytes())), v),
    }
}

/// `nat[field] += value`.
fn add_to(nat: &mut Fixed, name: &str, v: P) -> R<()> {
    let slot = field(nat, name)?;
    *slot = add(slot, &v).ok_or(())?;
    Ok(())
}

/// `_add_if`: only a value Python calls true.
fn add_if(nat: &mut Fixed, name: &str, v: P) -> R<()> {
    if truthy(&v) { add_to(nat, name, v) } else { Ok(()) }
}

/// `_highest`.
fn highest(nat: &mut Fixed, name: &str, v: P) -> R<()> {
    let slot = field(nat, name)?;
    if greater(&v, slot).ok_or(())? {
        *slot = v;
    }
    Ok(())
}

fn set_of<'a>(nat: &'a mut Fixed, name: &str) -> R<&'a mut OSet> {
    match field(nat, name)? {
        P::Set(s) => Ok(s),
        _ => Err(()),
    }
}

fn dict_of<'a>(nat: &'a mut Fixed, name: &str) -> R<&'a mut OMap> {
    match field(nat, name)? {
        P::Dict(m) | P::DefaultDict(_, m) => Ok(m),
        _ => Err(()),
    }
}

fn list_of<'a>(nat: &'a mut Fixed, name: &str) -> R<&'a mut Vec<P>> {
    match field(nat, name)? {
        P::List(v) => Ok(v),
        _ => Err(()),
    }
}

/// What a `defaultdict` with this factory makes for a new key.
fn made(f: Factory) -> P {
    match f {
        Factory::Int => P::Int(0),
        Factory::Float => P::Float(0.0),
        Factory::List => P::List(vec![]),
        Factory::Counter => P::Counter(OMap::new()),
    }
}

/// `target[key] += item` on a `defaultdict`.
fn pairs_add(nat: &mut Fixed, name: &str, pairs: impl Iterator<Item = (Key, P)>) -> R<()> {
    let (factory, map) = match field(nat, name)? {
        P::DefaultDict(f, m) => (*f, m),
        _ => return Err(()),
    };
    for (key, item) in pairs {
        let slot = map.entry(key, || made(factory));
        *slot = add(slot, &item).ok_or(())?;
    }
    Ok(())
}

/// Every name the scan or the country blocks spell, shared: one `Arc` per
/// distinct name for the whole save, so a culture on forty thousand pops is
/// one allocation here and one string object once unpickled.
#[derive(Default)]
struct Names(FxMap<Vec<u8>, Str>);

impl Names {
    fn get(&mut self, b: &[u8]) -> Str {
        if let Some(s) = self.0.get(b) {
            return s.clone();
        }
        let s = text(b);
        self.0.insert(b.to_vec(), s.clone());
        s
    }

    fn of(&mut self, s: &str) -> Str {
        if s.is_ascii() {
            self.get(s.as_bytes())
        } else {
            let b: Vec<u8> = s.chars().map(|c| c as u32 as u8).collect();
            self.get(&b)
        }
    }
}

/// `_pairs_add_nested`: `counter[kind] = counter.get(kind, 0) + item`.
fn pairs_add_nested(nat: &mut Fixed, name: &str, rows: &[(i64, Vec<(String, i64)>)],
                    names: &mut Names) -> R<()> {
    let map = match field(nat, name)? {
        P::DefaultDict(Factory::Counter, m) => m,
        _ => return Err(()),
    };
    for (pid, items) in rows {
        let counter = match map.entry(Key::I(*pid), || P::Counter(OMap::new())) {
            P::Counter(c) => c,
            _ => return Err(()),
        };
        for (kind, n) in items {
            let key = Key::S(names.of(kind));
            let now = match counter.get(&key) {
                Some(v) => add(v, &P::Int(*n)).ok_or(())?,
                None => P::Int(*n),
            };
            counter.set(key, now);
        }
    }
    Ok(())
}

/// `fold_provinces(nat, block, names)`.
fn fold_provinces(nat: &mut Fixed, n: &crate::province::Nation, table: &[Str],
                  names: &mut Names) -> R<()> {
    add_to(nat, "provinces", P::Int(n.provinces))?;
    add_to(nat, "ports", P::Int(n.ports))?;
    add_to(nat, "total_pop", P::Int(n.total_pop))?;
    add_to(nat, "life_unmet", P::Int(n.life_unmet))?;
    add_to(nat, "starving", P::Int(n.starving))?;
    add_if(nat, "naval_base_levels", P::Float(n.naval_base_levels))?;
    highest(nat, "max_naval_base", P::Float(n.max_naval_base))?;
    add_to(nat, "fort_levels", P::Float(n.fort_levels))?;
    add_to(nat, "railroad_levels", P::Float(n.railroad_levels))?;
    add_to(nat, "literacy_weighted", P::Float(n.literacy_weighted))?;
    add_to(nat, "con_weighted", P::Float(n.con_weighted))?;
    add_to(nat, "mil_weighted", P::Float(n.mil_weighted))?;
    add_to(nat, "money_total", P::Float(n.money_total))?;
    let cores = set_of(nat, "core_provinces")?;
    for c in &n.cores {
        cores.add(Key::I(*c));
    }
    let occupied = set_of(nat, "occupied_provinces")?;
    for c in &n.occupied {
        occupied.add(Key::I(*c));
    }
    let colonial = dict_of(nat, "province_colonial")?;
    for (pid, flag) in &n.colonial {
        colonial.set(Key::I(*pid), P::Int(*flag));
    }
    let counted = |c: &crate::province::Counter, names: &mut Names| -> Vec<(Key, P)> {
        c.order.iter().zip(&c.total)
            .map(|(name, t)| (Key::S(names.get(name)), P::Int(*t)))
            .collect()
    };
    pairs_add(nat, "pop_by_type", counted(&n.pop_by_type, names).into_iter())?;
    pairs_add(nat, "pop_by_culture", counted(&n.pop_by_culture, names).into_iter())?;
    // `_population_rows`: the whole field replaced, one row a group.
    let mut rows = OMap::new();
    for group in &n.population_order {
        let st = &n.population_by_state[group];
        let mut as_dict = |c: &crate::province::Counter| {
            let mut m = OMap::new();
            for (k, v) in counted(c, names) {
                m.set(k, v);
            }
            P::Dict(m)
        };
        let types = as_dict(&st.types);
        let cultures = as_dict(&st.cultures);
        rows.set(Key::I(*group), P::List(vec![
            P::Int(st.total), P::Float(st.literate), types, cultures, P::Int(st.provinces)]));
    }
    put(nat, "population_by_state", P::Dict(rows));
    add_to(nat, "soldiers_noncolonial", P::Int(n.soldiers_noncolonial))?;
    add_to(nat, "pop_noncolonial", P::Int(n.pop_noncolonial))?;
    add_to(nat, "literacy_noncolonial", P::Float(n.literacy_noncolonial))?;
    add_to(nat, "mob_excluded_culture", P::Int(n.mob_excluded_culture))?;
    // Sorted by province, as the JSON sent them.
    let mut at: Vec<&i64> = n.soldier_pops_at.keys().collect();
    at.sort();
    let soldiers = dict_of(nat, "soldier_pops_at")?;
    for pid in at {
        match soldiers.entry(Key::I(*pid), || P::List(vec![])) {
            P::List(v) => v.extend(n.soldier_pops_at[pid].iter().map(|s| P::Int(*s))),
            _ => return Err(()),
        }
    }
    let pool = list_of(nat, "mobilizable_pops")?;
    pool.reserve(n.mobilizable.len());
    for (kind, culture, size, pid) in &n.mobilizable {
        pool.push(P::Tuple(vec![
            P::Str(table.get(*kind as usize).ok_or(())?.clone()),
            P::Str(table.get(*culture as usize).ok_or(())?.clone()),
            P::Int(*size), P::Int(*pid)]));
    }
    Ok(())
}

/// `fold_country(nat, block)`.
fn fold_country(nat: &mut Fixed, c: &Country, names: &mut Names) -> R<()> {
    put(nat, "tag", P::Str(names.of(&c.tag)));
    for (name, value) in &c.scalars {
        put(nat, name, P::Str(names.of(value)));
    }
    for (name, value) in &c.numerics {
        put(nat, name, P::Float(*value));
    }
    put(nat, "is_mobilized", P::Int(c.is_mobilized));
    put(nat, "human", P::Bool(c.human));
    {
        let reforms = dict_of(nat, "reforms")?;
        for (key, item) in &c.reforms {
            reforms.set(Key::S(names.of(key)), P::Str(names.of(item)));
        }
    }
    let strs = |v: &[String], names: &mut Names| -> Vec<P> {
        v.iter().map(|s| P::Str(names.of(s))).collect()
    };
    if !c.accepted_cultures.is_empty() {
        put(nat, "accepted_cultures", P::List(strs(&c.accepted_cultures, names)));
    }
    if !c.country_flags.is_empty() {
        let mut flags = OSet::default();
        for f in &c.country_flags {
            flags.add(Key::S(names.of(f)));
        }
        put(nat, "country_flags", P::Set(flags));
    }
    let modifiers = strs(&c.modifiers, names);
    list_of(nat, "modifiers")?.extend(modifiers);
    if !c.goods_supply.is_empty() {
        let mut m = OMap::new();
        for (good, v) in &c.goods_supply {
            m.set(Key::S(names.of(good)), P::Float(*v));
        }
        put(nat, "goods_supply", P::Dict(m));
    }
    if !c.invention_ids.is_empty() {
        put(nat, "invention_ids", P::List(c.invention_ids.iter().map(|i| P::Int(*i)).collect()));
    }
    add_to(nat, "mobilizing", P::Int(c.mobilizing))?;
    add_to(nat, "states", P::Int(c.states))?;
    {
        let ps = dict_of(nat, "province_state")?;
        for (a, b) in &c.province_state {
            ps.set(Key::I(*a), P::Int(*b));
        }
    }
    {
        let cp = set_of(nat, "colonial_provinces")?;
        for p in &c.colonial_provinces {
            cp.add(Key::I(*p));
        }
    }
    {
        let cl = dict_of(nat, "colonial_level")?;
        for (a, b) in &c.colonial_level {
            cl.set(Key::I(*a), P::Int(*b));
        }
    }
    add_to(nat, "factory_count", P::Int(c.factory_count))?;
    add_to(nat, "factory_levels", P::Int(c.factory_levels))?;
    add_to(nat, "techs", P::Int(c.techs))?;
    let techs = strs(&c.tech_list, names);
    list_of(nat, "tech_list")?.extend(techs);
    add_to(nat, "army_techs", P::Int(c.army_techs))?;
    add_to(nat, "navy_techs", P::Int(c.navy_techs))?;
    add_to(nat, "brigades", P::Int(c.brigades))?;
    add_to(nat, "armies", P::Int(c.armies))?;
    add_to(nat, "navies", P::Int(c.navies))?;
    add_to(nat, "ships", P::Int(c.ships))?;
    list_of(nat, "regiment_pops")?.extend(c.regiment_pops.iter().map(|p| P::Int(*p)));
    let typed = |v: &[(String, i64)], names: &mut Names| -> Vec<(Key, P)> {
        v.iter().map(|(t, n)| (Key::S(names.of(t)), P::Int(*n))).collect()
    };
    pairs_add(nat, "regiments_by_type", typed(&c.regiments_by_type, names).into_iter())?;
    pairs_add(nat, "ships_by_type", typed(&c.ships_by_type, names).into_iter())?;
    let crew: Vec<(Key, P)> = c.ship_crew.iter()
        .map(|(t, n)| (Key::S(names.of(t)), P::Float(*n))).collect();
    pairs_add(nat, "ship_crew", crew.into_iter())?;
    pairs_add_nested(nat, "units_at", &c.units_at, names)?;
    pairs_add_nested(nat, "men_at", &c.men_at, names)?;
    Ok(())
}

/// Everything about the save that is not the nations, as the record needs it.
pub struct Head<'a> {
    pub file: &'a [u8],
    pub date: &'a [u8],
    pub player: &'a [u8],
}

/// The wars, the market and the great power list: what Python read out of
/// the file while this scanned the provinces, and what this now reads on a
/// thread of its own for the same reason (`main.rs`).
pub struct Rest {
    wars: Vec<P>,
    market: P,
    great: P,
}

/// `Rest`, from the save's top-level blocks. `date` is the save's own, which
/// the market's record carries.
pub fn read_rest(text: &[u8], blocks: &[(&[u8], usize, usize)], date: &[u8]) -> R<Rest> {
    let mut wars = Vec::new();
    let mut market = P::None;
    let mut seen_market = false;
    let mut great = P::List(vec![]);
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
            // The first one, whatever it is; only a dict makes a market.
            seen_market = true;
            if let V::Dict(block) = &tree {
                market = clause::read_worldmarket(block, date)?;
            }
        } else if let Some(war) = clause::read_war(&tree, key == b"active_war")? {
            wars.push(war);
        }
    }
    Ok(Rest { wars, market, great })
}

/// The whole record, pickled: `(meta, nations)`.
pub fn build(head: &Head, scan: &Scan, countries: &[Country], rest: Rest) -> R<Vec<u8>> {
    let mut names = Names::default();
    let table: Vec<Str> = scan.words.names.iter().map(|n| names.get(n)).collect();

    // Nations in the order Python's defaultdict made them: the provinces'
    // owners as the scan first met them. Only the ones that will be kept,
    // though: a nation is kept for holding land or people, both of which
    // come from the provinces alone, so one with neither is known to be
    // dropped before anything is folded into it. Python built all of them
    // and threw away most -- 236 of 277 in a save of 1880 -- and so did this.
    let mut order: Vec<Str> = Vec::new();
    let mut nations: FxMap<Str, Fixed> = FxMap::default();
    for tag in &scan.seen {
        let scanned = &scan.nations[tag.as_slice()];
        if !(scanned.provinces > 0 || scanned.total_pop > 0) {
            continue;
        }
        let tag_s = names.get(tag);
        let nat = nations.entry(tag_s.clone()).or_insert_with(|| {
            order.push(tag_s.clone());
            blank()
        });
        fold_provinces(nat, scanned, &table, &mut names)?;
    }
    for c in countries {
        let tag_s = names.of(&c.tag);
        if let Some(nat) = nations.get_mut(&tag_s) {
            fold_country(nat, c, &mut names)?;
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
    let mut live = OMap::new();
    for tag in &order {
        let mut nat = nations.remove(tag).ok_or(())?;
        let (mut regular, mut mobilized) = (0i64, 0i64);
        for p in list_of(&mut nat, "regiment_pops")?.iter() {
            let pid = if let P::Int(i) = p { *i } else { return Err(()) };
            match registry.get(&pid) {
                None | Some(true) => regular += 1,
                Some(false) => mobilized += 1,
            }
        }
        // Python adds them one at a time; they are ints, so the sum is the same.
        if regular > 0 {
            add_to(&mut nat, "regular_brigades", P::Int(regular))?;
        }
        if mobilized > 0 {
            add_to(&mut nat, "mobilized_brigades", P::Int(mobilized))?;
        }
        put(&mut nat, "regiment_pops", P::Tuple(vec![]));
        let holds = |nat: &mut Fixed, name: &str| -> R<bool> {
            Ok(matches!(field(nat, name)?, P::Int(n) if *n > 0))
        };
        if holds(&mut nat, "provinces")? || holds(&mut nat, "total_pop")? {
            live.set(Key::S(tag.clone()), P::Fixed(Box::new(nat)));
        }
    }

    let mut owners = OMap::new();
    for (pid, owner, held) in &scan.owners {
        owners.set(Key::I(*pid), P::Tuple(vec![P::Str(names.get(owner)), P::Str(names.get(held))]));
    }
    let k = |x: &str| Key::S(text(x.as_bytes()));
    let mut meta = OMap::new();
    meta.set(k("file"), P::Str(text(head.file)));
    meta.set(k("date"), P::Str(text(head.date)));
    meta.set(k("player"), P::Str(text(head.player)));
    // `market` holds its place from the start, as the Python's dict does,
    // with None where the save had no market to read.
    meta.set(k("market"), rest.market);
    meta.set(k("world_pop"), P::Int(scan.world_pop));
    meta.set(k("province_owner"), P::Dict(owners));
    meta.set(k("great_nations"), rest.great);
    meta.set(k("wars"), P::List(rest.wars));

    let mut out = Pickler::new();
    out.value(&P::Tuple(vec![P::Dict(meta), P::Dict(live)]));
    Ok(out.finish())
}

// A save read token by token, for one not laid out the way the game writes it.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The scan (`province.rs`, `country.rs`) finds a save's entries by where
// the game puts them: a top-level key at the left margin with its `{` on
// the next line, a province's fields one tab in, a pop's two. A save
// reflowed by a text editor is none of that, and Python reads it the slow
// way instead (`readsave._Whole` with `flat=False`): `v2parse.Tokens`,
// `walk_entries`, `parse_block` and `read_pop`, the country and province
// readers fed by them. These are those, rule for rule -- the token pattern
// with Python's `\s`, `skip_to_close` by `block_end` from the last token,
// a repeated key kept at its first place with its values gathered -- and
// what they find goes into the same record the scan fills.

use crate::clause::{unquote, V};
use crate::country::{Country, Tables};
use crate::engine::modread::{block_end, py_float, str_of};
use crate::pickle::{FxMap, FxSet};
use crate::province::{accumulate, pop_known, Parts, Pop, PopulationRules, Scan};
use crate::pyre::space;

/// `v2parse.Tokens`: a cursor over `TOKEN_RE`, one token of pushback, and a
/// whole-block skip.
pub struct Tokens<'a> {
    text: &'a [u8],
    pos: usize,
    pushed: Option<Option<(usize, usize)>>,
}

impl<'a> Tokens<'a> {
    pub fn new(text: &'a [u8], at: usize) -> Tokens<'a> {
        Tokens { text, pos: at, pushed: None }
    }

    /// The next token's span, or None at the end.
    pub fn next(&mut self) -> Option<(usize, usize)> {
        if let Some(t) = self.pushed.take() {
            return t;
        }
        let b = self.text;
        let n = b.len();
        let mut i = self.pos;
        while i < n && space(b[i]) {
            i += 1;
        }
        if i >= n {
            self.pos = n;
            return None;
        }
        let c = b[i];
        if c == b'"' {
            if let Some(off) = b[i + 1..].iter().position(|&x| x == b'"') {
                let end = i + 1 + off + 1;
                self.pos = end;
                return Some((i, end));
            }
        }
        if c == b'{' || c == b'}' || c == b'=' {
            self.pos = i + 1;
            return Some((i, i + 1));
        }
        let start = i;
        while i < n && !space(b[i]) && b[i] != b'{' && b[i] != b'}' && b[i] != b'=' {
            i += 1;
        }
        self.pos = i;
        Some((start, i))
    }

    pub fn push(&mut self, t: Option<(usize, usize)>) {
        self.pushed = Some(t);
    }

    pub fn get(&self, t: (usize, usize)) -> &'a [u8] {
        &self.text[t.0..t.1]
    }

    fn is(&self, t: Option<(usize, usize)>, what: &[u8]) -> bool {
        t.is_some_and(|t| self.get(t) == what)
    }

    /// Consume everything up to the `}` closing the block already opened.
    pub fn skip_to_close(&mut self) {
        if let Some(t) = self.pushed.take() {
            if self.is(t, b"}") {
                return;
            }
            if self.is(t, b"{") {
                self.skip_to_close();
            }
        }
        self.pos = block_end(self.text, self.pos).unwrap_or(self.text.len());
    }
}

/// One entry `walk_entries` yields: a key, and its value or where its block
/// begins.
pub enum Entry<'a> {
    Value(&'a [u8]),
    Block(usize),
}

/// `walk_entries(tok, top)`: every `key = value` one level inside a block
/// (or at the top of the file), each block skipped before it is handed over.
pub fn walk_entries<'a>(tok: &mut Tokens<'a>, top: bool) -> Vec<(&'a [u8], Entry<'a>)> {
    let mut out = Vec::new();
    loop {
        let t = match tok.next() {
            None => return out,
            Some(t) => t,
        };
        let word = tok.get(t);
        if word == b"}" {
            if !top {
                return out;
            }
            continue;
        }
        if top && (word == b"{" || word == b"=") {
            continue;
        }
        let nxt = tok.next();
        if nxt.is_none() {
            return out;
        }
        if !tok.is(nxt, b"=") {
            tok.push(nxt);
            continue;
        }
        let val = match tok.next() {
            None => return out,
            Some(v) => v,
        };
        if tok.get(val) == b"{" {
            let at = val.1;
            tok.skip_to_close();
            out.push((unquote(word), Entry::Block(at)));
        } else {
            out.push((unquote(word), Entry::Value(unquote(tok.get(val)))));
        }
    }
}

/// `parse_block(tok, skip)`, the `{` already read.
pub fn parse_block(tok: &mut Tokens, skip: &[&[u8]]) -> V {
    let mut out: Vec<(Vec<u8>, V)> = Vec::new();
    let mut items: Vec<V> = Vec::new();
    loop {
        let t = match tok.next() {
            None => break,
            Some(t) => t,
        };
        let word = tok.get(t);
        if word == b"}" {
            break;
        }
        if word == b"{" {
            items.push(parse_block(tok, skip));
            continue;
        }
        if word == b"=" {
            continue;
        }
        let nxt = tok.next();
        if tok.is(nxt, b"=") {
            let val_tok = tok.next();
            let val = match val_tok {
                None => break,
                Some(v) if tok.get(v) == b"{" => {
                    if skip.contains(&unquote(word)) {
                        tok.skip_to_close();
                        continue;
                    }
                    parse_block(tok, skip)
                }
                Some(v) => V::Str(unquote(tok.get(v)).to_vec()),
            };
            let key = unquote(word);
            match out.iter().position(|(k, _)| k.as_slice() == key) {
                Some(p) => {
                    let slot = &mut out[p].1;
                    let held = std::mem::replace(slot, V::Multi(Vec::new()));
                    *slot = match held {
                        V::Multi(mut many) => {
                            many.push(val);
                            V::Multi(many)
                        }
                        one => V::Multi(vec![one, val]),
                    };
                }
                None => out.push((key.to_vec(), val)),
            }
        } else {
            items.push(V::Str(unquote(word).to_vec()));
            tok.push(nxt);
        }
    }
    if !items.is_empty() {
        if out.is_empty() {
            return V::List(items);
        }
        let v = V::List(items);
        match out.iter().position(|(k, _)| k == b"_items") {
            Some(p) => out[p].1 = v,
            None => out.push((b"_items".to_vec(), v)),
        }
    }
    let mut tree = crate::clause::Tree::default();
    tree.pairs = out;
    V::Dict(tree)
}

/// `read_pop(tok)`: a pop's scalars, in the order first seen, the last of
/// a repeated one kept.
fn read_pop<'a>(tok: &mut Tokens<'a>) -> Vec<(&'a [u8], &'a [u8])> {
    let mut out: Vec<(&[u8], &[u8])> = Vec::new();
    loop {
        let t = match tok.next() {
            None => break,
            Some(t) => t,
        };
        if tok.get(t) == b"}" {
            break;
        }
        let nxt = tok.next();
        if nxt.is_none() {
            break;
        }
        if !tok.is(nxt, b"=") {
            tok.push(nxt);
            continue;
        }
        let val = match tok.next() {
            None => break,
            Some(v) => v,
        };
        if tok.get(val) == b"{" {
            tok.skip_to_close();
        } else {
            let key = unquote(tok.get(t));
            let value = unquote(tok.get(val));
            match out.iter_mut().find(|(k, _)| *k == key) {
                Some(slot) => slot.1 = value,
                None => out.push((key, value)),
            }
        }
    }
    out
}

// ------------------------------------------------------ Python's numbers

/// `to_float(value, default)`.
fn to_float(v: Option<&V>, default: f64) -> f64 {
    match v {
        Some(V::Str(s)) => py_float(s).unwrap_or(default),
        _ => default,
    }
}

/// `to_int(value, default)`: `int(float(value))`; Err for the infinity
/// Python lets out as an OverflowError.
fn to_int(v: Option<&V>, default: i64) -> Result<i64, String> {
    match v {
        Some(V::Str(s)) => to_int_text(s, default),
        _ => Ok(default),
    }
}

fn to_int_text(s: &[u8], default: i64) -> Result<i64, String> {
    match py_float(s) {
        None => Ok(default),
        Some(f) if f.is_nan() => Ok(default),
        Some(f) if f.is_infinite() => Err("int() of an infinity".into()),
        Some(f) if f.abs() < 9.0e18 => Ok(f.trunc() as i64),
        Some(_) => Err("a number past 64 bits".into()),
    }
}

fn get<'v>(v: &'v V, key: &[u8]) -> Option<&'v V> {
    match v {
        V::Dict(d) => d.get(key),
        _ => None,
    }
}

fn pairs(v: &V) -> &[(Vec<u8>, V)] {
    match v {
        V::Dict(d) => &d.pairs,
        _ => &[],
    }
}

fn text(b: &[u8]) -> String {
    crate::engine::modread::l1(b)
}

/// `sub_blocks(value)`.
fn sub_blocks(v: &V) -> Vec<&V> {
    match v {
        V::Dict(_) => vec![v],
        V::List(x) | V::Multi(x) => x.iter().filter(|e| matches!(e, V::Dict(_))).collect(),
        _ => Vec::new(),
    }
}

/// `as_list(value)`.
fn as_list(v: Option<&V>) -> Vec<&V> {
    crate::clause::as_list(v)
}

/// The `_items` of a block, or the block when it is a bare list.
fn items_of(v: &V) -> Vec<&V> {
    match v {
        V::List(x) => x.iter().collect(),
        V::Dict(_) => match get(v, b"_items") {
            Some(V::List(x)) | Some(V::Multi(x)) => x.iter().collect(),
            Some(one) => vec![one],
            None => Vec::new(),
        },
        _ => Vec::new(),
    }
}

// ----------------------------------------------------------- the units

#[derive(Default)]
struct Tally {
    order: Vec<String>,
    total: Vec<f64>,
}

impl Tally {
    fn add(&mut self, name: &str, by: f64) {
        match self.order.iter().position(|o| o == name) {
            Some(i) => self.total[i] += by,
            None => {
                self.order.push(name.to_string());
                self.total.push(by);
            }
        }
    }
    fn ints(&self) -> Vec<(String, i64)> {
        self.order.iter().cloned().zip(self.total.iter().map(|v| *v as i64)).collect()
    }
    fn floats(&self) -> Vec<(String, f64)> {
        self.order.iter().cloned().zip(self.total.iter().copied()).collect()
    }
}

#[derive(Default)]
struct Units {
    brigades: i64,
    armies: i64,
    navies: i64,
    ships: i64,
    regiment_pops: Vec<i64>,
    by_type: Tally,
    ships_by_type: Tally,
    ship_crew: Tally,
    at: Vec<(i64, Tally, Tally)>,
}

/// `readsave.count_units`.
fn count_units(node: &V, out: &mut Units, where_: Option<i64>) -> Result<(), String> {
    for (key, value) in pairs(node) {
        if key.first() == Some(&b'_') {
            continue;
        }
        if key == b"regiment" {
            for reg in sub_blocks(value) {
                out.brigades += 1;
                out.regiment_pops.push(match get(reg, b"pop") {
                    Some(src @ V::Dict(_)) => to_int(get(src, b"id"), -1)?,
                    _ => -1,
                });
                let raw = text(&get(reg, b"type").map(str_of).unwrap_or_default());
                let rtype = if py_float(raw.as_bytes()).is_some() { String::new() } else { raw };
                let rtype = if rtype.is_empty() { "unknown".to_string() } else { rtype };
                out.by_type.add(&rtype, 1.0);
                if let Some(w) = where_ {
                    let i = match out.at.iter().position(|(p, _, _)| *p == w) {
                        Some(i) => i,
                        None => {
                            out.at.push((w, Tally::default(), Tally::default()));
                            out.at.len() - 1
                        }
                    };
                    out.at[i].1.add(&rtype, 1.0);
                    let men = (to_float(get(reg, b"strength"), 0.0) * 1000.0).round_ties_even();
                    out.at[i].2.add(&rtype, men);
                }
            }
        } else if key == b"ship" {
            for ship in sub_blocks(value) {
                out.ships += 1;
                let kind = match get(ship, b"type") {
                    Some(v) => text(&str_of(v)),
                    None => "unknown".to_string(),
                };
                out.ships_by_type.add(&kind, 1.0);
                let strength = to_float(get(ship, b"strength"), 100.0) / 100.0;
                let experience = (to_float(get(ship, b"experience"), 0.0) / 100.0).clamp(0.0, 0.95);
                out.ship_crew.add(&kind, strength.max(0.0) / (1.0 - experience));
            }
        } else if key == b"army" || key == b"navy" {
            let blocks = sub_blocks(value);
            if key == b"army" {
                out.armies += blocks.len() as i64;
            } else {
                out.navies += blocks.len() as i64;
            }
            for block in blocks {
                let here = to_int(get(block, b"location"), -1)?;
                count_units(block, out, if here > 0 { Some(here) } else { where_ })?;
            }
        }
    }
    Ok(())
}

// ------------------------------------------------------------ a country

const SCALARS: &[(&[u8], &str)] = &[
    (b"nationalvalue", "nationalvalue"),
    (b"primary_culture", "primary_culture"),
    (b"civilized", "civilized"),
    (b"government", "government"),
    (b"capital", "capital"),
];
const NUMERICS: &[(&[u8], &str)] = &[
    (b"prestige", "prestige"),
    (b"badboy", "infamy"),
    (b"money", "treasury"),
    (b"tax_base", "tax_base"),
    (b"war_exhaustion", "war_exhaustion"),
    (b"revanchism", "revanchism"),
    (b"plurality", "plurality"),
    (b"research_points", "research_points"),
    (b"ruling_party", "ruling_party"),
];
const STATE_SKIP: &[&[u8]] = &[b"employment", b"stockpile", b"id"];
const UNIT_SKIP: &[&[u8]] = &[b"id", b"leader"];

/// `read_country(..., flat=False)`: one country block, walked.
fn read_country(text_: &[u8], at: usize, tag: &str, tables: &Tables) -> Result<Country, String> {
    let mut out = Country { tag: tag.to_string(), ..Default::default() };
    let mut units = Units::default();
    let mut tok = Tokens::new(text_, at);
    for (key, entry) in walk_entries(&mut tok, false) {
        match entry {
            Entry::Block(block_at) => {
                let mut sub = Tokens::new(text_, block_at);
                match key {
                    b"army" | b"navy" => {
                        let block = parse_block(&mut sub, UNIT_SKIP);
                        let mut wrapper = crate::clause::Tree::default();
                        wrapper.pairs.push((key.to_vec(), block));
                        count_units(&V::Dict(wrapper), &mut units, None)?;
                    }
                    b"culture" => {
                        let block = parse_block(&mut sub, &[]);
                        if matches!(block, V::List(_) | V::Dict(_)) {
                            out.accepted_cultures = items_of(&block).iter()
                                .map(|c| text(&str_of(c))).collect();
                        }
                    }
                    b"flags" => {
                        let block = parse_block(&mut sub, &[]);
                        if let V::Dict(_) = block {
                            out.country_flags = pairs(&block).iter()
                                .filter(|(k, v)| k.first() != Some(&b'_')
                                        && str_of(v).eq_ignore_ascii_case(b"yes"))
                                .map(|(k, _)| text(k)).collect();
                        }
                    }
                    b"modifier" => {
                        let block = parse_block(&mut sub, &[]);
                        if let Some(m) = get(&block, b"modifier") {
                            out.modifiers.push(text(unquote(&str_of(m))));
                        }
                    }
                    b"saved_country_supply" => {
                        let block = parse_block(&mut sub, &[]);
                        if let V::Dict(_) = block {
                            out.goods_supply = pairs(&block).iter()
                                .filter(|(g, v)| g.first() != Some(&b'_') && to_float(Some(v), 0.0) > 0.0)
                                .map(|(g, v)| (text(g), to_float(Some(v), 0.0))).collect();
                        }
                    }
                    b"active_inventions" => {
                        let block = parse_block(&mut sub, &[]);
                        let mut ids = Vec::new();
                        for i in items_of(&block) {
                            ids.push(to_int(Some(i), -1)?);
                        }
                        out.invention_ids = ids;
                    }
                    b"scheduled_mobilization" => {
                        let block = parse_block(&mut sub, &[]);
                        if !matches!(block, V::Dict(_)) {
                            return Err("a mobilization order that is a list".into());
                        }
                        let spawned = get(&block, b"spawned").map(str_of).unwrap_or(b"no".to_vec());
                        if !spawned.eq_ignore_ascii_case(b"yes") {
                            out.mobilizing += 1;
                        }
                    }
                    b"state" => {
                        let block = parse_block(&mut sub, STATE_SKIP);
                        if !matches!(block, V::Dict(_)) {
                            return Err("a state that is a list".into());
                        }
                        out.states += 1;
                        let ordinal = out.states;
                        let ids = match get(&block, b"provinces") {
                            Some(p @ V::List(_)) | Some(p @ V::Multi(_)) | Some(p @ V::Dict(_)) => items_of_or_list(p),
                            _ => Vec::new(),
                        };
                        let colonial = get(&block, b"is_colonial").is_some();
                        let level = if colonial { to_int(get(&block, b"is_colonial"), 0)? } else { 0 };
                        for pid in ids {
                            let pid = to_int(Some(pid), -1)?;
                            out.province_state.push((pid, ordinal));
                            if colonial {
                                out.colonial_provinces.push(pid);
                                out.colonial_level.push((pid, level));
                            }
                        }
                        for bld in as_list(get(&block, b"state_buildings")) {
                            if let V::Dict(_) = bld {
                                out.factory_count += 1;
                                out.factory_levels += to_int(get(bld, b"level"), 1)?;
                            }
                        }
                    }
                    b"technology" => {
                        let block = parse_block(&mut sub, &[]);
                        for (tech, tval) in pairs(&block) {
                            if tech.first() == Some(&b'_') {
                                continue;
                            }
                            let first = match tval {
                                V::List(x) | V::Multi(x) if !x.is_empty() => &x[0],
                                other => other,
                            };
                            if to_int(Some(first), 0)? == 1 {
                                let name = text(tech);
                                out.techs += 1;
                                if tables.army_techs.iter().any(|t| *t == name) {
                                    out.army_techs += 1;
                                } else if tables.navy_techs.iter().any(|t| *t == name) {
                                    out.navy_techs += 1;
                                }
                                out.tech_list.push(name);
                            }
                        }
                    }
                    _ => {}
                }
            }
            Entry::Value(clean) => {
                if key == b"mobilize" {
                    out.is_mobilized = clean.eq_ignore_ascii_case(b"yes") as i64;
                } else if key == b"human" {
                    out.human = clean.eq_ignore_ascii_case(b"yes");
                } else if tables.reform_keys.iter().any(|r| r.as_bytes() == key) {
                    out.reforms.push((text(key), text(unquote(clean))));
                } else if let Some((_, name)) = SCALARS.iter().find(|(k, _)| *k == key) {
                    out.scalars.push((name.to_string(), text(clean)));
                } else if let Some((_, name)) = NUMERICS.iter().find(|(k, _)| *k == key) {
                    out.numerics.push((name.to_string(), py_float(clean).unwrap_or(0.0)));
                }
            }
        }
    }
    out.brigades = units.brigades;
    out.armies = units.armies;
    out.navies = units.navies;
    out.ships = units.ships;
    out.regiment_pops = units.regiment_pops;
    out.regiments_by_type = units.by_type.ints();
    out.ships_by_type = units.ships_by_type.ints();
    out.ship_crew = units.ship_crew.floats();
    out.units_at = units.at.iter().map(|(p, t, _)| (*p, t.ints())).collect();
    out.men_at = units.at.iter().map(|(p, _, m)| (*p, m.ints())).collect();
    Ok(out)
}

/// A state's `provinces`: a bare list, or a block's `_items`.
fn items_of_or_list(v: &V) -> Vec<&V> {
    match v {
        V::List(_) | V::Multi(_) => match v {
            V::List(x) | V::Multi(x) => x.iter().collect(),
            _ => Vec::new(),
        },
        V::Dict(_) => items_of(v),
        _ => Vec::new(),
    }
}

// ----------------------------------------------------------- a province

/// `building_level(value)`.
fn building_level(v: Option<&V>) -> f64 {
    let v = match v {
        None => return 0.0,
        Some(v) => v,
    };
    match v {
        V::List(x) | V::Multi(x) if !x.is_empty() => to_float(Some(&x[0]), 0.0),
        V::Dict(_) => {
            for key in [&b"level"[..], b"building_level"] {
                if let Some(l) = get(v, key) {
                    return to_float(Some(l), 0.0);
                }
            }
            match get(v, b"_items") {
                Some(V::List(x)) | Some(V::Multi(x)) if !x.is_empty() => to_float(Some(&x[0]), 0.0),
                _ => 0.0,
            }
        }
        other => to_float(Some(other), 0.0),
    }
}

/// `pop_culture`: the first field neither the game's own nor a number.
fn pop_culture<'a>(pop: &[(&'a [u8], &'a [u8])]) -> Option<&'a [u8]> {
    for (key, val) in pop {
        if pop_known(key) || key.first() == Some(&b'_') {
            continue;
        }
        if py_float(val).is_none() {
            return Some(key);
        }
    }
    None
}

/// `read_province(..., flat=False)`, into the same bookkeeping as the scan.
#[allow(clippy::too_many_arguments)]
fn read_province(text_: &[u8], at: usize, pid: i64, pop_types: &[Vec<u8>], mob_types: &[Vec<u8>],
                 scan: &mut Scan, rules: &FxMap<Vec<u8>, PopulationRules>,
                 referenced: &FxSet<i64>, groups: &FxMap<i64, i64>) -> Result<(), String> {
    let mut owner: Option<&[u8]> = None;
    let mut controller: Option<&[u8]> = None;
    let mut colonial_flag = 0i64;
    let mut cores: Vec<&[u8]> = Vec::new();
    let mut pops: Vec<Pop> = Vec::new();
    let mut buildings: Vec<(&[u8], V)> = Vec::new();
    let mut tok = Tokens::new(text_, at);
    for (key, entry) in walk_entries(&mut tok, false) {
        match entry {
            Entry::Value(value) => {
                if key == b"owner" {
                    owner = Some(value);
                } else if key == b"controller" {
                    controller = Some(value);
                } else if key == b"core" {
                    if !cores.contains(&value) {
                        cores.push(value);
                    }
                } else if key == b"colonial" {
                    colonial_flag = to_int_text(value, 0)?;
                }
            }
            Entry::Block(block_at) => {
                if pop_types.iter().any(|t| t.as_slice() == key) {
                    let pop = read_pop(&mut Tokens::new(text_, block_at));
                    let field = |name: &[u8]| pop.iter().find(|(k, _)| *k == name).map(|(_, v)| *v);
                    pops.push(Pop {
                        kind: key,
                        id: field(b"id"),
                        size: field(b"size"),
                        culture: pop_culture(&pop),
                        money: field(b"money"),
                        con: field(b"con"),
                        mil: field(b"mil"),
                        literacy: field(b"literacy"),
                        life: field(b"life_needs"),
                    });
                } else if key == b"naval_base" || key == b"fort" || key == b"railroad" {
                    let block = parse_block(&mut Tokens::new(text_, block_at), &[]);
                    match buildings.iter_mut().find(|(k, _)| *k == key) {
                        Some(slot) => slot.1 = block,
                        None => buildings.push((key, block)),
                    }
                }
            }
        }
    }
    let level = |name: &[u8]| building_level(buildings.iter().find(|(k, _)| *k == name).map(|(_, v)| v));
    let parts = Parts {
        owner,
        controller,
        colonial_flag,
        cores,
        naval_base: level(b"naval_base"),
        fort: level(b"fort"),
        railroad: level(b"railroad"),
        pops,
    };
    accumulate(parts, pid, mob_types, scan, rules, referenced, groups);
    Ok(())
}

// ------------------------------------------------------------- a save

/// `looks_like_country_tag`, for latin-1 keys: three characters, the first
/// an upper-case letter, all letters or digits, not all digits.
pub fn looks_like_country_tag(key: &[u8]) -> bool {
    let alpha = |c: u8| crate::pyre::word(c) && c != b'_' && !c.is_ascii_digit()
        && !matches!(c, 0xb2 | 0xb3 | 0xb9 | 0xbc..=0xbe);
    let upper = |c: u8| c.is_ascii_uppercase() || matches!(c, 0xc0..=0xd6 | 0xd8..=0xde);
    let alnum = |c: u8| crate::pyre::word(c) && c != b'_';
    key.len() == 3 && alpha(key[0]) && upper(key[0]) && key.iter().all(|&c| alnum(c))
        && !key.iter().all(|&c| c.is_ascii_digit() || matches!(c, 0xb2 | 0xb3 | 0xb9))
}

/// What a walked save gives the record: its date and player, its countries
/// in file order, and its provinces folded into `scan`; and every top-level
/// block, as (key, content start, where it closes), for the wars, the market
/// and the great powers.
pub struct Walked<'a> {
    pub date: String,
    pub player: String,
    pub countries: Vec<Country>,
    pub blocks: Vec<(&'a [u8], usize, usize)>,
}

/// A whole save, walked: `_walk_top` and the two passes `analyze_save`
/// makes over its blocks. Err is what Python would raise out of, which is
/// handed back.
#[allow(clippy::too_many_arguments)]
pub fn read<'a>(text_: &'a [u8], pop_types: &[Vec<u8>], mob_types: &[Vec<u8>], tables: &Tables,
                scan: &mut Scan, population_groups: &FxMap<i64, i64>)
                -> Result<Walked<'a>, String> {
    let mut date: Option<&[u8]> = None;
    let mut player: Option<&[u8]> = None;
    let mut blocks = Vec::new();
    let mut tok = Tokens::new(text_, 0);
    for (key, entry) in walk_entries(&mut tok, true) {
        match entry {
            Entry::Block(at) => {
                let stop = block_end(text_, at).unwrap_or(text_.len());
                blocks.push((key, at, stop));
            }
            Entry::Value(v) => {
                if key == b"date" && date.is_none_or(|d| d.is_empty()) {
                    date = Some(v);
                } else if key == b"player" && player.is_none_or(|p| p.is_empty()) {
                    player = Some(v);
                }
            }
        }
    }
    let mut countries = Vec::new();
    let mut rules: FxMap<Vec<u8>, PopulationRules> = FxMap::default();
    let mut referenced = FxSet::default();
    for (key, at, _stop) in &blocks {
        if looks_like_country_tag(key) {
            let country = read_country(text_, *at, &text(key), tables)?;
            let rule = rules.entry(key.to_vec()).or_default();
            let bytes = |s: &str| s.chars().map(|c| c as u8).collect::<Vec<_>>();
            rule.accepted.extend(country.accepted_cultures.iter().map(|s| bytes(s)));
            for (name, value) in &country.scalars {
                if name == "primary_culture" && !value.is_empty() {
                    rule.accepted.insert(bytes(value));
                }
            }
            rule.colonial.extend(&country.colonial_provinces);
            referenced.extend(&country.regiment_pops);
            countries.push(country);
        }
    }
    for (key, at, _stop) in &blocks {
        if !key.is_empty() && key.iter().all(|c| c.is_ascii_digit()) {
            let pid = match crate::engine::modread::py_int(key) {
                Ok(Some(p)) => p,
                _ => return Err("a province number past 64 bits".into()),
            };
            read_province(text_, *at, pid, pop_types, mob_types, scan, &rules, &referenced,
                          population_groups)?;
        } else if !key.is_empty() && key.iter().all(|c| c.is_ascii_digit() || matches!(c, 0xb2 | 0xb3 | 0xb9)) {
            return Err("int() of a superscript province number".into());
        }
    }
    Ok(Walked {
        date: text(date.unwrap_or(b"")),
        player: text(player.unwrap_or(b"")),
        countries,
        blocks,
    })
}

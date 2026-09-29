// Country blocks, read the way `read_country` and `count_units` read them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The provinces were the bulk of the file; the countries are the bulk of what
// was left, and once these two are here the analyzer never reads a save at
// all. The awkward part is not the country block itself but what it contains:
// armies inside navies inside armies, states with a list of provinces, a
// technology block whose values are `{1 0.000}`. So this carries a small
// parser for the format, matching the Python one's conventions exactly --
// repeated keys collapse into a list, a block of bare values is a list, and
// bare values mixed with keys are kept under `_items`.

use crate::text::{find, unquote};
use crate::pickle::FxMap;

/// A token cursor over the save's own grammar: `"quoted"`, `{`, `}`, `=`, or
/// a run of anything else. The same rule as the Python `TOKEN_RE`.
pub struct Tokens<'a> {
    text: &'a str,
    bytes: &'a [u8],
    pos: usize,
    pushed: Option<&'a str>,
}

impl<'a> Tokens<'a> {
    pub fn new(text: &'a str, at: usize) -> Tokens<'a> {
        Tokens { text, bytes: text.as_bytes(), pos: at, pushed: None }
    }

    pub fn next(&mut self) -> Option<&'a str> {
        if let Some(t) = self.pushed.take() {
            return Some(t);
        }
        let b = self.bytes;
        while self.pos < b.len() && (b[self.pos] as char).is_whitespace() {
            self.pos += 1;
        }
        if self.pos >= b.len() {
            return None;
        }
        let start = self.pos;
        match b[start] {
            b'"' => {
                let mut i = start + 1;
                while i < b.len() && b[i] != b'"' {
                    i += 1;
                }
                self.pos = (i + 1).min(b.len());
                Some(&self.text[start..self.pos])
            }
            b'{' | b'}' | b'=' => {
                self.pos = start + 1;
                Some(&self.text[start..self.pos])
            }
            _ => {
                let mut i = start;
                while i < b.len() {
                    let c = b[i];
                    if (c as char).is_whitespace() || c == b'{' || c == b'}'
                        || c == b'='
                    {
                        break;
                    }
                    i += 1;
                }
                self.pos = i;
                Some(&self.text[start..i])
            }
        }
    }

    pub fn push(&mut self, t: &'a str) {
        self.pushed = Some(t);
    }

    /// Step over the block whose `{` has just been read.
    pub fn skip_to_close(&mut self) {
        let mut depth = 1;
        // Unused blocks need their boundaries, not tokens or allocations.
        // Quoting follows next(): a brace inside a quoted name is data.
        self.pushed = None;
        let mut quoted = false;
        let mut bare = false;
        while self.pos < self.bytes.len() && depth > 0 {
            let c = self.bytes[self.pos];
            if quoted {
                if c == b'"' { quoted = false; }
            } else {
                match c {
                    b'"' if !bare => quoted = true,
                    b'{' => { depth += 1; bare = false; }
                    b'}' => { depth -= 1; bare = false; }
                    b'=' => bare = false,
                    c if (c as char).is_whitespace() => bare = false,
                    _ => bare = true,
                }
            }
            self.pos += 1;
        }
    }
}

#[derive(Debug)]
pub enum Value {
    Text(String),
    /// A block of bare values, or the several values of a repeated key.
    List(Vec<Value>),
    Dict(Dict),
}

#[derive(Debug, Default)]
pub struct Dict {
    pub pairs: Vec<(String, Value)>,
    pub items: Vec<Value>,
}

impl Dict {
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.pairs.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    pub fn has(&self, key: &str) -> bool {
        self.pairs.iter().any(|(k, _)| k == key)
    }

    pub fn text(&self, key: &str) -> Option<&str> {
        match self.get(key) {
            Some(Value::Text(s)) => Some(s),
            _ => None,
        }
    }
}

/// Every dict directly under a value, whether it appeared once or many times.
pub fn sub_blocks(v: &Value) -> Vec<&Dict> {
    match v {
        Value::Dict(d) => vec![d],
        Value::List(items) => items
            .iter()
            .filter_map(|x| match x {
                Value::Dict(d) => Some(d),
                _ => None,
            })
            .collect(),
        _ => Vec::new(),
    }
}

/// Parse a block whose opening `{` has already been read.
///
/// Repeated keys collapse into a list under that key; a block made only of
/// bare values becomes a list; bare values alongside keys are kept as
/// `items`. That is what the Python does, and several readers downstream
/// depend on which of the three they get.
pub fn parse_block(tok: &mut Tokens, skip: &[&str]) -> Value {
    parse_fields(tok, skip, Shape::All)
}

/// Retain only fields used by the state and unit consumers. Keeping the
/// existing duplicate-key representation preserves malformed/reference
/// blocks and the ordering of repeated regiments, ships and embarked armies.
#[derive(Clone, Copy)]
enum Shape { All, State, Factory, Units, Regiment, Pop, Ship }

impl Shape {
    fn field(self, key: &str) -> Option<Shape> {
        use Shape::*;
        match (self, key) {
            (All, _) => Some(All),
            (State, "provinces" | "is_colonial") => Some(All),
            (State, "state_buildings") => Some(Factory),
            (Factory, "level") => Some(All),
            (Units, "location") => Some(All),
            (Units, "army" | "navy") => Some(Units),
            (Units, "regiment") => Some(Regiment),
            (Units, "ship") => Some(Ship),
            (Regiment, "type" | "strength") => Some(All),
            (Regiment, "pop") => Some(Pop),
            (Pop, "id") => Some(All),
            (Ship, "type" | "strength" | "experience") => Some(All),
            _ => None,
        }
    }
}

fn parse_fields(tok: &mut Tokens, skip: &[&str], shape: Shape) -> Value {
    let mut pairs: Vec<(String, Value)> = Vec::new();
    let mut items: Vec<Value> = Vec::new();
    let mut discarded_pair = false;
    loop {
        let t = match tok.next() {
            None => break,
            Some("}") => break,
            Some(t) => t,
        };
        if t == "{" {
            items.push(parse_fields(tok, skip, shape));
            continue;
        }
        if t == "=" {
            continue;
        }
        let nxt = tok.next();
        match nxt {
            Some("=") => {
                let key = unquote(t);
                let val_tok = tok.next();
                let child = match shape.field(key) {
                    Some(child) => child,
                    None => {
                        discarded_pair |= val_tok.is_some()
                            && !(val_tok == Some("{") && skip.contains(&key));
                        if val_tok == Some("{") { tok.skip_to_close(); }
                        continue;
                    }
                };
                let val = match val_tok {
                    Some("{") => {
                        if skip.contains(&key) {
                            tok.skip_to_close();
                            continue;
                        }
                        parse_fields(tok, skip, child)
                    }
                    None => break,
                    Some(v) => Value::Text(unquote(v).to_string()),
                };
                match pairs.iter_mut().find(|(k, _)| k == key) {
                    Some(slot) => {
                        // A repeat: the pair becomes the list of both.
                        let held = std::mem::replace(&mut slot.1,
                                                     Value::List(Vec::new()));
                        match held {
                            Value::List(mut many) => {
                                many.push(val);
                                slot.1 = Value::List(many);
                            }
                            one => slot.1 = Value::List(vec![one, val]),
                        }
                    }
                    None => pairs.push((key.to_string(), val)),
                }
            }
            other => {
                items.push(Value::Text(unquote(t).to_string()));
                if let Some(o) = other {
                    tok.push(o);
                }
            }
        }
    }
    if !items.is_empty() && pairs.is_empty() && !discarded_pair {
        return Value::List(items);
    }
    Value::Dict(Dict { pairs, items })
}

fn to_float(s: &str) -> f64 {
    s.trim().parse::<f64>().unwrap_or(0.0)
}

fn to_float_or(s: Option<&str>, fallback: f64) -> f64 {
    match s {
        Some(v) => v.trim().parse::<f64>().unwrap_or(fallback),
        None => fallback,
    }
}

fn to_int(s: &str) -> i64 {
    let v = s.trim().parse::<f64>().unwrap_or(0.0);
    if v.is_finite() { v.trunc() as i64 } else { 0 }
}

fn to_int_or(s: Option<&str>, fallback: i64) -> i64 {
    match s {
        Some(v) => {
            let f = v.trim().parse::<f64>();
            match f {
                Ok(x) if x.is_finite() => x.trunc() as i64,
                _ => fallback,
            }
        }
        None => fallback,
    }
}

/// Everything a country block says, in the analyzer's own terms.
#[derive(Default)]
pub struct Country {
    pub tag: String,
    pub scalars: Vec<(String, String)>,
    pub numerics: Vec<(String, f64)>,
    pub is_mobilized: i64,
    pub human: bool,
    pub reforms: Vec<(String, String)>,
    pub accepted_cultures: Vec<String>,
    pub country_flags: Vec<String>,
    pub modifiers: Vec<String>,
    pub goods_supply: Vec<(String, f64)>,
    pub invention_ids: Vec<i64>,
    pub mobilizing: i64,
    pub states: i64,
    pub province_state: Vec<(i64, i64)>,
    pub colonial_provinces: Vec<i64>,
    pub colonial_level: Vec<(i64, i64)>,
    pub factory_count: i64,
    pub factory_levels: i64,
    pub techs: i64,
    pub tech_list: Vec<String>,
    pub army_techs: i64,
    pub navy_techs: i64,
    // from the units
    pub brigades: i64,
    pub armies: i64,
    pub navies: i64,
    pub ships: i64,
    pub regiment_pops: Vec<i64>,
    pub regiments_by_type: Vec<(String, i64)>,
    pub ships_by_type: Vec<(String, i64)>,
    pub ship_crew: Vec<(String, f64)>,
    pub units_at: Vec<(i64, Vec<(String, i64)>)>,
    pub men_at: Vec<(i64, Vec<(String, i64)>)>,
}

/// An ordered counter, so what comes back is in the order the file gave it.
#[derive(Default)]
struct Tally {
    order: Vec<String>,
    index: FxMap<String, usize>,
    total: Vec<f64>,
}

impl Tally {
    fn add(&mut self, name: &str, by: f64) {
        match self.index.get(name) {
            Some(&i) => self.total[i] += by,
            None => {
                self.index.insert(name.to_string(), self.order.len());
                self.order.push(name.to_string());
                self.total.push(by);
            }
        }
    }
    fn ints(&self) -> Vec<(String, i64)> {
        self.order.iter().cloned()
            .zip(self.total.iter().map(|v| *v as i64)).collect()
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
    at: Vec<(i64, Tally)>,
    men: Vec<(i64, Tally)>,
}

impl Units {
    fn at_mut(&mut self, where_: i64) -> usize {
        match self.at.iter().position(|(p, _)| *p == where_) {
            Some(i) => i,
            None => {
                self.at.push((where_, Tally::default()));
                self.men.push((where_, Tally::default()));
                self.at.len() - 1
            }
        }
    }
}

/// Tally armies, navies, regiments and ships anywhere inside a unit block.
///
/// Recursive on purpose: an army loaded onto transports is stored as an
/// `army` block inside the `navy` carrying it, so reading army->regiment at
/// one fixed depth silently drops every embarked brigade.
fn count_units(node: &Dict, out: &mut Units, where_: Option<i64>) {
    for (key, value) in &node.pairs {
        if key.starts_with('_') {
            continue;
        }
        if key == "regiment" {
            for reg in sub_blocks(value) {
                out.brigades += 1;
                let pop_id = match reg.get("pop") {
                    Some(Value::Dict(d)) => to_int_or(d.text("id"), -1),
                    _ => -1,
                };
                out.regiment_pops.push(pop_id);
                // A unit type is an unquoted name; a bare id reference
                // carries a number instead, and a number is not a name.
                let raw = reg.text("type").unwrap_or("");
                let rtype = if raw.trim().parse::<f64>().is_ok() { "" } else { raw };
                let rtype = if rtype.is_empty() { "unknown" } else { rtype };
                out.by_type.add(rtype, 1.0);
                if let Some(w) = where_ {
                    let i = out.at_mut(w);
                    out.at[i].1.add(rtype, 1.0);
                    let strength = to_float(reg.text("strength").unwrap_or(""));
                    out.men[i].1.add(rtype, (strength * 1000.0).round());
                }
            }
        } else if key == "ship" {
            for ship in sub_blocks(value) {
                out.ships += 1;
                let kind = ship.text("type").unwrap_or("unknown");
                out.ships_by_type.add(kind, 1.0);
                // Both are percentages. Strength scales the damage a hull
                // deals; experience is subtracted from the damage it takes,
                // which leaves it as a divisor on its owner's side.
                let strength = to_float_or(ship.text("strength"), 100.0) / 100.0;
                let experience = to_float_or(ship.text("experience"), 0.0) / 100.0;
                let experience = experience.clamp(0.0, 0.95);
                out.ship_crew.add(kind, strength.max(0.0) / (1.0 - experience));
            }
        } else if key == "army" || key == "navy" {
            let blocks = sub_blocks(value);
            if key == "army" {
                out.armies += blocks.len() as i64;
            } else {
                out.navies += blocks.len() as i64;
            }
            for block in blocks {
                // An embarked army has no location of its own, so it
                // inherits the navy's.
                let here = to_int_or(block.text("location"), -1);
                count_units(block, out, if here > 0 { Some(here) } else { where_ });
            }
        }
    }
}

pub struct Tables<'a> {
    pub army_techs: &'a [String],
    pub navy_techs: &'a [String],
    pub reform_keys: &'a [String],
}

const STATE_SKIP: &[&str] = &["employment", "stockpile", "id"];
const UNIT_SKIP: &[&str] = &["id", "leader"];

const SCALARS: &[(&str, &str)] = &[
    ("nationalvalue", "nationalvalue"),
    ("primary_culture", "primary_culture"),
    ("civilized", "civilized"),
    ("government", "government"),
    ("capital", "capital"),
];
const NUMERICS: &[(&str, &str)] = &[
    ("prestige", "prestige"),
    ("badboy", "infamy"),
    ("money", "treasury"),
    ("tax_base", "tax_base"),
    ("war_exhaustion", "war_exhaustion"),
    ("revanchism", "revanchism"),
    ("plurality", "plurality"),
    ("research_points", "research_points"),
    ("ruling_party", "ruling_party"),
];

/// One country block.
pub fn read_country(text: &str, at: usize, stop: usize, tag: &str,
                    tables: &Tables) -> Country {
    let mut out = Country::default();
    out.tag = tag.to_string();
    let mut units = Units::default();
    let bytes = text.as_bytes();

    // The same one-tab entries the Python scans: `\n\t<key>=<value>`, where
    // a value starting with `{` means the block that follows.
    let mut i = at;
    while i < stop {
        let nl = match find(bytes, b"\n\t", i, stop) {
            None => break,
            Some(n) => n,
        };
        let key_start = nl + 2;
        let mut p = key_start;
        while p < stop && bytes[p] != b'=' {
            let c = bytes[p];
            if (c as char).is_whitespace() || c == b'{' || c == b'}' || c == b'"' {
                break;
            }
            p += 1;
        }
        if p >= stop || bytes[p] != b'=' {
            i = nl + 2;
            continue;
        }
        let key = &text[key_start..p];
        let line_end = match bytes[p..stop].iter().position(|&c| c == b'\n') {
            Some(k) => p + k,
            None => stop,
        };
        let value = text[p + 1..line_end].trim();
        i = line_end;

        if !value.is_empty() && !value.starts_with('{') {
            let clean = unquote(value);
            if key == "mobilize" {
                out.is_mobilized = if clean.eq_ignore_ascii_case("yes") { 1 } else { 0 };
            } else if key == "human" {
                out.human = clean.eq_ignore_ascii_case("yes");
            } else if tables.reform_keys.iter().any(|r| r == key) {
                out.reforms.push((key.to_string(), clean.to_string()));
            } else if let Some((_, name)) = SCALARS.iter().find(|(k, _)| *k == key) {
                // Unquoted: the Python's entry scanner strips the quotes
                // before the value ever reaches this decision, so a primary
                // culture is `dutch` and not `"dutch"`.
                out.scalars.push((name.to_string(), clean.to_string()));
            } else if let Some((_, name)) = NUMERICS.iter().find(|(k, _)| *k == key) {
                out.numerics.push((name.to_string(), to_float(clean)));
            }
            continue;
        }

        // A block: find its `{` and read it only if something wants it.
        let brace = match find(bytes, b"{", p, stop) {
            None => continue,
            Some(b) => b,
        };
        match key {
            "army" | "navy" => {
                let mut tok = Tokens::new(text, brace + 1);
                let block = parse_fields(&mut tok, UNIT_SKIP, Shape::Units);
                i = tok.pos;
                let mut wrapper = Dict::default();
                wrapper.pairs.push((key.to_string(), block));
                count_units(&wrapper, &mut units, None);
            }
            "culture" => {
                let mut tok = Tokens::new(text, brace + 1);
                match parse_block(&mut tok, &[]) {
                    Value::List(items) => {
                        for v in items {
                            if let Value::Text(s) = v {
                                out.accepted_cultures.push(s);
                            }
                        }
                    }
                    Value::Dict(d) => {
                        for v in d.items {
                            if let Value::Text(s) = v {
                                out.accepted_cultures.push(s);
                            }
                        }
                    }
                    _ => {}
                }
            }
            "flags" => {
                let mut tok = Tokens::new(text, brace + 1);
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    for (k, v) in &d.pairs {
                        if k.starts_with('_') {
                            continue;
                        }
                        if let Value::Text(s) = v {
                            if s.eq_ignore_ascii_case("yes") {
                                out.country_flags.push(k.clone());
                            }
                        }
                    }
                }
            }
            "modifier" => {
                let mut tok = Tokens::new(text, brace + 1);
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    if let Some(Value::Text(s)) = d.get("modifier") {
                        out.modifiers.push(s.clone());
                    }
                }
            }
            "saved_country_supply" => {
                let mut tok = Tokens::new(text, brace + 1);
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    for (g, v) in &d.pairs {
                        if g.starts_with('_') {
                            continue;
                        }
                        if let Value::Text(s) = v {
                            let n = to_float(s);
                            if n > 0.0 {
                                out.goods_supply.push((g.clone(), n));
                            }
                        }
                    }
                }
            }
            "active_inventions" => {
                let mut tok = Tokens::new(text, brace + 1);
                let block = parse_block(&mut tok, &[]);
                let ids: Vec<&Value> = match &block {
                    Value::List(items) => items.iter().collect(),
                    Value::Dict(d) => d.items.iter().collect(),
                    _ => Vec::new(),
                };
                out.invention_ids = ids.iter().map(|v| match v {
                    Value::Text(s) => to_int_or(Some(s), -1),
                    _ => -1,
                }).collect();
            }
            "scheduled_mobilization" => {
                let mut tok = Tokens::new(text, brace + 1);
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    let spawned = d.text("spawned").unwrap_or("no");
                    if !spawned.eq_ignore_ascii_case("yes") {
                        out.mobilizing += 1;
                    }
                } else {
                    out.mobilizing += 1;
                }
            }
            "state" => {
                let mut tok = Tokens::new(text, brace + 1);
                let block = parse_fields(&mut tok, STATE_SKIP, Shape::State);
                i = tok.pos;
                if let Value::Dict(d) = block {
                    out.states += 1;
                    let ordinal = out.states;
                    let ids: Vec<i64> = match d.get("provinces") {
                        Some(Value::List(items)) => items.iter().map(|v| match v {
                            Value::Text(s) => to_int_or(Some(s), -1),
                            _ => -1,
                        }).collect(),
                        Some(Value::Dict(inner)) => inner.items.iter().map(|v| match v {
                            Value::Text(s) => to_int_or(Some(s), -1),
                            _ => -1,
                        }).collect(),
                        _ => Vec::new(),
                    };
                    // `is_colonial=1` is a protectorate and `=2` a colony;
                    // both sit outside the stated states, and the level
                    // matters to the brigade cap.
                    let colonial = d.has("is_colonial");
                    let level = if colonial {
                        to_int_or(d.text("is_colonial"), 0)
                    } else { 0 };
                    for pid in ids {
                        out.province_state.push((pid, ordinal));
                        if colonial {
                            out.colonial_provinces.push(pid);
                            out.colonial_level.push((pid, level));
                        }
                    }
                    if let Some(v) = d.get("state_buildings") {
                        for bld in sub_blocks(v) {
                            out.factory_count += 1;
                            out.factory_levels += to_int_or(bld.text("level"), 1);
                        }
                    }
                }
            }
            "technology" => {
                let mut tok = Tokens::new(text, brace + 1);
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    for (tech, tval) in &d.pairs {
                        if tech.starts_with('_') {
                            continue;
                        }
                        let first = match tval {
                            Value::List(items) => match items.first() {
                                Some(Value::Text(s)) => s.as_str(),
                                _ => "",
                            },
                            Value::Dict(inner) => match inner.items.first() {
                                Some(Value::Text(s)) => s.as_str(),
                                _ => "",
                            },
                            Value::Text(s) => s.as_str(),
                        };
                        if to_int(first) == 1 {
                            out.techs += 1;
                            out.tech_list.push(tech.clone());
                            if tables.army_techs.iter().any(|t| t == tech) {
                                out.army_techs += 1;
                            } else if tables.navy_techs.iter().any(|t| t == tech) {
                                out.navy_techs += 1;
                            }
                        }
                    }
                }
            }
            _ => {}
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
    out.units_at = units.at.iter().map(|(p, t)| (*p, t.ints())).collect();
    out.men_at = units.men.iter().map(|(p, t)| (*p, t.ints())).collect();
    out
}

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
//
// It reads the save's own bytes, which are latin-1: a byte is a character.
// What it parses borrows from them, and only what a country keeps -- a
// culture, a flag, a technology's name -- is decoded into a `String`. It used
// to decode every country block whole before reading a word of it.

use crate::text::{find, latin1, unquote_b};
use crate::fx::FxMap;

/// Whether a byte of the save is whitespace, as Python's `\s` judged the
/// latin-1 text it decoded -- the ASCII spaces, NEL and the no-break space --
/// and as `str::trim` does too. A latin-1 byte is a whole character, so
/// there is no second byte of anything to mistake for one.
pub(crate) fn is_space(c: u8) -> bool {
    matches!(c, 0x09..=0x0d | 0x20 | 0x85 | 0xa0)
}

/// `str::trim` on the decoded text, done on the bytes.
fn trim(s: &[u8]) -> &[u8] {
    let mut a = 0;
    let mut b = s.len();
    while a < b && is_space(s[a]) { a += 1; }
    while b > a && is_space(s[b - 1]) { b -= 1; }
    &s[a..b]
}

/// Whether latin-1 bytes are the same text as a decoded name.
fn eq_latin1(b: &[u8], s: &str) -> bool {
    if b.is_ascii() {
        return b == s.as_bytes();
    }
    let mut chars = s.chars();
    b.iter().all(|&c| chars.next() == Some(c as char)) && chars.next().is_none()
}

/// A token cursor over the save's own grammar: `"quoted"`, `{`, `}`, `=`, or
/// a run of anything else. The same rule as the Python `TOKEN_RE`.
pub struct Tokens<'a> {
    bytes: &'a [u8],
    pos: usize,
    pushed: Option<&'a [u8]>,
}

impl<'a> Tokens<'a> {
    pub fn new(bytes: &'a [u8], at: usize) -> Tokens<'a> {
        Tokens { bytes, pos: at, pushed: None }
    }

    pub fn next(&mut self) -> Option<&'a [u8]> {
        if let Some(t) = self.pushed.take() {
            return Some(t);
        }
        let b = self.bytes;
        while self.pos < b.len() && is_space(b[self.pos]) {
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
                Some(&b[start..self.pos])
            }
            b'{' | b'}' | b'=' => {
                self.pos = start + 1;
                Some(&b[start..self.pos])
            }
            _ => {
                let mut i = start;
                while i < b.len() {
                    let c = b[i];
                    if is_space(c) || c == b'{' || c == b'}' || c == b'=' {
                        break;
                    }
                    i += 1;
                }
                self.pos = i;
                Some(&b[start..i])
            }
        }
    }

    pub fn push(&mut self, t: &'a [u8]) {
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
                    // NEL and the no-break space leave a word open, as
                    // they did when this ran over the block re-encoded as
                    // UTF-8 and took their second byte for a letter: a
                    // quote straight after one does not open a name here,
                    // though `next()` would open one. Kept as it was.
                    _ if is_space(c) && c < 0x80 => bare = false,
                    _ => bare = true,
                }
            }
            self.pos += 1;
        }
    }
}

/// What a block holds, borrowed from the save's bytes.
#[derive(Debug)]
pub enum Value<'a> {
    Text(&'a [u8]),
    /// A block of bare values, or the several values of a repeated key.
    List(Vec<Value<'a>>),
    Dict(Dict<'a>),
}

#[derive(Debug, Default)]
pub struct Dict<'a> {
    pub pairs: Vec<(&'a [u8], Value<'a>)>,
    pub items: Vec<Value<'a>>,
}

impl<'a> Dict<'a> {
    pub fn get(&self, key: &[u8]) -> Option<&Value<'a>> {
        self.pairs.iter().find(|(k, _)| *k == key).map(|(_, v)| v)
    }

    pub fn has(&self, key: &[u8]) -> bool {
        self.pairs.iter().any(|(k, _)| *k == key)
    }

    pub fn text(&self, key: &[u8]) -> Option<&'a [u8]> {
        match self.get(key) {
            Some(Value::Text(s)) => Some(s),
            _ => None,
        }
    }
}

/// Every dict directly under a value, whether it appeared once or many times.
pub fn sub_blocks<'v, 'a>(v: &'v Value<'a>) -> Vec<&'v Dict<'a>> {
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
pub fn parse_block<'a>(tok: &mut Tokens<'a>, skip: &[&[u8]]) -> Value<'a> {
    parse_fields(tok, skip, Shape::All)
}

/// Retain only fields used by the state and unit consumers. Keeping the
/// existing duplicate-key representation preserves malformed/reference
/// blocks and the ordering of repeated regiments, ships and embarked armies.
#[derive(Clone, Copy)]
enum Shape { All, State, Factory, Units, Regiment, Pop, Ship }

impl Shape {
    fn field(self, key: &[u8]) -> Option<Shape> {
        use Shape::*;
        match (self, key) {
            (All, _) => Some(All),
            (State, b"provinces" | b"is_colonial") => Some(All),
            (State, b"state_buildings") => Some(Factory),
            (Factory, b"level") => Some(All),
            (Units, b"location") => Some(All),
            (Units, b"army" | b"navy") => Some(Units),
            (Units, b"regiment") => Some(Regiment),
            (Units, b"ship") => Some(Ship),
            (Regiment, b"type" | b"strength") => Some(All),
            (Regiment, b"pop") => Some(Pop),
            (Pop, b"id") => Some(All),
            (Ship, b"type" | b"strength" | b"experience") => Some(All),
            _ => None,
        }
    }
}

fn parse_fields<'a>(tok: &mut Tokens<'a>, skip: &[&[u8]], shape: Shape) -> Value<'a> {
    let mut pairs: Vec<(&'a [u8], Value<'a>)> = Vec::new();
    let mut items: Vec<Value<'a>> = Vec::new();
    let mut discarded_pair = false;
    loop {
        let t = match tok.next() {
            None => break,
            Some(b"}") => break,
            Some(t) => t,
        };
        if t == b"{" {
            items.push(parse_fields(tok, skip, shape));
            continue;
        }
        if t == b"=" {
            continue;
        }
        let nxt = tok.next();
        match nxt {
            Some(b"=") => {
                let key = unquote_b(t);
                let val_tok = tok.next();
                let child = match shape.field(key) {
                    Some(child) => child,
                    None => {
                        discarded_pair |= val_tok.is_some()
                            && !(val_tok == Some(b"{") && skip.contains(&key));
                        if val_tok == Some(b"{") { tok.skip_to_close(); }
                        continue;
                    }
                };
                let val = match val_tok {
                    Some(b"{") => {
                        if skip.contains(&key) {
                            tok.skip_to_close();
                            continue;
                        }
                        parse_fields(tok, skip, child)
                    }
                    None => break,
                    Some(v) => Value::Text(unquote_b(v)),
                };
                match pairs.iter_mut().find(|(k, _)| *k == key) {
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
                    None => pairs.push((key, val)),
                }
            }
            other => {
                items.push(Value::Text(unquote_b(t)));
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

/// `float(s)` as `str::parse` reads the decoded text, trimmed: None where it
/// fails. A number is ASCII, so bytes that are not cannot parse either way.
fn parse_float(s: &[u8]) -> Option<f64> {
    std::str::from_utf8(trim(s)).ok()?.parse::<f64>().ok()
}

fn to_float(s: &[u8]) -> f64 {
    parse_float(s).unwrap_or(0.0)
}

fn to_float_or(s: Option<&[u8]>, fallback: f64) -> f64 {
    match s {
        Some(v) => parse_float(v).unwrap_or(fallback),
        None => fallback,
    }
}

fn to_int(s: &[u8]) -> i64 {
    let v = parse_float(s).unwrap_or(0.0);
    if v.is_finite() { v.trunc() as i64 } else { 0 }
}

fn to_int_or(s: Option<&[u8]>, fallback: i64) -> i64 {
    match s {
        Some(v) => match parse_float(v) {
            Some(x) if x.is_finite() => x.trunc() as i64,
            _ => fallback,
        },
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
/// It counts the save's own bytes and decodes each name once, at the end.
#[derive(Default)]
struct Tally<'a> {
    order: Vec<&'a [u8]>,
    index: FxMap<&'a [u8], usize>,
    total: Vec<f64>,
}

impl<'a> Tally<'a> {
    fn add(&mut self, name: &'a [u8], by: f64) {
        match self.index.get(name) {
            Some(&i) => self.total[i] += by,
            None => {
                self.index.insert(name, self.order.len());
                self.order.push(name);
                self.total.push(by);
            }
        }
    }
    fn ints(&self) -> Vec<(String, i64)> {
        self.order.iter().map(|n| latin1(n))
            .zip(self.total.iter().map(|v| *v as i64)).collect()
    }
    fn floats(&self) -> Vec<(String, f64)> {
        self.order.iter().map(|n| latin1(n)).zip(self.total.iter().copied()).collect()
    }
}

#[derive(Default)]
struct Units<'a> {
    brigades: i64,
    armies: i64,
    navies: i64,
    ships: i64,
    regiment_pops: Vec<i64>,
    by_type: Tally<'a>,
    ships_by_type: Tally<'a>,
    ship_crew: Tally<'a>,
    at: Vec<(i64, Tally<'a>)>,
    men: Vec<(i64, Tally<'a>)>,
}

impl<'a> Units<'a> {
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
fn count_units<'a>(node: &Dict<'a>, out: &mut Units<'a>, where_: Option<i64>) {
    for (key, value) in &node.pairs {
        let key = *key;
        if key.first() == Some(&b'_') {
            continue;
        }
        if key == b"regiment" {
            for reg in sub_blocks(value) {
                out.brigades += 1;
                let pop_id = match reg.get(b"pop") {
                    Some(Value::Dict(d)) => to_int_or(d.text(b"id"), -1),
                    _ => -1,
                };
                out.regiment_pops.push(pop_id);
                // A unit type is an unquoted name; a bare id reference
                // carries a number instead, and a number is not a name.
                let raw = reg.text(b"type").unwrap_or(b"");
                let rtype: &[u8] = if parse_float(raw).is_some() { b"" } else { raw };
                let rtype: &[u8] = if rtype.is_empty() { b"unknown" } else { rtype };
                out.by_type.add(rtype, 1.0);
                if let Some(w) = where_ {
                    let i = out.at_mut(w);
                    out.at[i].1.add(rtype, 1.0);
                    let strength = to_float(reg.text(b"strength").unwrap_or(b""));
                    out.men[i].1.add(rtype, (strength * 1000.0).round_ties_even());
                }
            }
        } else if key == b"ship" {
            for ship in sub_blocks(value) {
                out.ships += 1;
                let kind = ship.text(b"type").unwrap_or(b"unknown");
                out.ships_by_type.add(kind, 1.0);
                // Both are percentages. Strength scales the damage a hull
                // deals; experience is subtracted from the damage it takes,
                // which leaves it as a divisor on its owner's side.
                let strength = to_float_or(ship.text(b"strength"), 100.0) / 100.0;
                let experience = to_float_or(ship.text(b"experience"), 0.0) / 100.0;
                let experience = experience.clamp(0.0, 0.95);
                out.ship_crew.add(kind, strength.max(0.0) / (1.0 - experience));
            }
        } else if key == b"army" || key == b"navy" {
            let blocks = sub_blocks(value);
            if key == b"army" {
                out.armies += blocks.len() as i64;
            } else {
                out.navies += blocks.len() as i64;
            }
            for block in blocks {
                // An embarked army has no location of its own, so it
                // inherits the navy's.
                let here = to_int_or(block.text(b"location"), -1);
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

const STATE_SKIP: &[&[u8]] = &[b"employment", b"stockpile", b"id"];
const UNIT_SKIP: &[&[u8]] = &[b"id", b"leader"];

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

/// The bare values of a block, whether it came back a list or kept them
/// beside keys.
fn bare_values<'v, 'a>(block: &'v Value<'a>) -> &'v [Value<'a>] {
    match block {
        Value::List(items) => items,
        Value::Dict(d) => &d.items,
        _ => &[],
    }
}

/// One country block: the save's bytes from `at` to `stop`.
pub fn read_country(bytes: &[u8], at: usize, stop: usize, tag: &str,
                    tables: &Tables) -> Country {
    let mut out = Country::default();
    out.tag = tag.to_string();
    let mut units = Units::default();

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
            if is_space(c) || c == b'{' || c == b'}' || c == b'"' {
                break;
            }
            p += 1;
        }
        if p >= stop || bytes[p] != b'=' {
            i = nl + 2;
            continue;
        }
        let key = &bytes[key_start..p];
        let line_end = match bytes[p..stop].iter().position(|&c| c == b'\n') {
            Some(k) => p + k,
            None => stop,
        };
        let value = trim(&bytes[p + 1..line_end]);
        i = line_end;

        if !value.is_empty() && value[0] != b'{' {
            let clean = unquote_b(value);
            if key == b"mobilize" {
                out.is_mobilized = if clean.eq_ignore_ascii_case(b"yes") { 1 } else { 0 };
            } else if key == b"human" {
                out.human = clean.eq_ignore_ascii_case(b"yes");
            } else if tables.reform_keys.iter().any(|r| eq_latin1(key, r)) {
                out.reforms.push((latin1(key), latin1(clean)));
            } else if let Some((_, name)) = SCALARS.iter().find(|(k, _)| *k == key) {
                // Unquoted: the Python's entry scanner strips the quotes
                // before the value ever reaches this decision, so a primary
                // culture is `dutch` and not `"dutch"`.
                out.scalars.push((name.to_string(), latin1(clean)));
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
        // A block runs to the end of the country at most, as it did when
        // the country was a copy of its own.
        let mut tok = Tokens::new(&bytes[..stop], brace + 1);
        match key {
            b"army" | b"navy" => {
                let block = parse_fields(&mut tok, UNIT_SKIP, Shape::Units);
                i = tok.pos;
                let mut wrapper = Dict::default();
                wrapper.pairs.push((key, block));
                count_units(&wrapper, &mut units, None);
            }
            b"culture" => {
                for v in bare_values(&parse_block(&mut tok, &[])) {
                    if let Value::Text(s) = v {
                        out.accepted_cultures.push(latin1(s));
                    }
                }
            }
            b"flags" => {
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    for (k, v) in &d.pairs {
                        if k.first() == Some(&b'_') {
                            continue;
                        }
                        if let Value::Text(s) = v {
                            if s.eq_ignore_ascii_case(b"yes") {
                                out.country_flags.push(latin1(k));
                            }
                        }
                    }
                }
            }
            b"modifier" => {
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    if let Some(Value::Text(s)) = d.get(b"modifier") {
                        out.modifiers.push(latin1(s));
                    }
                }
            }
            b"saved_country_supply" => {
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    for (g, v) in &d.pairs {
                        if g.first() == Some(&b'_') {
                            continue;
                        }
                        if let Value::Text(s) = v {
                            let n = to_float(s);
                            if n > 0.0 {
                                out.goods_supply.push((latin1(g), n));
                            }
                        }
                    }
                }
            }
            b"active_inventions" => {
                let block = parse_block(&mut tok, &[]);
                out.invention_ids = bare_values(&block).iter().map(|v| match v {
                    Value::Text(s) => to_int_or(Some(s), -1),
                    _ => -1,
                }).collect();
            }
            b"scheduled_mobilization" => {
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    let spawned = d.text(b"spawned").unwrap_or(b"no");
                    if !spawned.eq_ignore_ascii_case(b"yes") {
                        out.mobilizing += 1;
                    }
                } else {
                    out.mobilizing += 1;
                }
            }
            b"state" => {
                let block = parse_fields(&mut tok, STATE_SKIP, Shape::State);
                i = tok.pos;
                if let Value::Dict(d) = block {
                    out.states += 1;
                    let ordinal = out.states;
                    let ids: Vec<i64> = match d.get(b"provinces") {
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
                    let colonial = d.has(b"is_colonial");
                    let level = if colonial {
                        to_int_or(d.text(b"is_colonial"), 0)
                    } else { 0 };
                    for pid in ids {
                        out.province_state.push((pid, ordinal));
                        if colonial {
                            out.colonial_provinces.push(pid);
                            out.colonial_level.push((pid, level));
                        }
                    }
                    if let Some(v) = d.get(b"state_buildings") {
                        for bld in sub_blocks(v) {
                            out.factory_count += 1;
                            out.factory_levels += to_int_or(bld.text(b"level"), 1);
                        }
                    }
                }
            }
            b"technology" => {
                if let Value::Dict(d) = parse_block(&mut tok, &[]) {
                    for (tech, tval) in &d.pairs {
                        if tech.first() == Some(&b'_') {
                            continue;
                        }
                        let first: &[u8] = match tval {
                            Value::List(items) => match items.first() {
                                Some(Value::Text(s)) => s,
                                _ => b"",
                            },
                            Value::Dict(inner) => match inner.items.first() {
                                Some(Value::Text(s)) => s,
                                _ => b"",
                            },
                            Value::Text(s) => s,
                        };
                        if to_int(first) == 1 {
                            out.techs += 1;
                            out.tech_list.push(latin1(tech));
                            if tables.army_techs.iter().any(|t| eq_latin1(tech, t)) {
                                out.army_techs += 1;
                            } else if tables.navy_techs.iter().any(|t| eq_latin1(tech, t)) {
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

#[cfg(test)]
mod tests {
    use super::*;

    /// `Å` and `à` are the bytes `C5` and `E0`, and `A0` is a no-break
    /// space: a bare word holding one of the first two is read whole, and
    /// the third ends a word, as Python reads the decoded text.
    #[test]
    fn a_bare_word_past_ascii_is_one_token() {
        let text = b"\xc5land_flag=yes \xe0x\xa0y }";
        let mut tok = Tokens::new(text, 0);
        let got: Vec<&[u8]> = std::iter::from_fn(|| tok.next()).collect();
        let want: [&[u8]; 6] = [b"\xc5land_flag", b"=", b"yes", b"\xe0x", b"y", b"}"];
        assert_eq!(got, want);
    }

    /// A name is matched against the decoded tables by its characters, not
    /// its bytes: `C3 A9` is `Ã©` in a save, never `é`.
    #[test]
    fn latin1_names_match_by_character() {
        assert!(eq_latin1(b"army_tech", "army_tech"));
        assert!(eq_latin1(b"\xe9cole", "\u{e9}cole"));
        assert!(!eq_latin1(b"\xc3\xa9cole", "\u{e9}cole"));
        assert!(!eq_latin1(b"\xe9cole", "\u{e9}col"));
        assert!(!eq_latin1(b"army", "army_tech"));
    }

    /// A skipped block reads a quote straight after a no-break space as it
    /// did on the UTF-8 copy -- not as opening a name, so the brace after it
    /// closes the block -- and after an ASCII space as opening one.
    #[test]
    fn a_skipped_block_reads_a_no_break_space_as_it_did() {
        let mut tok = Tokens::new(b"a=\xa0\"}\" } after", 0);
        tok.skip_to_close();
        assert_eq!(tok.next(), Some(&b"\" } after"[..]));
        let mut tok = Tokens::new(b"a= \"}\" } after", 0);
        tok.skip_to_close();
        assert_eq!(tok.next(), Some(&b"after"[..]));
    }
}

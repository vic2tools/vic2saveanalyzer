// The wars, the world market and the great power list, read as Python reads them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// These three were the last of a save the analyzer still read in Python, and
// in `--record` mode they are read here. They go through the generic tree
// Python's `v2parse.parse_span` builds and then `readwar.read_war` and
// `readsave.read_worldmarket`, so this carries its own copy of both halves,
// rule for rule, rather than the country reader's parser, which differs on
// purpose in two places: it folds a repeated key into an earlier list of
// bare values, where Python keeps the two apart, and its whitespace is
// Rust's rather than Python's `\s`.
//
// Where Python would do something no save should make it do -- call `str()`
// on a block where a name belongs and keep the repr, turn an infinite number
// into an int and raise -- this refuses the save instead (`Err`), and the
// analyzer reads it the other way, which does exactly what it always did.

use crate::pickle::{text, Key, OMap, P};

pub type R<T> = Result<T, ()>;

/// Python's `str.isspace()` for a character that is one latin-1 byte, which
/// is what `\s` in `TOKEN_RE` matches.
pub fn py_space(c: u8) -> bool {
    matches!(c, 0x09..=0x0d | 0x1c..=0x1f | 0x20 | 0x85 | 0xa0)
}

/// `TOKEN_RE.findall(text)`: `"[^"]*"|[{}=]|[^\s{}=]+`.
pub fn tokens(b: &[u8]) -> Vec<&[u8]> {
    let mut out = Vec::with_capacity(b.len() / 6);
    let mut i = 0;
    let n = b.len();
    while i < n {
        let c = b[i];
        if py_space(c) {
            i += 1;
            continue;
        }
        if c == b'"' {
            // A quote that closes anywhere later is one token; one that never
            // closes is the start of a bare word like any other character.
            if let Some(off) = b[i + 1..].iter().position(|&x| x == b'"') {
                let end = i + 1 + off + 1;
                out.push(&b[i..end]);
                i = end;
                continue;
            }
        }
        if c == b'{' || c == b'}' || c == b'=' {
            out.push(&b[i..i + 1]);
            i += 1;
            continue;
        }
        let start = i;
        while i < n {
            let x = b[i];
            if py_space(x) || x == b'{' || x == b'}' || x == b'=' {
                break;
            }
            i += 1;
        }
        out.push(&b[start..i]);
    }
    out
}

pub fn unquote(t: &[u8]) -> &[u8] {
    if t.len() >= 2 && t[0] == b'"' && t[t.len() - 1] == b'"' {
        &t[1..t.len() - 1]
    } else {
        t
    }
}

/// A value of the tree `parse_span` builds.
#[derive(Debug)]
pub enum V {
    Str(Vec<u8>),
    /// A block of bare values: a plain `list`.
    List(Vec<V>),
    /// A key that repeated: a `_MultiList`.
    Multi(Vec<V>),
    Dict(Tree),
}

/// A dict of the tree, in insertion order, `_items` included as a key.
#[derive(Debug, Default)]
pub struct Tree {
    pub pairs: Vec<(Vec<u8>, V)>,
}

impl Tree {
    pub fn get(&self, key: &[u8]) -> Option<&V> {
        self.pairs.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    fn position(&self, key: &[u8]) -> Option<usize> {
        self.pairs.iter().position(|(k, _)| k == key)
    }
}

/// `_parse_listed`: (the value, where it ended).
pub fn parse(toks: &[&[u8]], mut i: usize) -> (V, usize) {
    let mut out = Tree::default();
    let mut items: Vec<V> = Vec::new();
    let n = toks.len();
    while i < n {
        let t = toks[i];
        i += 1;
        if t == b"}" {
            break;
        }
        if t == b"{" {
            let (val, j) = parse(toks, i);
            i = j;
            items.push(val);
            continue;
        }
        if t == b"=" {
            continue;
        }
        let nxt = if i < n { Some(toks[i]) } else { None };
        if nxt.is_some() {
            i += 1;
        }
        if nxt == Some(b"=") {
            if i >= n {
                break;
            }
            let val_tok = toks[i];
            i += 1;
            let val = if val_tok == b"{" {
                let (v, j) = parse(toks, i);
                i = j;
                v
            } else {
                V::Str(unquote(val_tok).to_vec())
            };
            let key = unquote(t);
            match out.position(key) {
                Some(p) => {
                    let slot = &mut out.pairs[p].1;
                    let held = std::mem::replace(slot, V::Multi(Vec::new()));
                    *slot = match held {
                        V::Multi(mut many) => {
                            many.push(val);
                            V::Multi(many)
                        }
                        one => V::Multi(vec![one, val]),
                    };
                }
                None => out.pairs.push((key.to_vec(), val)),
            }
        } else {
            items.push(V::Str(unquote(t).to_vec()));
            if nxt.is_some() {
                i -= 1;
            }
        }
    }
    if !items.is_empty() {
        if out.pairs.is_empty() {
            return (V::List(items), i);
        }
        let v = V::List(items);
        match out.position(b"_items") {
            Some(p) => out.pairs[p].1 = v,
            None => out.pairs.push((b"_items".to_vec(), v)),
        }
    }
    (V::Dict(out), i)
}

/// `parse_span(text, 0, len(text))` for a block's span.
pub fn parse_span(b: &[u8]) -> V {
    parse(&tokens(b), 0).0
}

// ------------------------------------------------------------- conversions

/// Python's `float(s)` for a string: Ok(None) is the ValueError the callers
/// catch, Err is a spelling Python accepts that this does not follow
/// (underscores between digits), refused rather than guessed at.
pub fn py_float(s: &[u8]) -> R<Option<f64>> {
    let mut a = 0;
    let mut z = s.len();
    while a < z && py_space(s[a]) {
        a += 1;
    }
    while z > a && py_space(s[z - 1]) {
        z -= 1;
    }
    let t = &s[a..z];
    if t.is_empty() {
        return Ok(None);
    }
    if t.contains(&b'_') {
        return Err(());
    }
    // Python's grammar: [sign] (digits [. [digits]] | . digits) [e [sign] digits],
    // or inf / infinity / nan in any case after a sign.
    let body = if t[0] == b'+' || t[0] == b'-' { &t[1..] } else { t };
    let lower: Vec<u8> = body.iter().map(|c| c.to_ascii_lowercase()).collect();
    if lower == b"inf" || lower == b"infinity" || lower == b"nan" {
        let v = if lower == b"nan" { f64::NAN } else { f64::INFINITY };
        return Ok(Some(if t[0] == b'-' { -v } else { v }));
    }
    let mut j = 0;
    let digits = |j: &mut usize| {
        let s = *j;
        while *j < body.len() && body[*j].is_ascii_digit() {
            *j += 1;
        }
        *j - s
    };
    let whole = digits(&mut j);
    let mut frac = 0;
    if j < body.len() && body[j] == b'.' {
        j += 1;
        frac = digits(&mut j);
    }
    if whole == 0 && frac == 0 {
        return Ok(None);
    }
    if j < body.len() && (body[j] == b'e' || body[j] == b'E') {
        j += 1;
        if j < body.len() && (body[j] == b'+' || body[j] == b'-') {
            j += 1;
        }
        if digits(&mut j) == 0 {
            return Ok(None);
        }
    }
    if j != body.len() {
        return Ok(None);
    }
    match std::str::from_utf8(t).ok().and_then(|x| x.parse::<f64>().ok()) {
        Some(v) => Ok(Some(v)),
        None => Err(()),
    }
}

/// `to_float(value, default)`.
pub fn to_float(v: Option<&V>, default: f64) -> R<f64> {
    match v {
        Some(V::Str(s)) => Ok(py_float(s)?.unwrap_or(default)),
        _ => Ok(default),
    }
}

/// `to_int(value, default)`: `int(float(value))`, the ValueError and
/// TypeError caught. `int()` of an infinity raises OverflowError, which is
/// not caught and ended the read in Python, so it is refused here.
pub fn to_int(v: Option<&V>, default: i64) -> R<i64> {
    match v {
        Some(V::Str(s)) => match py_float(s)? {
            None => Ok(default),
            Some(f) if f.is_nan() => Ok(default),
            Some(f) if f.is_infinite() => Err(()),
            Some(f) => {
                let t = f.trunc();
                if t >= -9.2e18 && t <= 9.2e18 { Ok(t as i64) } else { Err(()) }
            }
        },
        _ => Ok(default),
    }
}

/// `unquote(str(value))` where value came from `.get(key, "")`: a string,
/// or the default for a missing key. Anything else is a block where a name
/// belongs, and Python would have kept its repr.
pub(crate) fn name(v: Option<&V>) -> R<Vec<u8>> {
    match v {
        None => Ok(Vec::new()),
        Some(V::Str(s)) => Ok(unquote(s).to_vec()),
        _ => Err(()),
    }
}

/// `str(value).lower() == "yes"`.
pub(crate) fn yes(v: Option<&V>) -> R<bool> {
    match v {
        None => Ok(false),
        Some(V::Str(s)) => Ok(s.eq_ignore_ascii_case(b"yes")),
        _ => Err(()),
    }
}

/// `as_list(value)`.
pub(crate) fn as_list(v: Option<&V>) -> Vec<&V> {
    match v {
        None => Vec::new(),
        Some(V::List(x)) | Some(V::Multi(x)) => x.iter().collect(),
        Some(one) => vec![one],
    }
}

fn s(x: &[u8]) -> P {
    P::Str(text(x))
}

fn k(x: &[u8]) -> Key {
    Key::S(text(x))
}

// --------------------------------------------------------------------- wars

const I32_WRAP: i64 = (1i64 << 32) / 1000;

pub(crate) fn unwrap_overflow(n: i64) -> i64 {
    if n < 0 { n + I32_WRAP } else { n }
}

fn side(v: Option<&V>) -> R<P> {
    let block = match v {
        Some(V::Dict(d)) => d,
        _ => return Ok(P::None),
    };
    let mut out = OMap::new();
    out.set(k(b"country"), s(&name(block.get(b"country"))?));
    out.set(k(b"leader"), s(&name(block.get(b"leader"))?));
    out.set(k(b"losses"), P::Int(unwrap_overflow(to_int(block.get(b"losses"), 0)?)));
    let mut units = OMap::new();
    for (key, val) in &block.pairs {
        if key == b"country" || key == b"leader" || key == b"losses" || key.first() == Some(&b'_') {
            continue;
        }
        let n = unwrap_overflow(to_int(Some(val), 0)?);
        if n != 0 {
            units.set(k(key), P::Int(n));
        }
    }
    out.set(k(b"units"), P::Dict(units));
    Ok(P::Dict(out))
}

/// `^\d{3,4}\.\d{1,2}\.\d{1,2}$`. A key ending in a newline, which `$`
/// would also let through, is refused: no save writes one.
pub(crate) fn dated(key: &[u8]) -> R<bool> {
    if key.last() == Some(&b'\n') {
        return Err(());
    }
    let parts: Vec<&[u8]> = key.split(|&c| c == b'.').collect();
    Ok(parts.len() == 3
        && parts.iter().all(|p| p.iter().all(|c| c.is_ascii_digit()))
        && (3..=4).contains(&parts[0].len())
        && (1..=2).contains(&parts[1].len())
        && (1..=2).contains(&parts[2].len()))
}

/// `dates.date_key` for a key `dated` accepted.
pub(crate) fn date_key(d: &[u8]) -> (i64, i64, i64) {
    let mut it = d.split(|&c| c == b'.').map(|p| {
        p.iter().fold(0i64, |a, &c| a * 10 + (c - b'0') as i64)
    });
    (it.next().unwrap_or(0), it.next().unwrap_or(0), it.next().unwrap_or(0))
}

fn battle(raw: &V, when: Option<&[u8]>, out: &mut Vec<P>) -> R<()> {
    let raw = match raw {
        V::Dict(d) => d,
        _ => return Ok(()),
    };
    let mut b = OMap::new();
    b.set(k(b"name"), s(&name(raw.get(b"name"))?));
    b.set(k(b"location"), P::Int(to_int(raw.get(b"location"), 0)?));
    b.set(k(b"date"), match when { Some(w) => s(w), None => P::None });
    b.set(k(b"attacker_won"), P::Bool(yes(raw.get(b"result"))?));
    b.set(k(b"attacker"), side(raw.get(b"attacker"))?);
    b.set(k(b"defender"), side(raw.get(b"defender"))?);
    out.push(P::Dict(b));
    Ok(())
}

fn goal_of(raw: &V) -> R<Option<OMap>> {
    let raw = match raw {
        V::Dict(d) => d,
        _ => return Ok(None),
    };
    let mut g = OMap::new();
    g.set(k(b"casus_belli"), s(&name(raw.get(b"casus_belli"))?));
    g.set(k(b"actor"), s(&name(raw.get(b"actor"))?));
    g.set(k(b"receiver"), s(&name(raw.get(b"receiver"))?));
    g.set(k(b"province"), P::Int(to_int(raw.get(b"state_province_id"), 0)?));
    g.set(k(b"added"), s(&name(raw.get(b"date"))?));
    g.set(k(b"fulfilled"), P::Bool(yes(raw.get(b"is_fulfilled"))?));
    Ok(Some(g))
}

fn sorted_names(mut v: Vec<Vec<u8>>) -> P {
    // Python sorts str by code point, which for latin-1 is the byte.
    v.sort();
    v.dedup();
    P::List(v.iter().map(|x| s(x)).collect())
}

/// `readwar.read_war(block, active)`, or None for a block that is not a dict.
pub fn read_war(v: &V, active: bool) -> R<Option<P>> {
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
    let mut battles: Vec<P> = Vec::new();
    let mut battle_dates: Vec<Vec<u8>> = Vec::new();
    for (key, value) in &history.pairs {
        if key == b"battle" {
            for raw in as_list(Some(value)) {
                battle(raw, None, &mut battles)?;
            }
            continue;
        }
        if !dated(key)? {
            continue;
        }
        for entry in as_list(Some(value)) {
            let entry = match entry {
                V::Dict(d) => d,
                _ => continue,
            };
            for (what, who) in &entry.pairs {
                if what == b"battle" {
                    for raw in as_list(Some(who)) {
                        let before = battles.len();
                        battle(raw, Some(key), &mut battles)?;
                        if battles.len() > before {
                            battle_dates.push(key.clone());
                        }
                    }
                } else if what == b"add_attacker" || what == b"add_defender" {
                    joined.push((key.clone(), name(Some(who))?, what == b"add_attacker"));
                } else if what == b"rem_attacker" || what == b"rem_defender" {
                    left.push((key.clone(), name(Some(who))?, what == b"rem_attacker"));
                }
            }
        }
    }

    let mut goals = Vec::new();
    for raw in as_list(block.get(b"war_goal")) {
        if let Some(g) = goal_of(raw)? {
            let has = |f: &[u8]| matches!(g.get(&k(f)), Some(P::Str(x)) if !x.is_empty());
            if has(b"actor") || has(b"receiver") {
                goals.push(P::Dict(g));
            }
        }
    }
    let empty_goal = Tree::default();
    let goal = match block.get(b"original_wargoal") {
        Some(V::Dict(d)) => d,
        _ => &empty_goal,
    };

    // `min`/`max` with `date_key`: the first of equals wins either way.
    let dates: Vec<&Vec<u8>> = joined.iter().map(|j| &j.0)
        .chain(left.iter().map(|l| &l.0))
        .chain(battle_dates.iter())
        .collect();
    let pick = |want_max: bool| -> Vec<u8> {
        let mut best: Option<&Vec<u8>> = None;
        for d in &dates {
            let better = match best {
                None => true,
                Some(b) if want_max => date_key(d) > date_key(b),
                Some(b) => date_key(d) < date_key(b),
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
        for tag in as_list(block.get(side_key)) {
            fighting.push(name(Some(tag))?);
        }
    }
    let event = |list: &Vec<(Vec<u8>, Vec<u8>, bool)>| {
        P::List(list.iter().map(|(d, w, a)| P::List(vec![s(d), s(w), P::Bool(*a)])).collect())
    };

    let mut goal_out = OMap::new();
    goal_out.set(k(b"casus_belli"), s(&name(goal.get(b"casus_belli"))?));
    goal_out.set(k(b"actor"), s(&name(goal.get(b"actor"))?));
    goal_out.set(k(b"receiver"), s(&name(goal.get(b"receiver"))?));
    goal_out.set(k(b"province"), P::Int(to_int(goal.get(b"state_province_id"), 0)?));

    let mut war = OMap::new();
    war.set(k(b"name"), s(&name(block.get(b"name"))?));
    war.set(k(b"active"), P::Bool(active));
    war.set(k(b"start"), s(&start));
    war.set(k(b"end"), s(&end));
    war.set(k(b"original_attacker"), s(&name(block.get(b"original_attacker"))?));
    war.set(k(b"original_defender"), s(&name(block.get(b"original_defender"))?));
    let side = |attacking: bool| -> Vec<Vec<u8>> {
        joined.iter().filter(|j| j.2 == attacking).map(|j| j.1.clone()).collect()
    };
    war.set(k(b"attackers"), sorted_names(side(true)));
    war.set(k(b"defenders"), sorted_names(side(false)));
    war.set(k(b"fighting"), sorted_names(fighting));
    war.set(k(b"joins"), event(&joined));
    war.set(k(b"leaves"), event(&left));
    war.set(k(b"goals"), P::List(goals));
    war.set(k(b"goal"), P::Dict(goal_out));
    war.set(k(b"battles"), P::List(battles));
    Ok(Some(P::Dict(war)))
}

// ------------------------------------------------------------------- market

/// `int(p)` for one part of a `YYYY.M.D` date: Ok(None) is the ValueError
/// `shift_months` catches. Signs are Python's; spaces and underscores, which
/// `int()` also takes, are refused.
pub(crate) fn py_int(p: &[u8]) -> R<Option<i64>> {
    if p.iter().any(|&c| py_space(c) || c == b'_') {
        return Err(());
    }
    let (neg, digits) = match p.first() {
        Some(b'-') => (true, &p[1..]),
        Some(b'+') => (false, &p[1..]),
        _ => (false, p),
    };
    if digits.is_empty() || !digits.iter().all(|c| c.is_ascii_digit()) {
        return Ok(None);
    }
    if digits.len() > 15 {
        return Err(());
    }
    let v = digits.iter().fold(0i64, |a, &c| a * 10 + (c - b'0') as i64);
    Ok(Some(if neg { -v } else { v }))
}

/// `readsave.shift_months(date, back)`.
pub(crate) fn shift_months(date: &[u8], back: i64) -> R<Vec<u8>> {
    let parts: Vec<&[u8]> = date.split(|&c| c == b'.').collect();
    if parts.len() != 3 {
        return Ok(Vec::new());
    }
    let mut n = [0i64; 3];
    for (i, p) in parts.iter().enumerate() {
        match py_int(p)? {
            Some(v) => n[i] = v,
            None => return Ok(Vec::new()),
        }
    }
    let total = n[0] * 12 + (n[1] - 1) - back;
    Ok(format!("{}.{}.{}", total.div_euclid(12), total.rem_euclid(12) + 1, n[2]).into_bytes())
}

fn numeric(block: &Tree, key: &[u8]) -> R<P> {
    let mut out = OMap::new();
    if let Some(V::Dict(sub)) = block.get(key) {
        for (k2, v) in &sub.pairs {
            if k2.first() == Some(&b'_') {
                continue;
            }
            if let V::Str(_) = v {
                out.set(k(k2), P::Float(to_float(Some(v), 0.0)?));
            }
        }
    }
    Ok(P::Dict(out))
}

/// `readsave.read_worldmarket(block, save_date)`.
pub fn read_worldmarket(block: &Tree, save_date: &[u8]) -> R<P> {
    let current = numeric(block, b"price_pool")?;
    let history_blocks: Vec<&Tree> = as_list(block.get(b"price_history"))
        .into_iter()
        .filter_map(|v| match v { V::Dict(d) => Some(d), _ => None })
        .collect();
    let last_update = match block.get(b"price_history_last_update") {
        None => Vec::new(),
        Some(V::Str(x)) => unquote(x).to_vec(),
        Some(_) => Vec::new(),
    };
    let mut history = Vec::new();
    let count = history_blocks.len() as i64;
    for (idx, snap) in history_blocks.iter().enumerate() {
        let stamp = if last_update.is_empty() {
            Vec::new()
        } else {
            shift_months(&last_update, count - 1 - idx as i64)?
        };
        if stamp.is_empty() {
            continue;
        }
        let stamp = text(&stamp);
        for (good, price) in &snap.pairs {
            if good.first() == Some(&b'_') {
                continue;
            }
            if let V::Str(_) = price {
                history.push(P::Tuple(vec![P::Str(stamp.clone()), s(good),
                                           P::Float(to_float(Some(price), 0.0)?)]));
            }
        }
    }
    let mut snapshot = OMap::new();
    for (name, key) in [
        (&b"world_pool"[..], &b"worldmarket_pool"[..]),
        (b"supply", b"supply_pool"),
        (b"demand", b"demand"),
        (b"real_demand", b"real_demand"),
        (b"actual_sold", b"actual_sold"),
        (b"actual_sold_world", b"actual_sold_world"),
        (b"discovered", b"discovered_goods"),
    ] {
        snapshot.set(k(name), numeric(block, key)?);
    }
    let mut out = OMap::new();
    out.set(k(b"current"), current);
    out.set(k(b"history"), P::List(history));
    out.set(k(b"last_update"), s(&last_update));
    out.set(k(b"snapshot"), P::Dict(snapshot));
    out.set(k(b"save_date"), s(save_date));
    Ok(P::Dict(out))
}

/// The great power list: `[to_int(i, -1) for i in ids]`.
pub fn great_nations(v: &V) -> R<P> {
    let ids: Vec<&V> = match v {
        V::List(items) => items.iter().collect(),
        V::Dict(d) => match d.get(b"_items") {
            None => Vec::new(),
            Some(V::List(items)) | Some(V::Multi(items)) => items.iter().collect(),
            // A key really named `_items` holding a string: Python would
            // walk it a character at a time.
            Some(_) => return Err(()),
        },
        _ => Vec::new(),
    };
    let mut out = Vec::with_capacity(ids.len());
    for i in ids {
        out.push(P::Int(to_int(Some(i), -1)?));
    }
    Ok(P::List(out))
}

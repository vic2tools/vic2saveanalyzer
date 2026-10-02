// The generic tree Python's `v2parse.parse_span` builds, and the
// conversions its readers made of it, read as Python read them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The wars, the world market and the great power list (`engine::model`),
// the mod's files (`modread`) and the odd block elsewhere go through this
// tree, rule for rule as Python built it, rather than the country reader's
// parser, which differs on purpose in two places: it folds a repeated key
// into an earlier list of bare values, where Python keeps the two apart, and
// its whitespace is Rust's rather than Python's `\s`.
//
// Where Python would do something no save should make it do -- call `str()`
// on a block where a name belongs and keep the repr, turn an infinite number
// into an int and raise -- this refuses the save instead (`Err`).

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
/// catch. Underscores between digits, spaces Python trims, `inf` and `nan`
/// are all Python's (`modread::py_float`).
pub fn py_float(s: &[u8]) -> R<Option<f64>> {
    Ok(crate::engine::modread::py_float(s))
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
/// the default for a missing key, or -- a block where a name belongs -- the
/// repr Python makes of it.
pub(crate) fn name(v: Option<&V>) -> R<Vec<u8>> {
    match v {
        None => Ok(Vec::new()),
        Some(V::Str(s)) => Ok(unquote(s).to_vec()),
        Some(other) => Ok(unquote(&crate::engine::modread::str_of(other)).to_vec()),
    }
}

/// `str(value).lower() == "yes"`: never, for a block.
pub(crate) fn yes(v: Option<&V>) -> R<bool> {
    match v {
        Some(V::Str(s)) => Ok(s.eq_ignore_ascii_case(b"yes")),
        _ => Ok(false),
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

// --------------------------------------------------------------------- wars

const I32_WRAP: i64 = (1i64 << 32) / 1000;

pub(crate) fn unwrap_overflow(n: i64) -> i64 {
    if n < 0 { n + I32_WRAP } else { n }
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

// ------------------------------------------------------------------- market

/// `int(p)` for one part of a `YYYY.M.D` date: Ok(None) is the ValueError
/// `shift_months` catches; a number past an i64 is refused.
pub(crate) fn py_int(p: &[u8]) -> R<Option<i64>> {
    crate::engine::modread::py_int(p).map_err(|_| ())
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

/// The great power list: `[to_int(i, -1) for i in ids]`.
pub fn great_nations(v: &V) -> R<Vec<i64>> {
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
        out.push(to_int(Some(i), -1)?);
    }
    Ok(out)
}

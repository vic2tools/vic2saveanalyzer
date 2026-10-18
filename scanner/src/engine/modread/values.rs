// A mod file's values as Python's mod reader read them: its numbers, its
// trees, and the repr of either.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;

/// What `float()` and `int()` trim from a str: C's whitespace and the
/// non-ASCII spaces, which leaves `\x1c`-`\x1f` in.
pub(super) fn num_space(c: u8) -> bool {
    matches!(c, 0x09..=0x0d | 0x20 | 0x85 | 0xa0)
}

pub(super) fn num_trim(s: &[u8]) -> &[u8] {
    let mut a = 0;
    let mut z = s.len();
    while a < z && num_space(s[a]) {
        a += 1;
    }
    while z > a && num_space(s[z - 1]) {
        z -= 1;
    }
    &s[a..z]
}

/// Underscores out, if each sits between two digits, as Python allows.
pub(super) fn no_underscores(t: &[u8]) -> Option<Vec<u8>> {
    let mut out = Vec::with_capacity(t.len());
    for (i, &c) in t.iter().enumerate() {
        if c == b'_' {
            if i == 0 || i + 1 == t.len() || !t[i - 1].is_ascii_digit() || !t[i + 1].is_ascii_digit() {
                return None;
            }
        } else {
            out.push(c);
        }
    }
    Some(out)
}

/// Python's `float(s)` for latin-1 text: None is the ValueError.
pub fn py_float(s: &[u8]) -> Option<f64> {
    let t = no_underscores(num_trim(s))?;
    if t.is_empty() {
        return None;
    }
    let body = if t[0] == b'+' || t[0] == b'-' { &t[1..] } else { &t[..] };
    let lowered: Vec<u8> = body.iter().map(|c| c.to_ascii_lowercase()).collect();
    if lowered == b"inf" || lowered == b"infinity" || lowered == b"nan" {
        let v = if lowered == b"nan" { f64::NAN } else { f64::INFINITY };
        return Some(if t[0] == b'-' { -v } else { v });
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
        return None;
    }
    if j < body.len() && (body[j] == b'e' || body[j] == b'E') {
        j += 1;
        if j < body.len() && (body[j] == b'+' || body[j] == b'-') {
            j += 1;
        }
        if digits(&mut j) == 0 {
            return None;
        }
    }
    if j != body.len() {
        return None;
    }
    std::str::from_utf8(&t).ok()?.parse::<f64>().ok()
}

/// Python's `int(s)`: Ok(None) is the ValueError; a number past what an
/// i64 holds is declined, since Python would carry it on as a big int.
pub fn py_int(s: &[u8]) -> D<Option<i64>> {
    let t = match no_underscores(num_trim(s)) {
        Some(t) => t,
        None => return Ok(None),
    };
    let (neg, digits) = match t.first() {
        Some(b'-') => (true, &t[1..]),
        Some(b'+') => (false, &t[1..]),
        _ => (false, &t[..]),
    };
    if digits.is_empty() || !digits.iter().all(|c| c.is_ascii_digit()) {
        return Ok(None);
    }
    let digits = {
        let z = digits.iter().position(|&c| c != b'0').unwrap_or(digits.len() - 1);
        &digits[z..]
    };
    if digits.len() > 18 {
        return no("a number too large to follow");
    }
    let v = digits.iter().fold(0i64, |a, &c| a * 10 + (c - b'0') as i64);
    Ok(Some(if neg { -v } else { v }))
}

/// `float(text)` where Python lets the ValueError out.
pub(super) fn must_float(s: &[u8]) -> D<f64> {
    match py_float(s) {
        Some(v) => Ok(v),
        None => raised(format!("could not convert string to float: {}", py_repr(&l1(s)))),
    }
}

/// `to_float(value, default)`.
pub(super) fn to_float(v: Option<&V>, default: f64) -> f64 {
    match v {
        Some(V::Str(s)) => py_float(s).unwrap_or(default),
        _ => default,
    }
}

/// `to_int(value, default)`: `int(float(value))`, whose OverflowError on
/// an infinity nothing catches.
pub(super) fn to_int(v: Option<&V>, default: i64) -> D<i64> {
    match v {
        Some(V::Str(s)) => match py_float(s) {
            None => Ok(default),
            Some(f) if f.is_nan() => Ok(default),
            Some(f) if f.is_infinite() => no("int() of an infinity"),
            Some(f) => {
                let t = f.trunc();
                if t.abs() < 9.0e18 { Ok(t as i64) } else { no("a number too large to follow") }
            }
        },
        _ => Ok(default),
    }
}

/// `str.isdigit()` for a latin-1 word, and whether `int()` then takes it:
/// the superscripts are digits to the one and not to the other.
pub(super) fn digit_word(w: &[u8]) -> D<bool> {
    if w.is_empty() || !w.iter().all(|&c| c.is_ascii_digit() || matches!(c, 0xb2 | 0xb3 | 0xb9)) {
        return Ok(false);
    }
    if w.iter().any(|&c| !c.is_ascii_digit()) {
        return raised(format!("invalid literal for int() with base 10: {}", py_repr(&l1(w))));
    }
    Ok(true)
}

/// `str.split()`.
pub(super) fn split_ws(b: &[u8]) -> impl Iterator<Item = &[u8]> {
    b.split(|&c| space(c)).filter(|w| !w.is_empty())
}

/// `str.strip()` for latin-1 text.
pub(super) fn strip(b: &[u8]) -> &[u8] {
    let mut a = 0;
    let mut z = b.len();
    while a < z && space(b[a]) {
        a += 1;
    }
    while z > a && space(b[z - 1]) {
        z -= 1;
    }
    &b[a..z]
}

/// `str.lower()` for latin-1 text.
pub(super) fn lower1(b: &[u8]) -> Vec<u8> {
    b.iter().map(|&c| match c {
        b'A'..=b'Z' => c + 32,
        0xc0..=0xde if c != 0xd7 => c + 32,
        _ => c,
    }).collect()
}

/// `repr()` of a value, for the places Python calls `str()` on what may be
/// a block.
pub(super) fn repr(v: &V, out: &mut String) {
    match v {
        V::Str(s) => repr_str(s, out),
        V::List(x) | V::Multi(x) => {
            out.push('[');
            for (i, e) in x.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                repr(e, out);
            }
            out.push(']');
        }
        V::Dict(d) => {
            out.push('{');
            for (i, (k, e)) in d.pairs.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                repr_str(k, out);
                out.push_str(": ");
                repr(e, out);
            }
            out.push('}');
        }
    }
}

pub(super) fn repr_str(s: &[u8], out: &mut String) {
    let q = if s.contains(&b'\'') && !s.contains(&b'"') { '"' } else { '\'' };
    out.push(q);
    for &c in s {
        match c {
            b'\\' => out.push_str("\\\\"),
            b'\t' => out.push_str("\\t"),
            b'\n' => out.push_str("\\n"),
            b'\r' => out.push_str("\\r"),
            c if c as char == q => {
                out.push('\\');
                out.push(q);
            }
            0x00..=0x1f | 0x7f..=0xa0 | 0xad => out.push_str(&format!("\\x{:02x}", c)),
            c => out.push(c as char),
        }
    }
    out.push(q);
}

/// `str(value)`, latin-1.
pub(crate) fn str_of(v: &V) -> Vec<u8> {
    match v {
        V::Str(s) => s.clone(),
        other => {
            let mut s = String::new();
            repr(other, &mut s);
            // A repr of latin-1 text is latin-1 again.
            s.chars().map(|c| c as u32 as u8).collect()
        }
    }
}

pub(super) fn is_dict(v: &V) -> bool {
    matches!(v, V::Dict(_))
}

pub(super) fn pairs(v: &V) -> &[(Vec<u8>, V)] {
    match v {
        V::Dict(d) => &d.pairs,
        _ => &[],
    }
}

pub(super) fn get<'v>(v: &'v V, key: &[u8]) -> Option<&'v V> {
    match v {
        V::Dict(d) => d.get(key),
        _ => None,
    }
}

/// A parsed value in JSON's terms, as `json.dumps` would write the tree.
pub(super) fn tree_json(v: &V) -> J {
    match v {
        V::Str(s) => js(s),
        V::List(x) | V::Multi(x) => J::List(x.iter().map(tree_json).collect()),
        V::Dict(d) => J::Obj(d.pairs.iter().map(|(k, e)| (l1(k), tree_json(e))).collect()),
    }
}

pub(super) fn sorted_json(s: &Set) -> J {
    J::List(s.iter().map(|x| js(x)).collect())
}

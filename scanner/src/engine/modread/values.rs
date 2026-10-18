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
use crate::py::repr::Repr;
use crate::py::num::float_latin1;

/// `float(text)` where Python lets the ValueError out.
pub(super) fn must_float(s: &[u8]) -> D<f64> {
    match float_latin1(s) {
        Some(v) => Ok(v),
        None => raised(format!("could not convert string to float: {}", crate::py::repr::str_repr(&l1(s)))),
    }
}

/// `to_float(value, default)`.
pub(super) fn to_float(v: Option<&V>, default: f64) -> f64 {
    match v {
        Some(V::Str(s)) => float_latin1(s).unwrap_or(default),
        _ => default,
    }
}

/// `to_int(value, default)`: `int(float(value))`, whose OverflowError on
/// an infinity nothing catches.
pub(super) fn to_int(v: Option<&V>, default: i64) -> D<i64> {
    match v {
        Some(V::Str(s)) => match float_latin1(s) {
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
        return raised(format!("invalid literal for int() with base 10: {}", crate::py::repr::str_repr(&l1(w))));
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

/// `str(value)`, latin-1.
pub(crate) fn str_of(v: &V) -> Vec<u8> {
    match v {
        V::Str(s) => s.clone(),
        other => {
            let s = other.repr();
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

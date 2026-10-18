// Python's `repr()`, for the places the analyzer called `str()` on something
// that may be a block: a save's or a mod's tree (`V`), or a trigger's JSON
// (`J`).
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::py::json::J;
use crate::save::clause::V;

/// `repr()` of a str: quoted as Python quotes it, with what Python does not
/// print escaped. Printable is Python's rule exactly for the first 256
/// characters, and past them for the spaces, separators and format
/// characters a path could hold.
pub fn str_repr(s: &str) -> String {
    let q = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::new();
    out.push(q);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if c == q => {
                out.push('\\');
                out.push(q);
            }
            c if !printable(c) => {
                let n = c as u32;
                if n < 0x100 {
                    out.push_str(&format!("\\x{:02x}", n));
                } else if n < 0x10000 {
                    out.push_str(&format!("\\u{:04x}", n));
                } else {
                    out.push_str(&format!("\\U{:08x}", n));
                }
            }
            c => out.push(c),
        }
    }
    out.push(q);
    out
}

/// `str.isprintable()` for one character.
fn printable(c: char) -> bool {
    let n = c as u32;
    match n {
        0x00..=0x1f | 0x7f..=0xa0 | 0xad => false,
        0x20..=0x7e | 0xa1..=0xff => true,
        0x1680 | 0x2000..=0x200f | 0x2028..=0x202f | 0x205f..=0x2064 | 0x3000 | 0xfeff => false,
        0xe000..=0xf8ff | 0xf0000..=0x10ffff => false,
        _ => true,
    }
}

/// `repr()` of a tree: a list as `[a, b]`, a block as `{'k': v}`.
pub trait Repr {
    fn repr_into(&self, out: &mut String);

    fn repr(&self) -> String {
        let mut out = String::new();
        self.repr_into(&mut out);
        out
    }
}

fn list<T: Repr>(items: &[T], out: &mut String) {
    out.push('[');
    for (i, e) in items.iter().enumerate() {
        if i > 0 {
            out.push_str(", ");
        }
        e.repr_into(out);
    }
    out.push(']');
}

fn dict<'a, T: Repr + 'a>(pairs: impl Iterator<Item = (String, &'a T)>, out: &mut String) {
    out.push('{');
    for (i, (k, e)) in pairs.enumerate() {
        if i > 0 {
            out.push_str(", ");
        }
        out.push_str(&str_repr(&k));
        out.push_str(": ");
        e.repr_into(out);
    }
    out.push('}');
}

/// A save's or a mod's text is latin-1: a byte a character.
fn latin1(b: &[u8]) -> String {
    b.iter().map(|&c| c as char).collect()
}

impl Repr for V {
    fn repr_into(&self, out: &mut String) {
        match self {
            V::Str(s) => out.push_str(&str_repr(&latin1(s))),
            V::List(x) | V::Multi(x) => list(x, out),
            V::Dict(d) => dict(d.pairs.iter().map(|(k, e)| (latin1(k), e)), out),
        }
    }
}

impl Repr for J {
    fn repr_into(&self, out: &mut String) {
        match self {
            J::Str(s) => out.push_str(&str_repr(s)),
            J::List(x) => list(x, out),
            J::Obj(pairs) => dict(pairs.iter().map(|(k, e)| (k.clone(), e)), out),
            // A number, a bool or null, as the mod's JSON wrote it.
            other => other.write(out),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_str_is_quoted_and_escaped_as_python_does() {
        assert_eq!(str_repr("it's"), "\"it's\"");
        assert_eq!(str_repr("a\tb\\"), "'a\\tb\\\\'");
        assert_eq!(str_repr("\u{a0}\u{e9}\u{2028}"), "'\\xa0\u{e9}\\u2028'");
    }

    #[test]
    fn a_save_block_and_a_json_block_read_alike() {
        let v = V::List(vec![V::Str(b"a".to_vec()), V::Str(b"b\xe9".to_vec())]);
        let j = J::List(vec![J::Str("a".into()), J::Str("b\u{e9}".into())]);
        assert_eq!(v.repr(), "['a', 'b\u{e9}']");
        assert_eq!(j.repr(), v.repr());
    }
}

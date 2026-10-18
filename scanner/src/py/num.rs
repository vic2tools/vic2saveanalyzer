// Python's `float()` and `int()` of text, the rules every reader of a save,
// a mod and a date follows.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::fmt::py_space_char;

/// What `float()` and `int()` trim from latin-1 text: C's whitespace and the
/// two non-ASCII spaces latin-1 has, which leaves `\x1c`-`\x1f` in.
fn latin1_space(c: u8) -> bool {
    matches!(c, 0x09..=0x0d | 0x20 | 0x85 | 0xa0)
}

fn latin1_trim(s: &[u8]) -> &[u8] {
    let mut a = 0;
    let mut z = s.len();
    while a < z && latin1_space(s[a]) {
        a += 1;
    }
    while z > a && latin1_space(s[z - 1]) {
        z -= 1;
    }
    &s[a..z]
}

/// Underscores out, if each sits between two digits, as Python allows.
fn no_underscores(t: &[u8]) -> Option<Vec<u8>> {
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

/// `float()` of text already trimmed and rid of its underscores.
fn float_of(t: &[u8]) -> Option<f64> {
    if t.is_empty() {
        return None;
    }
    let body = if t[0] == b'+' || t[0] == b'-' { &t[1..] } else { t };
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
    std::str::from_utf8(t).ok()?.parse::<f64>().ok()
}

/// Python's `float(s)` for a str: None for the ValueError.
pub fn float(s: &str) -> Option<f64> {
    // Not quite `str.strip()`: `float()` maps non-ASCII whitespace to spaces
    // and then trims C's six, so `\x1c`-`\x1f`, which `isspace` calls space,
    // stay and make it a ValueError.
    let t = s.trim_matches(|c: char| {
        matches!(c, '\t'..='\r' | ' ') || (c as u32 >= 0x80 && py_space_char(c))
    });
    float_of(&no_underscores(t.as_bytes())?)
}

/// Python's `float(s)` for latin-1 text, a byte a character: None for the
/// ValueError.
pub fn float_latin1(s: &[u8]) -> Option<f64> {
    float_of(&no_underscores(latin1_trim(s))?)
}

/// An `int()` Python would carry on as a big int, past what an i64 holds.
#[derive(Debug, PartialEq)]
pub struct TooLarge;

impl std::fmt::Display for TooLarge {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str("a number too large to follow")
    }
}

/// Python's `int(s)` for latin-1 text: Ok(None) for the ValueError, and
/// past eighteen digits (leading zeros aside) too large to follow.
pub fn int_latin1(s: &[u8]) -> Result<Option<i64>, TooLarge> {
    let t = match no_underscores(latin1_trim(s)) {
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
        return Err(TooLarge);
    }
    let v = digits.iter().fold(0i64, |a, &c| a * 10 + (c - b'0') as i64);
    Ok(Some(if neg { -v } else { v }))
}

/// Python's `int(s)` for a str, trimmed of what `str.isspace` calls space:
/// None for the ValueError, and for a number past what an i64 holds.
pub fn int(s: &str) -> Option<i64> {
    let t = s.trim_matches(py_space_char);
    let (neg, body) = match t.as_bytes().first() {
        Some(b'-') => (true, &t[1..]),
        Some(b'+') => (false, &t[1..]),
        _ => (false, t),
    };
    if body.is_empty() {
        return None;
    }
    let b = body.as_bytes();
    // Digits, with single underscores between them, as Python allows.
    if !b[0].is_ascii_digit() || !b[b.len() - 1].is_ascii_digit() {
        return None;
    }
    let mut v: i64 = 0;
    let mut prev_us = false;
    for &c in b {
        if c == b'_' {
            if prev_us {
                return None;
            }
            prev_us = true;
            continue;
        }
        if !c.is_ascii_digit() {
            return None;
        }
        prev_us = false;
        v = v.checked_mul(10)?.checked_add((c - b'0') as i64)?;
    }
    Some(if neg { -v } else { v })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_float_is_trimmed_of_pythons_spaces_and_no_others() {
        assert_eq!(float(" 1 "), Some(1.0));
        assert_eq!(float("\u{2000}2\u{3000}"), Some(2.0));
        assert_eq!(float("\x1c1"), None);
        assert_eq!(float_latin1(b"\xa01\x85"), Some(1.0));
        assert_eq!(float_latin1(b"\x1c1"), None);
    }

    #[test]
    fn floats_take_underscores_where_python_does() {
        assert_eq!(float("1_000"), Some(1000.0));
        assert_eq!(float(" 1_0.5_0 "), Some(10.5));
        for bad in ["_1", "1_", "1__0", "1_.5", "1._5"] {
            assert_eq!(float(bad), None, "{}", bad);
        }
    }

    #[test]
    fn a_float_takes_underscores_infinities_and_nan_as_python_does() {
        assert_eq!(float("1_0.5"), Some(10.5));
        assert_eq!(float("1__0"), None);
        assert_eq!(float_latin1(b"_1"), None);
        assert_eq!(float("1e400"), Some(f64::INFINITY));
        assert_eq!(float_latin1(b"-Infinity"), Some(f64::NEG_INFINITY));
        assert!(float("nan").unwrap().is_nan());
        assert_eq!(float("1e"), None);
        assert_eq!(float_latin1(b"."), None);
    }

    #[test]
    fn an_int_of_latin1_text_says_when_it_is_too_large_to_follow() {
        assert_eq!(int_latin1(b" -12 "), Ok(Some(-12)));
        assert_eq!(int_latin1(b"1_000"), Ok(Some(1000)));
        assert_eq!(int_latin1(b"1.5"), Ok(None));
        assert_eq!(int_latin1(b"000000000000000000000007"), Ok(Some(7)));
        assert_eq!(int_latin1(b"999999999999999999"), Ok(Some(999_999_999_999_999_999)));
        assert_eq!(int_latin1(b"9999999999999999999"), Err(TooLarge));
    }

    #[test]
    fn an_int_of_a_str_is_none_past_what_an_i64_holds() {
        assert_eq!(int(" 12 "), Some(12));
        assert_eq!(int("1_000"), Some(1000));
        assert_eq!(int("1__0"), None);
        assert_eq!(int("_1"), None);
        assert_eq!(int("99999999999999999999"), None);
    }
}

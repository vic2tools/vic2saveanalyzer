// The game's dates, `1847.1.1`, turned into things that sort and plot:
// `dates.py`.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::pyfmt::py_space_char;

/// Python's `int(s)` for a str: None for the ValueError.
pub fn py_int(s: &str) -> Option<i64> {
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

/// `date_key`: the parts as numbers, or (0, 0, 0) for anything else.
pub fn date_key(date: &str) -> Vec<i64> {
    let mut out = Vec::with_capacity(3);
    for p in date.split('.') {
        match py_int(p) {
            Some(v) => out.push(v),
            None => return vec![0, 0, 0],
        }
    }
    out
}

/// `year_fraction`: a date as a position on a year axis; 0.0 otherwise.
pub fn year_fraction(date: &str) -> f64 {
    let mut parts = date.split('.');
    let (y, m, d) = match (parts.next(), parts.next(), parts.next(), parts.next()) {
        (Some(y), Some(m), Some(d), None) => (y, m, d),
        _ => return 0.0,
    };
    match (py_int(y), py_int(m), py_int(d)) {
        (Some(y), Some(m), Some(d)) => y as f64 + (m - 1) as f64 / 12.0 + (d - 1) as f64 / 365.0,
        _ => 0.0,
    }
}

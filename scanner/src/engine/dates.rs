// The game's dates, `1847.1.1`, turned into things that sort and plot:
// `vic2tools/keeper.py`'s `ymd`.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::py::num::int;

/// `date_key`: the parts as numbers, or (0, 0, 0) for anything else.
pub fn date_key(date: &str) -> Vec<i64> {
    let mut out = Vec::with_capacity(3);
    for p in date.split('.') {
        match int(p) {
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
    match (int(y), int(m), int(d)) {
        (Some(y), Some(m), Some(d)) => y as f64 + (m - 1) as f64 / 12.0 + (d - 1) as f64 / 365.0,
        _ => 0.0,
    }
}

// A faster province scanner for the Victoria 2 campaign analyzer.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Reading bytes as the analyzer's Python reads text: the numbers, the quotes,
// the country tags, the latin-1 decode, and finding a needle. `find` and the
// quotes are used by both readers and written once here. The country reader
// keeps its own number parsing, on text it has already decoded: it trims
// whitespace the way Python's `float()` does, which is wider than the ASCII
// these byte versions trim, and the two agree only because the game writes
// ASCII numbers.

// Byte versions of the three conversions. A save's numbers are ASCII, so
// nothing here needs the file decoded first -- which is the whole point:
// decoding 31 MB to read a few thousand characters of it cost 23 ms a save
// and a 31 MB allocation, and on a machine already bound by memory traffic
// the allocation costs more than the milliseconds.
pub(crate) fn trim_b(s: &[u8]) -> &[u8] {
    let mut a = 0;
    let mut b = s.len();
    while a < b && (s[a] as char).is_ascii_whitespace() { a += 1; }
    while b > a && (s[b - 1] as char).is_ascii_whitespace() { b -= 1; }
    &s[a..b]
}

pub(crate) fn trim_end_b(s: &[u8]) -> &[u8] {
    let mut b = s.len();
    while b > 0 && (s[b - 1] as char).is_ascii_whitespace() { b -= 1; }
    &s[..b]
}

pub(crate) fn to_float_b(s: &[u8]) -> f64 {
    match std::str::from_utf8(trim_b(s)) {
        Ok(t) => t.parse::<f64>().unwrap_or(0.0),
        Err(_) => 0.0,
    }
}

/// `int(float(s))`: truncation toward zero, which is what the analyzer does
/// to every size in the file. `"12345.000"` is 12345, not an error.
pub(crate) fn to_int_b(s: &[u8]) -> i64 {
    let v = to_float_b(s);
    if v.is_finite() { v.trunc() as i64 } else { 0 }
}

pub(crate) fn unquote_b(b: &[u8]) -> &[u8] {
    if b.len() >= 2 && b[0] == b'"' && b[b.len() - 1] == b'"' {
        &b[1..b.len() - 1]
    } else {
        b
    }
}

pub(crate) fn is_number_b(s: &[u8]) -> bool {
    std::str::from_utf8(s).ok().and_then(|t| t.parse::<f64>().ok()).is_some()
}


/// Windows-1252 bytes as a Rust string, the way Python's latin-1 decode
/// reads them: byte value is code point, and nothing can fail.
pub(crate) fn latin1(raw: &[u8]) -> String {
    let mut out = String::with_capacity(raw.len() + 16);
    let mut start = 0usize;
    let mut i = 0usize;
    while i < raw.len() {
        match raw[i..].iter().position(|&b| b >= 0x80) {
            None => break,
            Some(off) => {
                let hit = i + off;
                // Safe: everything from `start` to `hit` is ASCII.
                out.push_str(unsafe { std::str::from_utf8_unchecked(&raw[start..hit]) });
                out.push(raw[hit] as char);
                start = hit + 1;
                i = hit + 1;
            }
        }
    }
    out.push_str(unsafe { std::str::from_utf8_unchecked(&raw[start..]) });
    out
}


/// Whether these bytes are a country tag, by the same rule as the Python:
/// three characters, the first an uppercase letter, all alphanumeric.
pub(crate) fn tag_bytes(key: &[u8]) -> bool {
    key.len() == 3
        && key[0].is_ascii_alphabetic()
        && key[0].is_ascii_uppercase()
        && key.iter().all(|c| c.is_ascii_alphanumeric())
        && !key.iter().all(|c| c.is_ascii_digit())
}

/// `unquote_b` for text: the same two quotes off the same two ends.
pub(crate) fn unquote(s: &str) -> &str {
    // Safe: only ASCII quote bytes are removed, from either end, so what
    // is left is still whole characters.
    unsafe { std::str::from_utf8_unchecked(unquote_b(s.as_bytes())) }
}

/// Where `needle` next starts in `hay[from..stop]`, as an index into `hay`.
pub(crate) fn find(hay: &[u8], needle: &[u8], from: usize, stop: usize) -> Option<usize> {
    let end = stop.min(hay.len());
    if from >= end {
        return None;
    }
    // A sliding window, which reads oddly for a two-byte needle and is the
    // fastest of the three things tried here: scanning for the first byte and
    // checking the second measured 0.10s -> 0.15s on a 31 MB save, because
    // the compiler vectorises this and cannot vectorise a loop that restarts
    // at every newline.
    hay[from..end]
        .windows(needle.len())
        .position(|w| w == needle)
        .map(|i| i + from)
}

/// Where the two bytes `a` then `b` next start in `hay[from..stop]`: `find`
/// for a two-byte needle, eight bytes at a time.
///
/// `top_level_blocks` looks for `\n{` across the whole file, and the sliding
/// window above spent a sixth of a save's scan doing it: 34 MB for three
/// thousand hits. This compares a word at once -- a byte of the word is
/// marked where it equals `a`, another where it equals `b`, and a hit is an
/// `a` mark with a `b` mark in the byte after it, the last byte of one word
/// carried into the first of the next. Plain arithmetic on a `u64`, so the
/// same everywhere the scanner is built.
pub(crate) fn find_pair(hay: &[u8], a: u8, b: u8, from: usize, stop: usize) -> Option<usize> {
    const LOW: u64 = 0x0101_0101_0101_0101;
    const SEVEN: u64 = 0x7f7f_7f7f_7f7f_7f7f;
    let end = stop.min(hay.len());
    if from >= end {
        return None;
    }
    // The high bit of each byte of `x` that is zero, and of no other.
    let zeros = |x: u64| !(((x & SEVEN).wrapping_add(SEVEN)) | x | SEVEN);
    let (wa, wb) = (LOW * a as u64, LOW * b as u64);
    let mut i = from;
    let mut carry = 0u64;
    while i + 8 <= end {
        let w = u64::from_le_bytes(hay[i..i + 8].try_into().unwrap());
        let ma = zeros(w ^ wa);
        let hit = ((ma << 8) | carry) & zeros(w ^ wb);
        if hit != 0 {
            let at = i + (hit.trailing_zeros() / 8) as usize;
            return Some(at - 1);
        }
        carry = ma >> 56;
        i += 8;
    }
    // The last few bytes, and a pair that starts in the last whole word.
    let start = if i > from && carry != 0 { i - 1 } else { i };
    hay[start..end].windows(2).position(|w| w[0] == a && w[1] == b).map(|k| start + k)
}

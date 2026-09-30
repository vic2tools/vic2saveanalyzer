// Numbers and text as the analyzer's Python writes them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The report and the tables are compared with the Python program's byte for
// byte, so every number that reaches either has to come out as Python would
// have spelled it: `repr` of a float (`1e-05`, `100.0`, `1e+16`), `round(x, n)`
// on the exact binary value, `//` on floats, an int kept apart from a float
// that happens to be whole. `testkit` holds these to Python on millions of
// random values (`vic2scan selftest-fmt`).

/// A number as a Python record holds it: an int stays an int, a float a
/// float, and they print differently (`0` against `0.0`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Num {
    I(i64),
    F(f64),
}

impl Num {
    pub fn as_f64(self) -> f64 {
        match self {
            Num::I(i) => i as f64,
            Num::F(f) => f,
        }
    }

    /// Python's `a + b`.
    pub fn add(self, b: Num) -> Num {
        match (self, b) {
            (Num::I(x), Num::I(y)) => Num::I(x + y),
            (x, y) => Num::F(x.as_f64() + y.as_f64()),
        }
    }

    /// Python's `a > b`, exact across the two kinds for the sizes a save holds.
    pub fn gt(self, b: Num) -> bool {
        match (self, b) {
            (Num::I(x), Num::I(y)) => x > y,
            (x, y) => x.as_f64() > y.as_f64(),
        }
    }

    pub fn truthy(self) -> bool {
        match self {
            Num::I(x) => x != 0,
            Num::F(x) => x != 0.0,
        }
    }

    pub fn push_repr(self, out: &mut String) {
        match self {
            Num::I(i) => push_int(out, i),
            Num::F(f) => push_float(out, f),
        }
    }
}

pub fn push_int(out: &mut String, v: i64) {
    let mut buf = itoa_buf();
    out.push_str(itoa(&mut buf, v));
}

fn itoa_buf() -> [u8; 24] {
    [0u8; 24]
}

fn itoa(buf: &mut [u8; 24], v: i64) -> &str {
    let neg = v < 0;
    let mut n = v.unsigned_abs();
    let mut i = buf.len();
    loop {
        i -= 1;
        buf[i] = b'0' + (n % 10) as u8;
        n /= 10;
        if n == 0 {
            break;
        }
    }
    if neg {
        i -= 1;
        buf[i] = b'-';
    }
    // Safe: ASCII digits and a sign.
    unsafe { std::str::from_utf8_unchecked(&buf[i..]) }
}

/// A few dozen bytes on the stack that `write!` can fill: the shortest
/// digits are asked of Rust's formatter without a String for every number.
struct Stack {
    b: [u8; 48],
    n: usize,
}

impl std::fmt::Write for Stack {
    fn write_str(&mut self, s: &str) -> std::fmt::Result {
        let end = self.n + s.len();
        if end > self.b.len() {
            return Err(std::fmt::Error);
        }
        self.b[self.n..end].copy_from_slice(s.as_bytes());
        self.n = end;
        Ok(())
    }
}

/// The shortest digits that read back as `v` (v finite, > 0), into `out`,
/// and (how many, the decimal point's place): v = 0.d1d2... x 10^decpt.
fn shortest(v: f64, out: &mut [u8; 24]) -> (usize, i32) {
    // Rust's `{:e}` gives the shortest round-tripping digits, the closest of
    // them to the value, as Python's repr does (David Gay's mode 0) -- except
    // when the value sits exactly halfway between two such spellings, where
    // Rust rounds up and Python to the even digit: 267406172.666015625 is
    // `...62` in Python and `...63` here. Those ties are found exactly and
    // turned the other way.
    use std::fmt::Write as _;
    let mut st = Stack { b: [0; 48], n: 0 };
    write!(st, "{:e}", v).unwrap();
    let text = &st.b[..st.n];
    let e_at = text.iter().position(|&c| c == b'e').unwrap();
    let mut n = 0;
    for &c in &text[..e_at] {
        if c != b'.' {
            out[n] = c;
            n += 1;
        }
    }
    let exp_text = std::str::from_utf8(&text[e_at + 1..]).unwrap();
    let decpt = exp_text.parse::<i32>().unwrap() + 1;
    if n > 1 && (out[n - 1] - b'0') % 2 == 1 {
        let digits = std::str::from_utf8(&out[..n]).unwrap();
        if let Some((other, d)) = even_neighbour(v, digits, decpt) {
            out[..other.len()].copy_from_slice(other.as_bytes());
            return (other.len(), d);
        }
    }
    (n, decpt)
}

/// For a tie -- `v` exactly half a last digit away from `digits` -- the
/// even spelling on the other side, if it reads back as `v` too.
fn even_neighbour(v: f64, digits: &str, decpt: i32) -> Option<(String, i32)> {
    let d: u128 = digits.parse().ok()?;
    let n = digits.len() as i32;
    let t = decpt - n; // the last digit stands for 10^t
    let bits = v.to_bits();
    let exp_bits = ((bits >> 52) & 0x7ff) as i32;
    let frac = bits & ((1u64 << 52) - 1);
    let (m, e) = if exp_bits == 0 { (frac, -1074) } else { (frac | 1 << 52, exp_bits - 1075) };
    let tz = m.trailing_zeros() as i32;
    let (m, e) = (m >> tz, e + tz);
    // v * 10^(1 - t) must be the whole number 10d +- 5.
    let scaled: u128 = if e < 0 {
        let f = -e; // decimal places the exact value has
        if f != 1 - t || f > 27 {
            return None;
        }
        m as u128 * 5u128.pow(f as u32)
    } else {
        // A whole number: v / 10^(t - 1), exactly.
        if t < 1 || e > 70 {
            return None;
        }
        let whole = (m as u128) << e;
        let p = 10u128.checked_pow((t - 1) as u32)?;
        if whole % p != 0 {
            return None;
        }
        whole / p
    };
    let other = if scaled == 10 * d - 5 {
        d - 1
    } else if scaled == 10 * d + 5 {
        d + 1
    } else {
        return None;
    };
    let mut text = other.to_string();
    let decpt = decpt + text.len() as i32 - n;
    while text.len() > 1 && text.ends_with('0') {
        text.pop();
    }
    let back: f64 = format!("0.{}e{}", text, decpt).parse().ok()?;
    if back == v { Some((text, decpt)) } else { None }
}

/// `repr(v)` for a float.
pub fn push_float(out: &mut String, v: f64) {
    if v.is_nan() {
        out.push_str("nan");
        return;
    }
    if v.is_infinite() {
        out.push_str(if v > 0.0 { "inf" } else { "-inf" });
        return;
    }
    if v == 0.0 {
        out.push_str(if v.is_sign_negative() { "-0.0" } else { "0.0" });
        return;
    }
    // A whole number under 10^15 is its digits and `.0`, which is most of
    // what the tables hold: levels, counts made floats by a sum.
    if v == v.trunc() && v.abs() < 1e15 {
        push_int(out, v as i64);
        out.push_str(".0");
        return;
    }
    if v < 0.0 {
        out.push('-');
    }
    let mut buf = [0u8; 24];
    let (n, decpt) = shortest(v.abs(), &mut buf);
    // Safe: ASCII digits.
    let digits = unsafe { std::str::from_utf8_unchecked(&buf[..n]) };
    let n = n as i32;
    if decpt <= -4 || decpt > 16 {
        out.push_str(&digits[..1]);
        if n > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        let e = decpt - 1;
        out.push('e');
        out.push(if e < 0 { '-' } else { '+' });
        let a = e.unsigned_abs();
        if a < 10 {
            out.push('0');
        }
        push_int(out, a as i64);
    } else if decpt <= 0 {
        out.push_str("0.");
        for _ in 0..(-decpt) {
            out.push('0');
        }
        out.push_str(digits);
    } else if decpt >= n {
        out.push_str(digits);
        for _ in 0..(decpt - n) {
            out.push('0');
        }
        out.push_str(".0");
    } else {
        out.push_str(&digits[..decpt as usize]);
        out.push('.');
        out.push_str(&digits[decpt as usize..]);
    }
}

const POW10: [f64; 23] = [
    1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e13, 1e14, 1e15,
    1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22,
];

/// Python's `round(x, n)` for 0 <= n <= 17: the exact binary value rounded
/// to n decimals, halves to even, read back as the nearest float.
pub fn round(x: f64, n: u32) -> f64 {
    if !x.is_finite() || x == 0.0 {
        return x;
    }
    assert!(n <= 17);
    let bits = x.to_bits();
    let neg = bits >> 63 != 0;
    let exp_bits = ((bits >> 52) & 0x7ff) as i32;
    let frac = bits & ((1u64 << 52) - 1);
    let (mant, exp) = if exp_bits == 0 {
        (frac, -1074)
    } else {
        (frac | (1u64 << 52), exp_bits - 1075)
    };
    if exp >= 0 {
        return x; // already a whole number
    }
    let shift = (-exp) as u32;
    let scaled = mant as u128 * 10u128.pow(n);
    let q = if shift >= 128 {
        // Below 2^-18 of a unit in the last place kept: rounds to nothing.
        0u128
    } else {
        let q = scaled >> shift;
        let rem = scaled & ((1u128 << shift) - 1);
        let half = 1u128 << (shift - 1);
        if rem > half || (rem == half && q & 1 == 1) { q + 1 } else { q }
    };
    let mag = if q == 0 {
        0.0
    } else if q < (1u128 << 53) {
        // Both exact, and one IEEE division is correctly rounded.
        q as f64 / POW10[n as usize]
    } else {
        format!("{}e-{}", q, n).parse::<f64>().unwrap()
    };
    if neg { -mag } else { mag }
}

/// Python's `sum(floats)` from its default start of 0, as CPython 3.12 and
/// later add it: the first item as it is, the rest with Neumaier's
/// compensation, the compensation added at the end. Plain left-to-right
/// addition differs from it in the last place often enough to show in a
/// rounded total (`2758.73` against `2758.74`). None for no items, where
/// Python's answer is the int 0.
pub fn py_sum(items: impl IntoIterator<Item = f64>) -> Option<f64> {
    let mut it = items.into_iter();
    let mut f = 0.0f64 + it.next()?;
    let mut c = 0.0f64;
    for x in it {
        let t = f + x;
        if f.abs() >= x.abs() {
            c += (f - t) + x;
        } else {
            c += (x - t) + f;
        }
        f = t;
    }
    if c != 0.0 && c.is_finite() {
        f += c;
    }
    Some(f)
}

/// Python's `a // b` for floats (`_float_div_mod`).
pub fn floordiv(vx: f64, wx: f64) -> f64 {
    let mut m = vx % wx;
    let mut div = (vx - m) / wx;
    if m != 0.0 {
        if (wx < 0.0) != (m < 0.0) {
            m += wx;
            div -= 1.0;
        }
    }
    let _ = m;
    if div != 0.0 {
        let mut f = div.floor();
        if div - f > 0.5 {
            f += 1.0;
        }
        f
    } else {
        (0.0f64).copysign(vx / wx)
    }
}

/// Python's `int(v)` for a float: truncation. None where Python would raise.
pub fn trunc_int(v: f64) -> Option<i64> {
    if !v.is_finite() {
        return None;
    }
    let t = v.trunc();
    if t >= -9.223372036854775e18 && t <= 9.223372036854775e18 {
        Some(t as i64)
    } else {
        None
    }
}

/// Python's `str.isspace()` for one character, which is what `str.strip()`
/// and `float()` trim.
pub fn py_space_char(c: char) -> bool {
    matches!(c, '\t'..='\r' | '\x1c'..='\x1f' | ' ' | '\u{85}' | '\u{a0}' | '\u{1680}'
        | '\u{2000}'..='\u{200a}' | '\u{2028}' | '\u{2029}' | '\u{202f}' | '\u{205f}'
        | '\u{3000}')
}

/// Python's `float(s)` for a str: None for the ValueError. Underscores are
/// taken where Python takes them, one between two digits, as
/// `modread::py_float` takes them for the save's own text.
pub fn py_float(s: &str) -> Option<f64> {
    // Not quite `str.strip()`: `float()` maps non-ASCII whitespace to spaces
    // and then trims C's six, so `\x1c`-`\x1f`, which `isspace` calls space,
    // stay and make it a ValueError.
    let t = s.trim_matches(|c: char| {
        matches!(c, '\t'..='\r' | ' ') || (c as u32 >= 0x80 && py_space_char(c))
    });
    let owned;
    let t = if t.contains('_') {
        let b = t.as_bytes();
        for (i, &c) in b.iter().enumerate() {
            if c == b'_' && (i == 0 || i + 1 == b.len() || !b[i - 1].is_ascii_digit()
                             || !b[i + 1].is_ascii_digit()) {
                return None;
            }
        }
        owned = t.replace('_', "");
        owned.as_str()
    } else {
        t
    };
    if t.is_empty() {
        return None;
    }
    let body = t.strip_prefix(['+', '-']).unwrap_or(t);
    let lower = body.to_ascii_lowercase();
    if lower == "inf" || lower == "infinity" || lower == "nan" {
        let v = if lower == "nan" { f64::NAN } else { f64::INFINITY };
        return Some(if t.starts_with('-') { -v } else { v });
    }
    let b = body.as_bytes();
    let mut j = 0;
    let digits = |j: &mut usize| {
        let s = *j;
        while *j < b.len() && b[*j].is_ascii_digit() {
            *j += 1;
        }
        *j - s
    };
    let whole = digits(&mut j);
    let mut frac = 0;
    if j < b.len() && b[j] == b'.' {
        j += 1;
        frac = digits(&mut j);
    }
    if whole == 0 && frac == 0 {
        return None;
    }
    if j < b.len() && (b[j] == b'e' || b[j] == b'E') {
        j += 1;
        if j < b.len() && (b[j] == b'+' || b[j] == b'-') {
            j += 1;
        }
        if digits(&mut j) == 0 {
            return None;
        }
    }
    if j != b.len() {
        return None;
    }
    t.parse::<f64>().ok()
}

// ------------------------------------------------------------------- JSON

/// A string as `json.dumps` writes it: ensure_ascii, so everything outside
/// printable ASCII is a `\u` escape (a surrogate pair above the BMP).
pub fn push_json_str(out: &mut String, s: &str) {
    out.push('"');
    let bytes = s.as_bytes();
    let mut start = 0;
    for (i, &b) in bytes.iter().enumerate() {
        if (0x20..0x7f).contains(&b) && b != b'"' && b != b'\\' {
            continue;
        }
        if b >= 0x80 && !s.is_char_boundary(i) {
            continue;
        }
        out.push_str(&s[start..i]);
        if b >= 0x80 {
            let c = s[i..].chars().next().unwrap();
            let mut units = [0u16; 2];
            for u in c.encode_utf16(&mut units) {
                push_u_escape(out, *u as u32);
            }
            start = i + c.len_utf8();
            continue;
        }
        match b {
            b'"' => out.push_str("\\\""),
            b'\\' => out.push_str("\\\\"),
            b'\n' => out.push_str("\\n"),
            b'\r' => out.push_str("\\r"),
            b'\t' => out.push_str("\\t"),
            0x08 => out.push_str("\\b"),
            0x0c => out.push_str("\\f"),
            _ => push_u_escape(out, b as u32),
        }
        start = i + 1;
    }
    out.push_str(&s[start..]);
    out.push('"');
}

fn push_u_escape(out: &mut String, u: u32) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    out.push_str("\\u");
    for shift in [12, 8, 4, 0] {
        out.push(HEX[((u >> shift) & 0xf) as usize] as char);
    }
}

/// A float as `json.dumps` writes it.
pub fn push_json_float(out: &mut String, v: f64) {
    if v.is_nan() {
        out.push_str("NaN");
    } else if v.is_infinite() {
        out.push_str(if v > 0.0 { "Infinity" } else { "-Infinity" });
    } else {
        push_float(out, v);
    }
}

// -------------------------------------------------------------------- CSV

/// One field as Python's `csv.writer` (the excel dialect) writes it: quoted
/// when it holds the delimiter, a quote or a line break, quotes doubled.
pub fn push_csv_field(out: &mut String, s: &str) {
    if s.bytes().any(|b| b == b',' || b == b'"' || b == b'\r' || b == b'\n') {
        out.push('"');
        for c in s.chars() {
            if c == '"' {
                out.push('"');
            }
            out.push(c);
        }
        out.push('"');
    } else {
        out.push_str(s);
    }
}

/// Selftest: read lines from stdin and answer each, for a Python check to
/// compare with its own. `f HEX` -> repr; `r HEX N` -> repr(round(x, N));
/// `d HEX HEX` -> repr(a // b); `j TEXT` -> json.dumps of the text as hex
/// utf-8; `p TEXT` -> repr(float(text)) or `E`.
pub fn selftest() {
    use std::io::{BufRead, Write};
    let stdin = std::io::stdin();
    let stdout = std::io::stdout();
    let mut out = std::io::BufWriter::new(stdout.lock());
    let hexf = |h: &str| f64::from_bits(u64::from_str_radix(h, 16).unwrap());
    for line in stdin.lock().lines() {
        let line = line.unwrap();
        let mut parts = line.splitn(3, ' ');
        let op = parts.next().unwrap_or("");
        let mut s = String::new();
        match op {
            "f" => push_float(&mut s, hexf(parts.next().unwrap())),
            "r" => {
                let x = hexf(parts.next().unwrap());
                let n: u32 = parts.next().unwrap().parse().unwrap();
                push_float(&mut s, round(x, n));
            }
            "d" => {
                let a = hexf(parts.next().unwrap());
                let b = hexf(parts.next().unwrap());
                push_float(&mut s, floordiv(a, b));
            }
            "j" => {
                let raw: Vec<u8> = (0..parts.next().unwrap_or("").len() / 2)
                    .map(|i| u8::from_str_radix(&line[2 + 2 * i..4 + 2 * i], 16).unwrap())
                    .collect();
                push_json_str(&mut s, &String::from_utf8(raw).unwrap());
            }
            "s" => {
                let xs: Vec<f64> = line[2..].split(' ').filter(|h| !h.is_empty()).map(hexf).collect();
                match py_sum(xs) {
                    Some(v) => push_float(&mut s, v),
                    None => s.push('0'),
                }
            }
            "b" => push_float(&mut s, crate::text::to_float_b(line.get(2..).unwrap_or("").as_bytes())),
            "p" => match py_float(line.get(2..).unwrap_or("")) {
                Some(v) => push_float(&mut s, v),
                None => s.push('E'),
            },
            _ => s.push('?'),
        }
        writeln!(out, "{}", s).unwrap();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn floats_take_underscores_where_python_does() {
        assert_eq!(py_float("1_000"), Some(1000.0));
        assert_eq!(py_float(" 1_0.5_0 "), Some(10.5));
        for bad in ["_1", "1_", "1__0", "1_.5", "1._5"] {
            assert_eq!(py_float(bad), None, "{}", bad);
        }
    }
}

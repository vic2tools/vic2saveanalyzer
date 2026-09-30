// JSON read in, and written back out the way Python's `json.dumps` writes it.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// What the analyzer hands the report engine -- the run's settings and the
// mod it has read -- comes as JSON written by Python, and some of it goes
// into the report as it came (the technology tree, the culture names). An
// object keeps its keys in order, an int stays apart from a float, and
// writing a value back out gives the text `json.dumps(value,
// separators=(",", ":"))` gave.

use crate::pyfmt::{push_int, push_json_float, push_json_str};

#[derive(Debug, Clone, PartialEq)]
pub enum J {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    List(Vec<J>),
    Obj(Vec<(String, J)>),
}

impl J {
    pub fn get(&self, key: &str) -> Option<&J> {
        match self {
            J::Obj(pairs) => pairs.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    /// `self[key]`, or Null.
    pub fn at(&self, key: &str) -> &J {
        static NULL: J = J::Null;
        self.get(key).unwrap_or(&NULL)
    }

    pub fn str(&self) -> &str {
        match self {
            J::Str(s) => s,
            _ => "",
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            J::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn int(&self) -> i64 {
        match self {
            J::Int(i) => *i,
            J::Float(f) => *f as i64,
            J::Bool(b) => *b as i64,
            _ => 0,
        }
    }

    pub fn float(&self) -> f64 {
        match self {
            J::Int(i) => *i as f64,
            J::Float(f) => *f,
            _ => 0.0,
        }
    }

    pub fn truthy(&self) -> bool {
        match self {
            J::Null => false,
            J::Bool(b) => *b,
            J::Int(i) => *i != 0,
            J::Float(f) => *f != 0.0,
            J::Str(s) => !s.is_empty(),
            J::List(v) => !v.is_empty(),
            J::Obj(v) => !v.is_empty(),
        }
    }

    pub fn list(&self) -> &[J] {
        match self {
            J::List(v) => v,
            _ => &[],
        }
    }

    pub fn pairs(&self) -> &[(String, J)] {
        match self {
            J::Obj(v) => v,
            _ => &[],
        }
    }

    pub fn is_null(&self) -> bool {
        matches!(self, J::Null)
    }

    /// This value as `json.dumps(value, separators=(",", ":"))` writes it.
    pub fn write(&self, out: &mut String) {
        match self {
            J::Null => out.push_str("null"),
            J::Bool(true) => out.push_str("true"),
            J::Bool(false) => out.push_str("false"),
            J::Int(i) => push_int(out, *i),
            J::Float(f) => push_json_float(out, *f),
            J::Str(s) => push_json_str(out, s),
            J::List(v) => {
                out.push('[');
                for (i, x) in v.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    x.write(out);
                }
                out.push(']');
            }
            J::Obj(v) => {
                out.push('{');
                for (i, (k, x)) in v.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    push_json_str(out, k);
                    out.push(':');
                    x.write(out);
                }
                out.push('}');
            }
        }
    }
}

pub fn parse(text: &str) -> Result<J, String> {
    let mut p = Parser { b: text.as_bytes(), s: text, i: 0 };
    p.ws();
    let v = p.value()?;
    p.ws();
    if p.i != p.b.len() {
        return Err(format!("trailing text at {}", p.i));
    }
    Ok(v)
}

struct Parser<'a> {
    b: &'a [u8],
    s: &'a str,
    i: usize,
}

impl<'a> Parser<'a> {
    fn ws(&mut self) {
        while self.i < self.b.len() && matches!(self.b[self.i], b' ' | b'\t' | b'\n' | b'\r') {
            self.i += 1;
        }
    }

    fn eat(&mut self, lit: &str) -> bool {
        if self.s[self.i..].starts_with(lit) {
            self.i += lit.len();
            true
        } else {
            false
        }
    }

    fn value(&mut self) -> Result<J, String> {
        if self.i >= self.b.len() {
            return Err("unexpected end".into());
        }
        match self.b[self.i] {
            b'{' => {
                self.i += 1;
                let mut pairs = Vec::new();
                self.ws();
                if self.eat("}") {
                    return Ok(J::Obj(pairs));
                }
                loop {
                    self.ws();
                    let k = self.string()?;
                    self.ws();
                    if !self.eat(":") {
                        return Err(format!("expected : at {}", self.i));
                    }
                    self.ws();
                    let v = self.value()?;
                    pairs.push((k, v));
                    self.ws();
                    if self.eat(",") {
                        continue;
                    }
                    if self.eat("}") {
                        return Ok(J::Obj(pairs));
                    }
                    return Err(format!("expected , or }} at {}", self.i));
                }
            }
            b'[' => {
                self.i += 1;
                let mut items = Vec::new();
                self.ws();
                if self.eat("]") {
                    return Ok(J::List(items));
                }
                loop {
                    self.ws();
                    items.push(self.value()?);
                    self.ws();
                    if self.eat(",") {
                        continue;
                    }
                    if self.eat("]") {
                        return Ok(J::List(items));
                    }
                    return Err(format!("expected , or ] at {}", self.i));
                }
            }
            b'"' => Ok(J::Str(self.string()?)),
            _ => {
                for (lit, v) in [("true", J::Bool(true)), ("false", J::Bool(false)),
                                 ("null", J::Null), ("NaN", J::Float(f64::NAN)),
                                 ("Infinity", J::Float(f64::INFINITY)),
                                 ("-Infinity", J::Float(f64::NEG_INFINITY))] {
                    if self.eat(lit) {
                        return Ok(v);
                    }
                }
                self.number()
            }
        }
    }

    fn number(&mut self) -> Result<J, String> {
        let start = self.i;
        let mut float = false;
        while self.i < self.b.len() {
            match self.b[self.i] {
                b'0'..=b'9' | b'-' | b'+' => {}
                b'.' | b'e' | b'E' => float = true,
                _ => break,
            }
            self.i += 1;
        }
        let t = &self.s[start..self.i];
        if t.is_empty() {
            return Err(format!("unexpected character at {}", start));
        }
        if !float {
            if let Ok(v) = t.parse::<i64>() {
                return Ok(J::Int(v));
            }
        }
        t.parse::<f64>().map(J::Float).map_err(|_| format!("bad number {}", t))
    }

    fn hex4(&mut self) -> Result<u32, String> {
        let h = self.s.get(self.i..self.i + 4).ok_or("short escape")?;
        self.i += 4;
        u32::from_str_radix(h, 16).map_err(|_| "bad escape".to_string())
    }

    fn string(&mut self) -> Result<String, String> {
        if !self.eat("\"") {
            return Err(format!("expected string at {}", self.i));
        }
        let mut out = String::new();
        let mut start = self.i;
        loop {
            if self.i >= self.b.len() {
                return Err("unterminated string".into());
            }
            match self.b[self.i] {
                b'"' => {
                    out.push_str(&self.s[start..self.i]);
                    self.i += 1;
                    return Ok(out);
                }
                b'\\' => {
                    out.push_str(&self.s[start..self.i]);
                    self.i += 1;
                    let c = self.b[self.i];
                    self.i += 1;
                    match c {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\x08'),
                        b'f' => out.push('\x0c'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let mut u = self.hex4()?;
                            if (0xd800..0xdc00).contains(&u) && self.s[self.i..].starts_with("\\u") {
                                let save = self.i;
                                self.i += 2;
                                let lo = self.hex4()?;
                                if (0xdc00..0xe000).contains(&lo) {
                                    u = 0x10000 + ((u - 0xd800) << 10) + (lo - 0xdc00);
                                } else {
                                    self.i = save;
                                }
                            }
                            out.push(char::from_u32(u).unwrap_or('\u{fffd}'));
                        }
                        _ => return Err("bad escape".into()),
                    }
                    start = self.i;
                }
                _ => self.i += 1,
            }
        }
    }
}

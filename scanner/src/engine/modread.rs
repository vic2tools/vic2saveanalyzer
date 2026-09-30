// A mod folder read the way `mod_reader.py` reads it.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// What comes out is what `export_mod` (`testkit/modexport.py`) makes of the
// `Mod` Python reads -- every field the engine uses, in JSON's terms -- so
// the two are held to each other as text (`testkit/modread.py`), and the
// engine reads either one the same way.
//
// Each function below is its namesake in `mod_reader.py`, rule for rule,
// and the regular expressions are Python's own, run by `pyre`. The texts
// are latin-1, a byte to a character, except the localisation, which the
// game writes in Windows-1252 and Python decodes that way. Where Python
// would raise -- a number `float()` refuses, a file it cannot open -- this
// declines, and the analyzer reads the mod in Python, which raises as it
// always did.

use crate::clause::{parse, tokens, unquote, V};
use crate::engine::rules::{Decline, D};
use crate::jsonr::J;
use crate::omap::OMap;
use crate::pyfmt::py_space_char;
use crate::pyre::{space, word, Re};
use std::cell::RefCell;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::rc::Rc;

type Set = BTreeSet<Vec<u8>>;

fn no<T>(why: impl Into<String>) -> D<T> {
    Err(Decline(why.into()))
}

/// What marks a decline as an exception Python raises and the analyzer
/// turns into a sentence (`RunError(str(exc))`): the rest of the message is
/// that sentence, word for word.
const RAISED: &str = "\u{1}raised: ";

fn raised<T>(sentence: impl Into<String>) -> D<T> {
    Err(Decline(format!("{}{}", RAISED, sentence.into())))
}

/// The sentence Python refuses the run with, when this is one.
pub fn raised_sentence(d: &Decline) -> Option<&str> {
    d.0.strip_prefix(RAISED)
}

/// latin-1 bytes as the str Python decoded them to.
pub fn l1(b: &[u8]) -> String {
    b.iter().map(|&c| c as char).collect()
}

fn js(b: &[u8]) -> J {
    J::Str(l1(b))
}

// ------------------------------------------------------------ paths

#[cfg(windows)]
const SEP: char = '\\';
#[cfg(not(windows))]
const SEP: char = '/';

fn is_sep(c: char) -> bool {
    c == '/' || (cfg!(windows) && c == '\\')
}

/// `os.path.join(a, b)`.
#[cfg(not(windows))]
pub fn join(a: &str, b: &str) -> String {
    if b.starts_with('/') {
        b.to_string()
    } else if a.is_empty() || a.ends_with('/') {
        format!("{}{}", a, b)
    } else {
        format!("{}/{}", a, b)
    }
}

/// `os.path.join(a, b)`, ntpath's: a part with a root keeps the drive
/// before it, a part with another drive starts again.
#[cfg(windows)]
pub fn join(a: &str, b: &str) -> String {
    fn drive(p: &str) -> &str {
        let c: Vec<char> = p.chars().take(2).collect();
        if c.len() == 2 && c[1] == ':' && c[0].is_ascii_alphabetic() { &p[..2] } else { "" }
    }
    let (ad, bd) = (drive(a), drive(b));
    let b_rest = &b[bd.len()..];
    if b_rest.starts_with(is_sep) {
        return if !bd.is_empty() || ad.is_empty() { b.to_string() } else { format!("{}{}", ad, b_rest) };
    }
    if !bd.is_empty() && !bd.eq_ignore_ascii_case(ad) {
        return b.to_string();
    }
    let a_rest = &a[ad.len()..];
    if a_rest.is_empty() || a_rest.ends_with(is_sep) {
        format!("{}{}", a, b_rest)
    } else {
        format!("{}{}{}", a, SEP, b_rest)
    }
}

fn joins(a: &str, parts: &[&str]) -> String {
    parts.iter().fold(a.to_string(), |acc, p| join(&acc, p))
}

/// `os.path.dirname`, for an absolute path.
fn dirname(p: &str) -> String {
    match p.rfind(is_sep) {
        None => String::new(),
        Some(i) => {
            let head = &p[..i + 1];
            let trimmed = head.trim_end_matches(is_sep);
            if trimmed.is_empty() || (cfg!(windows) && trimmed.ends_with(':')) {
                head.to_string()
            } else {
                trimmed.to_string()
            }
        }
    }
}

fn basename(p: &str) -> &str {
    match p.rfind(is_sep) {
        None => p,
        Some(i) => &p[i + 1..],
    }
}

fn is_file(p: &str) -> bool {
    std::path::Path::new(p).is_file()
}

fn is_dir(p: &str) -> bool {
    std::path::Path::new(p).is_dir()
}

/// `str.lower()`.
fn lower(s: &str) -> String {
    s.to_lowercase()
}

/// `os.listdir`, in the order the folder gives: None when it cannot be
/// listed, a decline for a name Python would hold as undecodable.
fn listdir(folder: &str) -> D<Option<Vec<String>>> {
    let rd = match std::fs::read_dir(folder) {
        Ok(rd) => rd,
        Err(_) => return Ok(None),
    };
    let mut out = Vec::new();
    for e in rd {
        let e = match e {
            Ok(e) => e,
            Err(e) => return no(format!("listing {}: {}", folder, e)),
        };
        match e.file_name().into_string() {
            Ok(s) => out.push(s),
            Err(_) => return no(format!("a file name in {} is not text", folder)),
        }
    }
    Ok(Some(out))
}

// ------------------------------------------------------- Python's numbers

/// What `float()` and `int()` trim from a str: C's whitespace and the
/// non-ASCII spaces, which leaves `\x1c`-`\x1f` in.
fn num_space(c: u8) -> bool {
    matches!(c, 0x09..=0x0d | 0x20 | 0x85 | 0xa0)
}

fn num_trim(s: &[u8]) -> &[u8] {
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
fn must_float(s: &[u8]) -> D<f64> {
    match py_float(s) {
        Some(v) => Ok(v),
        None => raised(format!("could not convert string to float: {}", py_repr(&l1(s)))),
    }
}

/// `to_float(value, default)`.
fn to_float(v: Option<&V>, default: f64) -> f64 {
    match v {
        Some(V::Str(s)) => py_float(s).unwrap_or(default),
        _ => default,
    }
}

/// `to_int(value, default)`: `int(float(value))`, whose OverflowError on
/// an infinity nothing catches.
fn to_int(v: Option<&V>, default: i64) -> D<i64> {
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
fn digit_word(w: &[u8]) -> D<bool> {
    if w.is_empty() || !w.iter().all(|&c| c.is_ascii_digit() || matches!(c, 0xb2 | 0xb3 | 0xb9)) {
        return Ok(false);
    }
    if w.iter().any(|&c| !c.is_ascii_digit()) {
        return raised(format!("invalid literal for int() with base 10: {}", py_repr(&l1(w))));
    }
    Ok(true)
}

/// `str.split()`.
fn split_ws(b: &[u8]) -> impl Iterator<Item = &[u8]> {
    b.split(|&c| space(c)).filter(|w| !w.is_empty())
}

/// `str.strip()` for latin-1 text.
fn strip(b: &[u8]) -> &[u8] {
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
fn lower1(b: &[u8]) -> Vec<u8> {
    b.iter().map(|&c| match c {
        b'A'..=b'Z' => c + 32,
        0xc0..=0xde if c != 0xd7 => c + 32,
        _ => c,
    }).collect()
}

/// `repr()` of a value, for the places Python calls `str()` on what may be
/// a block.
fn repr(v: &V, out: &mut String) {
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

fn repr_str(s: &[u8], out: &mut String) {
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

fn is_dict(v: &V) -> bool {
    matches!(v, V::Dict(_))
}

fn pairs(v: &V) -> &[(Vec<u8>, V)] {
    match v {
        V::Dict(d) => &d.pairs,
        _ => &[],
    }
}

fn get<'v>(v: &'v V, key: &[u8]) -> Option<&'v V> {
    match v {
        V::Dict(d) => d.get(key),
        _ => None,
    }
}

/// A parsed value in JSON's terms, as `json.dumps` would write the tree.
fn tree_json(v: &V) -> J {
    match v {
        V::Str(s) => js(s),
        V::List(x) | V::Multi(x) => J::List(x.iter().map(tree_json).collect()),
        V::Dict(d) => J::Obj(d.pairs.iter().map(|(k, e)| (l1(k), tree_json(e))).collect()),
    }
}

fn sorted_json(s: &Set) -> J {
    J::List(s.iter().map(|x| js(x)).collect())
}

// ------------------------------------------------------------- the reader

struct Pats {
    comment: Re,
    opens: Re,
    not_block: Re,
    limit: Re,
    req: Re,
    tag: Re,
    invention: Re,
    chance: Re,
    base: Re,
    modifier: Re,
    factor: Re,
    blocked: Re,
    lua_comment: Re,
    strata: Re,
    country_entry: Re,
    war_policy: Re,
    word_block: Re,
    impact: Re,
    region: Re,
    line_block: Re,
    unit_type: Re,
    klass: Re,
    ship_block: Re,
    ship_stat: Re,
    color: Re,
    sea: Re,
    change_tag: Re,
    tag3: Re,
}

impl Pats {
    fn new() -> Pats {
        Pats {
            comment: Re::new(r"#[^\r\n]*"),
            opens: Re::new(r"\s*=\s*\{"),
            not_block: Re::with(r"NOT\s*=\s*\{(?:[^{}]|\{[^{}]*\})*\}", false, true),
            limit: Re::new(r"limit\s*=\s*\{"),
            req: Re::new(r"([a-z_][a-z_0-9]*)\s*=\s*1\b"),
            tag: Re::new(r"tag\s*=\s*(\w+)"),
            invention: Re::new(r"invention\s*=\s*(\w+)"),
            chance: Re::new(r"chance\s*=\s*\{"),
            base: Re::new(r"base\s*=\s*([-\d.]+)"),
            modifier: Re::with(r"modifier\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", false, true),
            factor: Re::new(r"factor\s*=\s*([-\d.]+)"),
            blocked: Re::with(r"NOT\s*=\s*\{\s*invention\s*=\s*(\w+)\s*\}", false, true),
            lua_comment: Re::new(r"--.*"),
            strata: Re::new(r"(?<![\w.])strata\s*=\s*(\w+)"),
            country_entry: Re::with(r#"^\s*([A-Z0-9]{3})\s*=\s*"?([^"\r\n]+?)"?\s*$"#, true, false),
            war_policy: Re::new(r"war_policy\s*=\s*(\w+)"),
            word_block: Re::new(r"(\w+)\s*=\s*\{"),
            impact: Re::new(r"mobilization_impact\s*=\s*([-\d.]+)"),
            region: Re::new(r"([A-Za-z0-9_]+)\s*=\s*\{([^{}]*)\}"),
            line_block: Re::with(r"^(\w+)\s*=\s*\{", true, false),
            unit_type: Re::new(r"(?<![\w_])type\s*=\s*(\w+)"),
            klass: Re::new(r"(?<![\w_])unit_type\s*=\s*(\w+)"),
            ship_block: Re::new(r"(\w+)\s*=\s*\{([^{}]*)\}"),
            ship_stat: Re::new(r"(\w+)\s*=\s*([-\d.]+)"),
            color: Re::new(r"color\s*=\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}"),
            sea: Re::new(r"sea_starts\s*=\s*\{([^}]*)\}"),
            change_tag: Re::new(r"change_tag(?:_no_core_switch)?\s*=\s*([A-Z0-9]{3})\b"),
            tag3: Re::new(r"(?<![\w_])tag\s*=\s*([A-Z0-9]{3})\b"),
        }
    }
}

type Top = Rc<Vec<(Vec<u8>, V)>>;

/// One line of a localisation file with a name on it: its key, its first
/// column, and whether the line is a comment.
struct Loc {
    key: String,
    english: String,
    hash: bool,
}

pub struct Reader {
    path: String,
    base: Option<String>,
    re: Pats,
    plain: RefCell<HashMap<String, Rc<Vec<u8>>>>,
    trees: RefCell<HashMap<String, Top>>,
    loc: RefCell<Option<Rc<Vec<Loc>>>>,
}

/// `is_install`: the folder holds the game's map.
pub fn is_install(path: &str) -> bool {
    !path.is_empty() && is_file(&joins(path, &["map", "default.map"]))
}

/// `_base_game_path`, for a path already made absolute.
pub fn base_game_path(path: &str) -> Option<String> {
    if path.is_empty() {
        return None;
    }
    let parent = dirname(path);
    let root = dirname(&parent);
    if lower(basename(&parent)) != "mod" {
        return None;
    }
    if !is_install(&root) {
        return None;
    }
    Some(root)
}

impl Reader {
    pub fn new(path: &str) -> Reader {
        Reader {
            path: path.to_string(),
            base: base_game_path(path),
            re: Pats::new(),
            plain: RefCell::new(HashMap::new()),
            trees: RefCell::new(HashMap::new()),
            loc: RefCell::new(None),
        }
    }

    /// The base game first, then the mod: the order most things are laid
    /// over each other in.
    fn game_then_mod(&self) -> Vec<&str> {
        let mut v = Vec::new();
        if let Some(b) = &self.base {
            v.push(b.as_str());
        }
        v.push(self.path.as_str());
        v
    }

    fn mod_then_game(&self) -> Vec<&str> {
        let mut v = vec![self.path.as_str()];
        if let Some(b) = &self.base {
            v.push(b.as_str());
        }
        v
    }

    fn resolved_file(&self, parts: &[&str]) -> String {
        let own = joins(&self.path, parts);
        if is_file(&own) {
            return own;
        }
        if let Some(root) = &self.base {
            let inherited = joins(root, parts);
            if is_file(&inherited) {
                return inherited;
            }
        }
        own
    }

    /// `_files`: the `.txt` files of a folder, by name without regard to case.
    fn files(folder: &str) -> D<Vec<String>> {
        if !is_dir(folder) {
            return Ok(Vec::new());
        }
        let mut names: Vec<String> = match listdir(folder)? {
            Some(n) => n.into_iter().filter(|f| lower(f).ends_with(".txt")).collect(),
            None => return no(format!("cannot list {}", folder)),
        };
        names.sort_by_cached_key(|n| lower(n));
        Ok(names)
    }

    /// `resolved_files`: (name, the copy the game reads), in load order.
    fn resolved_files(&self, folder: &str) -> D<Vec<(String, String)>> {
        let mut chosen: OMap<String, (String, String)> = OMap::new();
        for root in self.game_then_mod() {
            let target = join(root, folder);
            for name in Reader::files(&target)? {
                let full = join(&target, &name);
                chosen.set(lower(&name), (name, full));
            }
        }
        Ok(chosen.values().cloned().collect())
    }

    fn read(path: &str) -> D<Vec<u8>> {
        std::fs::read(path).or_else(|e| raised(crate::engine::os_error_text(&e, path)))
    }

    /// `_plain`: one file with its comments cut out.
    fn plain(&self, path: &str) -> D<Rc<Vec<u8>>> {
        if let Some(t) = self.plain.borrow().get(path) {
            return Ok(t.clone());
        }
        let raw = Reader::read(path)?;
        let t = Rc::new(self.re.comment.remove(&raw));
        self.plain.borrow_mut().insert(path.to_string(), t.clone());
        Ok(t)
    }

    /// `read_clausewitz`: every top-level `key = { ... }`, in file order.
    fn clausewitz(&self, path: &str) -> D<Top> {
        if let Some(t) = self.trees.borrow().get(path) {
            return Ok(t.clone());
        }
        let text = self.plain(path)?;
        let toks = tokens(&text);
        let mut out = Vec::new();
        let n = toks.len();
        let mut i = 0;
        while i < n {
            let t = toks[i];
            i += 1;
            if t == b"{" || t == b"}" || t == b"=" {
                continue;
            }
            if i >= n {
                break;
            }
            let nxt = toks[i];
            i += 1;
            if nxt != b"=" {
                i -= 1;
                continue;
            }
            if i >= n {
                break;
            }
            let v = toks[i];
            i += 1;
            if v == b"{" {
                let (block, j) = parse(&toks, i);
                i = j;
                out.push((unquote(t).to_vec(), block));
            }
        }
        let top = Rc::new(out);
        self.trees.borrow_mut().insert(path.to_string(), top.clone());
        Ok(top)
    }

    // ------------------------------------------------- text-level helpers

    /// `_block_text(raw, name)`.
    fn block_text<'t>(&self, raw: &'t [u8], name: &[u8]) -> &'t [u8] {
        if name.is_empty() {
            // `str.find("")` finds every position; the first that opens a
            // block is the answer.
            for at in 0..=raw.len() {
                if let Some(t) = self.opens_at(raw, at, 0) {
                    return t;
                }
            }
            return b"";
        }
        let mut from = 0;
        while let Some(off) = find(&raw[from..], name) {
            let at = from + off;
            if let Some(t) = self.opens_at(raw, at, name.len()) {
                return t;
            }
            from = at + 1;
        }
        b""
    }

    fn opens_at<'t>(&self, raw: &'t [u8], at: usize, len: usize) -> Option<&'t [u8]> {
        if at > 0 && (word(raw[at - 1]) || raw[at - 1] == b'.') {
            return None;
        }
        let m = self.re.opens.match_at(raw, at + len)?;
        Some(match block_end(raw, m.end()) {
            Some(end) => &raw[m.end()..end - 1],
            None => b"",
        })
    }

    /// `_limit_of`: (techs, tags, inventions) a `limit` asks for.
    fn limit_of(&self, text: &[u8]) -> (Set, Set, Set) {
        let m = match self.re.limit.search(text, 0) {
            Some(m) => m,
            None => return (Set::new(), Set::new(), Set::new()),
        };
        let body = body_of(text, m.end());
        let positive = self.re.not_block.remove(body);
        let groups = |re: &Re| -> Set {
            re.find_all(&positive).iter().map(|m| m.group(&positive, 1).to_vec()).collect()
        };
        let mut reqs = groups(&self.re.req);
        let tags = groups(&self.re.tag);
        let invs = groups(&self.re.invention);
        reqs.retain(|r| !invs.contains(r));
        (reqs, tags, invs)
    }

    /// `_chance_floor`: (base, [(factor, blocked invention)]).
    fn chance_floor(&self, text: &[u8]) -> D<(Option<f64>, Vec<(f64, Vec<u8>)>)> {
        let m = match self.re.chance.search(text, 0) {
            Some(m) => m,
            None => return Ok((None, Vec::new())),
        };
        let body = body_of(text, m.end());
        let base = self.re.base.search(body, 0);
        let mut pairs = Vec::new();
        for md in self.re.modifier.find_all(body) {
            let inner = md.group(body, 1);
            let factor = self.re.factor.search(inner, 0);
            let blocked = self.re.blocked.search(inner, 0);
            if let (Some(f), Some(b)) = (factor, blocked) {
                pairs.push((must_float(f.group(inner, 1))?, b.group(inner, 1).to_vec()));
            }
        }
        let base = match base {
            Some(b) => Some(must_float(b.group(body, 1))?),
            None => None,
        };
        Ok((base, pairs))
    }

    /// `_named_blocks(text, keyword)`.
    fn named_blocks<'t>(&self, text: &'t [u8], keyword: &[u8]) -> Vec<&'t [u8]> {
        let mut pat = b"\\b".to_vec();
        pat.extend_from_slice(keyword);
        pat.extend_from_slice(b"\\s*=\\s*\\{");
        let re = Re::bytes(&pat, false, false);
        let mut out = Vec::new();
        let mut i = 0;
        while let Some(m) = re.search(text, i) {
            let end = block_end(text, m.end());
            out.push(match end {
                Some(e) => &text[m.end()..e - 1],
                None => &text[m.end()..],
            });
            i = end.unwrap_or(text.len());
        }
        out
    }

    /// `_drop_block(text, keyword)`.
    fn drop_block(&self, text: &[u8], keyword: &[u8]) -> Vec<u8> {
        let mut pat = b"\\b".to_vec();
        pat.extend_from_slice(keyword);
        pat.extend_from_slice(b"\\s*=\\s*\\{");
        let re = Re::bytes(&pat, false, false);
        let mut out = Vec::new();
        let mut i = 0;
        loop {
            match re.search(text, i) {
                None => {
                    out.extend_from_slice(&text[i..]);
                    return out;
                }
                Some(m) => {
                    out.extend_from_slice(&text[i..m.start()]);
                    i = block_end(text, m.end()).unwrap_or(text.len());
                }
            }
        }
    }

    /// `_ship_changes(text)`: {target: {stat: delta}}.
    fn ship_changes(&self, text: &[u8]) -> D<OMap<Vec<u8>, OMap<Vec<u8>, f64>>> {
        let mut found: OMap<Vec<u8>, OMap<Vec<u8>, f64>> = OMap::new();
        for hit in self.re.ship_block.find_all(text) {
            let inner = hit.group(text, 2);
            let mut deltas: OMap<Vec<u8>, f64> = OMap::new();
            for m in self.re.ship_stat.find_all(inner) {
                let stat = m.group(inner, 1);
                if SHIP_STATS.contains(&stat) {
                    deltas.set(stat.to_vec(), must_float(m.group(inner, 2))?);
                }
            }
            if deltas.is_empty() {
                continue;
            }
            let into = found.entry(hit.group(text, 1).to_vec(), OMap::new);
            for (stat, value) in deltas.iter() {
                let was = into.get(stat).copied().unwrap_or(0.0);
                into.set(stat.clone(), was + value);
            }
        }
        Ok(found)
    }

    // ------------------------------------------------------ localisation

    /// Every localisation line with a first column, the mod's files first
    /// and then the game's, each folder in name order.
    fn loc(&self) -> D<Rc<Vec<Loc>>> {
        if let Some(l) = self.loc.borrow().as_ref() {
            return Ok(l.clone());
        }
        let mut out = Vec::new();
        for root in self.mod_then_game() {
            let folder = join(root, "localisation");
            if !is_dir(&folder) {
                continue;
            }
            let mut names = match listdir(&folder)? {
                Some(n) => n,
                None => return no(format!("cannot list {}", folder)),
            };
            names.sort();
            for name in names {
                if !lower(&name).ends_with(".csv") {
                    continue;
                }
                let raw = match std::fs::read(join(&folder, &name)) {
                    Ok(r) => r,
                    Err(_) => continue,
                };
                for line in split_lines(&raw) {
                    let (key, rest) = match line.iter().position(|&c| c == b';') {
                        Some(i) => (&line[..i], &line[i + 1..]),
                        None => (line, &b""[..]),
                    };
                    let first = match rest.iter().position(|&c| c == b';') {
                        Some(i) => &rest[..i],
                        None => rest,
                    };
                    let english = loc_strip(first);
                    if english.is_empty() {
                        continue;
                    }
                    out.push(Loc { key: cp1252(loc_strip(key)), english: cp1252(english),
                                   hash: line.first() == Some(&b'#') });
                }
            }
        }
        let rc = Rc::new(out);
        *self.loc.borrow_mut() = Some(rc.clone());
        Ok(rc)
    }

    /// `_text_localisation(path, wanted)`: in the order the files give.
    fn text_localisation(&self, wanted: &HashSet<String>) -> D<OMap<String, String>> {
        let mut out: OMap<String, String> = OMap::new();
        for l in self.loc()?.iter() {
            if wanted.contains(&l.key) && !out.contains_key(&l.key) {
                out.set(l.key.clone(), l.english.clone());
            }
        }
        Ok(out)
    }

    /// `_read_localisation`: country names, and their per-government forms.
    fn read_localisation(&self) -> D<OMap<String, String>> {
        let mut out: OMap<String, String> = OMap::new();
        for l in self.loc()?.iter() {
            if l.hash || !country_key(&l.key) || out.contains_key(&l.key) {
                continue;
            }
            out.set(l.key.clone(), l.english.clone());
        }
        Ok(out)
    }
}

const SHIP_STATS: [&[u8]; 5] = [b"hull", b"gun_power", b"evasion", b"torpedo_attack",
                                b"supply_consumption_score"];

const NOT_A_CULTURE: [&[u8]; 5] = [b"color", b"unit", b"union", b"leader", b"is_overseas"];

fn find(hay: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.len() > hay.len() {
        return None;
    }
    let first = needle[0];
    let mut i = 0;
    while i + needle.len() <= hay.len() {
        match hay[i..hay.len() - needle.len() + 1].iter().position(|&c| c == first) {
            None => return None,
            Some(off) => {
                i += off;
                if &hay[i..i + needle.len()] == needle {
                    return Some(i);
                }
                i += 1;
            }
        }
    }
    None
}

/// `v2parse.block_end`: past the closing brace, given the start of an open
/// block's body; quoted braces do not count.
pub fn block_end(text: &[u8], start: usize) -> Option<usize> {
    let mut depth = 1i64;
    let mut i = start;
    while depth > 0 {
        let off = text[i..].iter().position(|&c| c == b'"' || c == b'{' || c == b'}')?;
        let at = i + off;
        match text[at] {
            b'"' => {
                let q = text[at + 1..].iter().position(|&c| c == b'"')?;
                i = at + 1 + q + 1;
            }
            b'{' => {
                depth += 1;
                i = at + 1;
            }
            _ => {
                depth -= 1;
                i = at + 1;
            }
        }
    }
    Some(i)
}

/// `text[m.end():end - 1 if end is not None else len(text)]`.
fn body_of(text: &[u8], start: usize) -> &[u8] {
    match block_end(text, start) {
        Some(end) => &text[start..end - 1],
        None => &text[start..],
    }
}

/// `str.splitlines()` of Windows-1252 text, done on the bytes: every byte
/// that ends a line decodes to itself.
fn split_lines(b: &[u8]) -> Vec<&[u8]> {
    let mut out = Vec::new();
    let mut start = 0;
    let mut i = 0;
    while i < b.len() {
        match b[i] {
            b'\r' => {
                out.push(&b[start..i]);
                if i + 1 < b.len() && b[i + 1] == b'\n' {
                    i += 1;
                }
                start = i + 1;
            }
            b'\n' | 0x0b | 0x0c | 0x1c | 0x1d | 0x1e => {
                out.push(&b[start..i]);
                start = i + 1;
            }
            _ => {}
        }
        i += 1;
    }
    if start < b.len() {
        out.push(&b[start..]);
    }
    out
}

/// `str.strip()` of Windows-1252 text, on the bytes: 0x85 is an ellipsis
/// there, not a space.
fn loc_strip(b: &[u8]) -> &[u8] {
    let sp = |c: u8| matches!(c, 0x09..=0x0d | 0x1c..=0x20 | 0xa0);
    let mut a = 0;
    let mut z = b.len();
    while a < z && sp(b[a]) {
        a += 1;
    }
    while z > a && sp(b[z - 1]) {
        z -= 1;
    }
    &b[a..z]
}

const CP1252: [u32; 32] = [
    0x20ac, 0xfffd, 0x201a, 0x0192, 0x201e, 0x2026, 0x2020, 0x2021, 0x02c6, 0x2030, 0x0160,
    0x2039, 0x0152, 0xfffd, 0x017d, 0xfffd, 0xfffd, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022,
    0x2013, 0x2014, 0x02dc, 0x2122, 0x0161, 0x203a, 0x0153, 0xfffd, 0x017e, 0x0178,
];

/// `bytes.decode("cp1252", "replace")`.
pub fn cp1252(b: &[u8]) -> String {
    b.iter().map(|&c| {
        if (0x80..0xa0).contains(&c) {
            char::from_u32(CP1252[(c - 0x80) as usize]).unwrap()
        } else {
            c as char
        }
    }).collect()
}

/// `^[A-Z][A-Z0-9]{2}(_[a-z_]+)?$`, on a stripped key.
fn country_key(k: &str) -> bool {
    let b = k.as_bytes();
    if b.len() < 3 || !b[0].is_ascii_uppercase()
        || !b[1..3].iter().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit())
    {
        return false;
    }
    if b.len() == 3 {
        return true;
    }
    b[3] == b'_' && b.len() > 4 && b[4..].iter().all(|&c| c.is_ascii_lowercase() || c == b'_')
}

/// `_pretty(key)`: underscores to spaces, stripped, capitalised.
fn pretty(key: &str) -> String {
    let s = key.replace('_', " ");
    let s = s.trim_matches(py_space_char);
    let mut chars = s.chars();
    let mut out = String::new();
    if let Some(c) = chars.next() {
        out.push_str(&title(c));
        out.push_str(&chars.as_str().to_lowercase());
    }
    out
}

/// A character's title case, which is its upper case but for a few.
fn title(c: char) -> String {
    match c {
        'ß' => "Ss".into(),
        '\u{1c4}'..='\u{1c6}' => "\u{1c5}".into(),
        '\u{1c7}'..='\u{1c9}' => "\u{1c8}".into(),
        '\u{1ca}'..='\u{1cc}' => "\u{1cb}".into(),
        '\u{1f1}'..='\u{1f3}' => "\u{1f2}".into(),
        'ﬀ' => "Ff".into(),
        'ﬁ' => "Fi".into(),
        'ﬂ' => "Fl".into(),
        'ﬃ' => "Ffi".into(),
        'ﬄ' => "Ffl".into(),
        'ﬅ' | 'ﬆ' => "St".into(),
        c => c.to_uppercase().collect(),
    }
}

/// `os.path.splitext(name)[0]`.
fn stem(name: &str) -> &str {
    let sep = name.rfind(is_sep).map_or(0, |i| i + 1);
    match name.rfind('.') {
        Some(dot) if dot > sep => {
            if name[sep..dot].chars().any(|c| c != '.') { &name[..dot] } else { name }
        }
        _ => name,
    }
}

/// `f[:-4]`.
fn cut4(name: &str) -> &str {
    let mut end = name.len();
    for _ in 0..4 {
        match name[..end].char_indices().next_back() {
            Some((i, _)) => end = i,
            None => break,
        }
    }
    &name[..end]
}

/// `_find_mob_size(block)`: mobilisation size at the top of a block or in
/// its `effect`.
fn find_mob_size(block: &V) -> f64 {
    let mut total = 0.0;
    for (key, val) in pairs(block) {
        if key == b"mobilisation_size" {
            match val {
                V::List(x) | V::Multi(x) => {
                    for v in x {
                        total += to_float(Some(v), 0.0);
                    }
                }
                one => total += to_float(Some(one), 0.0),
            }
        } else if key == b"effect" && is_dict(val) {
            total += find_mob_size(val);
        }
    }
    total
}

/// `_trigger_conditions`: every condition a trigger names.
fn trigger_conditions(trigger: &V, out: &mut HashSet<Vec<u8>>) {
    if !is_dict(trigger) {
        return;
    }
    for (key, value) in pairs(trigger) {
        if key == b"AND" || key == b"OR" || key == b"NOT" {
            for part in crate::clause::as_list(Some(value)) {
                trigger_conditions(part, out);
            }
        } else if is_dict(value) {
            out.insert(key.clone());
            trigger_conditions(value, out);
        } else {
            out.insert(key.clone());
        }
    }
}

/// `_flatten_effects`: (label key, value) for every field that is not
/// bookkeeping.
fn flatten_effects<'a>(block: impl Iterator<Item = &'a (Vec<u8>, V)>, skip: &[&[u8]], prefix: &[u8],
                       out: &mut Vec<(Vec<u8>, Vec<u8>)>) {
    for (key, val) in block {
        if key.first() == Some(&b'_') || skip.contains(&key.as_slice()) {
            continue;
        }
        let mut label = prefix.to_vec();
        label.extend_from_slice(key);
        match val {
            V::Dict(d) => {
                label.extend_from_slice(b": ");
                flatten_effects(d.pairs.iter(), skip, &label, out);
            }
            V::List(x) | V::Multi(x) => {
                for item in x {
                    if let V::Str(s) = item {
                        out.push((label.clone(), s.clone()));
                    }
                }
            }
            V::Str(s) => out.push((label, s.clone())),
        }
    }
}

const TECH_SKIP: [&[u8]; 8] = [b"area", b"year", b"cost", b"ai_chance", b"unciv_military",
                               b"unciv_naval", b"unciv_economic", b"unciv_culture"];
const INVENTION_SKIP: [&[u8]; 3] = [b"icon", b"limit", b"chance"];

/// `_invention_effects`: its own fields, then those of its `effect`.
fn invention_effects(block: &V) -> Vec<(Vec<u8>, Vec<u8>)> {
    let mut out = Vec::new();
    if !is_dict(block) {
        return out;
    }
    flatten_effects(pairs(block).iter().filter(|(k, _)| k != b"effect"), &INVENTION_SKIP, b"", &mut out);
    if let Some(nested @ V::Dict(_)) = get(block, b"effect") {
        flatten_effects(pairs(nested).iter(), &INVENTION_SKIP, b"", &mut out);
    }
    out
}

/// `_brace_blocks`: every second-level body, its opening brace included.
fn brace_blocks(text: &[u8]) -> Vec<&[u8]> {
    let mut out = Vec::new();
    let mut depth = 0i64;
    let mut start: Option<usize> = None;
    for (i, &c) in text.iter().enumerate() {
        if c == b'{' {
            depth += 1;
            if depth == 2 {
                start = Some(i);
            }
        } else if c == b'}' {
            if depth == 2 {
                if let Some(s) = start.take() {
                    out.push(&text[s..i]);
                }
            }
            depth -= 1;
        }
    }
    out
}

fn fmap(m: &OMap<Vec<u8>, f64>) -> J {
    J::Obj(m.iter().map(|(k, v)| (l1(k), J::Float(*v))).collect())
}

fn smap(m: &OMap<String, String>) -> J {
    J::Obj(m.iter().map(|(k, v)| (k.clone(), J::Str(v.clone()))).collect())
}

fn ship_json(m: &OMap<Vec<u8>, OMap<Vec<u8>, f64>>) -> J {
    J::Obj(m.iter().map(|(k, v)| (l1(k), fmap(v))).collect())
}

// ------------------------------------------------------------ the pieces

impl Reader {
    fn read_defines(&self) -> D<OMap<Vec<u8>, f64>> {
        let mut out = OMap::new();
        let fname = self.resolved_file(&["common", "defines.lua"]);
        if !is_file(&fname) {
            return Ok(out);
        }
        let text = self.re.lua_comment.remove(&self.plain(&fname)?);
        for key in ["POP_SIZE_PER_REGIMENT", "POP_MIN_SIZE_FOR_REGIMENT", "MIN_MOBILIZE_LIMIT",
                    "POP_MIN_SIZE_FOR_REGIMENT_COLONY_MULTIPLIER",
                    "POP_MIN_SIZE_FOR_REGIMENT_NONCORE_MULTIPLIER",
                    "POP_MIN_SIZE_FOR_REGIMENT_PROTECTORATE_MULTIPLIER"] {
            let re = Re::new(&format!(r"(?<![\w.]){}\s*=\s*([-\d.]+)", key));
            if let Some(m) = re.search(&text, 0) {
                out.set(key.as_bytes().to_vec(), must_float(m.group(&text, 1))?);
            }
        }
        Ok(out)
    }

    fn read_poptypes(&self) -> D<OMap<String, Vec<u8>>> {
        let mut out = OMap::new();
        for (name, target) in self.resolved_files("poptypes")? {
            let text = self.plain(&target)?;
            if let Some(m) = self.re.strata.search(&text, 0) {
                out.set(lower(stem(&name)), lower1(m.group(&text, 1)));
            }
        }
        Ok(out)
    }

    fn country_entries(&self) -> D<Vec<(Vec<u8>, Vec<u8>)>> {
        let listing = self.resolved_file(&["common", "countries.txt"]);
        if !is_file(&listing) {
            return Ok(Vec::new());
        }
        let text = self.plain(&listing)?;
        let mut seen = HashSet::new();
        let mut out = Vec::new();
        for m in self.re.country_entry.find_all(&text) {
            let tag = m.group(&text, 1).to_vec();
            if !seen.insert(tag.clone()) {
                continue;
            }
            out.push((tag, strip(m.group(&text, 2)).to_vec()));
        }
        Ok(out)
    }

    /// The war policy of every party, in engine load order.
    fn party_policies(&self) -> D<Vec<Vec<u8>>> {
        let mut out = Vec::new();
        for (_tag, rel) in self.country_entries()? {
            let rel = l1(&rel).replace('/', &SEP.to_string());
            let target = self.resolved_file(&["common", &rel]);
            if !is_file(&target) {
                continue;
            }
            let text = self.plain(&target)?;
            for block in self.named_blocks(&text, b"party") {
                out.push(match self.re.war_policy.search(block, 0) {
                    Some(m) => m.group(block, 1).to_vec(),
                    None => Vec::new(),
                });
            }
        }
        Ok(out)
    }

    fn modifier_mob_impacts(&self) -> D<OMap<Vec<u8>, f64>> {
        let mut out = OMap::new();
        for name in ["event_modifiers.txt", "triggered_modifiers.txt"] {
            let target = self.resolved_file(&["common", name]);
            if !is_file(&target) {
                continue;
            }
            for (key, block) in self.clausewitz(&target)?.iter() {
                if let Some(v) = get(block, b"mobilization_impact") {
                    out.set(key.clone(), to_float(Some(v), 0.0));
                }
            }
        }
        Ok(out)
    }

    fn mobilization_impacts(&self) -> D<OMap<Vec<u8>, f64>> {
        let target = self.resolved_file(&["common", "issues.txt"]);
        let mut out = OMap::new();
        if !is_file(&target) {
            return Ok(out);
        }
        let text = self.plain(&target)?;
        for party in self.named_blocks(&text, b"party_issues") {
            for policy in self.named_blocks(party, b"war_policy") {
                for m in self.re.word_block.find_all(policy) {
                    let name = m.group(policy, 1);
                    let block = self.named_blocks(&policy[m.start()..], name);
                    let first = match block.first() {
                        Some(b) => *b,
                        None => continue,
                    };
                    if let Some(hit) = self.re.impact.search(first, 0) {
                        let v = must_float(hit.group(first, 1))?;
                        if !out.contains_key(name) {
                            out.set(name.to_vec(), v);
                        }
                    }
                }
            }
        }
        Ok(out)
    }

    fn reform_mob(&self) -> D<(OMap<(Vec<u8>, Vec<u8>), f64>, Vec<Vec<u8>>)> {
        let target = self.resolved_file(&["common", "issues.txt"]);
        let mut sizes = OMap::new();
        let mut groups = Vec::new();
        if !is_file(&target) {
            return Ok((sizes, groups));
        }
        for (category, block) in self.clausewitz(&target)?.iter() {
            if category == b"party_issues" || !is_dict(block) {
                continue;
            }
            for (reform, body) in pairs(block) {
                if reform.first() == Some(&b'_') || !is_dict(body) {
                    continue;
                }
                groups.push(reform.clone());
                for (option, spec) in pairs(body) {
                    if option.first() == Some(&b'_') || !is_dict(spec) {
                        continue;
                    }
                    let size = find_mob_size(spec);
                    if size != 0.0 {
                        sizes.set((reform.clone(), option.clone()), size);
                    }
                }
            }
        }
        Ok((sizes, groups))
    }

    fn static_mob(&self) -> D<OMap<Vec<u8>, f64>> {
        let target = self.resolved_file(&["common", "static_modifiers.txt"]);
        let mut out = OMap::new();
        if !is_file(&target) {
            return Ok(out);
        }
        for (name, block) in self.clausewitz(&target)?.iter() {
            let size = find_mob_size(block);
            if size != 0.0 {
                out.set(name.clone(), size);
            }
        }
        Ok(out)
    }

    /// (name, size, impact, trigger) for the triggered modifiers that move either.
    fn triggered_mob(&self) -> D<Vec<(Vec<u8>, f64, f64, Option<(Top, usize)>)>> {
        let target = self.resolved_file(&["common", "triggered_modifiers.txt"]);
        let mut out = Vec::new();
        if !is_file(&target) {
            return Ok(out);
        }
        let top = self.clausewitz(&target)?;
        for (i, (name, block)) in top.iter().enumerate() {
            if !is_dict(block) {
                continue;
            }
            let size = find_mob_size(block);
            let impact = to_float(get(block, b"mobilization_impact"), 0.0);
            if size == 0.0 && impact == 0.0 {
                continue;
            }
            let has = matches!(get(block, b"trigger"), Some(V::Dict(_)));
            out.push((name.clone(), size, impact, if has { Some((top.clone(), i)) } else { None }));
        }
        Ok(out)
    }

    fn culture_blocks(&self, mut each: impl FnMut(&[u8], &[u8])) -> D<()> {
        for root in self.game_then_mod() {
            let target = joins(root, &["common", "cultures.txt"]);
            if !is_file(&target) {
                continue;
            }
            for (group, block) in self.clausewitz(&target)?.iter() {
                if !is_dict(block) {
                    continue;
                }
                for (name, body) in pairs(block) {
                    if name.first() == Some(&b'_') || NOT_A_CULTURE.contains(&name.as_slice()) {
                        continue;
                    }
                    let culture = match body {
                        V::Dict(_) => true,
                        V::List(x) | V::Multi(x) => x.first().map_or(false, is_dict),
                        _ => false,
                    };
                    if culture {
                        each(name, group);
                    }
                }
            }
        }
        Ok(())
    }

    fn continents(&self) -> D<Vec<(i64, Vec<u8>)>> {
        let target = self.map_file("continent.txt");
        let mut out: OMap<i64, Vec<u8>> = OMap::new();
        if !is_file(&target) {
            return Ok(Vec::new());
        }
        for (name, block) in self.clausewitz(&target)?.iter() {
            if !is_dict(block) {
                continue;
            }
            for pid in crate::clause::as_list(get(block, b"provinces")) {
                if let V::Str(_) = pid {
                    out.set(to_int(Some(pid), -1)?, name.clone());
                }
            }
        }
        Ok(out.iter().map(|(k, v)| (*k, v.clone())).collect())
    }

    fn base_prices(&self) -> D<OMap<Vec<u8>, f64>> {
        let target = self.resolved_file(&["common", "goods.txt"]);
        let mut out = OMap::new();
        if !is_file(&target) {
            return Ok(out);
        }
        for (_c, block) in self.clausewitz(&target)?.iter() {
            if !is_dict(block) {
                continue;
            }
            for (good, spec) in pairs(block) {
                if good.first() == Some(&b'_') || !is_dict(spec) {
                    continue;
                }
                if let Some(c) = get(spec, b"cost") {
                    out.set(good.clone(), to_float(Some(c), 0.0));
                }
            }
        }
        Ok(out)
    }

    fn regions(&self) -> D<OMap<Vec<u8>, Vec<i64>>> {
        let target = self.map_file("region.txt");
        let mut out = OMap::new();
        if !is_file(&target) {
            return Ok(out);
        }
        let text = self.plain(&target)?;
        for hit in self.re.region.find_all(&text) {
            let mut ids = Vec::new();
            for n in split_ws(hit.group(&text, 2)) {
                if digit_word(n)? {
                    ids.push(py_int(n)?.unwrap());
                }
            }
            if !ids.is_empty() {
                out.set(hit.group(&text, 1).to_vec(), ids);
            }
        }
        Ok(out)
    }

    fn unit_kinds(&self) -> D<OMap<Vec<u8>, Vec<u8>>> {
        let mut out = OMap::new();
        for (_n, target) in self.resolved_files("units")? {
            let body = self.plain(&target)?;
            for m in self.re.line_block.find_all(&body) {
                let end = (m.end() + 900).min(body.len());
                let window = &body[m.end()..end];
                if let Some(kind) = self.re.unit_type.search(window, 0) {
                    out.set(m.group(&body, 1).to_vec(), kind.group(window, 1).to_vec());
                }
            }
        }
        Ok(out)
    }

    fn naval_units(&self) -> D<J> {
        let mut out: OMap<Vec<u8>, J> = OMap::new();
        for (_n, target) in self.resolved_files("units")? {
            let body = self.plain(&target)?;
            for m in self.re.line_block.find_all(&body) {
                let name = m.group(&body, 1);
                let block = self.block_text(&body, name);
                match self.re.unit_type.search(block, 0) {
                    Some(k) if k.group(block, 1) == b"naval" => {}
                    _ => continue,
                }
                let mut stats = Vec::new();
                for stat in SHIP_STATS {
                    let mut pat = b"(?<![\\w_])".to_vec();
                    pat.extend_from_slice(stat);
                    pat.extend_from_slice(b"\\s*=\\s*([-\\d.]+)");
                    let re = Re::bytes(&pat, false, false);
                    stats.push(match re.search(block, 0) {
                        Some(h) => must_float(h.group(block, 1))?,
                        None => 0.0,
                    });
                }
                let heavy = match self.re.klass.search(block, 0) {
                    Some(k) => k.group(block, 1) == b"big_ship",
                    None => false,
                };
                out.set(name.to_vec(), J::Obj(vec![
                    ("hull".into(), J::Float(stats[0])),
                    ("gun_power".into(), J::Float(stats[1])),
                    ("evasion".into(), J::Float(stats[2])),
                    ("torpedo_attack".into(), J::Float(stats[3])),
                    ("score".into(), J::Float(stats[4])),
                    ("heavy".into(), J::Int(heavy as i64)),
                ]));
            }
        }
        Ok(J::Obj(out.into_iter_pairs().map(|(k, v)| (l1(&k), v)).collect()))
    }

    fn naval_tech_effects(&self) -> D<J> {
        let mut out = Vec::new();
        for (_n, target) in self.resolved_files("technologies")? {
            let raw = self.plain(&target)?;
            for (name, _b) in self.clausewitz(&target)?.iter() {
                let found = self.ship_changes(&self.drop_block(self.block_text(&raw, name), b"ai_chance"))?;
                if !found.is_empty() {
                    set_pair(&mut out, l1(name), ship_json(&found));
                }
            }
        }
        Ok(J::Obj(out))
    }

    fn naval_invention_effects(&self) -> D<J> {
        let mut out = Vec::new();
        for (_n, target) in self.resolved_files("inventions")? {
            let raw = self.plain(&target)?;
            for (name, _b) in self.clausewitz(&target)?.iter() {
                let body = self.block_text(&raw, name);
                let mut found: OMap<Vec<u8>, OMap<Vec<u8>, f64>> = OMap::new();
                for effect in self.named_blocks(body, b"effect") {
                    for (who, deltas) in self.ship_changes(effect)?.iter() {
                        let into = found.entry(who.clone(), OMap::new);
                        for (stat, value) in deltas.iter() {
                            let was = into.get(stat).copied().unwrap_or(0.0);
                            into.set(stat.clone(), was + value);
                        }
                    }
                }
                if found.is_empty() {
                    continue;
                }
                let (reqs, tags, _invs) = self.limit_of(body);
                set_pair(&mut out, l1(name), J::Obj(vec![
                    ("effects".into(), ship_json(&found)),
                    ("techs".into(), sorted_json(&reqs)),
                    ("tags".into(), sorted_json(&tags)),
                ]));
            }
        }
        Ok(J::Obj(out))
    }

    fn map_source(&self) -> String {
        let own = join(&self.path, "map");
        if is_file(&join(&own, "provinces.bmp")) && is_file(&join(&own, "definition.csv")) {
            return self.path.clone();
        }
        self.base.clone().unwrap_or_else(|| self.path.clone())
    }

    fn map_file(&self, name: &str) -> String {
        joins(&self.map_source(), &["map", name])
    }

    fn country_files(&self) -> D<OMap<Vec<u8>, String>> {
        let mut out = OMap::new();
        for root in self.game_then_mod() {
            let listing = joins(root, &["common", "countries.txt"]);
            if !is_file(&listing) {
                continue;
            }
            let text = self.plain(&listing)?;
            for m in self.re.country_entry.find_all(&text) {
                let rel = l1(strip(m.group(&text, 2))).replace('/', &SEP.to_string());
                for home in [self.path.as_str(), root] {
                    let target = joins(home, &["common", &rel]);
                    if is_file(&target) {
                        out.set(m.group(&text, 1).to_vec(), target);
                        break;
                    }
                }
            }
        }
        Ok(out)
    }

    fn country_colours(&self) -> D<J> {
        let mut out = Vec::new();
        for (tag, target) in self.country_files()?.iter() {
            let text = self.plain(target)?;
            if let Some(hit) = self.re.color.search(&text, 0) {
                let mut s = String::from("#");
                for g in 1..=3 {
                    let v = py_int(hit.group(&text, g))?.unwrap();
                    s.push_str(&format!("{:02x}", v));
                }
                out.push((l1(tag), J::Str(s)));
            }
        }
        Ok(J::Obj(out))
    }

    fn sea_provinces(&self) -> D<Vec<i64>> {
        let target = self.map_file("default.map");
        if !is_file(&target) {
            return Ok(Vec::new());
        }
        let text = self.plain(&target)?;
        let mut out = BTreeSet::new();
        if let Some(hit) = self.re.sea.search(&text, 0) {
            for n in split_ws(hit.group(&text, 1)) {
                if digit_word(n)? {
                    out.insert(py_int(n)?.unwrap());
                }
            }
        }
        Ok(out.into_iter().collect())
    }

    fn unit_positions(&self) -> D<Vec<J>> {
        let target = self.map_file("positions.txt");
        if !is_file(&target) {
            return Ok(Vec::new());
        }
        let mut out: OMap<i64, (f64, f64)> = OMap::new();
        for (key, block) in self.clausewitz(&target)?.iter() {
            if !is_dict(block) {
                continue;
            }
            let mut spot = None;
            for anchor in [&b"unit"[..], b"text_position", b"building_construction",
                           b"military_construction", b"factory", b"city", b"town"] {
                if let Some(c @ V::Dict(d)) = get(block, anchor) {
                    if d.get(b"x").is_some() {
                        spot = Some(c);
                        break;
                    }
                }
            }
            let spot = match spot {
                Some(s) => s,
                None => continue,
            };
            let at = (to_float(get(spot, b"x"), 0.0), to_float(get(spot, b"y"), 0.0));
            if let Some(p) = py_int(key)? {
                out.set(p, at);
            }
        }
        Ok(out.iter().map(|(p, (x, y))| J::List(vec![J::Int(*p), J::Float(*x), J::Float(*y)])).collect())
    }

    fn province_names(&self) -> D<Vec<J>> {
        let target = self.map_file("definition.csv");
        if !is_file(&target) {
            return Ok(Vec::new());
        }
        let raw = Reader::read(&target)?;
        let mut out: OMap<i64, Vec<u8>> = OMap::new();
        let mut lines = raw.split_inclusive(|&c| c == b'\n');
        lines.next();
        for line in lines {
            let bits: Vec<&[u8]> = line.split(|&c| c == b';').collect();
            if bits.len() < 5 {
                continue;
            }
            let pid = match py_int(bits[0])? {
                Some(p) => p,
                None => continue,
            };
            let name = strip(bits[4]);
            if !name.is_empty() && lower1(name) != b"x" {
                out.set(pid, name.to_vec());
            }
        }
        Ok(out.iter().map(|(p, n)| J::List(vec![J::Int(*p), js(n)])).collect())
    }

    fn flag_styles(&self) -> D<J> {
        let target = self.resolved_file(&["common", "governments.txt"]);
        let mut out = Vec::new();
        if !is_file(&target) {
            return Ok(J::Obj(out));
        }
        for (name, block) in self.clausewitz(&target)?.iter() {
            if !is_dict(block) {
                continue;
            }
            let variant = match get(block, b"flagType") {
                Some(v) => unquote(unquote(&str_of(v))).to_vec(),
                None => Vec::new(),
            };
            let elects = match get(block, b"election") {
                Some(V::Str(s)) => s.eq_ignore_ascii_case(b"yes"),
                Some(_) => false,
                None => false,
            };
            set_pair(&mut out, l1(name), J::List(vec![js(&variant), J::Bool(elects)]));
        }
        Ok(J::Obj(out))
    }

    fn flag_roots(&self) -> Vec<J> {
        let mut roots = vec![joins(&self.path, &["gfx", "flags"])];
        let parts: Vec<&str> = self.path.split(SEP).collect();
        if parts.len() >= 2 && lower(parts[parts.len() - 2]) == "mod" {
            let up = parts[..parts.len() - 2].join(&SEP.to_string());
            roots.push(joins(&up, &["gfx", "flags"]));
        }
        roots.into_iter().filter(|r| is_dir(r)).map(J::Str).collect()
    }

    fn formations(&self) -> D<J> {
        let mut out: OMap<Vec<u8>, Set> = OMap::new();
        for (_n, target) in self.resolved_files("decisions")? {
            let text = self.plain(&target)?;
            for block in brace_blocks(&text) {
                let made = match self.re.change_tag.search(block, 0) {
                    Some(m) => m.group(block, 1).to_vec(),
                    None => continue,
                };
                let potential = self.block_text(block, b"potential");
                let from: Set = self.re.tag3.find_all(potential).iter()
                    .map(|m| m.group(potential, 1).to_vec()).collect();
                if !from.is_empty() {
                    out.entry(made, Set::new).extend(from);
                }
            }
        }
        Ok(J::Obj(out.iter().map(|(k, v)| (l1(k), sorted_json(v))).collect()))
    }

    fn top_level_keys(&self, folder: &str, keys: &mut HashSet<String>) -> D<()> {
        for (_n, target) in self.resolved_files(folder)? {
            let text = self.plain(&target)?;
            for m in self.re.line_block.find_all(&text) {
                keys.insert(l1(m.group(&text, 1)));
            }
        }
        Ok(())
    }

    fn display_names(&self) -> D<OMap<String, String>> {
        let mut keys: HashSet<String> = HashSet::new();
        for root in self.game_then_mod() {
            let target = joins(root, &["common", "goods.txt"]);
            if is_file(&target) {
                for (_c, block) in self.clausewitz(&target)?.iter() {
                    if is_dict(block) {
                        for (g, _) in pairs(block) {
                            if g.first() != Some(&b'_') {
                                keys.insert(l1(g));
                            }
                        }
                    }
                }
            }
            let folder = join(root, "poptypes");
            if is_dir(&folder) {
                for f in Reader::files(&folder)? {
                    keys.insert(cut4(&f).to_string());
                }
            }
            let target = joins(root, &["common", "cb_types.txt"]);
            if is_file(&target) {
                for (name, block) in self.clausewitz(&target)?.iter() {
                    if is_dict(block) {
                        keys.insert(l1(name));
                    }
                }
            }
        }
        self.top_level_keys("units", &mut keys)?;
        self.top_level_keys("technologies", &mut keys)?;
        if keys.is_empty() {
            return Ok(OMap::new());
        }
        self.text_localisation(&keys)
    }

    /// `_invention_index`: {invention: (techs it needs, its effects)} for
    /// every invention gated on a tech.
    fn invention_index(&self) -> D<OMap<Vec<u8>, (Set, Vec<(Vec<u8>, Vec<u8>)>)>> {
        let mut out = OMap::new();
        for (_n, target) in self.resolved_files("inventions")? {
            let raw = self.plain(&target)?;
            for (name, block) in self.clausewitz(&target)?.iter() {
                let (reqs, _t, _i) = self.limit_of(self.block_text(&raw, name));
                if !reqs.is_empty() {
                    out.set(name.clone(), (reqs, invention_effects(block)));
                }
            }
        }
        Ok(out)
    }

    fn technology_tree(&self) -> D<J> {
        let mut files = self.resolved_files("technologies")?;
        if files.is_empty() {
            return Ok(J::Obj(Vec::new()));
        }
        let rule_map = self.invention_index()?;
        let mut gated: HashMap<Vec<u8>, Vec<Vec<u8>>> = HashMap::new();
        for (name, (techs, _e)) in rule_map.iter() {
            for tech in techs {
                gated.entry(tech.clone()).or_default().push(name.clone());
            }
        }
        struct Tech {
            key: Vec<u8>,
            year: i64,
            cost: i64,
            effects: Vec<(Vec<u8>, Vec<u8>)>,
            inventions: Vec<Vec<u8>>,
        }
        struct Column {
            area: Vec<u8>,
            techs: Vec<Tech>,
        }
        let mut tree: OMap<String, Vec<Column>> = OMap::new();
        let mut keys: HashSet<String> = HashSet::new();
        let head = |label: &[u8]| -> String {
            let first = match label.iter().position(|&c| c == b':') {
                Some(i) => &label[..i],
                None => label,
            };
            l1(strip(first))
        };
        files.sort_by(|a, b| a.0.cmp(&b.0));
        for (fname, target) in &files {
            let category = cut4(fname).replace("_tech", "");
            let mut areas: Vec<Column> = Vec::new();
            for (key, block) in self.clausewitz(target)?.iter() {
                if !is_dict(block) {
                    continue;
                }
                let area = match get(block, b"area") {
                    Some(v) => unquote(&str_of(v)).to_vec(),
                    None => b"other".to_vec(),
                };
                let effects = {
                    let mut e = Vec::new();
                    flatten_effects(pairs(block).iter(), &TECH_SKIP, b"", &mut e);
                    e
                };
                let mut invs = gated.get(key).cloned().unwrap_or_default();
                invs.sort();
                keys.insert(l1(key));
                keys.insert(l1(&area));
                for (label, _v) in &effects {
                    keys.insert(head(label));
                }
                for inv in gated.get(key).map(|v| v.as_slice()).unwrap_or(&[]) {
                    keys.insert(l1(inv));
                    if let Some((_t, eff)) = rule_map.get(inv) {
                        for (label, _v) in eff {
                            keys.insert(head(label));
                        }
                    }
                }
                let tech = Tech {
                    key: key.clone(),
                    year: to_int(get(block, b"year"), 0)?,
                    cost: to_int(get(block, b"cost"), 0)?,
                    effects,
                    inventions: invs,
                };
                match areas.iter_mut().find(|c| c.area == area) {
                    Some(c) => c.techs.push(tech),
                    None => areas.push(Column { area, techs: vec![tech] }),
                }
            }
            if !areas.is_empty() {
                keys.insert(category.clone());
                tree.set(category, areas);
            }
        }
        let names = self.text_localisation(&keys)?;
        let name = |k: &str| -> String {
            match names.get(k) {
                Some(v) if !v.is_empty() => v.clone(),
                _ => pretty(k),
            }
        };
        let effects_json = |effects: &[(Vec<u8>, Vec<u8>)]| -> J {
            J::List(effects.iter().map(|(label, value)| {
                J::List(vec![J::Str(name(&l1(label))), js(value)])
            }).collect())
        };
        let mut tree_json = Vec::new();
        for (category, areas) in tree.iter() {
            let cols = areas.iter().map(|col| {
                let techs = col.techs.iter().map(|t| {
                    let invs = t.inventions.iter().map(|inv| {
                        let eff = rule_map.get(inv).map(|(_t, e)| e.as_slice()).unwrap_or(&[]);
                        J::List(vec![js(inv), J::Str(name(&l1(inv))), effects_json(eff)])
                    }).collect();
                    J::Obj(vec![
                        ("key".into(), js(&t.key)),
                        ("year".into(), J::Int(t.year)),
                        ("cost".into(), J::Int(t.cost)),
                        ("effects".into(), effects_json(&t.effects)),
                        ("inventions".into(), J::List(invs)),
                        ("name".into(), J::Str(name(&l1(&t.key)))),
                    ])
                }).collect();
                J::Obj(vec![
                    ("area".into(), js(&col.area)),
                    ("techs".into(), J::List(techs)),
                    ("label".into(), J::Str(name(&l1(&col.area)))),
                ])
            }).collect();
            tree_json.push((category.clone(), J::List(cols)));
        }
        let categories = tree.keys().map(|c| (c.clone(), J::Str(name(c)))).collect();
        Ok(J::Obj(vec![("tree".into(), J::Obj(tree_json)), ("categories".into(), J::Obj(categories))]))
    }

    /// `invention_sequence`: [name, size, techs, tags] in engine load order.
    fn invention_sequence(&self) -> D<Vec<J>> {
        let mut files = self.resolved_files("inventions")?;
        files.sort_by(|a, b| a.0.cmp(&b.0));
        let mut seq = Vec::new();
        for (_n, full) in &files {
            let raw = self.plain(full)?;
            for (name, block) in self.clausewitz(full)?.iter() {
                let (reqs, tags, _i) = self.limit_of(self.block_text(&raw, name));
                seq.push(J::List(vec![js(name), J::Float(find_mob_size(block)),
                                      sorted_json(&reqs), sorted_json(&tags)]));
            }
        }
        Ok(seq)
    }
}

/// `out[key] = value` on a JSON object being built: a key already there
/// keeps its place.
fn set_pair(out: &mut Vec<(String, J)>, key: String, value: J) {
    match out.iter_mut().find(|(k, _)| *k == key) {
        Some(slot) => slot.1 = value,
        None => out.push((key, value)),
    }
}

/// What reading a save needs of a mod (`mod_reader.ModHead`): the strata
/// of its pop types, the reforms a save must carry, the defines a brigade
/// count uses and the state each province belongs to.
pub struct Head {
    pub strata: OMap<String, Vec<u8>>,
    pub reform_names: Set,
    pub defines: OMap<Vec<u8>, f64>,
    pub province_regions: OMap<i64, Vec<u8>>,
}

type Triggers = Vec<(Vec<u8>, f64, f64, Option<(Top, usize)>)>;

impl Reader {
    /// `_head`, in its order: the strata, the reforms, the triggers, the
    /// defines, the regions -- and the three read on the way that the whole
    /// mod keeps as well.
    fn head_parts(&self) -> D<(Head, OMap<(Vec<u8>, Vec<u8>), f64>, Triggers, OMap<Vec<u8>, Vec<i64>>)> {
        let strata = self.read_poptypes()?;
        let (reform_sizes, reform_groups) = self.reform_mob()?;
        let triggers = self.triggered_mob()?;
        let mut asked = HashSet::new();
        for (_n, _s, _i, t) in &triggers {
            if let Some((top, i)) = t {
                if let Some(tr) = get(&top[*i].1, b"trigger") {
                    trigger_conditions(tr, &mut asked);
                }
            }
        }
        let mut watched: Set = reform_sizes.keys().map(|(g, _o)| g.clone()).collect();
        for g in &reform_groups {
            if asked.contains(g) {
                watched.insert(g.clone());
            }
        }
        let defines = self.read_defines()?;
        let regions = self.regions()?;
        let mut province_regions: OMap<i64, Vec<u8>> = OMap::new();
        for (name, ids) in regions.iter() {
            for pid in ids {
                if !province_regions.contains_key(pid) {
                    province_regions.set(*pid, name.clone());
                }
            }
        }
        Ok((Head { strata, reform_names: watched, defines, province_regions }, reform_sizes, triggers, regions))
    }
}

/// `mod_reader.mod_head(path)`, for a path made absolute.
pub fn head(path: &str) -> D<Head> {
    Ok(Reader::new(path).head_parts()?.0)
}

/// What `cross._mod_facts` knows of a folder: the tags it lists, the pop
/// types it defines, its technologies, how many inventions its array holds
/// and the provinces its map defines. The last three are empty where
/// reading them raised, as Python's `except Exception` leaves them; the
/// first two raise out, as Python's do.
pub struct Facts {
    pub tags: Vec<String>,
    pub pops: Vec<String>,
    pub techs: Vec<String>,
    pub inventions: i64,
    pub provinces: Vec<i64>,
}

pub fn facts(root: &str) -> D<Facts> {
    let r = Reader::new(root);
    let techs = (|| -> D<Vec<String>> {
        let mut out = Vec::new();
        for (_n, target) in r.resolved_files("technologies")? {
            for (name, _b) in r.clausewitz(&target)?.iter() {
                out.push(l1(name));
            }
        }
        Ok(out)
    })().unwrap_or_default();
    let provinces = (|| -> D<Vec<i64>> {
        let target = r.resolved_file(&["map", "definition.csv"]);
        let raw = std::fs::read(&target).or_else(|_| no("no definition.csv"))?;
        let mut out = Vec::new();
        // Text mode: a line ends at \n, \r or \r\n.
        let text: Vec<u8> = raw.iter().map(|&c| if c == b'\r' { b'\n' } else { c }).collect();
        for line in text.split(|&c| c == b'\n') {
            let first = line.split(|&c| c == b';').next().unwrap_or(b"");
            let head = strip(first);
            if digit_word(head)? {
                out.push(py_int(head)?.unwrap_or(0));
            }
        }
        Ok(out)
    })().unwrap_or_default();
    let inventions = (|| -> D<i64> { Ok(r.invention_sequence()?.len() as i64) })().unwrap_or(0);
    let tags = r.country_entries()?.iter().map(|(t, _)| l1(t)).collect();
    let pops = r.read_poptypes()?.keys().cloned().collect();
    Ok(Facts { tags, pops, techs, inventions, provinces })
}

/// `mod_reader.invention_files(path)`: {invention: the file it is defined
/// in}, the first file in load order that defines it.
pub fn invention_files(path: &str) -> D<OMap<String, String>> {
    let r = Reader::new(path);
    let mut out: OMap<String, String> = OMap::new();
    for (fname, target) in r.resolved_files("inventions")? {
        for (name, _b) in r.clausewitz(&target)?.iter() {
            let name = l1(name);
            if !out.contains_key(&name) {
                out.set(name, fname.clone());
            }
        }
    }
    Ok(out)
}

/// `mod_reader.has_rules(path)`: whether there are technologies or
/// inventions to read.
pub fn has_rules(path: &str) -> D<bool> {
    let r = Reader::new(path);
    Ok(!r.resolved_files("technologies")?.is_empty() || !r.resolved_files("inventions")?.is_empty())
}

/// The mod at `path` -- absolute, as `_mod_root` makes it -- as
/// `export_mod(load_mod(path))` has it.
pub fn export(path: &str) -> D<J> {
    let r = Reader::new(path);
    let mut tech_files = r.resolved_files("technologies")?;
    let mut inv_files = r.resolved_files("inventions")?;
    tech_files.sort_by_cached_key(|f| lower(&f.0));
    inv_files.sort_by_cached_key(|f| lower(&f.0));

    let mut tech_mob: OMap<Vec<u8>, f64> = OMap::new();
    let mut tech_count = 0i64;
    let mut tech_names: Set = Set::new();
    for (_n, f) in &tech_files {
        for (name, block) in r.clausewitz(f)?.iter() {
            tech_count += 1;
            tech_names.insert(name.clone());
            let size = find_mob_size(block);
            if size != 0.0 {
                tech_mob.set(name.clone(), size);
            }
        }
    }

    let mut rules: Vec<(String, J)> = Vec::new();
    for (_n, f) in &inv_files {
        let raw = r.plain(f)?;
        for (name, block) in r.clausewitz(f)?.iter() {
            let size = find_mob_size(block);
            if size == 0.0 {
                continue;
            }
            let body = r.block_text(&raw, name);
            let (reqs, tags, invs) = r.limit_of(body);
            let (base, blockers) = r.chance_floor(body)?;
            set_pair(&mut rules, l1(name), J::Obj(vec![
                ("size".into(), J::Float(size)),
                ("techs".into(), sorted_json(&reqs)),
                ("tags".into(), sorted_json(&tags)),
                ("requires".into(), sorted_json(&invs)),
                ("base".into(), base.map_or(J::Null, J::Float)),
                ("blockers".into(), J::List(blockers.iter()
                    .map(|(f, b)| J::List(vec![J::Float(*f), js(b)])).collect())),
            ]));
        }
    }

    let mut event_mob: OMap<Vec<u8>, f64> = OMap::new();
    let ev_file = r.resolved_file(&["common", "event_modifiers.txt"]);
    if is_file(&ev_file) {
        for (name, block) in r.clausewitz(&ev_file)?.iter() {
            let size = find_mob_size(block);
            if size != 0.0 {
                event_mob.set(name.clone(), size);
            }
        }
    }
    let mut nv_mob: OMap<Vec<u8>, f64> = OMap::new();
    let nv_file = r.resolved_file(&["common", "nationalvalues.txt"]);
    if is_file(&nv_file) {
        for (name, block) in r.clausewitz(&nv_file)?.iter() {
            let size = find_mob_size(block);
            if size != 0.0 {
                nv_mob.set(name.clone(), size);
            }
        }
    }
    if tech_count == 0 && rules.is_empty() {
        return no(format!("{} has no technologies/ or inventions/ folder", path));
    }

    let (head, reform_sizes, triggers, regions) = r.head_parts()?;
    let Head { strata, reform_names: watched, defines, province_regions } = head;

    let judged: HashSet<&Vec<u8>> = triggers.iter().map(|t| &t.0).collect();
    let event_mob: OMap<Vec<u8>, f64> = event_mob.iter().filter(|(k, _)| !judged.contains(k))
        .map(|(k, v)| (k.clone(), *v)).collect();
    let modifier_impacts: OMap<Vec<u8>, f64> = r.modifier_mob_impacts()?.iter()
        .filter(|(k, _)| !judged.contains(k)).map(|(k, v)| (k.clone(), *v)).collect();

    let state_names = {
        let keys: HashSet<String> = regions.keys().map(|k| l1(k)).collect();
        r.text_localisation(&keys)?
    };
    let culture_names = {
        let mut keys = HashSet::new();
        r.culture_blocks(|name, _g| {
            keys.insert(l1(name));
        })?;
        if keys.is_empty() { OMap::new() } else { r.text_localisation(&keys)? }
    };
    let mut culture_groups: OMap<Vec<u8>, Vec<u8>> = OMap::new();
    r.culture_blocks(|name, group| culture_groups.set(name.to_vec(), group.to_vec()))?;

    let bmp = r.map_file("provinces.bmp");
    let csv = r.map_file("definition.csv");
    let has_map = is_file(&bmp) && is_file(&csv);

    let pairs_i = |m: &OMap<i64, Vec<u8>>| -> J {
        J::List(m.iter().map(|(p, s)| J::List(vec![J::Int(*p), js(s)])).collect())
    };
    let mut out: Vec<(String, J)> = Vec::new();
    let mut put = |k: &str, v: J| out.push((k.to_string(), v));
    put("path", J::Str(path.to_string()));
    put("invention_sequence", J::List(r.invention_sequence()?));
    put("party_policies", J::List(r.party_policies()?.iter().map(|p| js(p)).collect()));
    put("localisation", smap(&r.read_localisation()?));
    put("base_prices", fmap(&r.base_prices()?));
    put("country_order", J::List(r.country_entries()?.iter().map(|(t, _)| js(t)).collect()));
    put("formations", r.formations()?);
    put("culture_names", smap(&culture_names));
    put("display_names", smap(&r.display_names()?));
    put("province_names", J::List(r.province_names()?));
    put("province_regions", pairs_i(&province_regions));
    put("state_names", smap(&state_names));
    put("unit_kinds", J::Obj(r.unit_kinds()?.iter().map(|(k, v)| (l1(k), js(v))).collect()));
    put("naval_units", r.naval_units()?);
    put("naval_effects", r.naval_invention_effects()?);
    put("naval_tech_effects", r.naval_tech_effects()?);
    put("technology", r.technology_tree()?);
    put("mob_impacts", fmap(&r.mobilization_impacts()?));
    put("modifier_impacts", fmap(&modifier_impacts));
    put("reform_mob", J::List(reform_sizes.iter().map(|((g, o), v)| {
        J::List(vec![js(g), js(o), J::Float(*v)])
    }).collect()));
    put("reform_names", sorted_json(&watched));
    put("static_mob", fmap(&r.static_mob()?));
    put("triggered_mob", J::List(triggers.iter().map(|(n, s, i, t)| {
        let trig = match t {
            Some((top, k)) => tree_json(get(&top[*k].1, b"trigger").unwrap()),
            None => J::Obj(Vec::new()),
        };
        J::List(vec![js(n), J::Float(*s), J::Float(*i), trig])
    }).collect()));
    put("culture_groups", J::Obj(culture_groups.iter().map(|(k, v)| (l1(k), js(v))).collect()));
    put("continents", J::List(r.continents()?.iter()
        .map(|(p, s)| J::List(vec![J::Int(*p), js(s)])).collect()));
    put("technologies", sorted_json(&tech_names));
    put("defines", fmap(&defines));
    put("strata", J::Obj(strata.iter().map(|(k, v)| (k.clone(), js(v))).collect()));
    put("invention_rules", J::Obj(rules));
    put("event_mob", fmap(&event_mob));
    put("tech_mob", fmap(&tech_mob));
    put("nv_mob", fmap(&nv_mob));
    put("tech_count", J::Int(tech_count));
    // Read by Python only when the page is drawn, where what it raises is
    // not turned into a sentence: handed back, not refused.
    let later = |d: Decline| Decline(format!("the map or the flags: {}", d.0.trim_start_matches(RAISED)));
    put("colours", if has_map { r.country_colours().map_err(later)? } else { J::Obj(Vec::new()) });
    put("sea", J::List(if has_map {
        r.sea_provinces().map_err(later)?.into_iter().map(J::Int).collect()
    } else { Vec::new() }));
    put("positions", J::List(if has_map { r.unit_positions().map_err(later)? } else { Vec::new() }));
    put("flag_styles", r.flag_styles().map_err(later)?);
    put("flag_roots", J::List(r.flag_roots()));
    put("map_bmp", J::Str(if has_map { bmp } else { String::new() }));
    put("map_csv", J::Str(if has_map { csv } else { String::new() }));
    Ok(J::Obj(out))
}

/// `vic2scan mod-export PATH`: the mod as JSON on stdout, for holding to
/// `export_mod`.
pub fn main(args: &[String]) {
    let path = &args[2];
    let t = std::time::Instant::now();
    // The patterns recurse once a step inside a repeated group; a thread
    // of its own gives them room whatever the text.
    let got = std::thread::Builder::new().stack_size(256 << 20)
        .spawn({
            let path = path.clone();
            move || export(&path)
        }).unwrap().join().unwrap();
    match got {
        Ok(j) => {
            let mut s = String::new();
            j.write(&mut s);
            println!("{}", s);
            eprintln!("read in {:.3} s", t.elapsed().as_secs_f64());
        }
        Err(Decline(why)) => {
            eprintln!("declined: {}", why);
            std::process::exit(3);
        }
    }
}

/// `repr(s)` of a str: quoted the way Python quotes it, with what Python
/// does not print escaped. Printable is Python's rule exactly for the first
/// 256 characters, and past them for the spaces, separators and format
/// characters a path could hold.
pub fn py_repr(s: &str) -> String {
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

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
// Reading a save is 90% scanning text and converting numbers, and about
// fifty-five percent of it is one loop: the province blocks, which are most
// of the file and hold every pop in the game. That loop is what this is. The
// analyzer still reads the country blocks, the wars and the market itself --
// they are a fifth of the time and most of the intricacy -- and it still
// reads everything itself if this binary is missing, so a build that has not
// got a Rust compiler loses speed and nothing else.
//
// The rules below are not this program's own. They are Python's, in
// `read_province` and `v2parse`, reproduced exactly on purpose: the pop
// culture found by elimination, `int(float(x))` truncation, a building level
// read from either a bare pair or a dict. Where they look strange, they look
// strange in both places, and `testkit/parity.py` holds them to it save by
// save against real campaigns.

mod country;

use country::{read_country, Country, Tables};
use std::collections::HashMap;
use std::io::{self, BufRead, Read, Write};
use std::time::Instant;

// The fields a pop can hold other than its culture line. A field not in here,
// whose value does not parse as a number, is the culture -- which is how the
// game writes it: `french=catholic`, with no key of its own.
const POP_KNOWN: &[&str] = &[
    "id", "size", "money", "ideology", "issues", "mil", "con", "literacy",
    "bank", "con_factor", "luxury_needs", "everyday_needs", "life_needs",
    "size_changes", "movement", "promoted", "demoted", "days_of_loss",
    "converted", "local_migration", "external_migration", "colonial_migration",
    "assimilated", "type", "faction", "random", "political_movement",
    "social_movement", "supported_regiment", "employed", "stockpile",
    "movement_tag", "movement_issue", "need", "production_type",
    "last_spending", "current_producing", "percent_afforded",
    "percent_sold_domestic", "percent_sold_export", "leftover", "throttle",
    "needs_cost", "production_income", "promotion", "literacy_change",
    "con_change", "mil_change",
];

const STARVING_BELOW: f64 = 0.05;

// Byte versions of the three conversions. A save's numbers are ASCII, so
// nothing here needs the file decoded first -- which is the whole point:
// decoding 31 MB to read a few thousand characters of it cost 23 ms a save
// and a 31 MB allocation, and on a machine already bound by memory traffic
// the allocation costs more than the milliseconds.
fn trim_b(s: &[u8]) -> &[u8] {
    let mut a = 0;
    let mut b = s.len();
    while a < b && (s[a] as char).is_ascii_whitespace() { a += 1; }
    while b > a && (s[b - 1] as char).is_ascii_whitespace() { b -= 1; }
    &s[a..b]
}

fn trim_end_b(s: &[u8]) -> &[u8] {
    let mut b = s.len();
    while b > 0 && (s[b - 1] as char).is_ascii_whitespace() { b -= 1; }
    &s[..b]
}

fn to_float_b(s: &[u8]) -> f64 {
    match std::str::from_utf8(trim_b(s)) {
        Ok(t) => t.parse::<f64>().unwrap_or(0.0),
        Err(_) => 0.0,
    }
}

fn to_int_b(s: &[u8]) -> i64 {
    let v = to_float_b(s);
    if v.is_finite() { v.trunc() as i64 } else { 0 }
}

fn unquote_b(b: &[u8]) -> &[u8] {
    if b.len() >= 2 && b[0] == b'"' && b[b.len() - 1] == b'"' {
        &b[1..b.len() - 1]
    } else {
        b
    }
}

fn is_number_b(s: &[u8]) -> bool {
    std::str::from_utf8(s).ok().and_then(|t| t.parse::<f64>().ok()).is_some()
}

/// `float(s)` as Python reads it, with Python's fallback to a default.
fn to_float(s: &str) -> f64 {
    s.trim().parse::<f64>().unwrap_or(0.0)
}

/// `int(float(s))`: truncation toward zero, which is what the analyzer does
/// to every size in the file. `"12345.000"` is 12345, not an error.
fn to_int(s: &str) -> i64 {
    let v = s.trim().parse::<f64>().unwrap_or(0.0);
    if v.is_finite() {
        v.trunc() as i64
    } else {
        0
    }
}

/// Vic2 tags are three characters: ENG, FRA, and dynamic ones like D01.
fn looks_like_country_tag(key: &str) -> bool {
    let b = key.as_bytes();
    b.len() == 3
        && b[0].is_ascii_alphabetic()
        && b[0].is_ascii_uppercase()
        && b.iter().all(|c| c.is_ascii_alphanumeric())
        && !b.iter().all(|c| c.is_ascii_digit())
}

/// Windows-1252 bytes as a Rust string, the way Python's latin-1 decode
/// reads them: byte value is code point, and nothing can fail.
fn latin1(raw: &[u8]) -> String {
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
fn tag_bytes(key: &[u8]) -> bool {
    key.len() == 3
        && key[0].is_ascii_alphabetic()
        && key[0].is_ascii_uppercase()
        && key.iter().all(|c| c.is_ascii_alphanumeric())
        && !key.iter().all(|c| c.is_ascii_digit())
}


fn unquote(s: &str) -> &str {
    let b = s.as_bytes();
    if b.len() >= 2 && b[0] == b'"' && b[b.len() - 1] == b'"' {
        &s[1..s.len() - 1]
    } else {
        s
    }
}

/// Names stored once, referred to by number.
#[derive(Default)]
struct Interner {
    names: Vec<Vec<u8>>,
    index: HashMap<Vec<u8>, u32>,
}

impl Interner {
    fn id(&mut self, name: &[u8]) -> u32 {
        if let Some(&i) = self.index.get(name) {
            return i;
        }
        let i = self.names.len() as u32;
        self.names.push(name.to_vec());
        self.index.insert(name.to_vec(), i);
        i
    }
}

/// A count per name that remembers the order names first appeared.
#[derive(Default)]
struct Counter {
    order: Vec<Vec<u8>>,
    index: HashMap<Vec<u8>, usize>,
    total: Vec<i64>,
}

impl Counter {
    fn add(&mut self, name: &[u8], by: i64) {
        match self.index.get(name) {
            Some(&i) => self.total[i] += by,
            None => {
                self.index.insert(name.to_vec(), self.order.len());
                self.order.push(name.to_vec());
                self.total.push(by);
            }
        }
    }
}

#[derive(Default)]
struct Nation {
    provinces: i64,
    cores: Vec<i64>,
    colonial: Vec<(i64, i64)>,
    occupied: Vec<i64>,
    ports: i64,
    naval_base_levels: f64,
    max_naval_base: f64,
    fort_levels: f64,
    railroad_levels: f64,
    total_pop: i64,
    life_unmet: i64,
    starving: i64,
    literacy_weighted: f64,
    con_weighted: f64,
    mil_weighted: f64,
    money_total: f64,
    // Insertion-ordered, not sorted: the report sorts cultures by size with
    // a stable sort, so two cultures of equal size come out in the order the
    // file first mentioned them. A HashMap emitted alphabetically silently
    // reorders those ties, which is a difference of one line in a table and
    // took a whole-campaign hash to notice.
    pop_by_type: Counter,
    pop_by_culture: Counter,
    pop_at: HashMap<i64, i64>,
    soldiers_at: HashMap<i64, i64>,
    soldier_pops_at: HashMap<i64, Vec<i64>>,
    literacy_at: HashMap<i64, f64>,
    // (pop type, culture, size, province), the first two as interned ids:
    // a campaign has a dozen pop types and a few hundred cultures, and this
    // list holds tens of thousands of entries per save. Two fresh strings
    // apiece was the scanner's largest single cost.
    mobilizable: Vec<(u32, u32, i64, i64)>,
}

/// One pop, as the scan fills it in: every field is text until it is wanted.
#[derive(Default)]
struct Pop<'a> {
    kind: &'a [u8],
    id: Option<&'a [u8]>,
    size: Option<&'a [u8]>,
    culture: Option<&'a [u8]>,
    money: Option<&'a [u8]>,
    con: Option<&'a [u8]>,
    mil: Option<&'a [u8]>,
    literacy: Option<&'a [u8]>,
    life: Option<&'a [u8]>,
}

/// Every top-level block, as (key, content start, stop).
///
/// Found from the braces rather than the keys, exactly as Python does it: a
/// top-level block opens with `{` alone at column zero and its key is the
/// line above. Returns None if any brace has something other than a bare
/// `key=` above it -- a save reflowed by a text editor -- and then the caller
/// falls back to Python, which has a slower reader that copes.
fn top_level_blocks(bytes: &[u8]) -> Option<Vec<(&[u8], usize, usize)>> {
    let mut found: Vec<(&[u8], usize, usize)> = Vec::new();
    let mut pos = 0usize;
    while let Some(hit) = find_from(bytes, b"\n{", pos) {
        let line = bytes[..hit].iter().rposition(|&c| c == b'\n').map_or(0, |i| i + 1);
        let mut key = &bytes[line..hit];
        if key.last() == Some(&b'\r') {
            key = &key[..key.len() - 1];
        }
        if key.last() != Some(&b'=') {
            return None;
        }
        let bare = &key[..key.len() - 1];
        if bare.is_empty() || !bare.iter().all(|&c| {
            c.is_ascii_alphanumeric() || c == b'_' || c == b'-' || c == b'.'
        }) {
            return None;
        }
        found.push((bare, hit + 2, line));
        pos = hit + 2;
    }
    if found.is_empty() {
        return None;
    }
    let mut out = Vec::with_capacity(found.len());
    for i in 0..found.len() {
        let stop = if i + 1 < found.len() { found[i + 1].2 } else { bytes.len() };
        out.push((found[i].0, found[i].1, stop));
    }
    Some(out)
}

fn find_from(hay: &[u8], needle: &[u8], from: usize) -> Option<usize> {
    if from >= hay.len() {
        return None;
    }
    // A sliding window, which reads oddly for a two-byte needle and is the
    // fastest of the three things tried here: scanning for the first byte and
    // checking the second measured 0.10s -> 0.15s on a 31 MB save, because
    // the compiler vectorises this and cannot vectorise a loop that restarts
    // at every newline.
    hay[from..]
        .windows(needle.len())
        .position(|w| w == needle)
        .map(|i| i + from)
}

/// A building's level, from either `{ 6.000 6.000 }` or `{ level=6 }`.
fn building_level(bytes: &[u8], open: usize, stop: usize) -> f64 {
    let close = match find_from(bytes, b"}", open) {
        Some(i) if i <= stop => i,
        _ => return 0.0,
    };
    let inner = &bytes[open + 1..close];
    for line in inner.split(|&c| c == b'\n') {
        let line = trim_b(line);
        if let Some(eq) = line.iter().position(|&c| c == b'=') {
            let k = trim_b(&line[..eq]);
            let v = trim_b(&line[eq + 1..]);
            if k == b"level" || k == b"building_level" {
                return to_float_b(v);
            }
        }
    }
    // A bare pair: the first number in the block is the level.
    for word in inner.split(|&c| (c as char).is_ascii_whitespace()) {
        if !word.is_empty() && is_number_b(word) {
            return to_float_b(word);
        }
    }
    0.0
}

struct Scan {
    world_pop: i64,
    owners: Vec<(i64, Vec<u8>, Vec<u8>)>,
    nations: HashMap<Vec<u8>, Nation>,
    // The order nations were first seen, which is the order the file names
    // them. Python builds its dict that way and rows are written by walking
    // it, so emitting them alphabetically reordered every CSV in the run
    // while leaving the report -- which aggregates -- looking identical.
    seen: Vec<Vec<u8>>,
    pop_ids: Vec<i64>,
    pop_kinds: Vec<u32>,
    words: Interner,
}



/// One province block, attributing its pops to the owner.
///
/// The line shapes are the ones Python's `PROVINCE_FIELDS` matches, and the
/// depth is load-bearing: one tab is the province's own fields and the line
/// that opens a pop, two tabs are that pop's numbers. A save written at any
/// other depth is not one the game wrote.
fn read_province(
    bytes: &[u8],
    at: usize,
    stop: usize,
    pid: i64,
    pop_types: &[Vec<u8>],
    mob_types: &[Vec<u8>],
    scan: &mut Scan,
) {
    let mut owner: Option<&[u8]> = None;
    let mut controller: Option<&[u8]> = None;
    let mut colonial_flag: i64 = 0;
    let mut cores: Vec<&[u8]> = Vec::new();
    let mut pops: Vec<Pop> = Vec::new();
    let mut naval_base = 0.0f64;
    let mut fort = 0.0f64;
    let mut railroad = 0.0f64;
    let mut current: Option<usize> = None;

    let mut i = at;
    while i < stop {
        let nl = match find_from(bytes, b"\n\t", i) {
            Some(n) if n < stop => n,
            _ => break,
        };
        let mut p = nl + 1;
        let mut depth = 0usize;
        while p < stop && bytes[p] == b'\t' {
            depth += 1;
            p += 1;
        }
        let end = match bytes[p..stop.min(bytes.len())].iter()
            .position(|&c| c == b'\n')
        {
            Some(k) => p + k,
            None => stop,
        };
        let line = &bytes[p..end];
        i = end;
        let eq = match line.iter().position(|&c| c == b'=') {
            Some(e) => e,
            None => continue,
        };
        let key = &line[..eq];
        let mut value = &line[eq + 1..];
        if value.last() == Some(&b'\r') {
            value = &value[..value.len() - 1];
        }
        if key.is_empty() || key.iter().any(|&c| {
            (c as char).is_ascii_whitespace() || c == b'{' || c == b'}' || c == b'"'
        }) {
            continue;
        }

        // Python's province pattern reaches exactly two levels: one tab for
        // the province's own fields, two for a pop's. Deeper is not matched
        // there and is not matched here.
        if depth > 2 {
            continue;
        }
        if depth == 2 {
            if let Some(idx) = current {
                let slot = &mut pops[idx];
                if key == b"id" {
                    if slot.id.is_none() {
                        slot.id = Some(trim_end_b(value));
                    }
                } else if key == b"size" {
                    slot.size = Some(trim_end_b(value));
                } else if key == b"money" {
                    slot.money = Some(trim_end_b(value));
                } else if key == b"con" {
                    slot.con = Some(trim_end_b(value));
                } else if key == b"mil" {
                    slot.mil = Some(trim_end_b(value));
                } else if key == b"literacy" {
                    slot.literacy = Some(trim_end_b(value));
                } else if key == b"life_needs" {
                    slot.life = Some(trim_end_b(value));
                } else {
                    // Culture by elimination: a field the game does not name,
                    // whose value is not a number. The value must also begin
                    // with something that is neither a digit nor the end of
                    // the line, which is what Python's pattern demands, so a
                    // block opening like `ideology=` is not a culture.
                    let starts_right = match value.first().copied() {
                        Some(c) => c != b'\r' && c != b'\n' && !c.is_ascii_digit(),
                        None => false,
                    };
                    if starts_right
                        && slot.culture.is_none()
                        && !POP_KNOWN.iter().any(|k| k.as_bytes() == key)
                        && !is_number_b(unquote_b(trim_end_b(value)))
                    {
                        slot.culture = Some(key);
                    }
                }
            }
            continue;
        }

        // A province-level field. Anything here closes the pop above it.
        let trimmed = trim_b(value);
        if !trimmed.is_empty() && trimmed[0] != b'{' {
            current = None;
            if key == b"owner" {
                owner = Some(unquote_b(trimmed));
            } else if key == b"controller" {
                controller = Some(unquote_b(trimmed));
            } else if key == b"core" {
                cores.push(unquote_b(trimmed));
            } else if key == b"colonial" {
                colonial_flag = to_int_b(trimmed);
            }
        } else if pop_types.iter().any(|t| t.as_slice() == key) {
            pops.push(Pop { kind: key, ..Default::default() });
            current = Some(pops.len() - 1);
        } else {
            current = None;
            if key == b"naval_base" || key == b"fort" || key == b"railroad" {
                if let Some(brace) = find_from(bytes, b"{", end) {
                    if brace < stop {
                        let level = building_level(bytes, brace, stop);
                        if key == b"naval_base" {
                            naval_base = level;
                        } else if key == b"fort" {
                            fort = level;
                        } else {
                            railroad = level;
                        }
                    }
                }
            }
        }
    }

    // Counted before the owner check: land nobody has colonised still holds
    // people, and they are still part of the world.
    for pop in &pops {
        scan.world_pop += pop.size.map_or(0, to_int_b);
    }
    let owner = match owner {
        Some(o) if !o.is_empty() => o,
        _ => return,
    };
    let held = controller.filter(|c| !c.is_empty()).unwrap_or(owner);
    scan.owners.push((pid, owner.to_vec(), held.to_vec()));

    if !scan.nations.contains_key(owner) {
        scan.seen.push(owner.to_vec());
    }
    let nat = scan.nations.entry(owner.to_vec()).or_default();
    nat.provinces += 1;
    if cores.iter().any(|c| *c == owner) {
        nat.cores.push(pid);
    }
    if colonial_flag != 0 {
        nat.colonial.push((pid, colonial_flag));
    }
    if held != owner {
        nat.occupied.push(pid);
    }
    if naval_base > 0.0 {
        nat.ports += 1;
        nat.naval_base_levels += naval_base;
        if naval_base > nat.max_naval_base {
            nat.max_naval_base = naval_base;
        }
    }
    nat.fort_levels += fort;
    nat.railroad_levels += railroad;

    for pop in &pops {
        if let Some(id) = pop.id {
            scan.pop_ids.push(to_int_b(id));
            let k = scan.words.id(pop.kind);
            scan.pop_kinds.push(k);
        }
        let size = pop.size.map_or(0, to_int_b);
        if size <= 0 {
            continue;
        }
        // Interned before the nation is borrowed: both live on the same
        // struct and the borrow checker is right to mind.
        let mob = match pop.culture {
            Some(culture) if mob_types.iter().any(|t| t.as_slice() == pop.kind) => {
                Some((scan.words.id(pop.kind), scan.words.id(culture)))
            }
            _ => None,
        };
        let nat = scan.nations.get_mut(owner).unwrap();
        nat.total_pop += size;
        nat.pop_by_type.add(pop.kind, size);
        if pop.kind == b"soldiers" {
            *nat.soldiers_at.entry(pid).or_insert(0) += size;
            nat.soldier_pops_at.entry(pid).or_default().push(size);
        }
        *nat.pop_at.entry(pid).or_insert(0) += size;
        if let Some(life) = pop.life {
            let got = to_float_b(life);
            if got < 1.0 {
                nat.life_unmet += size;
            }
            if got < STARVING_BELOW {
                nat.starving += size;
            }
        }
        if let Some(culture) = pop.culture {
            nat.pop_by_culture.add(culture, size);
            if let Some((k, c)) = mob {
                nat.mobilizable.push((k, c, size, pid));
            }
        }
        let literate = pop.literacy.map_or(0.0, to_float_b) * size as f64;
        nat.literacy_weighted += literate;
        *nat.literacy_at.entry(pid).or_insert(0.0) += literate;
        nat.con_weighted += pop.con.map_or(0.0, to_float_b) * size as f64;
        nat.mil_weighted += pop.mil.map_or(0.0, to_float_b) * size as f64;
        nat.money_total += pop.money.map_or(0.0, to_float_b);
    }
}

// ---------------------------------------------------------------- output

fn escape(out: &mut String, s: &[u8]) {
    out.push('"');
    // Windows-1252 byte to code point, the way Python's latin-1 decode reads
    // it -- done for the handful of names that leave here, not for the file.
    for c in s.iter().map(|&b| b as char) {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", c as u32))
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

/// A float as Python's `repr` writes it, so the two sides agree on the text
/// as well as the value.
fn num(v: f64) -> String {
    if v == v.trunc() && v.abs() < 1e16 {
        format!("{:.1}", v)
    } else {
        let mut s = format!("{}", v);
        if s.contains('e') {
            s = format!("{:e}", v);
        }
        s
    }
}

/// What every save is read against, as the command line gives it.
struct Lists {
    pop_types: Vec<Vec<u8>>,
    mob_types: Vec<Vec<u8>>,
    army_techs: Vec<String>,
    navy_techs: Vec<String>,
    reform_keys: Vec<String>,
}

/// A file turned down: the code a one-save run exits with, and why.
struct Refusal {
    code: i32,
    why: String,
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: vic2scan <save.v2> [--pop-types a,b] [--mob-types a,b]\n\
                   \x20      vic2scan --serve [--pop-types a,b] [--mob-types a,b]");
        std::process::exit(2);
    }
    let mut lists = Lists {
        pop_types: Vec::new(),
        mob_types: Vec::new(),
        army_techs: Vec::new(),
        navy_techs: Vec::new(),
        reform_keys: Vec::new(),
    };
    let mut k = 2;
    while k + 1 < args.len() {
        let list: Vec<String> = args[k + 1]
            .split(',')
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string())
            .collect();
        let as_bytes: Vec<Vec<u8>> =
            list.iter().map(|s| s.as_bytes().to_vec()).collect();
        match args[k].as_str() {
            "--pop-types" => lists.pop_types = as_bytes,
            "--mob-types" => lists.mob_types = as_bytes,
            "--army-techs" => lists.army_techs = list,
            "--navy-techs" => lists.navy_techs = list,
            "--reform-keys" => lists.reform_keys = list,
            _ => {}
        }
        k += 2;
    }
    if args[1] == "--serve" {
        serve(&lists);
    }

    let bench = args.iter().any(|a| a == "--bench");
    let mut raw = Vec::new();
    let stdout = io::stdout();
    let mut sink = stdout.lock();
    if let Err(no) = scan_one(&args[1], &lists, bench, &mut raw, &mut sink, false) {
        eprintln!("{}", no.why);
        std::process::exit(no.code);
    }
}

/// One process for many saves: a path a line on stdin, and each answered
/// on stdout exactly as a one-save run answers -- the block table on one
/// line, then the rest on one more -- or with one `{"refused":...}` line
/// for a file a one-save run would have exited over. It ends when stdin
/// does, which is when the worker that started it has gone.
///
/// A worker reads a dozen saves or more, and starting a scanner for each
/// cost more than the start: a new process is handed its 34 MB buffer as
/// fresh pages, each faulted in and zeroed by the kernel, and reading a
/// save into memory that way took 32 ms. Into the same buffer a second
/// time it takes 14. On Windows a process is also much slower to start.
fn serve(lists: &Lists) -> ! {
    let stdin = io::stdin();
    let mut asked = stdin.lock();
    let stdout = io::stdout();
    let mut sink = stdout.lock();
    let mut raw = Vec::new();
    let mut line = String::new();
    loop {
        line.clear();
        match asked.read_line(&mut line) {
            Ok(0) | Err(_) => std::process::exit(0),
            Ok(_) => {}
        }
        let path = line.strip_suffix('\n').unwrap_or(&line);
        if let Err(no) = scan_one(path, lists, false, &mut raw, &mut sink, true) {
            // The code alone: why it was turned down is Python's to say,
            // when it reads the file itself and meets the same thing.
            let said = format!("{{\"refused\":{}}}\n", no.code);
            if sink.write_all(said.as_bytes()).is_err() || sink.flush().is_err() {
                std::process::exit(5);    // nobody listening
            }
        }
    }
}

/// One save, answered on `sink`. `raw` is the buffer it is read into, kept
/// by the caller so that a scanner serving many saves reuses it.
fn scan_one(path: &str, lists: &Lists, bench: bool, raw: &mut Vec<u8>,
            sink: &mut impl Write, serving: bool) -> Result<(), Refusal> {
    let clock = Instant::now();
    let mut mark = |what: &str, since: &mut Instant| {
        if bench {
            eprintln!("  {:<22} {:>6.1} ms", what,
                      since.elapsed().as_secs_f64() * 1000.0);
            *since = Instant::now();
        }
    };
    let mut last = clock;

    raw.clear();
    if let Err(e) = std::fs::File::open(path).and_then(|mut f| f.read_to_end(raw)) {
        return Err(Refusal { code: 1, why: format!("cannot read {}: {}", path, e) });
    }
    mark("read the file", &mut last);
    if raw.starts_with(b"PK") {
        return Err(Refusal {
            code: 3,
            why: format!("{} is a zip archive, not a plaintext save", path),
        });
    }
    // The file stays bytes from here. Decoding all 31 MB of it to read the
    // 8 MB of country blocks cost 23 ms a save and, worse on a machine bound
    // by memory traffic, a 31 MB allocation per worker.
    let text: &[u8] = &raw[..];

    let blocks = match top_level_blocks(text) {
        Some(b) => b,
        None => {
            // Not the layout the game writes; let Python's slower reader have it.
            return Err(Refusal { code: 4, why: "not a flat save".to_string() });
        }
    };

    mark("find top blocks", &mut last);

    // The date, the player and where every non-province block is, sent now
    // rather than with everything else.
    //
    // This is known a fifth of the way through the run, and it is all the
    // caller needs to start on its own share -- the wars, the market, the
    // great power list, which it reads out of the file itself. Sent at the
    // end, as it used to be, the caller sat idle through the province scan
    // and then worked alone through the wars while this process sat idle in
    // turn: a save cost the two added together. Sent here they overlap, and
    // a save costs the longer of them.
    let mut date = String::new();
    let mut player = String::new();
    // Up to just after the first block's opening brace, which is the window
    // Python reads its head scalars from. Taking the whole first block
    // instead would let a `date=` nested inside it win.
    let head_end = blocks.first().map(|b| b.1).unwrap_or(0).min(text.len());
    for line in text[..head_end].split(|&c| c == b'\n').take(40) {
        if let Some(eq) = line.iter().position(|&c| c == b'=') {
            let k = trim_b(&line[..eq]);
            let v = unquote_b(trim_b(&line[eq + 1..]));
            if k == b"date" && date.is_empty() {
                date = latin1(v);
            } else if k == b"player" && player.is_empty() {
                player = latin1(v);
            }
        }
    }
    {
        let mut head = String::with_capacity(1 << 16);
        head.push_str("{\"date\":");
        escape(&mut head, date.as_bytes());
        head.push_str(",\"player\":");
        escape(&mut head, player.as_bytes());
        head.push_str(",\"blocks\":[");
        let mut first_block = true;
        for (key, at, stop) in &blocks {
            if !key.is_empty() && key.iter().all(|c| c.is_ascii_digit()) {
                continue;             // a province, read below and not here
            }
            if !first_block {
                head.push(',');
            }
            first_block = false;
            head.push('[');
            escape(&mut head, key);
            head.push_str(&format!(",{},{}]", at, stop));
        }
        head.push_str("]}\n");
        if sink.write_all(head.as_bytes()).is_err() || sink.flush().is_err() {
            std::process::exit(5);    // nobody listening
        }
    }
    mark("send the block table", &mut last);
    let mut scan = Scan {
        world_pop: 0,
        owners: Vec::new(),
        nations: HashMap::new(),
        pop_ids: Vec::new(),
        pop_kinds: Vec::new(),
        words: Interner::default(),
        seen: Vec::new(),
    };
    let tables = Tables {
        army_techs: &lists.army_techs,
        navy_techs: &lists.navy_techs,
        reform_keys: &lists.reform_keys,
    };
    let mut countries: Vec<Country> = Vec::new();
    for (key, at, stop) in &blocks {
        if !key.is_empty() && key.iter().all(|c| c.is_ascii_digit()) {
            let pid = to_int_b(key);
            read_province(text, *at, *stop, pid, &lists.pop_types,
                          &lists.mob_types, &mut scan);
        } else if tag_bytes(key) {
            // Decoded here and nowhere else: this block, and only this one.
            let chunk = latin1(&text[*at..(*stop).min(text.len())]);
            let tag = latin1(key);
            countries.push(read_country(&chunk, 0, chunk.len(), &tag, &tables));
        }
    }

    mark("scan provinces+countries", &mut last);
    // The date, the player and the block table went out above, before the
    // scan, and are not repeated here.
    let mut out = String::with_capacity(4 << 20);
    out.push_str("{\"world_pop\":");
    out.push_str(&scan.world_pop.to_string());
    out.push_str(",\"owners\":[");
    for (i, (pid, owner, held)) in scan.owners.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push('[');
        out.push_str(&pid.to_string());
        out.push(',');
        escape(&mut out, owner);
        out.push(',');
        escape(&mut out, held);
        out.push(']');
    }
    out.push_str("],\"pop_ids\":[");
    for (i, id) in scan.pop_ids.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str(&id.to_string());
    }
    out.push_str("],\"pop_kinds\":[");
    for (i, k) in scan.pop_kinds.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str(&k.to_string());
    }
    out.push_str("],\"kind_names\":[");
    for (i, n) in scan.words.names.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        escape(&mut out, n);
    }
    out.push_str("],\"nations\":{");
    let tags: Vec<&Vec<u8>> = scan.seen.iter().collect();
    for (n, tag) in tags.iter().enumerate() {
        if n > 0 {
            out.push(',');
        }
        let nat = &scan.nations[tag.as_slice()];
        escape(&mut out, tag);
        out.push_str(":{");
        out.push_str(&format!("\"provinces\":{}", nat.provinces));
        out.push_str(&format!(",\"ports\":{}", nat.ports));
        out.push_str(&format!(",\"total_pop\":{}", nat.total_pop));
        out.push_str(&format!(",\"life_unmet\":{}", nat.life_unmet));
        out.push_str(&format!(",\"starving\":{}", nat.starving));
        out.push_str(&format!(",\"naval_base_levels\":{}", num(nat.naval_base_levels)));
        out.push_str(&format!(",\"max_naval_base\":{}", num(nat.max_naval_base)));
        out.push_str(&format!(",\"fort_levels\":{}", num(nat.fort_levels)));
        out.push_str(&format!(",\"railroad_levels\":{}", num(nat.railroad_levels)));
        out.push_str(&format!(",\"literacy_weighted\":{}", num(nat.literacy_weighted)));
        out.push_str(&format!(",\"con_weighted\":{}", num(nat.con_weighted)));
        out.push_str(&format!(",\"mil_weighted\":{}", num(nat.mil_weighted)));
        out.push_str(&format!(",\"money_total\":{}", num(nat.money_total)));

        let ints = |out: &mut String, name: &str, v: &Vec<i64>| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, x) in v.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push_str(&x.to_string());
            }
            out.push(']');
        };
        ints(&mut out, "cores", &nat.cores);
        ints(&mut out, "occupied", &nat.occupied);

        out.push_str(",\"colonial\":[");
        for (i, (pid, flag)) in nat.colonial.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&format!("[{},{}]", pid, flag));
        }
        out.push(']');

        // Emitted as pairs in first-seen order, so the other side can rebuild
        // the dict with the same ordering Python's would have had.
        let strmap = |out: &mut String, name: &str, c: &Counter| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, k) in c.order.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push('[');
                escape(out, k);
                out.push(',');
                out.push_str(&c.total[i].to_string());
                out.push(']');
            }
            out.push(']');
        };
        strmap(&mut out, "pop_by_type", &nat.pop_by_type);
        strmap(&mut out, "pop_by_culture", &nat.pop_by_culture);

        let intmap = |out: &mut String, name: &str, m: &HashMap<i64, i64>| {
            out.push_str(&format!(",\"{}\":[", name));
            let mut keys: Vec<&i64> = m.keys().collect();
            keys.sort();
            for (i, k) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push_str(&format!("[{},{}]", k, m[*k]));
            }
            out.push(']');
        };
        intmap(&mut out, "pop_at", &nat.pop_at);
        intmap(&mut out, "soldiers_at", &nat.soldiers_at);

        out.push_str(",\"literacy_at\":[");
        let mut lkeys: Vec<&i64> = nat.literacy_at.keys().collect();
        lkeys.sort();
        for (i, k) in lkeys.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&format!("[{},{}]", k, num(nat.literacy_at[*k])));
        }
        out.push(']');

        out.push_str(",\"soldier_pops_at\":[");
        let mut skeys: Vec<&i64> = nat.soldier_pops_at.keys().collect();
        skeys.sort();
        for (i, k) in skeys.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&format!("[{},[", k));
            for (j, s) in nat.soldier_pops_at[*k].iter().enumerate() {
                if j > 0 {
                    out.push(',');
                }
                out.push_str(&s.to_string());
            }
            out.push_str("]]");
        }
        out.push(']');

        out.push_str(",\"mobilizable\":[");
        for (i, (kind, culture, size, pid)) in nat.mobilizable.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            // Ids into `kind_names`, resolved on the other side.
            out.push_str(&format!("[{},{},{},{}]", kind, culture, size, pid));
        }
        out.push(']');
        out.push('}');
    }
    out.push('}');

    // The countries, as their own table. The caller merges them into the
    // same nations the provinces filled, so the shapes here are the ones it
    // wants back: pairs in file order wherever order can be seen downstream.
    out.push_str(",\"countries\":[");
    for (n, c) in countries.iter().enumerate() {
        if n > 0 {
            out.push(',');
        }
        out.push('{');
        out.push_str("\"tag\":");
        escape(&mut out, c.tag.as_bytes());
        let pairs_s = |out: &mut String, name: &str, v: &Vec<(String, String)>| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, (k, val)) in v.iter().enumerate() {
                if i > 0 { out.push(','); }
                out.push('[');
                escape(out, k.as_bytes());
                out.push(',');
                escape(out, val.as_bytes());
                out.push(']');
            }
            out.push(']');
        };
        let pairs_f = |out: &mut String, name: &str, v: &Vec<(String, f64)>| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, (k, val)) in v.iter().enumerate() {
                if i > 0 { out.push(','); }
                out.push('[');
                escape(out, k.as_bytes());
                out.push_str(&format!(",{}]", num(*val)));
            }
            out.push(']');
        };
        let pairs_i = |out: &mut String, name: &str, v: &Vec<(String, i64)>| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, (k, val)) in v.iter().enumerate() {
                if i > 0 { out.push(','); }
                out.push('[');
                escape(out, k.as_bytes());
                out.push_str(&format!(",{}]", val));
            }
            out.push(']');
        };
        let strings = |out: &mut String, name: &str, v: &Vec<String>| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, x) in v.iter().enumerate() {
                if i > 0 { out.push(','); }
                escape(out, x.as_bytes());
            }
            out.push(']');
        };
        let ints = |out: &mut String, name: &str, v: &Vec<i64>| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, x) in v.iter().enumerate() {
                if i > 0 { out.push(','); }
                out.push_str(&x.to_string());
            }
            out.push(']');
        };
        let intpairs = |out: &mut String, name: &str, v: &Vec<(i64, i64)>| {
            out.push_str(&format!(",\"{}\":[", name));
            for (i, (a, b)) in v.iter().enumerate() {
                if i > 0 { out.push(','); }
                out.push_str(&format!("[{},{}]", a, b));
            }
            out.push(']');
        };
        pairs_s(&mut out, "scalars", &c.scalars);
        pairs_f(&mut out, "numerics", &c.numerics);
        out.push_str(&format!(",\"is_mobilized\":{}", c.is_mobilized));
        out.push_str(&format!(",\"human\":{}", if c.human { "true" } else { "false" }));
        pairs_s(&mut out, "reforms", &c.reforms);
        strings(&mut out, "accepted_cultures", &c.accepted_cultures);
        strings(&mut out, "country_flags", &c.country_flags);
        strings(&mut out, "modifiers", &c.modifiers);
        pairs_f(&mut out, "goods_supply", &c.goods_supply);
        ints(&mut out, "invention_ids", &c.invention_ids);
        out.push_str(&format!(",\"mobilizing\":{}", c.mobilizing));
        out.push_str(&format!(",\"states\":{}", c.states));
        intpairs(&mut out, "province_state", &c.province_state);
        ints(&mut out, "colonial_provinces", &c.colonial_provinces);
        intpairs(&mut out, "colonial_level", &c.colonial_level);
        out.push_str(&format!(",\"factory_count\":{}", c.factory_count));
        out.push_str(&format!(",\"factory_levels\":{}", c.factory_levels));
        out.push_str(&format!(",\"techs\":{}", c.techs));
        strings(&mut out, "tech_list", &c.tech_list);
        out.push_str(&format!(",\"army_techs\":{}", c.army_techs));
        out.push_str(&format!(",\"navy_techs\":{}", c.navy_techs));
        out.push_str(&format!(",\"brigades\":{}", c.brigades));
        out.push_str(&format!(",\"armies\":{}", c.armies));
        out.push_str(&format!(",\"navies\":{}", c.navies));
        out.push_str(&format!(",\"ships\":{}", c.ships));
        ints(&mut out, "regiment_pops", &c.regiment_pops);
        pairs_i(&mut out, "regiments_by_type", &c.regiments_by_type);
        pairs_i(&mut out, "ships_by_type", &c.ships_by_type);
        pairs_f(&mut out, "ship_crew", &c.ship_crew);
        out.push_str(",\"units_at\":[");
        for (i, (pid, t)) in c.units_at.iter().enumerate() {
            if i > 0 { out.push(','); }
            out.push_str(&format!("[{},[", pid));
            for (j, (k, v)) in t.iter().enumerate() {
                if j > 0 { out.push(','); }
                out.push('[');
                escape(&mut out, k.as_bytes());
                out.push_str(&format!(",{}]", v));
            }
            out.push_str("]]");
        }
        out.push_str("],\"men_at\":[");
        for (i, (pid, t)) in c.men_at.iter().enumerate() {
            if i > 0 { out.push(','); }
            out.push_str(&format!("[{},[", pid));
            for (j, (k, v)) in t.iter().enumerate() {
                if j > 0 { out.push(','); }
                out.push('[');
                escape(&mut out, k.as_bytes());
                out.push_str(&format!(",{}]", v));
            }
            out.push_str("]]");
        }
        out.push_str("]}");
    }
    out.push_str("]}");
    if serving {
        out.push('\n');              // the end of this save's answer
    }

    mark("build the output", &mut last);
    let sent = sink.write_all(out.as_bytes()).and_then(|_| sink.flush());
    if sent.is_err() && serving {
        std::process::exit(5);        // nobody listening
    }
    Ok(())
}

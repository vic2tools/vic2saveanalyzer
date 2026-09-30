// The analyzer's questions about saves rather than its report: `--peek` and
// `--verify`, as `explain.py` asks and answers them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Both read a save as text Python's way (`v2parse.Tokens`, `parse_block`,
// `pop_culture`), and print what `peek_save` and `verify_save` print, line
// for line. A save Python would refuse on the way in raises out of either
// and ends the Python run with a traceback; those are handed back to it
// before anything is printed, so the Python says what it says.

use crate::clause::{unquote, V};
use crate::engine::modread::py_float;
use crate::engine::walk::{looks_like_country_tag, parse_block, Tokens};
use crate::engine::{basename, read_save, Reading, Refused};
use crate::pickle::FxMap;
use crate::pyre::space;

const VANILLA_POP_TYPES: [&str; 12] = ["aristocrats", "artisans", "bureaucrats", "capitalists",
    "clergymen", "clerks", "craftsmen", "farmers", "labourers", "officers", "slaves", "soldiers"];

fn l1(b: &[u8]) -> String {
    crate::engine::modread::l1(b)
}

/// `_refuse_unless_whole`, asked of every file first: whether Python would
/// read it at all.
pub fn whole(path: &str) -> bool {
    use std::io::{Read, Seek, SeekFrom};
    let mut f = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(_) => return false,
    };
    let mut head = vec![0u8; 4096];
    let mut got = 0;
    while got < head.len() {
        match f.read(&mut head[got..]) {
            Ok(0) => break,
            Ok(k) => got += k,
            Err(_) => return false,
        }
    }
    let head = &head[..got];
    if head.starts_with(b"PK") {
        return false;
    }
    let has = |needle: &[u8]| head.windows(needle.len()).any(|w| w == needle);
    if !(has(b"date=") || has(b"date =")) {
        return false;
    }
    let len = match f.seek(SeekFrom::End(0)) {
        Ok(n) => n,
        Err(_) => return false,
    };
    let mut tail = Vec::new();
    if f.seek(SeekFrom::Start(len.saturating_sub(256))).is_err() || f.read_to_end(&mut tail).is_err() {
        return false;
    }
    let end = tail.iter().rposition(|c| !b" \t\n\r\x0b\x0c".contains(c));
    end.map(|i| tail[i]) == Some(b'}')
}

/// `str.isdigit()` for latin-1 text.
fn isdigit(k: &[u8]) -> bool {
    !k.is_empty() && k.iter().all(|&c| c.is_ascii_digit() || matches!(c, 0xb2 | 0xb3 | 0xb9))
}

/// `pop_culture(pop)` over a parsed pop block: (culture, religion), or
/// Python's None for either.
fn pop_culture(pop: &V) -> (String, String) {
    if let V::Dict(d) = pop {
        for (key, val) in &d.pairs {
            if crate::province::pop_known(key) || key.first() == Some(&b'_') {
                continue;
            }
            if let V::Str(v) = val {
                if py_float(v).is_none() {
                    return (l1(key), l1(v));
                }
            }
        }
    }
    ("None".into(), "None".into())
}

/// Up to `n` characters of latin-1 text.
fn chars(b: &[u8], n: usize) -> String {
    l1(&b[..b.len().min(n)])
}

/// `f"{text:<width}"`.
fn left(text: &str, width: usize) -> String {
    let n = text.chars().count();
    if n >= width { text.to_string() } else { format!("{}{}", text, " ".repeat(width - n)) }
}

/// `peek_save(path)`.
pub fn peek(path: &str) {
    let text = std::fs::read(path).unwrap_or_default();
    let mut tok = Tokens::new(&text, 0);
    let mut top_scalars: Vec<String> = Vec::new();
    let mut top_blocks: Vec<String> = Vec::new();
    let mut first_province: Option<(Vec<u8>, V)> = None;
    let mut first_country: Option<(Vec<u8>, V)> = None;
    loop {
        let t = match tok.next() {
            None => break,
            Some(t) => t,
        };
        let word = tok.get(t);
        if word == b"}" || word == b"{" || word == b"=" {
            continue;
        }
        let nxt = tok.next();
        if nxt.is_none() {
            break;
        }
        if tok.get(nxt.unwrap()) != b"=" {
            tok.push(nxt);
            continue;
        }
        let val = match tok.next() {
            None => break,
            Some(v) => v,
        };
        let key = unquote(word);
        if tok.get(val) == b"{" {
            if isdigit(key) && first_province.is_none() {
                first_province = Some((key.to_vec(), parse_block(&mut tok, &[])));
            } else if looks_like_country_tag(key) && first_country.is_none() {
                first_country = Some((key.to_vec(), parse_block(&mut tok, &[])));
            } else {
                top_blocks.push(if isdigit(key) { "<province>".into() }
                                else if looks_like_country_tag(key) { "<country>".into() }
                                else { l1(key) });
                tok.skip_to_close();
            }
        } else {
            top_scalars.push(format!("{}={}", l1(key), chars(unquote(tok.get(val)), 40)));
        }
    }
    crate::outln!("\n=== {} ===", basename(path));
    crate::outln!("\nTop-level scalars:");
    for item in top_scalars.iter().take(20) {
        crate::outln!("  {}", item);
    }
    let mut seen: Vec<&String> = Vec::new();
    for name in &top_blocks {
        if !seen.contains(&name) {
            seen.push(name);
        }
    }
    crate::outln!("\nTop-level blocks ({} total, distinct):", top_blocks.len());
    crate::outln!("  {}", seen.iter().take(40).map(|s| s.as_str()).collect::<Vec<_>>().join(", "));
    for (label, found) in [("province", &first_province), ("country", &first_country)] {
        let (key, block) = match found {
            None => {
                crate::outln!("\nNo {} block found -- the analyzer will report zeros.", label);
                continue;
            }
            Some(f) => f,
        };
        crate::outln!("\nFirst {} block ({}) keys:", label, l1(key));
        if let V::Dict(d) = block {
            for (k, v) in d.pairs.iter().take(40) {
                let kind = match v {
                    V::Dict(_) => "block",
                    V::List(_) | V::Multi(_) => "list",
                    V::Str(_) => "scalar",
                };
                let mut extra = String::new();
                let name = l1(k);
                if label == "province" && VANILLA_POP_TYPES.contains(&name.as_str()) {
                    let first = match v {
                        V::List(x) | V::Multi(x) => x.first(),
                        one => Some(one),
                    };
                    let (culture, religion) = match first {
                        Some(p @ V::Dict(_)) => pop_culture(p),
                        _ => ("None".into(), "None".into()),
                    };
                    extra = format!("  <- pop, culture={}, religion={}", culture, religion);
                }
                crate::outln!("  {} {}{}", left(&name, 24), kind, extra);
            }
        }
    }
    crate::outln!();
}

// -------------------------------------------------------------- verify

/// `f"{n:>w}"` and `f"{n:>w,}"`.
fn right(text: &str, width: usize) -> String {
    let n = text.chars().count();
    if n >= width { text.to_string() } else { format!("{}{}", " ".repeat(width - n), text) }
}

fn ints(n: i64, width: usize) -> String {
    right(&n.to_string(), width)
}

fn commas(n: i64, width: usize) -> String {
    right(&crate::engine::report::thousands(n), width)
}

/// `str.strip()` of a latin-1 line.
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

/// `re.match(r"^\d+=\s*$", line)` and `r"^\w+=\s*$"`.
fn head_line(line: &[u8], word_char: fn(u8) -> bool) -> bool {
    let n = line.iter().take_while(|&&c| word_char(c)).count();
    n > 0 && line.get(n) == Some(&b'=') && line[n + 1..].iter().all(|&c| space(c))
}

/// `to_int(text)`: `int(float(text))`, 0 for what it will not take.
fn to_int(s: &[u8]) -> i64 {
    match py_float(s) {
        Some(f) if f.is_finite() => f.trunc() as i64,
        _ => 0,
    }
}

/// `verify_save(path, reading)`: the text it prints, and how many nations
/// disagree.
pub fn verify_save(path: &str, reading: &Reading) -> Result<(String, usize), String> {
    let text = std::fs::read(path).map_err(|e| e.to_string())?;
    let mut truth_reg: FxMap<Vec<u8>, i64> = FxMap::default();
    let mut truth_ship: FxMap<Vec<u8>, i64> = FxMap::default();
    let (mut depth, mut current, mut pending): (i64, Option<Vec<u8>>, Option<&[u8]>) = (0, None, None);
    let mut tok = Tokens::new(&text, 0);
    while let Some(t) = tok.next() {
        let word = tok.get(t);
        if word == b"{" {
            depth += 1;
            if let Some(c) = &current {
                if pending == Some(&b"regiment"[..]) {
                    *truth_reg.entry(c.clone()).or_default() += 1;
                } else if pending == Some(&b"ship"[..]) {
                    *truth_ship.entry(c.clone()).or_default() += 1;
                }
            }
            pending = None;
        } else if word == b"}" {
            depth -= 1;
            if depth == 0 {
                current = None;
            }
        } else if word != b"=" {
            pending = Some(word);
            if depth == 0 && looks_like_country_tag(unquote(word)) {
                current = Some(unquote(word).to_vec());
            }
        }
    }

    let mut truth_pop: FxMap<Vec<u8>, i64> = FxMap::default();
    let (mut depth, mut in_province, mut owner): (i64, bool, Option<Vec<u8>>) = (0, false, None);
    for line in text.split(|&c| c == b'\n') {
        let mut line = line;
        while let Some(l) = line.strip_suffix(b"\r") {
            line = l;
        }
        let bare = strip(line);
        if depth == 0 {
            if head_line(line, |c| c.is_ascii_digit()) {
                in_province = true;
                owner = None;
            } else if head_line(line, crate::pyre::word) {
                in_province = false;
                owner = None;
            }
        }
        if in_province && depth == 1 && bare.starts_with(b"owner=") {
            owner = Some(unquote(strip(&bare[6..])).to_vec());
        } else if in_province && depth == 2 && bare.starts_with(b"size=") {
            if let Some(o) = owner.as_ref().filter(|o| !o.is_empty()) {
                *truth_pop.entry(o.clone()).or_default() += to_int(&bare[5..]);
            }
        }
        depth += line.iter().filter(|&&c| c == b'{').count() as i64
            - line.iter().filter(|&&c| c == b'}').count() as i64;
    }

    let mut raw = Vec::new();
    let save = match read_save(path, reading, &mut raw) {
        Ok(s) => s,
        Err(Refused::Skip(why)) | Err(Refused::Back(why)) => return Err(why),
    };
    let nations: FxMap<Vec<u8>, &crate::engine::model::Nation> = save.nations.iter()
        .map(|n| (n.key.chars().map(|c| c as u8).collect(), n)).collect();

    let mut say = vec![
        format!("\n=== {} ===", basename(path)),
        format!("{}{}{}{}{}{}{}{}{}", left("tag", 6), right("brigades", 10), right("scan", 8),
                right("diff", 7), right("ships", 10), right("scan", 8), right("diff", 7),
                right("people", 14), right("scan", 14)),
    ];
    let mut tags: Vec<&Vec<u8>> = truth_reg.keys().chain(truth_ship.keys()).chain(truth_pop.keys())
        .chain(nations.keys()).collect();
    tags.sort();
    tags.dedup();
    let mut mismatches = 0;
    for tag in tags {
        let nat = match nations.get(tag) {
            Some(n) => n,
            None => continue,
        };
        let (got_r, want_r) = (nat.brigades, *truth_reg.get(tag).unwrap_or(&0));
        let (got_s, want_s) = (nat.ships, *truth_ship.get(tag).unwrap_or(&0));
        let (got_p, want_p) = (nat.total_pop, *truth_pop.get(tag).unwrap_or(&0));
        if got_r != want_r || got_s != want_s || got_p != want_p {
            mismatches += 1;
            say.push(format!("{}{}{}{}{}{}{}{}{}", left(&l1(tag), 6), ints(got_r, 10), ints(want_r, 8),
                             ints(got_r - want_r, 7), ints(got_s, 10), ints(want_s, 8),
                             ints(got_s - want_s, 7), commas(got_p, 14), commas(want_p, 14)));
        }
    }
    if mismatches > 0 {
        say.push(format!("\n{} nations disagree. Please report this with the save.", mismatches));
    } else {
        let total_r: i64 = truth_reg.values().sum();
        let total_s: i64 = truth_ship.values().sum();
        let total_p: i64 = truth_pop.values().sum();
        say.push(format!("All nations agree: {} regiments, {} ships, {} people.",
                         crate::engine::report::thousands(total_r),
                         crate::engine::report::thousands(total_s),
                         crate::engine::report::thousands(total_p)));
    }
    say.push(String::new());
    Ok((say.join("\n"), mismatches))
}

/// `verify_all(files, PLAIN, jobs)`.
pub fn verify_all(files: &[String], jobs: Option<i64>) -> Result<(), String> {
    let reading = plain_reading();
    let biggest = files.iter().filter_map(|f| std::fs::metadata(f).ok()).map(|m| m.len()).max().unwrap_or(0);
    let workers = crate::engine::worker_count(files.len(), biggest, jobs);
    if workers > 1 && files.len() > 1 {
        crate::outln!("Checking {} save(s) on {} cores.", files.len(), workers);
    }
    let mut failed = None;
    crate::engine::in_order(files.len(), workers, |i| verify_save(&files[i], &reading), |_i, got| {
        match got {
            Ok((text, _bad)) if failed.is_none() => crate::outln!("{}", text),
            Ok(_) => {}
            Err(why) => {
                if failed.is_none() {
                    failed = Some(why);
                }
            }
        }
    });
    match failed {
        Some(why) => Err(why),
        None => Ok(()),
    }
}

/// `readsave.PLAIN`: the game's twelve pop types, its three mobilizable.
fn plain_reading() -> Reading {
    let mut army: Vec<String> = super::ARMY_LINES.iter().flat_map(|(_, t)| t.iter().map(|s| s.to_string())).collect();
    let mut navy: Vec<String> = super::NAVY_LINES.iter().flat_map(|(_, t)| t.iter().map(|s| s.to_string())).collect();
    army.sort();
    navy.sort();
    Reading {
        pop_types: VANILLA_POP_TYPES.iter().map(|s| s.as_bytes().to_vec()).collect(),
        mob_types: ["craftsmen", "farmers", "labourers"].iter().map(|s| s.as_bytes().to_vec()).collect(),
        reform_keys: Vec::new(),
        army_techs: army,
        navy_techs: navy,
        population_groups: FxMap::default(),
    }
}

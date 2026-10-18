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
// and the regular expressions are Python's own, run by `py::re`. The texts
// are latin-1, a byte to a character, except the localisation, which the
// game writes in Windows-1252 and Python decodes that way. Where Python
// would raise -- a number `float()` refuses, a file it cannot open -- this
// declines, and the analyzer reads the mod in Python, which raises as it
// always did.

use crate::save::clause::{parse, tokens, unquote, V};
use crate::engine::rules::{Decline, D};
use crate::py::json::J;
use crate::util::omap::OMap;
use crate::py::fmt::py_space_char;
use crate::py::re::{space, word, Re};
use std::cell::RefCell;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::rc::Rc;

mod export;
mod paths;
mod pieces;
mod reader;
mod values;

pub use export::export;
pub use paths::join;
pub use reader::{base_game_path, block_end, is_install, Reader};
pub(crate) use values::str_of;
use paths::*;
use pieces::set_pair;
use reader::*;
use values::*;
use crate::py::num::int_latin1;

type Set = BTreeSet<Vec<u8>>;

fn no<T>(why: impl Into<String>) -> D<T> {
    Err(Decline::Unreadable(why.into()))
}

/// A refusal in words: the sentence the run is refused with.
fn raised<T>(sentence: impl Into<String>) -> D<T> {
    Err(Decline::Raised(sentence.into()))
}

/// latin-1 bytes as the str Python decoded them to.
pub fn l1(b: &[u8]) -> String {
    b.iter().map(|&c| c as char).collect()
}

fn js(b: &[u8]) -> J {
    J::Str(l1(b))
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
                out.push(int_latin1(head)?.unwrap_or(0));
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
        Err(d) => {
            eprintln!("declined: {}", d.text());
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

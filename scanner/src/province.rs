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
// The province blocks: most of the file, and every pop in the game. What one
// province adds to its owner, read by the rules `readsave.read_province`
// reads it by, and the save-wide bookkeeping -- who owns what, each pop's
// type by its id, the world's people -- that no one nation's record holds.

use crate::text::{find, find_pair, is_number_b, to_float_b, to_int_b, trim_b, trim_end_b,
                  unquote_b};
use crate::pickle::{FxMap, FxSet};


// The fields a pop can hold other than its culture line. A field not in here,
// whose value does not parse as a number, is the culture -- which is how the
// game writes it: `french=catholic`, with no key of its own.
pub(crate) const POP_KNOWN: &[&str] = &[
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

pub(crate) const STARVING_BELOW: f64 = 0.05;


/// Names stored once, referred to by number.
#[derive(Default)]
pub(crate) struct Interner {
    pub(crate) names: Vec<Vec<u8>>,
    pub(crate) index: FxMap<Vec<u8>, u32>,
}

impl Interner {
    pub(crate) fn id(&mut self, name: &[u8]) -> u32 {
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
pub(crate) struct Counter {
    pub(crate) order: Vec<Vec<u8>>,
    pub(crate) index: FxMap<Vec<u8>, usize>,
    pub(crate) total: Vec<i64>,
}

impl Counter {
    pub(crate) fn add(&mut self, name: &[u8], by: i64) {
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
pub(crate) struct Nation {
    pub(crate) provinces: i64,
    pub(crate) cores: Vec<i64>,
    pub(crate) colonial: Vec<(i64, i64)>,
    pub(crate) occupied: Vec<i64>,
    pub(crate) ports: i64,
    pub(crate) naval_base_levels: f64,
    pub(crate) max_naval_base: f64,
    pub(crate) fort_levels: f64,
    pub(crate) railroad_levels: f64,
    pub(crate) total_pop: i64,
    pub(crate) life_unmet: i64,
    pub(crate) starving: i64,
    pub(crate) literacy_weighted: f64,
    pub(crate) con_weighted: f64,
    pub(crate) mil_weighted: f64,
    pub(crate) money_total: f64,
    // Insertion-ordered, not sorted: the report sorts cultures by size with
    // a stable sort, so two cultures of equal size come out in the order the
    // file first mentioned them. A HashMap emitted alphabetically silently
    // reorders those ties, which is a difference of one line in a table and
    // took a whole-campaign hash to notice.
    pub(crate) pop_by_type: Counter,
    pub(crate) pop_by_culture: Counter,
    pub(crate) population_by_state: FxMap<i64, Population>,
    pub(crate) population_order: Vec<i64>,
    pub(crate) soldiers_noncolonial: i64,
    pub(crate) pop_noncolonial: i64,
    pub(crate) literacy_noncolonial: f64,
    pub(crate) mob_excluded_culture: i64,
    pub(crate) soldier_pops_at: FxMap<i64, Vec<i64>>,
    // (pop type, culture, size, province), the first two as interned ids:
    // a campaign has a dozen pop types and a few hundred cultures, and this
    // list holds tens of thousands of entries per save. Two fresh strings
    // apiece was the scanner's largest single cost.
    pub(crate) mobilizable: Vec<(u32, u32, i64, i64)>,
}

#[derive(Default)]
pub(crate) struct Population {
    pub(crate) total: i64,
    pub(crate) literate: f64,
    pub(crate) types: Counter,
    pub(crate) cultures: Counter,
    pub(crate) provinces: i64,
}

#[derive(Default)]
pub(crate) struct PopulationRules {
    pub(crate) accepted: FxSet<Vec<u8>>,
    pub(crate) colonial: FxSet<i64>,
}

/// One pop, as the scan fills it in: every field is text until it is wanted.
#[derive(Default)]
pub(crate) struct Pop<'a> {
    pub(crate) kind: &'a [u8],
    pub(crate) id: Option<&'a [u8]>,
    pub(crate) size: Option<&'a [u8]>,
    pub(crate) culture: Option<&'a [u8]>,
    pub(crate) money: Option<&'a [u8]>,
    pub(crate) con: Option<&'a [u8]>,
    pub(crate) mil: Option<&'a [u8]>,
    pub(crate) literacy: Option<&'a [u8]>,
    pub(crate) life: Option<&'a [u8]>,
}

/// Every top-level block, as (key, content start, stop).
///
/// Found from the braces rather than the keys, exactly as Python does it: a
/// top-level block opens with `{` alone at column zero and its key is the
/// line above. Returns None if any brace has something other than a bare
/// `key=` above it -- a save reflowed by a text editor -- and then the caller
/// falls back to Python, which has a slower reader that copes.
pub(crate) fn top_level_blocks(bytes: &[u8]) -> Option<Vec<(&[u8], usize, usize)>> {
    let mut found: Vec<(&[u8], usize, usize)> = Vec::new();
    let mut pos = 0usize;
    while let Some(hit) = find_pair(bytes, b'\n', b'{', pos, bytes.len()) {
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


/// A building's level, from either `{ 6.000 6.000 }` or `{ level=6 }`.
pub(crate) fn building_level(bytes: &[u8], open: usize, stop: usize) -> f64 {
    let close = match find(bytes, b"}", open, bytes.len()) {
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

pub(crate) struct Scan {
    pub(crate) world_pop: i64,
    pub(crate) owners: Vec<(i64, Vec<u8>, Vec<u8>)>,
    pub(crate) nations: FxMap<Vec<u8>, Nation>,
    // The order nations were first seen, which is the order the file names
    // them. Python builds its dict that way and rows are written by walking
    // it, so emitting them alphabetically reordered every CSV in the run
    // while leaving the report -- which aggregates -- looking identical.
    pub(crate) seen: Vec<Vec<u8>>,
    pub(crate) pop_ids: Vec<i64>,
    pub(crate) pop_kinds: Vec<u32>,
    pub(crate) words: Interner,
}



/// One province block, attributing its pops to the owner.
///
/// The line shapes are the ones Python's `PROVINCE_FIELDS` matches, and the
/// depth is load-bearing: one tab is the province's own fields and the line
/// that opens a pop, two tabs are that pop's numbers. A save written at any
/// other depth is not one the game wrote.
pub(crate) fn read_province(
    bytes: &[u8],
    at: usize,
    stop: usize,
    pid: i64,
    pop_types: &[Vec<u8>],
    mob_types: &[Vec<u8>],
    scan: &mut Scan,
    rules: &FxMap<Vec<u8>, PopulationRules>,
    referenced_pops: &FxSet<i64>,
    population_groups: &FxMap<i64, i64>,
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
        let nl = match find(bytes, b"\n\t", i, bytes.len()) {
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
        // Python's province pattern reaches exactly two levels -- one tab for
        // the province's own fields, two for a pop's -- so a deeper line is
        // passed over whole, before anything looks inside it. Most of a
        // province is deeper: every pop's ideology and issues, twenty-odd
        // lines of numbers nothing here reads, which used to be searched for
        // an `=` and have their key checked only to be dropped after.
        if depth > 2 {
            continue;
        }
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
                if let Some(brace) = find(bytes, b"{", end, bytes.len()) {
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

    let country = rules.get(owner);
    let home = !country.is_some_and(|r| r.colonial.contains(&pid));
    let group = *population_groups.get(&pid).unwrap_or(&pid);
    let mut province_pop = 0;
    let mut province_literate = 0.0;

    for pop in &pops {
        if let Some(id) = pop.id {
            let id = to_int_b(id);
            if referenced_pops.contains(&id) {
                scan.pop_ids.push(id);
                let k = scan.words.id(pop.kind);
                scan.pop_kinds.push(k);
            }
        }
        let size = pop.size.map_or(0, to_int_b);
        if size <= 0 {
            continue;
        }
        // Interned before the nation is borrowed: both live on the same
        // struct and the borrow checker is right to mind.
        let candidate = pop.culture.is_some()
            && mob_types.iter().any(|t| t.as_slice() == pop.kind);
        let accepted = pop.culture.is_some_and(|c|
            country.is_some_and(|r| r.accepted.contains(c)));
        let mob = match pop.culture {
            Some(culture) if candidate && accepted => {
                Some((scan.words.id(pop.kind), scan.words.id(culture)))
            }
            _ => None,
        };
        let nat = scan.nations.get_mut(owner).unwrap();
        nat.total_pop += size;
        nat.pop_by_type.add(pop.kind, size);
        if province_pop == 0 {
            if !nat.population_by_state.contains_key(&group) {
                nat.population_order.push(group);
            }
            nat.population_by_state.entry(group).or_default().provinces += 1;
        }
        let state = nat.population_by_state.get_mut(&group).unwrap();
        state.types.add(pop.kind, size);
        if let Some(culture) = pop.culture { state.cultures.add(culture, size); }
        if pop.kind == b"soldiers" {
            if home { nat.soldiers_noncolonial += size; }
            nat.soldier_pops_at.entry(pid).or_default().push(size);
        }
        province_pop += size;
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
            } else if candidate && !accepted {
                nat.mob_excluded_culture += size;
            }
        }
        let literate = pop.literacy.map_or(0.0, to_float_b) * size as f64;
        nat.literacy_weighted += literate;
        province_literate += literate;
        nat.con_weighted += pop.con.map_or(0.0, to_float_b) * size as f64;
        nat.mil_weighted += pop.mil.map_or(0.0, to_float_b) * size as f64;
        nat.money_total += pop.money.map_or(0.0, to_float_b);
    }
    let nat = scan.nations.get_mut(owner).unwrap();
    if province_pop > 0 {
        let state = nat.population_by_state.get_mut(&group).unwrap();
        state.total += province_pop;
        state.literate += province_literate;
    }
    if home {
        nat.pop_noncolonial += province_pop;
        nat.literacy_noncolonial += province_literate;
    }
}

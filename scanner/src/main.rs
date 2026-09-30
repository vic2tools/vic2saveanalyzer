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
// Country metadata is read before provinces so the POP scan can accumulate
// geographic state populations directly, retain only referenced POP IDs and
// filter mobilization candidates before sending them to Python. The Python
// reader handles wars and the market concurrently and also provides a full
// fallback when the scanner is unavailable.
//
// The rules below are not this program's own. They are Python's, in
// `read_province` and `v2parse`, reproduced exactly on purpose: the pop
// culture found by elimination, `int(float(x))` truncation, a building level
// read from either a bare pair or a dict. Where they look strange, they look
// strange in both places, and `testkit/parity.py` holds them to it save by
// save against real campaigns.

mod clause;
mod country;
mod deflate;
mod engine;
mod front;
mod jsonr;
mod md5;
mod omap;
mod pickle;
mod province;
mod pyfmt;
mod pyre;
mod record;
mod text;

use country::{read_country, Country, Tables};
use province::{read_province, top_level_blocks, Counter, Interner, Scan, PopulationRules};
use crate::pickle::{FxMap, FxSet};
use std::io::{self, BufRead, Read, Write};
use std::time::Instant;
use text::{latin1, tag_bytes, to_int_b, trim_b, unquote_b};


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

fn counter(out: &mut String, counts: &Counter) {
    out.push('[');
    for (i, key) in counts.order.iter().enumerate() {
        if i > 0 { out.push(','); }
        out.push('[');
        escape(out, key);
        out.push_str(&format!(",{}]", counts.total[i]));
    }
    out.push(']');
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
    population_groups: FxMap<i64, i64>,
    /// Answer with the save's whole record, pickled (`record.rs`), in
    /// place of the block table and the scan as JSON.
    record: bool,
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
    if args[1] == "selftest-fmt" {
        pyfmt::selftest();
        return;
    }
    if args[1] == "bench-engine" {
        engine::bench(&args);
        return;
    }
    if args[1] == "report" {
        engine::main(&args);
        return;
    }
    if args[1] == "mod-signature" {
        front::signature_main(&args);
    }
    if args[1] == "analyze" {
        front::main(&args);
    }
    if args[1] == "mod-export" && args.len() == 3 {
        engine::modread::main(&args);
        return;
    }
    if args[1] == "selftest-re" {
        pyre::selftest();
        return;
    }
    if args[1] == "selftest-deflate" && args.len() == 4 {
        deflate::selftest(&args[2], &args[3]);
        return;
    }
    let mut lists = Lists {
        pop_types: Vec::new(),
        mob_types: Vec::new(),
        army_techs: Vec::new(),
        navy_techs: Vec::new(),
        reform_keys: Vec::new(),
        population_groups: FxMap::default(),
        record: args.iter().any(|a| a == "--record"),
    };
    let mut k = 2;
    while k + 1 < args.len() {
        if args[k] == "--record" || args[k] == "--bench" {
            k += 1;
            continue;
        }
        if args[k] == "--population-groups" {
            let text = std::fs::read_to_string(&args[k + 1]).unwrap_or_else(|e| {
                eprintln!("cannot read population grouping: {}", e);
                std::process::exit(2);
            });
            for line in text.lines() {
                let pair = line.split_once(' ').and_then(|(a, b)|
                    Some((a.parse::<i64>().ok()?, b.parse::<i64>().ok()?)));
                let (pid, group) = pair.unwrap_or_else(|| {
                    eprintln!("invalid population grouping");
                    std::process::exit(2);
                });
                lists.population_groups.insert(pid, group);
            }
            k += 2;
            continue;
        }
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
    let mark = |what: &str, since: &mut Instant| {
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
    // What `v2parse._refuse_unless_whole` turns down, turned down here too
    // for a record: in that mode Python never opens the file, and a save cut
    // short -- the game crashed while writing it, or is writing it now --
    // would be read as a whole one, most of its nations empty and nothing
    // said. Refused, it is read the other way, which says why.
    if lists.record {
        let head = &raw[..raw.len().min(4096)];
        let has = |needle: &[u8]| head.windows(needle.len()).any(|w| w == needle);
        let tail = &raw[raw.len().saturating_sub(256)..];
        let end = tail.iter().rposition(|c| !b" \t\n\r\x0b\x0c".contains(c));
        if !(has(b"date=") || has(b"date =")) || end.map(|i| tail[i]) != Some(b'}') {
            return Err(Refusal { code: 7, why: format!("{} is not a whole save", path) });
        }
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
    if !lists.record {
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
        nations: FxMap::default(),
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
    // The block index already exists. Parse each country once, before POPs
    // need acceptance, colonial status and the regiment-to-POP references.
    let mut rules: FxMap<Vec<u8>, PopulationRules> = FxMap::default();
    let mut referenced_pops = FxSet::default();
    let date_b: Vec<u8> = date.chars().map(|c| c as u32 as u8).collect();
    // For a record, the wars, the market and the great power list are read on
    // a thread of their own while this one scans the countries and provinces:
    // the two halves share nothing, and they are what Python read beside the
    // scanner before, so a save costs the longer of them and not the sum.
    let rest = std::thread::scope(|sc| {
        let ahead = if lists.record {
            Some(sc.spawn(|| record::read_rest(text, &blocks, &date_b)))
        } else {
            None
        };
        for (key, at, stop) in &blocks {
            if tag_bytes(key) {
                // Decoded here and nowhere else: this block, and only this one.
                let chunk = latin1(&text[*at..(*stop).min(text.len())]);
                let tag = latin1(key);
                let country = read_country(&chunk, 0, chunk.len(), &tag, &tables);
                let rule = rules.entry(key.to_vec()).or_default();
                let bytes = |s: &str| s.chars().map(|c| c as u8).collect::<Vec<_>>();
                rule.accepted.extend(country.accepted_cultures.iter().map(|s| bytes(s)));
                for (name, value) in &country.scalars {
                    if name == "primary_culture" && !value.is_empty() {
                        rule.accepted.insert(bytes(value));
                    }
                }
                rule.colonial.extend(&country.colonial_provinces);
                referenced_pops.extend(&country.regiment_pops);
                countries.push(country);
            }
        }
        for (key, at, stop) in &blocks {
            if !key.is_empty() && key.iter().all(|c| c.is_ascii_digit()) {
                read_province(text, *at, *stop, to_int_b(key), &lists.pop_types,
                              &lists.mob_types, &mut scan, &rules,
                              &referenced_pops, &lists.population_groups);
            }
        }
        ahead.map(|h| h.join().unwrap_or(Err(())))
    });

    mark("scan provinces+countries", &mut last);
    if let Some(rest) = rest {
        return answer_record(path, &date_b, &player, rest, &scan, &countries,
                             sink, serving, bench, &mut last);
    }
    // The date, the player and the block table went out above, before the
    // scan, and are not repeated here.
    let mut out = String::with_capacity(4 << 20);
    out.push_str("{\"population_aggregates\":true,\"world_pop\":");
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
        out.push_str(&format!(",\"soldiers_noncolonial\":{}", nat.soldiers_noncolonial));
        out.push_str(&format!(",\"pop_noncolonial\":{}", nat.pop_noncolonial));
        out.push_str(&format!(",\"literacy_noncolonial\":{}", num(nat.literacy_noncolonial)));
        out.push_str(&format!(",\"mob_excluded_culture\":{}", nat.mob_excluded_culture));

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

        out.push_str(",\"population_by_state\":[");
        for (i, group) in nat.population_order.iter().enumerate() {
            if i > 0 { out.push(','); }
            let state = &nat.population_by_state[group];
            out.push_str(&format!("[{},{},{},", group, state.total, num(state.literate)));
            counter(&mut out, &state.types);
            out.push(',');
            counter(&mut out, &state.cultures);
            out.push_str(&format!(",{}]", state.provinces));
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

/// The file's own name, as Python's `os.path.basename` gives it here.
fn basename(path: &str) -> &str {
    let cut: &[char] = if cfg!(windows) { &['/', '\\', ':'] } else { &['/'] };
    match path.rfind(cut) {
        Some(i) => &path[i + 1..],
        None => path,
    }
}

/// `--record`: the save's `(meta, nations)`, pickled, after a line saying
/// how many bytes of it follow. Refused with code 6 where the Python reader
/// would have done something the record will not copy (see `clause.rs`).
#[allow(clippy::too_many_arguments)]
fn answer_record(path: &str, date_b: &[u8], player: &str, rest: Result<record::Rest, ()>,
                 scan: &Scan, countries: &[Country],
                 sink: &mut impl Write, serving: bool, bench: bool,
                 last: &mut Instant) -> Result<(), Refusal> {
    let to_latin = |s: &str| -> Vec<u8> { s.chars().map(|c| c as u32 as u8).collect() };
    let player_b = to_latin(player);
    // Latin-1, as every string in the record is. A name that does not fit
    // is sent empty, and the analyzer, which checks it, puts its own in.
    let name = basename(path);
    let file = if name.chars().all(|c| (c as u32) < 256) { to_latin(name) } else { Vec::new() };
    let head = record::Head { file: &file, date: date_b, player: &player_b };
    let blob = match rest.and_then(|rest| record::build(&head, scan, countries, rest)) {
        Ok(b) => b,
        Err(()) => return Err(Refusal {
            code: 6,
            why: format!("{}: the wars or the market hold something only Python reads", path),
        }),
    };
    if bench {
        eprintln!("  {:<22} {:>6.1} ms", "build the record", last.elapsed().as_secs_f64() * 1000.0);
    }
    let said = format!("{{\"record\":{}}}\n", blob.len());
    let sent = sink.write_all(said.as_bytes())
        .and_then(|_| sink.write_all(&blob))
        .and_then(|_| sink.flush());
    if sent.is_err() && serving {
        std::process::exit(5);        // nobody listening
    }
    Ok(())
}

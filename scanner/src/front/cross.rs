// Several campaigns at once: `cross.py`, the survey and the comparison.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Every folder at or under the one given that holds saves is a campaign;
// each is read under the mod it was named or, failing that, the mod its last
// saves fit (`match_mod`: tags, pop types, technologies, the map and the
// invention array, by elimination); and the nations two or more of them
// share are compared, measure by measure, in the block the report carries.
// Python's rules and words throughout, its regular expressions run by
// `pyre` -- `savehead`'s as bytes patterns, whose classes are ASCII.

use super::{abspath, basename, join, pypath, refuse, Args, RunError, R};
use crate::engine::modread;
use crate::jsonr::J;
use crate::pyre::Re;
use std::collections::{BTreeSet, HashMap};

fn hand_back(why: &str) -> ! {
    crate::engine::decline(why)
}

fn l1(b: &[u8]) -> String {
    modread::l1(b)
}

// --------------------------------------------------------- the folders

/// `campaigns_in(parent)`: (name, path, saves) for every folder at or
/// under `parent`, six deep, that holds saves.
pub fn campaigns_in(parent: &str) -> Vec<(String, String, Vec<String>)> {
    let parent = pypath::normpath(parent);
    let mut found: Vec<(String, String, String, Vec<String>)> = Vec::new();
    walk(&parent, &parent, &mut found);
    let mut seen: HashMap<String, usize> = HashMap::new();
    for f in &found {
        *seen.entry(f.0.clone()).or_default() += 1;
    }
    found.into_iter().map(|(leaf, rel, root, files)| {
        let name = if seen[&leaf] == 1 || rel == "." { leaf } else { rel.replace(pypath::SEP_STR, "/") };
        (name, root, files)
    }).collect()
}

/// `os.walk`, top down, the folders in name order, links not followed.
fn walk(parent: &str, root: &str, found: &mut Vec<(String, String, String, Vec<String>)>) {
    let rd = match std::fs::read_dir(root) {
        Ok(rd) => rd,
        Err(_) => return,
    };
    let (mut dirs, mut files) = (Vec::new(), Vec::new());
    for e in rd.flatten() {
        let name = match e.file_name().into_string() {
            Ok(n) => n,
            Err(_) => hand_back("a folder name under --cross is not text"),
        };
        let link = e.file_type().map(|t| t.is_symlink()).unwrap_or(false);
        let is_dir = if link { std::fs::metadata(e.path()).map(|m| m.is_dir()).unwrap_or(false) }
                     else { e.file_type().map(|t| t.is_dir()).unwrap_or(false) };
        if is_dir {
            dirs.push((name, link));
        } else {
            files.push(name);
        }
    }
    let rel = relpath(root, parent);
    let depth = if rel == "." { 0 } else { rel.matches(pypath::SEP).count() };
    if rel != "." && depth >= 5 {
        dirs.clear();
    }
    dirs.sort();
    let mut saves: Vec<&String> = files.iter().filter(|f| f.to_lowercase().ends_with(".v2")).collect();
    saves.sort();
    if !saves.is_empty() {
        let leaf = basename(root);
        found.push((if leaf.is_empty() { root.to_string() } else { leaf }, rel.clone(), root.to_string(),
                    saves.iter().map(|f| join(root, f)).collect()));
    }
    for (d, link) in dirs {
        if !link {
            walk(parent, &join(root, &d), found);
        }
    }
}

/// `os.path.relpath(root, parent)`, for a folder at or under `parent`.
fn relpath(root: &str, parent: &str) -> String {
    if root == parent {
        return ".".into();
    }
    let rest = root.strip_prefix(parent).unwrap_or(root);
    rest.trim_start_matches(pypath::SEP).to_string()
}

/// `installed_mods(game_root)`: the game, and every mod folder beside it.
fn installed_mods(game_root: &str) -> Vec<(String, String)> {
    let mut out = vec![("(unmodded)".to_string(), game_root.to_string())];
    let home = join(game_root, "mod");
    let mut names: Vec<String> = match std::fs::read_dir(&home) {
        Ok(rd) => rd.flatten().filter_map(|e| e.file_name().into_string().ok()).collect(),
        Err(_) => return out,
    };
    names.sort();
    for name in names {
        let path = join(&home, &name);
        if pypath::isdir(&path) && pypath::isdir(&join(&path, "common")) {
            out.push((name, path));
        }
    }
    out
}

// ------------------------------------------------------ what a save holds

struct Sniffed {
    tags: BTreeSet<String>,
    pops: BTreeSet<String>,
    techs: BTreeSet<String>,
    top: i64,
    provinces: BTreeSet<i64>,
}

struct Pats {
    tag: Re,
    pop: Re,
    ids: Re,
    tech_block: Re,
    tech_name: Re,
    province: Re,
}

fn pats() -> Pats {
    Pats {
        tag: Re::new(r"\n([A-Z][A-Z0-9]{2})=\r?\n\{"),
        pop: Re::new(r"\n\t\t([a-z_]+)=\r?\n\t\t\{"),
        ids: Re::new(r"active_inventions=\s*\{([^}]*)\}"),
        tech_block: Re::with(r"\n\ttechnology=\r?\n\t\{(.*?)\n\t\}", false, true),
        tech_name: Re::new(r"\n\t\t(\w+)=\s*\{"),
        province: Re::new(r"\n(\d+)=\r?\n\{\r?\n\tname="),
    }
}

/// A match: (start, end, the group's start, the group's end).
type Hit = (usize, usize, usize, usize);

fn find_from(t: &[u8], at: usize, needle: &[u8]) -> Option<usize> {
    if at >= t.len() || needle.is_empty() {
        return None;
    }
    let first = needle[0];
    let mut i = at;
    while let Some(off) = t[i..].iter().position(|&c| c == first) {
        let k = i + off;
        if t[k..].starts_with(needle) {
            return Some(k);
        }
        i = k + 1;
    }
    None
}

/// Every match of a pattern that can only begin at `lead`, and can end in
/// only one place from there: `try_at` says where, or no.
fn scan(t: &[u8], lead: &[u8], try_at: impl Fn(usize) -> Option<Hit>) -> Vec<Hit> {
    let mut out = Vec::new();
    let mut at = 0;
    while let Some(i) = find_from(t, at, lead) {
        match try_at(i) {
            Some(hit) => {
                at = hit.1.max(i + 1);
                out.push(hit);
            }
            None => at = i + 1,
        }
    }
    out
}

/// `\r?` then `lit`, at `j`: where it ends.
fn cr_then(t: &[u8], mut j: usize, lit: &[u8]) -> Option<usize> {
    if t.get(j) == Some(&b'\r') {
        j += 1;
    }
    if t[j.min(t.len())..].starts_with(lit) { Some(j + lit.len()) } else { None }
}

/// The run of `ok` from `j`: where it stops.
fn run(t: &[u8], j: usize, ok: impl Fn(u8) -> bool) -> usize {
    let mut k = j;
    while k < t.len() && ok(t[k]) {
        k += 1;
    }
    k
}

/// `\n([A-Z][A-Z0-9]{2})=\r?\n\{`
pub fn sniff_tags(t: &[u8]) -> Vec<Hit> {
    scan(t, b"\n", |i| {
        let s = i + 1;
        let w = t.get(s..s + 3)?;
        if !(w[0].is_ascii_uppercase() && w[1..].iter().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit())) {
            return None;
        }
        if t.get(s + 3) != Some(&b'=') {
            return None;
        }
        Some((i, cr_then(t, s + 4, b"\n{")?, s, s + 3))
    })
}

/// `\n\t\t([a-z_]+)=\r?\n\t\t\{`
pub fn sniff_pops(t: &[u8]) -> Vec<Hit> {
    scan(t, b"\n\t\t", |i| {
        let s = i + 3;
        let e = run(t, s, |c| c.is_ascii_lowercase() || c == b'_');
        if e == s || t.get(e) != Some(&b'=') {
            return None;
        }
        Some((i, cr_then(t, e + 1, b"\n\t\t{")?, s, e))
    })
}

/// `active_inventions=\s*\{([^}]*)\}`
pub fn sniff_ids(t: &[u8]) -> Vec<Hit> {
    scan(t, b"active_inventions=", |i| {
        let j = run(t, i + 18, crate::pyre::space);
        if t.get(j) != Some(&b'{') {
            return None;
        }
        let close = j + 1 + t[j + 1..].iter().position(|&c| c == b'}')?;
        Some((i, close + 1, j + 1, close))
    })
}

/// `\n\ttechnology=\r?\n\t\{(.*?)\n\t\}`, with `re.S`.
pub fn sniff_tech_blocks(t: &[u8]) -> Vec<Hit> {
    scan(t, b"\n\ttechnology=", |i| {
        let s = cr_then(t, i + 13, b"\n\t{")?;
        let close = find_from(t, s, b"\n\t}")?;
        Some((i, close + 3, s, close))
    })
}

/// `\n\t\t(\w+)=\s*\{`
pub fn sniff_tech_names(t: &[u8]) -> Vec<Hit> {
    scan(t, b"\n\t\t", |i| {
        let s = i + 3;
        let e = run(t, s, crate::pyre::word);
        if e == s || t.get(e) != Some(&b'=') {
            return None;
        }
        let j = run(t, e + 1, crate::pyre::space);
        if t.get(j) != Some(&b'{') {
            return None;
        }
        Some((i, j + 1, s, e))
    })
}

/// `\n(\d+)=\r?\n\{\r?\n\tname=`
pub fn sniff_provinces(t: &[u8]) -> Vec<Hit> {
    scan(t, b"\n", |i| {
        let s = i + 1;
        let e = run(t, s, |c| c.is_ascii_digit());
        if e == s || t.get(e) != Some(&b'=') {
            return None;
        }
        let j = cr_then(t, e + 1, b"\n{")?;
        Some((i, cr_then(t, j, b"\n\tname=")?, s, e))
    })
}

/// `_sniff(path)`, by the scanners above. Err is what Python raises out of.
fn sniff(path: &str) -> Result<Sniffed, String> {
    let text = std::fs::read(path).map_err(|e| e.to_string())?;
    let g = |h: &Hit| &text[h.2..h.3];
    let tags = sniff_tags(&text).iter().map(|h| l1(g(h))).collect();
    let mut pops: HashMap<Vec<u8>, usize> = HashMap::new();
    for h in sniff_pops(&text) {
        *pops.entry(g(&h).to_vec()).or_default() += 1;
    }
    let mut top = 0i64;
    let mut any = false;
    for h in sniff_ids(&text) {
        for n in g(&h).split(|&c| crate::pyre::space(c)).filter(|w| !w.is_empty()) {
            if n.iter().all(|c| c.is_ascii_digit()) {
                let v = modread::py_int(n).map_err(|e| e.0)?.unwrap_or(0);
                top = if any { top.max(v) } else { v };
                any = true;
            } else if n.iter().all(|&c| c.is_ascii_digit() || matches!(c, 0xb2 | 0xb3 | 0xb9)) {
                return Err("int() of a superscript".into());
            }
        }
    }
    let mut techs = BTreeSet::new();
    for h in sniff_tech_blocks(&text) {
        let block = g(&h);
        for n in sniff_tech_names(block) {
            techs.insert(l1(&block[n.2..n.3]));
        }
    }
    let mut provinces = BTreeSet::new();
    for h in sniff_provinces(&text) {
        provinces.insert(modread::py_int(g(&h)).map_err(|e| e.0)?.unwrap_or(0));
    }
    Ok(Sniffed {
        tags,
        pops: pops.into_iter().filter(|(_, c)| *c > 50).map(|(k, _)| l1(&k)).collect(),
        techs,
        top,
        provinces,
    })
}

/// `vic2scan selftest-sniff [FILE...]`: the scanners against the patterns
/// they stand for (`pyre`, itself held to Python's `re`), on the files given
/// and on random text built from the pieces a save is made of.
pub fn selftest(files: &[String]) {
    let p = pats();
    let pairs: [(&Re, fn(&[u8]) -> Vec<Hit>, &str); 6] = [
        (&p.tag, sniff_tags, "tags"), (&p.pop, sniff_pops, "pops"), (&p.ids, sniff_ids, "ids"),
        (&p.tech_block, sniff_tech_blocks, "technology blocks"),
        (&p.tech_name, sniff_tech_names, "technology names"),
        (&p.province, sniff_provinces, "provinces"),
    ];
    let check = |text: &[u8], what: &str| -> usize {
        let mut bad = 0;
        for (re, fast, name) in &pairs {
            let slow: Vec<Hit> = re.find_all(text).iter().map(|m| (m.start(), m.end(), m.caps[1].0, m.caps[1].1)).collect();
            if slow != fast(text) {
                bad += 1;
                if bad <= 3 {
                    println!("{}: {} differ", what, name);
                }
            }
        }
        bad
    };
    let mut bad = 0;
    for f in files {
        let text = std::fs::read(f).unwrap_or_default();
        bad += check(&text, f);
    }
    let bits: [&[u8]; 24] = [b"\n", b"\r\n", b"\t", b"\t\t", b"{", b"}", b"=", b" ", b"ENG", b"A1", b"x_y",
        b"farmers", b"12", b"active_inventions", b"technology", b"name", b"\n\t}", b"\n{", b"\xe9",
        b"\x85", b"a", b"\x1c", b"1 2", b"\r"];
    let mut seed = 0x9e37_79b9_7f4a_7c15u64;
    let mut rnd = |n: usize| {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        (seed % n as u64) as usize
    };
    let mut cases = 0;
    for _ in 0..40000 {
        let mut text = Vec::new();
        for _ in 0..rnd(40) {
            text.extend_from_slice(bits[rnd(bits.len())]);
        }
        cases += 1;
        bad += check(&text, "random");
    }
    println!("{} files and {} random texts: {} differ", files.len(), cases, bad);
    std::process::exit(if bad == 0 { 0 } else { 1 });
}

/// What a folder defines, as `_mod_facts` keeps it.
struct Facts {
    tags: BTreeSet<String>,
    pops: BTreeSet<String>,
    techs: BTreeSet<String>,
    inventions: i64,
    provinces: BTreeSet<i64>,
}

fn mod_facts(root: &str) -> Result<Facts, String> {
    let back = |d: crate::engine::rules::Decline| d.0;
    let f = modread::facts(root).map_err(back)?;
    Ok(Facts {
        tags: f.tags.into_iter().collect(),
        pops: f.pops.into_iter().collect(),
        techs: f.techs.into_iter().collect(),
        inventions: f.inventions,
        provinces: f.provinces.into_iter().collect(),
    })
}

/// `match_mod(files, candidates)`: (label, path, [(label, verdict, detail)]).
#[allow(clippy::type_complexity)]
fn match_mod(files: &[String], candidates: &[(String, String)], facts: &mut HashMap<String, Facts>)
             -> Result<(Option<String>, Option<String>, Vec<(String, String, String)>), String> {
    let take = files.len().saturating_sub(2);
    let mut sniffed = Vec::new();
    for f in &files[take..] {
        sniffed.push(sniff(f)?);
    }
    let tags: BTreeSet<String> = sniffed.iter().flat_map(|s| s.tags.iter().cloned()).collect();
    let mut pops: BTreeSet<String> = sniffed.iter().flat_map(|s| s.pops.iter().cloned()).collect();
    let techs: BTreeSet<String> = sniffed.iter().flat_map(|s| s.techs.iter().cloned()).collect();
    let top = sniffed.iter().map(|s| s.top).max().unwrap_or(0);
    let provinces: BTreeSet<i64> = sniffed.iter().flat_map(|s| s.provinces.iter().copied()).collect();
    for (_label, root) in candidates {
        if !facts.contains_key(root) {
            facts.insert(root.clone(), mod_facts(root)?);
        }
    }
    if !candidates.is_empty() {
        let defined: BTreeSet<&String> = candidates.iter().flat_map(|(_, r)| facts[r].pops.iter()).collect();
        pops.retain(|p| defined.contains(p));
    }
    let mut rows = Vec::new();
    let mut fits: Vec<((f64, i64), String, String)> = Vec::new();
    let mut near: Vec<(i64, String, String, String)> = Vec::new();
    for (label, root) in candidates {
        let f = &facts[root];
        let mut why = Vec::new();
        let unknown: Vec<&String> = tags.difference(&f.tags).collect();
        if !unknown.is_empty() {
            why.push(format!("{} unknown tag{} ({})", unknown.len(), if unknown.len() == 1 { "" } else { "s" },
                             unknown.iter().take(4).map(|s| s.as_str()).collect::<Vec<_>>().join(" ")));
        }
        let missing: Vec<&String> = pops.difference(&f.pops).collect();
        if !missing.is_empty() {
            why.push(format!("no pop type {}", missing.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", ")));
        }
        let stray: Vec<&String> = techs.difference(&f.techs).collect();
        if !stray.is_empty() {
            why.push(format!("{} unknown technolog{} ({})", stray.len(), if stray.len() == 1 { "y" } else { "ies" },
                             stray.iter().take(3).map(|s| s.as_str()).collect::<Vec<_>>().join(" ")));
        }
        let gap = provinces.symmetric_difference(&f.provinces).count() as i64;
        if !provinces.is_empty() && !f.provinces.is_empty() && gap != 0 {
            why.push(format!("map has {} provinces, these saves {}", f.provinces.len(), provinces.len()));
        }
        if top > f.inventions {
            why.push(format!("save names invention {}, folder builds {}", top, f.inventions));
        }
        if !why.is_empty() {
            let distance = unknown.len() as i64 + missing.len() as i64 + stray.len() as i64 + gap
                + (top - f.inventions).max(0);
            near.push((distance, label.clone(), root.clone(), why.join("; ")));
            rows.push((label.clone(), "no".to_string(), why.join("; ")));
            continue;
        }
        let unused = f.tags.difference(&tags).count();
        let rank = (unused as f64 / f.tags.len().max(1) as f64, f.inventions - top);
        fits.push((rank, label.clone(), root.clone()));
        rows.push((label.clone(), "fits".to_string(),
                   format!("{} of its {} countries never mentioned, {} spare invention slots",
                           unused, f.tags.len(), f.inventions - top)));
    }
    if fits.is_empty() {
        if near.is_empty() {
            return Ok((None, None, rows));
        }
        near.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let (_d, label, root, why) = near.remove(0);
        rows.push((label.clone(), "nearest".to_string(), why));
        return Ok((Some(label), Some(root), rows));
    }
    fits.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let (_r, label, root) = fits.remove(0);
    Ok((Some(label), Some(root), rows))
}

// ------------------------------------------------------ one history

fn head_of(path: &str) -> Option<Vec<u8>> {
    use std::io::Read;
    let mut f = std::fs::File::open(path).ok()?;
    let mut buf = vec![0u8; 400_000];
    let mut got = 0;
    while got < buf.len() {
        match f.read(&mut buf[got..]) {
            Ok(0) => break,
            Ok(k) => got += k,
            Err(_) => return None,
        }
    }
    buf.truncate(got);
    Some(buf)
}

/// `savehead.fields(head)["date"]`, parsed by `ymd`.
fn head_key(head: &[u8]) -> Result<Vec<i64>, String> {
    let re = Re::ascii(r#"(date|player|start_date)\s*=\s*"([^"]*)""#, false, false);
    let mut date = None;
    let mut seen: Vec<&[u8]> = Vec::new();
    for m in re.find_all(head) {
        let key = m.group(head, 1);
        if !seen.contains(&key) {
            seen.push(key);
            if key == b"date" {
                date = Some(m.group(head, 2).to_vec());
            }
        }
        if seen.len() == 3 {
            break;
        }
    }
    let parts: Vec<&[u8]> = match &date {
        Some(d) => d.split(|&c| c == b'.').collect(),
        None => return Ok(vec![0]),
    };
    if parts.len() != 3 {
        return Ok(vec![0]);
    }
    let mut out = Vec::new();
    for p in parts {
        match modread::py_int(p).map_err(|e| e.0)? {
            Some(v) => out.push(v),
            None => return Ok(vec![0]),
        }
    }
    Ok(out)
}

/// `savehead.flags_in(head)`.
fn flags_in(head: &[u8]) -> BTreeSet<Vec<u8>> {
    let block = Re::ascii(r"^flags=\s*\{(.*?)^\}", true, true);
    let name = Re::ascii(r"^\s*([A-Za-z_]\w*)\s*=", true, false);
    match block.search(head, 0) {
        Some(m) => {
            let b = m.group(head, 1);
            name.find_all(b).iter().map(|n| n.group(b, 1).to_vec()).collect()
        }
        None => BTreeSet::new(),
    }
}

/// `history_breaks(files)`: [(file, worst, later saves checked)].
fn history_breaks(files: &[String]) -> Result<Vec<(String, usize, usize)>, String> {
    let mut heads = Vec::new();
    for path in files {
        let head = match head_of(path) {
            Some(h) => h,
            None => continue,
        };
        heads.push((basename(path), head_key(&head)?, flags_in(&head)));
    }
    let mut out = Vec::new();
    for (file, key, flags) in &heads {
        if flags.len() < 3 {
            continue;
        }
        let later: Vec<&BTreeSet<Vec<u8>>> = heads.iter().filter(|o| o.1 > *key).map(|o| &o.2).collect();
        if later.len() < 2 {
            continue;
        }
        let worst = later.iter().map(|o| flags.difference(o).count()).min().unwrap();
        if worst >= 6 {
            out.push((file.clone(), worst, later.len()));
        }
    }
    Ok(out)
}

// ------------------------------------------------------------ the survey

/// One campaign folder, and the mod it will be read under (`Surveyed`).
pub struct Surveyed {
    name: String,
    files: Vec<String>,
    mod_label: Option<String>,
    mod_path: Option<String>,
    candidates: Vec<(String, String, String)>,
    told: bool,
}

/// `%-22s`.
fn left(text: &str, width: usize) -> String {
    let n = text.chars().count();
    if n >= width { text.to_string() } else { format!("{}{}", text, " ".repeat(width - n)) }
}

/// `%3d`.
fn right(text: &str, width: usize) -> String {
    let n = text.chars().count();
    if n >= width { text.to_string() } else { format!("{}{}", " ".repeat(width - n), text) }
}

/// The saves of a campaign that may be from another game, said under the
/// campaign they are in. Python said them all after the survey, so the
/// note read as if it were about whichever campaign was listed last.
fn say_strays(e: &Surveyed) {
    for (stray, worst, of) in history_breaks(&e.files).unwrap_or_else(|why| hand_back(&why)) {
        crate::outln!("      note: {} disagrees with all {} later saves by at least {} event flags; \
                       it may be from another game", stray, of, worst);
    }
}

/// `survey_cross(parent, game_root, args)`.
pub fn survey_cross(parent: &str, args: &Args, verbose: bool) -> R<Vec<Surveyed>> {
    let game_root = args.game_root.as_deref().filter(|g| !g.is_empty());
    let on_the_game = |path: Option<&str>, flag: &str| -> R<()> {
        match super::settle_game(path, game_root) {
            Ok(_) => Ok(()),
            Err(RunError(why)) => Err(RunError(format!("{}: {}", flag, why))),
        }
    };
    if game_root.is_some() {
        on_the_game(None, "--game-root")?;
    }
    let mut chosen: Vec<(String, String)> = Vec::new();
    for (name, path) in &args.campaign_mod {
        let path = pypath::expanduser(&pypath::expandvars(path));
        if !pypath::isdir(&join(&path, "common")) {
            return refuse(format!("--campaign-mod {}: {} has no common/ inside it, so it is not a mod \
                                   folder.", name, path));
        }
        on_the_game(Some(&path), &format!("--campaign-mod {}", name))?;
        let key = name.to_lowercase();
        match chosen.iter_mut().find(|(k, _)| *k == key) {
            Some(slot) => slot.1 = path,
            None => chosen.push((key, path)),
        }
    }
    let mod_path = args.mod_path.as_deref().filter(|m| !m.is_empty());
    if let Some(m) = mod_path {
        on_the_game(Some(m), "--mod-path")?;
    }
    let told_for = |name: &str| chosen.iter().find(|(k, _)| *k == name.to_lowercase()).map(|(_, p)| p.clone());
    let found: Vec<Surveyed>;
    if let Some(m) = mod_path {
        let label = basename(&pypath::normpath(m));
        found = campaigns_in(parent).into_iter().map(|(name, _path, files)| {
            let told = told_for(&name);
            Surveyed {
                mod_label: Some(match &told {
                    Some(t) => basename(&pypath::normpath(t)),
                    None => label.clone(),
                }),
                mod_path: Some(told.clone().unwrap_or_else(|| m.to_string())),
                told: told.is_some(),
                name,
                files,
                candidates: Vec::new(),
            }
        }).collect();
        if verbose {
            let odd = found.iter().filter(|e| e.told).count();
            crate::outln!("Campaigns found under {}, read under {}{}:", parent, label,
                          if odd == 0 { "" } else { " except where named" });
            for e in &found {
                crate::outln!("  {} {} saves{}", left(&e.name, 22), right(&e.files.len().to_string(), 3),
                              if e.told { format!("  ->  {}   (as told)", e.mod_label.as_ref().unwrap()) }
                              else { String::new() });
                say_strays(e);
            }
        }
    } else if game_root.is_none() && chosen.is_empty() {
        return refuse("--cross needs --game-root (the Victoria 2 install folder, the one with mod/ \
                       inside) to work each campaign's mod out, --mod-path to read them all under one \
                       mod, or --campaign-mod to name them one at a time.");
    } else {
        let folders = campaigns_in(parent);
        let unsettled = folders.iter().any(|(n, _, _)| told_for(n).is_none());
        let mut list: Vec<Surveyed> = Vec::new();
        if unsettled && game_root.is_some() {
            let mods = installed_mods(game_root.unwrap());
            let mut facts = HashMap::new();
            for (name, _path, files) in folders {
                let (label, root, rows) = match_mod(&files, &mods, &mut facts)
                    .unwrap_or_else(|why| hand_back(&why));
                list.push(Surveyed { name, files, mod_label: label, mod_path: root, candidates: rows,
                                     told: false });
            }
        } else {
            for (name, _path, files) in folders {
                list.push(Surveyed { name, files, mod_label: None, mod_path: None, candidates: Vec::new(),
                                     told: false });
            }
        }
        for e in &mut list {
            if let Some(over) = told_for(&e.name) {
                e.mod_label = Some(basename(&pypath::normpath(&over)));
                e.mod_path = Some(over);
                e.candidates.clear();
                e.told = true;
            }
        }
        found = list;
        if verbose {
            crate::outln!("Campaigns found under {}:", parent);
            for e in &found {
                let fits = e.candidates.iter().filter(|r| r.1 == "fits").count();
                crate::outln!("  {} {} saves  ->  {}{}", left(&e.name, 22), right(&e.files.len().to_string(), 3),
                              e.mod_label.clone().unwrap_or_else(|| "no mod in that folder fits".into()),
                              if e.told { "   (as told)" } else { "" });
                if e.told {
                    say_strays(e);
                    continue;
                }
                let nearest: Vec<&(String, String, String)> = e.candidates.iter().filter(|r| r.1 == "nearest").collect();
                if let Some(n) = nearest.first() {
                    crate::outln!("      WARNING: nothing in {} explains these saves. The closest is {}, and it \
                                   does not match: {}. The numbers below are computed against a mod this \
                                   campaign was not played on -- name the right one with --mod-path.",
                                  game_root.unwrap_or("None"), n.0, n.2);
                } else if fits > 1 {
                    crate::outln!("      note: {} mods fit these saves; picked the one the campaign leaves \
                                   least of unused. Name it with --mod-path, or in the window pick the mod \
                                   itself instead of the folder, to settle it.", fits);
                } else if e.mod_label.is_none() {
                    crate::outln!("      note: nothing in {} explains these saves. If the mod is installed \
                                   elsewhere, point the mod box at it directly.", game_root.unwrap_or("None"));
                }
                say_strays(e);
            }
        }
    }
    Ok(found)
}

/// The stamp of a `--cross` run: every campaign that will be read, its
/// saves, and the mod it is read under.
pub fn cross_stamp(found: &[Surveyed], args: &Args) -> String {
    let read: Vec<&Surveyed> = found.iter().filter(|e| e.mod_path.is_some()).collect();
    let world: Vec<String> = read.iter().map(|e| {
        let m = e.mod_path.as_ref().unwrap();
        format!("{}|{}|{}", e.name, abspath(m), super::mod_signature(Some(m)))
    }).collect();
    let files: Vec<String> = read.iter().flat_map(|e| e.files.iter().cloned()).collect();
    super::report_stamp(&files, args, &world.join("\n"))
}

// ---------------------------------------------------------- the reading

/// `run_cross`: (the comparison as the page carries it, the primary
/// campaign's saves, its mod).
pub fn run_cross(parent: &str, found: &[Surveyed], args: &Args, verbose: bool, protocol: bool)
                 -> R<(Option<String>, Vec<String>, Option<String>)> {
    let mut results: Vec<(String, String, Vec<(String, String, Vec<Option<f64>>)>)> = Vec::new();
    let mut names: Vec<(String, String)> = Vec::new();
    let mut primary: Option<(&Surveyed, Vec<String>)> = None;
    for e in found {
        let mod_path = match &e.mod_path {
            Some(m) => m,
            None => {
                if verbose {
                    crate::outln!("  skipping {}: no mod in {} explains its saves", e.name,
                                  args.game_root.as_deref().unwrap_or("None"));
                }
                continue;
            }
        };
        // `load_mod` raises out of `run_cross` rather than refusing: that
        // much is Python's to say.
        let set = match super::setup(args, mod_path) {
            Ok(s) => s,
            Err(super::Settle::Refused(why)) | Err(super::Settle::Back(why)) => hand_back(&why),
        };
        let dates = super::dates_of(&e.files);
        let files = super::in_date_order(e.files.clone(), dates);
        if verbose {
            crate::outln!("Reading {} ({} saves) under {}", e.name, files.len(), e.mod_label.as_deref().unwrap_or(""));
        }
        let mut spec = super::spec_for(args, &set, &files, protocol);
        if let J::Obj(pairs) = &mut spec {
            for (k, v) in pairs.iter_mut() {
                if k == "quiet" {
                    *v = J::Bool(true);
                }
            }
            pairs.push(("cross_part".into(), J::Bool(true)));
        }
        let done = crate::engine::run_spec(&spec, None).expect("a campaign read returns what it read");
        if let Some(why) = done.run_error {
            return refuse(format!("{}: {}", e.name, why));
        }
        let part = match done.cross_part {
            Some(p) => p,
            None => continue,
        };
        results.push((e.name.clone(), e.mod_label.clone().unwrap_or_default(), part.rows));
        for (tag, label) in part.names {
            if !names.iter().any(|(t, _)| *t == tag) {
                names.push((tag, label));
            }
        }
        match &args.primary {
            Some(p) => {
                if e.name.to_lowercase() == p.to_lowercase() {
                    primary = Some((e, files));
                }
            }
            None => {
                if primary.as_ref().is_none_or(|(_, f)| files.len() > f.len()) {
                    primary = Some((e, files));
                }
            }
        }
    }
    if let (Some(p), None, false) = (&args.primary, &primary, results.is_empty()) {
        let known: Vec<&str> = results.iter().map(|r| r.0.as_str()).collect();
        return refuse(format!("No campaign called {} under {}. There is: {}",
                              modread::py_repr(p), parent, known.join(", ")));
    }
    let (entry, files) = match primary {
        Some(p) if !results.is_empty() => p,
        _ => return Ok((None, Vec::new(), args.mod_path.clone())),
    };
    let (payload, campaigns, tags) = series_payload(&results, &names);
    if verbose {
        crate::outln!("Cross-campaign: {} campaigns, {} nations in two or more of them.", campaigns, tags);
        crate::outln!("The rest of the report is {}{}.", entry.name,
                      if args.primary.is_some() { "" } else { " (the most saves; --primary picks another)" });
    }
    let mut text = String::new();
    payload.write(&mut text);
    Ok((Some(text), files, entry.mod_path.clone()))
}

/// `series_payload(results, names)`: the block the report carries, and how
/// many campaigns and shared nations it holds.
#[allow(clippy::type_complexity)]
fn series_payload(results: &[(String, String, Vec<(String, String, Vec<Option<f64>>)>)],
                  names: &[(String, String)]) -> (J, usize, usize) {
    use crate::engine::dates::year_fraction;
    use crate::pyfmt::round;
    let tables = crate::engine::tables::Tables::builtin(&[], String::new());
    let metrics = &tables.metrics;
    let mut seen: Vec<(String, BTreeSet<&str>)> = Vec::new();
    for (name, _m, rows) in results {
        for (_d, tag, _v) in rows {
            match seen.iter_mut().find(|(t, _)| t == tag) {
                Some(slot) => {
                    slot.1.insert(name);
                }
                None => {
                    let mut s = BTreeSet::new();
                    s.insert(name.as_str());
                    seen.push((tag.clone(), s));
                }
            }
        }
    }
    let mut shared: Vec<String> = seen.iter().filter(|(_, w)| w.len() >= 2).map(|(t, _)| t.clone()).collect();
    shared.sort();
    let keep: BTreeSet<&str> = shared.iter().map(|s| s.as_str()).collect();
    let mut used: BTreeSet<String> = BTreeSet::new();
    let mut campaigns = Vec::new();
    let mut series = Vec::new();
    for (name, label, rows) in results {
        // `sorted({dates}, key=year_fraction)`: a set, so its order before
        // the sort is Python's hash order; dates that tie on the key keep it.
        // No two real dates tie, and every save of a campaign has its own.
        let mut dates: Vec<&str> = Vec::new();
        for (d, _, _) in rows {
            if !dates.contains(&d.as_str()) {
                dates.push(d);
            }
        }
        dates.sort_by(|a, b| year_fraction(a).partial_cmp(&year_fraction(b)).unwrap());
        let start = dates.first().map(|d| year_fraction(d)).unwrap_or(0.0);
        // {tag: {key: {date: value}}}
        let mut by_tag: Vec<(String, Vec<(String, crate::omap::OMap<String, f64>)>)> = Vec::new();
        for (date, tag, values) in rows {
            if !keep.contains(tag.as_str()) {
                continue;
            }
            let i = match by_tag.iter().position(|(t, _)| t == tag) {
                Some(i) => i,
                None => {
                    by_tag.push((tag.clone(), Vec::new()));
                    by_tag.len() - 1
                }
            };
            for (k, (key, _l, _f)) in metrics.iter().enumerate() {
                if let Some(v) = values[k] {
                    let slot = &mut by_tag[i].1;
                    let j = match slot.iter().position(|(n, _)| n == key) {
                        Some(j) => j,
                        None => {
                            slot.push((key.clone(), crate::omap::OMap::new()));
                            slot.len() - 1
                        }
                    };
                    slot[j].1.set(date.clone(), v);
                }
            }
        }
        for (_tag, slot) in by_tag.iter_mut() {
            for (key, source, _l) in tables.growth.iter() {
                if let Some(src) = slot.iter().find(|(n, _)| n == source).map(|(_, m)| m) {
                    let readings: Vec<(&str, Option<f64>)> = dates.iter().map(|d| (*d, src.get(*d).copied())).collect();
                    let got = crate::engine::report::growth_series(&readings, tables.growth_span);
                    set_slot(slot, key, got);
                }
            }
            for (key, source, _l) in tables.gain.iter() {
                if let Some(src) = slot.iter().find(|(n, _)| n == source).map(|(_, m)| m) {
                    let readings: Vec<(&str, Option<f64>)> = dates.iter().map(|d| (*d, src.get(*d).copied())).collect();
                    let got = crate::engine::report::gain_series(&readings);
                    set_slot(slot, key, got);
                }
            }
        }
        let mut block = Vec::new();
        for (tag, slot) in &by_tag {
            let mut inner = Vec::new();
            for (key, dated) in slot {
                if dated.is_empty() {
                    continue;
                }
                used.insert(key.clone());
                let mut ds: Vec<(&String, &f64)> = dated.iter().collect();
                ds.sort_by(|a, b| year_fraction(a.0).partial_cmp(&year_fraction(b.0)).unwrap());
                inner.push((key.clone(), J::List(ds.iter().map(|(d, v)| {
                    let y = year_fraction(d);
                    J::List(vec![J::Float(round(y, 3)), J::Float(round(y - start, 3)), J::Float(round(**v, 4))])
                }).collect())));
            }
            if !inner.is_empty() {
                block.push((tag.clone(), J::Obj(inner)));
            }
        }
        campaigns.push(J::Obj(vec![
            ("name".into(), J::Str(name.clone())),
            ("mod".into(), J::Str(if label.is_empty() { "unmatched".into() } else { label.clone() })),
            ("saves".into(), J::Int(dates.len() as i64)),
            ("from".into(), J::Float(round(start, 3))),
            ("to".into(), match dates.last() {
                Some(d) => J::Float(round(year_fraction(d), 3)),
                None => J::Null,
            }),
            ("dates".into(), J::List(dates.iter().map(|d| {
                J::List(vec![J::Float(round(year_fraction(d), 3)), J::Str(d.to_string())])
            }).collect())),
        ]));
        series.push(J::Obj(block));
    }
    const RULEBOUND: [&str; 3] = ["mobilization_pool", "mobilization_brigades", "mobilisation_size"];
    let mut out_metrics = Vec::new();
    for (key, label, fmt) in metrics {
        if used.contains(key) {
            out_metrics.push(J::Obj(vec![
                ("key".into(), J::Str(key.clone())),
                ("label".into(), J::Str(label.clone())),
                ("fmt".into(), J::Str(fmt.clone())),
                ("rulebound".into(), J::Bool(RULEBOUND.contains(&key.as_str()))),
            ]));
        }
    }
    for (key, _s, label) in &tables.growth {
        if used.contains(key) {
            out_metrics.push(J::Obj(vec![
                ("key".into(), J::Str(key.clone())),
                ("label".into(), J::Str(label.clone())),
                ("fmt".into(), J::Str("percent".into())),
                ("rate".into(), J::Int(1)),
                ("rulebound".into(), J::Bool(false)),
            ]));
        }
    }
    for (key, _s, label) in &tables.gain {
        if used.contains(key) {
            out_metrics.push(J::Obj(vec![
                ("key".into(), J::Str(key.clone())),
                ("label".into(), J::Str(label.clone())),
                ("fmt".into(), J::Str("count".into())),
                ("delta".into(), J::Int(1)),
                ("rulebound".into(), J::Bool(false)),
            ]));
        }
    }
    let n_campaigns = campaigns.len();
    let n_tags = shared.len();
    let tag_names = J::Obj(shared.iter().map(|t| {
        let label = names.iter().find(|(n, _)| n == t).map(|(_, l)| l.clone()).unwrap_or_else(|| t.clone());
        (t.clone(), J::Str(label))
    }).collect());
    (J::Obj(vec![
        ("campaigns".into(), J::List(campaigns)),
        ("tags".into(), J::List(shared.iter().map(|t| J::Str(t.clone())).collect())),
        ("tagNames".into(), tag_names),
        ("metrics".into(), J::List(out_metrics)),
        ("series".into(), J::List(series)),
    ]), n_campaigns, n_tags)
}

fn set_slot(slot: &mut Vec<(String, crate::omap::OMap<String, f64>)>, key: &str,
            value: crate::omap::OMap<String, f64>) {
    match slot.iter_mut().find(|(n, _)| n == key) {
        Some(s) => s.1 = value,
        None => slot.push((key.to_string(), value)),
    }
}

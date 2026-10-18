// The reader: a mod folder and the game folders it inherits from, each
// file found, read and cut into blocks, as mod_reader.py does.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;

pub(super) struct Pats {
    pub(super) comment: Re,
    pub(super) opens: Re,
    pub(super) not_block: Re,
    pub(super) limit: Re,
    pub(super) req: Re,
    pub(super) tag: Re,
    pub(super) invention: Re,
    pub(super) chance: Re,
    pub(super) base: Re,
    pub(super) modifier: Re,
    pub(super) factor: Re,
    pub(super) blocked: Re,
    pub(super) lua_comment: Re,
    pub(super) strata: Re,
    pub(super) country_entry: Re,
    pub(super) war_policy: Re,
    pub(super) word_block: Re,
    pub(super) impact: Re,
    pub(super) region: Re,
    pub(super) line_block: Re,
    pub(super) unit_type: Re,
    pub(super) klass: Re,
    pub(super) ship_block: Re,
    pub(super) ship_stat: Re,
    pub(super) color: Re,
    pub(super) sea: Re,
    pub(super) change_tag: Re,
    pub(super) tag3: Re,
}

impl Pats {
    pub(super) fn new() -> Pats {
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

pub(super) type Top = Rc<Vec<(Vec<u8>, V)>>;

/// One line of a localisation file with a name on it: its key, its first
/// column, and whether the line is a comment.
pub(super) struct Loc {
    pub(super) key: String,
    pub(super) english: String,
    pub(super) hash: bool,
}

pub struct Reader {
    pub(super) path: String,
    pub(super) base: Option<String>,
    pub(super) re: Pats,
    pub(super) plain: RefCell<HashMap<String, Rc<Vec<u8>>>>,
    pub(super) trees: RefCell<HashMap<String, Top>>,
    pub(super) loc: RefCell<Option<Rc<Vec<Loc>>>>,
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
    if lower(&basename(&parent)) != "mod" {
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
    pub(super) fn game_then_mod(&self) -> Vec<&str> {
        let mut v = Vec::new();
        if let Some(b) = &self.base {
            v.push(b.as_str());
        }
        v.push(self.path.as_str());
        v
    }

    pub(super) fn mod_then_game(&self) -> Vec<&str> {
        let mut v = vec![self.path.as_str()];
        if let Some(b) = &self.base {
            v.push(b.as_str());
        }
        v
    }

    pub(super) fn resolved_file(&self, parts: &[&str]) -> String {
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
    pub(super) fn files(folder: &str) -> D<Vec<String>> {
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
    pub(super) fn resolved_files(&self, folder: &str) -> D<Vec<(String, String)>> {
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

    pub(super) fn read(path: &str) -> D<Vec<u8>> {
        std::fs::read(path).or_else(|e| raised(crate::engine::readsave::os_error_text(&e, path)))
    }

    /// `_plain`: one file with its comments cut out.
    pub(super) fn plain(&self, path: &str) -> D<Rc<Vec<u8>>> {
        if let Some(t) = self.plain.borrow().get(path) {
            return Ok(t.clone());
        }
        let raw = Reader::read(path)?;
        let t = Rc::new(self.re.comment.remove(&raw));
        self.plain.borrow_mut().insert(path.to_string(), t.clone());
        Ok(t)
    }

    /// `read_clausewitz`: every top-level `key = { ... }`, in file order.
    pub(super) fn clausewitz(&self, path: &str) -> D<Top> {
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
    pub(super) fn block_text<'t>(&self, raw: &'t [u8], name: &[u8]) -> &'t [u8] {
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

    pub(super) fn opens_at<'t>(&self, raw: &'t [u8], at: usize, len: usize) -> Option<&'t [u8]> {
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
    pub(super) fn limit_of(&self, text: &[u8]) -> (Set, Set, Set) {
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
    pub(super) fn chance_floor(&self, text: &[u8]) -> D<(Option<f64>, Vec<(f64, Vec<u8>)>)> {
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
    pub(super) fn named_blocks<'t>(&self, text: &'t [u8], keyword: &[u8]) -> Vec<&'t [u8]> {
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
    pub(super) fn drop_block(&self, text: &[u8], keyword: &[u8]) -> Vec<u8> {
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
    pub(super) fn ship_changes(&self, text: &[u8]) -> D<OMap<Vec<u8>, OMap<Vec<u8>, f64>>> {
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
    pub(super) fn loc(&self) -> D<Rc<Vec<Loc>>> {
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
    pub(super) fn text_localisation(&self, wanted: &HashSet<String>) -> D<OMap<String, String>> {
        let mut out: OMap<String, String> = OMap::new();
        for l in self.loc()?.iter() {
            if wanted.contains(&l.key) && !out.contains_key(&l.key) {
                out.set(l.key.clone(), l.english.clone());
            }
        }
        Ok(out)
    }

    /// `_read_localisation`: country names, and their per-government forms.
    pub(super) fn read_localisation(&self) -> D<OMap<String, String>> {
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

pub(super) const SHIP_STATS: [&[u8]; 5] = [b"hull", b"gun_power", b"evasion", b"torpedo_attack",
                                b"supply_consumption_score"];

pub(super) const NOT_A_CULTURE: [&[u8]; 5] = [b"color", b"unit", b"union", b"leader", b"is_overseas"];

pub(super) fn find(hay: &[u8], needle: &[u8]) -> Option<usize> {
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
pub(super) fn body_of(text: &[u8], start: usize) -> &[u8] {
    match block_end(text, start) {
        Some(end) => &text[start..end - 1],
        None => &text[start..],
    }
}

/// `str.splitlines()` of Windows-1252 text, done on the bytes: every byte
/// that ends a line decodes to itself.
pub(super) fn split_lines(b: &[u8]) -> Vec<&[u8]> {
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
pub(super) fn loc_strip(b: &[u8]) -> &[u8] {
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

pub(super) const CP1252: [u32; 32] = [
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
pub(super) fn country_key(k: &str) -> bool {
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
pub(super) fn pretty(key: &str) -> String {
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
pub(super) fn title(c: char) -> String {
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
pub(super) fn stem(name: &str) -> &str {
    let sep = name.rfind(is_sep).map_or(0, |i| i + 1);
    match name.rfind('.') {
        Some(dot) if dot > sep => {
            if name[sep..dot].chars().any(|c| c != '.') { &name[..dot] } else { name }
        }
        _ => name,
    }
}

/// `f[:-4]`.
pub(super) fn cut4(name: &str) -> &str {
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
pub(super) fn find_mob_size(block: &V) -> f64 {
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
pub(super) fn trigger_conditions(trigger: &V, out: &mut HashSet<Vec<u8>>) {
    if !is_dict(trigger) {
        return;
    }
    for (key, value) in pairs(trigger) {
        if key == b"AND" || key == b"OR" || key == b"NOT" {
            for part in crate::save::clause::as_list(Some(value)) {
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
pub(super) fn flatten_effects<'a>(block: impl Iterator<Item = &'a (Vec<u8>, V)>, skip: &[&[u8]], prefix: &[u8],
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

pub(super) const TECH_SKIP: [&[u8]; 8] = [b"area", b"year", b"cost", b"ai_chance", b"unciv_military",
                               b"unciv_naval", b"unciv_economic", b"unciv_culture"];
pub(super) const INVENTION_SKIP: [&[u8]; 3] = [b"icon", b"limit", b"chance"];

/// `_invention_effects`: its own fields, then those of its `effect`.
pub(super) fn invention_effects(block: &V) -> Vec<(Vec<u8>, Vec<u8>)> {
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
pub(super) fn brace_blocks(text: &[u8]) -> Vec<&[u8]> {
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

pub(super) fn fmap(m: &OMap<Vec<u8>, f64>) -> J {
    J::Obj(m.iter().map(|(k, v)| (l1(k), J::Float(*v))).collect())
}

pub(super) fn smap(m: &OMap<String, String>) -> J {
    J::Obj(m.iter().map(|(k, v)| (k.clone(), J::Str(v.clone()))).collect())
}

pub(super) fn ship_json(m: &OMap<Vec<u8>, OMap<Vec<u8>, f64>>) -> J {
    J::Obj(m.iter().map(|(k, v)| (l1(k), fmap(v))).collect())
}

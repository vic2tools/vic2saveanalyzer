// One function per game file: what each of the mod's files contributes.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;
use crate::py::num::int_latin1;

impl Reader {
    pub(super) fn read_defines(&self) -> D<OMap<Vec<u8>, f64>> {
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

    pub(super) fn read_poptypes(&self) -> D<OMap<String, Vec<u8>>> {
        let mut out = OMap::new();
        for (name, target) in self.resolved_files("poptypes")? {
            let text = self.plain(&target)?;
            if let Some(m) = self.re.strata.search(&text, 0) {
                out.set(lower(stem(&name)), lower1(m.group(&text, 1)));
            }
        }
        Ok(out)
    }

    pub(super) fn country_entries(&self) -> D<Vec<(Vec<u8>, Vec<u8>)>> {
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
    pub(super) fn party_policies(&self) -> D<Vec<Vec<u8>>> {
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

    pub(super) fn modifier_mob_impacts(&self) -> D<OMap<Vec<u8>, f64>> {
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

    pub(super) fn mobilization_impacts(&self) -> D<OMap<Vec<u8>, f64>> {
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

    pub(super) fn reform_mob(&self) -> D<(OMap<(Vec<u8>, Vec<u8>), f64>, Vec<Vec<u8>>)> {
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

    pub(super) fn static_mob(&self) -> D<OMap<Vec<u8>, f64>> {
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
    pub(super) fn triggered_mob(&self) -> D<Vec<(Vec<u8>, f64, f64, Option<(Top, usize)>)>> {
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

    pub(super) fn culture_blocks(&self, mut each: impl FnMut(&[u8], &[u8])) -> D<()> {
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

    pub(super) fn continents(&self) -> D<Vec<(i64, Vec<u8>)>> {
        let target = self.map_file("continent.txt");
        let mut out: OMap<i64, Vec<u8>> = OMap::new();
        if !is_file(&target) {
            return Ok(Vec::new());
        }
        for (name, block) in self.clausewitz(&target)?.iter() {
            if !is_dict(block) {
                continue;
            }
            for pid in crate::save::clause::as_list(get(block, b"provinces")) {
                if let V::Str(_) = pid {
                    out.set(to_int(Some(pid), -1)?, name.clone());
                }
            }
        }
        Ok(out.iter().map(|(k, v)| (*k, v.clone())).collect())
    }

    pub(super) fn base_prices(&self) -> D<OMap<Vec<u8>, f64>> {
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

    pub(super) fn regions(&self) -> D<OMap<Vec<u8>, Vec<i64>>> {
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
                    ids.push(int_latin1(n)?.unwrap());
                }
            }
            if !ids.is_empty() {
                out.set(hit.group(&text, 1).to_vec(), ids);
            }
        }
        Ok(out)
    }

    pub(super) fn unit_kinds(&self) -> D<OMap<Vec<u8>, Vec<u8>>> {
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

    pub(super) fn naval_units(&self) -> D<J> {
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

    pub(super) fn naval_tech_effects(&self) -> D<J> {
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

    pub(super) fn naval_invention_effects(&self) -> D<J> {
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

    pub(super) fn map_source(&self) -> String {
        let own = join(&self.path, "map");
        if is_file(&join(&own, "provinces.bmp")) && is_file(&join(&own, "definition.csv")) {
            return self.path.clone();
        }
        self.base.clone().unwrap_or_else(|| self.path.clone())
    }

    pub(super) fn map_file(&self, name: &str) -> String {
        joins(&self.map_source(), &["map", name])
    }

    pub(super) fn country_files(&self) -> D<OMap<Vec<u8>, String>> {
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

    pub(super) fn country_colours(&self) -> D<J> {
        let mut out = Vec::new();
        for (tag, target) in self.country_files()?.iter() {
            let text = self.plain(target)?;
            if let Some(hit) = self.re.color.search(&text, 0) {
                let mut s = String::from("#");
                for g in 1..=3 {
                    let v = int_latin1(hit.group(&text, g))?.unwrap();
                    s.push_str(&format!("{:02x}", v));
                }
                out.push((l1(tag), J::Str(s)));
            }
        }
        Ok(J::Obj(out))
    }

    pub(super) fn sea_provinces(&self) -> D<Vec<i64>> {
        let target = self.map_file("default.map");
        if !is_file(&target) {
            return Ok(Vec::new());
        }
        let text = self.plain(&target)?;
        let mut out = BTreeSet::new();
        if let Some(hit) = self.re.sea.search(&text, 0) {
            for n in split_ws(hit.group(&text, 1)) {
                if digit_word(n)? {
                    out.insert(int_latin1(n)?.unwrap());
                }
            }
        }
        Ok(out.into_iter().collect())
    }

    pub(super) fn unit_positions(&self) -> D<Vec<J>> {
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
            if let Some(p) = int_latin1(key)? {
                out.set(p, at);
            }
        }
        Ok(out.iter().map(|(p, (x, y))| J::List(vec![J::Int(*p), J::Float(*x), J::Float(*y)])).collect())
    }

    pub(super) fn province_names(&self) -> D<Vec<J>> {
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
            let pid = match int_latin1(bits[0])? {
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

    pub(super) fn flag_styles(&self) -> D<J> {
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

    pub(super) fn flag_roots(&self) -> Vec<J> {
        let mut roots = vec![joins(&self.path, &["gfx", "flags"])];
        let parts: Vec<&str> = self.path.split(SEP).collect();
        if parts.len() >= 2 && lower(parts[parts.len() - 2]) == "mod" {
            let up = parts[..parts.len() - 2].join(&SEP.to_string());
            roots.push(joins(&up, &["gfx", "flags"]));
        }
        roots.into_iter().filter(|r| is_dir(r)).map(J::Str).collect()
    }

    pub(super) fn formations(&self) -> D<J> {
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

    pub(super) fn top_level_keys(&self, folder: &str, keys: &mut HashSet<String>) -> D<()> {
        for (_n, target) in self.resolved_files(folder)? {
            let text = self.plain(&target)?;
            for m in self.re.line_block.find_all(&text) {
                keys.insert(l1(m.group(&text, 1)));
            }
        }
        Ok(())
    }

    pub(super) fn display_names(&self) -> D<OMap<String, String>> {
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
    pub(super) fn invention_index(&self) -> D<OMap<Vec<u8>, (Set, Vec<(Vec<u8>, Vec<u8>)>)>> {
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

    pub(super) fn technology_tree(&self) -> D<J> {
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
    pub(super) fn invention_sequence(&self) -> D<Vec<J>> {
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
pub(super) fn set_pair(out: &mut Vec<(String, J)>, key: String, value: J) {
    match out.iter_mut().find(|(k, _)| *k == key) {
        Some(slot) => slot.1 = value,
        None => out.push((key, value)),
    }
}

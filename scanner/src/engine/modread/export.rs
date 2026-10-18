// The mod as JSON, written (export) and read back (Mod::from_json):
// the engine's copy of a mod, kept between runs, is this text.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;
use crate::engine::rules::{Changes, Invention, Mod, NavalEffect, Rule, Ship, Triggered, SHIP_KEYS};
use crate::util::fx::{FxMap, FxSet};

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
            Some((top, k)) => tree_json(top[*k].1.get(b"trigger").unwrap()),
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
    // The map and the flags matter only to the page, where Python turned no
    // error into a sentence: past the rules, even a refusal in words is
    // something the run stops over.
    let later = |d: Decline| Decline::Unreadable(format!("the map or the flags: {}", d.text()));
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

pub(super) fn strings(v: &J) -> Vec<String> {
    v.list().iter().map(|x| x.str().to_string()).collect()
}

pub(super) fn floats(v: &J) -> FxMap<String, f64> {
    v.pairs().iter().map(|(k, x)| (k.clone(), x.float())).collect()
}

pub(super) fn texts(v: &J) -> FxMap<String, String> {
    v.pairs().iter().map(|(k, x)| (k.clone(), x.str().to_string())).collect()
}

pub(super) fn changes(v: &J) -> Changes {
    v.pairs().iter().map(|(who, deltas)| {
        (who.clone(), deltas.pairs().iter().map(|(k, x)| (k.clone(), x.float())).collect())
    }).collect()
}

impl Mod {
    pub fn from_json(j: &J) -> D<Mod> {
        let bad = |what: &str| Decline::Unreadable(format!("the mod export has no {}", what));
        if !matches!(j, J::Obj(_)) {
            return Err(bad("object"));
        }
        let invention_sequence = j.at("invention_sequence").list().iter().map(|e| {
            let e = e.list();
            Invention { name: e[0].str().to_string(), size: e[1].float(),
                        techs: strings(&e[2]), tags: strings(&e[3]) }
        }).collect();
        let mut formations: FxMap<String, FxSet<String>> = FxMap::default();
        for (tag, v) in j.at("formations").pairs() {
            formations.insert(tag.clone(), strings(v).into_iter().collect());
        }
        let pid_pairs = |key: &str| -> OMap<i64, String> {
            j.at(key).list().iter().map(|p| {
                let p = p.list();
                (p[0].int(), p[1].str().to_string())
            }).collect()
        };
        let naval_units = j.at("naval_units").pairs().iter().map(|(name, st)| {
            let mut stats = [0.0; 5];
            for (i, k) in SHIP_KEYS.iter().enumerate() {
                stats[i] = st.at(k).float();
            }
            Ship { name: name.clone(), stats, heavy: st.at("heavy").int() }
        }).collect();
        let naval_effects = j.at("naval_effects").pairs().iter().map(|(name, e)| {
            (name.clone(), NavalEffect { effects: changes(e.at("effects")),
                                         techs: strings(e.at("techs")),
                                         tags: strings(e.at("tags")) })
        }).collect();
        let naval_tech_effects = j.at("naval_tech_effects").pairs().iter()
            .map(|(name, e)| (name.clone(), changes(e))).collect();
        let reform_mob = j.at("reform_mob").list().iter().map(|r| {
            let r = r.list();
            ((r[0].str().to_string(), r[1].str().to_string()), r[2].float())
        }).collect();
        let triggered_mob = j.at("triggered_mob").list().iter().map(|t| {
            let t = t.list();
            Triggered { name: t[0].str().to_string(), size: t[1].float(), impact: t[2].float(),
                        trigger: t[3].clone() }
        }).collect();
        let invention_rules = j.at("invention_rules").pairs().iter().map(|(name, r)| {
            (name.clone(), Rule {
                size: r.at("size").float(),
                techs: strings(r.at("techs")),
                tags: strings(r.at("tags")),
                requires: strings(r.at("requires")),
                base: if r.at("base").is_null() { None } else { Some(r.at("base").float()) },
                blockers: r.at("blockers").list().iter()
                    .map(|b| (b.list()[0].float(), b.list()[1].str().to_string())).collect(),
            })
        }).collect();
        let flag_styles = j.at("flag_styles").pairs().iter().map(|(g, v)| {
            (g.clone(), (v.list()[0].str().to_string(), v.list()[1].truthy()))
        }).collect();
        let m = Mod {
            path: j.at("path").str().to_string(),
            invention_sequence,
            party_policies: strings(j.at("party_policies")),
            localisation: texts(j.at("localisation")),
            base_prices: j.at("base_prices").clone(),
            country_order: strings(j.at("country_order")),
            formations,
            culture_names: j.at("culture_names").clone(),
            display_names: j.at("display_names").clone(),
            province_names: pid_pairs("province_names"),
            province_regions: pid_pairs("province_regions"),
            state_names: j.at("state_names").pairs().iter()
                .map(|(k, v)| (k.clone(), v.str().to_string())).collect(),
            state_names_j: j.at("state_names").clone(),
            unit_kinds: texts(j.at("unit_kinds")),
            naval_units,
            naval_effects,
            naval_tech_effects,
            technology: j.at("technology").clone(),
            mob_impacts: floats(j.at("mob_impacts")),
            modifier_impacts: floats(j.at("modifier_impacts")),
            reform_mob,
            reform_names: strings(j.at("reform_names")).into_iter().collect(),
            static_mob: floats(j.at("static_mob")),
            triggered_mob,
            culture_groups: texts(j.at("culture_groups")),
            continents: pid_pairs("continents").into_iter_pairs().collect(),
            defines: floats(j.at("defines")),
            strata: texts(j.at("strata")),
            invention_rules,
            event_mob: floats(j.at("event_mob")),
            tech_mob: floats(j.at("tech_mob")),
            nv_mob: floats(j.at("nv_mob")),
            tech_count: j.at("tech_count").int(),
            technologies: strings(j.at("technologies")).into_iter().collect(),
            colours: texts(j.at("colours")),
            sea: j.at("sea").list().iter().map(|x| x.int()).collect(),
            positions: j.at("positions").list().iter().map(|p| {
                let p = p.list();
                (p[0].int(), p[1].float(), p[2].float())
            }).collect(),
            flag_styles,
            flag_roots: strings(j.at("flag_roots")),
            map_bmp: j.at("map_bmp").str().to_string(),
            map_csv: j.at("map_csv").str().to_string(),
        };
        Ok(m)
    }
}

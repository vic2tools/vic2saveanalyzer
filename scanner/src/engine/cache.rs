// A read save, kept between runs: what pass one made of it, in a compact
// form of the engine's own.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The everyday run is one new autosave beside a campaign already read, and
// the Python kept every save it had read for exactly that run. So does this.
// An entry is keyed by everything that decides what is in it -- the file as
// it stands (path, size, time), how it was read, the settings the reading
// and the preparing take, and the program itself -- so a changed anything is
// a miss, never a stale answer. It sits in the analyzer's own cache folder,
// named like the Python's entries so the window's "empty the cache" takes
// it too, and is written whole to a temporary name and then renamed into
// place, so a run that is stopped leaves no half an entry behind.
//
// The format is this file's: numbers as varints, every string once in a
// table and after that by number, which is most of what makes an entry
// small -- a campaign's names are a few hundred tags, cultures and goods
// repeated a hundred thousand times.

use crate::engine::finish::{Pre, PreNation};
use crate::engine::model::{Battle, FirstGoal, Goal, Market, Meta, Nation, Side, War};
use crate::engine::rules::Held;
use crate::omap::OMap;
use crate::pickle::{FxMap, FxSet};
use crate::pyfmt::Num;
use std::io::Write;

const MAGIC: &[u8; 8] = b"V2ENGC01";

pub struct W {
    out: Vec<u8>,
    strings: FxMap<String, u32>,
}

pub struct R<'a> {
    b: &'a [u8],
    i: usize,
    strings: Vec<String>,
}

type X<T> = Result<T, ()>;

impl W {
    fn new() -> W {
        W { out: Vec::with_capacity(1 << 20), strings: FxMap::default() }
    }

    fn u(&mut self, mut v: u64) {
        while v >= 0x80 {
            self.out.push((v as u8) | 0x80);
            v >>= 7;
        }
        self.out.push(v as u8);
    }

    fn i(&mut self, v: i64) {
        self.u(((v << 1) ^ (v >> 63)) as u64);
    }

    fn f(&mut self, v: f64) {
        self.out.extend_from_slice(&v.to_bits().to_le_bytes());
    }

    fn b(&mut self, v: bool) {
        self.out.push(v as u8);
    }

    fn s(&mut self, v: &str) {
        match self.strings.get(v) {
            Some(&n) => self.u(n as u64 + 1),
            None => {
                let n = self.strings.len() as u32;
                self.strings.insert(v.to_string(), n);
                self.u(0);
                self.u(v.len() as u64);
                self.out.extend_from_slice(v.as_bytes());
            }
        }
    }
}

impl<'a> R<'a> {
    fn u(&mut self) -> X<u64> {
        let mut v = 0u64;
        let mut shift = 0;
        loop {
            let byte = *self.b.get(self.i).ok_or(())?;
            self.i += 1;
            v |= ((byte & 0x7f) as u64) << shift;
            if byte & 0x80 == 0 {
                return Ok(v);
            }
            shift += 7;
            if shift > 63 {
                return Err(());
            }
        }
    }

    fn i(&mut self) -> X<i64> {
        let v = self.u()?;
        Ok(((v >> 1) as i64) ^ -((v & 1) as i64))
    }

    fn f(&mut self) -> X<f64> {
        let raw = self.b.get(self.i..self.i + 8).ok_or(())?;
        self.i += 8;
        Ok(f64::from_bits(u64::from_le_bytes(raw.try_into().unwrap())))
    }

    fn b(&mut self) -> X<bool> {
        let v = *self.b.get(self.i).ok_or(())?;
        self.i += 1;
        Ok(v != 0)
    }

    fn s(&mut self) -> X<String> {
        let n = self.u()?;
        if n > 0 {
            return self.strings.get(n as usize - 1).cloned().ok_or(());
        }
        let len = self.u()? as usize;
        let raw = self.b.get(self.i..self.i + len).ok_or(())?;
        self.i += len;
        let s = String::from_utf8(raw.to_vec()).map_err(|_| ())?;
        self.strings.push(s.clone());
        Ok(s)
    }

    fn len(&mut self) -> X<usize> {
        let n = self.u()? as usize;
        // A length no entry could hold is a damaged entry, not an allocation.
        if n > self.b.len() - self.i.min(self.b.len()) + 16 {
            return Err(());
        }
        Ok(n)
    }
}

// ------------------------------------------------------------- one type each

trait Keep: Sized {
    fn put(&self, w: &mut W);
    fn get(r: &mut R) -> X<Self>;
}

impl Keep for i64 {
    fn put(&self, w: &mut W) { w.i(*self) }
    fn get(r: &mut R) -> X<Self> { r.i() }
}

impl Keep for f64 {
    fn put(&self, w: &mut W) { w.f(*self) }
    fn get(r: &mut R) -> X<Self> { r.f() }
}

impl Keep for bool {
    fn put(&self, w: &mut W) { w.b(*self) }
    fn get(r: &mut R) -> X<Self> { r.b() }
}

impl Keep for String {
    fn put(&self, w: &mut W) { w.s(self) }
    fn get(r: &mut R) -> X<Self> { r.s() }
}

impl Keep for Num {
    fn put(&self, w: &mut W) {
        match self {
            Num::I(v) => { w.b(false); w.i(*v) }
            Num::F(v) => { w.b(true); w.f(*v) }
        }
    }
    fn get(r: &mut R) -> X<Self> {
        Ok(if r.b()? { Num::F(r.f()?) } else { Num::I(r.i()?) })
    }
}

impl<T: Keep> Keep for Vec<T> {
    fn put(&self, w: &mut W) {
        w.u(self.len() as u64);
        for x in self {
            x.put(w);
        }
    }
    fn get(r: &mut R) -> X<Self> {
        let n = r.len()?;
        let mut v = Vec::with_capacity(n);
        for _ in 0..n {
            v.push(T::get(r)?);
        }
        Ok(v)
    }
}

impl<T: Keep> Keep for Option<T> {
    fn put(&self, w: &mut W) {
        match self {
            None => w.b(false),
            Some(x) => { w.b(true); x.put(w) }
        }
    }
    fn get(r: &mut R) -> X<Self> {
        Ok(if r.b()? { Some(T::get(r)?) } else { None })
    }
}

impl<A: Keep, B: Keep> Keep for (A, B) {
    fn put(&self, w: &mut W) { self.0.put(w); self.1.put(w) }
    fn get(r: &mut R) -> X<Self> { Ok((A::get(r)?, B::get(r)?)) }
}

impl<A: Keep, B: Keep, C: Keep> Keep for (A, B, C) {
    fn put(&self, w: &mut W) { self.0.put(w); self.1.put(w); self.2.put(w) }
    fn get(r: &mut R) -> X<Self> { Ok((A::get(r)?, B::get(r)?, C::get(r)?)) }
}

impl<A: Keep, B: Keep, C: Keep, D: Keep> Keep for (A, B, C, D) {
    fn put(&self, w: &mut W) { self.0.put(w); self.1.put(w); self.2.put(w); self.3.put(w) }
    fn get(r: &mut R) -> X<Self> { Ok((A::get(r)?, B::get(r)?, C::get(r)?, D::get(r)?)) }
}

impl<K: Keep + Eq + std::hash::Hash + Clone, V: Keep> Keep for OMap<K, V> {
    fn put(&self, w: &mut W) {
        w.u(self.len() as u64);
        for (k, v) in self.iter() {
            k.put(w);
            v.put(w);
        }
    }
    fn get(r: &mut R) -> X<Self> {
        let n = r.len()?;
        let mut m = OMap::new();
        for _ in 0..n {
            let k = K::get(r)?;
            m.set(k, V::get(r)?);
        }
        Ok(m)
    }
}

impl<K: Keep + Eq + std::hash::Hash, V: Keep> Keep for FxMap<K, V> {
    fn put(&self, w: &mut W) {
        w.u(self.len() as u64);
        for (k, v) in self.iter() {
            k.put(w);
            v.put(w);
        }
    }
    fn get(r: &mut R) -> X<Self> {
        let n = r.len()?;
        let mut m = FxMap::default();
        for _ in 0..n {
            let k = K::get(r)?;
            m.insert(k, V::get(r)?);
        }
        Ok(m)
    }
}

impl<K: Keep + Eq + std::hash::Hash> Keep for FxSet<K> {
    fn put(&self, w: &mut W) {
        w.u(self.len() as u64);
        for k in self.iter() {
            k.put(w);
        }
    }
    fn get(r: &mut R) -> X<Self> {
        let n = r.len()?;
        let mut m = FxSet::default();
        for _ in 0..n {
            m.insert(K::get(r)?);
        }
        Ok(m)
    }
}

/// `Keep` for a struct, field by field in the order written.
macro_rules! keep_struct {
    ($t:ident { $($f:ident),* $(,)? }) => {
        impl Keep for $t {
            fn put(&self, w: &mut W) { $( self.$f.put(w); )* }
            fn get(r: &mut R) -> X<Self> {
                Ok($t { $( $f: Keep::get(r)?, )* })
            }
        }
    };
}

keep_struct!(Side { country, leader, losses, units });
keep_struct!(Battle { name, location, date, attacker_won, attacker, defender });
keep_struct!(Goal { casus_belli, actor, receiver, province, added, fulfilled });
keep_struct!(FirstGoal { casus_belli, actor, receiver, province });
keep_struct!(War { name, active, start, end, original_attacker, original_defender, attackers,
                   defenders, fighting, joins, leaves, goals, goal, battles });
keep_struct!(Held { tag, record_tag, tech_list, invention_ids });

impl Keep for Market {
    fn put(&self, w: &mut W) {
        self.current.put(w);
        self.history.put(w);
        for s in &self.snapshot {
            s.put(w);
        }
    }
    fn get(r: &mut R) -> X<Self> {
        let current = Keep::get(r)?;
        let history = Keep::get(r)?;
        let mut snapshot: [OMap<String, f64>; 7] = Default::default();
        for s in snapshot.iter_mut() {
            *s = Keep::get(r)?;
        }
        Ok(Market { current, history, snapshot })
    }
}

keep_struct!(Meta { file, date, player, world_pop, province_owner, great_nations, wars, market });

/// What `prepare` leaves of a nation: everything but the per-province
/// tables it spent, which are empty by then and stay empty here.
impl Keep for Nation {
    fn put(&self, w: &mut W) {
        let n = self;
        n.key.put(w); n.tag.put(w); n.primary_culture.put(w); n.accepted_cultures.put(w);
        n.civilized.put(w); n.government.put(w); n.capital.put(w); n.nationalvalue.put(w);
        n.prestige.put(w); n.infamy.put(w); n.treasury.put(w); n.tax_base.put(w);
        n.war_exhaustion.put(w); n.plurality.put(w); n.research_points.put(w);
        n.revanchism.put(w); n.ruling_party.put(w); n.techs.put(w); n.brigades.put(w);
        n.armies.put(w); n.ships.put(w); n.navies.put(w); n.ships_by_type.put(w);
        n.ship_crew.put(w); n.regiments_by_type.put(w); n.units_at.put(w); n.men_at.put(w);
        n.mobilized_brigades.put(w); n.regular_brigades.put(w); n.mobilizing.put(w);
        n.is_mobilized.put(w); n.tech_list.put(w); n.invention_ids.put(w); n.modifiers.put(w);
        n.country_flags.put(w); n.reforms.put(w); n.human.put(w); n.army_techs.put(w);
        n.navy_techs.put(w); n.factory_count.put(w); n.factory_levels.put(w); n.states.put(w);
        n.provinces.put(w); n.naval_base_levels.put(w); n.max_naval_base.put(w);
        n.ports.put(w); n.fort_levels.put(w); n.railroad_levels.put(w); n.total_pop.put(w);
        n.pop_by_type.put(w); n.pop_by_culture.put(w); n.life_unmet.put(w); n.starving.put(w);
        n.soldiers_noncolonial.put(w); n.pop_noncolonial.put(w);
        n.literacy_noncolonial.put(w); n.goods_supply.put(w); n.mob_excluded_culture.put(w);
        n.literacy_weighted.put(w); n.con_weighted.put(w); n.mil_weighted.put(w);
        n.money_total.put(w);
    }
    fn get(r: &mut R) -> X<Self> {
        let mut n = Nation::default();
        n.key = Keep::get(r)?; n.tag = Keep::get(r)?; n.primary_culture = Keep::get(r)?;
        n.accepted_cultures = Keep::get(r)?; n.civilized = Keep::get(r)?;
        n.government = Keep::get(r)?; n.capital = Keep::get(r)?; n.nationalvalue = Keep::get(r)?;
        n.prestige = Keep::get(r)?; n.infamy = Keep::get(r)?; n.treasury = Keep::get(r)?;
        n.tax_base = Keep::get(r)?; n.war_exhaustion = Keep::get(r)?;
        n.plurality = Keep::get(r)?; n.research_points = Keep::get(r)?;
        n.revanchism = Keep::get(r)?; n.ruling_party = Keep::get(r)?; n.techs = Keep::get(r)?;
        n.brigades = Keep::get(r)?; n.armies = Keep::get(r)?; n.ships = Keep::get(r)?;
        n.navies = Keep::get(r)?; n.ships_by_type = Keep::get(r)?; n.ship_crew = Keep::get(r)?;
        n.regiments_by_type = Keep::get(r)?; n.units_at = Keep::get(r)?;
        n.men_at = Keep::get(r)?; n.mobilized_brigades = Keep::get(r)?;
        n.regular_brigades = Keep::get(r)?; n.mobilizing = Keep::get(r)?;
        n.is_mobilized = Keep::get(r)?; n.tech_list = Keep::get(r)?;
        n.invention_ids = Keep::get(r)?; n.modifiers = Keep::get(r)?;
        n.country_flags = Keep::get(r)?; n.reforms = Keep::get(r)?; n.human = Keep::get(r)?;
        n.army_techs = Keep::get(r)?; n.navy_techs = Keep::get(r)?;
        n.factory_count = Keep::get(r)?; n.factory_levels = Keep::get(r)?;
        n.states = Keep::get(r)?; n.provinces = Keep::get(r)?;
        n.naval_base_levels = Keep::get(r)?; n.max_naval_base = Keep::get(r)?;
        n.ports = Keep::get(r)?; n.fort_levels = Keep::get(r)?;
        n.railroad_levels = Keep::get(r)?; n.total_pop = Keep::get(r)?;
        n.pop_by_type = Keep::get(r)?; n.pop_by_culture = Keep::get(r)?;
        n.life_unmet = Keep::get(r)?; n.starving = Keep::get(r)?;
        n.soldiers_noncolonial = Keep::get(r)?; n.pop_noncolonial = Keep::get(r)?;
        n.literacy_noncolonial = Keep::get(r)?; n.goods_supply = Keep::get(r)?;
        n.mob_excluded_culture = Keep::get(r)?; n.literacy_weighted = Keep::get(r)?;
        n.con_weighted = Keep::get(r)?; n.mil_weighted = Keep::get(r)?;
        n.money_total = Keep::get(r)?;
        Ok(n)
    }
}

keep_struct!(PreNation { tag, nat, kept, is_player, buckets, pool, entries, cap_rule });
keep_struct!(Pre { meta, nations, chunk, held });

// ------------------------------------------------------------- the entries

/// Where the entries live, what version of the program made them, and
/// whether this run may use them.
#[derive(Clone)]
pub struct Store {
    pub dir: String,
    pub version: String,
    pub on: bool,
}

/// A 128-bit name for a key: two independent 64-bit hashes, in hex.
fn name_of(key: &str) -> String {
    format!("engine_{}.pkl", hash_of(key))
}

fn hash_of(key: &str) -> String {
    let mut a: u64 = 0xcbf2_9ce4_8422_2325;
    let mut b: u64 = 0x8422_2325_cbf2_9ce4;
    for &c in key.as_bytes() {
        a = (a ^ c as u64).wrapping_mul(0x0000_0100_0000_01b3);
        b = (b.rotate_left(5) ^ c as u64).wrapping_mul(0x51_7c_c1_b7_27_22_0a_95);
    }
    format!("{:016x}{:016x}", a, b)
}

impl Store {
    /// The entry's path for one save read under `context` (the reading and
    /// the settings that shape what pass one makes), or None when the file
    /// cannot be looked at or caching is off.
    pub fn slot(&self, path: &str, context: &str) -> Option<(String, String)> {
        if !self.on || self.dir.is_empty() || self.version.is_empty() {
            return None;
        }
        let meta = std::fs::metadata(path).ok()?;
        let mtime = meta.modified().ok()?.duration_since(std::time::UNIX_EPOCH).ok()?.as_nanos();
        let full = std::path::absolute(path).ok()?;
        let key = format!("{}|{}|{}|{}|{}", full.to_string_lossy(), meta.len(), mtime,
                          self.version, context);
        let file = std::path::Path::new(&self.dir).join(name_of(&key));
        Some((file.to_string_lossy().to_string(), key))
    }

    /// The entry, or None: missing, from another key, or damaged.
    pub fn load(&self, slot: &(String, String)) -> Option<Pre> {
        let raw = std::fs::read(&slot.0).ok()?;
        let body = raw.strip_prefix(MAGIC)?;
        let mut r = R { b: body, i: 0, strings: Vec::new() };
        let key = r.s().ok()?;
        if key != slot.1 {
            return None;
        }
        let pre = Pre::get(&mut r).ok()?;
        if r.i != body.len() {
            return None;
        }
        Some(pre)
    }

    /// Keep an entry. A failure costs the next run the read, nothing more.
    pub fn store(&self, slot: &(String, String), pre: &Pre) {
        let mut w = W::new();
        w.out.extend_from_slice(MAGIC);
        w.s(&slot.1);
        pre.put(&mut w);
        let _ = std::fs::create_dir_all(&self.dir);
        let temporary = format!("{}.{}.tmp", slot.0, std::process::id());
        let written = std::fs::File::create(&temporary)
            .and_then(|mut f| f.write_all(&w.out).and_then(|_| f.flush()));
        if written.is_err() || std::fs::rename(&temporary, &slot.0).is_err() {
            let _ = std::fs::remove_file(&temporary);
        }
    }
}

// ------------------------------------------------------------- the mod

const MOD_MAGIC: &[u8] = b"V2ENGM01";

/// Where the mod read from `path` is kept, when Python has signed its files
/// (`mod_reader.mod_signature`, which it takes for the stamp anyway): keyed
/// by the folder, every file's size and time, and this program's version.
/// Kept whatever `--no-cache` says, as Python keeps its own read of a mod.
pub fn mod_slot(store: &Store, path: &str, signature: Option<&str>) -> Option<(String, String)> {
    let signature = signature?;
    if store.dir.is_empty() || store.version.is_empty() {
        return None;
    }
    let key = format!("mod|{}|{}|{}", path, signature, store.version);
    let file = std::path::Path::new(&store.dir).join(format!("enginemod_{}.pkl", hash_of(&key)));
    Some((file.to_string_lossy().to_string(), key))
}

/// The mod as it was read, or None: missing, from another key, or damaged.
pub fn mod_load(slot: &(String, String)) -> Option<crate::jsonr::J> {
    let raw = std::fs::read(&slot.0).ok()?;
    let body = raw.strip_prefix(MOD_MAGIC)?;
    let n = u32::from_le_bytes(body.get(..4)?.try_into().ok()?) as usize;
    let key = body.get(4..4 + n)?;
    if key != slot.1.as_bytes() {
        return None;
    }
    let text = std::str::from_utf8(&body[4 + n..]).ok()?;
    crate::jsonr::parse(text).ok()
}

/// Keep the mod as it was read. A failure costs the next run the read.
pub fn mod_store(slot: &(String, String), mod_json: &crate::jsonr::J) {
    let mut text = String::new();
    mod_json.write(&mut text);
    let mut out = MOD_MAGIC.to_vec();
    out.extend_from_slice(&(slot.1.len() as u32).to_le_bytes());
    out.extend_from_slice(slot.1.as_bytes());
    out.extend_from_slice(text.as_bytes());
    if let Some(dir) = std::path::Path::new(&slot.0).parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let temporary = format!("{}.{}.tmp", slot.0, std::process::id());
    let written = std::fs::File::create(&temporary)
        .and_then(|mut f| f.write_all(&out).and_then(|_| f.flush()));
    if written.is_err() || std::fs::rename(&temporary, &slot.0).is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
}

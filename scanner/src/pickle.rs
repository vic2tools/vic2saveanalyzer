// Python values, written as a pickle Python reads back in one call.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// A save read in `--record` mode goes back to the analyzer as the very
// `(meta, nations)` pair its Python reader would have built, pickled. JSON
// could not say it: a set is not a list, an int is not a float that happens
// to be whole, a `defaultdict(int)` is not a dict -- and each of those shows
// somewhere downstream, a `0` against a `0.0` in a CSV. Unpickling is also
// one C call where JSON plus the Python that turned it into records was most
// of what a save cost the analyzer. The pickle is the cache entry too: the
// worker writes these bytes to disk as they are.
//
// Only the opcodes of protocol 5 that these values need, and no framing,
// which the unpickler does not require. Strings are memoised, so a name the
// save repeats forty thousand times is one string object on the other side,
// as Python's reader interned it to be.
//
// Built for a save a worker reads every hundred milliseconds or so: strings
// are shared (`Arc`, since the wars are read on a thread of their own)
// rather than copied, and every hash here is `Fx`, a
// multiply-and-rotate that is several times cheaper than the standard
// library's for the short names and small numbers these maps hold. Nothing
// hashed here comes from anyone but the save's own writer.

use std::collections::{HashMap, HashSet};
use std::hash::{BuildHasherDefault, Hasher};
use std::sync::Arc;

/// The hash rustc itself uses for its own tables: fast, and fine where no
/// one is choosing the keys to collide.
#[derive(Default, Clone, Copy)]
pub struct Fx(u64);

impl Hasher for Fx {
    fn write(&mut self, bytes: &[u8]) {
        let mut chunks = bytes.chunks_exact(8);
        for c in &mut chunks {
            self.add(u64::from_le_bytes(c.try_into().unwrap()));
        }
        let rest = chunks.remainder();
        if !rest.is_empty() {
            let mut last = [0u8; 8];
            last[..rest.len()].copy_from_slice(rest);
            self.add(u64::from_le_bytes(last) ^ (rest.len() as u64) << 56);
        }
    }
    fn write_u8(&mut self, i: u8) { self.add(i as u64) }
    fn write_u32(&mut self, i: u32) { self.add(i as u64) }
    fn write_u64(&mut self, i: u64) { self.add(i) }
    fn write_i64(&mut self, i: i64) { self.add(i as u64) }
    fn write_usize(&mut self, i: usize) { self.add(i as u64) }
    fn finish(&self) -> u64 { self.0 }
}

impl Fx {
    #[inline]
    fn add(&mut self, w: u64) {
        self.0 = (self.0.rotate_left(5) ^ w).wrapping_mul(0x51_7c_c1_b7_27_22_0a_95);
    }
}

pub type FxMap<K, V> = HashMap<K, V, BuildHasherDefault<Fx>>;
pub type FxSet<K> = HashSet<K, BuildHasherDefault<Fx>>;

/// A string of the save: latin-1 bytes, one per character, shared.
pub type Str = Arc<[u8]>;

pub fn text(b: &[u8]) -> Str {
    Arc::from(b)
}

/// A dictionary key: every key the analyzer's records use is one of these.
#[derive(Clone, PartialEq, Eq, Hash, Debug)]
pub enum Key {
    I(i64),
    S(Str),
}

/// An insertion-ordered dict. Setting a key that is already there keeps its
/// place and replaces its value, as a Python dict does.
///
/// Most of the dicts in a record are small -- a state's handful of pop
/// types, the units in one province -- and a save has thousands of them, so
/// a dict is searched in order until it grows past `INDEXED` keys and only
/// then given a hash index.
#[derive(Default, Debug, Clone)]
pub struct OMap {
    pub keys: Vec<Key>,
    pub vals: Vec<P>,
    index: Option<FxMap<Key, usize>>,
}

const INDEXED: usize = 16;

impl OMap {
    pub fn new() -> OMap {
        OMap::default()
    }

    fn find(&self, key: &Key) -> Option<usize> {
        match &self.index {
            Some(index) => index.get(key).copied(),
            None => self.keys.iter().position(|k| k == key),
        }
    }

    fn push(&mut self, key: Key, val: P) -> usize {
        let at = self.keys.len();
        if let Some(index) = &mut self.index {
            index.insert(key.clone(), at);
        } else if at + 1 > INDEXED {
            let mut index: FxMap<Key, usize> = FxMap::default();
            index.reserve(at * 2);
            for (i, k) in self.keys.iter().enumerate() {
                index.insert(k.clone(), i);
            }
            index.insert(key.clone(), at);
            self.index = Some(index);
        }
        self.keys.push(key);
        self.vals.push(val);
        at
    }

    pub fn set(&mut self, key: Key, val: P) {
        match self.find(&key) {
            Some(i) => self.vals[i] = val,
            None => {
                self.push(key, val);
            }
        }
    }

    pub fn get(&self, key: &Key) -> Option<&P> {
        self.find(key).map(|i| &self.vals[i])
    }

    /// The value under `key`, made with `blank` first if it is not there --
    /// a `defaultdict` lookup.
    pub fn entry(&mut self, key: Key, blank: impl FnOnce() -> P) -> &mut P {
        let i = match self.find(&key) {
            Some(i) => i,
            None => self.push(key, blank()),
        };
        &mut self.vals[i]
    }

    pub fn len(&self) -> usize {
        self.keys.len()
    }
}

/// An insertion-ordered set, written out in the order its members arrived.
#[derive(Default, Debug, Clone)]
pub struct OSet {
    pub items: Vec<Key>,
    index: FxSet<Key>,
}

impl OSet {
    pub fn add(&mut self, k: Key) {
        if self.index.insert(k.clone()) {
            self.items.push(k);
        }
    }
}

/// A dict whose keys are known in advance, in their order: a nation's
/// record. Looked up by position rather than hashed, which for seventy
/// fields touched sixty times a nation is most of what folding one cost.
/// A key outside the layout goes after it, as a Python dict would put it.
#[derive(Debug, Clone)]
pub struct Fixed {
    pub names: &'static [&'static str],
    pub vals: Vec<P>,
    pub extra: OMap,
}

/// What a `defaultdict` makes for a key it has not seen.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Factory {
    Int,
    Float,
    List,
    Counter,
}

#[derive(Debug, Clone)]
pub enum P {
    None,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(Str),
    List(Vec<P>),
    Tuple(Vec<P>),
    Dict(OMap),
    Set(OSet),
    DefaultDict(Factory, OMap),
    Counter(OMap),
    Fixed(Box<Fixed>),
}

/// Python's `a + b` for the numbers a record adds up, or None where Python
/// would have raised or overflowed past what an i64 holds.
pub fn add(a: &P, b: &P) -> Option<P> {
    match (a, b) {
        (P::Int(x), P::Int(y)) => x.checked_add(*y).map(P::Int),
        (P::Int(x), P::Float(y)) => Some(P::Float(*x as f64 + *y)),
        (P::Float(x), P::Int(y)) => Some(P::Float(*x + *y as f64)),
        (P::Float(x), P::Float(y)) => Some(P::Float(*x + *y)),
        _ => None,
    }
}

/// Python's `a > b` for two numbers.
pub fn greater(a: &P, b: &P) -> Option<bool> {
    match (a, b) {
        (P::Int(x), P::Int(y)) => Some(x > y),
        (P::Int(x), P::Float(y)) => Some((*x as f64) > *y),
        (P::Float(x), P::Int(y)) => Some(*x > *y as f64),
        (P::Float(x), P::Float(y)) => Some(x > y),
        _ => None,
    }
}

/// Whether Python would call this number true.
pub fn truthy(a: &P) -> bool {
    match a {
        P::Int(x) => *x != 0,
        P::Float(x) => *x != 0.0,
        P::Bool(b) => *b,
        P::None => false,
        P::Str(s) => !s.is_empty(),
        P::List(v) | P::Tuple(v) => !v.is_empty(),
        P::Dict(m) | P::DefaultDict(_, m) | P::Counter(m) => m.len() > 0,
        P::Set(s) => !s.items.is_empty(),
        P::Fixed(_) => true,
    }
}

pub struct Pickler {
    out: Vec<u8>,
    // By the string's address first, which is the same `Arc` over and over
    // for a name the save repeats, and by its bytes after that.
    by_address: FxMap<usize, u32>,
    memo: FxMap<Str, u32>,
    names: FxMap<&'static str, u32>,
    next: u32,
}

impl Pickler {
    pub fn new() -> Pickler {
        let mut out = Vec::with_capacity(1 << 20);
        out.extend_from_slice(b"\x80\x05");
        Pickler { out, by_address: FxMap::default(), memo: FxMap::default(),
                  names: FxMap::default(), next: 0 }
    }

    pub fn finish(mut self) -> Vec<u8> {
        self.out.push(b'.');
        self.out
    }

    fn get(&mut self, i: u32) {
        if i < 256 {
            self.out.push(b'h');
            self.out.push(i as u8);
        } else {
            self.out.push(b'j');
            self.out.extend_from_slice(&i.to_le_bytes());
        }
    }

    fn memoize(&mut self) -> u32 {
        self.out.push(0x94);
        let i = self.next;
        self.next += 1;
        i
    }

    fn raw_str(&mut self, latin: &[u8]) {
        let wide = latin.iter().filter(|&&b| b >= 0x80).count();
        let size = latin.len() + wide;
        if size < 256 {
            self.out.push(0x8c);
            self.out.push(size as u8);
        } else {
            self.out.push(b'X');
            self.out.extend_from_slice(&(size as u32).to_le_bytes());
        }
        if wide == 0 {
            self.out.extend_from_slice(latin);
        } else {
            for &b in latin {
                if b < 0x80 {
                    self.out.push(b);
                } else {
                    self.out.push(0xC0 | (b >> 6));
                    self.out.push(0x80 | (b & 0x3F));
                }
            }
        }
    }

    /// A name this program spells itself: a module path, or a record's key.
    fn name(&mut self, name: &'static str, global: bool) {
        if let Some(&i) = self.names.get(name) {
            self.get(i);
            return;
        }
        if global {
            self.out.push(b'c');
            self.out.extend_from_slice(name.as_bytes());
            self.out.push(b'\n');
        } else {
            self.raw_str(name.as_bytes());
        }
        let i = self.memoize();
        self.names.insert(name, i);
    }

    pub fn str(&mut self, s: &Str) {
        let address = s.as_ptr() as usize;
        if let Some(&i) = self.by_address.get(&address) {
            self.get(i);
            return;
        }
        if let Some(&i) = self.memo.get(s) {
            self.by_address.insert(address, i);
            self.get(i);
            return;
        }
        self.raw_str(s);
        let i = self.memoize();
        self.memo.insert(s.clone(), i);
        self.by_address.insert(address, i);
    }

    pub fn int(&mut self, v: i64) {
        if (0..256).contains(&v) {
            self.out.push(b'K');
            self.out.push(v as u8);
        } else if (0..65536).contains(&v) {
            self.out.push(b'M');
            self.out.extend_from_slice(&(v as u16).to_le_bytes());
        } else if v >= i32::MIN as i64 && v <= i32::MAX as i64 {
            self.out.push(b'J');
            self.out.extend_from_slice(&(v as i32).to_le_bytes());
        } else {
            // LONG1: two's complement, little-endian, as few bytes as keep
            // the sign.
            let bytes = v.to_le_bytes();
            let mut n = 8;
            while n > 1 {
                let top = bytes[n - 1];
                let below = bytes[n - 2];
                if (top == 0 && below & 0x80 == 0) || (top == 0xff && below & 0x80 != 0) {
                    n -= 1;
                } else {
                    break;
                }
            }
            self.out.push(0x8a);
            self.out.push(n as u8);
            self.out.extend_from_slice(&bytes[..n]);
        }
    }

    fn key(&mut self, k: &Key) {
        match k {
            Key::I(i) => self.int(*i),
            Key::S(s) => self.str(s),
        }
    }

    fn items(&mut self, m: &OMap) {
        if m.len() == 0 {
            return;
        }
        self.out.push(b'(');
        for (k, v) in m.keys.iter().zip(&m.vals) {
            self.key(k);
            self.value(v);
        }
        self.out.push(b'u');
    }

    pub fn value(&mut self, p: &P) {
        match p {
            P::None => self.out.push(b'N'),
            P::Bool(true) => self.out.push(0x88),
            P::Bool(false) => self.out.push(0x89),
            P::Int(i) => self.int(*i),
            P::Float(f) => {
                self.out.push(b'G');
                self.out.extend_from_slice(&f.to_be_bytes());
            }
            P::Str(s) => self.str(s),
            P::List(v) => {
                self.out.push(b']');
                if !v.is_empty() {
                    self.out.push(b'(');
                    for x in v {
                        self.value(x);
                    }
                    self.out.push(b'e');
                }
            }
            P::Tuple(v) => match v.len() {
                0 => self.out.push(b')'),
                1..=3 => {
                    for x in v {
                        self.value(x);
                    }
                    self.out.push([0x85, 0x86, 0x87][v.len() - 1]);
                }
                _ => {
                    self.out.push(b'(');
                    for x in v {
                        self.value(x);
                    }
                    self.out.push(b't');
                }
            },
            P::Dict(m) => {
                self.out.push(b'}');
                self.items(m);
            }
            P::Fixed(f) => {
                self.out.push(b'}');
                self.out.push(b'(');
                for (name, v) in f.names.iter().zip(&f.vals) {
                    self.name(name, false);
                    self.value(v);
                }
                for (k, v) in f.extra.keys.iter().zip(&f.extra.vals) {
                    self.key(k);
                    self.value(v);
                }
                self.out.push(b'u');
            }
            P::Set(s) => {
                self.out.push(0x8f);
                if !s.items.is_empty() {
                    self.out.push(b'(');
                    for k in &s.items {
                        self.key(k);
                    }
                    self.out.push(0x90);
                }
            }
            P::DefaultDict(factory, m) => {
                self.name("collections\ndefaultdict", true);
                self.name(match factory {
                    Factory::Int => "builtins\nint",
                    Factory::Float => "builtins\nfloat",
                    Factory::List => "builtins\nlist",
                    Factory::Counter => "collections\nCounter",
                }, true);
                self.out.push(0x85);
                self.out.push(b'R');
                self.items(m);
            }
            P::Counter(m) => {
                self.name("collections\nCounter", true);
                self.out.push(b')');
                self.out.push(b'R');
                self.items(m);
            }
        }
    }
}

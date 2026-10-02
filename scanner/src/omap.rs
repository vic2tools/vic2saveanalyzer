// An insertion-ordered map: a Python dict's order, for any key.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Every table the report is built from was a dict, and dict order reaches
// the output everywhere: the order nations appear in, the order a stable
// sort breaks ties in, the order keys are written in the JSON. So the
// engine keeps its maps in the order keys arrived, and setting a key that is
// already there keeps its place. Small maps are searched in order; a map
// past `INDEXED` keys gets a hash index.

use crate::fx::FxMap;
use std::borrow::Borrow;
use std::hash::Hash;

const INDEXED: usize = 12;

#[derive(Clone, Debug)]
pub struct OMap<K, V> {
    keys: Vec<K>,
    vals: Vec<V>,
    index: Option<FxMap<K, usize>>,
}

impl<K, V> Default for OMap<K, V> {
    fn default() -> Self {
        OMap { keys: Vec::new(), vals: Vec::new(), index: None }
    }
}

impl<K: Eq + Hash + Clone, V: PartialEq> PartialEq for OMap<K, V> {
    fn eq(&self, other: &Self) -> bool {
        self.keys == other.keys && self.vals == other.vals
    }
}

impl<K: Eq + Hash + Clone, V> OMap<K, V> {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn len(&self) -> usize {
        self.keys.len()
    }

    pub fn is_empty(&self) -> bool {
        self.keys.is_empty()
    }

    fn find<Q>(&self, key: &Q) -> Option<usize>
    where
        K: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        match &self.index {
            Some(index) => index.get(key).copied(),
            None => self.keys.iter().position(|k| k.borrow() == key),
        }
    }

    fn push(&mut self, key: K, val: V) -> usize {
        let at = self.keys.len();
        if let Some(index) = &mut self.index {
            index.insert(key.clone(), at);
        } else if at + 1 > INDEXED {
            let mut index: FxMap<K, usize> = FxMap::default();
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

    pub fn get<Q>(&self, key: &Q) -> Option<&V>
    where
        K: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        self.find(key).map(|i| &self.vals[i])
    }

    pub fn get_mut<Q>(&mut self, key: &Q) -> Option<&mut V>
    where
        K: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        match self.find(key) {
            Some(i) => Some(&mut self.vals[i]),
            None => None,
        }
    }

    pub fn contains_key<Q>(&self, key: &Q) -> bool
    where
        K: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        self.find(key).is_some()
    }

    /// `d[key] = val`: a new key goes last, an old one keeps its place.
    pub fn set(&mut self, key: K, val: V) {
        match self.find(&key) {
            Some(i) => self.vals[i] = val,
            None => {
                self.push(key, val);
            }
        }
    }

    /// `d.setdefault(key, blank())`.
    pub fn entry(&mut self, key: K, blank: impl FnOnce() -> V) -> &mut V {
        let i = match self.find(&key) {
            Some(i) => i,
            None => self.push(key, blank()),
        };
        &mut self.vals[i]
    }

    pub fn iter(&self) -> impl Iterator<Item = (&K, &V)> {
        self.keys.iter().zip(self.vals.iter())
    }

    pub fn keys(&self) -> impl Iterator<Item = &K> {
        self.keys.iter()
    }

    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.vals.iter()
    }

    pub fn into_iter_pairs(self) -> impl Iterator<Item = (K, V)> {
        self.keys.into_iter().zip(self.vals)
    }
}

impl<K: Eq + Hash + Clone, V> FromIterator<(K, V)> for OMap<K, V> {
    fn from_iter<I: IntoIterator<Item = (K, V)>>(iter: I) -> Self {
        let mut m = OMap::new();
        for (k, v) in iter {
            m.set(k, v);
        }
        m
    }
}

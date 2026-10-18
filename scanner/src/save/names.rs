// The names a run meets, once each: a `Sym` is a small number standing for
// one of them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// A campaign says "infantry" or "RUS" in every save, in every nation, a
// hundred thousand times, and a run needs a few thousand different names in
// all. One table per run holds each name's text; everything else holds its
// number. The table is shared by every thread, and each thread keeps a cache
// in front of it, so a name seen before costs a hash and a compare, with no
// lock and no allocation.
//
// Ids are handed out in the order threads first meet names, so they differ
// from one run to the next. Nothing that reaches an output, a cache entry, a
// sort or a hash order may depend on one: `Sym` has no `Ord`, its number is
// private to this file, a cache entry is written by the names' text, and
// order by name is `cmp`. `VIC2_ENGINE_NAMES_SHIFT=k` takes the first `k`
// ids for placeholders, which moves every id and the order of every hash
// map keyed by one; a run with it set must give the same answers.
//
// Names are leaked: the run ends by forgetting its memory anyway, and a
// `--cross` run is a few campaigns, a few thousand names each.

use crate::util::fx::FxMap;
#[cfg(not(windows))]
use std::cell::Cell;
use std::sync::{Mutex, OnceLock};

/// A name. Equal ids are equal names within one run; the number means
/// nothing else and is never written anywhere.
#[derive(Copy, Clone, PartialEq, Eq, Hash, Default)]
pub struct Sym(u32);

impl Sym {
    /// Whether this is the empty name: the one id with a fixed meaning.
    pub fn is_empty(self) -> bool {
        self.0 == 0
    }

    /// The id's number, for indexing a dense table built after pass one
    /// (`rules::Dense`). Never an order: nothing may sort or print by it.
    pub fn index(self) -> usize {
        self.0 as usize
    }
}

/// How many names there are now, the empty one included.
pub fn len() -> usize {
    table().lock().unwrap_or_else(|e| e.into_inner()).texts.len()
}

impl std::fmt::Debug for Sym {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}", text(*self))
    }
}

struct Table {
    texts: Vec<&'static str>,
    ids: FxMap<&'static str, u32>,
}

fn table() -> &'static Mutex<Table> {
    static TABLE: OnceLock<Mutex<Table>> = OnceLock::new();
    TABLE.get_or_init(|| {
        let mut t = Table { texts: vec![""], ids: FxMap::default() };
        t.ids.insert("", 0);
        let shift = std::env::var("VIC2_ENGINE_NAMES_SHIFT").ok()
            .and_then(|v| v.parse::<usize>().ok()).unwrap_or(0);
        for k in 0..shift {
            // A name no save or mod can spell: a control character first.
            let name: &'static str = Box::leak(format!("\u{1}shift {k}").into_boxed_str());
            t.ids.insert(name, t.texts.len() as u32);
            t.texts.push(name);
        }
        Mutex::new(t)
    })
}

/// The id of a name already decoded, adding it if the run has not met it.
fn shared(name: &str) -> Sym {
    let mut t = table().lock().unwrap_or_else(|e| e.into_inner());
    if let Some(&id) = t.ids.get(name) {
        return Sym(id);
    }
    let name: &'static str = Box::leak(name.to_string().into_boxed_str());
    let id = t.texts.len() as u32;
    t.ids.insert(name, id);
    t.texts.push(name);
    Sym(id)
}

#[derive(Default)]
struct Local {
    /// A save's bytes to the name they decode to.
    by_bytes: FxMap<Vec<u8>, Sym>,
    /// Text to name, for the mod, the run's settings and the cache.
    by_text: FxMap<&'static str, Sym>,
    /// The table's texts so far, by id.
    mirror: Vec<&'static str>,
}

// A thread's `Local` is reached through a plain pointer, made on the thread's
// first use and never freed. Not through `thread_local!` on Windows: there
// std's thread-locals go through `guard::enable` on every access, which does
// three locked operations on one counter every thread shares, and with 31
// workers reading a few million names it was most of a warm load (gdb
// samples: 110 of 160 threads inside it). The system's own slot costs a load.
#[cfg(windows)]
fn local_ptr() -> *mut Local {
    use std::ffi::c_void;
    #[link(name = "kernel32")]
    extern "system" {
        fn TlsAlloc() -> u32;
        fn TlsGetValue(index: u32) -> *mut c_void;
        fn TlsSetValue(index: u32, value: *mut c_void) -> i32;
    }
    static SLOT: OnceLock<u32> = OnceLock::new();
    let slot = *SLOT.get_or_init(|| unsafe { TlsAlloc() });
    // SAFETY: plain calls into the system's thread-local slots.
    unsafe {
        let mut at = TlsGetValue(slot) as *mut Local;
        if at.is_null() {
            at = Box::into_raw(Box::new(Local::default()));
            TlsSetValue(slot, at as *mut c_void);
        }
        at
    }
}

#[cfg(not(windows))]
fn local_ptr() -> *mut Local {
    thread_local! {
        static LOCAL: Cell<*mut Local> = const { Cell::new(std::ptr::null_mut()) };
    }
    LOCAL.with(|cell| {
        let mut at = cell.get();
        if at.is_null() {
            at = Box::into_raw(Box::new(Local::default()));
            cell.set(at);
        }
        at
    })
}

fn with_local<R>(f: impl FnOnce(&mut Local) -> R) -> R {
    // SAFETY: the pointer is this thread's alone and is never freed, and
    // nothing run inside `f` comes back here for the same thread.
    f(unsafe { &mut *local_ptr() })
}

/// The name a save's bytes spell, decoded the way `text::latin1` does.
pub fn intern(bytes: &[u8]) -> Sym {
    with_local(|l| {
        if let Some(&s) = l.by_bytes.get(bytes) {
            return s;
        }
        let s = shared(&crate::save::text::latin1(bytes));
        l.by_bytes.insert(bytes.to_vec(), s);
        s
    })
}

/// The name this text spells.
pub fn intern_str(name: &str) -> Sym {
    with_local(|l| {
        if let Some(&s) = l.by_text.get(name) {
            return s;
        }
        let s = shared(name);
        let text = text_in(l, s);
        l.by_text.insert(text, s);
        s
    })
}

fn text_in(l: &mut Local, s: Sym) -> &'static str {
    let at = s.0 as usize;
    if at >= l.mirror.len() {
        let t = table().lock().unwrap_or_else(|e| e.into_inner());
        let have = l.mirror.len();
        l.mirror.extend_from_slice(&t.texts[have..]);
    }
    l.mirror[at]
}

/// What the name says.
pub fn text(s: Sym) -> &'static str {
    with_local(|l| text_in(l, s))
}

/// Order by what the names say, which is the order of the strings they
/// stand for. The only order `Sym`s have.
pub fn cmp(a: Sym, b: Sym) -> std::cmp::Ordering {
    if a == b {
        return std::cmp::Ordering::Equal;
    }
    text(a).cmp(text(b))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_id_for_one_name_however_it_arrives() {
        let a = intern(b"infantry");
        assert_eq!(a, intern_str("infantry"));
        assert_eq!(a, intern(b"infantry"));
        assert_eq!(text(a), "infantry");
        assert_eq!(intern(&[0xE9]), intern_str("\u{e9}"));
        assert_eq!(text(intern(b"")), "");
        assert_eq!(intern(b""), Sym::default());
    }

    /// Run with `VIC2_ENGINE_NAMES_SHIFT=k` set: the first real id is past
    /// the placeholders. Without it there is nothing to see, and it passes.
    #[test]
    fn the_shift_takes_the_first_ids() {
        let k: u32 = std::env::var("VIC2_ENGINE_NAMES_SHIFT").ok()
            .and_then(|v| v.parse().ok()).unwrap_or(0);
        assert!(intern_str("a name the shift test alone uses").0 > k);
        if k > 0 {
            assert!(text(Sym(k)).starts_with('\u{1}'));
        }
    }

    #[test]
    fn another_thread_reads_a_name_this_one_made() {
        let a = intern_str("seen here first");
        let t = std::thread::spawn(move || (text(a), intern(b"seen here first") == a));
        assert_eq!(t.join().unwrap(), ("seen here first", true));
    }

    #[test]
    fn cmp_follows_the_text_not_the_id() {
        let z = intern_str("zzz name");
        let a = intern_str("aaa name");
        assert_eq!(cmp(a, z), std::cmp::Ordering::Less);
        assert_eq!(cmp(z, a), std::cmp::Ordering::Greater);
        assert_eq!(cmp(a, a), std::cmp::Ordering::Equal);
    }
}

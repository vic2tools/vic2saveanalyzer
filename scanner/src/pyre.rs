// Python's `re`, for the patterns the mod reader uses, over latin-1 text.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// `mod_reader.py` reads most of a mod with regular expressions, and what
// they match at the edges -- a quote left open, a name that runs into a
// longer word, whitespace that crosses a line -- is part of what it reads.
// Rewritten by hand, each of those would be a new guess at what the pattern
// does. So the patterns are carried over as written and run by a matcher
// that works the way Python's does: backtracking, leftmost first, greedy
// and lazy repeats tried in the same order, a search trying every start in
// turn. Only the syntax the mod reader uses is understood, and anything else
// panics when the pattern is compiled, which is at the first run of a build.
//
// The text is a mod file decoded as latin-1, one byte to a character, so
// the classes are Python's for those 256 characters: `\w` takes the latin-1
// letters and `\s` takes `\x1c`-`\x1f`, `\x85` and `\xa0`, as `str` patterns
// do.

pub type Set = [bool; 256];

/// Python's `\w` for the latin-1 characters.
pub fn word(c: u8) -> bool {
    matches!(c, b'0'..=b'9' | b'A'..=b'Z' | b'_' | b'a'..=b'z' | 0xaa | 0xb2 | 0xb3 | 0xb5
        | 0xb9 | 0xba | 0xbc..=0xbe | 0xc0..=0xd6 | 0xd8..=0xf6 | 0xf8..=0xff)
}

/// Python's `\s`, which is `str.isspace()`, for the latin-1 characters.
pub fn space(c: u8) -> bool {
    matches!(c, 0x09..=0x0d | 0x1c..=0x20 | 0x85 | 0xa0)
}

#[derive(Debug)]
enum Node {
    Set(Box<Set>),
    Bol,
    Eol,
    EndZ,
    WordB,
    NotWordB,
    Group(Option<usize>, Vec<Vec<Node>>),
    Rep(Box<Node>, usize, usize, bool),
    NotBehind(Box<Set>),
}

pub struct Re {
    alts: Vec<Vec<Node>>,
    groups: usize,
    multiline: bool,
    /// The characters a match can begin with, when that is known.
    first: Option<Box<Set>>,
}

pub struct Match {
    /// (start, end) of the whole match and of each group; usize::MAX for
    /// a group that took no part.
    pub caps: Vec<(usize, usize)>,
}

impl Match {
    pub fn start(&self) -> usize {
        self.caps[0].0
    }
    pub fn end(&self) -> usize {
        self.caps[0].1
    }
    /// A group's text, or None when it took no part.
    pub fn get<'t>(&self, text: &'t [u8], g: usize) -> Option<&'t [u8]> {
        let (a, b) = self.caps[g];
        if a == usize::MAX { None } else { Some(&text[a..b]) }
    }
    /// A group's text, "" when it took no part, as `findall` gives it.
    pub fn group<'t>(&self, text: &'t [u8], g: usize) -> &'t [u8] {
        self.get(text, g).unwrap_or(b"")
    }
}

const NONE: (usize, usize) = (usize::MAX, usize::MAX);

struct Parser<'p> {
    p: &'p [u8],
    i: usize,
    groups: usize,
    dotall: bool,
}

impl<'p> Parser<'p> {
    fn peek(&self) -> Option<u8> {
        self.p.get(self.i).copied()
    }

    fn alts(&mut self) -> Vec<Vec<Node>> {
        let mut out = vec![self.seq()];
        while self.peek() == Some(b'|') {
            self.i += 1;
            out.push(self.seq());
        }
        out
    }

    fn seq(&mut self) -> Vec<Node> {
        let mut out = Vec::new();
        while let Some(c) = self.peek() {
            if c == b'|' || c == b')' {
                break;
            }
            let atom = self.atom();
            out.push(self.quantified(atom));
        }
        out
    }

    fn number(&mut self) -> Option<usize> {
        let s = self.i;
        while self.peek().map_or(false, |c| c.is_ascii_digit()) {
            self.i += 1;
        }
        std::str::from_utf8(&self.p[s..self.i]).unwrap().parse().ok()
    }

    fn quantified(&mut self, atom: Node) -> Node {
        let (min, max) = match self.peek() {
            Some(b'*') => { self.i += 1; (0, usize::MAX) }
            Some(b'+') => { self.i += 1; (1, usize::MAX) }
            Some(b'?') => { self.i += 1; (0, 1) }
            Some(b'{') if self.p.get(self.i + 1).map_or(false, |c| c.is_ascii_digit()) => {
                self.i += 1;
                let lo = self.number().unwrap();
                let hi = if self.peek() == Some(b',') {
                    self.i += 1;
                    self.number().unwrap_or(usize::MAX)
                } else {
                    lo
                };
                assert_eq!(self.peek(), Some(b'}'), "pattern: unclosed repeat");
                self.i += 1;
                (lo, hi)
            }
            _ => return atom,
        };
        let greedy = if self.peek() == Some(b'?') {
            self.i += 1;
            false
        } else {
            true
        };
        Node::Rep(Box::new(atom), min, max, greedy)
    }

    fn atom(&mut self) -> Node {
        let c = self.peek().unwrap();
        self.i += 1;
        match c {
            b'(' => {
                let idx = if self.p[self.i..].starts_with(b"?:") {
                    self.i += 2;
                    None
                } else if self.p[self.i..].starts_with(b"?<!") {
                    self.i += 3;
                    let inner = self.alts();
                    assert_eq!(self.peek(), Some(b')'), "pattern: unclosed look-behind");
                    self.i += 1;
                    match inner.into_iter().next().and_then(|mut s| if s.len() == 1 { s.pop() } else { None }) {
                        Some(Node::Set(set)) => return Node::NotBehind(set),
                        _ => panic!("pattern: look-behind of more than one character"),
                    }
                } else {
                    self.groups += 1;
                    Some(self.groups)
                };
                let inner = self.alts();
                assert_eq!(self.peek(), Some(b')'), "pattern: unclosed group");
                self.i += 1;
                Node::Group(idx, inner)
            }
            b'[' => Node::Set(Box::new(self.class())),
            b'.' => {
                let mut s = [true; 256];
                if !self.dotall {
                    s[b'\n' as usize] = false;
                }
                Node::Set(Box::new(s))
            }
            b'^' => Node::Bol,
            b'$' => Node::Eol,
            b'\\' => {
                let e = self.peek().unwrap();
                self.i += 1;
                match e {
                    b'b' => Node::WordB,
                    b'B' => Node::NotWordB,
                    b'Z' => Node::EndZ,
                    _ => Node::Set(Box::new(escape_set(e))),
                }
            }
            _ => Node::Set(Box::new(one(c))),
        }
    }

    fn class(&mut self) -> Set {
        let mut s = [false; 256];
        let negate = self.peek() == Some(b'^');
        if negate {
            self.i += 1;
        }
        let mut first = true;
        loop {
            let c = self.peek().expect("pattern: unclosed class");
            if c == b']' && !first {
                self.i += 1;
                break;
            }
            first = false;
            self.i += 1;
            if c == b'\\' {
                let e = self.peek().unwrap();
                self.i += 1;
                let set = escape_set(e);
                for (k, v) in set.iter().enumerate() {
                    s[k] |= *v;
                }
                continue;
            }
            if self.peek() == Some(b'-') && self.p.get(self.i + 1).map_or(false, |&x| x != b']') {
                let hi = self.p[self.i + 1];
                self.i += 2;
                for k in c..=hi {
                    s[k as usize] = true;
                }
            } else {
                s[c as usize] = true;
            }
        }
        if negate {
            for v in s.iter_mut() {
                *v = !*v;
            }
        }
        s
    }
}

fn one(c: u8) -> Set {
    let mut s = [false; 256];
    s[c as usize] = true;
    s
}

fn escape_set(e: u8) -> Set {
    let mut s = [false; 256];
    let by = |f: fn(u8) -> bool, neg: bool| {
        let mut s = [false; 256];
        for k in 0..256 {
            s[k] = f(k as u8) != neg;
        }
        s
    };
    match e {
        b's' => by(space, false),
        b'S' => by(space, true),
        b'w' => by(word, false),
        b'W' => by(word, true),
        b'd' => by(|c| c.is_ascii_digit(), false),
        b'D' => by(|c| c.is_ascii_digit(), true),
        b'n' => one(b'\n'),
        b'r' => one(b'\r'),
        b't' => one(b'\t'),
        c if c.is_ascii_alphanumeric() => panic!("pattern: unknown escape \\{}", c as char),
        c => {
            s[c as usize] = true;
            s
        }
    }
}

/// The characters a sequence's match can begin with, when that is known.
fn firsts(seq: &[Node]) -> Option<Set> {
    match seq.first()? {
        Node::Set(s) => Some(**s),
        Node::Group(_, alts) => {
            let mut all = [false; 256];
            for a in alts {
                let f = firsts(a)?;
                for k in 0..256 {
                    all[k] |= f[k];
                }
            }
            Some(all)
        }
        Node::Rep(inner, min, _, _) if *min > 0 => firsts(std::slice::from_ref(inner)),
        // Width-less checks: the match still begins with what follows.
        Node::WordB | Node::NotWordB | Node::NotBehind(_) => firsts(&seq[1..]),
        _ => None,
    }
}

type K<'k> = &'k mut dyn FnMut(usize, &mut Vec<(usize, usize)>) -> bool;

impl Re {
    pub fn new(pattern: &str) -> Re {
        Re::with(pattern, false, false)
    }

    /// `re.M` and `re.S`.
    pub fn with(pattern: &str, multiline: bool, dotall: bool) -> Re {
        Re::bytes(pattern.as_bytes(), multiline, dotall)
    }

    /// A pattern with a name from a mod's files in it, whose characters are
    /// latin-1 bytes like the text's.
    pub fn bytes(pattern: &[u8], multiline: bool, dotall: bool) -> Re {
        let mut p = Parser { p: pattern, i: 0, groups: 0, dotall };
        let alts = p.alts();
        assert!(p.i == pattern.len(), "pattern: stray ) in {}", String::from_utf8_lossy(pattern));
        let first = if alts.len() == 1 { firsts(&alts[0]).map(Box::new) } else { None };
        Re { alts, groups: p.groups, multiline, first }
    }

    /// `pattern.match(text, pos)`.
    pub fn match_at(&self, text: &[u8], pos: usize) -> Option<Match> {
        let mut caps = vec![NONE; self.groups + 1];
        self.try_at(text, pos, &mut caps)
    }

    fn try_at(&self, text: &[u8], pos: usize, caps: &mut Vec<(usize, usize)>) -> Option<Match> {
        for c in caps.iter_mut() {
            *c = NONE;
        }
        let mut end = usize::MAX;
        let mut done = |q: usize, _c: &mut Vec<(usize, usize)>| {
            end = q;
            true
        };
        let m = M { t: text, multiline: self.multiline };
        for alt in &self.alts {
            if m.seq(alt, 0, pos, caps, &mut done) {
                let mut caps = caps.clone();
                caps[0] = (pos, end);
                return Some(Match { caps });
            }
        }
        None
    }

    /// `pattern.search(text, pos)`.
    pub fn search(&self, text: &[u8], pos: usize) -> Option<Match> {
        let mut caps = vec![NONE; self.groups + 1];
        let mut at = pos;
        while at <= text.len() {
            if let Some(first) = &self.first {
                match text[at..].iter().position(|&c| first[c as usize]) {
                    Some(off) => at += off,
                    None => return None,
                }
            }
            if let Some(m) = self.try_at(text, at, &mut caps) {
                return Some(m);
            }
            at += 1;
        }
        None
    }

    /// `pattern.finditer(text)`: every match, left to right, none overlapping.
    pub fn find_all(&self, text: &[u8]) -> Vec<Match> {
        let mut out = Vec::new();
        let mut at = 0;
        while at <= text.len() {
            match self.search(text, at) {
                Some(m) => {
                    at = if m.end() == m.start() { m.end() + 1 } else { m.end() };
                    out.push(m);
                }
                None => break,
            }
        }
        out
    }

    /// `pattern.sub("", text)`.
    pub fn remove(&self, text: &[u8]) -> Vec<u8> {
        let mut out = Vec::with_capacity(text.len());
        let mut last = 0;
        for m in self.find_all(text) {
            out.extend_from_slice(&text[last..m.start()]);
            last = m.end();
        }
        out.extend_from_slice(&text[last..]);
        out
    }
}

struct M<'t> {
    t: &'t [u8],
    multiline: bool,
}

impl<'t> M<'t> {
    fn is_word(&self, p: usize) -> bool {
        p < self.t.len() && word(self.t[p])
    }

    fn seq(&self, nodes: &[Node], mut i: usize, mut p: usize, caps: &mut Vec<(usize, usize)>,
           k: K) -> bool {
        let n = self.t.len();
        // The steps that cannot backtrack are taken in a loop, so a long
        // literal costs no stack.
        loop {
            if i == nodes.len() {
                return k(p, caps);
            }
            match &nodes[i] {
                Node::Set(s) => {
                    if p < n && s[self.t[p] as usize] {
                        p += 1;
                    } else {
                        return false;
                    }
                }
                Node::Bol => {
                    let ok = if self.multiline { p == 0 || self.t[p - 1] == b'\n' } else { p == 0 };
                    if !ok {
                        return false;
                    }
                }
                Node::Eol => {
                    let ok = if self.multiline {
                        p == n || self.t[p] == b'\n'
                    } else {
                        p == n || (p + 1 == n && self.t[p] == b'\n')
                    };
                    if !ok {
                        return false;
                    }
                }
                Node::EndZ => {
                    if p != n {
                        return false;
                    }
                }
                Node::WordB | Node::NotWordB => {
                    let before = p > 0 && self.is_word(p - 1);
                    let edge = before != self.is_word(p);
                    if edge != matches!(nodes[i], Node::WordB) {
                        return false;
                    }
                }
                Node::NotBehind(s) => {
                    if p > 0 && s[self.t[p - 1] as usize] {
                        return false;
                    }
                }
                Node::Group(idx, alts) => {
                    let idx = *idx;
                    for alt in alts {
                        let start = p;
                        let ok = self.seq(alt, 0, p, caps, &mut |q, caps: &mut Vec<(usize, usize)>| {
                            let saved = idx.map(|g| caps[g]);
                            if let Some(g) = idx {
                                caps[g] = (start, q);
                            }
                            if self.seq(nodes, i + 1, q, caps, k) {
                                return true;
                            }
                            if let (Some(g), Some(s)) = (idx, saved) {
                                caps[g] = s;
                            }
                            false
                        });
                        if ok {
                            return true;
                        }
                    }
                    return false;
                }
                Node::Rep(inner, min, max, greedy) => {
                    if let Node::Set(s) = &**inner {
                        // One character a step: count the run and try its
                        // lengths in the order Python would.
                        let mut run = 0;
                        while run < *max && p + run < n && s[self.t[p + run] as usize] {
                            run += 1;
                        }
                        if run < *min {
                            return false;
                        }
                        if *greedy {
                            for c in (*min..=run).rev() {
                                if self.seq(nodes, i + 1, p + c, caps, k) {
                                    return true;
                                }
                            }
                        } else {
                            for c in *min..=run {
                                if self.seq(nodes, i + 1, p + c, caps, k) {
                                    return true;
                                }
                            }
                        }
                        return false;
                    }
                    return self.rep(inner, *min, *max, *greedy, 0, p, caps,
                                    &mut |q, caps: &mut Vec<(usize, usize)>| self.seq(nodes, i + 1, q, caps, k));
                }
            }
            i += 1;
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn rep(&self, node: &Node, min: usize, max: usize, greedy: bool, count: usize, p: usize,
           caps: &mut Vec<(usize, usize)>, k: K) -> bool {
        if greedy && !has_caps(node) {
            return self.greedy_steps(node, min, max, count, p, caps, k);
        }
        let one = std::slice::from_ref(node);
        if greedy {
            if count < max
                && self.seq(one, 0, p, caps, &mut |q, caps: &mut Vec<(usize, usize)>| {
                    q != p && self.rep(node, min, max, greedy, count + 1, q, caps, k)
                })
            {
                return true;
            }
            count >= min && k(p, caps)
        } else {
            if count >= min && k(p, caps) {
                return true;
            }
            count < max
                && self.seq(one, 0, p, caps, &mut |q, caps: &mut Vec<(usize, usize)>| {
                    q != p && self.rep(node, min, max, greedy, count + 1, q, caps, k)
                })
        }
    }

    /// A greedy repeat taken a step at a time while each step can end in
    /// only one place, which is what `(?:[^{}]|\{[^{}]*\})*` always does:
    /// the same order of tries as the recursion above, without a frame per
    /// character. A step that could end in more than one place is handed
    /// to the recursion from there.
    #[allow(clippy::too_many_arguments)]
    fn greedy_steps(&self, node: &Node, min: usize, max: usize, count: usize, p: usize,
                    caps: &mut Vec<(usize, usize)>, k: K) -> bool {
        let one = std::slice::from_ref(node);
        let mut at = vec![p];
        let mut ends = Vec::new();
        loop {
            let cur = *at.last().unwrap();
            let done = count + at.len() - 1;
            if done >= max {
                break;
            }
            ends.clear();
            self.seq(one, 0, cur, caps, &mut |q, _c: &mut Vec<(usize, usize)>| {
                if q != cur {
                    ends.push(q);
                }
                false
            });
            match ends.len() {
                0 => break,
                1 => at.push(ends[0]),
                _ => {
                    if self.rep_recursive(node, min, max, done, cur, caps, k) {
                        return true;
                    }
                    at.pop();
                    break;
                }
            }
        }
        for (i, &q) in at.iter().enumerate().rev() {
            if count + i >= min && k(q, caps) {
                return true;
            }
        }
        false
    }

    /// The greedy recursion, for a step with more than one way to end.
    fn rep_recursive(&self, node: &Node, min: usize, max: usize, count: usize, p: usize,
                     caps: &mut Vec<(usize, usize)>, k: K) -> bool {
        let one = std::slice::from_ref(node);
        if count < max
            && self.seq(one, 0, p, caps, &mut |q, caps: &mut Vec<(usize, usize)>| {
                q != p && self.rep_recursive(node, min, max, count + 1, q, caps, k)
            })
        {
            return true;
        }
        count >= min && k(p, caps)
    }
}

fn has_caps(node: &Node) -> bool {
    match node {
        Node::Group(Some(_), _) => true,
        Node::Group(None, alts) => alts.iter().any(|a| a.iter().any(has_caps)),
        Node::Rep(inner, ..) => has_caps(inner),
        _ => false,
    }
}

/// `vic2scan selftest-re`: patterns and texts on stdin, one JSON-ish line
/// each way, for `testkit` to hold against Python's `re`. Each input line is
/// `flags<TAB>pattern<TAB>text` with the text as hex; each output line is the
/// matches `finditer` finds, as `start,end` of every group.
pub fn selftest() {
    use std::io::BufRead;
    let stdin = std::io::stdin();
    let mut out = String::new();
    for line in stdin.lock().lines() {
        let line = line.unwrap();
        let mut parts = line.splitn(3, '\t');
        let flags = parts.next().unwrap();
        let pat = parts.next().unwrap();
        let hex = parts.next().unwrap_or("");
        let text: Vec<u8> = (0..hex.len() / 2)
            .map(|i| u8::from_str_radix(&hex[2 * i..2 * i + 2], 16).unwrap())
            .collect();
        let re = Re::with(pat, flags.contains('M'), flags.contains('S'));
        let mut first = true;
        for m in re.find_all(&text) {
            if !first {
                out.push(';');
            }
            first = false;
            let parts: Vec<String> = m.caps.iter().map(|&(a, b)| {
                if a == usize::MAX { "-".to_string() } else { format!("{},{}", a, b) }
            }).collect();
            out.push_str(&parts.join(" "));
        }
        out.push('\n');
    }
    print!("{}", out);
}

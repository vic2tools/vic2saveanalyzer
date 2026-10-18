// The tokens of a save or a mod as Python's TOKEN_RE cuts them:
// "quoted", {, }, =, or a run of anything else, with one token of pushback.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::engine::modread::block_end;
use crate::py::re::space;

/// `v2parse.Tokens`: a cursor over `TOKEN_RE`, one token of pushback, and a
/// whole-block skip.
pub struct Tokens<'a> {
    text: &'a [u8],
    pos: usize,
    pushed: Option<Option<(usize, usize)>>,
}

impl<'a> Tokens<'a> {
    pub fn new(text: &'a [u8], at: usize) -> Tokens<'a> {
        Tokens { text, pos: at, pushed: None }
    }

    /// The next token's span, or None at the end.
    pub fn next(&mut self) -> Option<(usize, usize)> {
        if let Some(t) = self.pushed.take() {
            return t;
        }
        let b = self.text;
        let n = b.len();
        let mut i = self.pos;
        while i < n && space(b[i]) {
            i += 1;
        }
        if i >= n {
            self.pos = n;
            return None;
        }
        let c = b[i];
        if c == b'"' {
            if let Some(off) = b[i + 1..].iter().position(|&x| x == b'"') {
                let end = i + 1 + off + 1;
                self.pos = end;
                return Some((i, end));
            }
        }
        if c == b'{' || c == b'}' || c == b'=' {
            self.pos = i + 1;
            return Some((i, i + 1));
        }
        let start = i;
        while i < n && !space(b[i]) && b[i] != b'{' && b[i] != b'}' && b[i] != b'=' {
            i += 1;
        }
        self.pos = i;
        Some((start, i))
    }

    pub fn push(&mut self, t: Option<(usize, usize)>) {
        self.pushed = Some(t);
    }

    pub fn get(&self, t: (usize, usize)) -> &'a [u8] {
        &self.text[t.0..t.1]
    }

    pub(crate) fn is(&self, t: Option<(usize, usize)>, what: &[u8]) -> bool {
        t.is_some_and(|t| self.get(t) == what)
    }

    /// Consume everything up to the `}` closing the block already opened.
    pub fn skip_to_close(&mut self) {
        if let Some(t) = self.pushed.take() {
            if self.is(t, b"}") {
                return;
            }
            if self.is(t, b"{") {
                self.skip_to_close();
            }
        }
        self.pos = block_end(self.text, self.pos).unwrap_or(self.text.len());
    }
}

# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""
Streaming parser for Victoria 2 (.v2) save files.

Vic2 saves are Clausewitz-format text: `key=value`, `key={ ... }`, and bare
lists `{ a b c }`. Files run 20-150 MB, so this walks the token stream and only
builds Python objects for the branches we actually want; everything else is
skipped by brace counting.
"""

import re

TOKEN_RE = re.compile(r'"[^"]*"|[{}=]|[^\s{}=]+')

# The vanilla pop types. Inside a province block these appear as sub-blocks,
# and the same key can repeat (one block per culture/religion combination).
#
# Mods add their own -- IGoR has `bankers` -- and a pop type missing from this
# set is skipped by `read_province`, so its people vanish from every total.
# `register_pop_types` lets the caller fold in whatever the mod's `poptypes/`
# folder declares before any save is read.
VANILLA_POP_TYPES = frozenset((
    "aristocrats", "artisans", "bureaucrats", "capitalists", "clergymen",
    "clerks", "craftsmen", "farmers", "labourers", "officers", "slaves",
    "soldiers",
))
POP_TYPES = set(VANILLA_POP_TYPES)


def register_pop_types(names):
    """
    The pop types to read, as the twelve the game ships plus the mod's own.

    This *replaces* rather than adds. The GUI runs one campaign after another
    inside a single process, and a set that only ever grew carried IGoR's
    `bankers` into the next campaign: Divergences of Darkness, which has no
    such pop type, read one anyway and then cached it under a key that said it
    had not. Which pop types exist is a property of the mod in hand, so it is
    set from scratch each time.
    """
    POP_TYPES.clear()
    POP_TYPES.update(VANILLA_POP_TYPES)
    POP_TYPES.update(n for n in names if n)


# Everything a pop block can hold *other* than the culture=religion line.
# The culture line has no fixed key -- it is literally `british=protestant` --
# so we identify it by elimination.
POP_KNOWN_FIELDS = frozenset([
    "id", "size", "money", "ideology", "issues", "mil", "con", "literacy",
    "bank", "con_factor", "luxury_needs", "everyday_needs", "life_needs",
    "size_changes", "movement", "promoted", "demoted", "days_of_loss",
    "converted", "local_migration", "external_migration", "colonial_migration",
    "assimilated", "type", "faction", "random", "political_movement",
    "social_movement", "supported_regiment", "employed", "stockpile",
    "movement_tag", "movement_issue",
    "need", "production_type", "last_spending", "current_producing",
    "percent_afforded", "percent_sold_domestic", "percent_sold_export",
    "leftover", "throttle", "needs_cost", "production_income", "promotion",
    "literacy_change", "con_change", "mil_change",
])


# Braces and the quote that can hide them. Skipping a block only needs to find
# the brace that closes it, so it can leap between these instead of tokenizing
# every word in between -- and most of a save is blocks nothing here reads.
_BRACE_RE = re.compile(r'["{}]')


class Tokens:
    """Token cursor with one-token pushback and a fast whole-block skip."""

    __slots__ = ("_text", "_it", "_pos", "_pushed", "_last")

    def __init__(self, text, pos=0):
        self._text = text
        self._it = TOKEN_RE.finditer(text, pos)
        self._pos = pos
        self._pushed = None
        self._last = None

    def next(self):
        if self._pushed is not None:
            tok = self._pushed
            self._pushed = None
            return tok
        m = next(self._it, None)
        if m is None:
            return None
        # Where the cursor is only matters when a block gets skipped, which is
        # once in thirty tokens, so the match is kept and asked for its end
        # then rather than three million times on the way there.
        self._last = m
        return m.group()

    def push(self, tok):
        self._pushed = tok

    def skip_to_close(self):
        """Consume everything up to the `}` closing the block already opened."""
        if self._pushed is not None:
            tok = self._pushed
            self._pushed = None
            if tok == "}":
                return
            if tok == "{":
                self.skip_to_close()
        text = self._text
        depth = 1
        i = self._last.end() if self._last is not None else self._pos
        while depth:
            m = _BRACE_RE.search(text, i)
            if m is None:
                i = len(text)
                break
            c = m.group()
            if c == '"':
                j = text.find('"', m.end())
                i = len(text) if j < 0 else j + 1
                continue
            depth += 1 if c == "{" else -1
            i = m.end()
        self._pos = i
        self._last = None             # the kept match is behind the skip now
        self._it = TOKEN_RE.finditer(text, i)


# --- reading a save by its layout rather than a token at a time -------------
#
# The token cursor above is indifferent to whitespace, which is what makes it
# safe, and it is also why a 46 MB save took 1.3 seconds: eight million tokens,
# every one of them a Python step, and most of them inside blocks nothing here
# reads. Five attempts to make that walk cheaper all came back under 1.1x, for
# the same reason each time -- the cost is walking the bytes, not what gets
# built out of them.
#
# The engine writes a save to a fixed layout, though, and mods cannot change it:
# a top-level key sits at column zero with its `{` alone on the next line, a
# province's own fields one tab in, a pop's two. Anchoring to that turns finding
# the blocks into a single C-level scan -- 118 MB/s against 35 -- and the blocks
# nothing reads are never looked at at all.
#
# This was checked against the walk on 69,106 top-level blocks across seventeen
# saves and four mods: same keys, same order, same block-or-scalar, every time.
# `layout_is_flat` is the cheap check that a file still looks like that, and
# when it does not -- a save reflowed by a text editor, a future version of the
# game -- everything falls back to the walk, which needs no layout at all.

_BARE_KEY = re.compile(r'[^\s={}"]+\Z')
HEAD_SCALAR = re.compile(r'(?m)^([^\s={}"]+)=([^\r\n]+)')
# `\n\t` rather than `(?m)^\t`: with a literal to look for, the engine can
# jump from newline to newline instead of offering it every line start in the
# file. Same matches, and about a third off the scan.
_ONE_TAB = re.compile(r'\n\t([^\s={}"]+)=([^\r\n]*)')
# A province's own entries and its pops' fields in one pass, so that a pop's
# numbers can be attributed to the pop block they follow.
#
# The two deep branches are what keeps this cheap. A pop has about two dozen
# fields and seven of them are ever read: six numbers, and the culture line,
# which has no fixed key -- it is literally `french=catholic` -- and so is
# picked out by having a value that does not begin with a digit. Matching only
# those turns half a million matches per save into two hundred thousand.
# Everything else in a pop, and the `ideology`, `issues` and `stockpile` blocks
# it carries, is never looked at, exactly as the token reader never looked at
# them.
PROVINCE_FIELDS = re.compile(
    r'\n\t(?:'
    r'\t(id|size|money|con|mil|literacy|life_needs)=([^\r\n]+)'
    r'|\t([^\s={}"]+)=([^\r\n0-9][^\r\n]*)'
    r'|([^\s={}"]+)=([^\r\n]*))')


class _Block:
    """Marks an entry whose value is a block rather than a scalar."""
    __slots__ = ()

    def __repr__(self):
        return "BLOCK"


BLOCK = _Block()


def top_level_blocks(text):
    """
    Every top-level block, as (key, content start, content stop).

    Found from the braces rather than from the keys. A top-level block opens
    with a `{` alone at column zero -- four thousand of them in a save -- and
    its key is the line above. Looking for the key means offering three million
    line starts to a regex, which came to a quarter of the whole parse; looking
    for `\n{` is a memchr, and the key is then read backwards off one line.

    A block runs to the key line of the next one. That is more than the block
    itself, and deliberately so: every reader stops at its own closing brace and
    ignores the rest, and finding that brace exactly would mean counting braces
    through the whole file again.

    Returns None if any of those braces has anything other than a bare `key=`
    above it, which is the whole of the layout this depends on. A save reflowed
    by a text editor fails here and is read by the token walk instead.
    """
    found = []
    pos = text.find("\n{")
    while pos >= 0:
        line = text.rfind("\n", 0, pos) + 1
        key = text[line:pos]
        if key[-1:] == "\r":
            key = key[:-1]
        if key[-1:] != "=" or not _BARE_KEY.match(key, 0, len(key) - 1):
            return None
        found.append((key[:-1], pos + 2, line))
        pos = text.find("\n{", pos + 2)
    if not found:
        return None
    return [(key, at, found[i + 1][2] if i + 1 < len(found) else len(text))
            for i, (key, at, _line) in enumerate(found)]


def scan_entries(text, start, stop):
    """
    Entries one level inside a block, read off the layout.

    Yields (key, value, at). `value` is the scalar as written, or `BLOCK`, in
    which case `at` is the position just past that block's `{`.
    """
    for m in _ONE_TAB.finditer(text, start, stop):
        value = m.group(2).strip()
        if value and value[0] != "{":
            yield m.group(1), unquote(value), -1
        else:
            brace = text.find("{", m.end(1), stop)
            if brace >= 0:
                yield m.group(1), BLOCK, brace + 1


def walk_entries(tok, top=False):
    """
    The same, tokenised, for a save whose whitespace cannot be trusted.

    Each block is skipped before it is handed over, so a caller reading it with
    a cursor of its own cannot disturb this one.

    `top` says there is no enclosing block to be closed, so a brace that turns
    up on its own is stepped over rather than taken as the end of anything.
    """
    while True:
        t = tok.next()
        if t is None:
            return
        if t == "}":
            if not top:
                return
            continue
        if top and t in ("{", "="):
            continue
        nxt = tok.next()
        if nxt is None:
            return
        if nxt != "=":
            tok.push(nxt)
            continue
        val = tok.next()
        if val is None:
            return
        if val == "{":
            at = tok._last.end()
            tok.skip_to_close()
            yield unquote(t), BLOCK, at
        else:
            yield unquote(t), unquote(val), -1


def unquote(tok):
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        return tok[1:-1]
    return tok


def skip_block(tok):
    """Consume tokens until the block opened by the caller's `{` closes."""
    tok.skip_to_close()


def parse_block(tok, skip=frozenset()):
    """
    Parse a block whose opening `{` has already been consumed.

    Returns a dict. Repeated keys collapse into a list under that key. A block
    made of bare values (`{ "irish" "welsh" }`) returns a list instead.

    `skip` names sub-blocks to step over at any depth rather than build. A
    state's `employment` is the reason it exists: it lists every employed pop of
    every factory and is most of the block by size, and nothing here has ever
    read it.
    """
    out = {}
    items = []
    while True:
        t = tok.next()
        if t is None or t == "}":
            break
        if t == "{":
            items.append(parse_block(tok, skip))
            continue
        if t == "=":
            continue
        nxt = tok.next()
        if nxt == "=":
            val_tok = tok.next()
            if val_tok == "{":
                key = unquote(t)
                if key in skip:
                    tok.skip_to_close()
                    continue
                val = parse_block(tok, skip)
            elif val_tok is None:
                break
            else:
                val = unquote(val_tok)
            key = unquote(t)
            if key in out:
                cur = out[key]
                if isinstance(cur, list) and getattr(cur, "_multi", False):
                    cur.append(val)
                else:
                    multi = _MultiList([cur, val])
                    out[key] = multi
            else:
                out[key] = val
        else:
            items.append(unquote(t))
            tok.push(nxt)
    if items:
        if not out:
            return items
        out["_items"] = items
    return out


class _MultiList(list):
    """Marks a list that came from repeated keys, not a bare value list."""
    _multi = True


def as_list(value):
    """Normalise a field that may be absent, single, or repeated."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def read_pop(tok):
    """
    One pop block, scalars only.

    Every pop carries an `ideology` and an `issues` sub-block, and between them
    they hold about two thirds of the tokens in the pop section of a save --
    sixteen party-support numbers and six ideology numbers against fourteen
    fields that are actually read. Nothing here looks at either, so they are
    skipped at the brace instead of being built into dictionaries and thrown
    away. `pop_culture` still works, because it only ever considered the string
    fields and a skipped block was never one.
    """
    out = {}
    while True:
        t = tok.next()
        if t is None or t == "}":
            break
        nxt = tok.next()
        if nxt is None:
            break
        if nxt != "=":
            tok.push(nxt)
            continue
        val = tok.next()
        if val is None:
            break
        if val == "{":
            tok.skip_to_close()
        else:
            out[unquote(t)] = unquote(val)
    return out


def pop_culture(pop):
    """
    Pull (culture, religion) out of a parsed pop block.

    The pair is stored as a bare `culture=religion` line with no stable key,
    so we take the first entry that isn't a known field and isn't numeric.
    """
    for key, val in pop.items():
        if key in POP_KNOWN_FIELDS or key.startswith("_"):
            continue
        if not isinstance(val, str):
            continue
        try:
            float(val)
        except ValueError:
            return key, val
    return None, None


def looks_like_country_tag(key):
    """Vic2 tags are three chars: ENG, FRA, plus dynamic ones like D01, U03."""
    return (
        len(key) == 3
        and key[0].isalpha()
        and key[0].isupper()
        and all(c.isalnum() for c in key)
        and not key.isdigit()
    )


def read_save_text(path):
    """
    Read a .v2 save as text, with a clear error if it isn't plaintext.

    Vic2 can write compressed/binary saves. Launching the game in debug mode
    and re-saving produces a plaintext file (about 10x larger).
    """
    with open(path, "rb") as fh:
        head = fh.read(4096)
        if head[:2] == b"PK":
            raise ValueError(
                f"{path} is a zip archive. Extract it, or re-save the game in "
                f"debug mode to get plaintext."
            )
        if b"date=" not in head and b'date =' not in head:
            raise ValueError(
                f"{path} does not look like a plaintext Vic2 save (no `date=` "
                f"in the header). If it is binary, launch Victoria 2 in debug "
                f"mode and re-save."
            )
        fh.seek(0)
        raw = fh.read()
    # Vic2 files are Windows-1252 / ANSI. latin-1 never raises, which matters
    # because province names carry stray high bytes in some mods.
    return raw.decode("latin-1")

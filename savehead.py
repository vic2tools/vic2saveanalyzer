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
The front of a save: what its first few hundred kilobytes say, without
reading the rest.

The keeper reads a save this way to decide which campaign an autosave
continues. `--cross`, in the scanner, holds a campaign folder's saves to the
same measured rule about event flags (`FLAG_GAP`, `FLAG_FLOOR`) to name one
that may be from another game; `scanner/src/front/cross.rs` copies the
numbers, and `testkit/histories.py` holds both to them.
"""

import re

# Everything the game writes above the first province block, with room to
# spare: the date, the player, the start date and the event flags.
HEADER_BYTES = 400_000

_FIELD = re.compile(rb'(date|player|start_date)\s*=\s*"([^"]*)"')
_FLAGS = re.compile(rb'^flags=\s*\{(.*?)^\}', re.M | re.S)
_FLAG_NAME = re.compile(rb'^\s*([A-Za-z_]\w*)\s*=', re.M)

# Global event flags accumulate, so an earlier save's flags should all be in
# a later save of the same game. Flags do get cleared on purpose --
# `money_setup_done` and the rest are one-shot setup flags -- so a few lost
# prove nothing. Two saves from one campaign never disagreed by more than
# five flags across the 2,850 real pairs this was measured on; two from
# different campaigns disagreed by twelve at the median. `FLAG_GAP` is that
# gap. Below `FLAG_FLOOR` flags there is nothing to measure -- an 1836 save
# has none at all.
#
# What `FLAG_FLOOR` costs, said plainly: in the opening year or two of a
# campaign there are barely any flags, so a nation formed that early cannot
# be shown to be the same campaign and the keeper starts a folder of its
# own. Nothing in the game forms in 1836, so this has never come up in play
# -- it turned up against a fake campaign written to test the keeper, whose
# saves carried two flags.
FLAG_GAP = 6
FLAG_FLOOR = 3


def head_of(path, size=HEADER_BYTES):
    """The first `size` bytes of a save, or None if it cannot be read."""
    try:
        with open(path, "rb") as fh:
            return fh.read(size)
    except OSError:
        return None


def fields(head):
    """{"date", "player", "start_date"}: the first of each the head has."""
    found = {}
    for match in _FIELD.finditer(head):
        found.setdefault(match.group(1).decode(),
                         match.group(2).decode("latin-1"))
        if len(found) == 3:
            break
    return found


def flags_in(head):
    """The global event flags a head carries, as a set of names."""
    block = _FLAGS.search(head)
    return set(_FLAG_NAME.findall(block.group(1))) if block else set()


def header(path):
    """
    The date, the player's tag, the start date and the event flags of a save.

    Returns None if the file cannot be read yet or does not look like a
    plaintext save -- both of which mean "not now" rather than "never": the
    game holds the file while it writes, and a save caught mid-write has no
    header.
    """
    head = head_of(path)
    if head is None or head[:2] == b"PK" or b"date=" not in head[:4096]:
        return None
    found = fields(head)
    if "date" not in found or "player" not in found:
        return None
    found["flags"] = flags_in(head)
    return found


def flags_lost(earlier, later):
    """
    How many of the earlier save's flags the later one lacks, or None when
    either has too few flags to be evidence (`FLAG_FLOOR`). Under `FLAG_GAP`
    the two can be one history; at or over it they are two games.
    """
    if len(earlier) < FLAG_FLOOR or len(later) < FLAG_FLOOR:
        return None
    return len(earlier - later)

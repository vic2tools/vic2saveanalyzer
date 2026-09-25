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

Three parts of the program look at saves this way. The keeper decides which
campaign an autosave continues; `--cross` checks that a folder's saves share
one history; and the analyzer puts a campaign's saves in date order before
it reads any of them. Each had its own copy of the patterns, and the keeper
and `--cross` each their own copy of the measured rule about event flags.
"""

import os
import re
import sys

from dates import ymd

# Everything the game writes above the first province block, with room to
# spare: the date, the player, the start date and the event flags.
HEADER_BYTES = 400_000

_FIELD = re.compile(rb'(date|player|start_date)\s*=\s*"([^"]*)"')
_FLAGS = re.compile(rb'^flags=\s*\{(.*?)^\}', re.M | re.S)
_FLAG_NAME = re.compile(rb'^\s*([A-Za-z_]\w*)\s*=', re.M)
_DATE = re.compile(rb'date\s*=\s*"([\d.]+)"')

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


def date_of(path):
    """A save's in-game date, off its first line, without parsing it."""
    try:
        with open(path, "rb") as fh:
            found = _DATE.search(fh.read(4096))
    except OSError:
        return ""
    return found.group(1).decode("ascii") if found else ""


def sort_key(date):
    """(0, year, month, day), or (1, 0, 0, 0) -- after every date -- for none."""
    got = ymd(date)
    return (0,) + got if got else (1, 0, 0, 0)


def in_date_order(files):
    """
    The saves sorted by the date inside them, read from their first line.

    Worth the 4 KB a save: the campaign has to be walked oldest first -- war
    histories fold that way -- and knowing the order up front is what lets
    saves be handed over one at a time instead of collected and sorted.
    Saves with no date come last, by name.
    """
    return sorted(files, key=lambda p: (sort_key(date_of(p)), p))


def one_per_date(files):
    """
    `files`, in date order, with one save per in-game date.

    Two saves carrying the same date used to be read twice over: every
    table held both, so a copy of one save doubled its rows, while the
    report -- which keeps one reading a date -- showed the later of the two.
    It happens for real. Every game's first save is 1836.1.1, so a folder
    holding two games holds two of those, and a save made by hand can fall
    on an autosave's day. The later-named file is kept, which is the one
    the report already showed, and the rest are named on the way past.
    """
    kept, dates, clash = [], [], {}
    for path in files:
        date = date_of(path)
        key = sort_key(date)
        if kept and key[0] == 0 and key == dates[-1]:
            clash.setdefault(date, [kept[-1]]).append(path)
            kept[-1] = path
            continue
        kept.append(path)
        dates.append(key)
    for date, same in clash.items():
        print("note: %s are all dated %s, so only %s is read. Saves from two "
              "games in one folder? Keep each game in a folder of its own."
              % (", ".join(os.path.basename(p) for p in same), date,
                 os.path.basename(same[-1])), file=sys.stderr)
    return kept

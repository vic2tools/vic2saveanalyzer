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
One war block of a save, read: its sides, who joined and left when, its
goals, and every battle it records with what each side lost.

Part of reading a save -- `readsave.analyze_save` hands it each
`active_war` and `previous_war` block -- and so part of what the parse
cache is keyed on. What a campaign makes of the wars across its saves is
`wars.py`, which is not.
"""

import re

from dates import date_key
from v2parse import as_list, to_int, unquote


_I32_WRAP = 2 ** 32 // 1000


def unwrap_overflow(n):
    """
    Undo a single signed-32-bit overflow on a Vic2 battle stat.

    Vic2 tracks casualties and per-type unit counts internally as a signed
    32-bit fixed-point integer with 3 implied decimal places (the true count
    times 1000). A troop count has no fractional part, so that raw internal
    value is always an exact multiple of 1000 -- but a save with big enough
    numbers (as heavily-scaled mods produce) can still push it past
    INT32_MAX and wrap around into negative territory, which is what turns
    up in the save file as a nonsensical negative loss or unit count.

    Since the true raw value was an exact multiple of 1000 and the wrap
    subtracts exactly 2**32, undoing it is just adding back 2**32 // 1000 =
    4,294,967 -- the arithmetic leaves no fractional remainder to round.

    This can't tell a once-wrapped value from one that wrapped twice (a true
    count north of roughly 4.29 million), which comes back out positive and
    silently wrong with no way to catch it from the number alone -- but
    that's already a game/mod bug either way, not something a sign check on
    its own can fully undo.
    """
    return n + _I32_WRAP if n < 0 else n


def _side(block):
    """One side of a battle: country, leader, losses and the units engaged."""
    if not isinstance(block, dict):
        return None
    out = {"country": unquote(str(block.get("country", ""))),
           "leader": unquote(str(block.get("leader", ""))),
           "losses": unwrap_overflow(to_int(block.get("losses"), 0)),
           "units": {}}
    for key, val in block.items():
        if key in ("country", "leader", "losses") or key.startswith("_"):
            continue
        n = unwrap_overflow(to_int(val, 0))
        if n:
            out["units"][key] = n
    return out


def read_war(block, active):
    """
    One `previous_war` or `active_war` block, flattened.

    `history` mixes two kinds of entry. Dated keys carry who joined or left and,
    while the war is recent enough, the battles themselves. Battles that have
    aged out of that window sit bare at the top of the history with no date at
    all, which is why dating them takes more than one save.
    """
    if not isinstance(block, dict):
        return None
    history = block.get("history")
    history = history if isinstance(history, dict) else {}

    joined, left, battles = [], [], []

    def take_battle(raw, when):
        if not isinstance(raw, dict):
            return
        battles.append({
            "name": unquote(str(raw.get("name", ""))),
            "location": to_int(raw.get("location"), 0),
            "date": when,
            # `result=yes` is an attacker victory; 889 of 1310 in one save.
            "attacker_won": str(raw.get("result", "")).lower() == "yes",
            "attacker": _side(raw.get("attacker")),
            "defender": _side(raw.get("defender")),
        })

    for key, value in history.items():
        if key == "battle":
            for raw in as_list(value):
                take_battle(raw, None)
            continue
        if not re.match(r"^\d{3,4}\.\d{1,2}\.\d{1,2}$", str(key)):
            continue
        for entry in as_list(value):
            if not isinstance(entry, dict):
                continue
            for what, who in entry.items():
                if what == "battle":
                    for raw in as_list(who):
                        take_battle(raw, key)
                elif what in ("add_attacker", "add_defender"):
                    joined.append((key, unquote(str(who)),
                                   what == "add_attacker"))
                elif what in ("rem_attacker", "rem_defender"):
                    left.append((key, unquote(str(who)),
                                 what == "rem_attacker"))

    def read_goal(raw):
        if not isinstance(raw, dict):
            return None
        return {
            "casus_belli": unquote(str(raw.get("casus_belli", ""))),
            "actor": unquote(str(raw.get("actor", ""))),
            "receiver": unquote(str(raw.get("receiver", ""))),
            "province": to_int(raw.get("state_province_id"), 0),
            "added": unquote(str(raw.get("date", ""))),
            # The game records this itself while the war runs, so a fulfilled
            # goal needs no inference from who owns what afterwards.
            "fulfilled": str(raw.get("is_fulfilled", "")).lower() == "yes",
        }

    # Goals added during the war live at the top level of an ACTIVE war and are
    # dropped when it ends, exactly as battle dates are. A war read only from
    # the final save keeps its original goal and nothing else -- the USA's claim
    # on Georgia inside the French Conquest of Friesland survives only in a save
    # taken while that war was still being fought.
    goals = [g for g in (read_goal(raw) for raw in as_list(block.get("war_goal")))
             if g and (g["actor"] or g["receiver"])]

    goal = block.get("original_wargoal")
    goal = goal if isinstance(goal, dict) else {}
    # `action` is not the war's start -- one war runs 1854 to 1858 with an
    # action of 1858.3.30, another has an action in the middle of its history.
    # The history's own dates are the reliable bounds.
    dates = ([d for d, _w, _a in joined] + [d for d, _w, _a in left]
             + [b["date"] for b in battles if b["date"]])
    return {
        "name": unquote(str(block.get("name", ""))),
        "active": active,
        "start": min(dates, key=date_key) if dates else "",
        "end": max(dates, key=date_key) if dates and not active else "",
        "original_attacker": unquote(str(block.get("original_attacker", ""))),
        "original_defender": unquote(str(block.get("original_defender", ""))),
        "attackers": sorted({w for _d, w, a in joined if a}),
        "defenders": sorted({w for _d, w, a in joined if not a}),
        # Who is in it now, as the war block itself lists them. The joins
        # above are not that: a nation that made a separate peace keeps its
        # join and gains a leave, and one put into the war by hand -- the
        # host of a multiplayer game merging two wars -- has no join at all.
        # This is what a trigger's `war = yes` is asked about.
        "fighting": sorted({unquote(str(tag)) for side in ("attacker", "defender")
                            for tag in as_list(block.get(side))}),
        # Raw (date, tag, is_attacker) join events, kept alongside the flat tag
        # sets above so a consumer can tell an original belligerent from a
        # later intervention -- the sets alone collapse that distinction.
        "joins": [[d, w, a] for d, w, a in joined],
        # And the other end of it. A nation can be knocked out of a war years
        # before the war finishes -- a separate peace, or annexation -- and the
        # join date alone reads as though it fought to the end.
        "leaves": [[d, w, a] for d, w, a in left],
        "goals": goals,
        "goal": {
            "casus_belli": unquote(str(goal.get("casus_belli", ""))),
            "actor": unquote(str(goal.get("actor", ""))),
            "receiver": unquote(str(goal.get("receiver", ""))),
            "province": to_int(goal.get("state_province_id"), 0),
        },
        "battles": battles,
    }

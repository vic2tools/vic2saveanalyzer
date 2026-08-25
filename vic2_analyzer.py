#!/usr/bin/env python3
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
Victoria 2 campaign analyzer.

Reads a folder of .v2 saves from the same game and builds a per-nation time
series: population, accepted-culture share, literacy, brigades, ships by type,
industry, naval bases, and the usual country scalars.

    python3 vic2_analyzer.py ~/Documents/Paradox\\ Interactive/Victoria2/save\\ games
    python3 vic2_analyzer.py saves/ --out results --tags ENG FRA GER
    python3 vic2_analyzer.py saves/ --no-html

Saves must be plaintext. If yours are binary, launch the game in debug mode
and re-save; the file gets about 10x bigger but becomes readable.
"""

import argparse
import csv
import math
import json
import hashlib
import os
import pickle
import re
import tempfile
import zlib
import sys
from collections import Counter, defaultdict

import v2parse
from v2parse import (
    BLOCK,
    HEAD_SCALAR,
    POP_KNOWN_FIELDS,
    POP_TYPES,
    TOKEN_RE,
    PROVINCE_FIELDS,
    Tokens,
    as_list,
    scan_entries,
    top_level_blocks,
    walk_entries,
    looks_like_country_tag,
    parse_block,
    pop_culture,
    read_pop,
    read_save_text,
    skip_block,
    to_float,
    to_int,
    unquote,
)
from tech_groups import (ARMY_LINES, ARMY_TECHS, NAVY_LINES,
                         NAVY_TECHS, TECH_GROUP)

POP_TYPE_LIST = sorted(POP_TYPES)

# Strata, for the "who actually holds the wealth" view.
STRATA = {
    "poor": ["farmers", "labourers", "slaves", "soldiers", "craftsmen"],
    "middle": ["artisans", "bureaucrats", "clergymen", "clerks", "officers"],
    "rich": ["aristocrats", "capitalists"],
}

# Mobilization draws from poor-strata pops that are neither soldiers (they
# already man the standing army) nor slaves, and only from pops of the primary
# or an accepted culture, in unoccupied non-colonial provinces. Which types
# those are is a property of the mod's poptypes/ folder, not a constant, so
# --mod-path replaces this default; it is what vanilla and IGoR both work out to.
MOBILIZABLE_TYPES = frozenset(["farmers", "labourers", "craftsmen"])

# The set read_province actually collects pops for. main() narrows or widens it
# from the mod's strata table (or --mob-types) before any save is parsed,
# because a pop type that is not collected here can never be counted later.
MOB_CANDIDATES = set(MOBILIZABLE_TYPES)

# Reform groups, as `common/issues.txt` names them. A country block writes its
# choice as a plain `conscription=mandatory_service` line, indistinguishable
# from any other scalar until you know that `conscription` is a reform -- which
# only the mod can say, and which some of them hang mobilisation size off. Set
# before any save is read, the same way the pop types are.
REFORM_KEYS = set()


def set_reform_keys(names):
    """Choose which country scalars read_country keeps as reform choices."""
    REFORM_KEYS.clear()
    REFORM_KEYS.update(names)


def set_mob_candidates(types):
    """Choose which pop types read_province keeps for the mobilization pool."""
    MOB_CANDIDATES.clear()
    MOB_CANDIDATES.update(types)


class Cancelled(Exception):
    """The caller asked for the run to stop before it finished."""


# A window has a Stop button; a terminal has Ctrl-C. Whoever is driving hands a
# callable in and it is asked, between saves, whether to carry on. Between
# saves rather than inside one because a save is a few seconds at worst and
# unwinding a half-read one buys nothing.
_STOP = None


def set_cancel_check(fn):
    """Give the analyzer something to ask before it starts the next save."""
    global _STOP
    _STOP = fn


def _stop_if_asked():
    if _STOP is not None and _STOP():
        raise Cancelled()


# Victoria II defines. A mod can change these; --mod-path reads the real values
# out of common/defines.lua, and the command line overrides both.
POP_SIZE_PER_REGIMENT = 3000
# The engine applies no minimum pop size to *mobilization*. POP_MIN_SIZE_FOR_REGIMENT
# governs how small a *soldier* pop may be and still support a standing brigade,
# which is a different rule on a different pop type -- IGoR sets it to 1000.
#
# How the count works is in brigades_from_clusters and in the README. It was
# measured on a purpose-built test bed inside the mod rather than fitted, and
# POP_SIZE_PER_REGIMENT is the only number in it. Six earlier models -- per-pop
# truncation, a cascade up province/state/nation, a province levy, a fixed
# share of short pops, a manpower threshold, and a pooled scale factor -- were
# each fitted to in-game readings and each failed somewhere; they are gone, and
# the README records what they were and how they broke.


def shift_months(date, back):
    """Step a `YYYY.M.D` date backwards by `back` months."""
    try:
        y, m, d = (int(p) for p in date.split("."))
    except (ValueError, AttributeError):
        return ""
    total = y * 12 + (m - 1) - back
    return f"{total // 12}.{total % 12 + 1}.{d}"


def read_worldmarket(block, save_date):
    """
    Pull price data out of the worldmarket block.

    Vic2 keeps a rolling buffer of monthly price snapshots in repeated
    `price_history` blocks, oldest first, stamped by `price_history_last_update`.
    One save therefore carries about three years of monthly prices, and a run of
    saves stitches into a continuous series.

    Prices move by at most ~0.01/day (see the `price_change` block), and
    consecutive history entries differ by up to ~0.30, which is what fixes the
    interval at one month.
    """
    def numeric(name):
        sub = block.get(name)
        if not isinstance(sub, dict):
            return {}
        return {k: to_float(v) for k, v in sub.items()
                if not k.startswith("_") and isinstance(v, str)}

    current = numeric("price_pool")
    history_blocks = [b for b in as_list(block.get("price_history"))
                      if isinstance(b, dict)]
    last_update = block.get("price_history_last_update", "")
    if isinstance(last_update, str):
        last_update = unquote(last_update)
    else:
        last_update = ""

    history = []
    count = len(history_blocks)
    for idx, snapshot in enumerate(history_blocks):
        stamp = shift_months(last_update, count - 1 - idx) if last_update else ""
        if not stamp:
            continue
        for good, price in snapshot.items():
            if good.startswith("_") or not isinstance(price, str):
                continue
            history.append((stamp, good, to_float(price)))

    snapshot_fields = {
        "world_pool": "worldmarket_pool",
        "supply": "supply_pool",
        "demand": "demand",
        "real_demand": "real_demand",
        "actual_sold": "actual_sold",
        "actual_sold_world": "actual_sold_world",
        "discovered": "discovered_goods",
    }
    snapshot = {name: numeric(key) for name, key in snapshot_fields.items()}

    return {
        "current": current,
        "history": history,
        "last_update": last_update,
        "snapshot": snapshot,
        "save_date": save_date,
    }


def blank_nation():
    return {
        "primary_culture": "",
        "accepted_cultures": [],
        "civilized": "",
        "government": "",
        "capital": "",
        "prestige": 0.0,
        "infamy": 0.0,
        "treasury": 0.0,
        "tax_base": 0.0,
        "war_exhaustion": 0.0,
        "plurality": 0.0,
        "research_points": 0.0,
        "techs": 0,
        "brigades": 0,
        "armies": 0,
        "ships": 0,
        "navies": 0,
        "ships_by_type": defaultdict(int),
        "regiments_by_type": defaultdict(int),
        "regiment_pops": [],
        # province id -> {unit type: brigades}, for the deployment map
        "units_at": defaultdict(Counter),
        "mobilized_brigades": 0,
        "regular_brigades": 0,
        "mobilizing": 0,
        "is_mobilized": 0,
        "tech_list": [],
        "invention_ids": [],
        "nationalvalue": "",
        "tag": "",
        "modifiers": [],
        "revanchism": 0.0,
        "ruling_party": 0,
        "war_policy": "",
        "country_flags": set(),
        # reform group -> the option this nation has chosen, for the handful of
        # reforms a mod attaches mobilisation size to.
        "reforms": {},
        "human": False,
        "is_player": False,
        "army_techs": 0,
        "navy_techs": 0,
        "factory_count": 0,
        "factory_levels": 0,
        "states": 0,
        "provinces": 0,
        "naval_base_levels": 0,
        "max_naval_base": 0,
        "ports": 0,
        "fort_levels": 0,
        "railroad_levels": 0,
        "total_pop": 0,
        "pop_by_type": defaultdict(int),
        "pop_by_culture": defaultdict(int),
        # province id -> soldier pop living there. Kept per province rather than
        # as one total because soldiers in a colonial state raise no brigades,
        # and which provinces those are is only known once the country block
        # has been read -- provinces come first in a save.
        "soldiers_at": defaultdict(int),
        # good -> what this nation put on the world market, from the save's own
        # `saved_country_supply`. Summed over the nations still holding land it
        # comes back to the world market's supply pool exactly, which is what
        # makes it a share of production rather than a stockpile. Summed over
        # every country block it overshoots, because a nation that no longer
        # exists keeps the last figure it ever had.
        "goods_supply": {},
        # Every eligible pop kept whole, as (poptype, culture, size, province).
        # The engine truncates each bucket of manpower it counts and throws the
        # remainder away, so the ceiling cannot be derived from a national
        # total -- where the buckets are drawn is the whole question.
        "mobilizable_pops": [],
        # What the pops dropped below came to, so the readout can still say so
        "mob_excluded_culture": 0,
        "colonial_provinces": set(),
        # province id -> state ordinal, because unused mobilization manpower
        # is pooled by state before it reaches the nation.
        "province_state": {},
        # Provinces the owner does not control. The engine mobilizes nobody
        # from an occupied province, so their pops are held aside rather than
        # dropped -- the difference is worth being able to see.
        "occupied_provinces": set(),
        "literacy_weighted": 0.0,
        "con_weighted": 0.0,
        "mil_weighted": 0.0,
        "money_total": 0.0,
    }


def building_level(value):
    """
    Province buildings are stored either as a bare pair `{ 6.000 6.000 }`
    or as a dict with a level field, depending on version and mod.
    """
    if isinstance(value, list) and value:
        return to_float(value[0])
    if isinstance(value, dict):
        for key in ("level", "building_level"):
            if key in value:
                return to_float(value[key])
        items = value.get("_items")
        if items:
            return to_float(items[0])
    return to_float(value)


# A pop as the counting needs it: its type, then the six fields read out of it
# and the culture its unnamed line gives. The scan fills these in place, which
# is what saves a save's worth of dictionaries -- twenty-five thousand of them,
# each built, filled and read back one key at a time.
_POP_TYPE, _POP_ID, _POP_SIZE, _POP_CULTURE = 0, 1, 2, 3
_POP_MONEY, _POP_CON, _POP_MIL, _POP_LITERACY = 4, 5, 6, 7
_POP_SLOT = {"id": _POP_ID, "size": _POP_SIZE, "money": _POP_MONEY,
             "con": _POP_CON, "mil": _POP_MIL, "literacy": _POP_LITERACY}


def _pop_fields(poptype, pop):
    """The same seven, out of a pop block the token reader built."""
    culture, _religion = pop_culture(pop)
    return [poptype, pop.get("id"), pop.get("size"), culture,
            pop.get("money"), pop.get("con"), pop.get("mil"),
            pop.get("literacy")]


def read_province(text, at, stop, nations, province_owner_sink,
                  pop_registry=None, province_id=None, owner_map=None,
                  flat=True):
    """One province block, attributing its pops to the owner."""
    owner = None
    controller = None
    pops = []
    buildings = {}

    if flat:
        # One scan yields the province's own entries and its pops' fields
        # interleaved, in file order, so each field lands in the pop block above
        # it. `current` is that block; anything at province level closes it,
        # which is what keeps the fields of a `military_construction` or a
        # `party_loyalty` from being read as somebody's pop. The loop is written
        # out rather than handed to a generator because it runs half a million
        # times a save, and a yield each time is a fifth of the parse.
        current = None
        for m in PROVINCE_FIELDS.finditer(text, at, stop):
            key = m.group(1)
            if key is not None:                       # a pop's own number
                if current is not None:
                    current[_POP_SLOT[key]] = m.group(2).rstrip()
                continue
            key = m.group(3)
            if key is not None:
                # A pop's culture is written as `french=catholic`, with no key
                # of its own, so it is the first field that is neither one of
                # the game's own nor a number -- which is how the token reader
                # found it too, by elimination over the whole block.
                if (current is not None and current[_POP_CULTURE] is None
                        and key not in POP_KNOWN_FIELDS):
                    try:
                        float(unquote(m.group(4).rstrip()))
                    except ValueError:
                        current[_POP_CULTURE] = key
                continue
            key = m.group(5)
            value = m.group(6).strip()
            if value and value[0] != "{":
                current = None
                if key == "owner":
                    owner = unquote(value)
                elif key == "controller":
                    controller = unquote(value)
            elif key in POP_TYPES:
                current = [key, None, None, None, None, None, None, None]
                pops.append(current)
            else:
                current = None
                if key in ("naval_base", "fort", "railroad"):
                    brace = text.find("{", m.end(5), stop)
                    if brace >= 0:
                        buildings[key] = parse_block(Tokens(text, brace + 1))
    else:
        for key, value, block_at in walk_entries(Tokens(text, at)):
            if value is not BLOCK:
                if key == "owner":
                    owner = value
                elif key == "controller":
                    controller = value
            elif key in POP_TYPES:
                pops.append(_pop_fields(key, read_pop(Tokens(text, block_at))))
            elif key in ("naval_base", "fort", "railroad"):
                buildings[key] = parse_block(Tokens(text, block_at))

    if not owner:
        return
    if owner_map is not None and province_id is not None:
        # Both, because the map shades occupied land by whoever holds it while
        # still knowing whose it is.
        owner_map[province_id] = (owner, controller or owner)
    province_owner_sink[owner] += 1
    nat = nations[owner]
    nat["provinces"] += 1
    if controller and controller != owner:
        nat["occupied_provinces"].add(province_id)

    nb = building_level(buildings.get("naval_base", 0))
    if nb > 0:
        nat["ports"] += 1
        nat["naval_base_levels"] += nb
        nat["max_naval_base"] = max(nat["max_naval_base"], nb)
    nat["fort_levels"] += building_level(buildings.get("fort", 0))
    nat["railroad_levels"] += building_level(buildings.get("railroad", 0))

    for pop in pops:
        poptype = pop[_POP_TYPE]
        if pop_registry is not None and pop[_POP_ID] is not None:
            pop_registry[to_int(pop[_POP_ID], -1)] = poptype
        size = to_int(pop[_POP_SIZE])
        if size <= 0:
            continue
        culture = pop[_POP_CULTURE]
        nat["total_pop"] += size
        nat["pop_by_type"][poptype] += size
        if poptype == "soldiers":
            nat["soldiers_at"][province_id] += size
        if culture:
            nat["pop_by_culture"][culture] += size
            if poptype in MOB_CANDIDATES:
                nat["mobilizable_pops"].append(
                    (poptype, culture, size, province_id))
        nat["literacy_weighted"] += to_float(pop[_POP_LITERACY]) * size
        nat["con_weighted"] += to_float(pop[_POP_CON]) * size
        nat["mil_weighted"] += to_float(pop[_POP_MIL]) * size
        nat["money_total"] += to_float(pop[_POP_MONEY])


def sub_blocks(value):
    """Every dict directly under a key, whether it appeared once or many times."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def count_units(node, nat, where=None):
    """
    Tally armies, navies, regiments and ships anywhere inside a unit block.

    This has to recurse: an army loaded onto transports is stored as an `army`
    block *inside* the `navy` carrying it, so reading army->regiment at one
    fixed depth silently drops every embarked brigade. Early-game colonial
    powers keep most of their army at sea, where the undercount is severe.
    """
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key.startswith("_"):
            continue
        if key == "regiment":
            for reg in sub_blocks(value):
                nat["brigades"] += 1
                # Every regiment names the pop it was raised from. Regiments
                # drawn from a soldier pop are standing brigades; anything drawn
                # from farmers, labourers and the like is mobilized manpower.
                src = reg.get("pop")
                nat["regiment_pops"].append(
                    to_int(src.get("id"), -1) if isinstance(src, dict) else -1)
                # Unit type is an unquoted string like `type=hussar`. Bare id
                # references elsewhere in the save carry a numeric type instead,
                # so anything that parses as a number is not a unit name.
                rtype = str(reg.get("type", ""))
                try:
                    float(rtype)
                    rtype = ""
                except ValueError:
                    pass
                nat["regiments_by_type"][rtype or "unknown"] += 1
                if where is not None:
                    nat["units_at"][where][rtype or "unknown"] += 1
        elif key == "ship":
            for ship in sub_blocks(value):
                nat["ships"] += 1
                nat["ships_by_type"][str(ship.get("type", "unknown"))] += 1
        elif key in ("army", "navy"):
            blocks = sub_blocks(value)
            nat["armies" if key == "army" else "navies"] += len(blocks)
            for block in blocks:
                # An embarked army sits inside the navy carrying it and has no
                # location of its own, so the navy's province is inherited.
                here = to_int(block.get("location"), -1)
                count_units(block, nat, here if here > 0 else where)


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
                    left.append((key, unquote(str(who))))

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
    dates = ([d for d, _w, _a in joined] + [d for d, _w in left]
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
        # Raw (date, tag, is_attacker) join events, kept alongside the flat tag
        # sets above so a consumer can tell an original belligerent from a
        # later intervention -- the sets alone collapse that distinction.
        "joins": [[d, w, a] for d, w, a in joined],
        "goals": goals,
        "goal": {
            "casus_belli": unquote(str(goal.get("casus_belli", ""))),
            "actor": unquote(str(goal.get("actor", ""))),
            "receiver": unquote(str(goal.get("receiver", ""))),
            "province": to_int(goal.get("state_province_id"), 0),
        },
        "battles": battles,
    }


# Blocks inside a country that are built and then never looked at. A state
# lists every employed pop of every factory under `employment`, which is most of
# the block by size; an `id` sub-block is the engine's own handle on a thing and
# says nothing about it; a `leader` is a handle too. `pop` is not in either list
# and must not be, because a regiment's pop is how a brigade is told from a
# mobilized one.
_STATE_SKIP = frozenset(("employment", "stockpile", "id"))
_UNIT_SKIP = frozenset(("id", "leader"))


def read_country(text, at, stop, tag, nations, flat=True):
    """One country block."""
    nat = nations[tag]
    nat["tag"] = tag
    scalars = {
        "nationalvalue": "nationalvalue",
        "primary_culture": "primary_culture",
        "civilized": "civilized",
        "government": "government",
        "capital": "capital",
    }
    numerics = {
        "prestige": "prestige",
        "badboy": "infamy",
        "money": "treasury",
        "tax_base": "tax_base",
        "war_exhaustion": "war_exhaustion",
        "revanchism": "revanchism",
        "plurality": "plurality",
        "research_points": "research_points",
        "ruling_party": "ruling_party",
    }

    entries = (scan_entries(text, at, stop) if flat
               else walk_entries(Tokens(text, at)))
    for key, value, block_at in entries:
        if value is BLOCK:
            if key in ("army", "navy"):
                count_units(
                    {key: parse_block(Tokens(text, block_at), _UNIT_SKIP)}, nat)
            elif key == "culture":
                block = parse_block(Tokens(text, block_at))
                if isinstance(block, list):
                    nat["accepted_cultures"] = [str(c) for c in block]
                elif isinstance(block, dict):
                    nat["accepted_cultures"] = [str(c) for c in block.get("_items", [])]
            elif key == "flags":
                block = parse_block(Tokens(text, block_at))
                if isinstance(block, dict):
                    nat["country_flags"] = {
                        k for k, v in block.items()
                        if not k.startswith("_") and str(v).lower() == "yes"}
            elif key == "modifier":
                block = parse_block(Tokens(text, block_at))
                if isinstance(block, dict) and "modifier" in block:
                    nat["modifiers"].append(unquote(str(block["modifier"])))
            elif key == "saved_country_supply":
                block = parse_block(Tokens(text, block_at))
                if isinstance(block, dict):
                    nat["goods_supply"] = {
                        g: to_float(v) for g, v in block.items()
                        if not g.startswith("_") and to_float(v) > 0}
            elif key == "active_inventions":
                block = parse_block(Tokens(text, block_at))
                ids = block if isinstance(block, list) else block.get("_items", []) if isinstance(block, dict) else []
                nat["invention_ids"] = [to_int(i, -1) for i in ids]
            elif key == "scheduled_mobilization":
                block = parse_block(Tokens(text, block_at))
                # Orders that have not spawned yet are brigades still coming.
                if str(block.get("spawned", "no")).lower() != "yes":
                    nat["mobilizing"] += 1
            elif key == "state":
                block = parse_block(Tokens(text, block_at), _STATE_SKIP)
                nat["states"] += 1
                provs = block.get("provinces")
                ids = (provs if isinstance(provs, list)
                       else provs.get("_items", []) if isinstance(provs, dict)
                       else [])
                ordinal = nat["states"]
                # Mobilization only draws from stated states; colonial and
                # protectorate states are marked with is_colonial.
                colonial = "is_colonial" in block
                for pid in ids:
                    pid = to_int(pid, -1)
                    nat["province_state"][pid] = ordinal
                    if colonial:
                        nat["colonial_provinces"].add(pid)
                for bld in as_list(block.get("state_buildings")):
                    if not isinstance(bld, dict):
                        continue
                    nat["factory_count"] += 1
                    nat["factory_levels"] += to_int(bld.get("level"), 1)
            elif key == "technology":
                block = parse_block(Tokens(text, block_at))
                if isinstance(block, dict):
                    for tech, tval in block.items():
                        if tech.startswith("_"):
                            continue
                        first = tval[0] if isinstance(tval, list) and tval else tval
                        if to_int(first) == 1:
                            nat["techs"] += 1
                            nat["tech_list"].append(tech)
                            if tech in ARMY_TECHS:
                                nat["army_techs"] += 1
                            elif tech in NAVY_TECHS:
                                nat["navy_techs"] += 1
        else:
            clean = value
            if key == "mobilize":
                nat["is_mobilized"] = int(clean.lower() == "yes")
            elif key == "human":
                nat["human"] = clean.lower() == "yes"
            elif key in REFORM_KEYS:
                nat["reforms"][key] = unquote(clean)
            elif key in scalars:
                nat[scalars[key]] = clean
            elif key in numerics:
                nat[numerics[key]] = to_float(clean)


def _walk_top(text, meta):
    """
    Every top-level block, found by tokenising instead of by layout.

    What a save whose whitespace is not the game's own gets: one reflowed by a
    text editor, or written by a version that lays things out differently. It
    reads the top-level scalars on the way past, which the scan takes off the
    head of the file instead.
    """
    for key, value, at in walk_entries(Tokens(text), top=True):
        if value is BLOCK:
            yield key, at, len(text)
        elif key == "date" and not meta["date"]:
            meta["date"] = value
        elif key == "player" and not meta["player"]:
            meta["player"] = value


def analyze_save(path, verbose=True):
    """Parse one save. Returns (meta, {tag: nation_stats})."""
    if verbose:
        print(f"  reading {os.path.basename(path)} ...", end="", flush=True)
    text = read_save_text(path)

    nations = defaultdict(blank_nation)
    province_counts = defaultdict(int)
    pop_registry = {}
    meta = {"file": os.path.basename(path), "date": "", "player": "", "market": None}
    province_owner = {}
    great_nations = []
    wars = []
    market_block = None

    # Where every top-level block starts, in one scan. A block runs to the next
    # key, which is all any reader needs, since each stops at its own closing
    # brace and ignores whatever follows. Blocks nothing here reads -- most of
    # the file -- are never looked at at all, which is most of the win: the old
    # walk had to count braces through all 26 MB of them.
    blocks = top_level_blocks(text)
    flat = blocks is not None
    if flat:
        # `date` and `player` are top-level scalars, and every top-level scalar
        # is written above the first block.
        for m in HEAD_SCALAR.finditer(text, 0, blocks[0][1]):
            key = m.group(1)
            if key == "date" and not meta["date"]:
                meta["date"] = unquote(m.group(2).strip())
            elif key == "player" and not meta["player"]:
                meta["player"] = unquote(m.group(2).strip())
    else:
        blocks = _walk_top(text, meta)

    for key, at, stop in blocks:
        if key.isdigit():
            read_province(text, at, stop, nations, province_counts,
                          pop_registry, province_id=int(key),
                          owner_map=province_owner, flat=flat)
        elif looks_like_country_tag(key):
            read_country(text, at, stop, key, nations, flat=flat)
        elif key in ("active_war", "previous_war"):
            war = read_war(parse_block(Tokens(text, at)), key == "active_war")
            if war:
                wars.append(war)
        elif key == "great_nations":
            # The engine's own great power list, in rank order, as 1-based
            # indices into the country array that common/countries.txt
            # defines. Nothing else in the save ranks nations.
            block = parse_block(Tokens(text, at))
            ids = (block if isinstance(block, list)
                   else block.get("_items", []) if isinstance(block, dict) else [])
            great_nations = [to_int(i, -1) for i in ids]
        elif key == "worldmarket" and market_block is None:
            market_block = parse_block(Tokens(text, at))

    # Classified after the whole file is read, so it does not depend on
    # provinces being written before countries.
    for nat in nations.values():
        for pid in nat["regiment_pops"]:
            poptype = pop_registry.get(pid)
            if poptype is None or poptype == "soldiers":
                nat["regular_brigades"] += 1
            else:
                nat["mobilized_brigades"] += 1
        # The two counts above are the whole reason this list exists, and this
        # is the last line that reads it, so it does not travel any further:
        # not back from the worker, not into the cache, not into the campaign.
        nat["regiment_pops"] = ()

    # A pop counts toward a mobilization ceiling only if the nation accepts its
    # culture, and which cultures those are is settled only once the country
    # block has been read -- a province can appear in the file before its owner.
    # Applying that here rather than in `finalize` drops about half of the
    # largest thing a parsed save carries: half of what a worker sends back,
    # half of what the cache stores, and half of what a campaign of monthly
    # autosaves holds in memory at once. The order of what survives is
    # untouched, because the counting rule depends on it.
    for nat in nations.values():
        pops = nat["mobilizable_pops"]
        if not pops:
            continue
        accepted = accepted_cultures_of(nat)
        keep = []
        dropped = 0
        for entry in pops:
            if entry[1] in accepted:
                keep.append(entry)
            else:
                dropped += entry[2]
        nat["mob_excluded_culture"] = dropped
        nat["mobilizable_pops"] = keep

    meta["province_owner"] = province_owner
    meta["great_nations"] = great_nations
    meta["wars"] = wars

    if isinstance(market_block, dict):
        meta["market"] = read_worldmarket(market_block, meta["date"])

    # Drop tags that exist in the file but hold nothing (released-nation stubs,
    # rebel placeholders, and every uncreated dynamic tag).
    live = {
        tag: nat
        for tag, nat in nations.items()
        if nat["provinces"] > 0 or nat["total_pop"] > 0
    }
    if verbose:
        months = len({d for d, _, _ in meta["market"]["history"]}) if meta["market"] else 0
        extra = f", {months} months of prices" if months else ""
        print(f" {meta['date']}, {len(live)} nations{extra}")
    return meta, live


def accepted_cultures_of(nat):
    """The primary culture plus every accepted one, as a set."""
    accepted = set(nat["accepted_cultures"])
    if nat["primary_culture"]:
        accepted.add(nat["primary_culture"])
    return accepted


def mobilization_clusters(nat, mob_types=MOBILIZABLE_TYPES,
                          include_occupied=False):
    """
    The manpower buckets a mobilization ceiling is counted over.

    Eligibility follows the engine: poor-strata pops that are neither soldiers
    nor slaves, of the primary or an accepted culture, in provinces that are
    neither colonial nor under enemy control.

    Returns (buckets, pool, entries), where buckets is a list of
    (province, state, poptype, size). The province and state travel with each
    bucket because the counting rule hands whatever a bucket cannot turn into
    a regiment up to them.
    """
    accepted = accepted_cultures_of(nat)
    colonial = nat["colonial_provinces"]
    occupied = set() if include_occupied else nat["occupied_provinces"]
    states = nat["province_state"]
    grouped = defaultdict(int)
    where = {}
    pool = 0
    entries = 0
    for index, entry in enumerate(nat["mobilizable_pops"]):
        poptype, culture, size, province_id = entry
        if poptype not in mob_types or culture not in accepted:
            continue
        if province_id in colonial or province_id in occupied:
            continue
        pool += size
        entries += 1
        # One bucket per pop, in save order. The engine walks pops, not
        # provinces, and the order is what decides when the pool is flushed.
        grouped[index] += size
        where[index] = (province_id, states.get(province_id, -1), poptype)
    buckets = [where[k] + (v,) for k, v in grouped.items()]
    return buckets, pool, entries


# Where a bucket's unused manpower goes, in order. Each rung pools what the one
# below it could not use and truncates again.
def brigades_from_clusters(buckets, rate, pop_per_regiment=POP_SIZE_PER_REGIMENT):
    """
    Brigades a nation's mobilizable pops yield, in the order the save lists them.

    The engine carries one pool of manpower too small to have raised a regiment
    yet. A pop big enough to raise regiments on its own raises them and EMPTIES
    that pool; a pop too small adds to it, and the pool yields a regiment and
    empties whenever it reaches the cost. That flush is why nations whose big
    and small pops interleave -- which is what cultural variety produces --
    mobilize worse than their population suggests, and it is why `buckets` must
    stay in save order.

    Measured against 139 controlled readings from a purpose-built test bed and
    57 in-game campaign readings; the only constant is POP_SIZE_PER_REGIMENT.
    """
    total = 0
    pool = 0.0
    for _province, _state, _poptype, size in buckets:
        manpower = size * rate
        if manpower <= 0:
            continue
        if manpower >= pop_per_regiment:
            total += int(manpower // pop_per_regiment)
            pool = 0.0
        else:
            pool += manpower
            if pool >= pop_per_regiment:
                total += 1
                pool = 0.0
    return total


def _parser_fingerprint():
    """
    A hash of the code that does the parsing.

    The cache stores what a save was turned into, not the save, so it has to
    expire the moment that translation changes. Hashing the two modules that do
    it means editing either one invalidates every entry automatically, which is
    the only version counter nobody forgets to bump.
    """
    digest = hashlib.md5()
    if getattr(sys, "frozen", False):
        # In the packaged exe the modules live inside the archive rather than on
        # disk, so the build itself is the version: one executable, one parser.
        try:
            stat = os.stat(sys.executable)
        except OSError:
            return ""
        digest.update(f"{sys.executable}|{stat.st_size}|{int(stat.st_mtime)}"
                      .encode("utf-8"))
        return digest.hexdigest()[:10]
    for module in (__file__, v2parse.__file__):
        try:
            with open(module, "rb") as fh:
                digest.update(fh.read())
        except OSError:
            return ""
    return digest.hexdigest()[:10]


def mod_fingerprint(mod_path, pop_types, reform_keys=()):
    """
    What the mod changes about parsing, as a short string.

    A save is not read the same way under every mod. `register_pop_types` adds
    the mod's own pop types to the set the province reader keeps, so the same
    file parsed under two mods yields two different results -- and the cache,
    keyed only by the file, would hand the second run the first one's answer.
    Naming the mod and the pop types it registered keeps those apart.
    """
    if not mod_path:
        return "no-mod"
    return hashlib.md5(
        (os.path.abspath(mod_path) + "|" + ",".join(sorted(pop_types))
         + "|" + ",".join(sorted(reform_keys)))
        .encode("utf-8")).hexdigest()[:10]


def _cache_slot(path, fingerprint, world="no-mod"):
    """Where this save's parsed form lives, keyed by the file, the parser and
    the mod it is being read under."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = hashlib.md5(
        f"{os.path.abspath(path)}|{stat.st_size}|{int(stat.st_mtime)}"
        f"|{fingerprint}|{world}".encode("utf-8")).hexdigest()
    folder = os.path.join(tempfile.gettempdir(), "vic2_analyzer_cache")
    return os.path.join(folder, key + ".pkl")


def _cache_read(slot):
    """What is in that cache slot, or None if there is nothing usable."""
    if not (slot and os.path.isfile(slot)):
        return None
    try:
        with open(slot, "rb") as fh:
            return pickle.loads(zlib.decompress(fh.read()))
    except Exception:
        return None                   # a bad entry is just a slow read


def _cache_write(slot, meta, nations):
    if not slot:
        return
    try:
        os.makedirs(os.path.dirname(slot), exist_ok=True)
        with open(slot, "wb") as fh:
            fh.write(zlib.compress(
                pickle.dumps((meta, dict(nations)), protocol=5), 1))
    except Exception:
        pass                          # caching is an optimisation, not a duty


# --- reading a folder of saves across however many cores the machine has -----
#
# Saves do not depend on each other, so the only thing stopping a folder from
# being read all at once is that every worker needs the same two pieces of
# global state the mod sets up: which pop types exist, and which of them can be
# mobilized. Windows starts workers with a fresh interpreter, so both are passed
# in and applied before the worker touches a save.

def _worker_setup(pop_types, mob_types, reform_keys=()):
    v2parse.register_pop_types(pop_types)
    set_mob_candidates(mob_types)
    set_reform_keys(reform_keys)


def _worker_parse(job):
    """One save, in a worker. Returns the slot so the parent can do the writing
    only once, and plain dicts because a defaultdict of lambdas will not pickle."""
    index, path, slot = job
    meta, nations = analyze_save(path, verbose=False)
    return index, slot, meta, dict(nations)


def _spare_memory():
    """Bytes the machine can spare right now, or None if it will not say."""
    if os.name != "nt":
        try:
            return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, AttributeError, OSError):
            return None
    try:
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _Status()
        status.dwLength = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    except Exception:
        pass
    return None


def worker_count(jobs, biggest_save, asked=None):
    """
    How many saves to read at once.

    Three things bound it. The machine's cores, minus one so the rest of the
    computer stays usable. The number of saves actually left to read, since a
    worker with nothing to do is pure startup cost. And memory: a worker holds
    its whole save as text plus what it builds out of it, which measures at
    roughly three times the file, so on a small machine that is the real
    ceiling -- six workers on eight free gigabytes, whatever the core count
    says. Only 60% of what is free is spent, because the report still has to be
    built afterwards.

    Measured on 38 saves and 32 logical cores: 63s on one, 13s on eight, 8.5s
    on sixteen, 7.3s on twenty-four. It keeps paying past the physical core
    count, just less, and flattens out rather than turning back, so there is no
    ceiling here beyond what the machine itself imposes.
    """
    if asked:
        return max(1, min(asked, jobs))
    cores = max(1, (os.cpu_count() or 1) - 1)
    room = jobs
    spare = _spare_memory()
    if spare:
        room = max(1, int(spare * 0.6) // max(biggest_save * 3, 1))
    return max(1, min(cores, jobs, room))


def parse_saves(files, verbose=True, use_cache=True, world="no-mod",
                pop_types=(), mob_types=(), reform_keys=(), jobs=None):
    """
    Every save in the folder, read in parallel when that is worth doing.

    Cached saves are loaded here rather than in a worker: it costs a few
    milliseconds each and a process started to do it would cost more than it
    saves. Only what is left over is worth spreading out.
    """
    fingerprint = _parser_fingerprint() if use_cache else ""
    slots = [_cache_slot(p, fingerprint, world) if fingerprint else None
             for p in files]

    out = [None] * len(files)
    todo = []
    for i, path in enumerate(files):
        _stop_if_asked()
        held = _cache_read(slots[i])
        if held is not None:
            out[i] = held
            if verbose:
                print(f"  {os.path.basename(path)} ... cached, "
                      f"{held[0].get('date', '?')}")
        else:
            todo.append(i)

    if not todo:
        return [item for item in out if item is not None]

    biggest = max((os.path.getsize(files[i]) for i in todo), default=0)
    workers = worker_count(len(todo), biggest, jobs)
    if workers > 1:
        try:
            return _parse_parallel(files, out, todo, slots, workers, verbose,
                                   pop_types, mob_types, reform_keys)
        except Cancelled:
            raise                     # asked to stop, not a machine that cannot
        except Exception as exc:
            # A machine that will not start workers still has to read its saves.
            print(f"  reading one at a time ({exc})", file=sys.stderr)

    for i in todo:
        _stop_if_asked()
        try:
            meta, nations = analyze_save(files[i], verbose=verbose)
        except (ValueError, OSError) as exc:
            print(f"  skipped {os.path.basename(files[i])}: {exc}",
                  file=sys.stderr)
            continue
        _cache_write(slots[i], meta, nations)
        out[i] = (meta, nations)
    return [item for item in out if item is not None]


def _parse_parallel(files, out, todo, slots, workers, verbose, pop_types,
                    mob_types, reform_keys=()):
    """
    Read the outstanding saves across several processes.

    Work is submitted one future per save rather than handed to `pool.map`, so
    a cancellation can drop everything that has not started yet. `map` gives no
    handle on the queue, and leaving the pool's context manager would then wait
    politely for all of it -- on a folder of hundreds of saves, a Stop button
    that takes ten minutes to stop.
    """
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    if verbose:
        print(f"Reading {len(todo)} save(s) on {workers} cores.")
    done = 0
    pool = ProcessPoolExecutor(max_workers=workers, initializer=_worker_setup,
                               initargs=(tuple(pop_types), tuple(mob_types),
                                         tuple(reform_keys)))
    try:
        pending = {pool.submit(_worker_parse, (i, files[i], slots[i]))
                   for i in todo}
        while pending:
            _stop_if_asked()
            # A short wait rather than a blocking one, so the Stop button is
            # answered while the workers are busy rather than after.
            ready, pending = wait(pending, timeout=0.25,
                                  return_when=FIRST_COMPLETED)
            for future in ready:
                index, slot, meta, nations = future.result()
                out[index] = (meta, nations)
                _cache_write(slot, meta, nations)
                done += 1
                if verbose:
                    print(f"  [{done}/{len(todo)}] "
                          f"{os.path.basename(files[index])} ... {meta['date']}")
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()
    return [item for item in out if item is not None]


def explain_mob_pool(tag, nat, meta, rate, args):
    """
    Show where a nation's mobilization pool comes from and what it is worth.

    The interesting number is not the ceiling but the gap between the two
    grouping models: they agree exactly when every province holds one pop per
    poor type, and diverge in proportion to how many cultures those pops are
    split across. That gap is the cost of truncating each pop separately.
    """
    mob_types = frozenset(args.mob_types)
    accepted = accepted_cultures_of(nat)
    occ = args.mob_include_occupied
    per_pop, pool, entries = mobilization_clusters(nat, mob_types, occ)
    # The other grouping the engine might have used: one bucket per province
    # and pop type rather than one per pop. It is not an option any anymore --
    # the engine groups per pop -- but the gap between the two is the whole
    # point of this readout, so it is rebuilt here from the same buckets.
    merged, first = defaultdict(int), {}
    for province, state, poptype, size in per_pop:
        key = (province, poptype)
        first.setdefault(key, (province, state, poptype))
        merged[key] += size
    per_pt = [first[k] + (v,) for k, v in merged.items()]

    dropped = defaultdict(int)
    # Pops of a culture the nation does not accept are dropped as the save is
    # read, so what they came to is carried as a total rather than recounted.
    if nat.get("mob_excluded_culture"):
        dropped["non-accepted culture"] += nat["mob_excluded_culture"]
    for poptype, culture, size, province_id in nat["mobilizable_pops"]:
        if poptype not in mob_types:
            continue
        if culture not in accepted:
            dropped["non-accepted culture"] += size
        elif not occ and province_id in nat["occupied_provinces"]:
            dropped["occupied province"] += size
        elif province_id in nat["colonial_provinces"]:
            dropped["colonial province"] += size

    print(f"\nMobilization pool for {tag} at {meta['date']} "
          f"({os.path.basename(meta['file'])})")
    print(f"  primary culture   {nat['primary_culture']}")
    print(f"  accepted cultures {' '.join(sorted(nat['accepted_cultures'])) or '(none)'}")
    print(f"  pop types counted {' '.join(sorted(mob_types))}")
    print(f"  mobilisation size {rate * 100:.2f}%   "
          f"POP_SIZE_PER_REGIMENT {args.pop_per_regiment}")
    print(f"\n  eligible population   {pool:>12,} in {entries} pop entries, "
          f"{len(per_pt)} province/type slots")
    if entries:
        print(f"  cultural split        {entries / max(1, len(per_pt)):.2f} pop "
              f"entries per province/type slot")
    for reason, size in sorted(dropped.items(), key=lambda kv: -kv[1]):
        print(f"  excluded: {reason:<20} {size:>12,}")

    per_pop_n = brigades_from_clusters(per_pop, rate, args.pop_per_regiment)
    per_pt_n = brigades_from_clusters(per_pt, rate, args.pop_per_regiment)
    untruncated = pool * rate / args.pop_per_regiment
    print(f"\n  ceiling, grouped per pop               {per_pop_n:>6}")
    print(f"  ceiling, grouped per province and type {per_pt_n:>6}"
          f"   ({'+' if per_pt_n >= per_pop_n else ''}{per_pt_n - per_pop_n})")
    print(f"  no truncation at all                   {untruncated:>6.0f}")
    print(f"  standing brigades                      {nat['brigades']:>6}"
          f"  ({nat['mobilized_brigades']} of them mobilized, "
          f"{nat['mobilizing']} queued)")
    print("\n  Compare the two ceilings against the in-game military panel.")

    biggest = sorted(per_pt, key=lambda b: -b[3])[:10]
    if biggest:
        print("\n  largest province/type slots")
        print(f"    {'prov':>6} {'manpower':>10} {'brigades':>8}")
        for province_id, _state, _type, size in biggest:
            print(f"    {province_id:>6} {size * rate:>10,.0f} "
                  f"{int(size * rate // args.pop_per_regiment):>8}")


def save_world(meta, mod):
    """
    What one save says about everybody, for the triggers that ask.

    A triggered modifier can turn on the year, on whether a country is a great
    power, on whether it is at war, or on who owns a particular province --
    none of which is a property of the country block itself. This gathers the
    four of them once per save rather than once per nation.
    """
    order = (mod or {}).get("country_order") or []
    powers = {order[i - 1] for i in meta.get("great_nations", ())
              if 0 < i <= len(order)}
    at_war = set()
    for war in meta.get("wars", ()):
        if not war.get("active"):
            continue
        at_war.update(war.get("attackers", ()))
        at_war.update(war.get("defenders", ()))
    year = 0
    date = meta.get("date") or ""
    if date.split(".")[0].isdigit():
        year = int(date.split(".")[0])
    return {
        "year": year,
        "great_powers": frozenset(powers),
        "at_war": frozenset(at_war),
        "owner": meta.get("province_owner") or {},
    }


def save_sort_key(path, meta_date):
    """Sort by in-game date when we have it, filename otherwise."""
    parts = meta_date.split(".")
    try:
        return (0, int(parts[0]), int(parts[1]), int(parts[2]))
    except (IndexError, ValueError):
        return (1, 0, 0, 0)


def finalize(nat, rate=1.0, pop_per_regiment=POP_SIZE_PER_REGIMENT,
             mob_types=MOBILIZABLE_TYPES, include_occupied=False, mod=None,
             world=None):
    """Derive the ratios that need the totals first."""
    total = nat["total_pop"]
    accepted_set = accepted_cultures_of(nat)
    primary = nat["primary_culture"]

    accepted_pop = sum(
        size for cul, size in nat["pop_by_culture"].items() if cul in accepted_set
    )
    primary_pop = nat["pop_by_culture"].get(primary, 0)

    buckets, pool_stated, entries = mobilization_clusters(
        nat, mob_types, include_occupied)
    brigades = brigades_from_clusters(buckets, rate, pop_per_regiment)

    out = dict(nat)
    out["mobilization_pool"] = pool_stated
    out["mobilization_pops"] = entries
    # A nation already mobilized has (some of) its ceiling standing in the army
    # or in the queue; only the remainder is still potential. This is what stops
    # mobilized brigades from being counted twice in "total potential".
    # `start_mobilization` limits a mobilization to
    #     floor(max(standing regiments, MIN_MOBILIZE_LIMIT) x (1 + impact))
    # where impact is the ruling party's war policy plus every national modifier
    # that moves mobilization_impact. The save stores the party as a 1-based
    # index into the engine's global party list, which `party_sequence` rebuilds,
    # and stores active event modifiers by name.
    #
    # Both halves are measured against China, whose army is small enough for the
    # cap to bind. 1890: 8 standing, a pro-military party, no modifiers, and the
    # game offers 8 x (1 + 3) = 32 of a 95-brigade ceiling. 1908: 6 standing, the
    # same policy but a communist government carrying totalitarianism_modifier at
    # -0.2, and the game's own tooltip reads "280.0%" and offers
    # floor(6 x 3.8) = 22 of a 1056-brigade ceiling.
    policy = ""
    cap = 0
    if mod:
        table = mod.get("party_sequence") or ()
        index = int(nat.get("ruling_party") or 0) - 1
        if 0 <= index < len(table):
            policy = table[index][3]
        impact = (mod.get("mob_impacts") or {}).get(policy)
        if impact is not None:
            # Event modifiers, which the save lists by name, plus triggered
            # ones, which it does not and which have to be judged from their
            # own triggers.
            from mod_reader import impact_for
            impact += impact_for(nat, mod, world)
            floor_ = int(to_float((mod.get("defines") or {}).get(
                "MIN_MOBILIZE_LIMIT", 3), 3))
            cap = int(max(nat["regular_brigades"], floor_) * (1.0 + impact))
    out["war_policy"] = policy
    out["mobilization_cap"] = cap
    # What the game will actually offer: the pop ceiling, held down by the cap.
    out["mobilization_available"] = min(brigades, cap) if cap else brigades
    # Ceiling minus what is already standing. For a nation that mobilized a
    # while ago this is pop GROWTH since it mobilized, not something the game
    # will let it raise -- Victoria 2 does not top up a mobilization.
    out["mobilization_remaining"] = max(
        0, brigades - nat["mobilized_brigades"] - nat["mobilizing"])
    # `rate` is the country's mobilisation size modifier, which the save does
    # not store, so it is a parameter.
    out["mobilization_brigades"] = brigades
    out["accepted_pop"] = accepted_pop
    out["primary_culture_pop"] = primary_pop
    out["accepted_pct"] = round(100.0 * accepted_pop / total, 2) if total else 0.0
    out["avg_literacy"] = round(nat["literacy_weighted"] / total, 5) if total else 0.0
    out["avg_consciousness"] = round(nat["con_weighted"] / total, 4) if total else 0.0
    out["avg_militancy"] = round(nat["mil_weighted"] / total, 4) if total else 0.0
    # Which pop types sit in which layer is the mod's business, not a
    # constant: GFM and Divergences of Darkness add poor-strata `serfs`, IGoR
    # and Ferrum Mare rich `bankers`. Counted against the vanilla list those
    # people simply vanished -- Ferrum Mare's LCT is 98% bankers and read as a
    # nation of two thousand.
    layers = (mod or {}).get("strata") or {}
    if layers:
        for stratum in STRATA:
            out[f"pop_{stratum}"] = sum(
                size for t, size in nat["pop_by_type"].items()
                if layers.get(t) == stratum)
    else:
        for stratum, types in STRATA.items():
            out[f"pop_{stratum}"] = sum(nat["pop_by_type"].get(t, 0) for t in types)
    # Soldiers in a colonial state support no brigade, so the soldier pops that
    # matter to an army are the ones in stated land. The share is taken against
    # the whole nation, colonies included: a soldier base of five million reads
    # differently under fifty million people than under two hundred.
    colonial = nat["colonial_provinces"]
    stated = sum(size for pid, size in nat["soldiers_at"].items()
                 if pid not in colonial)
    out["soldiers_noncolonial"] = stated
    out["soldiers_noncolonial_pct"] = (
        round(100.0 * stated / total, 3) if total else 0.0)
    return out


BASE_COLUMNS = [
    "date", "year", "tag", "is_player", "primary_culture", "civilized",
    "provinces", "states", "total_pop", "accepted_pop", "accepted_pct",
    "primary_culture_pop", "avg_literacy", "avg_consciousness", "avg_militancy",
    "brigades", "regular_brigades", "mobilized_brigades", "mobilizing",
    "is_mobilized", "armies", "ships", "navies",
    "factory_count", "factory_levels", "ports", "naval_base_levels",
    "max_naval_base", "railroad_levels", "fort_levels",
    "mobilisation_size", "mobilization_pool", "mobilization_pops",
    "mobilization_brigades", "mobilization_cap",
    "mobilization_available", "mobilization_remaining", "war_policy",
    "techs", "army_techs", "navy_techs", "prestige", "infamy", "treasury", "tax_base", "research_points",
    "war_exhaustion", "plurality",
    "pop_poor", "pop_middle", "pop_rich",
    "soldiers_noncolonial", "soldiers_noncolonial_pct",
]


GOOD_CATEGORIES = {
    "military": ["ammunition", "small_arms", "artillery", "canned_food",
                 "barrels", "tanks", "aeroplanes"],
    "raw": ["cattle", "coal", "cotton", "dye", "fish", "fruit", "grain", "iron",
            "oil", "opium", "precious_metal", "rubber", "silk", "sulphur", "tea",
            "timber", "tobacco", "tropical_wood", "wool", "coffee"],
    "industrial": ["cement", "clipper_convoy", "electric_gear", "explosives",
                   "fabric", "fertilizer", "fuel", "glass", "lumber",
                   "machine_parts", "paper", "steamer_convoy", "steel"],
    "consumer": ["automobiles", "furniture", "liquor", "luxury_clothes",
                 "luxury_furniture", "radio", "regular_clothes", "telephones",
                 "wine"],
}
GOOD_CATEGORY = {g: cat for cat, goods in GOOD_CATEGORIES.items() for g in goods}


_DATE_KEYS = {}


def date_key(date):
    """
    Sortable tuple for a `YYYY.M.D` string.

    Remembered, because a campaign holds a few hundred distinct dates and asks
    for their keys a few million times -- once per price reading, per sort
    comparison, per row. Twelve hundred entries is nothing to keep.
    """
    try:
        got = _DATE_KEYS.get(date)
    except TypeError:
        return (0, 0, 0)              # not even hashable, let alone a date
    if got is not None:
        return got
    try:
        got = tuple(int(p) for p in date.split("."))
    except (ValueError, AttributeError):
        got = (0, 0, 0)
    _DATE_KEYS[date] = got
    return got


def merge_prices(parsed):
    """
    Stitch every save's rolling price buffer into one series.

    Buffers from consecutive saves overlap heavily; keyed on (date, good) the
    duplicates collapse, and the result is continuous monthly coverage from the
    earliest buffer to the last save.
    """
    prices = {}
    sources = {}
    for meta, _ in parsed:
        market = meta.get("market")
        if not market:
            continue
        when = date_key(meta["date"])
        for stamp, good, price in market["history"]:
            key = (stamp, good)
            # A later save's buffer is the more settled record of the same month.
            if key not in prices or when >= sources.get(key, (0, 0, 0)):
                prices[key] = price
                sources[key] = when
        # The save's own date carries the live price, which the monthly buffer
        # has not recorded yet.
        for good, price in market["current"].items():
            prices[(meta["date"], good)] = price

    rows = []
    for (stamp, good), price in prices.items():
        rows.append({
            "date": stamp,
            "year": stamp.split(".")[0],
            "good": good,
            "category": GOOD_CATEGORY.get(good, "other"),
            "price": round(price, 5),
        })
    rows.sort(key=lambda r: (date_key(r["date"]), r["good"]))
    return rows


def market_snapshot_rows(parsed):
    """Per-save supply/demand context, which the save only stores for `now`."""
    rows = []
    for meta, _ in parsed:
        market = meta.get("market")
        if not market:
            continue
        snap = market["snapshot"]
        goods = set(market["current"])
        for field in snap.values():
            goods |= set(field)
        for good in sorted(goods):
            rows.append({
                "date": meta["date"],
                "year": meta["date"].split(".")[0],
                "good": good,
                "category": GOOD_CATEGORY.get(good, "other"),
                "price": round(market["current"].get(good, 0.0), 5),
                "world_pool": round(snap["world_pool"].get(good, 0.0), 3),
                "supply": round(snap["supply"].get(good, 0.0), 3),
                "demand": round(snap["demand"].get(good, 0.0), 3),
                "real_demand": round(snap["real_demand"].get(good, 0.0), 3),
                "actual_sold": round(snap["actual_sold"].get(good, 0.0), 3),
                "discovered": int(snap["discovered"].get(good, 0.0) > 0),
            })
    return rows


def _write_csv(path, rows, columns):
    """One CSV, columns picked out of each row dict.

    This is what `csv.DictWriter` does, minus the per-row Python call: handing
    `writerows` a generator lets the C writer pull the rows itself, which is
    worth having when a campaign of monthly autosaves has a few million of them.
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        if rows and isinstance(rows[0], dict):
            writer.writerows([row.get(c, "") for c in columns] for row in rows)
        else:
            # already in column order -- see the row loop in `main`
            writer.writerows(rows)


def write_outputs(rows, ship_rows, pop_rows, culture_rows, price_rows,
                  snapshot_rows, brigade_rows, tech_rows, outdir,
                  pop_columns=None):
    os.makedirs(outdir, exist_ok=True)
    columns = (BASE_COLUMNS + [f"pop_{t}" for t in (pop_columns or POP_TYPE_LIST)]
               + ["accepted_cultures"])

    main_path = os.path.join(outdir, "nations_timeseries.csv")
    _write_csv(main_path, rows, columns)

    paths = [main_path]
    tables = [
        ("prices.csv", price_rows, ["date", "year", "good", "category", "price"]),
        ("market_snapshot.csv", snapshot_rows,
         ["date", "year", "good", "category", "price", "world_pool", "supply",
          "demand", "real_demand", "actual_sold", "discovered"]),
        ("ships_by_type.csv", ship_rows, ["date", "year", "tag", "ship_type", "count"]),
        ("brigades_by_type.csv", brigade_rows,
         ["date", "year", "tag", "regiment_type", "count"]),
        ("technologies.csv", tech_rows,
         ["date", "year", "tag", "technology", "branch", "line"]),
        ("pops_by_type.csv", pop_rows, ["date", "year", "tag", "pop_type", "size"]),
        ("pops_by_culture.csv", culture_rows,
         ["date", "year", "tag", "culture", "size", "accepted"]),
    ]
    for name, data, cols in tables:
        if not data:
            continue
        path = os.path.join(outdir, name)
        _write_csv(path, data, cols)
        paths.append(path)
    return paths


def verify_save(path):
    """
    Cross-check unit counts against an independent brace-tracking scan.

    The analyzer walks structure; this counts `regiment` and `ship` blocks by
    raw nesting and attributes them to whichever top-level country block they
    fall in. If the two disagree, the structured reader is missing a nesting
    the save actually uses.
    """
    text = read_save_text(path)
    truth_reg, truth_ship = defaultdict(int), defaultdict(int)
    depth, current, pending = 0, None, None

    for match in TOKEN_RE.finditer(text):
        tok = match.group()
        if tok == "{":
            depth += 1
            if current:
                if pending == "regiment":
                    truth_reg[current] += 1
                elif pending == "ship":
                    truth_ship[current] += 1
            pending = None
        elif tok == "}":
            depth -= 1
            if depth == 0:
                current = None
        elif tok != "=":
            pending = tok
            if depth == 0 and looks_like_country_tag(unquote(tok)):
                current = unquote(tok)

    _meta, nations = analyze_save(path, verbose=False)

    print(f"\n=== {os.path.basename(path)} ===")
    print(f"{'tag':<6}{'brigades':>10}{'scan':>8}{'diff':>7}"
          f"{'ships':>10}{'scan':>8}{'diff':>7}")
    mismatches = 0
    for tag in sorted(set(truth_reg) | set(truth_ship) | set(nations)):
        nat = nations.get(tag)
        if not nat:
            continue
        got_r, want_r = nat["brigades"], truth_reg.get(tag, 0)
        got_s, want_s = nat["ships"], truth_ship.get(tag, 0)
        if got_r != want_r or got_s != want_s:
            mismatches += 1
            print(f"{tag:<6}{got_r:>10}{want_r:>8}{got_r - want_r:>7}"
                  f"{got_s:>10}{want_s:>8}{got_s - want_s:>7}")
    if mismatches:
        print(f"\n{mismatches} nations disagree. Please report this with the save.")
    else:
        total_r = sum(truth_reg.values())
        total_s = sum(truth_ship.values())
        print(f"All nations agree: {total_r:,} regiments, {total_s:,} ships.")
    print()


def peek_save(path):
    """
    Print the shape of a save: top-level keys, and the keys inside the first
    province and country block. Useful when a mod moves things around and the
    numbers come out wrong or zero.
    """
    text = read_save_text(path)
    tok = Tokens(text)
    top_scalars, top_blocks = [], []
    first_province = first_country = None

    while True:
        t = tok.next()
        if t is None:
            break
        if t in ("}", "{", "="):
            continue
        nxt = tok.next()
        if nxt is None:
            break
        if nxt != "=":
            tok.push(nxt)
            continue
        val = tok.next()
        if val is None:
            break
        key = unquote(t)
        if val == "{":
            if key.isdigit() and first_province is None:
                first_province = (key, parse_block(tok))
            elif looks_like_country_tag(key) and first_country is None:
                first_country = (key, parse_block(tok))
            else:
                if key.isdigit():
                    top_blocks.append("<province>")
                elif looks_like_country_tag(key):
                    top_blocks.append("<country>")
                else:
                    top_blocks.append(key)
                skip_block(tok)
        else:
            top_scalars.append(f"{key}={unquote(val)[:40]}")

    print(f"\n=== {os.path.basename(path)} ===")
    print("\nTop-level scalars:")
    for item in top_scalars[:20]:
        print(f"  {item}")
    seen = []
    for name in top_blocks:
        if name not in seen:
            seen.append(name)
    print(f"\nTop-level blocks ({len(top_blocks)} total, distinct):")
    print("  " + ", ".join(seen[:40]))

    for label, found in (("province", first_province), ("country", first_country)):
        if not found:
            print(f"\nNo {label} block found -- the analyzer will report zeros.")
            continue
        key, block = found
        print(f"\nFirst {label} block ({key}) keys:")
        if isinstance(block, dict):
            for k, v in list(block.items())[:40]:
                kind = ("block" if isinstance(v, dict)
                        else "list" if isinstance(v, list) else "scalar")
                extra = ""
                if label == "province" and k in POP_TYPES:
                    pops = v if isinstance(v, list) else [v]
                    culture, religion = pop_culture(pops[0]) if isinstance(pops[0], dict) else (None, None)
                    extra = f"  <- pop, culture={culture}, religion={religion}"
                print(f"  {k:<24} {kind}{extra}")
    print()



def main():
    ap = argparse.ArgumentParser(
        description="Aggregate Victoria 2 saves from one campaign into per-nation time series.",
    )
    ap.add_argument("saves", help="folder of .v2 saves, or a single .v2 file")
    ap.add_argument("-o", "--out", default="vic2_report", help="output folder")
    ap.add_argument("--tags", nargs="*", help="only keep these country tags")
    ap.add_argument("--mod-path",
                    help="game or mod folder containing technologies/ and "
                         "inventions/. When given, each nation's mobilisation "
                         "size is computed from the mod's own rules and "
                         "--mobilisation-size becomes a fallback only.")
    ap.add_argument("--explain-mob", metavar="TAG",
                    help="print every tech and invention contributing to that "
                         "nation's mobilisation size in the last save, then "
                         "exit. Needs --mod-path.")
    ap.add_argument("--mobilisation-size", type=float, default=1.0,
                    dest="mob_rate",
                    help="mobilisation size modifier, e.g. 0.05 for 5%%. The save "
                         "does not store it; read it off the in-game military "
                         "panel. Default 1.0 reports the absolute ceiling.")
    ap.add_argument("--pop-per-regiment", type=int, default=POP_SIZE_PER_REGIMENT,
                    help="POP_SIZE_PER_REGIMENT from defines.lua (default 3000)")
    ap.add_argument("--mob-types", nargs="*",
                    default=sorted(MOBILIZABLE_TYPES),
                    help="pop types that can mobilize. With --mod-path this "
                         "comes from the mod's poptypes/ strata; the default "
                         "here is what vanilla works out to.")
    ap.add_argument("--mob-include-occupied", action="store_true",
                    help="count provinces the owner has lost control of. The "
                         "engine excludes them, which is the default, but it "
                         "moves nations under siege a lot -- Russia in 1908 "
                         "reads 558 without them and 612 with -- so it is worth "
                         "checking against the game when a nation is at war.")
    ap.add_argument("-j", "--jobs", type=int, default=None, metavar="N",
                    help="how many saves to read at once. The default sizes "
                         "itself to the machine: one worker per core bar one, "
                         "capped by how many saves are left to read and by how "
                         "much memory is free. Pass 1 to read them one at a "
                         "time.")
    ap.add_argument("--no-cache", action="store_true",
                    help="re-read every save instead of reusing what was parsed "
                         "last time. The cache lives in the system temp folder, "
                         "keyed by the save's size and timestamp and by a hash "
                         "of the parsing code, so editing the parser expires it.")
    ap.add_argument("--map-scale", type=int, default=1, metavar="N",
                    help="how far to shrink the province bitmap for the map tab. "
                         "Default 1, the full 5616x2160 map at about 1.4MB, "
                         "which is the sharpest the tab gets and holds up when "
                         "you zoom into a single theatre. 2 halves it to "
                         "2808x1080 for about 660KB, 3 is 410KB, and 5 is 230KB "
                         "and visibly blocky once you zoom.")
    ap.add_argument("--player-nations", nargs="*", metavar="TAG", default=None,
                    help="tags that were run by a human. Some triggered "
                         "modifiers turn on it -- IGoR and GFM both hand a "
                         "human-run UNCIVILIZED nation +2%% mobilisation size, "
                         "and GFM pays a South American player differently "
                         "from a South American AI. Every country a person is "
                         "playing carries human=yes in its own block, so this "
                         "is only needed for a save that does not, and it "
                         "overrides what the save says when given. Pass it "
                         "with no tags to treat everyone as AI.")
    ap.add_argument("--explain-mob-pool", metavar="TAG",
                    help="print the mobilization pool of that nation in the "
                         "last save -- eligible pops, what colonial, occupied "
                         "and non-accepted provinces cost it, and the ceiling "
                         "under both grouping models -- then exit.")
    ap.add_argument("--min-pop", type=int, default=0,
                    help="drop nations below this population")
    ap.add_argument("--no-html", action="store_true", help="skip the HTML report")
    ap.add_argument("--peek", action="store_true",
                    help="print the structure of the first save and exit")
    ap.add_argument("--verify", action="store_true",
                    help="cross-check unit counts against an independent scan")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    saves_path = os.path.expanduser(os.path.expandvars(args.saves))
    if not os.path.exists(saves_path):
        sys.exit(
            f"Path not found: {saves_path}\n"
            f"If you used ~ in PowerShell, try $HOME instead, or give the full "
            f"path starting with C:\\Users\\..."
        )

    if os.path.isdir(saves_path):
        files = sorted(
            os.path.join(saves_path, f)
            for f in os.listdir(saves_path)
            if f.lower().endswith(".v2")
        )
        if not files:
            sys.exit(
                f"No .v2 files in {saves_path}\n"
                f"Point this at the folder that holds your saves, not at a "
                f"single save."
            )
    else:
        files = [saves_path]

    if not files:
        sys.exit(f"No .v2 saves found in {args.saves}")

    if args.peek:
        peek_save(files[0])
        return

    if args.verify:
        for path in files:
            verify_save(path)
        return

    verbose = not args.quiet
    if verbose:
        print(f"Found {len(files)} save(s).")

    # The mod is read before any save, because both the pop types read_province
    # keeps and the defines the counting uses have to be settled up front.
    #
    # Both are set from scratch rather than added to, because the window runs
    # one campaign after another in the same process: a set that only grew
    # carried the last mod's pop types and reform names into the next
    # campaign, which then read them out of saves that have none.
    mod = None
    from v2parse import VANILLA_POP_TYPES, register_pop_types
    register_pop_types(())
    set_reform_keys(())
    if args.mod_path:
        from mod_reader import load_mod
        mod = load_mod(args.mod_path)
        extra = set(mod["pop_types"]) - VANILLA_POP_TYPES
        register_pop_types(mod["pop_types"])
        defines = mod["defines"]
        if "POP_SIZE_PER_REGIMENT" in defines and args.pop_per_regiment == POP_SIZE_PER_REGIMENT:
            args.pop_per_regiment = int(defines["POP_SIZE_PER_REGIMENT"])
        if mod["mob_types"] and args.mob_types == sorted(MOBILIZABLE_TYPES):
            args.mob_types = sorted(mod["mob_types"])
        set_reform_keys(mod["reform_names"])
        if verbose:
            print("defines.lua: POP_SIZE_PER_REGIMENT="
                  f"{args.pop_per_regiment}")
            print(f"poptypes/: mobilizable = {' '.join(args.mob_types)}"
                  + (f"; mod-only pop types read: {' '.join(sorted(extra))}"
                     if extra else ""))

    set_mob_candidates(args.mob_types)

    # Which mod a save is read under changes what comes out of it, so it is part
    # of the cache key. Two campaigns on two mods no longer share entries.
    # Keyed on what the parse will actually use rather than on what the mod
    # declares: they are the same thing only when nothing has leaked in.
    world = mod_fingerprint(args.mod_path, v2parse.POP_TYPES, REFORM_KEYS)

    parsed = parse_saves(files, verbose=verbose, use_cache=not args.no_cache,
                         world=world, pop_types=sorted(v2parse.POP_TYPES),
                         mob_types=args.mob_types,
                         reform_keys=sorted(REFORM_KEYS), jobs=args.jobs)

    if not parsed:
        sys.exit("No saves could be read.")

    parsed.sort(key=lambda item: save_sort_key(item[0]["file"], item[0]["date"]))

    wanted = set(args.tags) if args.tags else None
    live = None
    if mod is not None:
        from mod_reader import (attainable_inventions, index_base_for,
                                unjudged_triggers, validate_indices)
        all_techs = {}
        every_nation = []
        for _meta, _nats in parsed:
            for _tag, _nat in _nats.items():
                all_techs.setdefault(_tag, set()).update(_nat["tech_list"])
                every_nation.append(_nat)
        live = attainable_inventions(mod, all_techs)
        # Saves name each nation's inventions by index. Decoding them is what
        # turns the mobilisation size from "every invention this nation could
        # have" into the ones it actually rolled.
        mod["index_base"] = index_base_for(mod, every_nation)
        if verbose:
            if mod["index_base"] is None:
                print("\nInvention indices could not be decoded from "
                      f"{len(mod['invention_sequence'])} inventions; falling back "
                      "to requirement matching, which overstates unlucky nations.")
            else:
                bad, total = validate_indices(mod, every_nation, mod["index_base"])
                print(f"\nInvention indices decoded against "
                      f"{len(mod['invention_sequence'])} inventions "
                      f"(base {mod['index_base']}): {bad} of {total} nation-invention "
                      f"pairs are unreachable ({bad / total * 100:.1f}%).")
        if verbose:
            rules = mod["invention_rules"]
            print(f"\nMod scan: {mod['tech_count']} techs "
                  f"({len(mod['tech_mob'])} grant mobilisation_size), "
                  f"{len(rules)} inventions grant it "
                  f"({len(live)} obtainable), "
                  f"{len(mod['event_mob'])} event modifiers, "
                  f"{sum(1 for _n, size, _i, _t in mod['triggered_mob'] if size)} "
                  f"triggered modifiers.")
            skipped = unjudged_triggers(mod)
            if skipped:
                print("  triggered modifiers left out, because their trigger "
                      "asks something this cannot answer: "
                      + ", ".join(skipped))
            for t, v in sorted(mod["tech_mob"].items()):
                print(f"  tech       {t:<44} +{v:.3f}")
            for n in sorted(rules):
                mark = "" if n in live else "   (unobtainable)"
                print(f"  invention  {n:<44} +{rules[n]['size']:.3f}{mark}")


    # A nation's mobilizable pops are one entry per pop per province -- eleven
    # thousand of them for a large nation, two megabytes a save -- and the only
    # thing that reads them is `finalize`, which turns them into a handful of
    # numbers. Letting each save drop its own once it has been read is the
    # difference between a campaign of monthly autosaves needing a couple of
    # gigabytes and needing nothing much at all. `--explain-mob-pool` prints the
    # raw list back, so it is the one caller that keeps them.
    keep_pools = bool(args.explain_mob_pool)

    rows, ship_rows, pop_rows, culture_rows = [], [], [], []
    brigade_rows, tech_rows = [], []
    # Ship stats as each nation's own inventions leave them. Nations that
    # researched the same things have the same ships, so the profiles are kept
    # once each and referred to by number rather than repeated per save.
    # The pop types a row has a column for. Frozen at import it was the
    # vanilla twelve, so a mod's own type -- IGoR's bankers, GFM's serfs --
    # was read out of the save, counted into the totals and then dropped on
    # the way to the table.
    pop_columns = sorted(v2parse.POP_TYPES)
    naval_profiles, naval_index, naval_of = [], {}, {}
    # good -> {date: {tag: what it put on the market}}, for the production view.
    supply_by = {}

    for meta, nations in parsed:
        _stop_if_asked()
        date = meta["date"]
        year = date.split(".")[0] if date else ""
        # What this save says about everyone, which is what the triggered
        # modifiers ask about: the year, the great powers, who is at war and
        # who owns what.
        stage = save_world(meta, mod)
        # Who was human. Every country a person is playing carries `human=yes`
        # in its own block, so a multiplayer game names all of its players and
        # not just whoever pressed save. Older saves and some mods write no
        # such marker at all, hence the fall back to the save's own player;
        # --player-nations still overrides both.
        played = {tag for tag, nat in nations.items() if nat.get("human")}
        humans = (set(args.player_nations) if args.player_nations is not None
                  else played if played
                  else {meta["player"]} if meta.get("player") else set())
        for tag, nat in nations.items():
            if wanted and tag not in wanted:
                continue
            if nat["total_pop"] < args.min_pop:
                continue
            nat["is_player"] = (tag in humans)
            if mod is not None:
                from mod_reader import breakdown
                parts = breakdown(nat, mod, live=live, world=stage)
                # A nation can be modified *below* zero -- IGoR's
                # china_mobilization_nerf is -100 -- and the engine floors
                # mobilisation size at zero.
                #
                # An empty contribution list means zero, not "unknown": an
                # uncivilized nation has no technology or invention granting
                # mobilisation size, and in IGoR no national value grants it
                # either, so its rate really is zero. Falling back to the
                # command-line rate here used to hand every uncivilized nation
                # 100%, which the old "uncivilized cannot mobilize" shortcut
                # happened to hide. The fallback belongs to the no-mod path.
                nation_rate = max(0.0, sum(v for _k, _n, v in parts))
            else:
                nation_rate = args.mob_rate
            done = finalize(nat, nation_rate, args.pop_per_regiment,
                            mob_types=frozenset(args.mob_types),
                            include_occupied=args.mob_include_occupied,
                            mod=mod, world=stage)
            if not keep_pools:
                nat["mobilizable_pops"] = ()
            done["mobilisation_size"] = round(nation_rate, 5)
            accepted_set = set(done["accepted_cultures"]) | {done["primary_culture"]}

            row = {
                "date": date,
                "year": year,
                "tag": tag,
                "is_player": int(nat["is_player"]),
                "accepted_cultures": ";".join(sorted(done["accepted_cultures"])),
            }
            for col in BASE_COLUMNS:
                if col in done:
                    row[col] = done[col]
            for ptype in pop_columns:
                row[f"pop_{ptype}"] = done["pop_by_type"].get(ptype, 0)
            rows.append(row)

            # These four tables are the ones a campaign has millions of rows
            # of -- a hundred technologies per nation per save on its own -- so
            # they are tuples in the column order declared in `write_outputs`
            # rather than dicts. A dict per row costs about twice the memory
            # and names the same six columns over and over.
            for stype, count in sorted(done["ships_by_type"].items()):
                ship_rows.append((date, year, tag, stype, count))
            if mod is not None and done["ships"]:
                from mod_reader import naval_profile
                profile = naval_profile(done, mod)
                key = json.dumps(profile, sort_keys=True)
                if key not in naval_index:
                    naval_index[key] = len(naval_profiles)
                    naval_profiles.append(profile)
                naval_of.setdefault(tag, {})[date] = naval_index[key]
            for good, amount in done["goods_supply"].items():
                supply_by.setdefault(good, {}).setdefault(date, {})[tag] = amount
            for rtype, count in sorted(done["regiments_by_type"].items()):
                brigade_rows.append((date, year, tag, rtype, count))
            for tech in sorted(done["tech_list"]):
                branch, line, _pos = TECH_GROUP.get(tech, ("other", "Other", 0))
                tech_rows.append((date, year, tag, tech, branch, line))
            for ptype, size in sorted(done["pop_by_type"].items()):
                pop_rows.append((date, year, tag, ptype, size))
            for culture, size in sorted(done["pop_by_culture"].items(),
                                        key=lambda kv: -kv[1]):
                culture_rows.append((date, year, tag, culture, size,
                                     int(culture in accepted_set)))

    if args.explain_mob_pool:
        tag = args.explain_mob_pool.upper()
        meta, nations = parsed[-1]
        nat = nations.get(tag)
        if nat is None:
            sys.exit(f"{tag} is not in {meta['file']}.")
        if mod is not None:
            from mod_reader import rate_for
            rate = rate_for(nat, mod, live=live,
                            world=save_world(meta, mod)) or args.mob_rate
        else:
            rate = args.mob_rate
        explain_mob_pool(tag, nat, meta, rate, args)
        return

    if args.explain_mob:
        if mod is None:
            sys.exit("--explain-mob needs --mod-path.")
        from mod_reader import breakdown
        tag = args.explain_mob.upper()
        meta, nations = parsed[-1]
        nat = nations.get(tag)
        if nat is None:
            sys.exit(f"{tag} is not in {meta['file']}.")
        parts = breakdown(nat, mod, live=live, world=save_world(meta, mod))
        print(f"\nMobilisation size for {tag} at {meta['date']}:")
        total = 0.0
        for kind, name, value in sorted(parts, key=lambda p: (p[0], -p[2])):
            total += value
            print(f"  {kind:<19}{name:<46} {value * 100:+.2f}%")
        print(f"  {'':<19}{'TOTAL':<46} {total * 100:>6.2f}%")
        print(f"\n{tag} has {len(nat['tech_list'])} techs and "
              f"{len(nat['invention_ids'])} active inventions; "
              f"{len(parts)} sources grant it mobilisation size.")
        from mod_reader import unjudged_triggers
        skipped = unjudged_triggers(mod)
        if skipped:
            print(f"Left out, because their trigger asks something this "
                  f"cannot answer: {', '.join(skipped)}.")
        print(f"Invention indices in save run "
              f"{min(nat['invention_ids'], default=0)}..{max(nat['invention_ids'], default=0)}; "
              f"the mod defines {len(mod['invention_sequence'])} inventions, "
              f"{mod['invention_count']} of which grant mobilisation size.")
        return

    # Each save carries the whole war history up to its date, so a campaign
    # holds one overlapping copy per save -- fifty megabytes over thirty-eight
    # saves, and near two gigabytes over twelve hundred monthly ones. Folded
    # into one book here, the saves can drop their lists straight away.
    from report import merge_wars
    war_book = merge_wars(parsed)
    for _meta, _n in parsed:
        _meta["wars"] = ()

    price_rows = merge_prices(parsed)
    snapshot_rows = market_snapshot_rows(parsed)
    paths = write_outputs(rows, ship_rows, pop_rows, culture_rows,
                          price_rows, snapshot_rows, brigade_rows, tech_rows,
                          args.out, pop_columns)

    if not args.no_html:
        from report import (build_map, build_report, build_succession,
                            build_wars)
        # Country names come from the mod's own localisation, which is where the
        # game gets them: a bare TAG, overridden by TAG_<government> when one
        # exists -- IGoR's PBC is "Peru-Bolivia" but "Andine Federation" while
        # it is a democracy. Saves are walked in order so the name reflects the
        # government the nation ended the series with. Without --mod-path there
        # is nothing to read and tags stand in for names.
        report_names = {}
        if mod is not None and mod.get("localisation"):
            from mod_reader import name_for
            loc = mod["localisation"]
            for _meta, _nations in parsed:
                for _tag, _nat in _nations.items():
                    report_names[_tag] = name_for(
                        _tag, str(_nat.get("government") or ""), loc)
        # The map needs the mod's province bitmap; without --mod-path the tab
        # is dropped rather than shown empty.
        map_data = build_map(mod, parsed, args.map_scale) if mod else None
        if map_data and map_data.get("derived") and not args.quiet:
            print(f"map/positions.txt anchors no army counter for "
                  f"{map_data['derived']} of the provinces holding troops; "
                  f"those markers sit at the middle of the province instead.")
        # The save ranks the great powers itself, as 1-based indices into the
        # country array common/countries.txt defines, so the mod is needed to
        # turn them back into tags.
        order = (mod or {}).get("country_order") or []
        great_powers = {}
        flags = {}
        if order:
            from mod_reader import (flag_images, flag_suffixes,
                                    government_flag_types)
            styles = government_flag_types(mod["path"])
            for meta_i, nations_i in parsed:
                picks = [order[i - 1] for i in meta_i.get("great_nations", ())
                         if 0 < i <= len(order)]
                if not picks:
                    continue
                row = []
                for tag in picks:
                    gov = str((nations_i.get(tag) or {}).get("government") or "")
                    # One flag per tag and flag variant, so a nation that turns
                    # communist mid-campaign flies both in turn without the
                    # image being stored twice. The suffix that will actually be
                    # used is the discriminator, since two governments can share
                    # a flagType and still fly different flags.
                    key = tag + "|" + (flag_suffixes(gov, styles)[0] or "base")
                    if key not in flags:
                        got = flag_images(mod["path"], [tag], {tag: gov})
                        if tag in got:
                            flags[key] = got[tag]
                    row.append([tag, key])
                great_powers[meta_i.get("date") or ""] = row
            # Battle tables name a lot of nations that never made great power,
            # and a flag beside the tag reads faster than a tag alone. These
            # take the plain national flag rather than a government variant.
            fighters = set()
            for war in war_book["wars"].values():
                fighters.update(war["attackers"])
                fighters.update(war["defenders"])
                for b in war["battles"].values():
                    for who in (b.get("attacker"), b.get("defender")):
                        if who and who.get("country"):
                            fighters.add(who["country"])
            for tag in sorted(t for t in fighters if t and t != "---"):
                if tag + "|" not in flags:
                    got = flag_images(mod["path"], [tag], {})
                    if tag in got:
                        flags[tag + "|"] = got[tag]
        html_path = build_report(
            rows, ship_rows, pop_rows, culture_rows, price_rows, snapshot_rows,
            brigade_rows, tech_rows, args.out,
            tag_names=report_names,
            map_data=map_data,
            base_prices=(mod or {}).get("base_prices"),
            great_powers=great_powers,
            flags=flags,
            technology=(mod or {}).get("technology"),
            wars=build_wars(parsed, (mod or {}).get("province_names"),
                            (mod or {}).get("province_regions"),
                            (mod or {}).get("state_names"),
                            (mod or {}).get("unit_kinds"), book=war_book),
            succession=build_succession(parsed,
                                        (mod or {}).get("formations")),
            culture_names=(mod or {}).get("culture_names"),
            display_names=(mod or {}).get("display_names"),
            naval={"profiles": naval_profiles, "of": naval_of,
                   "exact": (mod or {}).get("index_base") is not None}
                  if naval_profiles else None,
            supply=supply_by,
        )
        paths.insert(0, html_path)

    if verbose:
        print(f"\n{len(rows)} nation-rows across {len(parsed)} saves.")
        if price_rows:
            months = sorted({r["date"] for r in price_rows}, key=date_key)
            print(f"{len(months)} dated price points, "
                  f"{months[0]} to {months[-1]}, "
                  f"{len({r['good'] for r in price_rows})} goods.")
        latest_date, latest = parsed[-1]
        keep = {
            tag: nat for tag, nat in latest.items()
            if (not wanted or tag in wanted) and nat["total_pop"] >= args.min_pop
        }
        top = sorted(keep.items(), key=lambda kv: -kv[1]["total_pop"])[:8]
        print(f"\nLargest nations at {latest_date['date']}:")
        print(f"  {'tag':<5}{'pop':>12}{'accept%':>9}{'lit':>7}{'brig':>7}{'ships':>7}")
        stage = save_world(latest_date, mod)
        for tag, nat in top:
            if mod is not None:
                from mod_reader import rate_for
                # Zero is an answer, not a gap: an uncivilized nation with no
                # technology granting mobilisation size really does mobilize
                # nobody, and falling back to --mobilisation-size here handed
                # it 100% and disagreed with the table this same run wrote.
                nation_rate = rate_for(nat, mod, live=live, world=stage)
            else:
                nation_rate = args.mob_rate
            done = finalize(nat, nation_rate, args.pop_per_regiment,
                            frozenset(args.mob_types), mod=mod, world=stage)
            done["mobilisation_size"] = round(nation_rate, 5)
            print(f"  {tag:<5}{done['total_pop']:>12,}{done['accepted_pct']:>9.1f}"
                  f"{done['avg_literacy'] * 100:>6.1f}%{done['brigades']:>7}"
                  f"{done['ships']:>7}")
        if mod is not None:
            from mod_reader import rate_for
            latest_meta, latest_nations = parsed[-1]
            shown = sorted(latest_nations.items(),
                           key=lambda kv: -kv[1]["total_pop"])[:10]
            print(f"\nComputed mobilisation sizes at {latest_meta['date']} "
                  f"(check these against the in-game military panel):")
            stage = save_world(latest_meta, mod)
            for tag, nat in shown:
                print(f"  {tag}: "
                      f"{rate_for(nat, mod, live=live, world=stage) * 100:.2f}%")
        print("\nWrote:")
        for path in paths:
            print(f"  {path}")


if __name__ == "__main__":
    # A worker on Windows starts by re-running this file, and without this it
    # would run the whole analysis again instead of waiting for a job.
    import multiprocessing
    multiprocessing.freeze_support()
    main()

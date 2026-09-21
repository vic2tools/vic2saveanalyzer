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
Turning one Victoria 2 save into numbers.

`analyze_save` is the whole of it from the outside: a path in, and
`(what the save says about the world, {tag: what it says about that nation})`
out. Everything else here is a piece of that -- the province blocks and every
pop in them, the country blocks, the wars, the market -- and the rules are
the game's, which is why several of them look strange. A pop's culture is
found by elimination because that is how the game writes it. Sizes are
truncated rather than rounded because `int(float(x))` is what the engine
does. Where a rule looks odd there is a comment saying which save taught it.

None of this knows about caching, workers, reports or the command line. It
reads a file and says what is in it. `scanner/` reads the provinces and the
countries far faster when it has been built, and `fastscan` folds what it
sends into exactly the structures this would have filled, so the two are
held to each other field by field by `testkit/parity.py`.
"""

import os
import re
from collections import Counter, defaultdict

import v2parse
from v2parse import (
    BLOCK,
    HEAD_SCALAR,
    POP_KNOWN_FIELDS,
    POP_TYPES,
    PROVINCE_FIELDS,
    Tokens,
    as_list,
    looks_like_country_tag,
    parse_block,
    pop_culture,
    read_pop,
    scan_entries,
    to_float,
    to_int,
    top_level_blocks,
    unquote,
    walk_entries,
)
from tech_groups import ARMY_TECHS, NAVY_TECHS



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


# Below this share of its life needs a pop is losing people, and not slowly.
# Measured rather than chosen: 144 consecutive monthly saves of one session,
# 2.2 million pop-to-pop comparisons, each pop matched by id across a month.
# A pop getting nothing shrinks by a median 0.448% a month and 77% of them
# shrink at all, against 0.000% and 25% for a pop with its needs met -- and
# the 25% is the floor that promotion and migration alone produce. The drop
# is a cliff at the bottom rather than a slope: every band above 0.1 has a
# median of 0.000%, while everything below 0.05 is between -0.07% and
# -0.45%. So the line sits just above zero, which also keeps a pop written
# as 0.00100 on the same side of it as one written as 0.
STARVING_BELOW = 0.05


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
        # Per ship type, the sum over its hulls of `strength / (1 - experience)`
        # -- the two terms of the damage formula that differ between two real
        # fleets. It equals the hull count for a fresh, green navy, falls with
        # damage and rises with veterancy, and multiplying it by the type's
        # power level gives what those hulls are worth as they stand.
        "ship_crew": defaultdict(float),
        "regiments_by_type": defaultdict(int),
        "regiment_pops": [],
        # province id -> {unit type: brigades}, for the deployment map
        "units_at": defaultdict(Counter),
        # The men standing in each province, by unit type. A regiment writes
        # its `strength` in thousands -- a full one at POP_SIZE_PER_REGIMENT
        # 3000 reads 3.000, and one that has taken 400 casualties reads
        # 2.600 -- so counting regiments says a stack is the same size the
        # day after a battle as the day before it. Ships use a different
        # scale entirely (0 to 100, a percentage) and are not summed here.
        "men_at": defaultdict(Counter),
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
        # People in pops that cannot afford everything they need to live.
        # Not the same as starving to death -- a pop short of its life needs
        # shrinks, migrates and grows militant -- but it is the line under
        # which a population is in trouble.
        "life_unmet": 0,
        # And the sharper reading: pops at or near nothing, which are the
        # ones actually losing people. The two are nothing like the same
        # size -- in one 1836 save 64% of the world is short of something
        # while under 1% is starving -- so which is meant has to be said
        # rather than implied.
        "starving": 0,
        "soldiers_at": defaultdict(int),
        # The cap is a per-pop rule, not a per-province one: two pops of 1000
        # raise two brigades where a single pop of 2000 raises one, so the
        # sizes cannot be added up before the rule is applied to each.
        "soldier_pops_at": defaultdict(list),
        # Which of the nation's provinces it holds a core on, and which of its
        # colonies are protectorates -- the two facts that pick the multiplier.
        "core_provinces": set(),
        "colonial_level": {},
        # A province carries its own `colonial=` beside the `is_colonial` on the
        # state holding it. They agree in ordinary saves -- 498 of 498 in one
        # here, 285 of 288 in another -- but it is the province's own flag the
        # engine charges the multiplier against, measured on a test bed that
        # set only that one. Kept separately rather than folded into
        # `colonial_provinces`, which mobilization and the stated-states
        # literacy were both measured against as they stand.
        "province_colonial": {},
        # Per province, because whether a province is colonial is not known
        # until the country's state blocks are read, and provinces are read
        # first. Same shape as `soldiers_at`, which exists for the same reason.
        "pop_at": defaultdict(int),
        "literacy_at": defaultdict(float),
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

# How much of its life needs a pop is actually getting. The save writes this
# only for a pop that is short: across three saves every recorded value came
# out below 1, and the field is simply absent from a pop that wants for
# nothing. So its presence is the signal and its value is the severity.
_POP_LIFE = 8
_POP_SLOT = {"id": _POP_ID, "size": _POP_SIZE, "money": _POP_MONEY,
             "con": _POP_CON, "mil": _POP_MIL, "literacy": _POP_LITERACY,
             "life_needs": _POP_LIFE}


def _pop_fields(poptype, pop):
    """The same fields, out of a pop block the token reader built."""
    culture, _religion = pop_culture(pop)
    return [poptype, pop.get("id"), pop.get("size"), culture,
            pop.get("money"), pop.get("con"), pop.get("mil"),
            pop.get("literacy"), pop.get("life_needs")]


def read_province(text, at, stop, nations, province_owner_sink,
                  pop_registry=None, province_id=None, owner_map=None,
                  flat=True, world_sink=None):
    """One province block, attributing its pops to the owner."""
    owner = None
    controller = None
    colonial_flag = 0
    cores = set()
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
        # One `groups()` rather than up to six `group(n)` calls. This loop runs
        # about eleven thousand times per province and a million times per
        # save, and the call overhead alone measured a tenth of the parse.
        for m in PROVINCE_FIELDS.finditer(text, at, stop):
            g1, g2, g3, g4, g5, g6 = m.groups()
            key = g1
            if key is not None:                       # a pop's own number
                if current is not None:
                    current[_POP_SLOT[key]] = g2.rstrip()
                continue
            key = g3
            if key is not None:
                # A pop's culture is written as `french=catholic`, with no key
                # of its own, so it is the first field that is neither one of
                # the game's own nor a number -- which is how the token reader
                # found it too, by elimination over the whole block.
                if (current is not None and current[_POP_CULTURE] is None
                        and key not in POP_KNOWN_FIELDS):
                    try:
                        float(g4.rstrip())
                    except ValueError:
                        current[_POP_CULTURE] = key
                continue
            key = g5
            value = g6.strip()
            if value and value[0] != "{":
                current = None
                if key == "owner":
                    owner = unquote(value)
                elif key == "controller":
                    controller = unquote(value)
                elif key == "core":
                    cores.add(unquote(value))
                elif key == "colonial":
                    colonial_flag = to_int(value, 0)
            elif key in POP_TYPES:
                current = [key, None, None, None, None, None, None, None, None]
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
                elif key == "core":
                    cores.add(value)
                elif key == "colonial":
                    colonial_flag = to_int(value, 0)
            elif key in POP_TYPES:
                pops.append(_pop_fields(key, read_pop(Tokens(text, block_at))))
            elif key in ("naval_base", "fort", "railroad"):
                buildings[key] = parse_block(Tokens(text, block_at))

    # Counted before the owner check, because land nobody has colonised yet
    # still holds people and they are still part of the world. In 1836 that is
    # 6.4% of everyone alive, and by 1908 it is none of them -- so a world
    # total summed from nations alone would show the population climbing partly
    # because the map was being carved up, which is not what anyone reading it
    # would take it to mean.
    if world_sink is not None:
        for pop in pops:
            world_sink[0] += to_int(pop[_POP_SIZE])
    if not owner:
        return
    if owner_map is not None and province_id is not None:
        # Both, because the map shades occupied land by whoever holds it while
        # still knowing whose it is.
        owner_map[province_id] = (owner, controller or owner)
    province_owner_sink[owner] += 1
    nat = nations[owner]
    nat["provinces"] += 1
    if province_id is not None and owner in cores:
        nat["core_provinces"].add(province_id)
    if province_id is not None and colonial_flag:
        nat["province_colonial"][province_id] = colonial_flag
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
            nat["soldier_pops_at"][province_id].append(size)
        nat["pop_at"][province_id] += size
        # Absent means the pop wants for nothing; present and short of 1 means
        # it is going without some part of what it needs to live.
        life = pop[_POP_LIFE]
        if life is not None:
            got = to_float(life)
            if got < 1.0:
                nat["life_unmet"] += size
            if got < STARVING_BELOW:
                nat["starving"] += size
        if culture:
            nat["pop_by_culture"][culture] += size
            if poptype in MOB_CANDIDATES:
                nat["mobilizable_pops"].append(
                    (poptype, culture, size, province_id))
        literate = to_float(pop[_POP_LITERACY]) * size
        nat["literacy_weighted"] += literate
        nat["literacy_at"][province_id] += literate
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
                    nat["men_at"][where][rtype or "unknown"] += int(
                        round(to_float(reg.get("strength")) * 1000))
        elif key == "ship":
            for ship in sub_blocks(value):
                nat["ships"] += 1
                kind = str(ship.get("type", "unknown"))
                nat["ships_by_type"][kind] += 1
                # Both are written as percentages. Strength scales the damage a
                # hull deals; experience is subtracted from the damage it takes,
                # so rearranging the duel leaves it as a divisor on its owner's
                # side. A ship missing either reads as fresh and green.
                strength = to_float(ship.get("strength"), 100.0) / 100.0
                experience = to_float(ship.get("experience"), 0.0) / 100.0
                experience = min(0.95, max(0.0, experience))
                nat["ship_crew"][kind] += max(0.0, strength) / (1.0 - experience)
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
                # `is_colonial=1` is a protectorate and `=2` a colony. Both
                # are outside the stated states mobilization draws from, which
                # is all this used to need; the brigade cap charges them
                # different multipliers, so the level is kept as well.
                colonial = "is_colonial" in block
                level = to_int(block.get("is_colonial"), 0) if colonial else 0
                for pid in ids:
                    pid = to_int(pid, -1)
                    nat["province_state"][pid] = ordinal
                    if colonial:
                        nat["colonial_provinces"].add(pid)
                        nat["colonial_level"][pid] = level
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


class _Spans:
    """
    A save on disk, sliced like the bytes of one.

    `raw[at:stop]` reads that span and nothing else, so the loop below does
    not care which of the two it was handed. There is no other way to index
    it, because there is no other way the loop indexes it.
    """

    __slots__ = ("_fh",)

    def __init__(self, path):
        self._fh = v2parse.open_save(path)

    def __getitem__(self, span):
        self._fh.seek(span.start)
        return self._fh.read(span.stop - span.start)

    def close(self):
        self._fh.close()


def analyze_save(path, verbose=True, use_scanner=True):
    """
    Parse one save. Returns (meta, {tag: nation_stats}).

    `use_scanner=False` reads it entirely in Python. That is the fallback
    for a save the scanner half-read: see the retry at the end.
    """
    if verbose:
        print(f"  reading {os.path.basename(path)} ...", end="", flush=True)
    # Set the scanner going first. It answers in two parts: the block table
    # a fifth of the way in, and the provinces and countries at the end. The
    # wars, the market and the great power list are read here, out of the
    # file, and they need only the first part -- so they are read while the
    # scanner is still working rather than after it has finished.
    import fastscan
    running = (fastscan.start(path, v2parse.POP_TYPES, MOB_CANDIDATES,
                              army_techs=ARMY_TECHS, navy_techs=NAVY_TECHS,
                              reform_keys=REFORM_KEYS)
               if use_scanner else None)
    head = fastscan.head(running)

    nations = defaultdict(blank_nation)
    province_counts = defaultdict(int)
    pop_registry = {}
    meta = {"file": os.path.basename(path), "date": "", "player": "", "market": None}
    world_pop = [0]
    province_owner = {}
    great_nations = []
    wars = []
    market_block = None

    # Where every top-level block starts, in one scan. A block runs to the next
    # key, which is all any reader needs, since each stops at its own closing
    # brace and ignores whatever follows. Blocks nothing here reads -- most of
    # the file -- are never looked at at all, which is most of the win: the old
    # walk had to count braces through all 26 MB of them.
    # The scanner reads the provinces and the countries and says where
    # everything else is, so when it works the file is never read here at
    # all: the wars, the market and the great power list are lifted straight
    # off the disk a span at a time. When it does not, the file is read and
    # decoded whole and everything is done the way it always was.
    text = None
    scanned = None
    if head is not None:
        meta["date"] = head["date"]
        meta["player"] = head["player"]
        blocks = head["blocks"]
        flat = True
        raw = _Spans(path)
    else:
        if running is not None:
            running.abandon()
        raw = v2parse.read_save_bytes(path)
        text = raw.decode("latin-1")
        blocks = top_level_blocks(text)
    if head is None:
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

    # The province blocks -- most of the file, and every pop in the game --
    # go to the scanner when it has been built. It reads them in a fifth of
    # the time this does, and what it hands back is folded into exactly the
    # structures the loop below would have filled. When it is not there, or
    # will not take this file, `scanned` is None and nothing changes.
    for key, at, stop in blocks:
        if key.isdigit():
            if head is not None:
                continue              # the scanner is reading it right now
            read_province(text, at, stop, nations, province_counts,
                          pop_registry, province_id=int(key),
                          owner_map=province_owner, flat=flat,
                          world_sink=world_pop)
            continue

        country = looks_like_country_tag(key)
        if country and head is not None:
            continue                  # read by the scanner, never decoded here
        if not (country or key in ("active_war", "previous_war",
                                   "great_nations")
                or (key == "worldmarket" and market_block is None)):
            continue                  # nothing here reads this one

        if head is None:
            body, first, last = text, at, stop
        else:
            # Decoded now, and only this block: most of the file is provinces
            # and never becomes a string at all.
            body = raw[at:stop].decode("latin-1")
            first, last = 0, len(body)

        if country:
            read_country(body, first, last, key, nations, flat=flat)
        elif key in ("active_war", "previous_war"):
            war = read_war(parse_block(Tokens(body, first)),
                           key == "active_war")
            if war:
                wars.append(war)
        elif key == "great_nations":
            # The engine's own great power list, in rank order, as 1-based
            # indices into the country array that common/countries.txt
            # defines. Nothing else in the save ranks nations.
            block = parse_block(Tokens(body, first))
            ids = (block if isinstance(block, list)
                   else block.get("_items", []) if isinstance(block, dict) else [])
            great_nations = [to_int(i, -1) for i in ids]
        else:
            market_block = parse_block(Tokens(body, first))

    # Everything above happened while the scanner was still working. This
    # is where the two meet.
    if head is not None:
        raw.close()
        scanned = fastscan.collect(running)
        if scanned is None or "countries" not in scanned:
            # It started well and then did not finish, or it is an older
            # build that does not send the country blocks. Half a save is
            # not worth keeping, so this one is read again the slow way.
            #
            # Only the second of those is worth a word. A scanner that
            # turns a file down -- a save cut in half, a layout the game
            # does not write -- exits non-zero and is doing its job; a
            # mutated save was enough to make the old warning tell people
            # to rebuild a binary that was working perfectly.
            if not running.refused():
                fastscan.note_unusable()
            return analyze_save(path, verbose=verbose, use_scanner=False)
        fastscan.apply(scanned, nations, province_owner, pop_registry,
                       world_pop, province_counts)
        fastscan.apply_countries(scanned, nations)

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

    meta["world_pop"] = world_pop[0]
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

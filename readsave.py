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

import hashlib
import os
import pickle
from collections import defaultdict, namedtuple

import v2parse
from nation import (COUNTRY_NUMERICS, COUNTRY_SCALARS,
                    MOBILIZABLE_TYPES, accepted_cultures_of,
                    blank_nation)
from v2parse import (
    BLOCK,
    HEAD_SCALAR,
    POP_KNOWN_FIELDS,
    PROVINCE_FIELDS,
    Tokens,
    as_list,
    looks_like_country_tag,
    parse_block,
    parse_span,
    pop_culture,
    read_pop,
    scan_entries,
    to_float,
    to_int,
    top_level_blocks,
    unquote,
    walk_entries,
)
from readwar import read_war
from tech_groups import ARMY_TECHS, NAVY_TECHS


# Strata, for the "who actually holds the wealth" view.
STRATA = {
    "poor": ["farmers", "labourers", "slaves", "soldiers", "craftsmen"],
    "middle": ["artisans", "bureaucrats", "clergymen", "clerks", "officers"],
    "rich": ["aristocrats", "capitalists"],
}


def mod_fingerprint(mod_path, pop_types, reform_keys=(), mob_types=(),
                    population_groups=()):
    """
    What the mod changes about parsing, as a short string.

    A save is not read the same way under every mod. A mod's own pop types
    are read out of the provinces, so the same file read under two mods
    yields two different results -- and the cache, keyed only by the file,
    would hand the second run the first one's answer. Naming the mod and
    everything its reading keeps apart keeps those apart.
    """
    return hashlib.md5(
        ((os.path.abspath(mod_path) if mod_path else "no-mod")
         + "|" + ",".join(sorted(pop_types))
         + "|" + ",".join(sorted(reform_keys))
         + "|" + ",".join(sorted(mob_types))
         + "|" + repr(population_groups))
        .encode("utf-8")).hexdigest()[:10]


class Reading(namedtuple("Reading", "mod_path pop_types mob_types reform_keys population_groups",
                         defaults=((),))):
    """
    How a save is read under a mod, handed to `analyze_save` with the save.

    Pop types, mobilizable types and reform names select the fields read.
    `population_groups` maps provinces to a representative province of each
    geographic region. It lets the POP scan produce state aggregates directly,
    and is included in the cache identity because it changes their grouping.
    Numeric representatives keep region names out of the scanner protocol;
    provinces absent from the lookup remain independent groups.
    """

    __slots__ = ()

    def fingerprint(self):
        """The cache key for a save read this way."""
        return mod_fingerprint(self.mod_path, self.pop_types,
                               self.reform_keys, self.mob_types,
                               self.population_groups)


def reading_for(mod_path, mod, mob_types):
    """
    The reading a mod asks for. `mod` is a loaded mod or None for no mod.

    Sorted tuples rather than sets, because this is pickled to every worker
    and hashed into the cache key, and a set is neither ordered nor ordered
    the same way twice.
    """
    named = (mod.pop_types if mod else None) or ()
    # A numeric representative keeps region names out of the scanner protocol.
    # The map's regions can differ from the state's records in a save, so use
    # the same geographic grouping as the report, with one-province fallbacks.
    regions = (getattr(mod, "province_regions", None) if mod else None) or {}
    representatives = {}
    groups = []
    for pid, region in sorted(regions.items()):
        if region:
            groups.append((pid, representatives.setdefault(str(region), pid)))
    return Reading(
        mod_path=mod_path,
        pop_types=tuple(sorted(v2parse.VANILLA_POP_TYPES
                               | {n for n in named if n})),
        mob_types=tuple(sorted(mob_types)),
        reform_keys=tuple(sorted((mod.reform_names if mod else None) or ())),
        population_groups=tuple(groups))


# No mod: the twelve pop types the game ships and the three that can
# mobilize. What a run with no --mod-path reads a save under.
PLAIN = reading_for(None, None, MOBILIZABLE_TYPES)


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


def read_province(text, at, stop, found, province_id, flat, pop_types,
                  mob_types):
    """
    One province block, into `found`: its pops to the owner's record, and
    its owner, its pop ids and its people to the save's own bookkeeping.
    `pop_types` and `mob_types` are the reading's, as sets.
    """
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
            elif key in pop_types:
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
            elif key in pop_types:
                pops.append(_pop_fields(key, read_pop(Tokens(text, block_at))))
            elif key in ("naval_base", "fort", "railroad"):
                buildings[key] = parse_block(Tokens(text, block_at))

    # Counted before the owner check, because land nobody has colonised yet
    # still holds people and they are still part of the world. In 1836 that is
    # 6.4% of everyone alive, and by 1908 it is none of them -- so a world
    # total summed from nations alone would show the population climbing partly
    # because the map was being carved up, which is not what anyone reading it
    # would take it to mean.
    found.world_pop += sum(to_int(pop[_POP_SIZE]) for pop in pops)
    if not owner:
        return
    # Both, because the map shades occupied land by whoever holds it while
    # still knowing whose it is.
    found.province_owner[province_id] = (owner, controller or owner)
    if owner not in found.nations and owner in found.countries:
        found.nations[owner] = found.countries.pop(owner)
    nat = found.nations[owner]
    nat["provinces"] += 1
    if owner in cores:
        nat["core_provinces"].add(province_id)
    if colonial_flag:
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

    pop_registry = found.pop_registry
    accepted = accepted_cultures_of(nat)
    home = province_id not in nat["colonial_provinces"]
    group = found.population_groups.get(province_id, province_id)
    row = None
    province_pop = 0
    province_literate = 0.0
    for pop in pops:
        poptype = pop[_POP_TYPE]
        if pop[_POP_ID] is not None:
            pop_id = to_int(pop[_POP_ID], -1)
            if pop_id in found.referenced_pops:
                pop_registry[pop_id] = poptype
        size = to_int(pop[_POP_SIZE])
        if size <= 0:
            continue
        culture = pop[_POP_CULTURE]
        nat["total_pop"] += size
        nat["pop_by_type"][poptype] += size
        if poptype == "soldiers":
            if home:
                nat["soldiers_noncolonial"] += size
            nat["soldier_pops_at"][province_id].append(size)
        if row is None:
            row = nat["population_by_state"].get(group)
            if row is None:
                row = nat["population_by_state"][group] = [0, 0.0, {}, {}, 0]
            row[4] += 1
        province_pop += size
        for slot, key in ((2, poptype), (3, culture)):
            if key:
                counts = row[slot]
                counts[key] = counts.get(key, 0) + size
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
            if poptype in mob_types:
                if culture in accepted:
                    nat["mobilizable_pops"].append(
                        (poptype, culture, size, province_id))
                else:
                    nat["mob_excluded_culture"] += size
        literate = to_float(pop[_POP_LITERACY]) * size
        nat["literacy_weighted"] += literate
        province_literate += literate
        nat["con_weighted"] += to_float(pop[_POP_CON]) * size
        nat["mil_weighted"] += to_float(pop[_POP_MIL]) * size
        nat["money_total"] += to_float(pop[_POP_MONEY])
    if row is not None:
        row[0] += province_pop
        row[1] += province_literate
    if home:
        nat["pop_noncolonial"] += province_pop
        nat["literacy_noncolonial"] += province_literate


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


# Blocks inside a country that are built and then never looked at. A state
# lists every employed pop of every factory under `employment`, which is most of
# the block by size; an `id` sub-block is the engine's own handle on a thing and
# says nothing about it; a `leader` is a handle too. `pop` is not in either list
# and must not be, because a regiment's pop is how a brigade is told from a
# mobilized one.
_STATE_SKIP = frozenset(("employment", "stockpile", "id"))
_UNIT_SKIP = frozenset(("id", "leader"))


def read_country(text, at, stop, tag, nations, flat=True, *, reform_keys):
    """One country block. `reform_keys` is the reading's, as a set."""
    nat = nations[tag]
    nat["tag"] = tag
    # Declared beside the record in `nation`, and bound to a local because
    # the loop below looks them up per entry. They were two dict literals
    # built afresh for every nation of every save -- and a second copy of
    # what `scanner/src/country.rs` keeps as two `const` arrays, with
    # nothing checking the copies still agreed. `testkit/record.py` does.
    scalars = COUNTRY_SCALARS
    numerics = COUNTRY_NUMERICS

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
            elif key in reform_keys:
                nat["reforms"][key] = unquote(clean)
            elif key in scalars:
                nat[scalars[key]] = clean
            elif key in numerics:
                nat[numerics[key]] = to_float(clean)


class _Found:
    """
    What a save says that is not one nation's own record, gathered as the
    save is read -- by `read_province` block by block, or by
    `fastscan.apply` from the scanner's answer: every nation's record, who
    owns and who holds each province, the type of every pop by its id, and
    how many people the world holds.
    """

    __slots__ = ("nations", "countries", "province_owner", "pop_registry",
                 "world_pop", "referenced_pops", "population_groups")

    def __init__(self):
        self.nations = defaultdict(blank_nation)
        self.countries = defaultdict(blank_nation)
        self.province_owner = {}
        self.pop_registry = {}
        self.world_pop = 0
        self.referenced_pops = set()
        self.population_groups = {}


def _walk_top(text, source):
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
        elif key == "date" and not source.date:
            source.date = value
        elif key == "player" and not source.player:
            source.player = value


class _Spans:
    """
    A save on disk, sliced like the bytes of one: `raw[at:stop]` reads that
    span and nothing else.
    """

    __slots__ = ("_fh",)

    def __init__(self, path):
        self._fh = v2parse.open_save(path)

    def __getitem__(self, span):
        self._fh.seek(span.start)
        return self._fh.read(span.stop - span.start)

    def close(self):
        self._fh.close()


class _Scanned:
    """
    A save the Rust scanner is reading.

    The scanner reads the provinces and the countries, and answers in two
    parts: where every top-level block is, a fifth of the way in, and the
    provinces and countries at the end. Everything else -- the wars, the
    market, the great power list -- is lifted straight off the disk a span
    at a time between the two, so the file is never read whole here and
    most of it never becomes a string at all.
    """

    scanner_reads_nations = True
    flat = True

    def __init__(self, path, running, head):
        self._running = running
        self.date, self.player = head["date"], head["player"]
        self.blocks = head["blocks"]
        try:
            self._raw = _Spans(path)
        except BaseException:
            # Refused -- a save cut short is refused here, after the scanner
            # has already started on it -- so the scanner is let go now
            # rather than whenever its owner happens to be collected.
            running.abandon()
            raise

    def body(self, at, stop):
        """(text, first, last) of one block, decoded on its own."""
        text = self._raw[at:stop].decode("latin-1")
        return text, 0, len(text)

    def finish(self, found):
        """
        Fold the scanner's provinces and countries into `found`, or say
        False when it did not finish -- it started well and stopped, or it
        is an older build that does not send the countries. Half a save is
        not worth keeping, and the caller reads it again the slow way.

        Only the second of those is worth a word. A scanner that turns a
        file down -- a save cut in half, a layout the game does not write
        -- exits non-zero and is doing its job.
        """
        import fastscan
        self._raw.close()
        scanned = fastscan.collect(self._running)
        if scanned is None or "countries" not in scanned:
            if not self._running.refused():
                fastscan.note_unusable()
            return False
        fastscan.apply(scanned, found)
        fastscan.apply_countries(scanned, found.nations)
        return True


class _Whole:
    """
    A save read and decoded whole, every block of it read here.

    Where every top-level block starts is found in one scan. A block runs to
    the next key, which is all any reader needs, since each stops at its own
    closing brace and ignores whatever follows; blocks nothing here reads
    are never looked at. A save laid out some other way than the game lays
    it out -- `top_level_blocks` says None -- is walked token by token.
    """

    scanner_reads_nations = False

    def __init__(self, path):
        self.text = text = v2parse.read_save_bytes(path).decode("latin-1")
        self.date = self.player = ""
        blocks = top_level_blocks(text)
        self.flat = blocks is not None
        if not self.flat:
            self.blocks = _walk_top(text, self)
            return
        self.blocks = blocks
        # `date` and `player` are top-level scalars, and every top-level
        # scalar is written above the first block.
        for m in HEAD_SCALAR.finditer(text, 0, blocks[0][1]):
            key = m.group(1)
            if key == "date" and not self.date:
                self.date = unquote(m.group(2).strip())
            elif key == "player" and not self.player:
                self.player = unquote(m.group(2).strip())

    def body(self, at, stop):
        """(text, first, last) of one block: the whole text, and its span."""
        return self.text, at, stop

    def finish(self, found):
        return True


def _open(path, reading, use_scanner):
    """
    The save, as the scanner is reading it or as a whole text.

    The scanner is set going first, because the wars, the market and the
    great power list need only the first part of its answer and are read
    here while it is still working on the rest.
    """
    import fastscan
    running = (fastscan.start(path, reading.pop_types, reading.mob_types,
                              army_techs=ARMY_TECHS, navy_techs=NAVY_TECHS,
                              reform_keys=reading.reform_keys,
                              population_groups=reading.population_groups)
               if use_scanner else None)
    head = fastscan.head(running)
    if head is not None:
        return _Scanned(path, running, head)
    if running is not None:
        running.abandon()
    return _Whole(path)


def _settle(nations, pop_registry):
    """
    Classify regiments using only the POP IDs the country blocks referenced.

    Country metadata is read first, but the types of those POPs are not known
    until their provinces have been read. Culture eligibility has already
    been applied during the POP scan, preserving eligible POPs in save order.
    """
    for nat in nations.values():
        for pid in nat["regiment_pops"]:
            poptype = pop_registry.get(pid)
            if poptype is None or poptype == "soldiers":
                nat["regular_brigades"] += 1
            else:
                nat["mobilized_brigades"] += 1
        # The two counts above are the whole reason this list exists, and
        # this is the last line that reads it, so it does not travel any
        # further: not back from the worker, not into the cache, not into
        # the campaign.
        nat["regiment_pops"] = ()


def _changed(path, before):
    """Whether the file is not the one `before` was taken of."""
    if before is None:
        return False
    try:
        after = os.stat(path)
    except OSError:
        return True
    return ((before.st_size, before.st_mtime_ns)
            != (after.st_size, after.st_mtime_ns))


def _changed_twice(path):
    """What a save rewritten under both of two reads is refused with."""
    # Once is bad luck. Twice means the game is writing to it about as fast
    # as this can read it, and a save half from each of two months is worse
    # than no save.
    return ValueError(
        "%s changed while it was being read. It is probably the "
        "file the game is writing to right now; read the copies "
        "the keeper makes instead." % path)


def _say_read(meta, live):
    """The end of the verbose line `analyze_save` starts."""
    months = len({d for d, _, _ in meta["market"]["history"]}) if meta["market"] else 0
    extra = f", {months} months of prices" if months else ""
    print(f" {meta['date']}, {len(live)} nations{extra}")


def _read_record(path, reading, again=False):
    """
    (meta, nations, the pickled pair) as the scanner reads a save whole
    (`fastscan.record`), or None when it will not.

    The pickle is kept for the caller that caches the save, which then
    writes it as it came rather than pickling the pair again; it is None
    where the pair had to be touched here.
    """
    import fastscan
    try:
        before = os.stat(path)
    except OSError:
        before = None
    blob = fastscan.record(path, reading.pop_types, reading.mob_types,
                           army_techs=ARMY_TECHS, navy_techs=NAVY_TECHS,
                           reform_keys=reading.reform_keys,
                           population_groups=reading.population_groups)
    if blob is None:
        return None
    meta, live = pickle.loads(blob)
    if _changed(path, before):
        if again:
            raise _changed_twice(path)
        return _read_record(path, reading, again=True)
    # The scanner names the file as it was asked for it. A name latin-1
    # cannot hold comes back empty, and this one is the analyzer's to say.
    name = os.path.basename(path)
    if meta.get("file") != name:
        meta["file"] = name
        blob = None
    return meta, live, blob


def read_save(path, reading, use_scanner=True):
    """
    `analyze_save`, quietly, with the pickled `(meta, nations)` as a third
    value when the scanner read the save whole -- or None, when it did not
    and the pair was built here.
    """
    if use_scanner:
        got = _read_record(path, reading)
        if got is not None:
            return got
    meta, live = analyze_save(path, reading, verbose=False,
                              use_scanner=use_scanner, record=False)
    return meta, live, None


def analyze_save(path, reading, verbose=True, use_scanner=True, again=False,
                 record=True):
    """
    Parse one save, read the way `reading` says. Returns
    (meta, {tag: nation_stats}).

    With the scanner it is asked for the whole save first (`_read_record`),
    and for its provinces and countries alone, in JSON, when it will not
    give that, the rest read here. `record=False` skips the first, which the
    checks use to hold that second way to the others. `use_scanner=False`
    reads it entirely in Python, which is the fallback for a save the
    scanner half-read. `again=True` marks the one retry allowed when the
    file changed underneath the read; both are set by this function
    calling itself and by nothing else.
    """
    if verbose:
        print(f"  reading {os.path.basename(path)} ...", end="", flush=True)
    if use_scanner and record:
        got = _read_record(path, reading, again)
        if got is not None:
            if verbose:
                _say_read(got[0], got[1])
            return got[0], got[1]
    # What the file looked like before anything touched it, checked again
    # at the end. The scanner reads a save whole and the wars and the market
    # are lifted out of it beside it, so one rewritten in between would be
    # read half from each version and the halves would not agree. The keeper
    # guards its copies the same way, for the same reason: pointing this at
    # the folder the game is still writing to is a thing people do.
    try:
        before = os.stat(path)
    except OSError:
        before = None
    source = _open(path, reading, use_scanner)

    # The reading's three lists as sets, for the readers to test every key
    # against.
    pop_types = frozenset(reading.pop_types)
    mob_types = frozenset(reading.mob_types)
    reform_keys = frozenset(reading.reform_keys)
    found = _Found()
    found.population_groups = dict(reading.population_groups)
    if not source.scanner_reads_nations:
        # Only the block index is traversed twice: country bodies are parsed
        # once, before POPs need their acceptance and colonial metadata.
        source.blocks = list(source.blocks)
        for key, at, stop in source.blocks:
            if looks_like_country_tag(key):
                body, first, last = source.body(at, stop)
                read_country(body, first, last, key, found.countries,
                             flat=source.flat, reform_keys=reform_keys)
        found.referenced_pops = {pid for nat in found.countries.values()
                                 for pid in nat["regiment_pops"]}
    nations = found.nations
    meta = {"file": os.path.basename(path), "date": "", "player": "",
            "market": None}
    great_nations = []
    wars = []
    market_block = None

    for key, at, stop in source.blocks:
        if key.isdigit():
            if not source.scanner_reads_nations:
                text, first, last = source.body(at, stop)
                read_province(text, first, last, found, int(key),
                              source.flat, pop_types, mob_types)
            continue

        country = looks_like_country_tag(key)
        if country:
            continue
        if not (key in ("active_war", "previous_war",
                                   "great_nations")
                or (key == "worldmarket" and market_block is None)):
            continue                  # nothing here reads this one

        body, first, last = source.body(at, stop)
        # A block laid out the game's way ends where its span does, so it
        # is tokenised in one call; one found by walking the tokens (a save
        # some editor reflowed) runs to the end of the file, and is read a
        # token at a time as far as it goes.
        block = (parse_span(body, first, last) if source.flat
                 else parse_block(Tokens(body, first)))
        if key in ("active_war", "previous_war"):
            war = read_war(block, key == "active_war")
            if war:
                wars.append(war)
        elif key == "great_nations":
            # The engine's own great power list, in rank order, as 1-based
            # indices into the country array that common/countries.txt
            # defines. Nothing else in the save ranks nations.
            ids = (block if isinstance(block, list)
                   else block.get("_items", []) if isinstance(block, dict) else [])
            great_nations = [to_int(i, -1) for i in ids]
        else:
            market_block = block

    # Everything above happened while the scanner, if there was one, was
    # still working. This is where the two meet.
    if not source.finish(found):
        return analyze_save(path, reading, verbose=verbose,
                            use_scanner=False, again=again, record=False)

    nations.update(found.countries)

    _settle(nations, found.pop_registry)

    meta["date"], meta["player"] = source.date, source.player
    meta["world_pop"] = found.world_pop
    meta["province_owner"] = found.province_owner
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
    if _changed(path, before):
        if again:
            raise _changed_twice(path)
        return analyze_save(path, reading, verbose=verbose,
                            use_scanner=use_scanner, again=True, record=record)

    if verbose:
        _say_read(meta, live)
    return meta, live

#!/usr/bin/env python3
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
import os
import sys
from collections import Counter, defaultdict

from v2parse import (
    POP_TYPES,
    TOKEN_RE,
    Tokens,
    as_list,
    looks_like_country_tag,
    parse_block,
    pop_culture,
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


def set_mob_candidates(types):
    """Choose which pop types read_province keeps for the mobilization pool."""
    MOB_CANDIDATES.clear()
    MOB_CANDIDATES.update(types)


# Victoria II defines. A mod can change these; --mod-path reads the real values
# out of common/defines.lua, and the command line overrides both.
POP_SIZE_PER_REGIMENT = 3000
# The engine applies no minimum pop size to *mobilization*. POP_MIN_SIZE_FOR_REGIMENT
# governs how small a *soldier* pop may be and still support a standing brigade,
# which is a different rule on a different pop type -- IGoR sets it to 1000.
# Mobilization truncates: int(pop_manpower / POP_SIZE_PER_REGIMENT). Project
# Alice stops there, but that reads 11% low across eight in-game readings and
# up to 24% low on Turkey, so pops too small to fill a regiment evidently still
# contribute something. Two ways to model that, both calibrated against those
# readings rather than read out of the game:
#
#   cascade        manpower a bucket cannot use climbs province-type ->
#                  province -> state -> nation, pooling and truncating again at
#                  every rung. 6.2% mean error over 46 readings spanning
#                  1836-1908 and mobilisation sizes from 3% to 12.5%.
#   province-levy  the same idea stopped at the province. 2.3% on the 1908
#                  save alone, but 60% low in 1836.
#   short-share    a fixed share of the sub-regiment pops yields a brigade
#                  anyway. 1.2% on 1908 alone, 13.8% over all four saves.
#   threshold      a pop yields its first brigade once it clears this much
#                  manpower. 19.2% over all four saves.
#
# Only the cascade holds up across eras; every model that stops short of the
# nation collapses at low mobilisation sizes, where hardly any pop reaches a
# whole regiment on its own and the game still raises dozens of brigades. Its
# one parameter is what a mobilized regiment actually costs, which comes out
# above POP_SIZE_PER_REGIMENT and is fitted, not read out of the game.
# Measured on a 33-reading controlled test bed built inside the mod (see
# MOBILIZATION_TEST.md). A pop whose manpower reaches POP_SIZE_PER_REGIMENT
# raises whole regiments alone and its remainder is discarded. One that falls
# short still counts, as 1/k of a regiment, where k is how many such pops it
# would take to reach one: k = ceil(POP_SIZE_PER_REGIMENT / manpower). The
# fractions are summed across the whole nation and floored once at the end.
#
# Nothing in that is fitted. It reproduces all 33 controlled readings exactly,
# across mobilisation sizes from 3% to 17% and pop manpower from 180 to 26,000.
#
# On real campaign saves it reads about 6% high, uniformly across all four eras.
# A systematic bias with arithmetic this well pinned points at the eligible pool
# being slightly too permissive, not at the counting -- see the README.
#
# The older models below are kept selectable so this stays checkable.

# Superseded, retained for --mob-model. Measured on a 25-nation bed (see
# MOBILIZATION_TEST.md). A pop whose manpower reaches POP_SIZE_PER_REGIMENT
# raises whole regiments on its own and its remainder is discarded; a pop that
# falls short still counts, as a half. Both of those are measured, not fitted:
# 25 of 25 test nations are reproduced exactly with no free constants.
#
# The two thresholds below are the part the test bed could not pin, because no
# test pop sat under 1,860 manpower. They are fitted to 46 in-game campaign
# readings and are the only fitted numbers left in the model.
MOB_HALF_THRESHOLD = 1850
MOB_QUARTER_THRESHOLD = 300
CASCADE_REGIMENT_COST = 3220
# No longer a correction, and no longer needed: once the pool flush was
# measured the model reproduced 100 of 100 controlled readings, 39 of 39 older
# ones and 45 of 46 in-game campaign readings exactly. Kept only so the effect
# of scaling the pool can still be explored from the command line.
# The nations the report pre-selects under its "Players" button. Purely a
# convenience default for this campaign; override per run with --players.
DEFAULT_PLAYER_TAGS = [
    "CHI", "JAP", "USA", "ENG", "NGF", "PRU", "GER", "KUK", "AUS", "RUS",
    "SPA", "ITA", "FRA", "SAR", "SIC", "TUR", "EGY", "COM", "MEX", "NET",
    "PBC", "ARG", "GCO", "BRZ", "POR", "BOL", "CLM", "SWE", "SCA", "PER",
    "BEL",
]

MOB_POOL_FACTOR = 1.0
PROVINCE_LEVY_THRESHOLD = 2400
SHORT_BUCKET_SHARE = 0.1245
POP_MIN_SIZE_FOR_REGIMENT = 1925


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
        # Every eligible pop kept whole, as (poptype, culture, size, province).
        # The engine truncates each bucket of manpower it counts and throws the
        # remainder away, so the ceiling cannot be derived from a national
        # total -- where the buckets are drawn is the whole question.
        "mobilizable_pops": [],
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


def read_province(tok, nations, province_owner_sink, pop_registry=None,
                  province_id=None, owner_map=None):
    """Consume one province block, attributing its pops to the owner."""
    owner = None
    controller = None
    pops = []
    buildings = {}
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
            key = unquote(t)
            if key in POP_TYPES:
                pops.append((key, parse_block(tok)))
            elif key in ("naval_base", "fort", "railroad"):
                buildings[key] = parse_block(tok)
            else:
                skip_block(tok)
        else:
            if t == "owner":
                owner = unquote(val)
            elif t == "controller":
                controller = unquote(val)

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

    for poptype, pop in pops:
        if pop_registry is not None and "id" in pop:
            pop_registry[to_int(pop["id"], -1)] = poptype
        size = to_int(pop.get("size"))
        if size <= 0:
            continue
        culture, _religion = pop_culture(pop)
        nat["total_pop"] += size
        nat["pop_by_type"][poptype] += size
        if culture:
            nat["pop_by_culture"][culture] += size
            if poptype in MOB_CANDIDATES:
                nat["mobilizable_pops"].append(
                    (poptype, culture, size, province_id))
        nat["literacy_weighted"] += to_float(pop.get("literacy")) * size
        nat["con_weighted"] += to_float(pop.get("con")) * size
        nat["mil_weighted"] += to_float(pop.get("mil")) * size
        nat["money_total"] += to_float(pop.get("money"))


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


def read_country(tok, tag, nations):
    """Consume one country block."""
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
        key = unquote(t)

        if val == "{":
            if key in ("army", "navy"):
                count_units({key: parse_block(tok)}, nat)
            elif key == "culture":
                block = parse_block(tok)
                if isinstance(block, list):
                    nat["accepted_cultures"] = [str(c) for c in block]
                elif isinstance(block, dict):
                    nat["accepted_cultures"] = [str(c) for c in block.get("_items", [])]
            elif key == "flags":
                block = parse_block(tok)
                if isinstance(block, dict):
                    nat["country_flags"] = {
                        k for k, v in block.items()
                        if not k.startswith("_") and str(v).lower() == "yes"}
            elif key == "modifier":
                block = parse_block(tok)
                if isinstance(block, dict) and "modifier" in block:
                    nat["modifiers"].append(unquote(str(block["modifier"])))
            elif key == "active_inventions":
                block = parse_block(tok)
                ids = block if isinstance(block, list) else block.get("_items", []) if isinstance(block, dict) else []
                nat["invention_ids"] = [to_int(i, -1) for i in ids]
            elif key == "scheduled_mobilization":
                block = parse_block(tok)
                # Orders that have not spawned yet are brigades still coming.
                if str(block.get("spawned", "no")).lower() != "yes":
                    nat["mobilizing"] += 1
            elif key == "state":
                block = parse_block(tok)
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
                block = parse_block(tok)
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
                skip_block(tok)
        else:
            clean = unquote(val)
            if key == "mobilize":
                nat["is_mobilized"] = int(clean.lower() == "yes")
            elif key in scalars:
                nat[scalars[key]] = clean
            elif key in numerics:
                nat[numerics[key]] = to_float(clean)


def analyze_save(path, verbose=True):
    """Parse one save. Returns (meta, {tag: nation_stats})."""
    if verbose:
        print(f"  reading {os.path.basename(path)} ...", end="", flush=True)
    text = read_save_text(path)
    tok = Tokens(text)

    nations = defaultdict(blank_nation)
    province_counts = defaultdict(int)
    pop_registry = {}
    meta = {"file": os.path.basename(path), "date": "", "player": "", "market": None}
    province_owner = {}
    great_nations = []
    market_block = None

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
            if key.isdigit():
                read_province(tok, nations, province_counts, pop_registry,
                              province_id=int(key), owner_map=province_owner)
            elif looks_like_country_tag(key):
                read_country(tok, key, nations)
            elif key == "great_nations":
                # The engine's own great power list, in rank order, as 1-based
                # indices into the country array that common/countries.txt
                # defines. Nothing else in the save ranks nations.
                block = parse_block(tok)
                ids = (block if isinstance(block, list)
                       else block.get("_items", []) if isinstance(block, dict) else [])
                great_nations = [to_int(i, -1) for i in ids]
            elif key == "worldmarket" and market_block is None:
                market_block = parse_block(tok)
            else:
                skip_block(tok)
        else:
            clean = unquote(val)
            if key == "date" and not meta["date"]:
                meta["date"] = clean
            elif key == "player" and not meta["player"]:
                meta["player"] = clean

    # Classified after the whole file is read, so it does not depend on
    # provinces being written before countries.
    for nat in nations.values():
        for pid in nat["regiment_pops"]:
            poptype = pop_registry.get(pid)
            if poptype is None or poptype == "soldiers":
                nat["regular_brigades"] += 1
            else:
                nat["mobilized_brigades"] += 1

    meta["province_owner"] = province_owner
    meta["great_nations"] = great_nations

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
                          mob_grouping="pop",
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
        if mob_grouping == "province-type":
            # Pool same-type pops of every accepted culture within a province
            # before truncating, so the leftovers of small pops still add up.
            key = (province_id, poptype)
        else:
            # One bucket per pop entry, which is what Project Alice does.
            key = index
        grouped[key] += size
        where[key] = (province_id, states.get(province_id, -1), poptype)
    buckets = [where[k] + (v,) for k, v in grouped.items()]
    return buckets, pool, entries


# Where a bucket's unused manpower goes, in order. Each rung pools what the one
# below it could not use and truncates again.
CASCADE_LEVELS = ("province-type", "province", "state", "nation")


def _rung(level, province, state, poptype):
    if level == "province-type":
        return (province, poptype)
    if level == "province":
        return province
    if level == "state":
        return state
    return 0


def brigades_from_clusters(buckets, rate,
                           pop_per_regiment=POP_SIZE_PER_REGIMENT,
                           min_pop_per_regiment=0,
                           short_share=0.0,
                           levy_threshold=0,
                           cascade_cost=0,
                           half_threshold=0,
                           quarter_threshold=0,
                           reciprocal=False,
                           pool_factor=1.0):
    """
    Brigades a set of (province, state, poptype, size) buckets yields at `rate`.

    Every bucket truncates: it gives int(size * rate / cost) brigades. What
    becomes of the manpower that does not reach a whole regiment is the part
    that has to be calibrated, and the models are mutually exclusive.

    `cascade_cost` hands it up the chain in CASCADE_LEVELS, pooling and
    truncating again at every rung, so a pop too small to raise a regiment on
    its own still counts towards its province, its state and finally the
    nation. `levy_threshold` stops that chain at the province. `short_share`
    gives a fixed share of the sub-regiment buckets one brigade each.
    `min_pop_per_regiment` gives one to every such bucket above that manpower.
    All of them off is the plain truncation Project Alice documents.
    """
    if reciprocal:
        # The measured rule. The engine walks the pops of a nation in save
        # order carrying one pool of manpower that is too small to have raised
        # a regiment yet. A pop big enough to raise regiments by itself raises
        # them and EMPTIES that pool -- whatever had been gathered behind it is
        # thrown away. A pop too small to raise one adds to the pool, and the
        # pool yields a regiment and empties whenever it reaches the cost.
        #
        # The flush is the whole story of the old 6% error. A nation of small
        # pops never flushes, so its pool works perfectly; a nation whose big
        # and small pops interleave keeps losing what it had gathered, which is
        # why culturally mixed nations came out high. Order therefore matters,
        # and `buckets` must stay in the order the save lists the pops.
        total = 0
        pool = 0.0
        for _province, _state, _poptype, size in buckets:
            manpower = size * rate * pool_factor
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

    if half_threshold:
        total = 0.0
        for _province, _state, _poptype, size in buckets:
            manpower = size * rate
            if manpower >= pop_per_regiment:
                total += int(manpower // pop_per_regiment)
            elif manpower >= half_threshold:
                total += 0.5
            elif quarter_threshold and manpower >= quarter_threshold:
                total += 0.25
        return int(total)

    cost = cascade_cost or pop_per_regiment
    total = 0
    short = 0
    unused = defaultdict(float)
    for province, state, poptype, size in buckets:
        manpower = size * rate
        count = int(manpower // cost)
        if count == 0:
            if min_pop_per_regiment and manpower >= min_pop_per_regiment:
                count = 1
            else:
                short += 1
                unused[(province, state, poptype)] += manpower
        total += count
    total += int(short_share * short)

    if levy_threshold:
        levy = defaultdict(float)
        for (province, _state, _type), manpower in unused.items():
            levy[province] += manpower
        for pooled in levy.values():
            whole = int(pooled // cost)
            total += max(whole, 1) if pooled >= levy_threshold else whole
    elif cascade_cost:
        for level in CASCADE_LEVELS:
            pooled = defaultdict(float)
            home = {}
            for ident, manpower in unused.items():
                key = _rung(level, *ident)
                pooled[key] += manpower
                home[key] = ident
            unused = defaultdict(float)
            for key, manpower in pooled.items():
                whole = int(manpower // cost)
                if whole:
                    total += whole
                else:
                    # Still not enough here; try the next rung up.
                    unused[home[key]] += manpower
    return total


def model_knobs(args):
    """The counting knobs implied by --mob-model."""
    if args.mob_model == "measured":
        return 0, 0.0, 0, 0, 0, 0, True
    if args.mob_model == "half-tier":
        return 0, 0.0, 0, 0, args.mob_half_threshold, args.mob_quarter_threshold, False
    if args.mob_model == "cascade":
        return 0, 0.0, 0, args.mob_cascade_cost, 0, 0, False
    if args.mob_model == "province-levy":
        return 0, 0.0, args.mob_levy_threshold, 0, 0, 0, False
    if args.mob_model == "short-share":
        return 0, args.mob_short_share, 0, 0, 0, 0, False
    if args.mob_model == "threshold":
        return args.min_pop_per_regiment, 0.0, 0, 0, 0, 0, False
    return 0, 0.0, 0, 0, 0, 0, False


def finalize(nat, rate=1.0, pop_per_regiment=POP_SIZE_PER_REGIMENT,
             min_pop_per_regiment=0,
             mob_types=MOBILIZABLE_TYPES, mob_grouping="pop",
             include_occupied=False, short_share=0.0, levy_threshold=0,
             cascade_cost=0, half_threshold=0,
             quarter_threshold=0, reciprocal=True,
             pool_factor=MOB_POOL_FACTOR, mod=None):
    """Derive the ratios that need the totals first."""
    total = nat["total_pop"]
    accepted_set = accepted_cultures_of(nat)
    primary = nat["primary_culture"]

    accepted_pop = sum(
        size for cul, size in nat["pop_by_culture"].items() if cul in accepted_set
    )
    primary_pop = nat["pop_by_culture"].get(primary, 0)

    buckets, pool_stated, entries = mobilization_clusters(
        nat, mob_types, mob_grouping, include_occupied)
    brigades = brigades_from_clusters(
        buckets, rate, pop_per_regiment, min_pop_per_regiment, short_share,
        levy_threshold, cascade_cost, half_threshold, quarter_threshold,
        reciprocal, pool_factor)

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
            for name in nat.get("modifiers", ()):
                impact += (mod.get("modifier_impacts") or {}).get(name, 0.0)
            # The revanchism bands are triggered modifiers, evaluated live rather
            # than written into the save, so they have to be re-derived.
            rev = nat.get("revanchism", 0.0)
            band = 0.0
            for threshold, value in mod.get("revanchism_impact_ladder", ()):
                if rev >= threshold:
                    band = value
            impact += band
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
    for stratum, types in STRATA.items():
        out[f"pop_{stratum}"] = sum(nat["pop_by_type"].get(t, 0) for t in types)
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


def date_key(date):
    """Sortable tuple for a `YYYY.M.D` string."""
    try:
        return tuple(int(p) for p in date.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


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
        for stamp, good, price in market["history"]:
            key = (stamp, good)
            # A later save's buffer is the more settled record of the same month.
            if key not in prices or date_key(meta["date"]) >= sources.get(key, (0, 0, 0)):
                prices[key] = price
                sources[key] = date_key(meta["date"])
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


def write_outputs(rows, ship_rows, pop_rows, culture_rows, price_rows,
                  snapshot_rows, brigade_rows, tech_rows, outdir):
    os.makedirs(outdir, exist_ok=True)
    columns = BASE_COLUMNS + [f"pop_{t}" for t in POP_TYPE_LIST] + ["accepted_cultures"]

    main_path = os.path.join(outdir, "nations_timeseries.csv")
    with open(main_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

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
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for row in data:
                writer.writerow(row)
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


def calibrate_mob(readings, parsed, mod, live, args):
    """
    Search the counting model that reproduces a set of in-game figures.

    The engine's own arithmetic cannot be read from outside the game, so the
    free parts -- where the truncation is applied, and what becomes of pops too
    small to raise a regiment -- are fitted to whatever readings the player
    supplies. Everything else (mobilisation size, eligible pops, colonial and
    occupied provinces) is derived, not fitted.

    Readings are `TAG=N` for the last save, or `DATE:TAG=N` to name one, so a
    fit can span several saves at once. That matters more than the number of
    readings: nations at different mobilisation sizes, and saves from different
    eras, are what separate models that agree on any one snapshot.

    Each candidate is also scored leave-one-out -- the parameter is refitted
    without a reading and then asked to predict it. Held-out error much worse
    than in-sample means the fit is chasing noise.
    """
    by_date = {}
    for index, (meta, nations) in enumerate(parsed):
        by_date.setdefault(meta["date"], index)
    targets = {}
    for item in readings:
        stamp, _, rest = item.rpartition(":")
        if "=" not in rest:
            sys.exit(f"--mob-calibrate wants TAG=N or DATE:TAG=N, got {item!r}")
        tag, _, value = rest.partition("=")
        tag = tag.strip().upper()
        if stamp:
            if stamp not in by_date:
                sys.exit(f"No save dated {stamp}. Have: "
                         f"{', '.join(sorted(by_date))}")
            index = by_date[stamp]
        else:
            index = len(parsed) - 1
        if tag not in parsed[index][1]:
            sys.exit(f"{tag} is not in {parsed[index][0]['file']}.")
        targets[(index, tag)] = int(value)

    mob_types = frozenset(args.mob_types)
    rates = {}
    buckets = {}
    for index, tag in targets:
        nat = parsed[index][1][tag]
        if mod is not None:
            from mod_reader import rate_for
            rates[(index, tag)] = rate_for(nat, mod, live=live) or args.mob_rate
        else:
            rates[(index, tag)] = args.mob_rate
        for grouping in ("pop", "province-type"):
            clusters, _pool, _n = mobilization_clusters(
                nat, mob_types, grouping, args.mob_include_occupied)
            buckets[(grouping, index, tag)] = clusters

    def count(grouping, key, knobs):
        return brigades_from_clusters(buckets[(grouping,) + key], rates[key],
                                      args.pop_per_regiment, *knobs)

    grid = range(0, args.pop_per_regiment + 1, 25)
    costs = range(args.pop_per_regiment, args.pop_per_regiment * 2, 20)
    candidates = []
    for grouping in ("pop", "province-type"):
        candidates.append((grouping, "plain", "--mob-model plain",
                           [(0, 0.0, 0, 0)]))
        candidates.append((grouping, "cascade",
                           "--mob-model cascade --mob-cascade-cost {3}",
                           [(0, 0.0, 0, c) for c in costs]))
        candidates.append((grouping, "province-levy",
                           "--mob-model province-levy --mob-levy-threshold {2}",
                           [(0, 0.0, t, 0) for t in grid if t]))
        candidates.append((grouping, "threshold",
                           "--mob-model threshold --min-pop-per-regiment {0}",
                           [(t, 0.0, 0, 0) for t in grid]))
        candidates.append((grouping, "short-share",
                           "--mob-model short-share --mob-short-share {1:g}",
                           [(0, k / 2000, 0, 0) for k in range(0, 801)]))

    def score(grouping, knobs, keys):
        square = 0.0
        for key in keys:
            err = (count(grouping, key, knobs) - targets[key]) / targets[key]
            square += err * err
        return (square / len(keys)) ** 0.5

    keys = sorted(targets)
    results = []
    for grouping, name, template, space in candidates:
        knobs = min(space, key=lambda k: score(grouping, k, keys))
        rms = score(grouping, knobs, keys)
        worst = max(abs(count(grouping, k, knobs) - targets[k]) / targets[k]
                    for k in keys)
        held = 0.0
        for out in keys:
            rest = [k for k in keys if k != out]
            alt = min(space, key=lambda k: score(grouping, k, rest))
            err = (count(grouping, out, alt) - targets[out]) / targets[out]
            held += err * err
        held = (held / len(keys)) ** 0.5
        results.append((rms, worst, held, grouping, name,
                        template.format(*knobs), knobs))
    results.sort()

    dates = sorted({parsed[i][0]["date"] for i, _t in keys})
    print(f"\nCalibrating against {len(targets)} readings "
          f"across {len(dates)} saves ({', '.join(dates)})")
    print(f"\n  {'grouping':<14}{'model':<15}{'mean':>7}{'worst':>7}"
          f"{'held-out':>10}   flags")
    for rms, worst, held, grouping, name, flags, _knobs in results:
        print(f"  {grouping:<14}{name:<15}{rms * 100:>6.1f}%{worst * 100:>6.1f}%"
              f"{held * 100:>9.1f}%   --mob-grouping {grouping} {flags}")

    rms, worst, held, grouping, name, flags, knobs = results[0]
    print(f"\nBest: --mob-grouping {grouping} {flags}")
    last = None
    for key in keys:
        index, tag = key
        date = parsed[index][0]["date"]
        if date != last:
            print(f"\n  {date}")
            print(f"    {'tag':<5} {'rate':>6} {'in game':>8} {'fitted':>8}"
                  f" {'err':>7} {'plain trunc':>12} {'err':>7}")
            last = date
        got = count(grouping, key, knobs)
        plain = count(grouping, key, (0, 0.0, 0, 0))
        print(f"    {tag:<5} {rates[key] * 100:>5.1f}% {targets[key]:>8} "
              f"{got:>8} {(got - targets[key]) / targets[key] * 100:>+6.1f}% "
              f"{plain:>12} {(plain - targets[key]) / targets[key] * 100:>+6.1f}%")
    print("\n  Check the rate column against the game too -- it is derived, not "
          "fitted,\n  and a wrong rate moves the ceiling roughly in proportion.")


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
    per_pop, pool, entries = mobilization_clusters(nat, mob_types, "pop", occ)
    per_pt, _pool, _entries = mobilization_clusters(
        nat, mob_types, "province-type", occ)

    dropped = defaultdict(int)
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

    knobs = model_knobs(args)
    per_pop_n = brigades_from_clusters(per_pop, rate, args.pop_per_regiment, *knobs)
    per_pt_n = brigades_from_clusters(per_pt, rate, args.pop_per_regiment, *knobs)
    untruncated = pool * rate / args.pop_per_regiment
    print(f"\n  ceiling, --mob-grouping pop            {per_pop_n:>6}")
    print(f"  ceiling, --mob-grouping province-type  {per_pt_n:>6}"
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


def save_sort_key(path, meta_date):
    """Sort by in-game date when we have it, filename otherwise."""
    parts = meta_date.split(".")
    try:
        return (0, int(parts[0]), int(parts[1]), int(parts[2]))
    except (IndexError, ValueError):
        return (1, 0, 0, 0)


def main():
    ap = argparse.ArgumentParser(
        description="Aggregate Victoria 2 saves from one campaign into per-nation time series.",
    )
    ap.add_argument("saves", help="folder of .v2 saves, or a single .v2 file")
    ap.add_argument("-o", "--out", default="vic2_report", help="output folder")
    ap.add_argument("--tags", nargs="*", help="only keep these country tags")
    ap.add_argument("--players", nargs="*",
                    help="tags the report pre-selects and lists under Players "
                         "(defaults to DEFAULT_PLAYER_TAGS)")
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
    ap.add_argument("--mob-grouping", choices=("pop", "province-type"),
                    default="pop",
                    help="where the engine's truncation is applied. "
                         "province-type (default) pools accepted pops of the "
                         "same type within a province before truncating; pop "
                         "truncates each pop entry on its own, which is what "
                         "Project Alice documents. The two agree exactly for "
                         "single-culture nations and diverge with cultural "
                         "fragmentation.")
    ap.add_argument("--mob-model",
                    choices=("measured", "half-tier", "cascade",
                             "province-levy", "short-share", "threshold",
                             "plain"),
                    default="measured",
                    help="what becomes of manpower too small to fill a "
                         "regiment. cascade (default) sends it up "
                         "province-type -> province -> state -> nation; "
                         "province-levy stops at the province; short-share "
                         "gives a fixed share of the sub-regiment pops a "
                         "brigade each; threshold gives one to every such pop "
                         "above --min-pop-per-regiment; plain discards it, "
                         "which is what Project Alice documents and reads up "
                         "to 100%% low early in a game.")
    ap.add_argument("--mob-pool-factor", type=float, default=MOB_POOL_FACTOR,
                    help="scales every pop's manpower before counting. The "
                         "arithmetic reproduces 41 of 41 controlled readings at "
                         "1.0, but real campaign saves come out about 6%% high, "
                         "so this closes a gap whose cause is not identified. "
                         "Pass 1.0 for the uncorrected rule.")
    ap.add_argument("--mob-half-threshold", type=int,
                    default=MOB_HALF_THRESHOLD,
                    help="manpower at which a pop too small for a whole "
                         "regiment still counts as half a one, for --mob-model "
                         "measured. The half itself is measured; where the cut "
                         "sits is fitted.")
    ap.add_argument("--mob-quarter-threshold", type=int,
                    default=MOB_QUARTER_THRESHOLD,
                    help="manpower at which such a pop counts as a quarter "
                         "instead. Fitted; 0 disables the tier.")
    ap.add_argument("--mob-cascade-cost", type=int,
                    default=CASCADE_REGIMENT_COST,
                    help="manpower one mobilized regiment costs, for "
                         "--mob-model cascade. Fitted to in-game readings and "
                         "higher than POP_SIZE_PER_REGIMENT; recalibrate with "
                         "--mob-calibrate.")
    ap.add_argument("--mob-levy-threshold", type=int,
                    default=PROVINCE_LEVY_THRESHOLD,
                    help="manpower at which a province levy too small for a "
                         "whole regiment still raises one, for --mob-model "
                         "province-levy. Fitted to in-game readings; "
                         "recalibrate with --mob-calibrate.")
    ap.add_argument("--mob-short-share", type=float, default=SHORT_BUCKET_SHARE,
                    help="share of sub-regiment pops that raise a brigade "
                         "anyway, for --mob-model short-share. Fitted to "
                         "in-game readings; recalibrate with --mob-calibrate.")
    ap.add_argument("--min-pop-per-regiment", type=int,
                    default=POP_MIN_SIZE_FOR_REGIMENT,
                    help="manpower at which a sub-regiment pop still raises "
                         "one, for --mob-model threshold.")
    ap.add_argument("--mob-calibrate", metavar="TAG=N", nargs="+",
                    help="in-game mobilization figures, as TAG=N for the last "
                         "save or DATE:TAG=N to name one, e.g. --mob-calibrate "
                         "USA=560 1862.6.6:FRA=121. Fits every counting model "
                         "against them, ranks the fits, and exits without "
                         "writing anything.")
    ap.add_argument("--mob-include-occupied", action="store_true",
                    help="count provinces the owner has lost control of. The "
                         "engine excludes them, which is the default, but it "
                         "moves nations under siege a lot -- Russia in 1908 "
                         "reads 558 without them and 612 with -- so it is worth "
                         "checking against the game when a nation is at war.")
    ap.add_argument("--map-scale", type=int, default=2, metavar="N",
                    help="how far to shrink the province bitmap for the map tab. "
                         "Default 2, so 2808x1080 from a 5616x2160 map, which "
                         "costs about 660KB once however many saves are in the "
                         "report. 3 is 410KB, 5 is 230KB and visibly blocky "
                         "once you zoom, 1 is the full map at 1.4MB.")
    ap.add_argument("--player-nations", nargs="*", metavar="TAG", default=None,
                    help="tags that were run by a human. Only matters for "
                         "UNCIVILIZED nations, which in IGoR pick up "
                         "player_unciv_mobilization (+2%% mobilisation size) "
                         "when they are not AI. A save records only the nation "
                         "that took it, so in multiplayer every other human "
                         "reads as AI and has to be named here. Defaults to the "
                         "save's own player. Pass it with no tags to disable.")
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
    mod = None
    if args.mod_path:
        from mod_reader import load_mod
        mod = load_mod(args.mod_path)
        from v2parse import register_pop_types
        extra = set(mod["pop_types"]) - POP_TYPES
        register_pop_types(mod["pop_types"])
        defines = mod["defines"]
        if "POP_SIZE_PER_REGIMENT" in defines and args.pop_per_regiment == POP_SIZE_PER_REGIMENT:
            args.pop_per_regiment = int(defines["POP_SIZE_PER_REGIMENT"])
        if mod["mob_types"] and args.mob_types == sorted(MOBILIZABLE_TYPES):
            args.mob_types = sorted(mod["mob_types"])
        if verbose:
            print(f"defines.lua: POP_SIZE_PER_REGIMENT={args.pop_per_regiment} "
                  f"(mobilization threshold {args.min_pop_per_regiment}, "
                  f"calibrated -- see --mob-calibrate)")
            print(f"poptypes/: mobilizable = {' '.join(args.mob_types)}"
                  + (f"; mod-only pop types read: {' '.join(sorted(extra))}"
                     if extra else ""))

    set_mob_candidates(args.mob_types)

    parsed = []
    for path in files:
        try:
            meta, nations = analyze_save(path, verbose=verbose)
        except (ValueError, OSError) as exc:
            print(f"  skipped {os.path.basename(path)}: {exc}", file=sys.stderr)
            continue
        parsed.append((meta, nations))

    if not parsed:
        sys.exit("No saves could be read.")

    parsed.sort(key=lambda item: save_sort_key(item[0]["file"], item[0]["date"]))

    wanted = set(args.tags) if args.tags else None
    live = None
    if mod is not None:
        from mod_reader import attainable_inventions, index_base_for, validate_indices
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
                  f"{len(mod['revanchism_ladder'])} revanchism bands.")
            for t, v in sorted(mod["tech_mob"].items()):
                print(f"  tech       {t:<44} +{v:.3f}")
            for n in sorted(rules):
                mark = "" if n in live else "   (unobtainable)"
                print(f"  invention  {n:<44} +{rules[n]['size']:.3f}{mark}")


    rows, ship_rows, pop_rows, culture_rows = [], [], [], []
    brigade_rows, tech_rows = [], []

    for meta, nations in parsed:
        date = meta["date"]
        year = date.split(".")[0] if date else ""
        # Who was human. The save names only whoever saved it, so a multiplayer
        # game needs the rest on the command line.
        humans = (set(args.player_nations) if args.player_nations is not None
                  else {meta["player"]} if meta.get("player") else set())
        for tag, nat in nations.items():
            if wanted and tag not in wanted:
                continue
            if nat["total_pop"] < args.min_pop:
                continue
            nat["is_player"] = (tag in humans)
            if mod is not None:
                from mod_reader import breakdown
                parts = breakdown(nat, mod, live=live)
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
            knobs = model_knobs(args)
            done = finalize(nat, nation_rate, args.pop_per_regiment, knobs[0],
                            mob_types=frozenset(args.mob_types),
                            mob_grouping=args.mob_grouping,
                            include_occupied=args.mob_include_occupied,
                            short_share=knobs[1], levy_threshold=knobs[2],
                            cascade_cost=knobs[3], half_threshold=knobs[4],
                            quarter_threshold=knobs[5], reciprocal=knobs[6],
                            pool_factor=(args.mob_pool_factor if knobs[6] else 1.0),
                            mod=mod)
            done["mobilisation_size"] = round(nation_rate, 5)
            accepted_set = set(done["accepted_cultures"]) | {done["primary_culture"]}

            row = {
                "date": date,
                "year": year,
                "tag": tag,
                "is_player": int(tag == meta["player"]),
                "accepted_cultures": ";".join(sorted(done["accepted_cultures"])),
            }
            for col in BASE_COLUMNS:
                if col in done:
                    row[col] = done[col]
            for ptype in POP_TYPE_LIST:
                row[f"pop_{ptype}"] = done["pop_by_type"].get(ptype, 0)
            rows.append(row)

            for stype, count in sorted(done["ships_by_type"].items()):
                ship_rows.append({"date": date, "year": year, "tag": tag,
                                  "ship_type": stype, "count": count})
            for rtype, count in sorted(done["regiments_by_type"].items()):
                brigade_rows.append({"date": date, "year": year, "tag": tag,
                                     "regiment_type": rtype, "count": count})
            for tech in sorted(done["tech_list"]):
                branch, line, _pos = TECH_GROUP.get(tech, ("other", "Other", 0))
                tech_rows.append({"date": date, "year": year, "tag": tag,
                                  "technology": tech, "branch": branch,
                                  "line": line})
            for ptype, size in sorted(done["pop_by_type"].items()):
                pop_rows.append({"date": date, "year": year, "tag": tag,
                                 "pop_type": ptype, "size": size})
            for culture, size in sorted(done["pop_by_culture"].items(),
                                        key=lambda kv: -kv[1]):
                culture_rows.append({"date": date, "year": year, "tag": tag,
                                     "culture": culture, "size": size,
                                     "accepted": int(culture in accepted_set)})

    if args.mob_calibrate:
        calibrate_mob(args.mob_calibrate, parsed, mod, live, args)
        return

    if args.explain_mob_pool:
        tag = args.explain_mob_pool.upper()
        meta, nations = parsed[-1]
        nat = nations.get(tag)
        if nat is None:
            sys.exit(f"{tag} is not in {meta['file']}.")
        if mod is not None:
            from mod_reader import rate_for
            rate = rate_for(nat, mod, live=live) or args.mob_rate
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
        parts = breakdown(nat, mod, live=live)
        print(f"\nMobilisation size for {tag} at {meta['date']}:")
        total = 0.0
        for kind, name, value in sorted(parts, key=lambda p: (p[0], -p[2])):
            total += value
            print(f"  {kind:<15} {name:<48} +{value * 100:.2f}%")
        print(f"  {'':<15} {'TOTAL':<48} {total * 100:>6.2f}%")
        print(f"\n{tag} has {len(nat['tech_list'])} techs and "
              f"{len(nat['invention_ids'])} active inventions; "
              f"{len(parts)} of them grant mobilisation size.")
        print(f"Invention indices in save run "
              f"{min(nat['invention_ids'], default=0)}..{max(nat['invention_ids'], default=0)}; "
              f"mod has {mod['invention_count']} inventions.")
        return

    price_rows = merge_prices(parsed)
    snapshot_rows = market_snapshot_rows(parsed)
    paths = write_outputs(rows, ship_rows, pop_rows, culture_rows,
                          price_rows, snapshot_rows, brigade_rows, tech_rows,
                          args.out)

    if not args.no_html:
        from report import build_map, build_report
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
        # The save ranks the great powers itself, as 1-based indices into the
        # country array common/countries.txt defines, so the mod is needed to
        # turn them back into tags.
        order = (mod or {}).get("country_order") or []
        great_powers = {}
        flags = {}
        if order:
            from mod_reader import flag_images, government_flag_types
            variants = government_flag_types(mod["path"])
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
                    # image being stored twice.
                    key = tag + "|" + variants.get(gov, "")
                    if key not in flags:
                        got = flag_images(mod["path"], [tag], {tag: gov})
                        if tag in got:
                            flags[key] = got[tag]
                    row.append([tag, key])
                great_powers[meta_i.get("date") or ""] = row
        html_path = build_report(
            rows, ship_rows, pop_rows, culture_rows, price_rows, snapshot_rows,
            brigade_rows, tech_rows, args.out,
            tag_names=report_names,
            player_tags=args.players if args.players else DEFAULT_PLAYER_TAGS,
            map_data=map_data,
            base_prices=(mod or {}).get("base_prices"),
            great_powers=great_powers,
            flags=flags,
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
        for tag, nat in top:
            if mod is not None:
                from mod_reader import rate_for
                nation_rate = rate_for(nat, mod, live=live)
                if nation_rate <= 0:
                    nation_rate = args.mob_rate
            else:
                nation_rate = args.mob_rate
            done = finalize(nat, nation_rate, args.pop_per_regiment,
                            args.min_pop_per_regiment,
                            frozenset(args.mob_types), args.mob_grouping,
                            mod=mod)
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
            for tag, nat in shown:
                print(f"  {tag}: {rate_for(nat, mod, live=live) * 100:.2f}%")
        print("\nWrote:")
        for path in paths:
            print(f"  {path}")


if __name__ == "__main__":
    main()

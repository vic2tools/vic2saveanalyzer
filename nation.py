#!/usr/bin/env python3
"""
What a nation is, and what may be taken away from one.

A nation, once a save has been read, is a dictionary of seventy-two
fields. Until now nothing owned that: `readsave` built it, the Rust
scanner's adapter in `fastscan` filled in fifty-three of the same fields
from the other side, `vic2_analyzer` held the rules about which of them
survive which stage of a run, and seventeen files named the keys as bare
strings. Adding a field meant finding all of those and hoping.

So this module owns the record. It holds:

  * the fields and their empty values (`blank_nation`),
  * the two constants that decide what "mobilizable" means,
  * the pure functions that read one nation and answer a question about
    it, and
  * the rules for what is dropped when -- `SPENT_ON_FINALIZE` is what
    finishing consumes, `KEEP_NATION` is what survives the trim, and the
    `AS_PLAIN_DICTS` pair is what stops a counter being rebuilt as a
    counter on the far side of a pipe, and
  * how a scanned reading folds into one -- `SCANNED_PROVINCES` and
    `SCANNED_COUNTRY` say what the Rust scanner sends, where each piece
    goes and how it combines.

It imports nothing of ours, which is the point: `readsave`, `fastscan`,
`vic2_analyzer` and `explain` can all depend on it without any of them
depending on each other. That also unpicks a knot -- `explain` used to
reach back into `vic2_analyzer` for the two counting functions, which
`vic2_analyzer` imports in turn, a circle held apart only by importing
late.

`fastscan` no longer names any of these fields. It starts the scanner,
waits for it and hands what comes back here, and the folding -- which
container each piece goes into and whether it is added, replaced, updated
or extended -- is declared beside the fields themselves. A key the scanner
sends that no rule accounts for is refused rather than dropped in silence,
which is the direction that used to be dangerous: a scanner that has
learnt to send a new field and a Python that quietly ignores it look
exactly like everything working.

What is still written twice is `COUNTRY_SCALARS` and `COUNTRY_NUMERICS`,
because the second copy is in Rust and cannot import this. The check in
`testkit/record.py` reads those names straight out of
`scanner/src/country.rs` and fails if the two have drifted, along with the
rest of the shape -- and needs no save, no mod, no Rust compiler and not
even the built binary.
"""

from collections import Counter, defaultdict
from sys import intern as _intern


# Mobilization draws from poor-strata pops that are neither soldiers (they
# already man the standing army) nor slaves, and only from pops of the primary
# or an accepted culture, in unoccupied non-colonial provinces. Which types
# those are is a property of the mod's poptypes/ folder, not a constant, so
# --mod-path replaces this default; it is what vanilla and IGoR both work out to.
MOBILIZABLE_TYPES = frozenset(["farmers", "labourers", "craftsmen"])


# Victoria II defines. A mod can change these; --mod-path reads the real values
# out of common/defines.lua, and the command line overrides both.
POP_SIZE_PER_REGIMENT = 3000


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
        "soldiers_noncolonial": 0,
        "pop_noncolonial": 0,
        "literacy_noncolonial": 0.0,
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
        # `colonial_provinces`, which mobilization and home-state literacy use.
        "province_colonial": {},
        # Geographic group -> population, literate population, types,
        # cultures, populated province count. Filled during the POP scan.
        "population_by_state": {},
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
    buckets = []
    pool = 0
    for poptype, culture, size, province_id in nat["mobilizable_pops"]:
        if poptype not in mob_types or culture not in accepted:
            continue
        if province_id in colonial or province_id in occupied:
            continue
        pool += size
        buckets.append((province_id, states.get(province_id, -1), poptype, size))
    return buckets, pool, len(buckets)


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


# --- reading a folder of saves across however many cores the machine has -----
#
# Saves do not depend on each other, so the only thing stopping a folder from
# being read all at once is that every worker needs the same two pieces of
# global state the mod sets up: which pop types exist, and which of them can be
# mobilized. Windows starts workers with a fresh interpreter, so both are passed
# in and applied before the worker touches a save.

# Everything a nation carries that exists only to be folded into its totals.
# Each one is a table with an entry per province -- eleven thousand of them
# for a large nation -- they are about a third of what a parsed save weighs,
# and `finalize` is the last thing that ever reads any of them.
SPENT_ON_FINALIZE = ("mobilizable_pops", "population_by_state",
                     "literacy_noncolonial", "soldier_pops_at", "province_state")


# Counted with a `Counter` or a `defaultdict` because that is what counting
# wants, and sent as the plain dicts they already are. Rebuilding one on the
# far side of a pipe runs its `__init__`, and a save carries sixteen of them
# a nation: on a campaign of a hundred saves that is sixty-eight thousand
# constructor calls in the one process that has everything else to do.
# Nothing past here adds to them -- every reader does `.get`, `.items` or a
# plain walk -- and `dict()` keeps the order they were counted in, which
# several stable sorts downstream depend on.
AS_PLAIN_DICTS = ("ships_by_type", "ship_crew", "regiments_by_type",
                  "pop_by_type", "pop_by_culture")


AS_PLAIN_DICTS_INSIDE = ("units_at", "men_at")


# What survives a save once its own row has been built. Everything else in a
# parsed save is working material for that row -- the mobilizable pops, the
# per-province soldier, literacy and population tallies, the war histories
# once they have been folded -- and nothing reads it again. Holding it for
# the length of the campaign is what made a monthly century need gigabytes.
KEEP_META = ("date", "player", "file", "province_owner", "great_nations",
             "world_pop", "market")


KEEP_NATION = ("units_at", "men_at", "primary_culture", "accepted_cultures",
               "government", "total_pop", "is_player", "population_states", "capital")


# What `--inventions` and `--check-inventions` read back off the saves after
# the run, on top of the above. Both used to answer zero of everything --
# `--check-inventions` blaming the campaign for being too short to judge --
# because the trim had taken the two fields out from under them. Added to
# what is kept rather than keeping saves whole: two fields a nation against
# half a megabyte of them.
KEEP_FOR_INVENTIONS = ("tech_list", "invention_ids")


def trim_save(meta, nations, keep=KEEP_NATION):
    """One save reduced to what the rest of the run still asks for."""
    thin = {tag: {k: nat[k] for k in keep if k in nat}
            for tag, nat in nations.items()}
    return {k: v for k, v in meta.items() if k in KEEP_META}, thin


# ---------------------------------------------------------------------------
# Folding a scanner's reading into a record
#
# The Rust scanner in `scanner/` reads the provinces and the countries, which
# is most of a save, and hands them back in shapes chosen to be cheap to write
# and cheap to read: pairs rather than objects, one shared table of pop-type
# names rather than the name against every pop. Turning those into the record
# above is a fold, and it used to live in `fastscan` -- which meant `fastscan`
# named fifty-three of these fields itself, and had to know that `pop_by_type`
# is a counter you add into and `core_provinces` a set you update. Two files
# knowing the record is how two files drift apart.
#
# So the fold lives here, beside the fields it fills. What a scanner sends is
# declared as (what it calls it, where it goes, how it combines), and anything
# it sends that is not in these tables is an error rather than a silence --
# the dangerous direction, because a scanner that has learnt to send a new
# field and a Python that quietly drops it look exactly like everything
# working.


def _add(nat, field, value):
    nat[field] += value


def _add_if(nat, field, value):
    # Only when there is one, because that is what the Python reader does:
    # `naval_base_levels` starts as int 0 and is left alone by a province
    # with no naval base, so a nation without one carries `0` and not `0.0`.
    # The report never notices; the CSV writes the number out and does.
    if value:
        nat[field] += value


def _highest(nat, field, value):
    if value > nat[field]:
        nat[field] = value


def _put(nat, field, value):
    nat[field] = value


def _extend(nat, field, value):
    nat[field].extend(value)


def _extend_interned(nat, field, value):
    nat[field].extend(_intern(v) for v in value)


def _update_set(nat, field, value):
    nat[field].update(value)


def _replace(nat, field, value):
    # The scanner sends an empty list for "this nation has none", and the
    # blank record already holds the right empty thing -- which is not always
    # a list. Replacing only when there is something keeps the blank's type.
    if value:
        nat[field] = value


def _replace_list_interned(nat, field, value):
    if value:
        nat[field] = [_intern(v) for v in value]


def _replace_set_interned(nat, field, value):
    if value:
        nat[field] = {_intern(v) for v in value}


def _replace_dict_interned(nat, field, value):
    if value:
        nat[field] = {_intern(k): v for k, v in value}


def _pairs_put(nat, field, value):
    target = nat[field]
    for key, item in value:
        target[key] = item


def _pairs_put_interned(nat, field, value):
    target = nat[field]
    for key, item in value:
        target[_intern(key)] = _intern(item)


def _pairs_add(nat, field, value):
    target = nat[field]
    for key, item in value:
        target[key] += item


def _pairs_add_interned(nat, field, value):
    # Pairs, in the order the file first mentioned each name, because a
    # stable sort downstream breaks ties on it.
    target = nat[field]
    for key, item in value:
        target[_intern(key)] += item


def _pairs_extend(nat, field, value):
    target = nat[field]
    for key, items in value:
        target[key].extend(items)


def _pairs_add_nested(nat, field, value):
    target = nat[field]
    for key, items in value:
        counter = target[key]
        for kind, item in items:
            counter[_intern(kind)] = counter.get(kind, 0) + item


def _population_rows(nat, field, value):
    nat[field] = {group: [pop, literate,
                         {_intern(k): n for k, n in types},
                         {_intern(k): n for k, n in cultures}, provinces]
                  for group, pop, literate, types, cultures, provinces in value}


# What the scanner sends about the provinces a nation owns, and what becomes
# of each. `mobilizable` is not here: its pop types and cultures arrive as
# numbers into a shared name table, so it needs something the others do not.
SCANNED_PROVINCES = (
    ("provinces", "provinces", _add),
    ("ports", "ports", _add),
    ("total_pop", "total_pop", _add),
    ("life_unmet", "life_unmet", _add),
    ("starving", "starving", _add),
    ("naval_base_levels", "naval_base_levels", _add_if),
    ("max_naval_base", "max_naval_base", _highest),
    ("fort_levels", "fort_levels", _add),
    ("railroad_levels", "railroad_levels", _add),
    ("literacy_weighted", "literacy_weighted", _add),
    ("con_weighted", "con_weighted", _add),
    ("mil_weighted", "mil_weighted", _add),
    ("money_total", "money_total", _add),
    ("cores", "core_provinces", _update_set),
    ("occupied", "occupied_provinces", _update_set),
    ("colonial", "province_colonial", _pairs_put),
    ("pop_by_type", "pop_by_type", _pairs_add_interned),
    ("pop_by_culture", "pop_by_culture", _pairs_add_interned),
    ("population_by_state", "population_by_state", _population_rows),
    ("soldiers_noncolonial", "soldiers_noncolonial", _add),
    ("pop_noncolonial", "pop_noncolonial", _add),
    ("literacy_noncolonial", "literacy_noncolonial", _add),
    ("mob_excluded_culture", "mob_excluded_culture", _add),
    ("soldier_pops_at", "soldier_pops_at", _pairs_extend),
)


# And what it sends about the country block itself. `tag`, `scalars` and
# `numerics` are not here: the first is the key the block is found under, and
# the other two are name/value pairs whose names are fields of this record,
# which is the one thing the scanner is still told rather than asked.
SCANNED_COUNTRY = (
    ("is_mobilized", "is_mobilized", _put),
    ("human", "human", _put),
    ("reforms", "reforms", _pairs_put_interned),
    ("accepted_cultures", "accepted_cultures", _replace_list_interned),
    ("country_flags", "country_flags", _replace_set_interned),
    ("modifiers", "modifiers", _extend),
    ("goods_supply", "goods_supply", _replace_dict_interned),
    ("invention_ids", "invention_ids", _replace),
    ("mobilizing", "mobilizing", _add),
    ("states", "states", _add),
    ("province_state", "province_state", _pairs_put),
    ("colonial_provinces", "colonial_provinces", _update_set),
    ("colonial_level", "colonial_level", _pairs_put),
    ("factory_count", "factory_count", _add),
    ("factory_levels", "factory_levels", _add),
    ("techs", "techs", _add),
    ("tech_list", "tech_list", _extend_interned),
    ("army_techs", "army_techs", _add),
    ("navy_techs", "navy_techs", _add),
    ("brigades", "brigades", _add),
    ("armies", "armies", _add),
    ("navies", "navies", _add),
    ("ships", "ships", _add),
    ("regiment_pops", "regiment_pops", _extend),
    ("regiments_by_type", "regiments_by_type", _pairs_add_interned),
    ("ships_by_type", "ships_by_type", _pairs_add_interned),
    ("ship_crew", "ship_crew", _pairs_add_interned),
    ("units_at", "units_at", _pairs_add_nested),
    ("men_at", "men_at", _pairs_add_nested),
)


# What a country block's own lines are called in a save, and what they are
# called in this record. Both readers need this and both used to hold their
# own copy -- Python rebuilt these two dicts inside the loop, once per nation
# per save, and `scanner/src/country.rs` has the same pairs as two `const`
# arrays. The Rust one cannot import this, so it is still written twice; what
# is no longer true is that nobody checks. `testkit/record.py` reads the
# names straight out of the .rs file and fails if the two lists have drifted,
# which needs neither a Rust compiler nor a save.
COUNTRY_SCALARS = {
    "nationalvalue": "nationalvalue",
    "primary_culture": "primary_culture",
    "civilized": "civilized",
    "government": "government",
    "capital": "capital",
}

COUNTRY_NUMERICS = {
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


# The keys each fold handles without a rule of its own, so a block carrying
# something neither the table nor this set accounts for can be spotted.
PROVINCE_EXTRAS = frozenset(("mobilizable",))
COUNTRY_EXTRAS = frozenset(("tag", "scalars", "numerics"))


def _unknown(block, table, extras, what):
    stray = sorted(set(block) - {key for key, _f, _r in table} - extras)
    if stray:
        raise ValueError(
            "the scanner sent %s this does not know what to do with: %s. It "
            "is a newer build than this Python; rebuild the scanner from this "
            "tree, or add the field to nation.py."
            % (what, ", ".join(stray)))


def fold_provinces(nat, block, names):
    """
    What one nation's provinces came to, folded into its record.

    `names` is the scanner's shared table of interned strings: pop types and
    cultures arrive as indices into it, because a campaign has a dozen types
    and a few hundred cultures against tens of thousands of entries, and
    sending numbers is cheaper on both sides.
    """
    _unknown(block, SCANNED_PROVINCES, PROVINCE_EXTRAS, "province totals")
    for key, field, rule in SCANNED_PROVINCES:
        rule(nat, field, block[key])
    pool = nat["mobilizable_pops"]
    for kind, culture, size, pid in block["mobilizable"]:
        pool.append((names[kind], names[culture], size, pid))


def fold_country(nat, block):
    """
    One country block from the scanner, folded into its record.

    The containers are the ones `blank_nation` made, filled rather than
    replaced, so a Counter stays a Counter and a defaultdict stays a
    defaultdict for everything downstream that leans on it.
    """
    _unknown(block, SCANNED_COUNTRY, COUNTRY_EXTRAS, "a country block")
    tag = _intern(block["tag"])
    nat["tag"] = tag
    for name, value in block["scalars"]:
        nat[name] = _intern(value)
    for name, value in block["numerics"]:
        nat[name] = value
    for key, field, rule in SCANNED_COUNTRY:
        rule(nat, field, block[key])
    return tag

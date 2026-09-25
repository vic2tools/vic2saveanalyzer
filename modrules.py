#!/usr/bin/env python3
"""
What a mod's rules are worth to one nation.

`mod_reader` turns a mod folder into tables: which technologies grant
mobilisation size, which inventions do, which modifiers a save can name,
and what each triggered modifier asks before it applies. This asks the
other question -- given those tables and one nation out of one save, what
does the nation actually get?

The two are different jobs and they were tangled. Reading a mod happens
once a run; this happens once per nation per save, four thousand times on
a hundred-save campaign, in whichever process is doing the finishing. The
thirteen functions here were also sitting in two disjoint stretches of a
two-and-a-half thousand line file, five hundred lines apart, which is
usually the file telling you something.

The trigger evaluator is the heart of it. A triggered modifier applies
only if its condition holds, and the conditions are a small language:
AND/OR/NOT, a country's own fields, numeric floors, province scopes. What
it cannot read it says so about, through `unjudged_triggers`, and an
unreadable modifier is left out rather than guessed at -- a guess here is
a wrong mobilisation size for a whole campaign, reported with the same
confidence as a right one.
"""

from v2parse import to_float, to_int, unquote


# What `_trigger_ok` can judge. A country-scope condition is a plain field of
# the nation; a numeric one is a floor, which is how the engine reads
# `revanchism = 0.10`. Anything not named here makes the whole modifier
# unknown, and an unknown modifier is left out rather than guessed at.
_TRIGGER_YESNO = ("civilized", "war", "exists", "is_greater_power", "ai")
_TRIGGER_TEXT = {
    "tag": "tag",
    "government": "government",
    "primary_culture": "primary_culture",
    "nationalvalue": "nationalvalue",
}
_TRIGGER_NUMBER = {
    "revanchism": "revanchism",
    "badboy": "infamy",
    "prestige": "prestige",
    "war_exhaustion": "war_exhaustion",
    "plurality": "plurality",
    "money": "treasury",
    "total_pops": "total_pop",
}


def _conditions(block):
    """
    One trigger block as a list of single-condition blocks.

    A Clausewitz block is a bag of key/value pairs and the same key may appear
    more than once, which the parser hands back as a list. `OR = { tag = FRA
    tag = BOR }` is two conditions, not one condition with two values, and
    only the enclosing operator says whether they are ANDed or ORed.
    """
    out = []
    for key, value in block.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            out.extend({key: v} for v in value)
        else:
            out.append({key: value})
    return out


def _all(results):
    """AND over answers that may be unknown: one False settles it."""
    if any(r is False for r in results):
        return False
    return None if any(r is None for r in results) else True


def _any(results):
    """OR over answers that may be unknown: one True settles it."""
    if any(r is True for r in results):
        return True
    return None if any(r is None for r in results) else False


def _trigger_ok(trigger, nat, mod, world, inventions=()):
    """
    Whether a country meets a triggered modifier's trigger. None means the
    trigger says something this cannot judge, and the caller should leave the
    modifier out rather than assume either way.
    """
    if not isinstance(trigger, dict):
        return True
    return _all([_condition_ok(c, nat, mod, world, inventions)
                 for c in _conditions(trigger)])


def _condition_ok(cond, nat, mod, world, inventions):
    """One `key = value` out of a trigger."""
    (key, value), = cond.items()

    if key in ("AND", "OR", "NOT"):
        if not isinstance(value, dict):
            return None
        answers = [_condition_ok(c, nat, mod, world, inventions)
                   for c in _conditions(value)]
        if key == "OR":
            return _any(answers)
        if key == "AND":
            return _all(answers)
        # `NOT = { a b }` holds when none of a, b do.
        flipped = [None if a is None else not a for a in answers]
        return _all(flipped)

    if key == "capital_scope":
        return _province_ok(value, to_int(nat.get("capital"), -1), mod)

    if isinstance(value, dict):
        return None                   # a scope this does not know how to enter

    text = unquote(str(value))
    reforms = nat.get("reforms") or {}
    groups = mod.reform_names or frozenset()

    if key in _TRIGGER_YESNO:
        want = text.lower() == "yes"
        if key == "ai":
            got = not nat.get("is_player")
        elif key == "exists":
            if text.lower() not in ("yes", "no"):
                return None           # `exists = TAG` asks about someone else
            got = True
        elif key == "war":
            if world is None:
                return None
            got = nat.get("tag") in world.get("at_war", ())
        elif key == "is_greater_power":
            if world is None:
                return None
            got = nat.get("tag") in world.get("great_powers", ())
        else:
            got = str(nat.get("civilized", "")).lower() == "yes"
        return got == want

    if key in _TRIGGER_TEXT:
        return text == str(nat.get(_TRIGGER_TEXT[key], ""))

    if key in _TRIGGER_NUMBER:
        return (to_float(nat.get(_TRIGGER_NUMBER[key]), 0.0)
                >= to_float(text, 0.0))

    if key == "year":
        if world is None or not world.get("year"):
            return None
        return world["year"] >= to_int(text, 0)

    if key == "capital":
        return to_int(nat.get("capital"), -1) == to_int(text, -2)

    if key == "owns":
        if world is None:
            return None
        return world.get("owner", {}).get(to_int(text, -1)) == nat.get("tag")

    if key == "is_culture_group":
        table = mod.culture_groups or {}
        if not table:
            return None
        return table.get(str(nat.get("primary_culture", ""))) == text

    if key == "invention":
        if inventions is None:
            return None
        return text in inventions

    if key == "technology":
        return text in set(nat.get("tech_list") or ())

    if key == "has_country_flag":
        return text in (nat.get("country_flags") or ())

    if key == "has_country_modifier":
        return text in (nat.get("modifiers") or ())

    if key in groups:
        return reforms.get(key) == text

    return None


def _province_ok(trigger, pid, mod):
    """The province-scope half, which is only ever reached through capital_scope."""
    if not isinstance(trigger, dict):
        return None
    return _all([_province_condition(c, pid, mod) for c in _conditions(trigger)])


def _province_condition(cond, pid, mod):
    (key, value), = cond.items()
    if key in ("AND", "OR", "NOT"):
        if not isinstance(value, dict):
            return None
        answers = [_province_condition(c, pid, mod) for c in _conditions(value)]
        if key == "OR":
            return _any(answers)
        if key == "AND":
            return _all(answers)
        return _all([None if a is None else not a for a in answers])
    if isinstance(value, dict):
        return None
    if key == "continent":
        where = (mod.continents or {}).get(pid)
        if not where:
            return None
        return where == unquote(str(value))
    if key == "province_id":
        return pid == to_int(value, -2)
    return None


def held_inventions(nation, mod):
    """
    The inventions a nation actually holds, by name.

    None when the save's numeric indices could not be decoded for this install:
    the requirement-matching fallback answers a different question -- which
    inventions the nation *could* have -- and a trigger asking whether it holds
    one deserves "cannot tell" rather than that.
    """
    base = mod.index_base
    if base is None:
        return None
    seq = mod.invention_sequence or ()
    out = set()
    for idx in nation.get("invention_ids", ()):
        j = idx - base
        if 0 <= j < len(seq):
            out.add(seq[j]["name"])
    return out


def breakdown(nation, mod, live=None, world=None):
    """
    Every contribution to a nation's mobilisation size, as
    [(source_kind, name, value), ...]. `rate_for` is the sum of these.

    `world` is what the save says about everyone else -- the year, who the
    great powers are, who is at war, who owns which province -- which some
    triggered modifiers ask about. Without it those modifiers are left out.
    """
    parts = []
    for tech in nation["tech_list"]:
        value = mod.tech_mob.get(tech, 0.0)
        if value:
            parts.append(("tech", tech, value))

    # Which inventions the nation holds, both for the ones that grant
    # mobilisation size and for the triggered modifiers that ask about one.
    inventions = held_inventions(nation, mod)
    base = mod.index_base
    if base is not None:
        # The save says exactly which inventions this nation rolled. Nothing
        # else does: two nations with identical technology routinely differ,
        # because inventions fire on a chance roll.
        seq = mod.invention_sequence
        for idx in nation.get("invention_ids", ()):
            j = idx - base
            if 0 <= j < len(seq) and seq[j]["size"]:
                parts.append(("invention", seq[j]["name"], seq[j]["size"]))
    else:
        # Indices could not be decoded for this install, so fall back to
        # assuming a nation holds every invention whose `limit` it meets. That
        # is an upper bound, and it overstates nations with poor luck.
        techs = set(nation["tech_list"])
        tag = nation.get("tag", "")
        for name, rule in (mod.invention_rules or {}).items():
            if live is not None and name not in live:
                continue
            if not rule["techs"] <= techs:
                continue
            if rule["tags"] and tag not in rule["tags"]:
                continue
            parts.append(("invention", name, rule["size"]))

    nv = nation.get("nationalvalue", "")
    value = mod.nv_mob.get(nv, 0.0)
    if value:
        parts.append(("national value", nv, value))

    for name in nation.get("modifiers", ()):
        value = (mod.event_mob or {}).get(name, 0.0)
        if value:
            parts.append(("event modifier", name, value))

    # Reforms. The save writes the chosen option as a plain line in the country
    # block -- `conscription=mandatory_service` -- so this needs no judgement at
    # all; it was simply never read. GFM's conscription ladder is worth up to
    # +6%, which is more than its whole technology tree grants.
    for reform, option in (nation.get("reforms") or {}).items():
        value = (mod.reform_mob or {}).get((reform, option), 0.0)
        if value:
            parts.append(("reform", f"{reform} = {option}", value))

    # The flat penalty every uncivilized country carries. It is a static
    # modifier: the engine applies it to anyone uncivilized and writes nothing
    # down. -10% in the base game, -20% in Divergences of Darkness, absent in
    # IGoR and Ferrum Mare.
    if str(nation.get("civilized", "")).lower() == "no":
        value = (mod.static_mob or {}).get("unciv_nation", 0.0)
        if value:
            parts.append(("uncivilized", "unciv_nation", value))

    # Triggered modifiers, which cover the old revanchism ladder and the old
    # player-unciv special case as well as everything neither of them reached:
    # GFM alone hands AI France +13%, Prussia +10% before 1880, Afghanistan
    # +20% and the smaller South American nations up to +8.5%.
    for name, size, _impact, trigger in (mod.triggered_mob or ()):
        if not size:
            continue
        if _trigger_ok(trigger, nation, mod, world, inventions):
            parts.append(("triggered modifier", name, size))
    return parts


def unjudged_triggers(mod):
    """
    Names of the triggered modifiers whose trigger this cannot read, so a run
    can say what it left out instead of quietly being wrong by that much.
    """
    out = []
    for name, size, _impact, trigger in (mod.triggered_mob or ()):
        if not size:
            continue
        if _unreadable(trigger, mod):
            out.append(name)
    return out


def _unreadable(trigger, mod):
    """Does this trigger name a condition `_condition_ok` has no answer for?"""
    if not isinstance(trigger, dict):
        return False
    known = (set(_TRIGGER_YESNO) | set(_TRIGGER_TEXT) | set(_TRIGGER_NUMBER)
             | set(mod.reform_names or ())
             | {"year", "capital", "owns", "is_culture_group", "invention",
                "technology", "has_country_flag", "has_country_modifier"})
    for cond in _conditions(trigger):
        (key, value), = cond.items()
        if key in ("AND", "OR", "NOT"):
            if not isinstance(value, dict) or _unreadable(value, mod):
                return True
        elif key == "capital_scope":
            if not isinstance(value, dict):
                return True
            for inner in _conditions(value):
                (name, _v), = inner.items()
                if name not in ("AND", "OR", "NOT", "continent", "province_id"):
                    return True
        elif key not in known:
            return True
    return False


def rate_for(nation, mod, live=None, world=None, fallback=0.0):
    """
    The share of its people a nation may mobilize.

    Sum of every contribution, floored at zero. Contributions can be
    strongly negative -- IGoR nerfs China's mobilisation by -100 -- and the
    engine clamps the result at zero rather than letting it wrap into
    something meaningful.

    `fallback` is for a run with no mod at all, where the command line is
    the only source of a rate. It is **not** what an empty contribution
    list means. An empty list is zero: an uncivilized nation has no
    technology or invention granting mobilisation size, and in IGoR no
    national value grants it either, so its rate really is zero. Handing
    it the command-line rate instead gave every uncivilized nation 100%,
    which the old "uncivilized cannot mobilize" shortcut happened to hide.

    That distinction is why this takes the fallback rather than leaving
    callers to write `rate_for(...) or default`. Two callers did, and one
    of them -- `--explain-mob-pool` -- went on printing 100% for nations
    the report itself scored at 0.
    """
    if mod is None:
        return fallback
    return max(0.0, sum(value for _kind, _name, value in
                        breakdown(nation, mod, live, world)))


def impact_for(nation, mod, world=None, inventions=None):
    """
    A nation's mobilization_impact from every national modifier that moves it.

    The ruling party's war policy is the base and `finalize` adds that; this is
    what sits on top -- event modifiers, which a save lists by name, and
    triggered modifiers, which it does not.
    """
    # `None` means "work them out", an empty list means "this nation holds
    # none". `False` used to stand in for the first, which reads as a
    # boolean answer to a question about a list.
    if inventions is None:
        inventions = held_inventions(nation, mod)
    total = 0.0
    for name in nation.get("modifiers", ()):
        total += (mod.modifier_impacts or {}).get(name, 0.0)
    for name, _size, impact, trigger in (mod.triggered_mob or ()):
        if not impact:
            continue
        if _trigger_ok(trigger, nation, mod, world, inventions):
            total += impact
    return total


def great_powers(meta, mod):
    """
    The save's great powers, in the engine's rank order, as tags.

    The save ranks them itself, as 1-based indices into the country array
    `common/countries.txt` defines, so the mod is needed to turn them back
    into tags. Without one there is nobody to name.
    """
    order = (mod.country_order if mod else None) or []
    return [order[i - 1] for i in meta.get("great_nations", ())
            if 0 < i <= len(order)]


def save_world(meta, mod):
    """
    What one save says about everybody, for the triggers that ask.

    A triggered modifier can turn on the year, on whether a country is a great
    power, on whether it is at war, or on who owns a particular province --
    none of which is a property of the country block itself. This gathers the
    four of them once per save rather than once per nation.
    """
    powers = great_powers(meta, mod)
    at_war = set()
    for war in meta.get("wars", ()):
        if not war.get("active"):
            continue
        # The war's own list of who is in it now. The history's joins keep
        # a nation that has since made peace and miss one added by hand; a
        # war that lists nobody, which the game never writes, falls back to
        # them rather than to no one.
        at_war.update(war.get("fighting") or (list(war.get("attackers", ()))
                                              + list(war.get("defenders", ()))))
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

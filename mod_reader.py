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
Reads mobilisation_size modifiers out of a Victoria 2 game or mod folder.

Point this at any folder that contains `technologies/` and `inventions/` --
vanilla or a mod. Three sources of the modifier are read:

- technologies/*.txt   -- techs, referenced by NAME in the save (reliable)
- inventions/*.txt     -- inventions, referenced by INDEX in the save
- common/nationalvalues.txt -- national values, referenced by name in the save

Two more parts of the mod come along because the brigade count needs them:
`common/defines.lua` for POP_SIZE_PER_REGIMENT, and `poptypes/` for the strata
of every pop type -- which is what decides who can be mobilized, and which pop
types exist at all.

Inventions are matched by their own requirements, not by the numeric indices the
save stores. Those indices depend on engine load order, which cannot be
reconstructed from a mod folder alone -- an install may load invention files the
folder does not contain, and every ordering tested disagreed with in-game
values. Requirements are stable: a nation has an invention's modifier when it
meets that invention's `limit`, and inventions whose acquisition chance is
driven to zero by a dependency on an unobtainable invention are excluded.
"""

import array
import base64
import hashlib
import os
import pickle
import re
import struct
import tempfile
import zlib

from itertools import groupby

from v2parse import Tokens, as_list, parse_block, to_float, to_int, unquote

_COMMENT = re.compile(r"#[^\r\n]*")


def _read_clausewitz(path):
    """Parse one game file into {top_level_key: block}."""
    with open(path, "rb") as fh:
        text = fh.read().decode("latin-1")
    text = _COMMENT.sub("", text)
    tok = Tokens(text)
    out = []
    while True:
        t = tok.next()
        if t is None:
            break
        if t in "{}=":
            continue
        nxt = tok.next()
        if nxt is None:
            break
        if nxt != "=":
            tok.push(nxt)
            continue
        v = tok.next()
        if v is None:
            break
        if v == "{":
            out.append((unquote(t), parse_block(tok)))
    return out


def _block_text(raw, name):
    """The raw text of one top-level block, for regex-level inspection."""
    m = re.search(r"(?<![\w.])" + re.escape(name) + r"\s*=\s*\{", raw)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    while i < len(raw):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return raw[m.end():i]
        i += 1
    return ""


def _find_mob_size(block):
    """mobilisation_size wherever it hides: top level or inside effect = {}."""
    if not isinstance(block, dict):
        return 0.0
    total = 0.0
    for key, val in block.items():
        if key == "mobilisation_size":
            for v in (val if isinstance(val, list) else [val]):
                total += to_float(v)
        elif key == "effect" and isinstance(val, dict):
            total += _find_mob_size(val)
    return total


_NOT_BLOCK = re.compile(r"NOT\s*=\s*\{(?:[^{}]|\{[^{}]*\})*\}", re.S)


def _limit_of(block_text):
    """Tech requirements, tag locks and invention requirements from a `limit`."""
    m = re.search(r"limit\s*=\s*\{", block_text)
    if not m:
        return set(), set(), set()
    depth, i = 0, m.end() - 1
    while i < len(block_text):
        if block_text[i] == "{":
            depth += 1
        elif block_text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = block_text[m.end():i]
    positive = _NOT_BLOCK.sub("", body)      # NOT = {...} is not a requirement
    reqs = set(re.findall(r"([a-z_][a-z_0-9]*)\s*=\s*1\b", positive))
    tags = set(re.findall(r"tag\s*=\s*(\w+)", positive))
    invs = set(re.findall(r"invention\s*=\s*(\w+)", positive))
    reqs -= invs
    return reqs, tags, invs


def _chance_floor(block_text):
    """
    (base, [(factor, blocked_invention), ...]) from a `chance` block.

    Only modifiers of the form `NOT = { invention = X }` are read. When X turns
    out to be unobtainable the NOT is always true, so that factor always
    applies -- which is how a mod disables an invention without deleting it.
    """
    m = re.search(r"chance\s*=\s*\{", block_text)
    if not m:
        return None, []
    depth, i = 0, m.end() - 1
    while i < len(block_text):
        if block_text[i] == "{":
            depth += 1
        elif block_text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = block_text[m.end():i]
    base = re.search(r"base\s*=\s*([-\d.]+)", body)
    pairs = []
    for mod in re.finditer(r"modifier\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", body, re.S):
        text = mod.group(1)
        factor = re.search(r"factor\s*=\s*([-\d.]+)", text)
        blocked = re.search(r"NOT\s*=\s*\{\s*invention\s*=\s*(\w+)\s*\}", text, re.S)
        if factor and blocked:
            pairs.append((float(factor.group(1)), blocked.group(1)))
    return (float(base.group(1)) if base else None), pairs


# Defines that govern how many brigades a pop can raise. A mod is free to move
# any of them, and IGoR does: its POP_MIN_SIZE_FOR_REGIMENT is 1000, not the
# vanilla-ish 3000 the analyzer used to assume.
_DEFINE_KEYS = (
    "POP_SIZE_PER_REGIMENT",
    "POP_MIN_SIZE_FOR_REGIMENT",
    "MIN_MOBILIZE_LIMIT",
    "POP_MIN_SIZE_FOR_REGIMENT_COLONY_MULTIPLIER",
    "POP_MIN_SIZE_FOR_REGIMENT_NONCORE_MULTIPLIER",
    "POP_MIN_SIZE_FOR_REGIMENT_PROTECTORATE_MULTIPLIER",
)


def read_defines(path):
    """
    The handful of `common/defines.lua` constants that touch brigade counts.

    defines.lua is Lua, not Clausewitz, so it is read with a regex rather than
    the block parser: every key we want is a plain `NAME = number,` line.
    """
    out = {}
    fname = _resolved_file(path, "common", "defines.lua")
    if not os.path.isfile(fname):
        return out
    with open(fname, "rb") as fh:
        text = _COMMENT.sub("", fh.read().decode("latin-1"))
    text = re.sub("--.*", "", text)   # Lua line comments
    for key in _DEFINE_KEYS:
        m = re.search(r"(?<![\w.])" + key + r"\s*=\s*([-\d.]+)", text)
        if m:
            out[key] = float(m.group(1))
    return out


def read_poptypes(path):
    """
    {pop_type: strata} from `poptypes/`, where the file name is the type name.

    Mobilization draws from poor-strata pops that are neither soldiers nor
    slaves, so the strata table is what decides the eligible set -- hardcoding
    farmers/labourers/craftsmen only happens to be right for vanilla-like mods.
    """
    out = {}
    for target in _resolved_files(path, "poptypes").values():
        with open(target, "rb") as fh:
            text = _COMMENT.sub("", fh.read().decode("latin-1"))
        m = re.search(r"(?<![\w.])strata\s*=\s*(\w+)", text)
        if m:
            name = os.path.basename(target)
            out[os.path.splitext(name)[0].lower()] = m.group(1).lower()
    return out


def mobilizable_types(strata):
    """Poor-strata pop types minus the two the engine never mobilizes."""
    return frozenset(
        name for name, layer in strata.items()
        if layer == "poor" and name not in ("soldiers", "slaves")
    )


def _files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(
        (f for f in os.listdir(folder) if f.lower().endswith(".txt")),
        key=str.lower,
    )


def _named_blocks(text, keyword):
    """Bodies of every `<keyword> = { ... }` block, brace-matched."""
    out, i = [], 0
    pat = re.compile(r"\b" + keyword + r"\s*=\s*\{")
    while True:
        m = pat.search(text, i)
        if not m:
            return out
        depth, j = 0, m.end() - 1
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(text[m.end():j])
        i = j + 1


def _plain(path):
    """One game file as comment-stripped text."""
    with open(path, "rb") as fh:
        return _COMMENT.sub("", fh.read().decode("latin-1"))


def _country_entries(path):
    """
    [(tag, its country file), ...] in the engine's own array order.

    A mod can name the same tag twice in `common/countries.txt` -- Divergences
    of Darkness lists eight of them, ARC and AZL among them -- and the engine
    keeps only the first. Anything counting positions has to drop the repeats
    or every index past the first one is off by however many came before it.
    Dropped, this list matches the order a save writes its country blocks in,
    tag for tag, which is the engine's array by definition.
    """
    listing = _resolved_file(path, "common", "countries.txt")
    if not os.path.isfile(listing):
        return []
    entry = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*"?([^"\r\n]+?)"?\s*$', re.M)
    seen = set()
    out = []
    for tag, rel in entry.findall(_plain(listing)):
        if tag in seen:
            continue
        seen.add(tag)
        out.append((tag, rel.strip()))
    return out


def party_sequence(path):
    """
    Every party in engine load order, so a save's `ruling_party` index decodes.

    Saves store `ruling_party` as a bare 0-based index into the engine's global
    party list, which the engine builds by walking `common/countries.txt` in
    file order and taking each country file's `party = {...}` blocks in order --
    the same trick the invention indices need. Returns
    [(tag, name, ideology, war_policy), ...].

    Verified against China in the 1890 save: index 2437 decodes to a jingoist
    party, and jingoism's mobilization_impact of 4 against China's 8 standing
    regiments gives the 32 the game offers. One-based indexing decodes to a
    pro-military party and predicts 24, which the game does not show.
    """
    out = []
    for tag, rel in _country_entries(path):
        target = _resolved_file(path, "common", rel.replace("/", os.sep))
        if not os.path.isfile(target):
            continue
        for block in _named_blocks(_plain(target), "party"):
            name = re.search(r'name\s*=\s*"?([\w.\-]+)', block)
            ideology = re.search(r"ideology\s*=\s*(\w+)", block)
            policy = re.search(r"war_policy\s*=\s*(\w+)", block)
            out.append((tag,
                        name.group(1) if name else "",
                        ideology.group(1) if ideology else "",
                        policy.group(1) if policy else ""))
    return out


def modifier_mob_impacts(path):
    """
    {modifier name: mobilization_impact} for every national modifier that moves
    it, from event_modifiers.txt and triggered_modifiers.txt.

    Saves list a country's active modifiers by name, so these resolve exactly.
    IGoR's `totalitarianism_modifier` carries -0.2, which is why China reads a
    280% impact in 1908 on a war policy worth 300%.
    """
    out = {}
    for name in ("event_modifiers.txt", "triggered_modifiers.txt"):
        target = _resolved_file(path, "common", name)
        if not os.path.isfile(target):
            continue
        for key, block in _read_clausewitz(target):
            if isinstance(block, dict) and "mobilization_impact" in block:
                out[key] = to_float(block["mobilization_impact"], 0.0)
    return out


def mobilization_impacts(path):
    """
    {war policy: mobilization_impact}, out of the mod's own issues.txt.

    Every option under `party_issues > war_policy`, rather than the four
    vanilla names: a mod is free to add a fifth stance, and one that does
    would have read as no policy at all.
    """
    target = _resolved_file(path, "common", "issues.txt")
    if not os.path.isfile(target):
        return {}
    out = {}
    for party in _named_blocks(_plain(target), "party_issues"):
        for policy in _named_blocks(party, "war_policy"):
            for m in re.finditer(r"(\w+)\s*=\s*\{", policy):
                block = _named_blocks(policy[m.start():], m.group(1))
                if not block:
                    continue
                hit = re.search(r"mobilization_impact\s*=\s*([-\d.]+)", block[0])
                if hit:
                    out.setdefault(m.group(1), float(hit.group(1)))
    return out


def reform_mob(path):
    """
    ({(reform, option): mobilisation_size}, frozenset(reform names)) from issues.txt.

    A reform option is an ordinary modifier block, and a mod is free to hang
    mobilisation size off one: GFM adds a `conscription` reform whose four
    rungs run +1% to +6%, which is more than most nations get from their whole
    technology tree, and its `centralization` reform takes 1% back at two of
    its levels. Saves write the chosen option as a plain `conscription=
    mandatory_service` line in the country block, so this resolves exactly.

    `party_issues` is skipped: those are party platforms, not national reforms,
    and a country's stance on them comes from its ruling party rather than from
    a line of its own.
    """
    target = _resolved_file(path, "common", "issues.txt")
    sizes, groups = {}, set()
    if not os.path.isfile(target):
        return sizes, frozenset()
    for category, block in _read_clausewitz(target):
        if category == "party_issues" or not isinstance(block, dict):
            continue
        for reform, body in block.items():
            if reform.startswith("_") or not isinstance(body, dict):
                continue
            groups.add(reform)
            for option, spec in body.items():
                if option.startswith("_") or not isinstance(spec, dict):
                    continue
                size = _find_mob_size(spec)
                if size:
                    sizes[(reform, option)] = size
    return sizes, frozenset(groups)


def static_mob(path):
    """
    {static modifier: mobilisation_size} from `common/static_modifiers.txt`.

    Only `unciv_nation` is used, and it is worth -10% in the base game and
    -20% in Divergences of Darkness. The engine hands it to every uncivilized
    country, unconditionally, and nothing writes it into the save.
    """
    target = _resolved_file(path, "common", "static_modifiers.txt")
    out = {}
    if not os.path.isfile(target):
        return out
    for name, block in _read_clausewitz(target):
        size = _find_mob_size(block)
        if size:
            out[name] = size
    return out


def triggered_mob(path):
    """
    [(name, mobilisation_size, mobilization_impact, trigger)] for every
    triggered modifier that moves either.

    Triggered modifiers are re-evaluated by the engine every day and are never
    written into a save -- unlike event modifiers, which a country lists by
    name -- so the only way to know a country has one is to read its trigger
    and judge it. `_trigger_ok` does that for the conditions these actually
    use, and says so rather than guessing when it meets one it cannot judge.
    """
    target = _resolved_file(path, "common", "triggered_modifiers.txt")
    out = []
    if not os.path.isfile(target):
        return out
    for name, block in _read_clausewitz(target):
        if not isinstance(block, dict):
            continue
        size = _find_mob_size(block)
        impact = to_float(block.get("mobilization_impact"), 0.0)
        if not size and not impact:
            continue
        trigger = block.get("trigger")
        out.append((name, size, impact,
                    trigger if isinstance(trigger, dict) else {}))
    return out


def _trigger_conditions(trigger, out):
    """Every plain condition name a trigger uses, however deeply nested."""
    if not isinstance(trigger, dict):
        return out
    for key, value in trigger.items():
        if key in ("AND", "OR", "NOT"):
            for part in as_list(value):
                _trigger_conditions(part, out)
        elif isinstance(value, dict):
            out.add(key)
            _trigger_conditions(value, out)
        else:
            out.add(key)
    return out


def watched_reforms(sizes, groups, triggers):
    """
    The reform groups a save has to carry, which is as few as possible.

    Every country block names its choice for thirty-odd reforms and a campaign
    of monthly autosaves holds hundreds of country blocks per year, so keeping
    all of them would cost more memory than the mobilisation pool does. Only
    two kinds are worth anything here: a reform some option of which grants
    mobilisation size, and one a triggered modifier asks about.
    """
    asked = set()
    for _name, _size, _impact, trigger in triggers:
        _trigger_conditions(trigger, asked)
    return frozenset({group for group, _option in sizes} | (set(groups) & asked))


def culture_groups(path):
    """{culture: its culture group} from `common/cultures.txt`."""
    out = {}
    for root in (base_game_path(path), path):
        if not root:
            continue
        target = os.path.join(root, "common", "cultures.txt")
        if not os.path.isfile(target):
            continue
        for group, block in _read_clausewitz(target):
            if not isinstance(block, dict):
                continue
            for name, body in block.items():
                if name.startswith("_") or name in _NOT_A_CULTURE:
                    continue
                if isinstance(body, dict) or (isinstance(body, list)
                                              and body and isinstance(body[0], dict)):
                    out[name] = group
    return out


def continents(path):
    """{province id: continent} from `map/continent.txt`."""
    target = _map_file(path, "continent.txt")
    out = {}
    if not os.path.isfile(target):
        return out
    for name, block in _read_clausewitz(target):
        if not isinstance(block, dict):
            continue
        for pid in as_list(block.get("provinces")):
            if isinstance(pid, (str, int)):
                out[to_int(pid, -1)] = name
    return out


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
    groups = mod.get("reform_names") or frozenset()

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
        table = mod.get("culture_groups") or {}
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
        where = (mod.get("continents") or {}).get(pid)
        if not where:
            return None
        return where == unquote(str(value))
    if key == "province_id":
        return pid == to_int(value, -2)
    return None


def read_localisation(path):
    """
    Country names out of the mod's own `localisation/*.csv`.

    Paradox localisation is `KEY;english;french;...`, Windows-1252, and country
    names come in two flavours: a bare `TAG` and government-specific
    `TAG_<government>` overrides. IGoR names PBC "Peru-Bolivia" plainly but
    "Andine Federation" while it is a democracy, which is what the game shows,
    so both are kept and `name_for` picks between them.

    Files are read in name order and the FIRST definition of a key wins, which is
    how the engine behaves: IGoR defines `PBC_democracy` as "Andine Federation"
    in its country pack and "The Andean Republic" in a later file, and the game
    shows the former.

    The mod is read first and the game underneath it after, on that same rule
    and for the same reason `text_localisation` does it: a mod renames what it
    means to rename and inherits the rest. Divergences of Darkness names 599 of
    its 658 tags and leaves Denmark, Norway, Sweden and Belgium to the base
    game, and reading only the mod folder left those showing as bare tags.
    """
    wanted = re.compile(r"^[A-Z][A-Z0-9]{2}(_[a-z_]+)?$")
    out = {}
    for root in (path, base_game_path(path)):
        if not root:
            continue
        folder = os.path.join(root, "localisation")
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".csv"):
                continue
            try:
                with open(os.path.join(folder, name), "rb") as fh:
                    text = fh.read().decode("cp1252", "replace")
            except OSError:
                continue
            for line in text.splitlines():
                if not line or line.startswith("#") or ";" not in line:
                    continue
                key, _, rest = line.partition(";")
                key = key.strip()
                if not wanted.match(key):
                    continue
                english = rest.split(";", 1)[0].strip()
                if english:
                    out.setdefault(key, english)
    return out


def name_for(tag, government, localisation):
    """The name the game shows for a country: government override, then plain."""
    if government:
        specific = localisation.get(f"{tag}_{government}")
        if specific:
            return specific
    return localisation.get(tag) or tag


def base_prices(path):
    """{good: base cost} from `common/goods.txt`, which nests goods in categories."""
    target = _resolved_file(path, "common", "goods.txt")
    if not os.path.isfile(target):
        return {}
    out = {}
    for _category, block in _read_clausewitz(target):
        if not isinstance(block, dict):
            continue
        for good, spec in block.items():
            if good.startswith("_") or not isinstance(spec, dict):
                continue
            if "cost" in spec:
                out[good] = to_float(spec["cost"], 0.0)
    return out


def regions(path):
    """
    {state name: [province ids]} from `map/region.txt`.

    A war goal names one province, but it wants the whole state, so testing
    whether a goal was met means knowing which provinces travel together.
    """
    target = _map_file(path, "region.txt")
    if not os.path.isfile(target):
        return {}
    out = {}
    for line in _plain(target).splitlines():
        hit = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*\{([^}]*)\}", line)
        if hit:
            ids = [int(n) for n in hit.group(2).split() if n.isdigit()]
            if ids:
                out[hit.group(1)] = ids
    return out


def _resolved_file(path, *parts):
    """
    The copy of one named file the game would actually read.

    Same rule as `_resolved_files`, for the files there is only one of:
    `common/issues.txt` and its neighbours. A mod that ships its own wins; a
    mod that ships none inherits the game's whole. Returns the mod's path
    either way when neither exists, so a caller's `isfile` check still fails
    the way it used to.
    """
    own = os.path.join(path, *parts)
    if os.path.isfile(own):
        return own
    root = base_game_path(path)
    if root:
        inherited = os.path.join(root, *parts)
        if os.path.isfile(inherited):
            return inherited
    return own


def _resolved_files(path, folder):
    """
    {file name: the copy the game would actually read}, in load order.

    Victoria II resolves a mod file by file: a mod's `units/frigate.txt`
    replaces the game's, and a file the mod does not ship is inherited whole.
    So the base game is listed first and the mod laid over the top, keyed by
    name -- the same rule `country_files` and `map_source` follow.
    """
    out = {}
    for root in (base_game_path(path), path):
        if not root:
            continue
        target = os.path.join(root, folder)
        for name in _files(target):
            out[name] = os.path.join(target, name)
    return out


def unit_kinds(path):
    """{unit type: 'land' or 'naval'} from `units/*.txt`."""
    out = {}
    for target in _resolved_files(path, "units").values():
        body = _plain(target)
        for m in re.finditer(r"^(\w+)\s*=\s*\{", body, re.M):
            kind = re.search(r"(?<![\w_])type\s*=\s*(\w+)", body[m.end():m.end() + 900])
            if kind:
                out[m.group(1)] = kind.group(1)
    return out


# What a ship is worth in a fight, and what it costs the naval limit. Read as
# written: `evasion` is a fraction, the rest are plain numbers.
_SHIP_STATS = ("hull", "gun_power", "evasion", "torpedo_attack",
               "supply_consumption_score")


def naval_units(path):
    """
    {ship: {hull, gun_power, evasion, torpedo_attack, score, heavy}} for every
    naval unit in `units/*.txt`.

    These are the numbers behind a ship's power level: two ships trading fire
    deal damage in proportion to their own gun power and in inverse proportion
    to the other's hull, and evasion throws a share of the incoming ticks away
    entirely. `score` is `supply_consumption_score`, the naval points the ship
    costs, so power per point can be read off as well. `heavy` marks a
    `big_ship`, which is the only kind torpedoes work against.
    """
    out = {}
    for target in _resolved_files(path, "units").values():
        body = _plain(target)
        for m in re.finditer(r"^(\w+)\s*=\s*\{", body, re.M):
            block = _block_text(body, m.group(1))
            kind = re.search(r"(?<![\w_])type\s*=\s*(\w+)", block)
            if not kind or kind.group(1) != "naval":
                continue
            stats = {}
            for stat in _SHIP_STATS:
                hit = re.search(r"(?<![\w_])" + stat + r"\s*=\s*([-\d.]+)", block)
                stats[stat] = float(hit.group(1)) if hit else 0.0
            klass = re.search(r"(?<![\w_])unit_type\s*=\s*(\w+)", block)
            out[m.group(1)] = {
                "hull": stats["hull"],
                "gun_power": stats["gun_power"],
                "evasion": stats["evasion"],
                "torpedo_attack": stats["torpedo_attack"],
                "score": stats["supply_consumption_score"],
                "heavy": int(bool(klass) and klass.group(1) == "big_ship"),
            }
    return out


def _drop_block(text, keyword):
    """The text with every `<keyword> = { ... }` cut out, braces matched."""
    out, i = [], 0
    pat = re.compile(r"\b" + keyword + r"\s*=\s*\{")
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:m.start()])
        depth, j = 0, m.end() - 1
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1


def _ship_changes(text):
    """{target: {stat: delta}} for every `<target> = { <ship stat> = n }` here.

    The target is left as written -- a ship name, or `navy_base` for all of
    them -- and checked against the mod's actual units at the point of use, so
    anything else this picks up falls away there.
    """
    found = {}
    for hit in re.finditer(r"(\w+)\s*=\s*\{([^{}]*)\}", text):
        deltas = {stat: float(value) for stat, value in
                  re.findall(r"(\w+)\s*=\s*([-\d.]+)", hit.group(2))
                  if stat in _SHIP_STATS}
        if not deltas:
            continue
        into = found.setdefault(hit.group(1), {})
        for stat, value in deltas.items():
            into[stat] = into.get(stat, 0.0) + value
    return found


def naval_tech_effects(path):
    """
    {technology: {ship or 'navy_base': {stat: delta}}} from `technologies/*.txt`.

    Almost every naval upgrade in the game is an invention rather than a
    technology, and in vanilla and four of the mods here `technologies/` touches
    no ship at all. GFM is the exception -- `naval_directionism` hands the two
    transports speed and evasion directly -- so techs are read too, and they are
    the easier half: a save names a nation's technologies outright, with none of
    the index-decoding the inventions need.

    `ai_chance` is cut out first. It is full of `modifier = { ... }` blocks that
    look like the thing being searched for and are weightings, not effects.
    """
    out = {}
    for target in _resolved_files(path, "technologies").values():
        raw = _plain(target)
        for name, _block in _read_clausewitz(target):
            found = _ship_changes(_drop_block(_block_text(raw, name), "ai_chance"))
            if found:
                out[name] = found
    return out


def naval_invention_effects(path):
    """
    {invention: {ship or 'navy_base': {stat: delta}}} for the inventions that
    upgrade a ship.

    This is where nearly every naval upgrade lives: a technology opens an area,
    and the inventions under it are what add the gun power and the hull. The
    few a technology grants directly are `naval_tech_effects`. `navy_base` is
    the engine's name for "every naval unit", so it is kept as written and
    applied to all of them at the point of use.

    Only `effect = { ... }` is read. A `limit` or a `chance` block names ships
    too -- as requirements, not as changes -- and reading those as upgrades
    would hand a nation the stats of the ships it merely needed to unlock the
    invention.
    """
    out = {}
    for target in _resolved_files(path, "inventions").values():
        raw = _plain(target)
        for name, _block in _read_clausewitz(target):
            body = _block_text(raw, name)
            found = {}
            for effect in _named_blocks(body, "effect"):
                for who, deltas in _ship_changes(effect).items():
                    into = found.setdefault(who, {})
                    for stat, value in deltas.items():
                        into[stat] = into.get(stat, 0.0) + value
            if not found:
                continue
            # The requirements come along for the ride: when a save's invention
            # indices cannot be decoded, the only way left to guess what a
            # nation has rolled is what it could have rolled.
            reqs, tags, _invs = _limit_of(body)
            out[name] = {"effects": found, "techs": reqs, "tags": tags}
    return out


def naval_profile(nation, mod):
    """
    One nation's ships as they actually fight, as
    {ship: {gun_power, hull, evasion, torpedo_attack, score, heavy}}.

    A ship's power level is `gun_power x hull / (1 - evasion)`: in a duel each
    side's damage runs with its own gun power and against the other's hull,
    and evasion throws away a share of the ticks aimed at it, so rearranging
    "who out-damages whom" leaves every term on its owner's side. Torpedoes
    are added to gun power only against a `big_ship`, which is why `heavy` is
    carried through to whoever does the comparing.

    Upgrades come from the nation's technologies, which a save names outright,
    and from its inventions, which it names by index. The inventions follow
    `breakdown`: decoded when the load order can be reconstructed, and otherwise
    guessed as every invention whose requirements the nation meets, which
    flatters nations with bad luck.
    """
    units = mod.get("naval_units") or {}
    rules = mod.get("naval_effects") or {}
    out = {ship: dict(stats) for ship, stats in units.items()}
    if not out:
        return out

    def apply(changes):
        for who, deltas in changes.items():
            # `navy_base` is the engine's name for every naval unit at once.
            ships = list(out) if who == "navy_base" else [who] if who in out else []
            for ship in ships:
                for stat, delta in deltas.items():
                    key = "score" if stat == "supply_consumption_score" else stat
                    out[ship][key] = out[ship].get(key, 0.0) + delta

    # Technologies are named outright by the save, so these need no guessing.
    tech_rules = mod.get("naval_tech_effects") or {}
    for tech in nation.get("tech_list", ()):
        if tech in tech_rules:
            apply(tech_rules[tech])

    base = mod.get("index_base")
    if base is not None:
        seq = mod.get("invention_sequence") or []
        held = [seq[i - base]["name"] for i in nation.get("invention_ids", ())
                if 0 <= i - base < len(seq)]
    else:
        techs = set(nation.get("tech_list", ()))
        tag = nation.get("tag", "")
        held = [name for name, rule in rules.items()
                if rule["techs"] <= techs
                and (not rule["tags"] or tag in rule["tags"])]

    for name in held:
        rule = rules.get(name)
        if rule:
            apply(rule["effects"])

    for stats in out.values():
        stats["gun_power"] = max(0.0, stats["gun_power"])
        stats["hull"] = max(0.0, stats["hull"])
        stats["torpedo_attack"] = max(0.0, stats["torpedo_attack"])
        # A ship that dodged everything would divide by zero and be worth
        # infinity. Nothing in the game or in any mod looked at gets near this.
        stats["evasion"] = min(0.95, max(0.0, stats["evasion"]))
    return out


def state_names(path):
    """{state key: the name the game shows}, e.g. PER_1112 -> Tabriz."""
    keys = set(regions(path))
    return {k: v for k, v in text_localisation(path, keys).items() if v}


def province_regions(path):
    """
    {province id: state name}, the reverse of `regions`.

    A province belongs to the first region that claims it, the way a tag belongs
    to its first line in `common/countries.txt`. Divergences of Darkness keeps a
    metaregion in `region.txt` -- MET_1, one entry naming almost every province
    on the map -- and reversing the mapping without that rule handed all 2,704
    of them to it, which turned every state in the war tab into "Earth".
    """
    out = {}
    for name, ids in regions(path).items():
        for pid in ids:
            out.setdefault(pid, name)
    return out


def country_order(path):
    """
    Tags in `common/countries.txt` order, which is the engine's country array.

    A save's `great_nations` list holds 1-based indices into it, so this is what
    turns "2 10 9 16 6 4 8 12" into a great power ranking.
    """
    return [tag for tag, _file in _country_entries(path)]


_COUNTRY_ENTRY = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*"?([^"\r\n]+?)"?\s*$', re.M)


def country_files(path):
    """
    {tag: the file defining it}, the mod's copy winning over the game's.

    Same partial-mod story as the map: Ferrum Mare's `common/countries.txt`
    names 179 tags and its `countries/` folder holds 130 files, so a campaign
    played on the standard nations found a colour for two of them and drew
    the rest of the world as unclaimed ground. The base game is read first
    and the mod laid over the top, which is the order the game resolves them
    in.
    """
    out = {}
    for root in (base_game_path(path), path):
        if not root:
            continue
        listing = os.path.join(root, "common", "countries.txt")
        if not os.path.isfile(listing):
            continue
        for tag, rel in _COUNTRY_ENTRY.findall(_plain(listing)):
            rel = rel.strip().replace("/", os.sep)
            # A tag may be listed by one and shipped by the other, so the file
            # is looked for in both regardless of which list named it.
            for home in (path, root):
                target = os.path.join(home, "common", rel)
                if os.path.isfile(target):
                    out[tag] = target
                    break
    return out


def country_colours(path):
    """{tag: '#rrggbb'} from each country file's `color = { r g b }`."""
    out = {}
    for tag, target in country_files(path).items():
        hit = re.search(r"color\s*=\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}",
                        _plain(target))
        if hit:
            out[tag] = "#%02x%02x%02x" % tuple(int(g) for g in hit.groups())
    return out


def base_game_path(path):
    """
    The Victoria II install a mod sits inside, or None when there isn't one.

    Mods live at `<install>/mod/<name>`, so the install is two levels up.
    Confirmed by looking for files no mod folder holds on its own, rather
    than trusting the shape of the path.
    """
    if not path:
        return None
    root = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    if os.path.basename(os.path.dirname(os.path.abspath(path))).lower() != "mod":
        return None
    if not os.path.isfile(os.path.join(root, "map", "default.map")):
        return None
    return root


def map_source(path):
    """
    Where to read the province layout from: the mod, or the game beneath it.

    Victoria II resolves a mod file by file. A mod that ships no
    `provinces.bmp` runs on the base game's map -- Modus Omnino Demens ships
    one file in `map/` and inherits the rest -- and reading only the mod
    folder gave it no map at all. So the bitmap and `definition.csv` are
    resolved as a pair, because a bitmap read against another map's ids is
    worse than no map.

    `positions.txt` and `default.map` follow whichever map won, for the same
    reason: army counters placed by coordinates from a *different* map would
    land in the wrong provinces, so a mod with its own bitmap never borrows
    the game's positions. Anything it then leaves unanchored is covered by
    `province_anchors`.
    """
    own = os.path.join(path, "map")
    if (os.path.isfile(os.path.join(own, "provinces.bmp"))
            and os.path.isfile(os.path.join(own, "definition.csv"))):
        return path
    return base_game_path(path) or path


def _map_file(path, name):
    """One file from `map/`, taken from wherever the province layout is."""
    return os.path.join(map_source(path), "map", name)


def unit_positions(path):
    """
    {province: (x, y)} in map pixels, from `map/positions.txt`.

    This is the anchor the game itself draws army stacks on, so counters land
    where a player expects rather than at a computed centroid. The file's y runs
    from the bottom of the map, matching the province bitmap, and is flipped to
    screen orientation by the caller that knows the height.
    """
    target = _map_file(path, "positions.txt")
    if not os.path.isfile(target):
        return {}
    out = {}
    for key, block in _read_clausewitz(target):
        if not isinstance(block, dict):
            continue
        # A handful of provinces carry a positions block with no `unit` entry --
        # Ghazni and Manila among them -- so fall back through the other
        # anchors the file gives before giving up on the province.
        spot = None
        for anchor in ("unit", "text_position", "building_construction",
                       "military_construction", "factory", "city", "town"):
            candidate = block.get(anchor)
            if isinstance(candidate, dict) and "x" in candidate:
                spot = candidate
                break
        if spot is None:
            continue
        try:
            out[int(key)] = (to_float(spot.get("x"), 0.0), to_float(spot.get("y"), 0.0))
        except (TypeError, ValueError):
            continue
    return out


def province_anchors(width, runs, wanted):
    """
    A point inside each of `wanted`, taken from the run-length raster.

    `map/positions.txt` is the game's own anchor for army counters and stays
    the first choice, but a mod is free to ship a stripped one: Ferrum Mare
    gives 3,450 provinces a positions block and a usable anchor to 178 of
    them. Every province without one used to drop off the deployment map
    silently, which on that mod meant almost all of them.

    The bitmap is already in hand, so the fallback is the province's own
    pixels -- the one nearest their centroid, which for a crescent or an
    archipelago keeps the marker on the province instead of in the bay it
    wraps around. Where `positions.txt` does give an anchor the two agree to
    within a pixel or so, which is what makes it safe to mix them on one map.

    Coordinates come back in downsampled grid units, the space
    `positions.txt` is scaled into, and point at the centre of a cell.
    """
    if not width or not wanted:
        return {}

    def walk():
        """(province, x, y) for every raster cell belonging to `wanted`."""
        at = 0
        for pid, count in runs:
            if pid in wanted:
                for i in range(at, at + count):
                    yield pid, i % width, i // width
            at += count

    # Two passes rather than one, so nothing holds a province's pixels: at
    # full scale the grid is twelve million cells and the land alone would be
    # a few hundred megabytes of coordinate tuples.
    totals = {}
    for pid, x, y in walk():
        got = totals.get(pid)
        if got is None:
            totals[pid] = [x, y, 1]
        else:
            got[0] += x
            got[1] += y
            got[2] += 1
    middle = {pid: (sx / n, sy / n) for pid, (sx, sy, n) in totals.items()}

    best = {}
    for pid, x, y in walk():
        cx, cy = middle[pid]
        far = (x - cx) ** 2 + (y - cy) ** 2
        if pid not in best or far < best[pid][0]:
            best[pid] = (far, x, y)
    return {pid: [round(x + 0.5, 1), round(y + 0.5, 1)]
            for pid, (_far, x, y) in best.items()}


def sea_provinces(path):
    """Province ids the map treats as water, from `map/default.map`."""
    target = _map_file(path, "default.map")
    if not os.path.isfile(target):
        return frozenset()
    hit = re.search(r"sea_starts\s*=\s*\{([^}]*)\}", _plain(target))
    if not hit:
        return frozenset()
    return frozenset(int(n) for n in hit.group(1).split() if n.isdigit())


def province_names(path):
    """{province id: name} from `map/definition.csv`."""
    target = _map_file(path, "definition.csv")
    if not os.path.isfile(target):
        return {}
    out = {}
    with open(target, "rb") as fh:
        next(fh, None)
        for line in fh:
            bits = line.decode("latin-1").split(";")
            if len(bits) < 5:
                continue
            try:
                pid = int(bits[0])
            except ValueError:
                continue
            name = bits[4].strip()
            if name and name.lower() != "x":
                out[pid] = name
    return out


def province_raster(path, scale=4):
    """
    The province bitmap, downsampled, as (width, height, runs).

    `runs` is [(province id, pixel count), ...] in reading order, which is how
    the report ships a map small enough to embed: the bitmap is 5616x2160 and
    36 MB, but province areas are contiguous, so a quarter-scale grid run-length
    encodes to about 130 KB and still shows every province in the game.

    Only the sampled rows are read, so this costs a tenth of a second rather
    than the minute a full decode would take. The result is kept next to the
    parsed saves in the temp folder, because a mod's map does not change between
    runs and half a second is most of what is left once the saves are cached.
    """
    bmp = _map_file(path, "provinces.bmp")
    csv_path = _map_file(path, "definition.csv")
    if not (os.path.isfile(bmp) and os.path.isfile(csv_path)):
        return 0, 0, []

    slot = _raster_slot(bmp, csv_path, scale)
    if slot and os.path.isfile(slot):
        try:
            with open(slot, "rb") as fh:
                return pickle.loads(zlib.decompress(fh.read()))
        except Exception:
            pass                      # a bad entry just means decoding it again

    # Keyed by the three bytes as the bitmap stores them -- blue, green, red --
    # so a pixel is looked up by slicing the row rather than by unpacking it
    # into a tuple of three integers three million times.
    colour = {}
    with open(csv_path, "rb") as fh:
        next(fh, None)
        for line in fh:
            bits = line.decode("latin-1").split(";")
            if len(bits) < 4:
                continue
            try:
                colour[bytes((int(bits[3]), int(bits[2]), int(bits[1])))] = \
                    int(bits[0])
            except ValueError:
                continue

    with open(bmp, "rb") as fh:
        head = fh.read(54)
        if head[:2] != b"BM":
            return 0, 0, []
        offset = struct.unpack("<I", head[10:14])[0]
        width, height = struct.unpack("<ii", head[18:26])
        bpp = struct.unpack("<H", head[28:30])[0]
        if bpp != 24:
            return 0, 0, []
        stride = ((width * bpp + 31) // 32) * 4
        out_w, out_h = width // scale, height // scale
        grid = array.array("i", bytes(4 * out_w * out_h))
        at = 0
        step = scale * 3
        span = out_w * step
        look = colour.get
        for oy in range(out_h):
            # Rows are stored top-down here despite the positive height a
            # bottom-up BMP declares: file row 168 holds Sitka, whose own
            # position is 168 rows from the top. Flipping would put Alaska in
            # the southern ocean.
            fh.seek(offset + (oy * scale) * stride)
            row = fh.read(stride)
            # Provinces are contiguous, so a pixel almost always repeats the one
            # to its left. Comparing three bytes is cheaper than a dict lookup,
            # and skips nine in ten of them.
            seen, pid = None, 0
            for i in range(0, span, step):
                key = row[i:i + 3]
                if key != seen:
                    seen = key
                    pid = look(key, 0)
                grid[at] = pid
                at += 1

    made = (out_w, out_h, [(pid, sum(1 for _ in run))
                           for pid, run in groupby(grid)])
    if slot:
        try:
            os.makedirs(os.path.dirname(slot), exist_ok=True)
            with open(slot, "wb") as fh:
                fh.write(zlib.compress(pickle.dumps(made, protocol=5), 1))
        except Exception:
            pass                      # caching is an optimisation, not a duty
    return made


def _raster_slot(bmp, csv_path, scale):
    """Where this map's decoded form lives, keyed by the two files it comes
    from and the scale it was decoded at."""
    try:
        a, b = os.stat(bmp), os.stat(csv_path)
    except OSError:
        return None
    # The trailing number is this decoder's version. Bump it when what comes
    # out of the same two files changes, or a stale entry outlives the change.
    key = hashlib.md5(
        f"{os.path.abspath(bmp)}|{a.st_size}|{int(a.st_mtime)}"
        f"|{b.st_size}|{int(b.st_mtime)}|{scale}|2".encode("utf-8")).hexdigest()
    return os.path.join(tempfile.gettempdir(), "vic2_analyzer_cache",
                        "map_" + key + ".pkl")


def government_flag_types(path):
    """
    {government: (flag variant, holds elections)} from common/governments.txt.

    Both halves matter. `flagType` alone cannot pick a flag, because absolute
    monarchy, Prussian constitutionalism and HM's Government all declare
    `flagType = monarchy` -- vanilla does the same -- while the game plainly
    flies different flags for them. What separates them is whether the
    government holds elections, and that is the line the game draws: a
    constitutional monarchy flies the national flag, an absolute one the
    imperial or legitimist variant. Germany is the clean case, black-red-gold
    under a constitutional monarchy against the black-white-red empire flag
    under an absolute one.
    """
    target = _resolved_file(path, "common", "governments.txt")
    if not os.path.isfile(target):
        return {}
    out = {}
    for name, block in _read_clausewitz(target):
        if not isinstance(block, dict):
            continue
        out[name] = (unquote(str(block.get("flagType", ""))),
                     str(block.get("election", "no")).lower() == "yes")
    return out


def flag_suffixes(government, styles):
    """
    Flag file suffixes to try, best first, for a government.

    Fitted to what the game actually displays rather than to `flagType`, which
    cannot be the whole story: in one 1908 save Germany and Japan share both a
    government (HM's Government) and a ruling party ideology (reactionary) and
    still fly different files, and a democratic United States under a communist
    party flies the plain national flag rather than the communist one.

    Of the eight great powers in that save, seven fly the plain `TAG.tga`. Only
    an autocracy -- `flagType = monarchy` with no elections -- reliably takes a
    variant. Germany is a standing exception: it shows black-red-gold, which is
    `GER_republic.tga`, and nothing in the files distinguishes it from Japan.
    """
    variant, elects = styles.get(government, ("", True))
    if variant == "monarchy" and not elects:
        return ["_monarchy", ""]
    if variant in ("communist", "fascist"):
        return ["_" + variant, ""]
    return ["", "_republic"]


def _read_tga(target):
    """
    (width, height, rgb bytes) from a Vic2 flag.

    Flags come as uncompressed (type 2) or run-length encoded (type 10) TGA at
    24 or 32 bits. A handful are 8-bit greyscale, which nothing here wants, and
    those return None so the caller can fall back to a plain colour.
    """
    with open(target, "rb") as fh:
        blob = fh.read()
    if len(blob) < 18:
        return None
    idlen, cmaptype, imgtype = blob[0], blob[1], blob[2]
    width, height, bpp, descriptor = struct.unpack("<HHBB", blob[12:18])
    if imgtype not in (2, 10) or bpp not in (24, 32) or not width or not height:
        return None
    at = 18 + idlen
    if cmaptype:
        at += struct.unpack("<H", blob[5:7])[0] * (blob[7] // 8)
    step = bpp // 8
    want = width * height
    if imgtype == 2:
        px = blob[at:at + want * step]
    else:
        buf = bytearray()
        while len(buf) < want * step and at < len(blob):
            packet = blob[at]
            at += 1
            count = (packet & 0x7F) + 1
            if packet & 0x80:
                buf += blob[at:at + step] * count
                at += step
            else:
                buf += blob[at:at + count * step]
                at += count * step
        px = bytes(buf)
    if len(px) < want * step:
        return None
    rgb = bytearray(want * 3)
    for i in range(want):                       # stored BGR(A)
        s = i * step
        rgb[i * 3] = px[s + 2]
        rgb[i * 3 + 1] = px[s + 1]
        rgb[i * 3 + 2] = px[s]
    if not (descriptor & 0x20):                 # rows run bottom-up
        stride = width * 3
        rgb = bytearray(b"".join(
            bytes(rgb[y * stride:(y + 1) * stride])
            for y in range(height - 1, -1, -1)))
    return width, height, bytes(rgb)


def _write_png(width, height, rgb):
    """Minimal truecolour PNG: IHDR, one IDAT, IEND, no row filtering."""
    raw = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3]
                   for y in range(height))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def _flag_roots(path):
    """The mod's flag folder, then the base game's, which is where most live."""
    roots = [os.path.join(path, "gfx", "flags")]
    parts = os.path.normpath(path).split(os.sep)
    if len(parts) >= 2 and parts[-2].lower() == "mod":
        roots.append(os.path.join(os.sep.join(parts[:-2]), "gfx", "flags"))
    return [r for r in roots if os.path.isdir(r)]


def _shrink(width, height, rgb, target):
    """Nearest-neighbour downscale. Flags render about 34px wide, so the source
    93x64 is four times more pixel than any of them needs."""
    if width <= target:
        return width, height, rgb
    out_w = target
    out_h = max(1, round(height * target / width))
    out = bytearray(out_w * out_h * 3)
    for y in range(out_h):
        sy = min(height - 1, y * height // out_h)
        row = sy * width * 3
        for x in range(out_w):
            sx = min(width - 1, x * width // out_w)
            i, j = (y * out_w + x) * 3, row + sx * 3
            out[i:i + 3] = rgb[j:j + 3]
    return out_w, out_h, bytes(out)


def flag_images(path, wanted, governments=None, width=46):
    """
    {tag: PNG data URI} for the tags asked for, converted from the mod's TGAs.

    Which variant a country flies depends on its government -- `flagType` in
    governments.txt names it -- so a communist Russia gets the communist flag.
    The mod's own folder wins over the base game's, which is how a mod replaces
    a flag without shipping all 1,300.
    """
    governments = governments or {}
    types = government_flag_types(path)
    roots = _flag_roots(path)
    out = {}
    for tag in wanted:
        names = [tag + s for s in flag_suffixes(governments.get(tag, ""), types)]
        for name in names:
            found = None
            for root in roots:
                candidate = os.path.join(root, name + ".tga")
                if os.path.isfile(candidate):
                    found = candidate
                    break
            if not found:
                continue
            try:
                image = _read_tga(found)
            except (OSError, struct.error, IndexError):
                image = None
            if image:
                out[tag] = ("data:image/png;base64,"
                            + base64.b64encode(
                                _write_png(*_shrink(*image, width))).decode())
                break
    return out


def text_localisation(path, wanted):
    """
    {key: english} for an arbitrary set of localisation keys.

    `read_localisation` keeps only country-shaped keys because that is all the
    map needs; the technology tree wants tech names, area headings and modifier
    labels, which look like anything.

    The mod is read first and the base game after it, and the first definition
    of a key wins -- so a mod that renames something keeps its own name, and a
    partial mod that only adds files still gets the game's names for everything
    it left alone.
    """
    wanted = set(wanted)
    out = {}
    for root in (path, base_game_path(path)):
        if not root:
            continue
        folder = os.path.join(root, "localisation")
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".csv"):
                continue
            try:
                with open(os.path.join(folder, name), "rb") as fh:
                    text = fh.read().decode("cp1252", "replace")
            except OSError:
                continue
            for line in text.splitlines():
                key, _, rest = line.partition(";")
                key = key.strip()
                if key in wanted and key not in out:
                    english = rest.split(";", 1)[0].strip()
                    if english:
                        out[key] = english
    return out


# Everything inside a culture group that is a block but not a culture.
_NOT_A_CULTURE = {"color", "unit", "union", "leader", "is_overseas"}


def culture_names(path):
    """
    {culture: the name the game shows}, e.g. nanfaren -> Nanfaren.

    `common/cultures.txt` nests cultures inside culture groups, one block each
    alongside the group's own `union`, `leader` and `unit` entries, so a block
    is a culture when it is none of those. The names themselves are ordinary
    localisation keys.

    Worth having because a save writes the key and nothing else: a report
    without this lists China's people as `nanfaren` and `beifaren`.
    """
    keys = []
    for root in (base_game_path(path), path):
        if not root:
            continue
        target = os.path.join(root, "common", "cultures.txt")
        if not os.path.isfile(target):
            continue
        for _group, block in _read_clausewitz(target):
            if not isinstance(block, dict):
                continue
            for name, body in block.items():
                if name.startswith("_") or name in _NOT_A_CULTURE:
                    continue
                if isinstance(body, dict) or (isinstance(body, list)
                                              and body and isinstance(body[0], dict)):
                    keys.append(name)
    if not keys:
        return {}
    return {k: v for k, v in text_localisation(path, keys).items() if v}


def _top_level_keys(path, folder):
    """Every `name = {` at the start of a line, across base game and mod."""
    out = set()
    for target in _resolved_files(path, folder).values():
        for m in re.finditer(r"^(\w+)\s*=\s*\{", _plain(target), re.M):
            out.add(m.group(1))
    return out


def display_names(path):
    """
    {key: the name the game shows} for the bare keys a save writes down.

    A save records a good, a unit type, a pop type and a technology by its key
    and nothing else, so a report built from saves alone lists `small_arms`,
    `clipper_transport` and `post_napoleonic_thought`. All four are ordinary
    localisation keys, and a mod is free to rename any of them -- IGoR's
    `cattle` is Livestock -- so the names have to come from the mod's own
    files rather than from tidying the key up.

    One lookup for all four because they share a namespace in the game's own
    localisation and there is nothing to gain from four passes over it.
    """
    keys = set()
    for root in (base_game_path(path), path):
        if not root:
            continue
        target = os.path.join(root, "common", "goods.txt")
        if os.path.isfile(target):
            for _category, block in _read_clausewitz(target):
                if isinstance(block, dict):
                    keys |= {g for g in block if not g.startswith("_")}
        folder = os.path.join(root, "poptypes")
        if os.path.isdir(folder):
            keys |= {f[:-4] for f in _files(folder)}
        target = os.path.join(root, "common", "cb_types.txt")
        if os.path.isfile(target):
            for name, block in _read_clausewitz(target):
                if isinstance(block, dict):
                    keys.add(name)
    keys |= _top_level_keys(path, "units")
    keys |= _top_level_keys(path, "technologies")
    if not keys:
        return {}
    return {k: v for k, v in text_localisation(path, keys).items() if v}


# Bookkeeping rather than an effect a player would read off the tech.
_TECH_SKIP = {"area", "year", "cost", "ai_chance", "unciv_military",
              "unciv_naval", "unciv_economic", "unciv_culture"}


def _flatten_effects(block, skip, prefix=""):
    """[(label key, value)] for every field on `block` that isn't bookkeeping."""
    out = []
    for key, val in block.items():
        if key.startswith("_") or key in skip:
            continue
        if isinstance(val, dict):
            out.extend(_flatten_effects(val, skip, prefix + key + ": "))
        elif isinstance(val, list):
            for item in val:
                if not isinstance(item, (dict, list)):
                    out.append((prefix + key, str(item)))
        else:
            out.append((prefix + key, str(val)))
    return out


def _effects(block, prefix=""):
    """[(label key, value)] for everything on a tech that is an actual effect."""
    return _flatten_effects(block, _TECH_SKIP, prefix)


_INVENTION_SKIP = {"icon", "limit", "chance"}


def _invention_effects(block):
    """
    [(label key, value)] for what an invention itself grants.

    Unlike a tech, an invention's modifiers can sit at its own top level or be
    tucked inside an `effect = {}` sub-block -- `_find_mob_size` above already
    has to check both places for the same reason. `effect` is unwrapped into
    the same flat list here rather than nested under an "effect:" prefix,
    which would just be noise every invention repeats.
    """
    if not isinstance(block, dict):
        return []
    out = _flatten_effects({k: v for k, v in block.items() if k != "effect"},
                            _INVENTION_SKIP)
    nested = block.get("effect")
    if isinstance(nested, dict):
        out.extend(_flatten_effects(nested, _INVENTION_SKIP))
    return out


def invention_index(path):
    """
    {invention: {"requires": set of techs its `limit` needs,
                 "effects": [(label, value), ...] it grants}}, for every
    invention whose `limit` names at least one tech.

    An invention with no tech requirement never shows up under any tech's
    "makes available" list, so `technology_tree` has nothing to attach it
    to -- it's excluded here for the same reason `invention_rules` (built
    separately, for mobilisation) only cares about the inventions it can
    actually gate.
    """
    out = {}
    for target in _resolved_files(path, "inventions").values():
        raw = _COMMENT.sub("", open(target, "rb").read().decode("latin-1"))
        for name, block in _read_clausewitz(target):
            reqs, _tags, _invs = _limit_of(_block_text(raw, name))
            if reqs:
                out[name] = {"requires": reqs, "effects": _invention_effects(block)}
    return out


def technology_tree(path, rules=None):
    """
    The tech tree as the game draws it: five folders, columns, then techs.

    `technologies/*.txt` gives one file per category -- army, navy, commerce,
    culture, industry -- and every tech names the `area` it sits in, which is
    the column of the in-game screen. File order inside an area is the order the
    techs appear down that column, so it is kept.

    Each tech carries its year, cost, its effects, and the inventions gated
    behind it -- each with its own effects too -- which come from the
    invention `limit` and body already parsed by `invention_index`.
    """
    files = _resolved_files(path, "technologies")
    if not files:
        return {}

    rule_map = rules if rules is not None else invention_index(path)
    gated = {}
    inv_effects = {}
    for name, info in rule_map.items():
        # `rules` is a public parameter; accept the older {name: set(techs)}
        # shape too, in case anything still passes it that way.
        techs = info["requires"] if isinstance(info, dict) else info
        inv_effects[name] = info["effects"] if isinstance(info, dict) else []
        for tech in techs:
            gated.setdefault(tech, []).append(name)

    tree = {}
    keys = set()
    for fname in sorted(files):
        category = fname[:-4].replace("_tech", "")
        areas = []
        index = {}
        for key, block in _read_clausewitz(files[fname]):
            if not isinstance(block, dict):
                continue
            area = unquote(str(block.get("area", "other")))
            if area not in index:
                index[area] = {"area": area, "techs": []}
                areas.append(index[area])
            effects = _effects(block)
            index[area]["techs"].append({
                "key": key,
                "year": to_int(block.get("year"), 0),
                "cost": to_int(block.get("cost"), 0),
                "effects": effects,
                "inventions": sorted(gated.get(key, [])),
            })
            keys.add(key)
            keys.add(area)
            for label, _v in effects:
                keys.add(label.split(":")[0].strip())
            for inv in gated.get(key, ()):
                keys.add(inv)
                for label, _v in inv_effects.get(inv, ()):
                    keys.add(label.split(":")[0].strip())
        if areas:
            tree[category] = areas
            keys.add(category)

    names = text_localisation(path, keys)
    for category, areas in tree.items():
        for column in areas:
            column["label"] = names.get(column["area"]) or _pretty(column["area"])
            for tech in column["techs"]:
                tech["name"] = names.get(tech["key"]) or _pretty(tech["key"])
                tech["effects"] = [
                    [names.get(label) or _pretty(label), value]
                    for label, value in tech["effects"]
                ]
                tech["inventions"] = [
                    [inv, names.get(inv) or _pretty(inv),
                     [[names.get(lbl) or _pretty(lbl), val]
                      for lbl, val in inv_effects.get(inv, ())]]
                    for inv in tech["inventions"]
                ]
    return {"tree": tree,
            "categories": {c: names.get(c) or _pretty(c) for c in tree}}


def _pretty(key):
    """A readable label for a key the localisation files do not carry."""
    return key.replace("_", " ").strip().capitalize()


def formation_decisions(path):
    """
    {formed tag: {tags allowed to form it}}, from the mod's own decisions.

    A formation is a decision whose effect is `change_tag`, and whose
    `potential` names the tags that may take it -- `form_italy` is open to SAR
    and SIC, `form_germany` to NGF. Nothing records that the decision was
    *taken*: the country keeps its own flags through the tag change, and the
    file that forms Germany, Italy, Scandinavia and Romania sets no country
    flag at all. So this says who could have formed what, not who did. Which
    campaign it happened in still has to come off the province ledger.
    """
    out = {}
    for target in _resolved_files(path, "decisions").values():
        text = _plain(target)
        for block in _brace_blocks(text):
            made = re.search(r"change_tag(?:_no_core_switch)?\s*=\s*([A-Z0-9]{3})\b",
                             block)
            if not made:
                continue
            potential = _block_text(block, "potential")
            from_tags = set(re.findall(r"(?<![\w_])tag\s*=\s*([A-Z0-9]{3})\b",
                                       potential))
            if from_tags:
                out.setdefault(made.group(1), set()).update(from_tags)
    return out


def _brace_blocks(text):
    """Every second-level `name = { ... }` body, which is where a decision is."""
    out = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
            if depth == 2:
                start = i
        elif ch == "}":
            if depth == 2 and start is not None:
                out.append(text[start:i])
                start = None
            depth -= 1
    return out


def load_mod(path):
    """
    Returns {
      'tech_mob':      {tech_name: mobilisation_size},
      'inventions':    [ (name, mobilisation_size), ... ] in index order,
      'nv_mob':        {national_value_name: mobilisation_size},
      'tech_count':    int,
      'invention_count': int,
    }
    Raises FileNotFoundError if the folder has neither techs nor inventions.
    """
    path = os.path.expanduser(os.path.expandvars(path))
    # Both folders resolve file by file against the game underneath, the way
    # the engine does: a mod that ships one invention file still runs on the
    # game's other four, and reading only the mod folder lost them.
    tech_files = _resolved_files(path, "technologies")
    inv_files = _resolved_files(path, "inventions")
    nv_file = _resolved_file(path, "common", "nationalvalues.txt")

    tech_mob, tech_count = {}, 0
    for fname in sorted(tech_files, key=str.lower):
        for name, block in _read_clausewitz(tech_files[fname]):
            tech_count += 1
            size = _find_mob_size(block)
            if size:
                tech_mob[name] = size

    # Inventions are matched by their requirements rather than by the save's
    # numeric indices. Those indices depend on engine load order, which cannot
    # be reconstructed reliably from a mod folder -- an install may load files
    # this folder does not contain. Requirements are stable and checkable.
    invention_rules = {}
    for fname in sorted(inv_files, key=str.lower):
        raw = _COMMENT.sub("", open(inv_files[fname], "rb")
                           .read().decode("latin-1"))
        for name, block in _read_clausewitz(inv_files[fname]):
            size = _find_mob_size(block)
            if not size:
                continue
            body = _block_text(raw, name)
            reqs, tags, invs = _limit_of(body)
            base, blockers = _chance_floor(body)
            invention_rules[name] = {
                "size": size, "techs": reqs, "tags": tags,
                "requires": invs, "base": base, "blockers": blockers,
            }
    inventions = [(n, r["size"]) for n, r in invention_rules.items()]

    event_mob = {}
    ev_file = _resolved_file(path, "common", "event_modifiers.txt")
    if os.path.isfile(ev_file):
        for name, block in _read_clausewitz(ev_file):
            size = _find_mob_size(block)
            if size:
                event_mob[name] = size

    nv_mob = {}
    if os.path.isfile(nv_file):
        for name, block in _read_clausewitz(nv_file):
            size = _find_mob_size(block)
            if size:
                nv_mob[name] = size

    if not tech_count and not inventions:
        raise FileNotFoundError(
            f"{path} has no technologies/ or inventions/ folder. Point "
            f"--mod-path at the folder that contains them (the mod root, or "
            f"the Victoria 2 install folder for vanilla)."
        )

    strata = read_poptypes(path)
    reform_sizes, reform_groups = reform_mob(path)
    triggers = triggered_mob(path)
    reform_names = watched_reforms(reform_sizes, reform_groups, triggers)

    # A modifier is either looked up by name in the country's own list or
    # judged from its trigger. Names that are both are judged, so that the two
    # paths cannot both count the same thing.
    judged = {name for name, _s, _i, _t in triggers}
    event_mob = {k: v for k, v in event_mob.items() if k not in judged}
    modifier_impacts = {k: v for k, v in modifier_mob_impacts(path).items()
                        if k not in judged}

    return {
        "path": path,
        "invention_sequence": invention_sequence(path),
        "party_sequence": party_sequence(path),
        "localisation": read_localisation(path),
        "base_prices": base_prices(path),
        "country_order": country_order(path),
        "formations": formation_decisions(path),
        "culture_names": culture_names(path),
        "display_names": display_names(path),
        "province_names": province_names(path),
        "province_regions": province_regions(path),
        "state_names": state_names(path),
        "unit_kinds": unit_kinds(path),
        "naval_units": naval_units(path),
        "naval_effects": naval_invention_effects(path),
        "naval_tech_effects": naval_tech_effects(path),
        "technology": technology_tree(path),
        "mob_impacts": mobilization_impacts(path),
        "modifier_impacts": modifier_impacts,
        "reform_mob": reform_sizes,
        "reform_names": reform_names,
        "static_mob": static_mob(path),
        "triggered_mob": triggers,
        "culture_groups": culture_groups(path),
        "continents": continents(path),
        # Set by index_base_for once a save is in hand; None means the indices
        # could not be decoded and inventions fall back to requirement matching.
        "index_base": None,
        "defines": read_defines(path),
        "strata": strata,
        "pop_types": frozenset(strata),
        "mob_types": mobilizable_types(strata),
        "invention_rules": invention_rules,
        "event_mob": event_mob,
        "tech_mob": tech_mob,
        "inventions": inventions,
        "nv_mob": nv_mob,
        "tech_count": tech_count,
        "invention_count": len(inventions),
    }


def invention_sequence(path):
    """
    Every invention in engine load order, so the save's numeric indices decode.

    Saves store `active_inventions` as bare indices into the engine's global
    invention array. The array is built by walking `inventions/` -- files in
    plain ASCII order, so uppercase file names sort before lowercase, and
    inventions in the order they appear inside each file. Indices are 1-based.

    That ordering is a reconstruction, so `validate_indices` checks it against
    the save before anything trusts it: an invention a nation holds must be one
    whose `limit` that nation actually meets.
    """
    files = _resolved_files(path, "inventions")
    if not files:
        return []
    seq = []
    for fname in sorted(files):
        full = files[fname]
        with open(full, "rb") as fh:
            raw = _COMMENT.sub("", fh.read().decode("latin-1"))
        for name, block in _read_clausewitz(full):
            reqs, tags, _invs = _limit_of(_block_text(raw, name))
            seq.append({"name": name, "size": _find_mob_size(block),
                        "techs": reqs, "tags": tags})
    return seq


def validate_indices(mod, nations, base=1):
    """
    How often the decoded indices name an invention a nation could not have.

    Returns (violations, total). A correct ordering leaves almost none -- a
    handful survive because events and decisions can grant an invention whose
    `limit` the nation does not meet. A wrong ordering leaves tens of percent.
    """
    seq = mod.get("invention_sequence") or []
    bad = total = 0
    for nat in nations:
        techs = set(nat.get("tech_list", ()))
        tag = nat.get("tag", "")
        for idx in nat.get("invention_ids", ()):
            total += 1
            j = idx - base
            if j < 0 or j >= len(seq):
                bad += 1
                continue
            rule = seq[j]
            if not rule["techs"] <= techs:
                bad += 1
            elif rule["tags"] and tag not in rule["tags"]:
                bad += 1
    return bad, total


def index_base_for(mod, nations):
    """
    The index base that decodes this save, or None when neither one fits.

    Anything above a few percent of impossible inventions means the
    reconstructed load order is wrong for this install, and the caller should
    fall back to matching inventions by their requirements.
    """
    best, best_rate = None, 1.0
    for base in (1, 0):
        bad, total = validate_indices(mod, nations, base)
        if not total:
            return None
        rate = bad / total
        if rate < best_rate:
            best, best_rate = base, rate
    return best if best_rate <= 0.05 else None


def attainable_inventions(mod, all_nations):
    """
    Which mobilisation inventions any nation can actually get.

    An invention nobody meets the requirements for is unobtainable, and so is
    one whose acquisition chance is driven to zero because it depends on an
    unobtainable invention. IGoR's `non_interventionism` is the second case: its
    chance is base 95 with a -95 modifier that applies whenever the nation lacks
    `total_war_mobilisation`, and nothing in the save can reach that, so the
    chance is always zero.
    """
    rules = mod.get("invention_rules", {})
    live = {}
    for name, rule in rules.items():
        eligible = any(
            rule["techs"] <= nat_techs and (not rule["tags"] or tag in rule["tags"])
            for tag, nat_techs in all_nations.items()
        )
        live[name] = eligible

    # Settle chain effects: a blocker that is dead makes its dependant dead too.
    for _pass in range(len(rules) + 1):
        changed = False
        for name, rule in rules.items():
            if not live[name]:
                continue
            if any(not live.get(req, False) for req in rule["requires"]):
                live[name] = False
                changed = True
                continue
            base = rule["base"]
            # Only judge the chance when a dead invention actually drags it
            # down. A base of 0 is normal -- plenty of inventions start at zero
            # and rely on positive modifiers to become possible.
            dead_blockers = [f for f, blocked in rule["blockers"]
                             if not live.get(blocked, True)]
            if base is None or not dead_blockers:
                continue
            if base + sum(dead_blockers) <= 0:
                live[name] = False
                changed = True
        if not changed:
            break
    return {n for n, ok in live.items() if ok}


def held_inventions(nation, mod):
    """
    The inventions a nation actually holds, by name.

    None when the save's numeric indices could not be decoded for this install:
    the requirement-matching fallback answers a different question -- which
    inventions the nation *could* have -- and a trigger asking whether it holds
    one deserves "cannot tell" rather than that.
    """
    base = mod.get("index_base")
    if base is None:
        return None
    seq = mod.get("invention_sequence") or ()
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
        value = mod["tech_mob"].get(tech, 0.0)
        if value:
            parts.append(("tech", tech, value))

    # Which inventions the nation holds, both for the ones that grant
    # mobilisation size and for the triggered modifiers that ask about one.
    inventions = held_inventions(nation, mod)
    base = mod.get("index_base")
    if base is not None:
        # The save says exactly which inventions this nation rolled. Nothing
        # else does: two nations with identical technology routinely differ,
        # because inventions fire on a chance roll.
        seq = mod["invention_sequence"]
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
        for name, rule in mod.get("invention_rules", {}).items():
            if live is not None and name not in live:
                continue
            if not rule["techs"] <= techs:
                continue
            if rule["tags"] and tag not in rule["tags"]:
                continue
            parts.append(("invention", name, rule["size"]))

    nv = nation.get("nationalvalue", "")
    value = mod["nv_mob"].get(nv, 0.0)
    if value:
        parts.append(("national value", nv, value))

    for name in nation.get("modifiers", ()):
        value = mod.get("event_mob", {}).get(name, 0.0)
        if value:
            parts.append(("event modifier", name, value))

    # Reforms. The save writes the chosen option as a plain line in the country
    # block -- `conscription=mandatory_service` -- so this needs no judgement at
    # all; it was simply never read. GFM's conscription ladder is worth up to
    # +6%, which is more than its whole technology tree grants.
    for reform, option in (nation.get("reforms") or {}).items():
        value = (mod.get("reform_mob") or {}).get((reform, option), 0.0)
        if value:
            parts.append(("reform", f"{reform} = {option}", value))

    # The flat penalty every uncivilized country carries. It is a static
    # modifier: the engine applies it to anyone uncivilized and writes nothing
    # down. -10% in the base game, -20% in Divergences of Darkness, absent in
    # IGoR and Ferrum Mare.
    if str(nation.get("civilized", "")).lower() == "no":
        value = (mod.get("static_mob") or {}).get("unciv_nation", 0.0)
        if value:
            parts.append(("uncivilized", "unciv_nation", value))

    # Triggered modifiers, which cover the old revanchism ladder and the old
    # player-unciv special case as well as everything neither of them reached:
    # GFM alone hands AI France +13%, Prussia +10% before 1880, Afghanistan
    # +20% and the smaller South American nations up to +8.5%.
    for name, size, _impact, trigger in mod.get("triggered_mob", ()):
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
    for name, size, _impact, trigger in mod.get("triggered_mob", ()):
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
             | set(mod.get("reform_names") or ())
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


def rate_for(nation, mod, live=None, world=None):
    """
    Sum of every mobilisation size contribution a nation has, floored at zero.

    Contributions can be strongly negative -- IGoR nerfs China's mobilisation
    by -100 -- and the engine clamps the result at zero rather than letting it
    wrap into something meaningful.
    """
    return max(0.0, sum(value for _kind, _name, value in
                        breakdown(nation, mod, live, world)))


def impact_for(nation, mod, world=None, inventions=False):
    """
    A nation's mobilization_impact from every national modifier that moves it.

    The ruling party's war policy is the base and `finalize` adds that; this is
    what sits on top -- event modifiers, which a save lists by name, and
    triggered modifiers, which it does not.
    """
    if inventions is False:
        inventions = held_inventions(nation, mod)
    total = 0.0
    for name in nation.get("modifiers", ()):
        total += (mod.get("modifier_impacts") or {}).get(name, 0.0)
    for name, _size, impact, trigger in mod.get("triggered_mob", ()):
        if not impact:
            continue
        if _trigger_ok(trigger, nation, mod, world, inventions):
            total += impact
    return total

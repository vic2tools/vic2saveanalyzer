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

import os
import re
import struct

from v2parse import Tokens, as_list, parse_block, to_float, unquote

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
    fname = os.path.join(path, "common", "defines.lua")
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
    folder = os.path.join(path, "poptypes")
    if not os.path.isdir(folder):
        return out
    for fname in _files(folder):
        with open(os.path.join(folder, fname), "rb") as fh:
            text = _COMMENT.sub("", fh.read().decode("latin-1"))
        m = re.search(r"(?<![\w.])strata\s*=\s*(\w+)", text)
        if m:
            out[os.path.splitext(fname)[0].lower()] = m.group(1).lower()
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


def _revanchism_ladder(path):
    """
    Triggered modifiers keyed on revanchism, as [(threshold, mobilisation_size)].

    Only the revanchism trigger is handled: evaluating arbitrary triggers would
    mean reimplementing the script engine, and revanchism is the one that
    actually moves mobilisation size in practice.
    """
    steps = []
    if not os.path.isfile(path):
        return steps
    for _name, block in _read_clausewitz(path):
        size = _find_mob_size(block)
        if not size:
            continue
        trigger = block.get("trigger")
        if not isinstance(trigger, dict):
            continue
        rev = trigger.get("revanchism")
        if rev is None or isinstance(rev, (dict, list)):
            continue
        steps.append((to_float(rev), size))
    steps.sort()
    return steps


def _revanchism_impact_ladder(path):
    """
    The same triggered modifiers, as [(threshold, mobilization_impact)].

    These are evaluated by the engine at runtime rather than written into the
    save's per-country modifier list, so unlike the event modifiers they have to
    be re-derived from the nation's revanchism.
    """
    steps = []
    if not os.path.isfile(path):
        return steps
    for _name, block in _read_clausewitz(path):
        if not isinstance(block, dict) or "mobilization_impact" not in block:
            continue
        trigger = block.get("trigger")
        if not isinstance(trigger, dict):
            continue
        rev = trigger.get("revanchism")
        if rev is None or isinstance(rev, (dict, list)):
            continue
        steps.append((to_float(rev), to_float(block["mobilization_impact"], 0.0)))
    steps.sort()
    return steps


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
    listing = os.path.join(path, "common", "countries.txt")
    if not os.path.isfile(listing):
        return []
    out = []
    entry = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*"?([^"\r\n]+?)"?\s*$', re.M)
    for tag, rel in entry.findall(_plain(listing)):
        target = os.path.join(path, "common", rel.strip().replace("/", os.sep))
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
        target = os.path.join(path, "common", name)
        if not os.path.isfile(target):
            continue
        for key, block in _read_clausewitz(target):
            if isinstance(block, dict) and "mobilization_impact" in block:
                out[key] = to_float(block["mobilization_impact"], 0.0)
    return out


def mobilization_impacts(path):
    """{war policy: mobilization_impact}, out of the mod's own issues.txt."""
    target = os.path.join(path, "common", "issues.txt")
    if not os.path.isfile(target):
        return {}
    body = _plain(target)
    out = {}
    for name in ("jingoism", "pro_military", "anti_military", "pacifism"):
        for block in _named_blocks(body, name):
            hit = re.search(r"mobilization_impact\s*=\s*([-\d.]+)", block)
            if hit:
                out[name] = float(hit.group(1))
                break
    return out


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
    """
    folder = os.path.join(path, "localisation")
    if not os.path.isdir(folder):
        return {}
    wanted = re.compile(r"^[A-Z][A-Z0-9]{2}(_[a-z_]+)?$")
    out = {}
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


def country_colours(path):
    """{tag: '#rrggbb'} from each country file's `color = { r g b }`."""
    listing = os.path.join(path, "common", "countries.txt")
    if not os.path.isfile(listing):
        return {}
    out = {}
    entry = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*"?([^"\r\n]+?)"?\s*$', re.M)
    for tag, rel in entry.findall(_plain(listing)):
        target = os.path.join(path, "common", rel.strip().replace("/", os.sep))
        if not os.path.isfile(target):
            continue
        hit = re.search(r"color\s*=\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}", _plain(target))
        if hit:
            out[tag] = "#%02x%02x%02x" % tuple(int(g) for g in hit.groups())
    return out


def unit_positions(path):
    """
    {province: (x, y)} in map pixels, from `map/positions.txt`.

    This is the anchor the game itself draws army stacks on, so counters land
    where a player expects rather than at a computed centroid. The file's y runs
    from the bottom of the map, matching the province bitmap, and is flipped to
    screen orientation by the caller that knows the height.
    """
    target = os.path.join(path, "map", "positions.txt")
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


def sea_provinces(path):
    """Province ids the map treats as water, from `map/default.map`."""
    target = os.path.join(path, "map", "default.map")
    if not os.path.isfile(target):
        return frozenset()
    hit = re.search(r"sea_starts\s*=\s*\{([^}]*)\}", _plain(target))
    if not hit:
        return frozenset()
    return frozenset(int(n) for n in hit.group(1).split() if n.isdigit())


def province_names(path):
    """{province id: name} from `map/definition.csv`."""
    target = os.path.join(path, "map", "definition.csv")
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
    than the minute a full decode would take.
    """
    bmp = os.path.join(path, "map", "provinces.bmp")
    csv_path = os.path.join(path, "map", "definition.csv")
    if not (os.path.isfile(bmp) and os.path.isfile(csv_path)):
        return 0, 0, []

    colour = {}
    with open(csv_path, "rb") as fh:
        next(fh, None)
        for line in fh:
            bits = line.decode("latin-1").split(";")
            if len(bits) < 4:
                continue
            try:
                colour[(int(bits[1]), int(bits[2]), int(bits[3]))] = int(bits[0])
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
        runs = []
        prev, count = -1, 0
        for oy in range(out_h):
            fh.seek(offset + (height - 1 - oy * scale) * stride)
            row = fh.read(stride)
            for ox in range(out_w):
                i = ox * scale * 3
                pid = colour.get((row[i + 2], row[i + 1], row[i]), 0)
                if pid == prev:
                    count += 1
                else:
                    if count:
                        runs.append((prev, count))
                    prev, count = pid, 1
        if count:
            runs.append((prev, count))
    return out_w, out_h, runs


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
    tech_dir = os.path.join(path, "technologies")
    inv_dir = os.path.join(path, "inventions")
    nv_file = os.path.join(path, "common", "nationalvalues.txt")

    tech_mob, tech_count = {}, 0
    for fname in _files(tech_dir):
        for name, block in _read_clausewitz(os.path.join(tech_dir, fname)):
            tech_count += 1
            size = _find_mob_size(block)
            if size:
                tech_mob[name] = size

    # Inventions are matched by their requirements rather than by the save's
    # numeric indices. Those indices depend on engine load order, which cannot
    # be reconstructed reliably from a mod folder -- an install may load files
    # this folder does not contain. Requirements are stable and checkable.
    invention_rules = {}
    for fname in _files(inv_dir):
        raw = _COMMENT.sub("", open(os.path.join(inv_dir, fname), "rb")
                           .read().decode("latin-1"))
        for name, block in _read_clausewitz(os.path.join(inv_dir, fname)):
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
    ev_file = os.path.join(path, "common", "event_modifiers.txt")
    if os.path.isfile(ev_file):
        for name, block in _read_clausewitz(ev_file):
            size = _find_mob_size(block)
            if size:
                event_mob[name] = size

    ladder = _revanchism_ladder(os.path.join(path, "common", "triggered_modifiers.txt"))
    impact_ladder = _revanchism_impact_ladder(
        os.path.join(path, "common", "triggered_modifiers.txt"))

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

    return {
        "path": path,
        "invention_sequence": invention_sequence(path),
        "party_sequence": party_sequence(path),
        "localisation": read_localisation(path),
        "mob_impacts": mobilization_impacts(path),
        "modifier_impacts": modifier_mob_impacts(path),
        "revanchism_impact_ladder": impact_ladder,
        "party_sequence": party_sequence(path),
        "mob_impacts": mobilization_impacts(path),
        # Set by index_base_for once a save is in hand; None means the indices
        # could not be decoded and inventions fall back to requirement matching.
        "index_base": None,
        "defines": read_defines(path),
        "strata": strata,
        "pop_types": frozenset(strata),
        "mob_types": mobilizable_types(strata),
        "invention_rules": invention_rules,
        "event_mob": event_mob,
        "revanchism_ladder": ladder,
        "player_unciv_mob": player_unciv_mob(path),
        "tech_mob": tech_mob,
        "inventions": inventions,
        "nv_mob": nv_mob,
        "tech_count": tech_count,
        "invention_count": len(inventions),
    }


def player_unciv_mob(path):
    """
    Triggered modifiers that hand a *player-controlled* uncivilized nation extra
    mobilisation size, as [(name, size, excluded country flags)].

    IGoR's `player_unciv_mobilization` is +0.02 on `ai = no` and
    `civilized = no`, excluding whoever holds the `china` country flag. Saves
    cannot say who was human -- only the nation that took the save is written to
    the `player` field, so in multiplayer every other human reads as AI -- which
    is why the analyzer takes the list on the command line.
    """
    target = os.path.join(path, "common", "triggered_modifiers.txt")
    out = []
    if not os.path.isfile(target):
        return out
    for name, block in _read_clausewitz(target):
        if not isinstance(block, dict):
            continue
        size = block.get("mobilisation_size")
        trigger = block.get("trigger")
        if size is None or not isinstance(trigger, dict):
            continue
        if str(trigger.get("ai", "")).lower() != "no":
            continue
        if str(trigger.get("civilized", "")).lower() != "no":
            continue
        excluded = set()
        for neg in as_list(trigger.get("NOT")):
            if isinstance(neg, dict) and "has_country_flag" in neg:
                excluded.add(unquote(str(neg["has_country_flag"])))
        out.append((name, to_float(size, 0.0), frozenset(excluded)))
    return out


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
    folder = os.path.join(path, "inventions")
    if not os.path.isdir(folder):
        return []
    names = sorted(f for f in os.listdir(folder) if f.lower().endswith(".txt"))
    seq = []
    for fname in names:
        full = os.path.join(folder, fname)
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


def breakdown(nation, mod, live=None):
    """
    Every contribution to a nation's mobilisation size, as
    [(source_kind, name, value), ...]. `rate_for` is the sum of these.
    """
    parts = []
    for tech in nation["tech_list"]:
        value = mod["tech_mob"].get(tech, 0.0)
        if value:
            parts.append(("tech", tech, value))

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

    rev = nation.get("revanchism", 0.0)
    best = None
    for threshold, value in mod.get("revanchism_ladder", ()):
        if rev >= threshold:
            best = (threshold, value)
    if best:
        parts.append(("revanchism", f"{rev:.3f} >= {best[0]:.2f}", best[1]))

    # Only a human-run uncivilized nation gets this, and the save cannot say who
    # was human, so `is_player` is set from --player-nations.
    if nation.get("is_player") and str(nation.get("civilized", "")).lower() != "yes":
        flags = nation.get("country_flags") or frozenset()
        for name, size, excluded in mod.get("player_unciv_mob", ()):
            if excluded & set(flags):
                continue
            parts.append(("player unciv", name, size))
    return parts


def rate_for(nation, mod, live=None):
    """
    Sum of every mobilisation size contribution a nation has, floored at zero.

    Contributions can be strongly negative -- IGoR nerfs China's mobilisation
    by -100 -- and the engine clamps the result at zero rather than letting it
    wrap into something meaningful.
    """
    return max(0.0, sum(value for _kind, _name, value in
                        breakdown(nation, mod, live)))

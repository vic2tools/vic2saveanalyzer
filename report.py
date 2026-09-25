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
Builds a single self-contained HTML report from the analyzer's rows.

Visual direction is cyanotype: the blueprint process came into use for
engineering and ship drawings in exactly the period the game covers, so the
report is laid out like a drawing sheet -- title block, grid ground, white
linework.
"""

import base64
import gzip
import json
import os
from html import escape as _escape

from dates import year_fraction
from tech_groups import ARMY_LINES, NAVY_LINES
from template import TEMPLATE

METRICS = [
    ("total_pop", "Total population", "count"),
    ("accepted_pop", "Accepted-culture population", "count"),
    ("accepted_pct", "Accepted share", "percent"),
    ("primary_culture_pop", "Primary-culture population", "count"),
    ("avg_literacy", "Average literacy", "fraction"),
    ("avg_literacy_stated", "Literacy in own states", "fraction"),
    ("life_unmet", "Population with life needs unmet", "count"),
    ("life_unmet_pct", "Life needs unmet", "percent"),
    ("starving", "Starving population", "count"),
    ("starving_pct", "Starving share", "percent"),
    ("brigades", "Brigades (all)", "count"),
    ("regular_brigades", "Standing brigades", "count"),
    ("mobilized_brigades", "Mobilized brigades", "count"),
    ("mobilizing", "Mobilizing (queued)", "count"),
    ("brigade_cap", "Brigade cap", "count"),
    ("mobilization_pool", "Mobilizable population", "count"),
    ("mobilization_brigades", "Mobilization ceiling", "count"),
    ("ships", "Ships", "count"),
    ("factory_levels", "Factory levels", "count"),
    ("factory_count", "Factories", "count"),
    ("naval_base_levels", "Naval base levels", "count"),
    ("ports", "Provinces with a naval base", "count"),
    ("max_naval_base", "Largest naval base", "count"),
    ("railroad_levels", "Railroad levels", "count"),
    ("techs", "Technologies", "count"),
    ("prestige", "Prestige", "count"),
    ("provinces", "Provinces", "count"),
    ("states", "States", "count"),
    ("treasury", "Treasury", "count"),
    ("tax_base", "Tax base", "count"),
    ("avg_consciousness", "Average consciousness", "decimal"),
    ("avg_militancy", "Average militancy", "decimal"),
    ("infamy", "Infamy", "decimal"),
    ("pop_poor", "Poor strata", "count"),
    ("pop_middle", "Middle strata", "count"),
    ("pop_rich", "Rich strata", "count"),
]

# Measures nothing in a save holds: they are the rate of change of something
# that is. (derived key, what it is the growth of, what to call it.)
GROWTH_METRICS = [
    ("pop_growth", "total_pop", "Population growth (%/yr)"),
    ("accepted_growth", "accepted_pop", "Accepted-culture growth (%/yr)"),
]

# The same two as a count rather than a rate: how many people, not what
# percentage. A rate flatters a small nation -- three thousand people on a
# hundred thousand outruns a million on eighty million -- and buries who is
# actually adding the most. Measured save to save rather than annualised,
# because the question is what happened between these two readings.
GAIN_METRICS = [
    ("pop_gain", "total_pop", "Population gain (per save)"),
    ("accepted_gain", "accepted_pop", "Accepted-culture gain (per save)"),
]


def growth_series(readings, year_of, span=None):
    """
    A compounded yearly rate from a run of readings, as {date: percent}.

    Growth is a rate, so it needs two readings and the time between them. The
    anchor only moves once a reading is far enough from the last one to say
    something, which also means a nation missing from a save is measured across
    the gap rather than losing its series entirely.

    `readings` is (date, value) in chronological order, `year_of` turns a date
    into a fractional year. Lifted out of `build_report` so the cross-campaign
    block can compute the same measure the same way rather than keeping a
    second copy of this arithmetic that could drift from it.
    """
    if span is None:
        span = MIN_GROWTH_SPAN
    out, anchor = {}, None
    for date, value in readings:
        if value is None or value <= 0:
            continue
        if anchor is not None:
            gap = year_of(date) - year_of(anchor[0])
            if gap >= span:
                out[date] = round(
                    ((value / anchor[1]) ** (1.0 / gap) - 1.0) * 100, 4)
                anchor = (date, value)
            continue
        anchor = (date, value)
    return out


def gain_series(readings):
    """
    The change in a measure from one reading to the next, as {date: delta}.

    Unlike a rate this needs no minimum span: a difference between two readings
    is a fact about those two readings whenever they were taken. The first
    reading has nothing before it and so records no gain.

    `readings` is (date, value) in chronological order.
    """
    out, last = {}, None
    for date, value in readings:
        if value is None:
            continue
        if last is not None:
            out[date] = round(value - last, 4)
        last = value
    return out


# Saves a few days apart say nothing useful about a yearly rate: a fortnight of
# ordinary growth annualises into hundreds of percent. So a reading is only
# taken once this much of a year has passed since the last one, and the ones in
# between are skipped rather than plotted as spikes.
MIN_GROWTH_SPAN = 0.25

# Muted jewel tones and gilt, so series stay apart from each other and from the
# burgundy ground without turning the page into a pie chart.
SERIES_COLOURS = [
    "#E7C464", "#D4553F", "#8FB98C", "#8FA8C8",
    "#D48FA8", "#B5A85C", "#B48FC0", "#EADFC2",
    "#6FA8A0", "#E09A4C", "#9BAF6F", "#A87FA0",
]

CATEGORY_LABELS = {
    "military": "Military",
    "industrial": "Industrial",
    "raw": "Raw materials",
    "consumer": "Consumer",
    "other": "Other",
}

_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _b36(n):
    if n <= 0:
        return "0"
    out = ""
    while n:
        out = _B36[n % 36] + out
        n //= 36
    return out


def build_map(mod, parsed, scale=5):
    """
    Everything the deployment map needs, small enough to embed.

    The province bitmap is 36 MB, so it ships as a run-length encoded grid of
    province ids at 1/`scale` resolution -- about 220 KB of base36 text, painted
    to a canvas in the browser by looking each province up in the owner table.
    That means one raster covers every save: only ownership and unit positions
    change, and ownership ships as a delta against the previous save because a
    campaign rarely moves more than a few hundred provinces between snapshots.
    """
    from mod_reader import (country_colours, province_anchors, province_names,
                            province_raster, sea_provinces, unit_positions)

    if not mod or not mod.path:
        return None
    width, height, runs = province_raster(mod.path, scale)
    if not width:
        return None

    colours = country_colours(mod.path)
    sea = sea_provinces(mod.path)
    full_height = height * scale

    # Only provinces that ever hold troops need an anchor, which is a fraction
    # of the 3,000-odd the file lists.
    garrisoned = {pid
                  for _meta, nations in parsed
                  for nat in nations.values()
                  for pid in nat.get("units_at", {})
                  if pid > 0}
    spots = {}
    for pid, (x, y) in unit_positions(mod.path).items():
        if pid not in garrisoned:
            continue
        # positions.txt measures y from the bottom, like the bitmap
        spots[pid] = [round(x / scale, 1), round((full_height - y) / scale, 1)]
    # A mod may ship a positions.txt that names a province without giving it
    # any anchor at all. Those fall back to the province's own shape rather
    # than vanishing from the map -- see `province_anchors`.
    unanchored = garrisoned - set(spots)
    spots.update(province_anchors(width, runs, unanchored))
    fallback = len(unanchored & set(spots))

    # one tag table for every save, so ownership is a list of small integers
    tags = sorted({owner
                   for meta, _nations in parsed
                   for owner, _ctrl in meta.get("province_owner", {}).values()}
                  | {ctrl
                     for meta, _nations in parsed
                     for _owner, ctrl in meta.get("province_owner", {}).values()})
    index = {tag: i for i, tag in enumerate(tags)}

    owners, armies, previous = [], {}, {}
    for meta, nations in parsed:
        date = meta.get("date") or ""
        book = meta.get("province_owner", {})
        held = {pid: index[owner] for pid, (owner, _ctrl) in book.items()}
        changed = {pid: i for pid, i in held.items() if previous.get(pid) != i}
        gone = [pid for pid in previous if pid not in held]
        # Occupation is the exception rather than the rule -- a couple of dozen
        # provinces in a save at war -- so it rides along as a full list each
        # time instead of a delta.
        occupied = {pid: index[ctrl] for pid, (owner, ctrl) in book.items()
                    if ctrl != owner}
        owners.append({
            "date": date,
            "base": not previous,
            "set": ",".join(f"{p}:{i}" for p, i in sorted(changed.items())),
            "clear": ",".join(str(p) for p in sorted(gone)),
            "occ": ",".join(f"{p}:{i}" for p, i in sorted(occupied.items())),
        })
        previous = held

        here = {}
        for tag, nat in nations.items():
            for pid, types in nat.get("units_at", {}).items():
                if pid <= 0:
                    continue
                total = sum(types.values())
                if not total:
                    continue
                men = nat.get("men_at", {}).get(pid, {})
                here.setdefault(str(pid), []).append([
                    index.get(tag, -1), total,
                    ";".join(f"{t}:{n}" for t, n in
                             sorted(types.items(), key=lambda kv: -kv[1])),
                    # Men rather than regiments, and per type, so a stack worn
                    # down by fighting reads smaller than a fresh one the same
                    # size on paper.
                    sum(men.values()),
                    ";".join(f"{t}:{men.get(t, 0)}" for t, _n in
                             sorted(types.items(), key=lambda kv: -kv[1])),
                ])
        armies[date] = here

    return {
        "w": width,
        "h": height,
        "scale": scale,
        # How many garrisoned provinces the mod's positions.txt could not
        # anchor, so the caller can say so rather than leave it silent.
        "derived": fallback,
        "runs": " ".join(_b36(p) if c == 1 else _b36(p) + "." + _b36(c)
                         for p, c in runs),
        "tags": tags,
        "colours": {t: colours[t] for t in tags if t in colours},
        "sea": sorted(sea),
        "spots": spots,
        "names": {p: n for p, n in province_names(mod.path).items()
                  if p in spots},
        "owners": owners,
        "armies": armies,
        # What a regiment holds at full strength, so the map can say whether a
        # brigade is under-strength rather than just how many men it has.
        "regimentSize": int((mod.defines or {}).get(
            "POP_SIZE_PER_REGIMENT") or 3000),
    }


def build_succession(parsed, formations=None):
    """
    Which nation a vanished one turned into.

    A save records nothing about it. A nation that formed another leaves a block
    holding only its diplomatic relations -- no successor field, no event log --
    and the decision that formed Italy sets no country flag: it changes the tag,
    swaps the cores and inherits the other Italian states. The one flag that
    does survive such a change, IGoR's `dual_monarchy_done`, sits on
    Austria-Hungary because a country carries its own flags through a tag
    change, so it says the nation is the product of a decision without saying
    what it used to be.

    Two things do know. The mod's decisions declare who is *allowed* to form
    what -- `form_italy` is open to Sardinia-Piedmont and the Two Sicilies --
    and the province ledger says what actually happened in this campaign: NGF
    appears holding land that was Prussian one save earlier, and Prussia holds
    none any more. So a predecessor is a nation that disappears as the newcomer
    appears, having handed it most of what it owned, and that the mod either
    names as a former of it or whose people the newcomer accepts.

    Every part of that earns its place. Without "disappears", Austria-Hungary
    would be recorded as becoming Hungary in 1906 when it merely released it,
    and the Confederacy as replacing the United States. Without "most of what it
    owned", any neighbour that lost a province in the same window would qualify.
    And without the last test -- saves being years apart -- a conquest inside
    the same window reads exactly like a formation: it is what keeps Tibet from
    becoming a Dzungar khanate and Swaziland from becoming Batavia, while
    Denmark and Finland still become Scandinavia, whose cultures they are.

    On one campaign this finds Wallachia becoming Romania, Sardinia and the Two
    Sicilies becoming Italy, Austria becoming Austria-Hungary, Prussia and five
    small German states becoming the North German Federation, and that becoming
    Germany.
    """
    formations = formations or {}
    ledgers = []
    for meta, nations in parsed:
        book = {}
        for pid, (owner, _ctrl) in meta.get("province_owner", {}).items():
            if owner:
                book.setdefault(owner, set()).add(pid)
        home = {}
        for tag, nat in nations.items():
            primary = str(nat.get("primary_culture") or "")
            home[tag] = (primary,
                         set(nat.get("accepted_cultures") or ()) | {primary})
        ledgers.append((meta.get("date") or "", book, home))

    out = {}
    for (_before, was, was_home), (date, now, home) in zip(ledgers, ledgers[1:]):
        appeared = set(now) - set(was)
        vanished = set(was) - set(now)
        for tag in sorted(appeared):
            land = now[tag]
            if not land:
                continue
            _primary, accepts = home.get(tag, ("", set()))
            declared = formations.get(tag) or set()
            came = []
            # Sorted, because two predecessors that handed over the same share
            # sort equal and would otherwise be ordered by however the set
            # happened to iterate -- which is not the same twice, since Python
            # salts string hashing per process. A report should read the same
            # every time it is built from the same saves.
            for old in sorted(vanished):
                shared = was[old] & land
                if not shared:
                    continue
                # most of what the old nation held has to have become this one
                if len(shared) / len(was[old]) < 0.5:
                    continue
                # and the mod has to name it as a former of this nation, or
                # failing that -- releases and event tag changes are in no
                # decision file -- the newcomer has to claim its people. A
                # nation that becomes another keeps them; one merely conquered
                # in the same window does not.
                by_decision = old in declared
                mine = was_home.get(old, ("", set()))[0]
                if not by_decision and (not mine or mine not in accepts):
                    continue
                came.append([old, round(len(shared) / len(land), 4),
                             1 if by_decision else 0])
            if came:
                came.sort(key=lambda part: -part[1])
                out[tag] = {"date": date, "from": came}
    return out


# How many suppliers of one good are named at one date before the rest are
# rolled into a single "everyone else". A glut is made by the handful of
# nations at the top of this list; the ninetieth is noise, and naming all of
# them for every good at every save is most of a megabyte of report.
SUPPLY_NAMED = 14


def thin_facts(facts, series):
    """
    `facts` with everything `series` already carries taken out of it.

    The two are the same numbers in two orientations -- `series` is
    {tag: {measure: {date: value}}} and `facts` is {date: {tag: {measure:
    value}}} -- and they were both shipped whole. On a campaign of a
    hundred saves that is two megabytes of an eleven megabyte payload, and
    a seventh of the finished report, spent saying everything twice.

    What is left is the handful of fields no chart plots and so no series
    holds: the primary culture, whether the nation was mobilized, whether a
    person was playing it. The page transposes the rest back at boot, which
    costs it a few milliseconds and no accuracy, because these are the same
    values rather than a rounding of them.

    Returns (what is left, the measures taken out). The second is shipped
    with the first and is what the page transposes back -- and only that,
    not everything `series` happens to hold. `series` carries a dozen
    measures `facts` never did, and putting those in as well would hand the
    tables values they have never had: harmless today, because nothing
    reads them off a fact, and a silent change in what the page shows the
    first time something does.
    """
    held = set()
    for metrics in series.values():
        held.update(metrics)
    taken = sorted({k for by_tag in facts.values() for vals in by_tag.values()
                    for k in vals} & held)
    drop = set(taken)
    return ({date: {tag: {k: v for k, v in vals.items() if k not in drop}
                    for tag, vals in by_tag.items()}
             for date, by_tag in facts.items()},
            taken)


def as_columns(series, dates):
    """
    `series` with each measure as one value per date, in date order.

    It is built as {date: value} because that is how the rows arrive, and
    it was shipped that way -- which writes the date out again for every
    nation and every measure. A campaign of a hundred saves with forty
    nations and thirty-five measures says "1872.9.1" a hundred and fifty
    thousand times. The page already walks these against `DATA.dates` to
    plot them, so the dates were never carrying anything: as columns the
    same numbers are 2.95 MB instead of 1.15.

    A hole -- a nation not in that save -- is a null, where before it was
    a key that was not there. Both read as "no point here".
    """
    return {tag: {key: as_column(dated, dates)
                  for key, dated in metrics.items()}
            for tag, metrics in series.items()}


def as_column(dated, dates):
    """One {date: value} as one value per date, in order. See `as_columns`."""
    return [dated.get(d) for d in dates]


def rebuild_facts(facts, series, taken, dates):
    """
    Put the two back together, the way the page does at boot.

    `series` here is the shipped shape -- columns against `dates` -- because
    that is what the page has. Here so that it can be checked: this and the
    loop in the template are the same operation written twice, and if they
    drift the report shows numbers nothing here can reproduce.
    `testkit/facts.py` holds them to each other, and to
    `rebuild_facts(...) == facts`.
    """
    out = {date: {tag: dict(vals) for tag, vals in by_tag.items()}
           for date, by_tag in facts.items()}
    for tag, metrics in series.items():
        for key in taken:
            column = metrics.get(key)
            if not column:
                continue
            for i, value in enumerate(column):
                if value is None:
                    continue
                out.setdefault(dates[i], {}).setdefault(tag, {})[key] = value
    return out


def pack(payload):
    """
    The payload as the page carries it: JSON, gzipped, base64.

    A campaign saved by hand thirty times makes about seven megabytes of JSON,
    which is a large mail attachment. The same campaign autosaved every month
    makes a hundred and twenty, which is not a file anybody sends anyone. The
    shape compresses about nine-fold -- it is mostly repeated key names and
    columns of similar numbers -- so it travels compressed and the browser
    inflates it on the way in, which it does with `DecompressionStream`, built
    in and needing nothing shipped alongside.

    Base64 costs a third back on top. That is the price of putting bytes inside
    an HTML file and still having one file that opens off a disk with no server
    behind it, and it is worth paying: a report goes from 119 MB to about 17,
    and opens quicker than it did, because inflating a megabyte is faster than
    reading a hundred off a disk and parsing them.
    """
    return base64.b64encode(pack_bytes(payload)).decode("ascii")


def pack_bytes(payload):
    """
    The payload gzipped, which is what both the page and `--split` carry.

    Every `<` and `>` in it is turned into a look-alike first. The page
    writes names into its HTML -- war and battle names, leaders, provinces,
    nations, goods -- and those come out of save files and mods, which is
    to say out of anybody's hands: a war named `<img src=x onerror=...>`
    ran its script the moment the Wars tab drew, in a report that may be
    published to a public site. A name never has a real use for either
    character, and without them no text becomes markup, at any of the
    thirty places the page writes HTML or any it gains later. No name is
    ever written into an attribute, which is where a quote would matter
    instead. Done on the text, which only has them inside strings, rather
    than by walking the payload, so it costs a pass of `str.replace`.
    """
    raw = json.dumps(payload, separators=(",", ":"))
    raw = raw.replace("<", "\\u2039").replace(">", "\\u203a")
    # Level 6 rather than 9: the last 5% of size costs three times the wall
    # clock, and this runs once per report over a hundred megabytes.
    return gzip.compress(raw.encode("utf-8"), 6)


def _trim_supply(supply, dates):
    """
    {good: {date: {"t": world total, "n": [[tag, amount], ...]}}}, biggest first.

    What is dropped is still counted: `t` is the total over every supplier, so
    the share the named ones do not account for is the rest of the world.
    """
    if not supply:
        return {}
    keep = set(dates)
    out = {}
    for good, by_date in supply.items():
        rows = {}
        for date, by_tag in by_date.items():
            if date not in keep:
                continue
            total = sum(by_tag.values())
            if total <= 0:
                continue
            top = sorted(by_tag.items(), key=lambda kv: -kv[1])[:SUPPLY_NAMED]
            rows[date] = {"t": round(total, 2),
                          "n": [[tag, round(amount, 2)] for tag, amount in top]}
        if rows:
            out[good] = rows
    return out


def nation_names(mod, parsed):
    """
    {tag: the name the report shows}, from the mod's own localisation, which
    is where the game gets them: a bare TAG, overridden by TAG_<government>
    when one exists -- IGoR's PBC is "Peru-Bolivia" but "Andine Federation"
    while it is a democracy. Saves are walked in order so the name reflects
    the government the nation ended the series with. Without a mod there is
    nothing to read, and tags stand in for names.
    """
    names = {}
    if not mod or not mod.localisation:
        return names
    from mod_reader import name_for
    loc = mod.localisation
    for _meta, nations in parsed:
        for tag, nat in nations.items():
            names[tag] = name_for(tag, str(nat.get("government") or ""), loc)
    return names


def flags_for(mod, parsed, war_book):
    """
    ({date: [[tag, flag key], ...]}, {flag key: image}): each save's great
    powers in rank order, and the flags the great-power and battle tables
    fly. Nothing without a mod, which is what turns the save's great-power
    indices back into tags and holds the flag images.
    """
    great_powers, flags = {}, {}
    if not mod or not mod.country_order:
        return great_powers, flags
    from mod_reader import flag_images, flag_suffixes, government_flag_types
    from modrules import great_powers as ranked
    styles = government_flag_types(mod.path)
    for meta, nations in parsed:
        picks = ranked(meta, mod)
        if not picks:
            continue
        row = []
        for tag in picks:
            gov = str((nations.get(tag) or {}).get("government") or "")
            # One flag per tag and flag variant, so a nation that turns
            # communist mid-campaign flies both in turn without the image
            # being stored twice. The suffix that will actually be used is
            # the discriminator, since two governments can share a flagType
            # and still fly different flags.
            key = tag + "|" + (flag_suffixes(gov, styles)[0] or "base")
            if key not in flags:
                got = flag_images(mod.path, [tag], {tag: gov}, styles=styles)
                if tag in got:
                    flags[key] = got[tag]
            row.append([tag, key])
        great_powers[meta.get("date") or ""] = row
    # Battle tables name a lot of nations that never made great power, and a
    # flag beside the tag reads faster than a tag alone. These take the plain
    # national flag rather than a government variant.
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
            got = flag_images(mod.path, [tag], {}, styles=styles)
            if tag in got:
                flags[tag + "|"] = got[tag]
    return great_powers, flags


def build_report(rows, tables, price_rows, snapshot_rows, outdir,
                 tag_names=None, map_data=None,
                 base_prices=None, great_powers=None, flags=None,
                 technology=None, wars=None, succession=None,
                 naval=None, supply=None, culture_names=None,
                 display_names=None, cross=None, world_pop=None,
                 filename="report.html", split=False, alongside=None):
    os.makedirs(outdir, exist_ok=True)
    tag_names = tag_names or {}

    dates, seen = [], set()
    for row in rows:
        if row["date"] not in seen:
            seen.add(row["date"])
            dates.append(row["date"])
    dates.sort(key=year_fraction)

    tags = sorted({row["tag"] for row in rows})
    metric_keys = [key for key, _, _ in METRICS if any(key in row for row in rows)]

    series = {tag: {key: {} for key in metric_keys} for tag in tags}
    for row in rows:
        for key in metric_keys:
            val = row.get(key)
            if val is None or val == "":
                continue
            try:
                series[row["tag"]][key][row["date"]] = float(val)
            except (TypeError, ValueError):
                pass

    # Growth is a rate, so it needs two readings and the time between them. The
    # anchor only moves when a reading is far enough from the last one to say
    # something -- see MIN_GROWTH_SPAN -- which also means a nation missing from
    # a save measures across the gap rather than losing the series entirely.
    year_of = {d: year_fraction(d) for d in dates}
    growth_keys = []
    for key, source, _label in GROWTH_METRICS:
        if source not in metric_keys:
            continue
        growth_keys.append(key)
        for tag in tags:
            have = series[tag][source]
            series[tag][key] = growth_series(
                ((d, have.get(d)) for d in dates), year_of.__getitem__)
    for key, source, _label in GAIN_METRICS:
        if source not in metric_keys:
            continue
        growth_keys.append(key)
        for tag in tags:
            have = series[tag][source]
            series[tag][key] = gain_series((d, have.get(d)) for d in dates)

    # The per-nation tables arrive already grouped by nation and date, one
    # save's share at a time out of the worker that read it -- see
    # `save_tables` -- so what is left here is what depends on all of them.
    ships, crews = tables.ships, tables.crews
    ship_types = {stype for by_date in ships.values()
                  for held in by_date.values() for stype in held}
    brigades = tables.brigades
    regiment_types = {rtype for by_date in brigades.values()
                      for held in by_date.values() for rtype in held}

    # Techs are referenced by index so the payload does not repeat 100+ names
    # once per nation per save.
    tech_order, tech_meta = [], []
    for branch, lines in (("army", ARMY_LINES), ("navy", NAVY_LINES)):
        for line, techs in lines:
            for tech in techs:
                tech_order.append(tech)
                tech_meta.append([branch, line])
    seen_tech = set(tech_order)
    extra = sorted({tech for by_date in tables.techs.values()
                    for names in by_date.values() for tech in names}
                   - seen_tech)
    for tech in extra:
        tech_order.append(tech)
        tech_meta.append(["other", "Other"])
    tech_index = {t: i for i, t in enumerate(tech_order)}

    techs_by = {}
    for tag, by_date in tables.techs.items():
        for date, names in by_date.items():
            held = [tech_index[t] for t in names if t in tech_index]
            if held:
                held.sort()
                techs_by.setdefault(tag, {})[date] = held

    pops = tables.pops
    pop_types = {ptype for by_date in pops.values()
                 for held in by_date.values() for ptype in held}
    cultures = tables.cultures

    # ---- market ----
    price_dates, pseen = [], set()
    goods_meta, prices = {}, {}
    # (date, year, good, category, price), in `write_outputs`'s order.
    for date, _year, good, category, price in price_rows:
        if date not in pseen:
            pseen.add(date)
            price_dates.append(date)
        goods_meta.setdefault(good, category)
        prices.setdefault(good, {})[date] = float(price)
    price_dates.sort(key=year_fraction)

    # A good whose price never moves is undiscovered or untraded. Keep it out of
    # the default view rather than dropping it, so mods stay inspectable.
    movement = {}
    for good, by_date in prices.items():
        vals = [by_date[d] for d in price_dates if d in by_date]
        movement[good] = (abs(vals[-1] - vals[0]) / vals[0]
                          if len(vals) >= 2 and vals[0] else 0.0)

    snapshot = {}
    for row in snapshot_rows:
        # A demand of order a billion is nobody's economy: it is a standing
        # order to buy without limit, which some mods give a nation so that raw
        # materials always find a buyer. Every reading in the campaigns this was
        # checked against that carries one sits at exactly five times the good's
        # base cost, which is the engine's price ceiling -- so the flag means
        # "pegged at its maximum", and `real_demand` is what is left when the
        # standing order is set aside.
        raw_demand = float(row["demand"])
        snapshot.setdefault(row["date"], {})[row["good"]] = {
            "price": float(row["price"]),
            "supply": float(row["supply"]),
            "demand": float(row["real_demand"]),
            "actual_sold": float(row["actual_sold"]),
            "pegged": int(raw_demand > 1e9),
            "discovered": int(row["discovered"]),
        }

    facts = {}
    for row in rows:
        facts.setdefault(row["date"], {})[row["tag"]] = {
            "total_pop": int(float(row.get("total_pop") or 0)),
            "accepted_pop": int(float(row.get("accepted_pop") or 0)),
            "accepted_pct": float(row.get("accepted_pct") or 0),
            "avg_literacy": float(row.get("avg_literacy") or 0),
            "avg_literacy_stated": float(row.get("avg_literacy_stated") or 0),
            "life_unmet": int(float(row.get("life_unmet") or 0)),
            "life_unmet_pct": float(row.get("life_unmet_pct") or 0),
            "starving": int(float(row.get("starving") or 0)),
            "starving_pct": float(row.get("starving_pct") or 0),
            "avg_militancy": float(row.get("avg_militancy") or 0),
            "avg_consciousness": float(row.get("avg_consciousness") or 0),
            "brigades": int(float(row.get("brigades") or 0)),
            "regular_brigades": int(float(row.get("regular_brigades") or 0)),
            "mobilized_brigades": int(float(row.get("mobilized_brigades") or 0)),
            "mobilizing": int(float(row.get("mobilizing") or 0)),
            "brigade_cap": int(float(row.get("brigade_cap") or 0)),
            "mobilization_pool": int(float(row.get("mobilization_pool") or 0)),
            "mobilization_brigades": int(float(row.get("mobilization_brigades") or 0)),
            "mobilisation_size": float(row.get("mobilisation_size") or 0),
            "is_mobilized": int(float(row.get("is_mobilized") or 0)),
            "ships": int(float(row.get("ships") or 0)),
            "factory_levels": int(float(row.get("factory_levels") or 0)),
            "provinces": int(float(row.get("provinces") or 0)),
            "prestige": float(row.get("prestige") or 0),
            "primary_culture": row.get("primary_culture", ""),
            "is_player": int(float(row.get("is_player") or 0)),
            "soldiers_noncolonial": int(float(row.get("soldiers_noncolonial") or 0)),
            "techs": int(float(row.get("techs") or 0)),
            "army_techs": int(float(row.get("army_techs") or 0)),
            "navy_techs": int(float(row.get("navy_techs") or 0)),
        }


    slim_facts, fact_keys = thin_facts(facts, series)
    payload = {
        "dates": dates,
        "years": [year_fraction(d) for d in dates],
        "tags": tags,
        "tagNames": {t: tag_names.get(t, t) for t in tags},
        "cultureNames": culture_names or {},
        "names": display_names or {},
        "metrics": [
            {"key": key, "label": label, "fmt": fmt}
            for key, label, fmt in METRICS if key in metric_keys
        ] + [
            {"key": key, "label": label, "fmt": "percent", "rate": 1}
            for key, _source, label in GROWTH_METRICS if key in growth_keys
        ] + [
            {"key": key, "label": label, "fmt": "count", "delta": 1}
            for key, _source, label in GAIN_METRICS if key in growth_keys
        ],
        # Columns against `dates`, not {date: value}. See `as_columns`.
        "series": as_columns(series, dates),
        # Only what `series` does not already carry; the page transposes
        # the rest back, and `factKeys` says which. See `thin_facts`.
        "facts": slim_facts,
        "factKeys": fact_keys,
        "ships": ships,
        "crews": crews,
        "shipTypes": sorted(ship_types),
        "brigades": brigades,
        "regimentTypes": sorted(regiment_types),
        "techOrder": tech_order,
        "techMeta": tech_meta,
        "techsBy": techs_by,
        # Everyone alive, not just everyone with a government.
        "worldPop": world_pop or {},
        "pops": pops,
        "popTypes": sorted(pop_types),
        "cultures": cultures,
        "colours": SERIES_COLOURS,
        "map": map_data,
        "basePrices": base_prices or {},
        "greatPowers": great_powers or {},
        "flags": flags or {},
        "technology": technology or {},
        "wars": wars or [],
        "succession": succession or {},
        "priceDates": price_dates,
        "priceYears": [year_fraction(d) for d in price_dates],
        # Columns against `priceDates`, for the reason `as_columns` gives:
        # a good's price is one number a month, and writing the month out
        # beside each of them is most of what it costs.
        "prices": {good: as_column(by, price_dates)
                   for good, by in prices.items()},
        "goods": sorted(prices),
        "goodCategory": goods_meta,
        "categoryLabels": CATEGORY_LABELS,
        "movement": movement,
        "snapshot": snapshot,
        "snapshotDates": sorted(snapshot, key=year_fraction),
        "naval": naval,
        "supply": _trim_supply(supply, dates),
        "growthSpan": MIN_GROWTH_SPAN,
        # Present only when several campaigns were read at once, so a
        # single-campaign report carries none of this weight.
        "cross": cross or None,
    }

    # These two go into the page as it is written, outside the payload, and
    # a save's date is whatever the save says it is.
    span = _escape(f"{dates[0]} – {dates[-1]}") if dates else "—"
    price_span = (_escape(f"{price_dates[0]} – {price_dates[-1]}")
                  if price_dates else "no price data")

    # A report normally carries its payload inside it, because a report is a
    # file somebody was sent and one file is what they can open. `--split`
    # writes the payload beside the page instead: no base64 third on top, so a
    # campaign that came to 20 MB as one file comes to about 15, the page
    # itself opens in a moment, and both parts can be hosted. See `unpackFrom`
    # in the template for why that one needs a server behind it.
    # Everything above this line holds the interpreter lock the whole way;
    # everything below spends most of its time inside zlib, which does not.
    # `alongside` is a nudge saying the compression is starting, for a caller
    # with work of its own that can be done during it. It has to come back
    # promptly -- starting a thread is the point, not doing the work here.
    if alongside is not None:
        alongside()

    if split:
        data_name = os.path.splitext(filename)[0] + ".data.gz"
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, data_name), "wb") as fh:
            fh.write(pack_bytes(payload))
        html = TEMPLATE.replace("__DATA__", "").replace("__DATAURL__",
                                                        data_name)
    else:
        html = TEMPLATE.replace("__DATA__", pack(payload))
        html = html.replace("__DATAURL__", "")
    html = html.replace("__SAVECOUNT__", str(len(dates)))
    html = html.replace("__NATIONCOUNT__", str(len(tags)))
    html = html.replace("__SPAN__", span)
    html = html.replace("__PRICESPAN__", price_span)

    path = os.path.join(outdir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path

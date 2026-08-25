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
Several campaigns at once, without being told what they are.

Comparing one nation's run in one game against its run in another needs two
things the single-campaign path never had to answer: which saves belong to which
campaign, and which mod each campaign was played on. Asking the user to pick
thirty folders and thirty mods is not an answer, so both are worked out here.

A campaign is a folder. That is not a guess -- it is how saves are already kept,
one directory per game -- so the input is the parent directory and the campaigns
are its subdirectories. To catch the one real mistake, that a folder holds two
games' saves, `history_breaks` reads the global event flags each save carries:
they accumulate as a game runs, so an earlier save's flags are a later save's
past, and a save holding flags its successors never had did not come from the
same history.

The mod is worked out by elimination, cheapest test first. A country tag the
mod has never heard of, a pop type it does not define, or an invention index
past the end of the array it builds each rules a candidate out outright. What
survives is ranked by how tightly it fits.
"""

import io
import os
import re
from collections import Counter

from mod_reader import _country_entries, invention_sequence, read_poptypes

# The country blocks sit after the province data, near the end of the file, so
# identifying a save means reading all of it. Only the last save or two of a
# campaign is read, which is seconds even at 30 MB apiece.

_TAG = re.compile(r'\n([A-Z][A-Z0-9]{2})=\r?\n\{')
_POP = re.compile(r'\n\t\t([a-z_]+)=\r?\n\t\t\{')
_IDS = re.compile(r'active_inventions=\s*\{([^}]*)\}')
_DATE = re.compile(r'^date="([\d.]+)"', re.M)
_FLAGS = re.compile(r'^flags=\s*\{(.*?)^\}', re.M | re.S)
_FLAG_NAME = re.compile(r'^\s*([A-Za-z_][\w]*)\s*=', re.M)

# A pop type is real if provinces are full of it. A handful of matches is some
# other nested block that happens to look the same.
_POP_FLOOR = 50


def campaigns_in(parent, depth=6):
    """
    Every folder at or under `parent` that holds saves, as (name, path, files).

    The whole tree, not just the children: campaigns get grouped into folders of
    their own -- the two Divergences games sitting together under `dodgames` --
    and scanning one level deep would walk straight past them and report the
    parent as holding two campaigns when it holds four.

    The parent itself counts, so pointing this at a single campaign behaves the
    way the single-campaign path always did. A campaign is named by its own
    folder, or by the path down to it when two folders share a name.
    """
    found = []
    parent = os.path.normpath(parent)
    for root, dirs, files in os.walk(parent):
        rel = os.path.relpath(root, parent)
        if rel != "." and rel.count(os.sep) >= depth - 1:
            dirs[:] = []                  # deep enough; a save tree is not this deep
        dirs.sort()
        saves = sorted(f for f in files if f.lower().endswith(".v2"))
        if saves:
            found.append([os.path.basename(root) or root, rel, root,
                          [os.path.join(root, f) for f in saves]])
    seen = Counter(entry[0] for entry in found)
    out = []
    for leaf, rel, root, files in found:
        name = leaf if seen[leaf] == 1 or rel == "." else rel.replace(os.sep, "/")
        out.append((name, root, files))
    return out


def installed_mods(game_root):
    """The game itself plus every mod folder beside it, as (label, path)."""
    out = [("(unmodded)", game_root)]
    home = os.path.join(game_root, "mod")
    try:
        names = sorted(os.listdir(home))
    except OSError:
        return out
    for name in names:
        path = os.path.join(home, name)
        if os.path.isdir(path) and os.path.isdir(os.path.join(path, "common")):
            out.append((name, path))
    return out


def _sniff(path):
    """The identifying facts in one save: tags, pop types, top invention id."""
    with io.open(path, encoding='latin-1') as fh:
        text = fh.read()
    tags = {m.group(1) for m in _TAG.finditer(text)}
    pops = Counter(m.group(1) for m in _POP.finditer(text))
    ids = []
    for m in _IDS.finditer(text):
        ids.extend(int(n) for n in m.group(1).split() if n.isdigit())
    return {
        "tags": tags,
        "pops": {k for k, c in pops.items() if c > _POP_FLOOR},
        "top_invention": max(ids) if ids else 0,
    }


_CAPACITY = {}


def _capacity(root):
    """
    How many inventions the array this folder builds would hold.

    This asks the same `invention_sequence` the decoder itself walks, rather
    than counting the files a second time with a looser pattern. A count that
    disagreed with the real array would rule out the very mod a campaign was
    played on: a hand-rolled regex here read 556 inventions where the sequence
    builds 563, which was enough to reject the correct folder outright. Cached,
    because every campaign asks about every candidate.
    """
    if root not in _CAPACITY:
        try:
            _CAPACITY[root] = len(invention_sequence(root))
        except Exception:
            _CAPACITY[root] = 0
    return _CAPACITY[root]


def match_mod(files, candidates, sample=2):
    """
    Which of `candidates` this campaign was played on.

    Returns (best label, best path, [(label, verdict, detail)]) so the caller can
    show its working rather than only its answer. `sample` saves are sniffed --
    the last ones, which carry the most tags and the highest invention indices,
    so they rule the most out.
    """
    facts = [_sniff(p) for p in files[-sample:]] or [
        {"tags": set(), "pops": set(), "top_invention": 0}]
    tags = set().union(*(f["tags"] for f in facts))
    pops = set().union(*(f["pops"] for f in facts))
    top = max(f["top_invention"] for f in facts)

    # A province block nests more than pops at that indent -- `employment`,
    # `ideology`, `input_goods` all match the same shape. The only thing that
    # makes a name a pop type is that somebody defines it as one, so anything
    # no candidate has ever heard of is not evidence about any of them.
    strata_by_mod = {label: set(read_poptypes(root)) for label, root in candidates}
    pops &= set().union(*strata_by_mod.values()) if strata_by_mod else set()

    rows, fits = [], []
    for label, root in candidates:
        known = {t for t, _f in _country_entries(root)}
        strata = strata_by_mod[label]
        capacity = _capacity(root)
        unknown = tags - known
        missing = pops - strata
        why = []
        if unknown:
            why.append("%d unknown tag%s (%s)"
                       % (len(unknown), "" if len(unknown) == 1 else "s",
                          " ".join(sorted(unknown)[:4])))
        if missing:
            why.append("no pop type %s" % ", ".join(sorted(missing)))
        if top > capacity:
            why.append("save names invention %d, folder builds %d"
                       % (top, capacity))
        if why:
            rows.append((label, "no", "; ".join(why)))
            continue
        # Among folders that could have produced this save, the honest pick is
        # the one that explains it most tightly: fewest inventions left over,
        # then fewest countries the campaign never mentions.
        slack = (capacity - top, len(known - tags))
        fits.append((slack, label, root))
        rows.append((label, "fits", "%d spare invention slots, %d unused tags"
                     % (capacity - top, len(known - tags))))
    if not fits:
        return None, None, rows
    fits.sort()
    _slack, label, root = fits[0]
    return label, root, rows


def history_breaks(files, floor=3, width=6):
    """
    Saves in this folder that cannot share a history with the ones after them.

    Global event flags accumulate, so an earlier save's flags should be a subset
    of a later save's. Flags do get cleared deliberately -- `money_setup_done`
    and the rest are one-shot setup flags -- so contradicting a later save
    proves nothing on its own. Measured across 2,850 pairs of real saves, two
    from one campaign never disagreed by more than five flags, while two from
    different campaigns disagreed by twelve at the median. `width` sits above
    that first number: a save is only named when it contradicts *every* later
    save by at least that much, which held no false alarms on those campaigns.

    Returns [(file, worst disagreement, later saves checked)].
    """
    heads = []
    for path in files:
        try:
            with io.open(path, 'rb') as fh:
                blob = fh.read(400_000).decode('latin-1')
        except OSError:
            continue
        date = _DATE.search(blob)
        block = _FLAGS.search(blob)
        heads.append({
            "file": os.path.basename(path),
            "key": tuple(int(x) for x in date.group(1).split(".")) if date else (0,),
            "flags": set(_FLAG_NAME.findall(block.group(1))) if block else set(),
        })
    out = []
    for h in heads:
        if len(h["flags"]) < floor:
            continue                  # too little evidence to accuse it
        later = [o for o in heads if o["key"] > h["key"]]
        if len(later) < 2:
            continue
        # The weakest disagreement across every later save: one save that
        # happens to have cleared a flag cannot raise the alarm on its own.
        worst = min(len(h["flags"] - o["flags"]) for o in later)
        if worst >= width:
            out.append((h["file"], worst, len(later)))
    return out


# Measures whose meaning is a mod's to decide rather than the save's. They are
# offered like all the rest -- a mobilization ceiling is a real fact about a
# campaign, and comparing two is a fair question to ask -- but two mods answer
# them from different rulebooks, so the page says which ones those are instead
# of quietly dropping them.
RULEBOUND = frozenset((
    "mobilization_pool", "mobilization_brigades", "mobilisation_size",
))


def series_payload(results, names=None, floor=2):
    """
    The cross-campaign block the report carries, from finalized campaign rows.

    `results` is [(campaign name, mod label, rows)], where a row is
    (date, tag, finalized nation) -- the very rows the single-campaign charts
    and the CSVs are drawn from, so every measure the data visualizer offers is
    available here and means the same thing it does there.

    Only tags in at least `floor` campaigns are kept: a nation in one game has
    nothing to be compared against, and keeping the rest would bloat the page
    with a total conversion's private tag space.

    Time is carried twice per point -- the calendar year, and years since that
    campaign's own first save -- because campaigns rarely start on the same date
    or run the same length, and which of the two is honest depends on the
    question being asked.
    """
    from report import METRICS, GROWTH_METRICS, growth_series, year_fraction

    names = names or {}
    seen = {}
    for name, _mod, rows in results:
        for _date, tag, _done in rows:
            seen.setdefault(tag, set()).add(name)
    shared = sorted(t for t, where in seen.items() if len(where) >= floor)
    keep = set(shared)

    metrics, used = [], set()
    campaigns, series = [], []
    for name, mod, rows in results:
        dates = sorted({d for d, _t, _n in rows}, key=year_fraction)
        start = year_fraction(dates[0]) if dates else 0.0
        # {tag: {key: {date: value}}}, so the growth measures can be built from
        # the same shape `build_report` builds them from.
        by_tag = {}
        for date, tag, done in rows:
            if tag not in keep:
                continue
            slot = by_tag.setdefault(tag, {})
            for key, _label, _fmt in METRICS:
                value = done.get(key)
                if value is None or value == "":
                    continue
                try:
                    slot.setdefault(key, {})[date] = float(value)
                except (TypeError, ValueError):
                    continue
        year_of = {d: year_fraction(d) for d in dates}
        for tag, slot in by_tag.items():
            for key, source, _label in GROWTH_METRICS:
                if source in slot:
                    slot[key] = growth_series(
                        ((d, slot[source].get(d)) for d in dates),
                        year_of.__getitem__)

        block = {}
        for tag, slot in by_tag.items():
            for key, dated in slot.items():
                if not dated:
                    continue
                used.add(key)
                block.setdefault(tag, {})[key] = [
                    [round(year_of[d], 3), round(year_of[d] - start, 3),
                     round(dated[d], 4)]
                    for d in sorted(dated, key=year_fraction)]
        campaigns.append({
            "name": name,
            "mod": mod or "unmatched",
            "saves": len(dates),
            "from": round(start, 3),
            "to": round(year_of[dates[-1]], 3) if dates else None,
            # A point carries its year as a number so it can be plotted; the
            # hover wants the date it came from. Kept once per campaign rather
            # than on every point, where it would repeat across every measure.
            "dates": [[round(year_of[d], 3), d] for d in dates],
        })
        series.append(block)

    for key, label, fmt in METRICS:
        if key in used:
            metrics.append({"key": key, "label": label, "fmt": fmt,
                            "rulebound": key in RULEBOUND})
    for key, _source, label in GROWTH_METRICS:
        if key in used:
            metrics.append({"key": key, "label": label, "fmt": "percent",
                            "rate": 1, "rulebound": False})

    return {
        "campaigns": campaigns,
        "tags": shared,
        "tagNames": {t: names.get(t, t) for t in shared},
        "metrics": metrics,
        "series": series,
    }


def survey(parent, game_root):
    """
    Everything needed to read a folder of campaigns, worked out rather than asked.

    Returns one dict per campaign: its name, its saves, the mod matched to it,
    and the working behind that match.
    """
    mods = installed_mods(game_root)
    out = []
    for name, path, files in campaigns_in(parent):
        label, root, rows = match_mod(files, mods)
        out.append({
            "name": name,
            "path": path,
            "files": files,
            "mod_label": label,
            "mod_path": root,
            "candidates": rows,
        })
    return out

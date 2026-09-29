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

The mod is worked out by elimination. A country tag the folder has never heard
of, a pop type it does not define, a technology name it lacks, or an invention
index past the end of the array it builds each rules a candidate out, because a
save cannot hold a name the folder that made it never defined.

The map decides the rest, and it decides by identity rather than by size: a save
carries every province the map defines, so the two sets are equal or the save
did not come from that folder. This is what separates mods sharing a base, where
nothing else does -- CoRGI and IGoR agree on all 309 countries, all 150
technologies and all 566 inventions, and differ by three provinces.

Where several still fit, the one whose own country list the campaign comes
closest to exhausting wins, and the caller is told the answer was not forced.
Being told outright still beats all of it: `--mod-path` skips this entirely.
"""

import io
import os
import re
from collections import Counter
from dataclasses import dataclass, field

# Called through the module, so `testkit/crossrows.py` can watch it.
import finishing
from dates import ymd
from mod_reader import (country_entries, invention_sequence, read_clausewitz,
                        read_poptypes, resolved_file, resolved_files,
                        settle_campaign)
from readfolder import parse_saves
from readsave import PLAIN, reading_for
from run import RunError
from savehead import (FLAG_FLOOR, FLAG_GAP, dates_of, fields, flags_in,
                      head_of, in_date_order, one_per_date, sort_key)
from stamp import report_stamp

# The country blocks sit after the province data, near the end of the file, so
# identifying a save means reading all of it. Only the last save or two of a
# campaign is read, which is seconds even at 30 MB apiece.

_TAG = re.compile(r'\n([A-Z][A-Z0-9]{2})=\r?\n\{')
_POP = re.compile(r'\n\t\t([a-z_]+)=\r?\n\t\t\{')
_IDS = re.compile(r'active_inventions=\s*\{([^}]*)\}')
# A country's researched technologies, by name, and the highest province the
# save actually holds. Both are things a folder either defines or does not.
_TECH_BLOCK = re.compile(r'\n\ttechnology=\r?\n\t\{(.*?)\n\t\}', re.S)
_TECH_NAME = re.compile(r'\n\t\t(\w+)=\s*\{')
_PROVINCE = re.compile(r'\n(\d+)=\r?\n\{\r?\n\tname=')

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
    """Everything in one save that a folder either accounts for or cannot."""
    with io.open(path, encoding='latin-1') as fh:
        text = fh.read()
    tags = {m.group(1) for m in _TAG.finditer(text)}
    pops = Counter(m.group(1) for m in _POP.finditer(text))
    ids = []
    for m in _IDS.finditer(text):
        ids.extend(int(n) for n in m.group(1).split() if n.isdigit())
    techs = set()
    for block in _TECH_BLOCK.findall(text):
        techs |= set(_TECH_NAME.findall(block))
    return {
        "tags": tags,
        "pops": {k for k, c in pops.items() if c > _POP_FLOOR},
        "techs": techs,
        "top_invention": max(ids) if ids else 0,
        # Every province on the map is written to the save whoever owns it, so
        # this is not a sample of the map -- it is the map. Measured on four
        # campaigns it matched their mod's `definition.csv` exactly, with
        # nothing on either side that the other lacked.
        "provinces": frozenset(int(n) for n in _PROVINCE.findall(text)),
    }


_MOD_FACTS = {}


def _mod_facts(root):
    """The names and sizes a folder defines, cached: every campaign asks."""
    if root not in _MOD_FACTS:
        techs = set()
        try:
            for target in resolved_files(root, "technologies").values():
                for name, _block in read_clausewitz(target):
                    techs.add(name)
        except Exception:
            techs = set()
        provinces = set()
        try:
            target = resolved_file(root, "map", "definition.csv")
            with io.open(target, encoding='latin-1') as fh:
                for line in fh:
                    head = line.split(";")[0].strip()
                    if head.isdigit():
                        provinces.add(int(head))
        except Exception:
            provinces = set()
        _MOD_FACTS[root] = {
            "tags": {t for t, _f in country_entries(root)},
            "pops": set(read_poptypes(root)),
            "techs": techs,
            "inventions": _capacity(root),
            "provinces": frozenset(provinces),
        }
    return _MOD_FACTS[root]


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
    blank = {"tags": set(), "pops": set(), "techs": set(),
             "top_invention": 0, "provinces": frozenset()}
    facts = [_sniff(p) for p in files[-sample:]] or [blank]
    tags = set().union(*(f["tags"] for f in facts))
    pops = set().union(*(f["pops"] for f in facts))
    techs = set().union(*(f["techs"] for f in facts))
    top = max(f["top_invention"] for f in facts)
    provinces = set().union(*(f["provinces"] for f in facts))

    known = {label: _mod_facts(root) for label, root in candidates}

    # A province block nests more than pops at that indent -- `employment`,
    # `ideology`, `input_goods` all match the same shape. The only thing that
    # makes a name a pop type is that somebody defines it as one, so anything
    # no candidate has ever heard of is not evidence about any of them.
    if known:
        pops &= set().union(*(f["pops"] for f in known.values()))

    rows, fits, near = [], [], []
    for label, root in candidates:
        f = known[label]
        why = []
        unknown = tags - f["tags"]
        if unknown:
            why.append("%d unknown tag%s (%s)"
                       % (len(unknown), "" if len(unknown) == 1 else "s",
                          " ".join(sorted(unknown)[:4])))
        missing = pops - f["pops"]
        if missing:
            why.append("no pop type %s" % ", ".join(sorted(missing)))
        # Two campaigns can share every tag and still be on different mods.
        # Technology names separate them where tags cannot: Divergences and
        # Heartbreaker each hold eight the other has never defined.
        stray = techs - f["techs"]
        if stray:
            why.append("%d unknown technolog%s (%s)"
                       % (len(stray), "y" if len(stray) == 1 else "ies",
                          " ".join(sorted(stray)[:3])))
        # The map, as identity rather than as a ceiling. A save carries every
        # province the map defines, so the two sets are the same set or the save
        # did not come from this folder. This is what tells apart mods built on
        # a shared base: CoRGI and IGoR agree on all 309 countries, all 150
        # technologies and all 566 inventions, and differ by three provinces.
        # A ceiling test passed both and the winner was decided alphabetically.
        gap = len(provinces ^ f["provinces"])
        if provinces and f["provinces"] and gap:
            why.append("map has %d provinces, these saves %d"
                       % (len(f["provinces"]), len(provinces)))
        if top > f["inventions"]:
            why.append("save names invention %d, folder builds %d"
                       % (top, f["inventions"]))
        if why:
            # How far off it is, for the case where nothing fits at all: the
            # tests are strict enough that a mod updated since the save was
            # made is rejected, and the nearest miss is worth naming rather
            # than leaving the campaign unread.
            near.append((len(unknown) + len(missing) + len(stray) + gap
                         + max(0, top - f["inventions"]),
                         label, root, "; ".join(why)))
            rows.append((label, "no", "; ".join(why)))
            continue
        # Among folders that could have produced this save, prefer the one whose
        # own country list the campaign comes closest to exhausting. A save that
        # mentions every nation a mod defines is a tight explanation of it; one
        # that leaves a sixth of them unheard of is a loose one.
        #
        # Invention slack was tried first and is the wrong way round: a campaign
        # that ended early has slack against every candidate, and the mod with
        # the *smallest* array then looks closest simply for being smallest. On
        # the campaigns here that lost IGoR to Heartbreaker at every invention
        # count below the very last one, while unused tags picked correctly at
        # all of them. Slack stays as the second key, for folders that tie.
        unused = len(f["tags"] - tags)
        rank = (unused / max(1, len(f["tags"])), f["inventions"] - top)
        fits.append((rank, label, root))
        rows.append((label, "fits",
                     "%d of its %d countries never mentioned, %d spare "
                     "invention slots"
                     % (unused, len(f["tags"]), f["inventions"] - top)))
    if not fits:
        # Nothing explains these saves. Rather than dropping the campaign, name
        # the closest folder and let the caller say plainly that it is a near
        # miss -- usually the right mod at the wrong version.
        if not near:
            return None, None, rows
        near.sort()
        _distance, label, root, _why = near[0]
        rows.append((label, "nearest", _why))
        return label, root, rows
    fits.sort()
    _rank, label, root = fits[0]
    return label, root, rows


def history_breaks(files):
    """
    Saves in this folder that cannot share a history with the ones after them.

    An earlier save's global event flags should all be in a later save of the
    same game (`savehead`, where the rule and its measurement are). Flags do
    get cleared on purpose, so contradicting one later save proves nothing on
    its own: a save is only named when it loses at least `FLAG_GAP` flags
    against *every* later save, which held no false alarms on the campaigns
    it was measured on.

    Returns [(file, worst disagreement, later saves checked)].
    """
    heads = []
    for path in files:
        head = head_of(path)
        if head is None:
            continue
        heads.append({
            "file": os.path.basename(path),
            "key": ymd(fields(head).get("date")) or (0,),
            "flags": flags_in(head),
        })
    out = []
    for h in heads:
        if len(h["flags"]) < FLAG_FLOOR:
            continue                  # too little evidence to accuse it
        later = [o for o in heads if o["key"] > h["key"]]
        if len(later) < 2:
            continue
        # The weakest disagreement across every later save: one save that
        # happens to have cleared a flag cannot raise the alarm on its own.
        worst = min(len(h["flags"] - o["flags"]) for o in later)
        if worst >= FLAG_GAP:
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
    from dates import year_fraction
    from report import (METRICS, GAIN_METRICS, GROWTH_METRICS, gain_series,
                        growth_series)

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
            for key, source, _label in GAIN_METRICS:
                if source in slot:
                    slot[key] = gain_series(
                        (d, slot[source].get(d)) for d in dates)

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
    for key, _source, label in GAIN_METRICS:
        if key in used:
            metrics.append({"key": key, "label": label, "fmt": "count",
                            "delta": 1, "rulebound": False})

    return {
        "campaigns": campaigns,
        "tags": shared,
        "tagNames": {t: names.get(t, t) for t in shared},
        "metrics": metrics,
        "series": series,
    }


@dataclass
class Surveyed:
    """
    One campaign folder, and the mod its saves will be read under.

    `candidates` is the working behind a mod found by search: (the mod's
    label, "fits" or "nearest" or why not, the detail) per mod tried. `told`
    says the mod was named rather than found.
    """
    name: str
    path: str
    files: list
    mod_label: str = None
    mod_path: str = None
    candidates: list = field(default_factory=list)
    told: bool = False


def survey(parent, game_root):
    """
    Everything needed to read a folder of campaigns, worked out rather than asked.

    One `Surveyed` per campaign: its name, its saves, the mod matched to it,
    and the working behind that match.
    """
    mods = installed_mods(game_root)
    out = []
    for name, path, files in campaigns_in(parent):
        label, root, rows = match_mod(files, mods)
        out.append(Surveyed(name, path, files, label, root, rows))
    return out


def survey_cross(parent, game_root, args, verbose=True):
    """
    Every campaign under `parent`, and the mod each one will be read under.

    One `Surveyed` per campaign, and no save read whole: the mod is named,
    or worked out from the last save or two. This is everything the report
    is made from, which is why it is its own step: the report stamp has to
    cover every campaign in the comparison, not just the one the rest of the
    report is about, and it has to be taken before the campaigns are read,
    or a run with nothing to do reads all of them first to find that out.
    """
    # Every mod on the game it sits in, the same rule a single campaign is
    # held to (`mod_reader.settle_game`): an install named with --game-root
    # has to be one, and a mod named either way has to be in its mod folder.
    from mod_reader import settle_game

    def on_the_game(path, flag):
        try:
            settle_game(path, game_root)
        except ValueError as exc:
            raise RunError("%s: %s" % (flag, exc)) from exc

    if game_root:
        on_the_game(None, "--game-root")

    # Told, rather than worked out: `--campaign-mod NAME=PATH` settles one
    # campaign each. Two mods built on the same base can agree on their
    # countries, their technologies and their whole invention array, so the
    # search is a good guess and nothing more -- being told beats it every time.
    chosen = {}
    for name, path in args.campaign_mod or ():
        path = os.path.expanduser(os.path.expandvars(path))
        if not os.path.isdir(os.path.join(path, "common")):
            raise RunError("--campaign-mod %s: %s has no common/ inside it, so it is "
                     "not a mod folder." % (name, path))
        on_the_game(path, "--campaign-mod %s" % name)
        chosen[name.lower()] = path
    if args.mod_path:
        on_the_game(args.mod_path, "--mod-path")

    # Naming a mod is an answer, not a hint. Campaigns played on the same mod
    # are the ordinary case, and being told which one is better evidence than
    # anything that can be inferred, so the search is skipped entirely.
    if args.mod_path:
        label = os.path.basename(os.path.normpath(args.mod_path))
        found = []
        for name, path, files in campaigns_in(parent):
            # One mod for all of them is the general instruction; a campaign
            # named outright is the particular one, and the particular wins.
            told = chosen.get(name.lower())
            found.append(Surveyed(
                name, path, files,
                mod_label=(os.path.basename(os.path.normpath(told))
                           if told else label),
                mod_path=told or args.mod_path, told=bool(told)))
        if verbose:
            odd = sum(1 for e in found if e.told)
            print("Campaigns found under %s, read under %s%s:"
                  % (parent, label,
                     "" if not odd else " except where named"))
            for entry in found:
                print("  %-22s %3d saves%s"
                      % (entry.name, len(entry.files),
                         "  ->  %s   (as told)" % entry.mod_label
                         if entry.told else ""))
    elif not game_root and not chosen:
        raise RunError("--cross needs --game-root (the Victoria 2 install folder, the "
                 "one with mod/ inside) to work each campaign's mod out, "
                 "--mod-path to read them all under one mod, or "
                 "--campaign-mod to name them one at a time.")
    else:
        # Every campaign named outright is settled before anything is searched
        # for; only the rest go through `survey`, and if none are left the
        # search does not run at all.
        folders = campaigns_in(parent)
        unsettled = [e for e in folders if e[0].lower() not in chosen]
        found = (survey(parent, game_root) if (unsettled and game_root)
                 else [Surveyed(n, p, f) for n, p, f in folders])
        for entry in found:
            override = chosen.get(entry.name.lower())
            if override:
                entry.mod_path = override
                entry.mod_label = os.path.basename(os.path.normpath(override))
                entry.candidates = []
                entry.told = True
        if verbose:
            print("Campaigns found under %s:" % parent)
            for entry in found:
                fits = sum(1 for _l, v, _d in entry.candidates if v == "fits")
                print("  %-22s %3d saves  ->  %s%s"
                      % (entry.name, len(entry.files),
                         entry.mod_label or "no mod in that folder fits",
                         "   (as told)" if entry.told else ""))
                if entry.told:
                    continue
                nearest = [r for r in entry.candidates if r[1] == "nearest"]
                if nearest:
                    print("      WARNING: nothing in %s explains these saves. "
                          "The closest is %s, and it does not match: %s. The "
                          "numbers below are computed against a mod this "
                          "campaign was not played on -- name the right one "
                          "with --mod-path."
                          % (game_root, nearest[0][0], nearest[0][2]))
                elif fits > 1:
                    print("      note: %d mods fit these saves; picked the one "
                            "the campaign leaves least of unused. Name it with "
                            "--mod-path, or in the window pick the mod itself "
                            "instead of the folder, to settle it." % fits)
                elif not entry.mod_label:
                    print("      note: nothing in %s explains these saves. If "
                          "the mod is installed elsewhere, point the mod box "
                          "at it directly." % game_root)
    if verbose:
        for entry in found:
            for stray, worst, of in history_breaks(entry.files):
                print("      note: %s disagrees with all %d later saves by at "
                      "least %d event flags; it may be from another game"
                      % (stray, of, worst))
    return found


def cross_stamp(found, args):
    """
    The report stamp of a `--cross` run: every campaign that will be read,
    its saves, and the mod it is read under.
    """
    from mod_reader import mod_signature
    read = [entry for entry in found if entry.mod_path]
    world = "\n".join("%s|%s|%s" % (entry.name,
                                    os.path.abspath(entry.mod_path),
                                    mod_signature(entry.mod_path))
                       for entry in read)
    return report_stamp([f for entry in read for f in entry.files], args,
                        world)


def campaign_rows(parsed, mod, args, wanted=None):
    """
    One campaign's saves as finalized rows: (date, tag, nation).

    The same finishing the single-campaign path runs -- the same function
    against a spec from the same builder -- so a measure means here exactly
    what it means on the report's own charts. A second copy of the recipe
    had once drifted from the first in five places.

    `finishing.finish_nations` is called through the module, so that
    `testkit/crossrows.py` can watch both of its callers.
    """
    live = None
    if mod is not None:
        # Until this has run the mod refuses to say which base decodes the
        # campaign's invention indices, because "nobody looked" and "they do
        # not decode" mean different things and only one of them is a reason
        # to fall back to guessing what a nation holds.
        live, _every = settle_campaign(mod, parsed)

    spec = finishing.finish_spec(args, mod, live, wanted)
    out = []
    for meta, nations in parsed:
        for tag, done in finishing.finish_nations(meta, nations, spec).items():
            if finishing.kept_by(spec, tag, done):
                out.append((meta["date"], tag, done))
    return out


def run_cross(parent, found, args, verbose=True):
    """
    Read every campaign `survey_cross` found, each under its own mod.

    Returns (cross payload, the chosen campaign's files, its mod path, the
    `Reading` its saves were read under). That campaign -- the one
    `--primary` names, else the one with most saves -- becomes the subject
    of the ordinary report, so the cross-campaign block is an addition
    rather than a replacement.
    """
    from mod_reader import load_mod, name_for

    results, names, primary = [], {}, None
    for entry in found:
        if not entry.mod_path:
            if verbose:
                print("  skipping %s: no mod in %s explains its saves"
                      % (entry.name, args.game_root))
            continue
        mod = load_mod(entry.mod_path)
        # The defaults `main` applies, applied here too, so `--mob-types`
        # means the same on a cross run as on a single one. Only the pop list
        # is wanted here, for the parse; the regiment size comes from the
        # same function where `campaign_rows` builds the finishing spec.
        _regiment_size, mob_types = finishing.mod_defaults(args, mod)
        # How this campaign's saves are read, which is also their cache key.
        reading = reading_for(entry.mod_path, mod, mob_types)
        dates = dates_of(entry.files)
        files = one_per_date(in_date_order(entry.files, dates), dates)
        if verbose:
            print("Reading %s (%d saves) under %s"
                  % (entry.name, len(files), entry.mod_label))
        parsed = parse_saves(files, verbose=False,
                             use_cache=not args.no_cache, reading=reading,
                             jobs=args.jobs)
        if not parsed:
            continue
        parsed.sort(key=lambda p: sort_key(p[0]["date"]))
        results.append((entry.name, entry.mod_label,
                        campaign_rows(parsed, mod, args,
                                      set(args.tags) if args.tags else None)))
        # Nation names come from whichever mod names them: a tag any mod names
        # is better than the bare tag, and where two mods share a tag they were
        # measured to agree on it. Country names live in the localisation, not
        # in `display_names`, which is goods and unit types.
        loc = mod.localisation or {}
        for _meta, nations in parsed:
            for tag, nat in nations.items():
                if tag not in names:
                    label = name_for(tag, str(nat.get("government") or ""), loc)
                    if label and label != tag:
                        names[tag] = label
        if args.primary:
            if entry.name.lower() == args.primary.lower():
                primary = (entry, files, reading)
        elif primary is None or len(files) > len(primary[1]):
            primary = (entry, files, reading)

    if args.primary and primary is None and results:
        known = ", ".join(name for name, _m, _p in results)
        raise RunError("No campaign called %r under %s. There is: %s"
                 % (args.primary, parent, known))
    if not results or primary is None:
        return None, [], args.mod_path, PLAIN
    entry, files, reading = primary
    payload = series_payload(results, names=names)
    if verbose:
        print("Cross-campaign: %d campaigns, %d nations in two or more of them."
              % (len(payload["campaigns"]), len(payload["tags"])))
        print("The rest of the report is %s%s."
              % (entry.name,
                 "" if args.primary else " (the most saves; --primary picks "
                                         "another)"))
    return payload, files, entry.mod_path, reading

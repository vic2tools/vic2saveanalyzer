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

import json
import os

from tech_groups import ARMY_LINES, NAVY_LINES
from template import TEMPLATE

METRICS = [
    ("total_pop", "Total population", "count"),
    ("accepted_pop", "Accepted-culture population", "count"),
    ("accepted_pct", "Accepted share", "percent"),
    ("primary_culture_pop", "Primary-culture population", "count"),
    ("avg_literacy", "Average literacy", "fraction"),
    ("brigades", "Brigades (all)", "count"),
    ("regular_brigades", "Standing brigades", "count"),
    ("mobilized_brigades", "Mobilized brigades", "count"),
    ("mobilizing", "Mobilizing (queued)", "count"),
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

# Cultures per nation per save, beyond which the tail is negligible and only
# inflates the file.
MAX_CULTURES = 30


def year_fraction(date):
    try:
        y, m, d = (int(p) for p in date.split("."))
        return y + (m - 1) / 12.0 + (d - 1) / 365.0
    except (ValueError, AttributeError):
        return 0.0


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
    from mod_reader import (country_colours, province_names, province_raster,
                            sea_provinces, unit_positions)

    if not mod or not mod.get("path"):
        return None
    width, height, runs = province_raster(mod["path"], scale)
    if not width:
        return None

    colours = country_colours(mod["path"])
    sea = sea_provinces(mod["path"])
    full_height = height * scale

    # Only provinces that ever hold troops need an anchor, which is a fraction
    # of the 3,000-odd the file lists.
    garrisoned = {pid
                  for _meta, nations in parsed
                  for nat in nations.values()
                  for pid in nat.get("units_at", {})
                  if pid > 0}
    spots = {}
    for pid, (x, y) in unit_positions(mod["path"]).items():
        if pid not in garrisoned:
            continue
        # positions.txt measures y from the bottom, like the bitmap
        spots[pid] = [round(x / scale, 1), round((full_height - y) / scale, 1)]

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
                here.setdefault(str(pid), []).append([
                    index.get(tag, -1), total,
                    ";".join(f"{t}:{n}" for t, n in
                             sorted(types.items(), key=lambda kv: -kv[1])),
                ])
        armies[date] = here

    return {
        "w": width,
        "h": height,
        "scale": scale,
        "runs": " ".join(_b36(p) if c == 1 else _b36(p) + "." + _b36(c)
                         for p, c in runs),
        "tags": tags,
        "colours": {t: colours[t] for t in tags if t in colours},
        "sea": sorted(sea),
        "spots": spots,
        "names": {p: n for p, n in province_names(mod["path"]).items()
                  if p in spots},
        "owners": owners,
        "armies": armies,
    }


def _war_key(war):
    return (war["name"], war["original_attacker"], war["original_defender"],
            war["start"])


def _battle_key(battle, seen):
    """Identify a battle across saves. Province, name and both casualty counts
    pin it down; a repeat of all four in the same war gets an occurrence
    number, which is the only way two identical assaults stay separate."""
    base = (battle["name"], battle["location"],
            (battle["attacker"] or {}).get("losses", 0),
            (battle["defender"] or {}).get("losses", 0))
    seen[base] = seen.get(base, 0) + 1
    return base + (seen[base],)


def _at_sea(battle, kinds):
    """A battle is naval when the units present are ships."""
    for side in ("attacker", "defender"):
        for unit in ((battle.get(side) or {}).get("units") or {}):
            if kinds.get(unit) == "naval":
                return True
            if kinds.get(unit) == "land":
                return False
    return False


def _ledger_at(books, date, before):
    """Province ownership at the save just before, or just after, a date."""
    when = year_fraction(date)
    if before:
        fit = [b for d, b in books if year_fraction(d) <= when]
        return fit[-1] if fit else (books[0][1] if books else {})
    fit = [b for d, b in books if year_fraction(d) >= when]
    return fit[0] if fit else (books[-1][1] if books else {})


def _state_label(region, pid, state_names, province_names):
    """
    What to call the state a war goal names.

    Most have a name in the mod's localisation. Six in IGoR do not -- Goa, Diu,
    Pondicherry, Trankebar and the two canal zones, each a state of one province
    -- and the game itself falls back to naming them after that province, which
    is why one of these wars is called the Italian Colonial Conquest of Goa
    Region. Same fallback here, and the region key only if even that is missing.
    """
    named = state_names.get(region)
    if named:
        return named
    province = province_names.get(pid)
    if province:
        return f"{province} Region"
    return region or ""


def build_wars(parsed, province_names=None, province_regions=None,
               state_names=None, unit_kinds=None):
    """
    Every war in the campaign, with battle dates recovered across saves.

    A save dates only its most recent battles and drops the dates from older
    ones, so the latest save alone can date about 3% of them. Reading the whole
    folder lifts that to around 90%: each save catches a different window and
    the windows tile the campaign. What is still undated is left undated rather
    than guessed -- inheriting the last date seen while scanning, which is what
    the obvious approach does, is wrong for 97% of battles.
    """
    province_names = province_names or {}
    state_names = state_names or {}
    unit_kinds = unit_kinds or {}
    # Saves arrive in filename order, which is not date order: "mp_Italy1884"
    # sorts before "mp_The_United States1840". Diffing province ownership down
    # that list compares 1884 against 1840 and invents transfers.
    parsed = sorted(parsed, key=lambda pair: year_fraction(pair[0].get("date") or ""))
    wars = {}
    order = []
    for meta, _nations in parsed:
        for war in meta.get("wars", ()):
            key = _war_key(war)
            if key not in wars:
                wars[key] = {k: v for k, v in war.items() if k != "battles"}
                wars[key]["battles"] = {}
                order.append(key)
            held = wars[key]
            # a war that was active in an earlier save has since ended
            if war.get("end") and not held.get("end"):
                held["end"] = war["end"]
            if war.get("start") and (not held.get("start")
                    or year_fraction(war["start"]) < year_fraction(held["start"])):
                held["start"] = war["start"]
            if not war.get("active"):
                held["active"] = False
            for field in ("attackers", "defenders"):
                held[field] = sorted(set(held[field]) | set(war[field]))
            # Goals added mid-war vanish when it ends, so take them from
            # whichever save caught the war still running.
            book = held.setdefault("goalbook", {})
            for g in war.get("goals", ()):
                key = (g["actor"], g["receiver"], g["province"], g["casus_belli"])
                if key not in book or g["fulfilled"]:
                    book[key] = g
            seen = {}
            for battle in war["battles"]:
                bkey = _battle_key(battle, seen)
                there = held["battles"].get(bkey)
                if there is None:
                    held["battles"][bkey] = battle
                elif battle["date"] and not there["date"]:
                    there["date"] = battle["date"]      # a save that still knew

    # --- who took what, from the province ledger either side of each save
    shifts = []
    books = []
    previous = None
    for meta, _nations in parsed:
        book = {pid: owner for pid, (owner, _c) in
                meta.get("province_owner", {}).items()}
        books.append((meta.get("date") or "", book))
        if previous is not None:
            moved = [(pid, previous[0].get(pid), owner)
                     for pid, owner in book.items()
                     if previous[0].get(pid) and previous[0].get(pid) != owner]
            if moved:
                shifts.append((previous[1], meta.get("date") or "", moved))
        previous = (book, meta.get("date") or "")

    out = []
    for key in order:
        war = wars[key]
        battles = sorted(war["battles"].values(),
                         key=lambda b: (year_fraction(b["date"]) if b["date"]
                                        else 9999.0, b["name"]))
        atk = sum((b["attacker"] or {}).get("losses", 0) for b in battles)
        dfd = sum((b["defender"] or {}).get("losses", 0) for b in battles)
        # The war goal names one province of the state it wants, and names both
        # the nation demanding it and the nation holding it. That is far firmer
        # than guessing from timing: compare who held that state before the war
        # against who held it after, and the war either got what it asked for or
        # it did not. A war whose attacker is force-peaced out keeps its goal
        # and simply fails to meet it.
        # Every goal the war ever carried: the one it opened with, plus any
        # added while it ran and caught by a save. A war is not one demand --
        # the French Conquest of Friesland carried a French claim on Prussia
        # and two American claims, one of them on Mexico, and it is that third
        # goal that moved Georgia.
        recovered = list(war.get("goalbook", {}).values())
        listed = recovered or ([war["goal"]] if war["goal"]["actor"] else [])
        before = _ledger_at(books, war["start"], True) if war.get("start") else {}
        after = _ledger_at(books, war["end"] or war["start"], False)             if war.get("start") else {}
        goals, transfers = [], []
        for g in listed:
            actor, receiver, pid = g["actor"], g["receiver"], g["province"]
            state = (province_regions or {}).get(pid)
            wanted = ([p for p, s in (province_regions or {}).items() if s == state]
                      if state else ([pid] if pid else []))
            took = [p for p in wanted
                    if before.get(p) == receiver and after.get(p) == actor]
            had = [p for p in wanted if before.get(p) == receiver]
            # `is_fulfilled` is NOT the outcome. It says the claimant currently
            # holds the state by siege at the moment that save was taken, which
            # is a live condition during the war and says nothing about the
            # peace: the French claim on Prussia in the Friesland war reads
            # fulfilled and moved no province at all. Whether a goal was
            # actually met is only answerable from who owned the state either
            # side of the war.
            goals.append({
                "cb": g["casus_belli"], "actor": actor, "receiver": receiver,
                # The name the game shows, not the region key it is filed
                # under: NET_385 is Friesland, and the war is already called
                # the French Conquest of Friesland two lines above it.
                "state": _state_label(state, pid, state_names, province_names),
                "added": g.get("added", ""),
                "took": len(took), "of": len(had),
                "met": bool(had) and len(took) == len(had),
                "part": bool(took) and len(took) < len(had),
                "sieged": g.get("fulfilled") if "fulfilled" in g else None,
                "checkable": bool(had),
            })
            if took:
                # A war takes a state, not a scattered handful of provinces:
                # five names under Tabriz is one line, not five.
                transfers.append([state or "",
                                  _state_label(state, took[0], state_names,
                                               province_names),
                                  receiver, actor, len(took), len(had)])
        checkable = [g for g in goals if g["checkable"]]
        won = sum(1 for g in checkable if g["met"] or g["part"])
        outcome = (f"{won} of {len(checkable)} taken" if checkable else "")
        out.append({
            "name": war["name"],
            "start": war["start"],
            "end": war["end"],
            "active": bool(war["active"]),
            "attackers": war["attackers"] or [war["original_attacker"]],
            "defenders": war["defenders"] or [war["original_defender"]],
            "goal": war["goal"],
            "losses": [atk, dfd],
            "outcome": outcome,
            "goals": goals,
            "dated": sum(1 for b in battles if b["date"]),
            "battles": [{
                "sea": _at_sea(b, unit_kinds),
                "name": b["name"],
                "province": b["location"],
                "date": b["date"] or "",
                "won": b["attacker_won"],
                "a": [(b["attacker"] or {}).get("country", ""),
                      (b["attacker"] or {}).get("leader", ""),
                      (b["attacker"] or {}).get("losses", 0),
                      _units(b["attacker"])],
                "d": [(b["defender"] or {}).get("country", ""),
                      (b["defender"] or {}).get("leader", ""),
                      (b["defender"] or {}).get("losses", 0),
                      _units(b["defender"])],
            } for b in battles],
            "transfers": transfers,
        })
    out.sort(key=lambda w: year_fraction(w["start"]) if w["start"] else 9999.0)
    return out


def _units(side):
    if not side or not side.get("units"):
        return ""
    return ";".join(f"{k}:{v}" for k, v in
                    sorted(side["units"].items(), key=lambda kv: -kv[1]))



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
            for old in vanished:
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


def build_report(rows, ship_rows, pop_rows, culture_rows, price_rows,
                 snapshot_rows, brigade_rows, tech_rows, outdir,
                 tag_names=None, map_data=None,
                 base_prices=None, great_powers=None, flags=None,
                 technology=None, wars=None, succession=None,
                 filename="report.html"):
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

    ships, ship_types = {}, set()
    for row in ship_rows:
        ship_types.add(row["ship_type"])
        ships.setdefault(row["tag"], {}).setdefault(row["date"], {})[
            row["ship_type"]] = int(row["count"])

    brigades, regiment_types = {}, set()
    for row in brigade_rows:
        regiment_types.add(row["regiment_type"])
        brigades.setdefault(row["tag"], {}).setdefault(row["date"], {})[
            row["regiment_type"]] = int(row["count"])

    # Techs are referenced by index so the payload does not repeat 100+ names
    # once per nation per save.
    tech_order, tech_meta = [], []
    for branch, lines in (("army", ARMY_LINES), ("navy", NAVY_LINES)):
        for line, techs in lines:
            for tech in techs:
                tech_order.append(tech)
                tech_meta.append([branch, line])
    seen_tech = set(tech_order)
    extra = sorted({r["technology"] for r in tech_rows} - seen_tech)
    for tech in extra:
        tech_order.append(tech)
        tech_meta.append(["other", "Other"])
    tech_index = {t: i for i, t in enumerate(tech_order)}

    techs_by = {}
    for row in tech_rows:
        idx = tech_index.get(row["technology"])
        if idx is None:
            continue
        techs_by.setdefault(row["tag"], {}).setdefault(row["date"], []).append(idx)
    for tag in techs_by:
        for date in techs_by[tag]:
            techs_by[tag][date].sort()

    pops, pop_types = {}, set()
    for row in pop_rows:
        pop_types.add(row["pop_type"])
        pops.setdefault(row["tag"], {}).setdefault(row["date"], {})[
            row["pop_type"]] = int(row["size"])

    cultures = {}
    for row in culture_rows:
        cultures.setdefault(row["tag"], {}).setdefault(row["date"], []).append(
            [row["culture"], int(row["size"]), int(row["accepted"])])
    for tag in cultures:
        for date in cultures[tag]:
            cultures[tag][date].sort(key=lambda c: -c[1])
            del cultures[tag][date][MAX_CULTURES:]

    # ---- market ----
    price_dates, pseen = [], set()
    goods_meta, prices = {}, {}
    for row in price_rows:
        date = row["date"]
        if date not in pseen:
            pseen.add(date)
            price_dates.append(date)
        good = row["good"]
        goods_meta.setdefault(good, row.get("category", "other"))
        prices.setdefault(good, {})[date] = float(row["price"])
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
        # Vic2 pins a good at its price floor by adding a ~2e9 sentinel to
        # `demand`. `real_demand` is the honest number, and the sentinel is
        # itself a useful signal about which goods are bottomed out.
        raw_demand = float(row["demand"])
        snapshot.setdefault(row["date"], {})[row["good"]] = {
            "price": float(row["price"]),
            "supply": float(row["supply"]),
            "demand": float(row["real_demand"]),
            "actual_sold": float(row["actual_sold"]),
            "floored": int(raw_demand > 1e9),
            "discovered": int(row["discovered"]),
        }

    facts = {}
    for row in rows:
        facts.setdefault(row["date"], {})[row["tag"]] = {
            "total_pop": int(float(row.get("total_pop") or 0)),
            "accepted_pop": int(float(row.get("accepted_pop") or 0)),
            "accepted_pct": float(row.get("accepted_pct") or 0),
            "avg_literacy": float(row.get("avg_literacy") or 0),
            "avg_militancy": float(row.get("avg_militancy") or 0),
            "avg_consciousness": float(row.get("avg_consciousness") or 0),
            "brigades": int(float(row.get("brigades") or 0)),
            "regular_brigades": int(float(row.get("regular_brigades") or 0)),
            "mobilized_brigades": int(float(row.get("mobilized_brigades") or 0)),
            "mobilizing": int(float(row.get("mobilizing") or 0)),
            "mobilization_pool": int(float(row.get("mobilization_pool") or 0)),
            "mobilization_brigades": int(float(row.get("mobilization_brigades") or 0)),
            "mobilisation_size": float(row.get("mobilisation_size") or 0),
            "is_mobilized": int(float(row.get("is_mobilized") or 0)),
            "ships": int(float(row.get("ships") or 0)),
            "factory_levels": int(float(row.get("factory_levels") or 0)),
            "provinces": int(float(row.get("provinces") or 0)),
            "prestige": float(row.get("prestige") or 0),
            "primary_culture": row.get("primary_culture", ""),
            "techs": int(float(row.get("techs") or 0)),
            "army_techs": int(float(row.get("army_techs") or 0)),
            "navy_techs": int(float(row.get("navy_techs") or 0)),
        }


    payload = {
        "dates": dates,
        "years": [year_fraction(d) for d in dates],
        "tags": tags,
        "tagNames": {t: tag_names.get(t, t) for t in tags},
        "metrics": [
            {"key": key, "label": label, "fmt": fmt}
            for key, label, fmt in METRICS if key in metric_keys
        ],
        "series": series,
        "facts": facts,
        "ships": ships,
        "shipTypes": sorted(ship_types),
        "brigades": brigades,
        "regimentTypes": sorted(regiment_types),
        "techOrder": tech_order,
        "techMeta": tech_meta,
        "techsBy": techs_by,
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
        "prices": prices,
        "goods": sorted(prices),
        "goodCategory": goods_meta,
        "categoryLabels": CATEGORY_LABELS,
        "movement": movement,
        "snapshot": snapshot,
        "snapshotDates": sorted(snapshot, key=year_fraction),
    }

    span = f"{dates[0]} – {dates[-1]}" if dates else "—"
    price_span = (f"{price_dates[0]} – {price_dates[-1]}"
                  if price_dates else "no price data")

    html = TEMPLATE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
    html = html.replace("__SAVECOUNT__", str(len(dates)))
    html = html.replace("__NATIONCOUNT__", str(len(tags)))
    html = html.replace("__SPAN__", span)
    html = html.replace("__PRICESPAN__", price_span)

    path = os.path.join(outdir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path

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
Every war in a campaign, put together from the saves it passes through.

A save carries every war there has ever been, but only a window of each:
the most recent battles are dated and the older ones are not, and a war
that has ended keeps its sides but loses who joined when. `fold_wars`
merges one save's war list into a book that spans the campaign, oldest
save first; `pack_wars` and `fold_packed_wars` are the same fold for a
save whose wars were sent from a worker, which skips a war whose record
has not changed since it was last folded; and `build_wars` turns the book
into the Wars tab.

Reading a war out of a save is `readwar.read_war`'s job. This is what the
campaign makes of them, so it is imported by the finishing in the workers,
by the walk in `main`, and by the report -- and by none of the reading, so
editing it leaves the parse cache alone.
"""

import bisect
import pickle

from dates import year_fraction

INFINITY = float("inf")


def _war_key(war):
    """
    What makes two war records the same war, ignoring when they were read.

    Not the start date, which is the trap this used to fall into. A war's start
    is the earliest dated entry in its history, and that history shrinks as the
    war ages: battles lose their dates, so a war caught while it was being
    fought starts at its first battle, and the same war read from a later save
    starts at whatever dated entry is left -- often the engine's own removal
    events on the day it ended. Keying on that gave one war two identities, and
    the copy taken while it was live was never told it had finished, so it sat
    in the table marked ongoing for the rest of the campaign with the real
    ended row beneath it.

    A name and its two original belligerents do repeat across a long campaign,
    though, so this is only half an identity; `fold_wars` separates two fights
    that share one by the stretch of time each covers.
    """
    return (war["name"], war["original_attacker"], war["original_defender"])


def _war_span(war):
    """
    The stretch of time a war record covers, in year fractions.

    A record still being fought has no end, and runs to whenever the campaign
    got to -- which is what lets a later reading of it, dated only by the
    removals that closed it, be recognised as the same war. `None` where the
    record carries no date at all and says nothing about when it was fought.
    """
    if not war.get("start"):
        return None
    first = year_fraction(war["start"])
    if war.get("active"):
        return (first, INFINITY)
    last = year_fraction(war["end"]) if war.get("end") else first
    return (first, last if last > first else first)


def _participants(tags, join_dates, is_attacker, original_tag, start,
                  leave_dates=None, end=""):
    """
    Split one side's belligerents into original combatants and later
    interventions.

    A tag counts as original if it's the war's named original attacker or
    defender, if it has no recorded join date (founders usually aren't
    logged joining their own war -- only reinforcements get an explicit
    `add_attacker`/`add_defender` event), or if its first join date falls
    within a month of the war's start. Everything else is a later
    intervention. Originals sort first, each group oldest-joined first.
    """
    cutoff = year_fraction(start) + 1 / 12.0 if start else None
    out = []
    for tag in tags:
        joined = join_dates.get((tag, is_attacker), "")
        original = (
            tag == original_tag or not joined
            or cutoff is None or year_fraction(joined) <= cutoff
        )
        row = {"tag": tag, "joined": joined, "original": original}
        # The war leader: the one who declared it, or the one it was declared
        # on, and the one who signs the peace. The page flies its flag large.
        if tag == original_tag:
            row["leads"] = True
        # The engine removes everybody when a war ends, so most recorded exits
        # are the war finishing rather than anyone leaving it: 17,964 of 18,657
        # in one campaign fall on the war's own end date. Only an exit before
        # that says something the war's dates do not already say.
        #
        # An exit outside the war's own span is not this war's. A save keeps
        # only its most recent history and drops the rest, so an old war can be
        # reported ending earlier by a later save than by an earlier one, and a
        # handful of war names repeat with the same seeded start date. Either
        # can leave a date here that belongs to a different fight; shown, it
        # would read as a nation leaving a war years after that war ended.
        gone = (leave_dates or {}).get((tag, is_attacker), "")
        if gone and gone != end:
            after_start = not joined or year_fraction(gone) >= year_fraction(joined)
            before_end = not end or year_fraction(gone) < year_fraction(end)
            if after_start and before_end:
                row["left"] = gone
        out.append(row)
    out.sort(key=lambda p: (not p["original"],
                             year_fraction(p["joined"]) if p["joined"] else 0.0,
                             p["tag"]))
    return out


def _battle_key(battle, seen):
    """Identify a battle across saves. Province, name and both casualty counts
    pin it down; a repeat of all four in the same war gets an occurrence
    number, which is the only way two identical assaults stay separate."""
    base = (battle["name"], battle["location"],
            (battle["attacker"] or {}).get("losses", 0),
            (battle["defender"] or {}).get("losses", 0))
    seen[base] = seen.get(base, 0) + 1
    return base + (seen[base],)


def _side_losses(battles, attackers, defenders):
    """
    A war's casualties split between the two coalitions.

    `losses` counts by the role each nation played in each *battle*, which is
    not the same question: France defending an assault and France storming a
    fort the next month are both France, on the same side of the war. This
    sorts each battle's two figures by which coalition the nation fighting is
    in, so the pair adds up to the same total from the other direction.

    A nation can appear on both lists. Sometimes that is real -- a civil war
    where the same tag is recorded fighting itself -- and sometimes it is two
    wars that share a key merged into one record. Either way the tag alone
    cannot say which side it was on, so the battle answers instead: the two
    combatants in a battle are on opposite sides, so an unclear tag takes the
    opposite of whatever its opponent unambiguously is. Across 780 wars in
    three campaigns that left nothing unresolved, and the split reconciled
    with the plain total in every one.
    """
    att = set(attackers)
    dfd = set(defenders)

    def which(tag):
        """1 for the attacking coalition, -1 for the defending, 0 for unclear."""
        here, there = tag in att, tag in dfd
        return 1 if here and not there else -1 if there and not here else 0

    totals = [0, 0, 0]          # attackers, defenders, neither
    for battle in battles:
        pair = [battle.get("attacker") or {}, battle.get("defender") or {}]
        marks = [which(side.get("country") or "") for side in pair]
        if marks[0] == 0 and marks[1] != 0:
            marks[0] = -marks[1]
        if marks[1] == 0 and marks[0] != 0:
            marks[1] = -marks[0]
        for side, mark in zip(pair, marks):
            totals[0 if mark > 0 else 1 if mark < 0 else 2] += \
                side.get("losses", 0)
    return totals


def _at_sea(battle, kinds):
    """A battle is naval when the units present are ships."""
    for side in ("attacker", "defender"):
        for unit in ((battle.get(side) or {}).get("units") or {}):
            if kinds.get(unit) == "naval":
                return True
            if kinds.get(unit) == "land":
                return False
    return False


def _ledger_at(books, when_each, date, before):
    """
    Province ownership at the save just before, or just after, a date.

    `when_each` is the year fraction of each save, in the same order as
    `books`, which is date order. Both are asked for twice per war, so this
    bisects rather than walking the campaign each time.
    """
    if not books:
        return {}
    when = year_fraction(date)
    if before:
        at = bisect.bisect_right(when_each, when) - 1
        return books[max(at, 0)][1]
    at = bisect.bisect_left(when_each, when)
    return books[min(at, len(books) - 1)][1]


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


def fold_wars(book, war_list):
    """
    Fold one save's war list into a running book, `{"wars": {}, "order": []}`.

    A save carries the whole war history up to its date, not just what is
    happening now: by 1908 that is two and a half megabytes of it, and only two
    hundred and sixty of the wars are distinct. Thirty-eight saves therefore
    hold fifty megabytes of overlapping copies, and twelve hundred monthly ones
    would hold nearly two gigabytes. Folded into one book as the campaign is
    walked, the campaign keeps one copy of each war, and every save can drop
    its own list the moment it has been read. Saves are folded oldest first,
    because which of two readings of the same war goal is kept depends on
    which was seen first.
    """
    wars, order = book["wars"], book["order"]
    # Every war each name-and-belligerents triple has produced so far, as
    # [key, first, last] with the stretch it covers kept up to date as records
    # are folded in. A save's record joins the war it overlaps; a war of the
    # same name fought again years later overlaps nothing and starts a row of
    # its own. Held here rather than recomputed from each war because this is
    # the campaign's innermost loop -- a monthly century asks it a hundred
    # thousand times.
    index = book.setdefault("index", {})
    for war in war_list:
        name = _war_key(war)
        span = _war_span(war)
        slot = index.get(name)
        if slot is None:
            slot = index[name] = []
        found = None
        for entry in slot:
            # `entry[2]` is None until some save has seen this war finish: a
            # record that was still being fought when its save was taken only
            # says the war had not ended yet, so it stays open to anything
            # after it. Once a save reports the end, the war stops swallowing
            # later fights of the same name.
            top = INFINITY if entry[2] is None else entry[2]
            if span is None or entry[1] is None or (
                    entry[1] <= span[1] and span[0] <= top):
                found = entry
                break
        if found is None:
            key = name + (len(slot),)
            wars[key] = {k: v for k, v in war.items() if k != "battles"}
            wars[key]["battles"] = {}
            order.append(key)
            found = [key, span[0] if span else None,
                     span[1] if span and span[1] != INFINITY else None]
            slot.append(found)
        elif span is not None:
            if found[1] is None or span[0] < found[1]:
                found[1] = span[0]
            if span[1] != INFINITY and (found[2] is None or span[1] > found[2]):
                found[2] = span[1]
        held = wars[found[0]]
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
        # Earliest date each tag is seen joining each side, across every save
        # that caught the war. A later save can only add events an earlier one
        # hadn't happened yet -- never move one earlier -- so keeping the
        # minimum date per (tag, side) is always safe.
        jd = held.setdefault("join_dates", {})
        for d, w, a in war.get("joins", ()):
            if not d:
                continue
            k = (w, a)
            if k not in jd or year_fraction(d) < year_fraction(jd[k]):
                jd[k] = d
        # And when each left. The latest, not the earliest: a nation that was
        # knocked out, came back and was knocked out again finished on the last
        # of those, and that is the one the war ended for it on.
        ld = held.setdefault("leave_dates", {})
        for d, w, a in war.get("leaves", ()):
            if not d:
                continue
            k = (w, a)
            if k not in ld or year_fraction(d) > year_fraction(ld[k]):
                ld[k] = d
        # Goals added mid-war vanish when it ends, so take them from whichever
        # save caught the war still running.
        goals = held.setdefault("goalbook", {})
        for g in war.get("goals", ()):
            gkey = (g["actor"], g["receiver"], g["province"], g["casus_belli"])
            if gkey not in goals or g["fulfilled"]:
                goals[gkey] = g
        seen = {}
        for battle in war["battles"]:
            bkey = _battle_key(battle, seen)
            there = held["battles"].get(bkey)
            if there is None:
                held["battles"][bkey] = battle
            elif battle["date"] and not there["date"]:
                there["date"] = battle["date"]          # a save that still knew


def fold_packed_wars(book, packed):
    """
    `fold_wars`, for one save's wars as a worker sends them: each war's
    identity (`_war_key`) and the war pickled on its own.

    A save carries every war there has ever been, and from one save to the
    next almost all of them are the same records again: the war ended long
    ago and nothing about it has changed. Unpickling them was half of what
    the parent spent receiving a save, and folding them as much again.

    A record whose bytes are exactly those of the last record folded under
    its identity is not unpickled or folded. That is exact, not a guess:
    folding a record keeps the earliest of its dates and the latest of its
    endings, the union of its sides, each battle once under its key, and its
    goals by replacement -- so folding the same record into the state it
    left behind changes nothing. And nothing else has changed that state:
    a record only ever touches the wars under its own identity, and any
    record folded there since would now be the last one. Any other record
    -- a war still being fought, a new battle, a second war of the same
    name -- is unpickled and folded as it always was.
    """
    last = book.setdefault("last_folded", {})
    for name, blob in packed:
        if last.get(name) == blob:
            continue
        fold_wars(book, [pickle.loads(blob)])
        last[name] = blob


def pack_wars(wars):
    """One save's wars as `fold_packed_wars` takes them."""
    return [(_war_key(war), pickle.dumps(war, pickle.HIGHEST_PROTOCOL))
            for war in wars]


def build_wars(parsed, province_names=None, province_regions=None,
               state_names=None, unit_kinds=None, *, book):
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
    # `book` is the campaign's wars, folded save by save as it was walked;
    # see `fold_wars`.
    wars, order = book["wars"], book["order"]

    # --- who took what, from the province ledger either side of each save.
    # Only the ledgers themselves are wanted here: what changed hands between
    # one save and the next used to be diffed alongside them, province by
    # province, and then never read. On a monthly campaign that was a few
    # million comparisons and a list of every province that ever moved, both
    # thrown away at the end of the function.
    books = [(meta.get("date") or "",
              {pid: owner for pid, (owner, _c)
               in meta.get("province_owner", {}).items()})
             for meta, _nations in parsed]

    # Which provinces each state holds, indexed once. The goal loop below asks
    # this of every goal of every war, and scanning the whole province table
    # each time is a few million comparisons to answer a lookup.
    state_provinces = {}
    for _pid, _state in (province_regions or {}).items():
        state_provinces.setdefault(_state, []).append(_pid)
    # Where each save sits on the year axis, so the ownership either side of a
    # war is a bisect rather than a walk down every save in the campaign.
    ledger_dates = [year_fraction(d) for d, _b in books]

    out = []
    for key in order:
        war = wars[key]
        battles = sorted(war["battles"].values(),
                         key=lambda b: (year_fraction(b["date"]) if b["date"]
                                        else 9999.0, b["name"]))
        # A war cannot have ended before its own last battle. The end is the
        # latest dated entry of whichever save first caught the war finished,
        # and that history is already being trimmed by then: the 3rd American
        # War of Independence came out ending 1874.8.3, which is the day one
        # defender dropped out, while three battles other saves had dated ran
        # on to 1874.8.25. Where the two disagree the battle is the harder
        # fact -- men died there -- so it sets the end, which also puts the
        # ownership check below on the right side of the peace.
        last_battle = max((b["date"] for b in battles if b["date"]),
                          key=year_fraction, default="")
        end = war["end"]
        if (end and last_battle
                and year_fraction(last_battle) > year_fraction(end)):
            end = last_battle
        atk = sum((b["attacker"] or {}).get("losses", 0) for b in battles)
        dfd = sum((b["defender"] or {}).get("losses", 0) for b in battles)
        by_side = _side_losses(
            battles,
            war["attackers"] or [war["original_attacker"]],
            war["defenders"] or [war["original_defender"]])
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
        before = (_ledger_at(books, ledger_dates, war["start"], True)
                  if war.get("start") else {})
        # A war that was over before the first save has no before at all:
        # both lookups land on that first save, the state is compared with
        # itself, and nothing ever moved. The Austrian Liberation of
        # Moldavia, fought 1845-1849 and judged by an 1872 save against
        # itself, read "none taken" -- a verdict on a peace no save saw.
        # Only a save taken before the war ended can say who held the state
        # going in, so without one the goal is left unjudged.
        if (end and ledger_dates
                and ledger_dates[0] >= year_fraction(end)):
            before = {}
        after = (_ledger_at(books, ledger_dates, end or war["start"],
                            False) if war.get("start") else {})
        goals, transfers = [], []
        for g in listed:
            actor, receiver, pid = g["actor"], g["receiver"], g["province"]
            state = (province_regions or {}).get(pid)
            wanted = (state_provinces.get(state, ())
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
            "end": end,
            "active": bool(war["active"]),
            "attackers": war["attackers"] or [war["original_attacker"]],
            "defenders": war["defenders"] or [war["original_defender"]],
            "attacker_parties": _participants(
                war["attackers"] or [war["original_attacker"]],
                war.get("join_dates", {}), True,
                war["original_attacker"], war["start"],
                war.get("leave_dates", {}), end),
            "defender_parties": _participants(
                war["defenders"] or [war["original_defender"]],
                war.get("join_dates", {}), False,
                war["original_defender"], war["start"],
                war.get("leave_dates", {}), end),
            "goal": war["goal"],
            "losses": [atk, dfd],
            # The same casualties counted by coalition rather than by the role
            # each nation played in each battle. Third entry is whatever no
            # battle could place, which stays visible rather than being folded
            # into one of the sides.
            "side_losses": by_side,
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


def war_tags(wars):
    """
    Every nation `build_wars`' output names: both sides, every battle, every
    goal and every state that changed hands. Most of these were gone before
    the first save -- Baden, the North German Federation -- so nothing else
    in the report names them.
    """
    tags = set()
    for w in wars or ():
        tags.update(w["attackers"])
        tags.update(w["defenders"])
        for b in w["battles"]:
            tags.update((b["a"][0], b["d"][0]))
        for g in w["goals"]:
            tags.update((g["actor"], g["receiver"]))
        for t in w["transfers"]:
            tags.update(t[2:4])
    return {t for t in tags if t and t != "---"}


def _units(side):
    if not side or not side.get("units"):
        return ""
    return ";".join(f"{k}:{v}" for k, v in
                    sorted(side["units"].items(), key=lambda kv: -kv[1]))

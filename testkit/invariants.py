#!/usr/bin/env python3
"""
Check the arithmetic the report's own numbers have to satisfy.

Parity proves the two readers agree; it does not prove either of them is
right. These are the identities that hold whatever the save says -- the
strata are a partition of the population, a percentage is its own numerator
over its own denominator, brigades are the standing ones plus the mobilized
ones -- so a break is a bug in the counting and not a quirk of a campaign.

    python3 testkit/invariants.py out/nations_timeseries.csv [report.html]

Runs over every nation in every save. Says which rule broke, on which
nation and date, and by how much.
"""

import base64
import csv
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from outcome import SKIPPED                                 # noqa: E402
from dates import year_fraction                             # noqa: E402

# Floating point: literacy and money are accumulated in a different order
# from the totals they are checked against, so an identity can miss by a few
# parts in a billion and be perfectly correct. A break worth reporting is
# larger than the numbers involved, not larger than zero.
RELATIVE = 1e-9
ABSOLUTE = 1e-6


def near(a, b):
    """Whether two numbers are the same number, arrived at differently."""
    return abs(a - b) <= max(ABSOLUTE, RELATIVE * max(abs(a), abs(b)))


def number(row, key):
    """One field as a float. Missing or blank is zero, as the report reads it."""
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def percent_of(row, part, whole, places):
    """
    The percentage a report writes, rebuilt from its own two numbers.

    `places` because `finalize` does not round them all the same way: the
    accepted share goes to two, the rest to three. Worth knowing when
    reading them side by side, and not worth changing, since changing it
    would move numbers people have already seen.
    """
    bottom = number(row, whole)
    if not bottom:
        return 0.0
    return round(100.0 * number(row, part) / bottom, places)


# Each rule is (name, a function of the row returning (left, right)), and it
# holds when the two sides are the same number. Written as a pair rather
# than a boolean so a break can say by how much.
RULES = [
    ("the strata are the whole population",
     lambda r: (number(r, "total_pop"),
                number(r, "pop_poor") + number(r, "pop_middle")
                + number(r, "pop_rich"))),
    ("brigades are the standing ones plus the mobilized ones",
     lambda r: (number(r, "brigades"),
                number(r, "regular_brigades")
                + number(r, "mobilized_brigades"))),
    ("the accepted share is the accepted population over the whole",
     lambda r: (number(r, "accepted_pct"),
                percent_of(r, "accepted_pop", "total_pop", 2))),
    ("the unmet-needs share is that count over the whole",
     lambda r: (number(r, "life_unmet_pct"),
                percent_of(r, "life_unmet", "total_pop", 3))),
    ("the starving share is that count over the whole",
     lambda r: (number(r, "starving_pct"),
                percent_of(r, "starving", "total_pop", 3))),
    # Against the whole nation, colonies included, and deliberately so:
    # a soldier base of five million reads differently under fifty million
    # people than under two hundred. See `finalize`.
    ("the soldier share is that count over the whole population",
     lambda r: (number(r, "soldiers_noncolonial_pct"),
                percent_of(r, "soldiers_noncolonial", "total_pop", 3))),
]

# Fields that can only be one of two things, and fields that can only fall
# inside a range. A number outside them is not a small error; it means the
# field was read as something it is not.
FLAGS = ["is_player", "is_mobilized"]
RANGES = [
    ("avg_literacy", 0.0, 1.0),
    ("avg_literacy_stated", 0.0, 1.0),
    ("accepted_pct", 0.0, 100.0),
    ("life_unmet_pct", 0.0, 100.0),
    ("starving_pct", 0.0, 100.0),
    ("mobilisation_size", 0.0, 1.0),
]

# Counts, which cannot be negative. A negative one is a subtraction that
# ran the wrong way, and it would be plotted without comment.
NEVER_NEGATIVE = [
    "total_pop", "accepted_pop", "primary_culture_pop", "provinces",
    "states", "brigades", "regular_brigades", "mobilized_brigades",
    "mobilizing", "brigade_cap", "armies", "navies", "ships",
    "factory_count", "factory_levels", "ports", "naval_base_levels",
    "max_naval_base", "railroad_levels", "fort_levels", "techs",
    "army_techs", "navy_techs", "mobilization_pool",
    "mobilization_brigades", "life_unmet", "starving", "pop_poor",
    "pop_middle", "pop_rich", "pop_noncolonial", "soldiers_noncolonial",
]

# Rules that are an order rather than an equality: (name, left, right) holds
# when left <= right, allowing for the same floating-point slack.
ORDERED = [
    ("accepted culture is part of the population",
     "accepted_pop", "total_pop"),
    ("the primary culture is part of the accepted population",
     "primary_culture_pop", "accepted_pop"),
    ("people with unmet needs are part of the population",
     "life_unmet", "total_pop"),
    ("the starving are people whose needs are unmet",
     "starving", "life_unmet"),
    ("provinces with a naval base are provinces",
     "ports", "provinces"),
    ("the largest naval base is no larger than all of them together",
     "max_naval_base", "naval_base_levels"),
    ("soldiers outside the colonies are part of the population",
     "soldiers_noncolonial", "pop_noncolonial"),
    ("people outside the colonies are part of the population",
     "pop_noncolonial", "total_pop"),
    ("the mobilizable pool is part of the population",
     "mobilization_pool", "total_pop"),
    ("army and navy technologies are part of all technologies",
     "army_techs", "techs"),
    ("navy technologies are part of all technologies",
     "navy_techs", "techs"),
    ("standing brigades are within the cap",
     "regular_brigades", "brigade_cap"),
]


def payload_of(path):
    """The report's own data, or None if it carries none."""
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    found = re.search(r'const PACKED = "([^"]*)"', html)
    if not found or not found.group(1):
        return None                      # --split keeps it in another file
    return json.loads(gzip.decompress(base64.b64decode(found.group(1))))


def check_payload(data):
    """
    [(rule, what)] for everything in the report's data that does not hold.

    The table checks a nation against itself. These check the report
    against its own shape: that every column is as long as the list of
    dates it is read against, that every index points at something, that a
    war ends after it starts and its battles happen while it is being
    fought. A break here is a report that draws wrong, not one that adds
    up wrong.
    """
    bad = []

    def note(rule, what):
        bad.append((rule, what))

    dates, tags = data.get("dates", []), set(data.get("tags", []))
    if dates != sorted(dates, key=year_fraction):
        note("the dates are in order", "they are not")
    price_dates = data.get("priceDates", [])
    if price_dates != sorted(price_dates, key=year_fraction):
        note("the price dates are in order", "they are not")
    if len(data.get("years", [])) != len(dates):
        note("there is one year per date",
             "%d years, %d dates" % (len(data.get("years", [])), len(dates)))

    for tag in sorted(tags):
        if tag not in data.get("series", {}):
            note("every nation has a series", tag)
        if tag not in data.get("tagNames", {}):
            note("every nation has a name", tag)

    # The columns are read by index against these two lists, so a column of
    # the wrong length is silently the wrong data from the wrong date on.
    for tag, measures in data.get("series", {}).items():
        for key, column in measures.items():
            if len(column) != len(dates):
                note("a measure has one value per save",
                     "%s %s has %d for %d saves"
                     % (tag, key, len(column), len(dates)))
    for good, column in data.get("prices", {}).items():
        if len(column) != len(price_dates):
            note("a price has one value per priced month",
                 "%s has %d for %d months"
                 % (good, len(column), len(price_dates)))

    for date, by_tag in data.get("facts", {}).items():
        if date not in dates:
            note("a fact is about a save that happened", date)
        for tag in by_tag:
            if tag not in tags:
                note("a fact is about a nation the report lists", tag)

    depth = len(data.get("techOrder", []))
    for tag, by_date in data.get("techsBy", {}).items():
        for date, held in by_date.items():
            for i in held:
                if not 0 <= i < depth:
                    note("a technology index points at a technology",
                         "%s %s: %d of %d" % (tag, date, i, depth))

    kinds = set(data.get("popTypes", []))
    for tag, by_date in data.get("pops", {}).items():
        for date, counted in by_date.items():
            for kind in counted:
                if kind not in kinds:
                    note("a pop is of a type the report lists",
                         "%s %s %s" % (tag, date, kind))

    for tag, by_date in data.get("cultures", {}).items():
        for date, rows in by_date.items():
            for culture, size, accepted in rows:
                if size <= 0:
                    note("a culture in the list has people in it",
                         "%s %s %s" % (tag, date, culture))
                if accepted not in (0, 1):
                    note("accepted is a yes or a no", repr(accepted))

    for war in data.get("wars", []):
        name = war.get("name", "?")
        start, end = war.get("start"), war.get("end")
        if start and end and year_fraction(end) < year_fraction(start):
            note("a war ends after it starts",
                 "%s: %s to %s" % (name, start, end))
        if end and war.get("active"):
            note("a war that ended is not still being fought", name)
        if not war.get("attackers"):
            note("a war has somebody attacking", name)
        if not war.get("defenders"):
            note("a war has somebody defending", name)
        battles = war.get("battles") or []
        losses = [sum(b["a"][2] for b in battles),
                  sum(b["d"][2] for b in battles)]
        if list(war.get("losses") or [0, 0]) != losses:
            note("a war's losses are its battles' losses",
                 "%s: %s against %s" % (name, war.get("losses"), losses))
        if war.get("dated") != sum(1 for b in battles if b.get("date")):
            note("the dated-battle count is the number with a date", name)
        # Nothing saw who held the state going in, so nothing can say
        # whether the peace moved it.
        if (dates and end and not war.get("active")
                and year_fraction(end) <= year_fraction(dates[0])):
            for g in war.get("goals") or []:
                if g.get("checkable"):
                    note("a war over before the first save has no goal "
                         "judged", "%s, ended %s" % (name, end))
        for b in battles:
            when = b.get("date")
            if not when:
                continue
            if start and year_fraction(when) < year_fraction(start):
                note("a battle happens after its war starts",
                     "%s: %s before %s" % (name, when, start))
            if end and year_fraction(when) > year_fraction(end):
                note("a battle happens before its war ends",
                     "%s: %s after %s" % (name, when, end))
    return bad


def check_rows(path):
    """[(rule, tag, date, left, right)] for everything that does not hold."""
    broken = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            where = (row.get("tag", "?"), row.get("date", "?"))
            for name, both in RULES:
                left, right = both(row)
                if not near(left, right):
                    broken.append((name, where[0], where[1], left, right))
            for name, small, big in ORDERED:
                a, b = number(row, small), number(row, big)
                if a > b and not near(a, b):
                    broken.append((name, where[0], where[1], a, b))
            for field in FLAGS:
                got = number(row, field)
                if got not in (0.0, 1.0):
                    broken.append(("%s is a yes or a no" % field,
                                   where[0], where[1], got, "0 or 1"))
            for field, low, high in RANGES:
                got = number(row, field)
                if got < low or got > high:
                    broken.append(("%s is between %s and %s"
                                   % (field, low, high),
                                   where[0], where[1], got, "in range"))
            for field in NEVER_NEGATIVE:
                got = number(row, field)
                if got < 0:
                    broken.append(("%s is never negative" % field,
                                   where[0], where[1], got, ">= 0"))
    return broken


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    path = sys.argv[1]
    if not os.path.isfile(path):
        print("no such table: %s" % path)
        return 2

    with open(path, newline="", encoding="utf-8") as fh:
        count = sum(1 for _ in csv.DictReader(fh))
    broken = check_rows(path)

    print("%d nation-saves, %d rules each"
          % (count, len(RULES) + len(ORDERED) + len(FLAGS) + len(RANGES)
             + len(NEVER_NEGATIVE)))

    shape = []
    payload = True
    if len(sys.argv) > 2:
        data = payload_of(sys.argv[2])
        if data is None:
            print("  %s carries no payload to check"
                  % os.path.basename(sys.argv[2]))
            payload = False
        else:
            shape = check_payload(data)
            print("  and the report's own shape: %d nations, %d saves, "
                  "%d wars" % (len(data.get("tags", [])),
                               len(data.get("dates", [])),
                               len(data.get("wars", []))))

    if not broken and not shape:
        print("\nevery number agrees with every other number")
        return 0 if payload else SKIPPED

    if shape:
        print("\nBROKEN, in the report's shape:")
        by_rule = {}
        for rule, what in shape:
            by_rule.setdefault(rule, []).append(what)
        for rule in sorted(by_rule, key=lambda r: -len(by_rule[r])):
            print("  %s" % rule)
            print("      %d times; e.g. %s"
                  % (len(by_rule[rule]), by_rule[rule][0]))
        if not broken:
            return 1

    # One line per rule, with an example, rather than thousands of lines.
    by_rule = {}
    for name, tag, date, left, right in broken:
        by_rule.setdefault(name, []).append((tag, date, left, right))
    print("\nBROKEN:")
    for name in sorted(by_rule, key=lambda n: -len(by_rule[n])):
        hits = by_rule[name]
        tag, date, left, right = hits[0]
        print("  %s" % name)
        print("      %d of %d rows; e.g. %s at %s: %s against %s"
              % (len(hits), count, tag, date, left, right))
    return 1


if __name__ == "__main__":
    sys.exit(main())

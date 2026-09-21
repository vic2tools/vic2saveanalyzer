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

import csv
import os
import sys

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
    if not broken:
        print("\nevery number agrees with every other number")
        return 0

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

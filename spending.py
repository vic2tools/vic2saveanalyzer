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
What one save puts into the tables, worked out where the save was read.

A finished save gives up one row per nation for the main table, a handful of
tuples per nation for the five narrower ones, its ships' profiles and its
supply, and is then cut down to the few fields the rest of the run still
reads. None of that depends on any other save. It used to be done in the
parent, one save after another, with fifteen workers idle behind it -- the
worker unpickled into the parent a finished save it had just pickled, and
the parent turned it into rows, and later the table writer turned the rows
into CSV text on a thread beside the report. Now the worker does both and
sends the rows, the CSV text and the remains; the parent keeps only what
spans saves -- the lists the report is built from, the war book, which
ship profiles it has seen -- in `vic2_analyzer.walk_campaign`.

The same `save_rows` runs in the parent for the two diagnostics that keep
saves whole, so a table cannot come out differently for having been made
in one place rather than the other.
"""

import csv
import io
import json
from collections import namedtuple

import finishing
from nation import trim_save
from tech_groups import TECH_GROUP

BASE_COLUMNS = [
    "date", "year", "tag", "is_player", "primary_culture", "civilized",
    "provinces", "states", "total_pop", "accepted_pop", "accepted_pct",
    "primary_culture_pop", "avg_literacy", "avg_literacy_stated",
    "pop_noncolonial", "avg_consciousness", "avg_militancy",
    "brigades", "regular_brigades", "mobilized_brigades", "mobilizing",
    "brigade_cap",
    "is_mobilized", "armies", "ships", "navies",
    "factory_count", "factory_levels", "ports", "naval_base_levels",
    "max_naval_base", "railroad_levels", "fort_levels",
    "mobilisation_size", "mobilization_pool", "mobilization_pops",
    "mobilization_brigades", "mobilization_cap",
    "mobilization_available", "mobilization_remaining", "war_policy",
    "techs", "army_techs", "navy_techs", "prestige", "infamy", "treasury", "tax_base", "research_points",
    "war_exhaustion", "plurality",
    "pop_poor", "pop_middle", "pop_rich",
    "soldiers_noncolonial", "soldiers_noncolonial_pct",
    "life_unmet", "life_unmet_pct", "starving", "starving_pct",
]

# The tables a save writes its own rows into, in the order `SaveRows.text`
# holds them. `vic2_analyzer.write_outputs` names their columns.
PER_SAVE = ("nations_timeseries.csv", "ships_by_type.csv",
            "brigades_by_type.csv", "technologies.csv", "pops_by_type.csv",
            "pops_by_culture.csv")


def nation_columns(pop_columns):
    """The main table's columns, given the pop types this run reads."""
    return (BASE_COLUMNS + [f"pop_{t}" for t in pop_columns]
            + ["accepted_cultures"])


# One save's share of the tables. `naval` is (tag, key, profile) per nation
# with ships, `supply` is (good, tag, amount), both in nation order, and
# `text` is each of the `PER_SAVE` tables' rows as CSV, heading left out.
SaveRows = namedtuple("SaveRows", "rows ship_rows brigade_rows tech_rows "
                                  "pop_rows culture_rows naval supply text")

# What a worker sends back: the save cut down to what the run keeps, the
# wars the parent folds into its book, and the save's rows.
Spent = namedtuple("Spent", "meta nations wars rows")


def save_rows(meta, nations, spec, pop_columns):
    """One finished save's `SaveRows`."""
    date = meta["date"]
    year = date.split(".")[0] if date else ""
    rows, ship_rows, brigade_rows, tech_rows = [], [], [], []
    pop_rows, culture_rows, naval, supply = [], [], [], []
    for tag, done in nations.items():
        # The same question the finishing asked, asked of the same spec,
        # so a nation finished out in a worker and a nation finished in the
        # parent are kept or dropped by one rule.
        if not finishing.kept_by(spec, tag, done):
            continue
        accepted_set = set(done["accepted_cultures"]) | {done["primary_culture"]}

        row = {
            "date": date,
            "year": year,
            "tag": tag,
            "is_player": int(done["is_player"]),
            "accepted_cultures": ";".join(sorted(done["accepted_cultures"])),
        }
        for col in BASE_COLUMNS:
            if col in done:
                row[col] = done[col]
        for ptype in pop_columns:
            row[f"pop_{ptype}"] = done["pop_by_type"].get(ptype, 0)
        rows.append(row)

        # These tables are the ones a campaign has millions of rows of -- a
        # hundred technologies per nation per save on its own -- so they are
        # tuples in the column order declared in `write_outputs` rather than
        # dicts. A dict per row costs about twice the memory and names the
        # same six columns over and over.
        for stype, count in sorted(done["ships_by_type"].items()):
            ship_rows.append((date, year, tag, stype, count,
                              round(done["ship_crew"].get(stype, count), 3)))
        # Ship stats as each nation's own inventions leave them. Nations that
        # researched the same things have the same ships, so the parent keeps
        # each profile once and refers to it by number; the key it knows one
        # by is worked out here.
        if spec.mod is not None and done["ships"]:
            from mod_reader import naval_profile
            profile = naval_profile(done, spec.mod)
            naval.append((tag, json.dumps(profile, sort_keys=True), profile))
        for good, amount in done["goods_supply"].items():
            supply.append((good, tag, amount))
        for rtype, count in sorted(done["regiments_by_type"].items()):
            brigade_rows.append((date, year, tag, rtype, count))
        for tech in sorted(done["tech_list"]):
            branch, line, _pos = TECH_GROUP.get(tech, ("other", "Other", 0))
            tech_rows.append((date, year, tag, tech, branch, line))
        for ptype, size in sorted(done["pop_by_type"].items()):
            pop_rows.append((date, year, tag, ptype, size))
        for culture, size in sorted(done["pop_by_culture"].items(),
                                    key=lambda kv: -kv[1]):
            culture_rows.append((date, year, tag, culture, size,
                                 int(culture in accepted_set)))

    # The same writer the tables are opened with, so the text is what
    # writing these rows there would have written.
    columns = nation_columns(pop_columns)
    text = []
    for data in (rows, ship_rows, brigade_rows, tech_rows, pop_rows,
                 culture_rows):
        out = io.StringIO()
        writer = csv.writer(out)
        if data is rows:
            writer.writerows([row.get(c, "") for c in columns] for row in data)
        else:
            writer.writerows(data)
        text.append(out.getvalue())
    return SaveRows(rows, ship_rows, brigade_rows, tech_rows, pop_rows,
                    culture_rows, naval, supply, tuple(text))


def spend(meta, nations, spec, keep_fields, pop_columns):
    """
    A save finished, turned into its rows and cut down, in the worker that
    read it. What `readfolder` is handed as the `transform`, wrapped in a
    `partial`, so it has to stay a plain function at the top of a module:
    Windows sends it to each worker by name.
    """
    meta, finished = finishing.finish_and_pack(meta, nations, spec)
    rows = save_rows(meta, finished, spec, pop_columns)
    wars = meta.get("wars", ())
    meta, finished = trim_save(meta, finished, keep_fields)
    return Spent(meta, finished, wars, rows)

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
The world market across a campaign: the price of every good in every month,
and what each save says about supply and demand on the day it was written.

Reading a save's market block is `readsave.read_worldmarket`'s job. This is
what the campaign makes of them, and the two tables they are written to.
"""

from dates import date_key

# The two tables' columns. `merge_prices` makes tuples in the first order.
PRICE_COLUMNS = ("date", "year", "good", "category", "price")
SNAPSHOT_COLUMNS = ("date", "year", "good", "category", "price", "world_pool",
                    "supply", "demand", "real_demand", "actual_sold",
                    "discovered")

GOOD_CATEGORIES = {
    "military": ["ammunition", "small_arms", "artillery", "canned_food",
                 "barrels", "tanks", "aeroplanes"],
    "raw": ["cattle", "coal", "cotton", "dye", "fish", "fruit", "grain", "iron",
            "oil", "opium", "precious_metal", "rubber", "silk", "sulphur", "tea",
            "timber", "tobacco", "tropical_wood", "wool", "coffee"],
    "industrial": ["cement", "clipper_convoy", "electric_gear", "explosives",
                   "fabric", "fertilizer", "fuel", "glass", "lumber",
                   "machine_parts", "paper", "steamer_convoy", "steel"],
    "consumer": ["automobiles", "furniture", "liquor", "luxury_clothes",
                 "luxury_furniture", "radio", "regular_clothes", "telephones",
                 "wine"],
}
GOOD_CATEGORY = {g: cat for cat, goods in GOOD_CATEGORIES.items() for g in goods}


def merge_prices(parsed):
    """
    Stitch every save's rolling price buffer into one series.

    Buffers from consecutive saves overlap heavily; keyed on (date, good) the
    duplicates collapse, and the result is continuous monthly coverage from the
    earliest buffer to the last save.
    """
    prices = {}
    # Newest save first, and the first answer for a month is the one that
    # stands. Walked oldest first, every one of the hundred and twenty
    # thousand entries a campaign has had to be weighed against which save
    # had written it -- a second dictionary the same size as the first, and
    # a lookup in it per entry -- to settle that a later save's buffer is
    # the more settled record. Coming the other way the question does not
    # arise: whatever is already there was written by a later save.
    for meta, _ in reversed(parsed):
        market = meta.get("market")
        if not market:
            continue
        # The save's own date carries the live price, which its monthly
        # buffer has not recorded yet -- so it goes in before this save's
        # own history, and after every later save's, which is exactly the
        # order it won in before.
        stamp = meta["date"]
        for good, price in market["current"].items():
            key = (stamp, good)
            if key not in prices:
                prices[key] = price
        for stamp, good, price in market["history"]:
            key = (stamp, good)
            if key not in prices:
                prices[key] = price

    # Tuples in `PRICE_COLUMNS` order, like the other
    # big tables: a campaign has ninety thousand of these, and a dict each
    # was half the time this took and made the CSV writer name the same
    # five columns ninety thousand times.
    rows = []
    years = {}
    for (stamp, good), price in prices.items():
        year = years.get(stamp)
        if year is None:
            year = years[stamp] = stamp.split(".")[0]
        rows.append((stamp, year, good, GOOD_CATEGORY.get(good, "other"),
                     round(price, 5)))
    rows.sort(key=lambda r: (date_key(r[0]), r[2]))
    return rows


def market_snapshot_rows(parsed):
    """Per-save supply/demand context, which the save only stores for `now`."""
    rows = []
    for meta, _ in parsed:
        market = meta.get("market")
        if not market:
            continue
        snap = market["snapshot"]
        goods = set(market["current"])
        for field in snap.values():
            goods |= set(field)
        for good in sorted(goods):
            rows.append({
                "date": meta["date"],
                "year": meta["date"].split(".")[0],
                "good": good,
                "category": GOOD_CATEGORY.get(good, "other"),
                "price": round(market["current"].get(good, 0.0), 5),
                "world_pool": round(snap["world_pool"].get(good, 0.0), 3),
                "supply": round(snap["supply"].get(good, 0.0), 3),
                "demand": round(snap["demand"].get(good, 0.0), 3),
                "real_demand": round(snap["real_demand"].get(good, 0.0), 3),
                "actual_sold": round(snap["actual_sold"].get(good, 0.0), 3),
                "discovered": int(snap["discovered"].get(good, 0.0) > 0),
            })
    return rows

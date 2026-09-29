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
    # {stamp: {good: price}}. Keyed by the date and then the good rather than
    # by the pair, which was a tuple built and hashed for each of the half a
    # million entries 265 saves carry -- their buffers overlap, so most of
    # them are only looked up and passed over.
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
        day = prices.get(stamp)
        if day is None:
            day = prices[stamp] = {}
        for good, price in market["current"].items():
            if good not in day:
                day[good] = price
        last = None
        for stamp, good, price in market["history"]:
            if stamp != last:
                last = stamp
                day = prices.get(stamp)
                if day is None:
                    day = prices[stamp] = {}
            if good not in day:
                day[good] = price

    # Tuples in `PRICE_COLUMNS` order, like the other
    # big tables: a campaign has ninety thousand of these, and a dict each
    # was half the time this took and made the CSV writer name the same
    # five columns ninety thousand times.
    #
    # Oldest date first and then by good, as sorting every row by the pair
    # would put them, but sorted a date at a time: four thousand dates and a
    # few dozen goods each, rather than two hundred thousand rows through a
    # key function. Two spellings of one date (1869.09.29 and 1869.9.29) are
    # the one case where the two orders could part, and they take the old
    # way, whose ties fall in the order the entries were met.
    stamps = sorted(prices, key=date_key)
    keys = [date_key(s) for s in stamps]
    if any(a == b for a, b in zip(keys, keys[1:])):
        return _price_rows_by_pair(parsed)
    rows = []
    category = GOOD_CATEGORY.get
    for stamp in stamps:
        day = prices[stamp]
        year = stamp.split(".")[0]
        rows.extend([(stamp, year, good, category(good, "other"),
                      round(day[good], 5)) for good in sorted(day)])
    return rows


def _price_rows_by_pair(parsed):
    """`merge_prices` as it was, keyed by (date, good) and sorted by row."""
    prices = {}
    for meta, _ in reversed(parsed):
        market = meta.get("market")
        if not market:
            continue
        stamp = meta["date"]
        for good, price in market["current"].items():
            prices.setdefault((stamp, good), price)
        for stamp, good, price in market["history"]:
            prices.setdefault((stamp, good), price)
    rows = [(stamp, stamp.split(".")[0], good, GOOD_CATEGORY.get(good, "other"),
             round(price, 5)) for (stamp, good), price in prices.items()]
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

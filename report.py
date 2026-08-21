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

SERIES_COLOURS = [
    "#F2B441", "#E0644F", "#5FCBB4", "#A8B9F0",
    "#F08FB0", "#9BD65E", "#D9A0E0", "#EDE3C8",
    "#7FD9E8", "#F58B4C", "#B7C97A", "#C9A2F2",
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


def build_report(rows, ship_rows, pop_rows, culture_rows, price_rows,
                 snapshot_rows, brigade_rows, tech_rows, outdir,
                 tag_names=None, player_tags=None, map_data=None,
                 filename="report.html"):
    os.makedirs(outdir, exist_ok=True)
    tag_names = tag_names or {}
    player_tags = player_tags or []

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

    present_players = [t for t in player_tags if t in tags]

    payload = {
        "dates": dates,
        "years": [year_fraction(d) for d in dates],
        "tags": tags,
        "tagNames": {t: tag_names.get(t, t) for t in tags},
        "playerTags": present_players,
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

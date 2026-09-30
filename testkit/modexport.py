"""
The mod as the report engine used to be handed it: every field it reads,
in JSON's terms, made from the `Mod` Python reads.

The engine reads the mod folder itself now (`scanner/src/engine/modread.rs`)
and is held to this, text for text (`modread.py`): what the Rust makes of a
folder must be what `export_mod(load_mod(folder))` is. It is also how a
check hands the engine a mod Python read (`mod_file` in the spec).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def export_mod(mod):
    """
    The mod as the engine reads it: every field it uses, in JSON's terms.

    Dicts keyed by province id become lists of pairs, sets sorted lists,
    and the map's and the flags' inputs, which the report reads off the
    mod's files rather than off the `Mod`, are worked out here, once.
    """
    import mod_reader as mr
    path = mod.path

    def ordered(pairs):
        return [[k, v] for k, v in pairs]

    bmp = mr._map_file(path, "provinces.bmp")
    csv_path = mr._map_file(path, "definition.csv")
    has_map = os.path.isfile(bmp) and os.path.isfile(csv_path)
    rules = mod.invention_rules or {}
    return {
        "path": path,
        "invention_sequence": [[e["name"], e["size"], sorted(e["techs"]), sorted(e["tags"])]
                               for e in (mod.invention_sequence or ())],
        "party_policies": [p[3] for p in (mod.party_sequence or ())],
        "localisation": mod.localisation or {},
        "base_prices": mod.base_prices or {},
        "country_order": list(mod.country_order or ()),
        "formations": {tag: sorted(v) for tag, v in (mod.formations or {}).items()},
        "culture_names": mod.culture_names or {},
        "display_names": mod.display_names or {},
        "province_names": ordered((mod.province_names or {}).items()),
        "province_regions": ordered((mod.province_regions or {}).items()),
        "state_names": mod.state_names or {},
        "unit_kinds": mod.unit_kinds or {},
        "naval_units": mod.naval_units or {},
        "naval_effects": {name: {"effects": e["effects"], "techs": sorted(e["techs"]),
                                 "tags": sorted(e["tags"])}
                          for name, e in (mod.naval_effects or {}).items()},
        "naval_tech_effects": mod.naval_tech_effects or {},
        "technology": mod.technology or {},
        "mob_impacts": mod.mob_impacts or {},
        "modifier_impacts": mod.modifier_impacts or {},
        "reform_mob": [[r, o, v] for (r, o), v in (mod.reform_mob or {}).items()],
        "reform_names": sorted(mod.reform_names or ()),
        "static_mob": mod.static_mob or {},
        "triggered_mob": [[n, s, i, t] for n, s, i, t in (mod.triggered_mob or ())],
        "culture_groups": mod.culture_groups or {},
        "continents": ordered((mod.continents or {}).items()),
        "technologies": sorted(mod.technologies or ()),
        "defines": mod.defines or {},
        "strata": mod.strata or {},
        "invention_rules": {name: {"size": r["size"], "techs": sorted(r["techs"]),
                                   "tags": sorted(r["tags"]),
                                   "requires": sorted(r["requires"]),
                                   "base": r["base"],
                                   "blockers": [[f, b] for f, b in r["blockers"]]}
                            for name, r in rules.items()},
        "event_mob": mod.event_mob or {},
        "tech_mob": mod.tech_mob or {},
        "nv_mob": mod.nv_mob or {},
        "tech_count": mod.tech_count or 0,
        "colours": mr.country_colours(path) if has_map else {},
        "sea": sorted(mr.sea_provinces(path)) if has_map else [],
        "positions": [[p, x, y] for p, (x, y) in mr.unit_positions(path).items()]
                     if has_map else [],
        "flag_styles": {g: [v, e] for g, (v, e) in mr.government_flag_types(path).items()},
        "flag_roots": mr._flag_roots(path),
        "map_bmp": bmp if has_map else "",
        "map_csv": csv_path if has_map else "",
    }

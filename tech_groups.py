"""
Military technology groupings.

Victoria II saves list technologies as bare names with a researched flag and no
folder information, so the mapping from tech to army/navy line lives here. These
are the vanilla names, which most mods reuse; anything unrecognised is reported
under "Other" rather than dropped, so a mod's own techs still show up.

Order within each line is research order, so a nation's progress reads left to
right.
"""

ARMY_LINES = [
    ("Doctrine", [
        "post_napoleonic_thought", "strategic_mobility", "point_defense_system",
        "deep_defense_system", "infiltration",
    ]),
    ("Small arms", [
        "flintlock_rifles", "muzzle_loaded_rifles", "breech_loaded_rifles",
        "machine_guns", "bolt_action_rifles",
    ]),
    ("Artillery", [
        "bronze_muzzle_loaded_artillery", "iron_muzzle_loaded_artillery",
        "iron_breech_loaded_artillery", "steel_breech_loaded_artillery",
        "indirect_artillery_fire",
    ]),
    ("Military science", [
        "military_staff_system", "military_plans", "military_statistics",
        "military_logistics", "military_directionism",
    ]),
    ("Leadership", [
        "army_command_principle", "army_professionalism", "army_decision_making",
        "army_risk_management", "army_nco_training",
    ]),
]

NAVY_LINES = [
    ("Naval doctrine", [
        "post_nelsonian_thought", "battleship_column_doctrine",
        "raider_group_doctrine", "blue_and_brown_water_schools",
        "high_sea_battle_fleet",
    ]),
    ("Hulls", [
        "clipper_design", "steamers", "iron_steamers", "steel_steamers",
        "steam_turbine_ships",
    ]),
    ("Naval engineering", [
        "naval_design_bureaus", "fire_control_systems", "weapon_platforms",
        "main_armament", "advanced_naval_design",
    ]),
    ("Naval science", [
        "alphabetic_flag_signaling", "naval_plans", "naval_statistics",
        "naval_logistics", "naval_directionism",
    ]),
    ("Naval leadership", [
        "the_command_principle", "naval_professionalism",
        "naval_decision_making", "naval_risk_management", "naval_nco_training",
    ]),
]

ARMY_TECHS = {t for _line, techs in ARMY_LINES for t in techs}
NAVY_TECHS = {t for _line, techs in NAVY_LINES for t in techs}

# tech -> (branch, line, position in line)
TECH_GROUP = {}
for _branch, _lines in (("army", ARMY_LINES), ("navy", NAVY_LINES)):
    for _line, _techs in _lines:
        for _idx, _tech in enumerate(_techs):
            TECH_GROUP[_tech] = (_branch, _line, _idx)


def branch_of(tech):
    """'army', 'navy', or 'other' for anything not in the vanilla lists."""
    entry = TECH_GROUP.get(tech)
    return entry[0] if entry else "other"

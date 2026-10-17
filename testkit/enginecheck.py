#!/usr/bin/env python3
"""
The report engine against its recorded answers, on a world built to sit on
every boundary a count has.

The world is made here (`an_edge_world`): a mod and a few saves whose pops,
pools, soldiers, land, wars, armies, fleets, markets and technologies are
chosen so that each rule the engine applies shows in its answer. Each run --
the nine outputs and the printed words -- is held to `testkit/expected/
enginecheck/` (`expected.py`).

    python3 testkit/enginecheck.py [--update]

A real campaign is held to its own verified answers by `baseline.py`.
"""

import argparse
import os
import shutil
import sys
import tempfile

import kit                                                  # noqa: E402
import expected                                            # noqa: E402
from baseline import run                                   # noqa: E402

SYNTHETIC_RUNS = [
    ("on the edges", []),
    ("on the edges, occupied counted", ["--mob-include-occupied"]),
    ("on the edges, farmers only", ["--mob-types", "farmers"]),
    ("on the edges, verbose", ["VERBOSE"]),
]


def an_edge_world(holding):
    """
    (a mod, a folder of saves) built to sit on every boundary a count has:
    a pop worth exactly one regiment, a pool that fills to exactly one,
    soldiers either side of the smallest pop a brigade may be raised from,
    and land that is colonial, occupied and not cored. The mod grants half
    its people to mobilisation and charges a thousand a regiment, and has
    no map, no defines past that and no flags, which are paths of their own.
    """
    import fixtures
    import savefmt
    pops = fixtures.POPS + ["serfs"]
    mod = fixtures.a_mod_in_a_game(holding, "edges", pops=pops, pop_per_regiment=1000,
                                   mob_size=0.5)
    folder = os.path.join(holding, "edge-saves")
    os.makedirs(folder)
    for n, (date, grow) in enumerate((("1870.1.1", 0), ("1871.1.1", 2), ("1872.1.1", 1))):
        def people(pid, kinds):
            return [savefmt.pop(kind, pid * 100 + i, size + grow * (i % 2), culture=culture)
                    for i, (kind, size, culture) in enumerate(kinds)]
        savefmt.write(
            os.path.join(folder, "edge%d.v2" % n),
            savefmt.head(date, player="ENG"),
            savefmt.province(1, "ENG", people(1, [
                ("farmers", 2000, "british"), ("farmers", 1999, "british"),
                ("labourers", 1, "british"), ("craftsmen", 4000, "british"),
                ("soldiers", 999, "british"), ("soldiers", 1000, "british"),
                ("soldiers", 3000, "british"), ("soldiers", 2999, "british"),
                ("serfs", 2002, "british"), ("farmers", 700, "irish")])),
            savefmt.province(2, "ENG", people(2, [
                ("farmers", 6000, "british"), ("soldiers", 4000, "british")]),
                extra=["colonial=2"]),
            savefmt.province(3, "ENG", people(3, [
                ("labourers", 8000, "british"), ("soldiers", 1500, "british")]),
                extra=['controller="FRA"']),
            savefmt.province(4, "FRA", people(4, [
                ("farmers", 3000, "french"), ("soldiers", 1000, "french")])),
            savefmt.country("ENG", techs=fixtures.TECHS, inventions=[1],
                            extra=["ruling_party=1", "human=yes"]),
            savefmt.country("FRA", culture="french", capital=4,
                            techs=fixtures.TECHS[:1], inventions=[1]),
            savefmt.war("The Edge War", "ENG", "FRA", active=n < 2,
                        action="1870.5.%d" % (n + 1)))
    return mod, folder


FURNISHED_RUNS = [
    ("furnished", []),
    ("furnished, verbose", ["VERBOSE"]),
    ("furnished, campaigns compared", ["CROSS"]),
]


def a_furnished_world(holding):
    """
    (a mod, a folder of saves): `savefmt.furnished` -- armies and a navy,
    a national value, a national modifier, a reform, accepted cultures,
    states -- at two dates, read under a mod given the rules the baseline
    adds to a real one (triggered, issue and static modifiers that grant
    mobilisation).
    """
    import baseline
    import fixtures
    import savefmt
    mod = fixtures.a_mod_in_a_game(os.path.join(holding, "made"), "Rich", tags=["SWE", "DEN"],
                                   pops=fixtures.POPS, pop_per_regiment=1000, mob_size=0.5)
    raw = os.path.join(holding, "raw")
    os.makedirs(raw)
    later = os.path.join(raw, "b.v2")
    savefmt.furnished(later)
    with open(later, "rb") as fh:
        text = fh.read()
    with open(os.path.join(raw, "a.v2"), "wb") as fh:
        fh.write(text.replace(b'date="1881.3.24"', b'date="1880.3.24"', 1))
    _world, world_mod, saves = baseline.a_world(os.path.join(holding, "world"), mod, raw,
                                                "national_confusion")
    return world_mod, saves


MAPPED_RUNS = [
    ("mapped", []),
    ("mapped, campaigns compared", ["CROSS"]),
]

# The rules the mapped world's mod grants mobilisation by, each its own
# size, so a rule read wrong shows as a size of its own: a national value, an
# event modifier (which also raises the cap), a reform, and a trigger asking
# for an invention.
MAPPED_RULES = {
    "nationalvalues.txt": "nv_order = {\n\tmobilisation_size = 0.02\n}\n",
    "event_modifiers.txt": "national_confusion = {\n\tmobilisation_size = 0.01\n"
                           "\tmobilization_impact = 0.5\n}\n",
    "issues.txt": "party_issues = {\n\twar_policy = {\n"
                  "\t\tjingoism = {\n\t\t\tmobilization_impact = 0.25\n\t\t}\n\t}\n}\n"
                  "political_reforms = {\n\tvote_franschise = {\n"
                  "\t\tnone_voting = {\n\t\t\tmobilisation_size = 0.001\n\t\t}\n"
                  "\t\tuniversal_voting = {\n\t\t\tmobilisation_size = 0.03\n\t\t}\n\t}\n}\n",
    "triggered_modifiers.txt": "mapped_invention = {\n\tmobilisation_size = 0.04\n"
                               "\ttrigger = { invention = an_invention_0 }\n}\n",
    "countries/ENG.txt": "party = {\n\tname = \"ENG_jingo\"\n\tstart_date = 1800.1.1\n"
                         "\tend_date = 2000.1.1\n\tideology = liberal\n"
                         "\twar_policy = jingoism\n}\n",
}


def a_mapped_world(holding):
    """
    (a mod, a folder of saves) with a map, so the page draws armies and
    carries a state chunk for each save: `raster`'s five provinces in three
    states. ENG has armies met in province 2 before province 1, two kinds
    with as many regiments in province 2, ships met out of name order, two
    cultures of equal size met out of name order, and states of several pop
    types; it holds a national value, a reform, an event modifier and an
    invention the mod's rules grant mobilisation for, and a party whose war
    policy gives it a cap. FRA holds the other invention. The world market's
    goods are met out of name order, and the war has two battles of one
    name on one date, each with two unit kinds of as many men on a side. The
    mod names ENG and FRA's republic in its localisation, for `--cross`.
    """
    from pathlib import Path
    import fixtures
    import raster
    import savefmt
    mod = fixtures.a_mod_in_a_game(holding, "Mapped", tags=["ENG", "FRA"], pops=fixtures.POPS,
                                   pop_per_regiment=1000)
    raster.write_map(Path(mod), raster.picture(23, 19))
    with open(os.path.join(mod, "map", "region.txt"), "w") as fh:
        fh.write("ENG_1 = { 1 2 }\nENG_2 = { 3 }\nFRA_1 = { 4 5 }\n")
    for name, text in MAPPED_RULES.items():
        path = os.path.join(mod, "common", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)
    os.makedirs(os.path.join(mod, "localisation"))
    with open(os.path.join(mod, "localisation", "mapped.csv"), "w") as fh:
        fh.write("ENG;Mapland;;;;;;;;;;;;x\nFRA_democracy;The Mapped Republic;;;;;;;;;;;;x\n")

    def regiments(*kinds):
        return sum((savefmt.nest("regiment", ['\t\t\tname="%d %s"' % (i, kind),
                                              "\t\t\ttype=%s" % kind, "\t\t\tcount=1000",
                                              "\t\t\tstrength=3.000"], 2)
                    for i, kind in enumerate(kinds)), [])

    def army(name, where, *kinds):
        return ("army", ['\t\tname="%s"' % name] + regiments(*kinds) + ["\t\tlocation=%d" % where])

    def ship(name, kind):
        return savefmt.nest("ship", ['\t\t\tname="%s"' % name, "\t\t\ttype=%s" % kind,
                                     "\t\t\tstrength=100.000"], 2)

    def state(ids):
        return ("state", savefmt.nest("provinces", ["\t\t\t" + ids], 2))

    def side(country, losses):
        return savefmt.nest("attacker" if country == "ENG" else "defender",
                            ['\t\t\t\t\tcountry="%s"' % country, '\t\t\t\t\tleader=""',
                             "\t\t\t\t\tinfantry=3000", "\t\t\t\t\tcavalry=3000",
                             "\t\t\t\t\tlosses=%d" % losses], 4)

    def battle(where):
        return savefmt.nest("battle", ['\t\t\t\tname="Battle of the Map"',
                                       "\t\t\t\tlocation=%d" % where, "\t\t\t\tresult=yes"]
                            + side("ENG", 500) + side("FRA", 800), 3)

    goods = ["wool", "cement", "ammunition"]

    def pool(name, scale):
        return savefmt.nest(name, ["\t\t%s=%.5f" % (g, scale * (i + 1))
                                   for i, g in enumerate(goods)], 1)

    market = (["worldmarket=", "{"] + pool("worldmarket_pool", 10) + pool("price_pool", 1.5)
              + pool("supply_pool", 7) + pool("demand", 6) + pool("real_demand", 5)
              + pool("actual_sold", 4) + pool("actual_sold_world", 3)
              + pool("discovered_goods", 1)
              + savefmt.nest("price_history",
                             sum((["\t\t{"] + ["\t\t\t%s=%.5f" % (g, month + i)
                                               for i, g in enumerate(goods)] + ["\t\t}"]
                                  for month in (1.0, 2.0)), []), 1)
              + ['\tprice_history_last_update="1879.12.1"', "}"])

    folder = os.path.join(holding, "saves")
    os.makedirs(folder)
    for n, date in enumerate(("1880.1.1", "1881.1.1")):
        def people(pid, kinds):
            return [savefmt.pop(kind, pid * 100 + i, size + 10 * n, culture=culture)
                    for i, (kind, size, culture) in enumerate(kinds)]
        war = (["active_war=", "{", '\tname="The Mapped War"']
               + savefmt.nest("history", savefmt.nest("1880.6.1", battle(1) + battle(2), 2), 1)
               + ['\toriginal_attacker="ENG"', '\toriginal_defender="FRA"',
                  '\tattacker="ENG"', '\tdefender="FRA"', '\taction="1880.5.1"', "}"])
        savefmt.write(
            os.path.join(folder, "mapped%d.v2" % n),
            savefmt.head(date, player="ENG"),
            savefmt.province(1, "ENG", people(1, [
                ("farmers", 3000, "british"), ("craftsmen", 2000, "british"),
                ("soldiers", 2000, "british"), ("farmers", 1500, "welsh")])),
            savefmt.province(2, "ENG", people(2, [
                ("farmers", 4000, "british"), ("labourers", 1500, "irish"),
                ("soldiers", 1000, "british")])),
            savefmt.province(3, "ENG", people(3, [("labourers", 2500, "british")])),
            savefmt.province(4, "FRA", people(4, [
                ("farmers", 3000, "french"), ("soldiers", 1000, "french")])),
            savefmt.province(5, "FRA", people(5, [("craftsmen", 2000, "french")])),
            savefmt.country("ENG", techs=fixtures.TECHS, inventions=[1],
                            extra=["ruling_party=1", "human=yes", "nationalvalue=nv_order",
                                   "vote_franschise=universal_voting"],
                            blocks=[("culture", ['\t\t"welsh" "irish"']),
                                    ("modifier", ['\t\tmodifier="national_confusion"',
                                                  '\t\tdate="1879.1.1"']),
                                    state("1 2"), state("3"),
                                    army("Second Army", 2, "infantry", "cavalry"),
                                    army("First Army", 1, "infantry", "infantry"),
                                    ("navy", ['\t\tname="Home Fleet"'] + ship("Thunder", "monitor")
                                     + ship("Swift", "frigate") + ship("Bold", "monitor"))]),
            savefmt.country("FRA", culture="french", capital=4, techs=fixtures.TECHS[:1],
                            inventions=[2], blocks=[state("4 5")]),
            war, market)
    # The same saves as two campaigns, for --cross.
    for part, name in (("early", "mapped0.v2"), ("late", "mapped1.v2")):
        os.makedirs(os.path.join(holding, "cross", part))
        shutil.copy(os.path.join(folder, name), os.path.join(holding, "cross", part, name))
    return mod, folder


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--update", action="store_true",
                    help="write what the program answers now as the expected answers")
    args = ap.parse_args()
    kit.need_scanner()
    holding = tempfile.mkdtemp(prefix="vic2engine")
    try:
        # A folder of its own: the helpers that build a small game write
        # into `<holding>/game`.
        mod, folder = an_edge_world(os.path.join(holding, "edges"))
        rich_mod, rich = a_furnished_world(os.path.join(holding, "furnished"))
        mapped_mod, mapped = a_mapped_world(os.path.join(holding, "mapped"))
        out = os.path.join(holding, "out")
        bad = expected.hold_cases(
            expected.REPO, "enginecheck",
            [(name, lambda f=flags: run(folder, mod, f, out, holding))
             for name, flags in SYNTHETIC_RUNS]
            + [(name, lambda f=flags: run(rich, rich_mod, f, out, holding))
               for name, flags in FURNISHED_RUNS]
            + [(name, lambda f=flags: run(mapped, mapped_mod, f, out, holding))
               for name, flags in MAPPED_RUNS], args.update)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    if not bad and not args.update:
        print("the report engine gives the recorded answers, %d ways"
              % (len(SYNTHETIC_RUNS) + len(FURNISHED_RUNS) + len(MAPPED_RUNS)))
    return bad


if __name__ == "__main__":
    sys.exit(main())

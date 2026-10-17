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
        out = os.path.join(holding, "out")
        bad = expected.hold_cases(
            expected.REPO, "enginecheck",
            [(name, lambda f=flags: run(folder, mod, f, out, holding))
             for name, flags in SYNTHETIC_RUNS]
            + [(name, lambda f=flags: run(rich, rich_mod, f, out, holding))
               for name, flags in FURNISHED_RUNS], args.update)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    if not bad and not args.update:
        print("the report engine gives the recorded answers, %d ways" % len(SYNTHETIC_RUNS))
    return bad


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
`--cross` and the report, measuring the same campaign.

`--cross` reads several campaigns at once, puts a block comparing them into
the report, and then builds the rest of that report out of the primary one.
The primary campaign is therefore measured twice on one page, and for a long
time the two measurements were made by two copies of one recipe that had
quietly drifted apart in five places: the mod's regiment size, `--mob-types`
against the mod's own list, `--player-nations` and the save's own
`player=`, and the floor `--min-pop` sets.

    python3 testkit/crossrows.py [--update]

Two campaigns under two mods that disagree about every one of those, built
from `matching.a_mod` and `savefmt`, run once per way of asking. Each run is
held to the answer recorded for it (`expected.py`): the Python's, taken
while it was still here and checked then, case by case, for what that way
of asking had to come back with -- the mod's pop list unless `--mob-types`
was given, ENG playing unless `--player-nations` said otherwise, PRU (a
province and nobody in it) measured at `--min-pop 0` and dropped at 1000,
the regiment size asked for winning even at the vanilla 3000 -- and for the
cross block and the report agreeing on every nation of the primary campaign.
"""

import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import expected                                            # noqa: E402
import matching                                            # noqa: E402
import savefmt                                             # noqa: E402


# The mod alpha was played on. A regiment costs a third of what vanilla
# charges, and `serfs` are a poor stratum the vanilla list has never heard
# of -- so a run that falls back to the built-in defaults gets both the
# divisor and the eligible pops wrong, and says so in the brigade count.
ALPHA_REGIMENT = 1000
BETA_REGIMENT = 5000
VANILLA_REGIMENT = 3000
MOD_POPS = matching.POPS + ["serfs"]
RATE = 0.5


def a_campaign_save(path, date, scale):
    """
    One save with nothing a person marked as theirs.

    No `human=yes` anywhere, which is the ordinary case for a
    single-player save and the one that separates the two readings: the
    report falls back to the save's own `player=`, and the cross path used
    to fall back to nobody.

    PRU holds one province and nobody in it, so it has no people at all.
    The report measures it -- `--min-pop` defaults to nought -- and the
    cross path used to raise that floor to one behind the caller's back.
    The province is the point: without it PRU has neither land nor people,
    which is what `analyze_save` drops as a released-nation stub, and the
    `--min-pop` case had nothing to measure either way.
    """
    def people(pid, kinds):
        out = []
        for i, (kind, size, culture) in enumerate(kinds):
            out.append(savefmt.pop(kind, pid * 100 + i, int(size * scale),
                                   culture=culture,
                                   religion="protestant"
                                   if culture == "british" else "catholic"))
        return out

    parts = [savefmt.head(date, player="ENG")]
    parts.append(savefmt.province(1, "ENG", people(1, [
        ("farmers", 12000, "british"), ("labourers", 7000, "british"),
        ("serfs", 3500, "british"), ("soldiers", 2000, "british")])))
    parts.append(savefmt.province(2, "ENG", people(2, [
        ("craftsmen", 9000, "british"), ("farmers", 4500, "british")])))
    # Irish under English rule: poor, mobilizable by type, and of no
    # accepted culture, so nothing may count them.
    parts.append(savefmt.province(3, "ENG", people(3, [
        ("farmers", 2500, "irish")])))
    parts.append(savefmt.province(4, "FRA", people(4, [
        ("farmers", 11000, "french"), ("serfs", 6000, "french")])))
    parts.append(savefmt.province(5, "FRA", people(5, [
        ("labourers", 5000, "french")])))
    # Prussia's one province, with nobody in it. It has to hold *land* to be
    # measured at all: `analyze_save` drops a tag with neither land nor people
    # as a released-nation stub, so the PRU this check used to build -- a
    # country block and nothing else -- never reached either path, and the
    # `--min-pop` case below had no subject. With a province and no pops it
    # survives that filter and is then exactly what `--min-pop 0` is about: a
    # nation of nought people that the caller has asked to see.
    parts.append(savefmt.province(6, "PRU", []))

    parts.append(savefmt.country("ENG", techs=matching.TECHS, inventions=[1]))
    parts.append(savefmt.country("FRA", culture="french", capital=4,
                                 techs=matching.TECHS[:2], inventions=[1]))
    parts.append(savefmt.country("PRU", culture="prussian", capital=1))
    return savefmt.write(path, *parts)


def a_world(holding):
    """Two campaigns, two mods, and the folder that holds them both."""
    mod_a = matching.a_mod_in_a_game(holding, "mod-alpha", pops=MOD_POPS,
                                     pop_per_regiment=ALPHA_REGIMENT,
                                     mob_size=RATE)
    mod_b = matching.a_mod_in_a_game(holding, "mod-beta",
                                     pop_per_regiment=BETA_REGIMENT,
                                     mob_size=RATE)
    parent = os.path.join(holding, "campaigns")
    alpha = os.path.join(parent, "alpha")
    beta = os.path.join(parent, "beta")
    os.makedirs(alpha)
    os.makedirs(beta)
    for i, date in enumerate(("1870.1.1", "1875.1.1", "1880.1.1")):
        a_campaign_save(os.path.join(alpha, "a%d.v2" % i), date, 1.0 + i * 0.1)
    for i, date in enumerate(("1871.1.1", "1876.1.1")):
        a_campaign_save(os.path.join(beta, "b%d.v2" % i), date, 0.9 + i * 0.1)
    return parent, mod_a, mod_b


CASES = [
    # Nobody is marked human in these saves, so the only thing left that can
    # say who was playing is the save's own `player=`, which is ENG.
    ("as it comes", []),
    # The mod names five mobilizable pop types and the caller names one.
    ("--mob-types honoured", ["--mob-types", "farmers"]),
    # And one the mod's own list leaves out: which pops are read out of a
    # save and which are counted must come from the same list.
    ("--mob-types outside the mod's list", ["--mob-types", "soldiers"]),
    # `--player-nations` overrides the lot, including the save's own player.
    ("--player-nations honoured", ["--player-nations", "FRA"]),
    # A floor of nought keeps PRU, a nation of nobody...
    ("--min-pop honoured", ["--min-pop", "0"]),
    # ...and the floor still works when it is asked for.
    ("--min-pop excludes", ["--min-pop", "1000"]),
    # The vanilla regiment size, asked for out loud, under a mod that sets
    # its own: naming the default must not read as saying nothing.
    ("--pop-per-regiment at the default", ["--pop-per-regiment", str(VANILLA_REGIMENT)]),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--update", action="store_true",
                    help="write what the program answers now as the expected answers")
    args = ap.parse_args()
    holding = tempfile.mkdtemp(prefix="vic2cross")
    book = expected.Book(expected.REPO, "crossrows", args.update)
    bad = 0
    try:
        parent, mod_a, mod_b = a_world(holding)
        width = max(len(n) for n, _e in CASES)
        for name, extra in CASES:
            out = os.path.join(holding, "out")
            env = dict(os.environ)
            env["TMPDIR"] = os.path.join(holding, "tmp")
            os.makedirs(env["TMPDIR"], exist_ok=True)
            got = expected.run(
                [parent, "--cross", "--primary", "alpha",
                 "--campaign-mod", "alpha=" + mod_a, "--campaign-mod", "beta=" + mod_b,
                 "--out", out, "--no-cache", "-j", "1"] + extra,
                holding, env, out, [(env["TMPDIR"], "TMP"), (holding, "HOLDING")])
            shutil.rmtree(out, ignore_errors=True)
            found = book.hold(name, got)
            bad += bool(found)
            expected.report(name, found, width)
        book.finish()
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print()
    if bad:
        print("%d of %d ways of asking differ from the recorded answers" % (bad, len(CASES)))
        return 1
    print("the cross block and the report give the recorded answers, %d ways" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Two mods that are nearly the same, and the save that belongs to one of them.

Reading a campaign under the wrong mod is the worst answer this program can
give, because it is not a wrong label -- it is wrong numbers. Two mods built
on a shared base rate the same cruiser differently, so the same save read
under the other one reports guns it never had. `--cross` decides
this by elimination, and nothing tested it.

    python3 testkit/matching.py

Builds a pair of minimal mod folders that differ by exactly one thing -- one
province, one technology, one country, one invention -- and a save that
belongs to one of them, then checks the match comes out right and says why.
Four differences, each tried in both directions, so a matcher that always
answered "the first one" would fail half of them.
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import kit                                                  # noqa: E402

import savefmt                                             # noqa: E402

from fixtures import TAGS, POPS, TECHS, a_mod, a_game, a_mod_in_a_game, a_vanilla, a_save, _linked  # noqa: F401,E402


def try_one(name, holding, make_mine, make_theirs, save_kwargs):
    """
    [what went wrong] when a campaign belonging to one of two mods is
    surveyed by `--cross`.

    Both ways round: the decoy is named to sort before the right answer's
    `wanted`, and then after it. Ties are broken by name, so a matcher that
    stopped telling them apart, or that always took the first or the last,
    fails one of the two.
    """
    out = []
    for decoy in ("another", "zz-another"):
        out += one_way(name, os.path.join(holding, decoy), make_mine, make_theirs, decoy,
                       save_kwargs)
    return out


def one_way(name, holding, make_mine, make_theirs, decoy, save_kwargs):
    import subprocess
    where = os.path.join(holding, name.replace(" ", "-"))
    game = a_game(os.path.join(where, "game"))
    make_mine(os.path.join(game, "mod", "wanted"))
    make_theirs(os.path.join(game, "mod", decoy))
    campaign = os.path.join(where, "campaigns", "camp")
    os.makedirs(campaign)
    a_save(os.path.join(campaign, "s.v2"), **save_kwargs)
    env = dict(os.environ, TMPDIR=os.path.join(where, "tmp"))
    os.makedirs(env["TMPDIR"])
    done = kit.analyze(*[os.path.join(where, "campaigns"), "--cross", "--game-root", game,
                           "--out", os.path.join(where, "out"), "--no-html", "--no-cache"], env=env)
    said = done.stdout + done.stderr
    line = next((l for l in said.splitlines() if l.strip().startswith("camp ")), "")
    if done.returncode or not line.split("->")[-1].strip().startswith("wanted"):
        return ["%s (decoy %s): the campaign was matched as %r, not to the mod it came from -- %s"
                % (name, decoy, line.strip(), said[-400:])]
    return []


def main():
    holding = tempfile.mkdtemp(prefix="vic2match")
    wrong = []
    try:
        cases = []

        # One province apart, which is the case the map test exists for:
        # two mods can agree on every country, technology and invention and
        # differ only here.
        mine = a_mod
        theirs = lambda root: a_mod(root, provinces=range(1, 42))
        cases.append(("one province apart", mine, theirs, {}))

        # A technology only one folder defines, and the save has it. The
        # test is one-sided and has to be: a save does not use every
        # technology its mod defines, so a folder holding one the campaign
        # never researched is not thereby ruled out. What rules a folder
        # out is a name in the save it has never heard of.
        mine = lambda root: a_mod(root, techs=TECHS + ["a_tech_of_its_own"])
        theirs = a_mod
        cases.append(("a technology only one defines", mine, theirs,
                      {"techs": TECHS + ["a_tech_of_its_own"]}))

        # One country apart: the save names a tag only one folder defines.
        mine = lambda root: a_mod(root, tags=TAGS + ["BAV"])
        theirs = a_mod
        cases.append(("one country apart", mine, theirs,
                      {"tags": TAGS + ["BAV"]}))

        # The save names an invention past the end of the other's array.
        mine = lambda root: a_mod(root, inventions=40)
        theirs = lambda root: a_mod(root, inventions=3)
        cases.append(("the save names a later invention", mine, theirs,
                      {"top_invention": 30}))

        for name, mine, theirs, kwargs in cases:
            bad = try_one(name, holding, mine, theirs, kwargs)
            wrong += bad
            print("  %-34s %s" % (name, "ok" if not bad else "FAIL"))
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("each campaign was matched to the mod it came from, either way round")
    return 0


if __name__ == "__main__":
    sys.exit(main())

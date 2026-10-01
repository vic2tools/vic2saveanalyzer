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
sys.path.insert(0, HERE)

import savefmt                                             # noqa: E402

TAGS = ["ENG", "FRA", "PRU", "RUS", "AUS", "TUR", "SPA", "USA"]
POPS = ["farmers", "labourers", "craftsmen", "soldiers", "aristocrats"]
TECHS = ["flintlock_rifles", "post_napoleonic_thought", "clipper_design",
         "the_stirrup", "iron_working"]


def a_mod(root, tags=None, techs=None, provinces=None, inventions=2,
          pops=None, pop_per_regiment=None, mob_size=0.0):
    """
    The smallest folder `_mod_facts` will read as a mod.

    The last three are for the callers that go on to *read* the mod rather
    than only match a campaign against it: which pops it lets a nation
    mobilize, what a regiment of them costs, and whether anything in it
    grants a mobilisation size at all. A mod that grants none is a mod every
    nation scores zero under, which makes a brigade count that cannot tell
    two regiment sizes apart. Left alone they write what they always wrote.
    """
    tags = TAGS if tags is None else tags
    techs = TECHS if techs is None else techs
    provinces = range(1, 41) if provinces is None else provinces
    pops = POPS if pops is None else pops

    os.makedirs(os.path.join(root, "common"), exist_ok=True)
    with open(os.path.join(root, "common", "countries.txt"), "w") as fh:
        for tag in tags:
            fh.write('%s = "countries/%s.txt"\n' % (tag, tag))

    os.makedirs(os.path.join(root, "poptypes"), exist_ok=True)
    for pop in pops:
        with open(os.path.join(root, "poptypes", pop + ".txt"), "w") as fh:
            fh.write("strata = poor\n")

    os.makedirs(os.path.join(root, "technologies"), exist_ok=True)
    with open(os.path.join(root, "technologies", "army_tech.txt"), "w") as fh:
        fh.write("folder = army_tech\n")
        for tech in techs:
            # Only the first one grants it, so a nation holding every
            # technology in the mod has a rate the test can state outright
            # rather than derive.
            grant = ("\tmobilisation_size = %.3f\n" % mob_size
                     if mob_size and tech == techs[0] else "")
            fh.write("%s = {\n\tarea = army_tech\n\tyear = 1836\n"
                     "\tcost = 100\n%s}\n" % (tech, grant))

    if pop_per_regiment is not None:
        # defines.lua is Lua, and `_read_defines` finds the key by regex
        # wherever it sits, so the real file's nesting is written out rather
        # than a flat line that would pass here and not in the game.
        with open(os.path.join(root, "common", "defines.lua"), "w") as fh:
            fh.write("NDefines = {\n\tNMilitary = {\n"
                     "\t\tPOP_SIZE_PER_REGIMENT = %d,\n\t},\n}\n"
                     % pop_per_regiment)

    os.makedirs(os.path.join(root, "inventions"), exist_ok=True)
    with open(os.path.join(root, "inventions", "army.txt"), "w") as fh:
        for i in range(inventions):
            fh.write("an_invention_%d = {\n\tlimit = {\n\t}\n"
                     "\tchance = {\n\t\tfactor = 1\n\t}\n}\n" % i)

    os.makedirs(os.path.join(root, "map"), exist_ok=True)
    with open(os.path.join(root, "map", "definition.csv"), "w") as fh:
        fh.write("province;red;green;blue;x;x\n")
        for pid in provinces:
            fh.write("%d;1;2;3;name;x\n" % pid)
    return root


def a_game(root):
    """
    The least a folder needs to be read as a Victoria II install: its map's
    `default.map`, and nothing in it to inherit.

    A mod is only read inside one: the analyzer refuses a mod anywhere but
    an install's mod folder, the way the game only loads mods from there.
    """
    # Fixture builders must never write through a link into real inputs.
    target = os.path.abspath(os.path.join(root, "map", "default.map"))
    check = target
    while True:
        if os.path.islink(check):
            raise ValueError("refusing to write a fixture through a symlink: " + check)
        parent = os.path.dirname(check)
        if parent == check:
            break
        check = parent
    os.makedirs(os.path.join(root, "map"), exist_ok=True)
    open(target, "w").close()
    return root


def a_mod_in_a_game(holding, name, **kwargs):
    """`a_mod`, at `<holding>/game/mod/<name>`, on an `a_game` install."""
    game = a_game(os.path.join(holding, "game"))
    return a_mod(os.path.join(game, "mod", name), **kwargs)


def a_vanilla(root, **kwargs):
    """
    An install a run can be read on with no mod: `a_mod`'s rules and names,
    and the map file that makes it an install. Every report is read on an
    installed game, so a check that runs the analyzer names one of these
    with `--game-root` where it used to name nothing.
    """
    return a_game(a_mod(root, **kwargs))


def a_save(path, tags=None, techs=None, provinces=None, top_invention=1):
    """A save carrying exactly the names a mod either accounts for or not."""
    tags = TAGS if tags is None else tags
    techs = TECHS if techs is None else techs
    provinces = range(1, 41) if provinces is None else provinces

    parts = [savefmt.head("1880.1.1", player=tags[0])]
    for pid in provinces:
        parts.append(savefmt.province(
            pid, tags[0], [savefmt.pop("farmers", pid, 1000)]))
    for tag in tags:
        parts.append(savefmt.country(tag, techs=techs,
                                     inventions=[top_invention]))
    return savefmt.write(path, *parts)


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
    done = subprocess.run([sys.executable, os.path.join(HERE, "vic2_analyzer.py"),
                           os.path.join(where, "campaigns"), "--cross", "--game-root", game,
                           "--out", os.path.join(where, "out"), "--no-html", "--no-cache"],
                          capture_output=True, text=True, env=env)
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

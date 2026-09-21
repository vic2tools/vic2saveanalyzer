#!/usr/bin/env python3
"""
Two mods that are nearly the same, and the save that belongs to one of them.

Reading a campaign under the wrong mod is the worst answer this program can
give, because it is not a wrong label -- it is wrong numbers. Two mods built
on a shared base rate the same cruiser differently, so the same save read
under the other one reports guns it never had. `cross.match_mod` decides
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

import cross                                               # noqa: E402

TAGS = ["ENG", "FRA", "PRU", "RUS", "AUS", "TUR", "SPA", "USA"]
POPS = ["farmers", "labourers", "craftsmen", "soldiers", "aristocrats"]
TECHS = ["flintlock_rifles", "post_napoleonic_thought", "clipper_design",
         "the_stirrup", "iron_working"]


def a_mod(root, tags=None, techs=None, provinces=None, inventions=2):
    """The smallest folder `_mod_facts` will read as a mod."""
    tags = TAGS if tags is None else tags
    techs = TECHS if techs is None else techs
    provinces = range(1, 41) if provinces is None else provinces

    os.makedirs(os.path.join(root, "common"), exist_ok=True)
    with open(os.path.join(root, "common", "countries.txt"), "w") as fh:
        for tag in tags:
            fh.write('%s = "countries/%s.txt"\n' % (tag, tag))

    os.makedirs(os.path.join(root, "poptypes"), exist_ok=True)
    for pop in POPS:
        with open(os.path.join(root, "poptypes", pop + ".txt"), "w") as fh:
            fh.write("strata = poor\n")

    os.makedirs(os.path.join(root, "technologies"), exist_ok=True)
    with open(os.path.join(root, "technologies", "army_tech.txt"), "w") as fh:
        fh.write("folder = army_tech\n")
        for tech in techs:
            fh.write("%s = {\n\tarea = army_tech\n\tyear = 1836\n"
                     "\tcost = 100\n}\n" % tech)

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


def a_save(path, tags=None, techs=None, provinces=None, top_invention=1):
    """A save carrying exactly the names a mod either accounts for or not."""
    tags = TAGS if tags is None else tags
    techs = TECHS if techs is None else techs
    provinces = range(1, 41) if provinces is None else provinces

    out = ['date="1880.1.1"', 'player="%s"' % tags[0], "government=3",
           'start_date="1836.1.1"']
    for pid in provinces:
        out += ["%d=" % pid, "{", '\tname="P%d"' % pid,
                '\towner="%s"' % tags[0], '\tcontroller="%s"' % tags[0],
                "\tfarmers=", "\t{", "\t\tid=%d" % pid, "\t\tsize=1000",
                "\t\tbritish=protestant", "\t}", "}"]
    for tag in tags:
        # The indentation is the format. `technology=` one tab in, each
        # technology two, each opening brace on its own line -- which is
        # how the sniffer finds them, and writing it any other way makes a
        # save that looks fine and carries no technologies at all.
        out += ["%s=" % tag, "{", '\tprimary_culture="british"',
                "\ttechnology=", "\t{"]
        for tech in techs:
            out += ["\t\t%s=" % tech, "\t\t{", "\t\t\t1 0.000", "\t\t}"]
        out += ["\t}", "\tactive_inventions=", "\t{",
                "\t\t%d" % top_invention, "\t}", "}"]
    with open(path, "w", encoding="latin-1", newline="\r\n") as fh:
        fh.write("\n".join(out) + "\n")
    return path


def try_one(name, holding, mine, theirs, save_kwargs):
    """
    [what went wrong] when a save belonging to `mine` is matched.

    Both directions, so a matcher that simply took the first candidate
    would be caught. And the decoy is named `another` against the right
    answer's `wanted`, because ties are broken alphabetically: if the
    thing being tested stops working and both folders fit, the decoy wins
    and the case fails, which is the whole point of having it.
    """
    wrong = []
    for order in ("right first", "right second"):
        pair = ([("wanted", mine), ("another", theirs)]
                if order == "right first"
                else [("another", theirs), ("wanted", mine)])
        save = a_save(os.path.join(holding, "s.v2"), **save_kwargs)
        cross._MOD_FACTS.clear()
        cross._CAPACITY.clear()
        label, _path, rows = cross.match_mod([save], pair, sample=1)
        if label != "wanted":
            why = "; ".join("%s: %s %s" % r for r in rows)
            wrong.append("%s (%s): matched %r, not the one it came from -- %s"
                         % (name, order, label, why[:150]))
    return wrong


def main():
    holding = tempfile.mkdtemp(prefix="vic2match")
    wrong = []
    try:
        cases = []

        # One province apart, which is the case the map test exists for:
        # two mods can agree on every country, technology and invention and
        # differ only here.
        mine = a_mod(os.path.join(holding, "p-mine"))
        theirs = a_mod(os.path.join(holding, "p-theirs"),
                       provinces=range(1, 42))
        cases.append(("one province apart", mine, theirs, {}))

        # A technology only one folder defines, and the save has it. The
        # test is one-sided and has to be: a save does not use every
        # technology its mod defines, so a folder holding one the campaign
        # never researched is not thereby ruled out. What rules a folder
        # out is a name in the save it has never heard of.
        mine = a_mod(os.path.join(holding, "t-mine"),
                     techs=TECHS + ["a_tech_of_its_own"])
        theirs = a_mod(os.path.join(holding, "t-theirs"))
        cases.append(("a technology only one defines", mine, theirs,
                      {"techs": TECHS + ["a_tech_of_its_own"]}))

        # One country apart: the save names a tag only one folder defines.
        mine = a_mod(os.path.join(holding, "c-mine"), tags=TAGS + ["BAV"])
        theirs = a_mod(os.path.join(holding, "c-theirs"))
        cases.append(("one country apart", mine, theirs,
                      {"tags": TAGS + ["BAV"]}))

        # The save names an invention past the end of the other's array.
        mine = a_mod(os.path.join(holding, "i-mine"), inventions=40)
        theirs = a_mod(os.path.join(holding, "i-theirs"), inventions=3)
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

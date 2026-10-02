#!/usr/bin/env python3
"""
The shapes a save can take, read end to end and held to recorded answers.

Real campaigns are written one way, so a check against them proves the
common path and nothing else. These are the shapes that differ from it, each
of which has broken a reader or come within one rule of it:

- the awkward save: a pop with a mod's own block nested inside it, a
  province with no owner (its people still count to the world), a nation with
  no naval base and one whose harbour is occupied;
- the awkward country: an army loaded onto a transport, a key that appears
  twice, a colonial state, a technology written as a pair, a ship with
  experience, accepted cultures, flags, modifiers and the mod-set reforms;
- the furnished save `savefmt.furnished` writes, with as much in it as the
  builders can write;
- states: two of a nation's states in one region of a mod whose
  region.txt spans lines and carries comments, a colonial state, a state
  whose region is named `__proto__`, pops of accepted and unaccepted
  cultures, land nobody owns -- and the same save with its countries first,
  and laid out with spaces where the game writes tabs.

Each is read as a report, with `--peek` and with `--verify`, and every
answer -- what was printed, the status, the nine tables and what the page
carries -- must be the one recorded (`expected.py`). The answers were the
Python reader's, taken while it was still here; before then these checks
held the Rust scanner to that reader field by field.

    python3 testkit/saveshapes.py [--update]
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

AWKWARD = '''date="1881.3.1"
player="ENG"
government=3
flags=
{
\tthe_great_trek=yes
}
start_date="1836.1.1"
1=
{
\tname="Plain"
\towner="ENG"
\tcontroller="ENG"
\tcore="ENG"
\tfarmers=
\t{
\t\tid=101
\t\tsize=1000
\t\tbritish=protestant
\t\tmoney=5.00000
\t\tliteracy=0.50000
\t\tlife_needs=0.90000
\t}
}
2=
{
\tname="Nested"
\towner="ENG"
\tcontroller="ENG"
\tfarmers=
\t{
\t\tid=102
\t\tsize=2000
\t\tguild=
\t\t{
\t\t\tname="Weavers"
\t\t\tcharter="royal"
\t\t}
\t\tbritish=catholic
\t\tliteracy=0.25000
\t}
}
3=
{
\tname="Unowned"
\tfarmers=
\t{
\t\tid=103
\t\tsize=7777
\t\tbritish=protestant
\t}
}
4=
{
\tname="Harbour"
\towner="FRA"
\tcontroller="ENG"
\tnaval_base=
\t{
\t\tlevel=4
\t}
\tsoldiers=
\t{
\t\tid=104
\t\tsize=500
\t\tfrench=catholic
\t\tliteracy=0.10000
\t}
}
ENG=
{
\tprimary_culture="british"
\tgovernment=democracy
\tprestige=10.000
\tmoney=100.00000
}
FRA=
{
\tprimary_culture="french"
\tgovernment=democracy
\tprestige=5.000
\tmoney=50.00000
}
'''

COUNTRY = '''date="1881.3.1"
player="ENG"
government=3
flags=
{
\tthe_great_trek=yes
}
start_date="1836.1.1"
1=
{
\tname="Home"
\towner="ENG"
\tcontroller="ENG"
\tcore="ENG"
\tsoldiers=
\t{
\t\tid=1
\t\tsize=5000
\t\tbritish=protestant
\t\tliteracy=0.50000
\t}
}
2=
{
\tname="Colony"
\towner="ENG"
\tcontroller="ENG"
\tfarmers=
\t{
\t\tid=2
\t\tsize=3000
\t\tzulu=animist
\t\tliteracy=0.10000
\t}
}
ENG=
{
\tprimary_culture="british"
\tculture=
\t{
\t\t"welsh" "irish"
\t}
\tgovernment=hms_government
\tcivilized=yes
\tcapital=1
\tprestige=42.500
\tbadboy=3.250
\tmoney=1234.56789
\twar_exhaustion=1.500
\tmobilize=yes
\thuman=yes
\tvoting_system=first_past_the_post
\tslavery=no_slavery
\tflags=
\t{
\t\twon_the_war=yes
\t\tlost_the_peace=no
\t}
\tmodifier=
\t{
\t\tmodifier="the_sick_man"
\t\tdate="1880.1.1"
\t}
\tmodifier=
\t{
\t\tmodifier="great_power"
\t\tdate="1881.1.1"
\t}
\ttechnology=
\t{
\t\tflintlock_rifles=
\t\t{
\t\t\t1 0.000
\t\t}
\t\tpost_napoleonic_thought=
\t\t{
\t\t\t1 0.000
\t\t}
\t\tclipper_design=
\t\t{
\t\t\t1 0.000
\t\t}
\t\tnot_researched=
\t\t{
\t\t\t0 0.000
\t\t}
\t}
\tactive_inventions=
\t{
\t\t3 17 42
\t}
\tsaved_country_supply=
\t{
\t\tammunition=12.50000
\t\tcoal=0.00000
\t}
\tstate=
\t{
\t\tid=
\t\t{
\t\t\tid=1
\t\t\ttype=47
\t\t}
\t\tprovinces=
\t\t{
\t\t\t1
\t\t}
\t\tstate_buildings=
\t\t{
\t\t\tlevel=4
\t\t\tbuilding=0
\t\t}
\t}
\tstate=
\t{
\t\tprovinces=
\t\t{
\t\t\t2
\t\t}
\t\tis_colonial=2
\t}
\tscheduled_mobilization=
\t{
\t\tspawned=no
\t}
\tarmy=
\t{
\t\tname="Home Army"
\t\tlocation=1
\t\tregiment=
\t\t{
\t\t\tname="1st Foot"
\t\t\tpop=
\t\t\t{
\t\t\t\tid=1
\t\t\t\ttype=7
\t\t\t}
\t\t\ttype=infantry
\t\t\tstrength=0.75000
\t\t}
\t\tregiment=
\t\t{
\t\t\tname="2nd Horse"
\t\t\tpop=
\t\t\t{
\t\t\t\tid=2
\t\t\t\ttype=7
\t\t\t}
\t\t\ttype=cavalry
\t\t\tstrength=1.00000
\t\t}
\t}
\tnavy=
\t{
\t\tname="Channel Fleet"
\t\tlocation=2
\t\tship=
\t\t{
\t\t\tname="HMS Test"
\t\t\ttype=manowar
\t\t\tstrength=80.000
\t\t\texperience=25.000
\t\t}
\t\tarmy=
\t\t{
\t\t\tname="Embarked"
\t\t\tregiment=
\t\t\t{
\t\t\t\tname="3rd Marines"
\t\t\t\tpop=
\t\t\t\t{
\t\t\t\t\tid=3
\t\t\t\t\ttype=7
\t\t\t\t}
\t\t\t\ttype=infantry
\t\t\t\tstrength=0.50000
\t\t\t}
\t\t}
\t}
}
'''


def write_text(path, text):
    with open(path, "w", encoding="latin-1", newline="\r\n") as fh:
        fh.write(text)
    return path


def states_parts():
    """The states save, as its parts, in the game's order."""
    def state(ids, extra=()):
        return ("state", savefmt.nest("provinces", ["\t\t\t" + ids], 2) + list(extra))
    return [savefmt.head("1880.1.1"),
            savefmt.province(1, "ENG", [savefmt.pop("clerks", 1, 100, literacy=1)]),
            savefmt.province(2, "ENG", [savefmt.pop("farmers", 2, 500, culture="irish", literacy=.1),
                                        savefmt.pop("farmers", 3, 400, culture="french", literacy=.1)]),
            savefmt.province(3, "FRA", [savefmt.pop("farmers", 4, 500, culture="french", literacy=.8)]),
            savefmt.province(4, "ENG", [savefmt.pop("farmers", 5, 200, culture="french", literacy=.2)]),
            savefmt.province(5, "ENG", [savefmt.pop("soldiers", 6, 50, literacy=.5)]),
            savefmt.province(6, None, [savefmt.pop("farmers", 7, 111)]),
            savefmt.country("ENG", blocks=[("culture", ["\t\t\"irish\""]),
                                           state("1"), state("2"),
                                           state("4", ["\t\tis_colonial=2"]), state("5")]),
            savefmt.country("FRA", culture="french", blocks=[state("3")])]


REGIONS = ("shared = { 1 2\n3 # the third\n}\n"
           "colony = {\n\t4\n}\n"
           "__proto__ = { 5 }\n"
           "everything = { 1 2 3 4 5 6 }\n")


def worlds(holding):
    """[(name, the saves folder, the arguments naming the game or mod)]."""
    game = matching.a_vanilla(os.path.join(holding, "Victoria 2"))
    plain = ["--game-root", game]
    out = []

    def folder(name):
        where = os.path.join(holding, "saves", name)
        os.makedirs(where)
        return where

    write_text(os.path.join(folder("awkward"), "awkward.v2"), AWKWARD)
    out.append(("awkward", os.path.join(holding, "saves", "awkward"), plain))
    write_text(os.path.join(folder("country"), "country.v2"), COUNTRY)
    out.append(("country", os.path.join(holding, "saves", "country"), plain))
    savefmt.furnished(os.path.join(folder("furnished"), "furnished.v2"))
    out.append(("furnished", os.path.join(holding, "saves", "furnished"), plain))

    mod = matching.a_mod_in_a_game(os.path.join(holding, "regions"), "Regions",
                                   pops=matching.POPS + ["clerks"])
    with open(os.path.join(mod, "map", "region.txt"), "w") as fh:
        fh.write(REGIONS)
    # A map of the five provinces, with runs of every awkward kind in it
    # (`raster.picture`), and anchors the game gives for two of them.
    import raster
    from pathlib import Path
    raster.write_map(Path(mod), raster.picture(23, 19))
    with open(os.path.join(mod, "map", "positions.txt"), "w") as fh:
        fh.write("1 = { unit = { x = 10.000 y = 12.000 } }\n"
                 "2 = { town = { x = 5.500 y = 6.000 } }\n")
    parts = states_parts()
    savefmt.write(os.path.join(folder("states"), "states.v2"), *parts)
    out.append(("states", os.path.join(holding, "saves", "states"), ["--mod-path", mod]))
    savefmt.write(os.path.join(folder("states, countries first"), "states.v2"),
                  parts[0], *parts[-2:], *parts[1:-2])
    out.append(("states, countries first", os.path.join(holding, "saves", "states, countries first"),
                ["--mod-path", mod]))
    spaced = os.path.join(folder("states, spaced"), "states.v2")
    with open(os.path.join(holding, "saves", "states", "states.v2"), "rb") as fh:
        text = fh.read()
    with open(spaced, "wb") as fh:
        fh.write(text.replace(b"=\r\n{", b"= {").replace(b"\t", b"    "))
    out.append(("states, spaced", os.path.join(holding, "saves", "states, spaced"),
                ["--mod-path", mod]))
    return out


ASKED = [("", []), ("peek", ["--peek"]), ("verified", ["--verify"])]


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--update", action="store_true",
                    help="write what the program answers now as the expected answers")
    args = ap.parse_args()
    holding = tempfile.mkdtemp(prefix="vic2shapes")
    book = expected.Book(expected.REPO, "saveshapes", args.update)
    bad = 0
    try:
        cases = [(("%s, %s" % (name, how)) if how else name, saves, game + asked)
                 for name, saves, game in worlds(holding) for how, asked in ASKED]
        width = max(len(c[0]) for c in cases)
        for name, saves, argv in cases:
            out = os.path.join(holding, "out")
            env = dict(os.environ)
            env["TMPDIR"] = os.path.join(holding, "tmp")
            os.makedirs(env["TMPDIR"], exist_ok=True)
            got = expected.run([saves, "--out", out, "--no-cache", "-j", "1"] + argv,
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
        print("%d of %d differ from the recorded answers" % (bad, len(cases)))
        return 1
    print("every shape gives the recorded answer, %d ways" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())

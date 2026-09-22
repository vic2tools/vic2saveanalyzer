#!/usr/bin/env python3
"""
The awkward save: layouts that are legal but rare, and have caught bugs.

Real campaigns are written one way, so parity against them proves the common
path and nothing else. These are the shapes that differ from it -- a pop with
a mod's own nested block inside it, a block indented where the game writes it
flat, a province with no owner, a nation with no naval base -- each of which
has either broken the Rust scanner or come within one rule of it.

    python3 testkit/awkward.py

Writes a save, reads it both ways, and says whether they agree.
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

SAVE = '''date="1881.3.1"
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


def main():
    import fastscan
    import readsave
    import vic2_analyzer as va

    out = os.path.join(HERE, "testkit", "_awkward.v2")
    with open(out, "w", encoding="latin-1", newline="\r\n") as fh:
        fh.write(SAVE)
    readsave.PLAIN.apply()

    fast = va.analyze_save(out, verbose=False)
    real = fastscan.scan
    fastscan.scan = lambda *a, **k: None
    try:
        slow = va.analyze_save(out, verbose=False)
    finally:
        fastscan.scan = real

    problems = []
    if fastscan.available() is None:
        print("no scanner built; only the Python reading is checked")
    for tag in sorted(set(fast[1]) | set(slow[1])):
        a, b = fast[1].get(tag, {}), slow[1].get(tag, {})
        for key in sorted(set(a) | set(b)):
            x, y = a.get(key), b.get(key)
            if isinstance(x, set) or isinstance(y, set):
                x, y = sorted(x or ()), sorted(y or ())
            if x != y:
                problems.append("%s.%s: scanner=%r python=%r" % (tag, key, x, y))

    eng = slow[1]["ENG"]
    # A pop with a mod's own nested block still has the culture the game gave
    # it, not the name of the block or of anything inside it.
    cultures = dict(eng["pop_by_culture"])
    if sorted(cultures) != ["british"]:
        problems.append("cultures came out as %s, expected only british"
                        % sorted(cultures))
    # The unowned province's people are in the world but in nobody's nation.
    if slow[0]["world_pop"] != 1000 + 2000 + 7777 + 500:
        problems.append("world_pop is %s, expected 11277" % slow[0]["world_pop"])
    if eng["total_pop"] != 3000:
        problems.append("ENG total_pop is %s, expected 3000" % eng["total_pop"])
    # A nation with no naval base keeps an integer zero, which the CSV writes.
    if repr(eng["naval_base_levels"]) != "0":
        problems.append("ENG naval_base_levels is %r, expected int 0"
                        % eng["naval_base_levels"])
    fra = slow[1]["FRA"]
    if fra["naval_base_levels"] != 4.0 or fra["ports"] != 1:
        problems.append("FRA harbour read as %r/%r"
                        % (fra["naval_base_levels"], fra["ports"]))
    # Held by someone else, so it counts as occupied.
    if sorted(fra["occupied_provinces"]) != [4]:
        problems.append("FRA occupied is %r" % sorted(fra["occupied_provinces"]))

    os.remove(out)
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("   " + p)
        return 1
    print("awkward save: both readings agree, and every expectation holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())

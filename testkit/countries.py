#!/usr/bin/env python3
"""
Country blocks with the awkward shapes in them.

The 1870s campaign exercises the common ones and nothing else, and the Rust
country reader has to agree with the Python on the rest too: an army loaded
onto a transport, a key that appears twice, a colonial state, a technology
written as a pair, a ship with experience, and the mod-set reform keys --
which real saves here never reach, because there is no mod on this machine.

    python3 testkit/countries.py

Reads the save both ways and compares every field of every nation.
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


def main():
    import readsave
    from readboth import both_ways, differences

    out = os.path.join(HERE, "testkit", "_countries.v2")
    with open(out, "w", encoding="latin-1", newline="\r\n") as fh:
        fh.write(SAVE)
    # Reforms are the mod's business, and without one nothing here would
    # exercise them. These two are real IGoR reform keys, and they are set
    # the way the program gives them: one reading, handed over with the save.
    reading = readsave.PLAIN._replace(reform_keys=("slavery", "voting_system"))

    fast, slow = both_ways(out, reading)

    problems = []
    for where, x, y in differences(fast, slow):
        problems.append("%s\n      rust  : %r\n      python: %r"
                        % (where, x, y))

    eng = slow[1]["ENG"]
    def want(what, got, expected):
        if got != expected:
            problems.append("%s is %r, expected %r" % (what, got, expected))

    want("techs", eng["techs"], 3)
    # Two of the three researched techs are army ones: flintlock_rifles and
    # post_napoleonic_thought. Getting this wrong first time is why the
    # expectation is spelled out rather than copied from a run.
    want("army techs", eng["army_techs"], 2)
    want("navy techs", eng["navy_techs"], 1)
    want("brigades (embarked one included)", eng["brigades"], 3)
    want("armies", eng["armies"], 2)
    want("navies", eng["navies"], 1)
    want("ships", eng["ships"], 1)
    want("states", eng["states"], 2)
    want("factories", eng["factory_count"], 1)
    want("factory levels", eng["factory_levels"], 4)
    want("colonial provinces", sorted(eng["colonial_provinces"]), [2])
    want("colonial level", dict(eng["colonial_level"]), {2: 2})
    want("both modifiers kept", sorted(eng["modifiers"]),
         ["great_power", "the_sick_man"])
    want("reforms", dict(eng["reforms"]),
         {"voting_system": "first_past_the_post", "slavery": "no_slavery"})
    want("accepted cultures", sorted(eng["accepted_cultures"]),
         ["irish", "welsh"])
    want("primary culture unquoted", eng["primary_culture"], "british")
    want("inventions", eng["invention_ids"], [3, 17, 42])
    want("goods with none left out", dict(eng["goods_supply"]),
         {"ammunition": 12.5})
    want("mobilized", eng["is_mobilized"], 1)
    want("human", eng["human"], True)
    want("mobilizing", eng["mobilizing"], 1)
    want("country flags (only the yes)", sorted(eng["country_flags"]),
         ["won_the_war"])
    want("the embarked brigade took the navy's province",
         dict(eng["units_at"].get(2, {})), {"infantry": 1})
    want("men at the navy's province",
         dict(eng["men_at"].get(2, {})), {"infantry": 500})
    # 80% strength against 25% experience: 0.8 / (1 - 0.25).
    crew = round(eng["ship_crew"]["manowar"], 6)
    want("ship crew", crew, round(0.8 / 0.75, 6))

    # Unused fields still need correct boundaries, including quoted braces
    # and inline closings. Locations may follow embarked troops. Duplicate
    # scalars and mixed bare/keyed blocks retain the generic reader's meaning.
    variants = [
        SAVE.replace('level=4', 'level=4\n\t\t\tprofit={ 1 2 { 3 } "} {" }'),
        SAVE.replace('building=0', 'building=0\n\t\t\t7').replace('level=4', 'ignored=4'),
        SAVE.replace('strength=80.000', 'strength=80.000\n\t\t\tstrength=50.000'),
        SAVE.replace('\t\tlocation=2\n', '').replace('\n\t}\n}', '\n\t\tlocation=2\n\t}\n}'),
    ]
    for n, text in enumerate(variants):
        with open(out, 'w', encoding='latin-1') as fh:
            fh.write(text)
        fast, slow = both_ways(out, reading)
        problems.extend('variant %s: %s' % (n, where)
                        for where, _x, _y in differences(fast, slow))
    os.remove(out)
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("   " + p)
        return 1
    print("country shapes: both readings agree, and every expectation holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())

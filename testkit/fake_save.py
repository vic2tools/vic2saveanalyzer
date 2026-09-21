#!/usr/bin/env python3
"""
A save-shaped file, for profiling the parser without owning the game.

Not a playable save -- it is the *shape* of one: the header scalars, a couple
of thousand province blocks each holding a dozen pops with their ideologies
and issues, a couple of hundred country blocks with technology, inventions and
armies, and a tail of wars. Those are the blocks the analyzer actually walks,
in roughly the proportions a real save has them, which is what a profile needs
to mean anything.

    python3 testkit/fake_save.py /tmp/big.v2 --mb 25
"""

import argparse
import random
import sys

POPS = ["farmers", "labourers", "artisans", "clerks", "craftsmen", "clergymen",
        "officers", "soldiers", "aristocrats", "capitalists", "bureaucrats"]
CULTURES = ["swedish", "north_german", "french", "british", "russian",
            "han", "yankee", "dixie", "polish", "italian"]
RELIGIONS = ["protestant", "catholic", "orthodox", "mahayana", "sunni"]
TAGS = ["SWE", "PRU", "FRA", "ENG", "RUS", "AUS", "TUR", "SPA", "USA", "CHI"]
GOODS = ["ammunition", "small_arms", "artillery", "canned_food", "cotton",
         "dye", "wool", "silk", "coal", "sulphur", "iron", "timber"]
UNITS = ["infantry", "cavalry", "artillery", "guard", "engineer"]


def tag_for(i):
    return TAGS[i % len(TAGS)] if i < len(TAGS) else "T%02d" % (i % 100)


def a_pop(rng, kind):
    """
    One pop, at the depth the game writes it.

    The depth is not decoration: the parser's province regex is anchored on
    it -- one tab for a province's own fields and for a pop's opening line,
    two for the pop's numbers. Written a level deeper, as this was at first,
    every pop in the file is silently invisible and a profile of the parser
    measures it doing half its work.
    """
    return (
        "\t%s=\n\t{\n"
        "\t\tid=\n\t\t{\n\t\t\tid=%d\n\t\t\ttype=13\n\t\t}\n"
        "\t\tsize=%d\n"
        "\t\t%s=%s\n"
        "\t\tmoney=%.5f\n"
        "\t\tideology=\n\t\t{\n%s\t\t}\n"
        "\t\tissues=\n\t\t{\n%s\t\t}\n"
        "\t\tcon=%.5f\n\t\tmil=%.5f\n\t\tliteracy=%.5f\n"
        "\t\tbank=%.5f\n\t\tlife_needs=%.5f\n"
        "\t}\n"
    ) % (kind, rng.randrange(1, 900000), rng.randrange(80, 90000),
         rng.choice(CULTURES), rng.choice(RELIGIONS), rng.uniform(0, 9000),
         "".join("\t\t\t%d=%.5f\n" % (i, rng.random()) for i in range(1, 7)),
         "".join("\t\t\t%d=%.5f\n" % (i, rng.random()) for i in range(1, 9)),
         rng.random() * 4, rng.random() * 6, rng.random(),
         rng.uniform(0, 500), rng.random())


def a_province(rng, pid):
    out = ["%d=\n{\n" % pid,
           '\tname="Province %d"\n' % pid,
           '\towner="%s"\n' % tag_for(rng.randrange(40)),
           '\tcontroller="%s"\n' % tag_for(rng.randrange(40)),
           '\tcore="%s"\n' % tag_for(rng.randrange(40)),
           "\tgarrison=%.3f\n" % (rng.random() * 100),
           "\tlife_rating=%d\n" % rng.randrange(10, 40)]
    for kind in rng.sample(POPS, rng.randrange(4, 10)):
        out.append(a_pop(rng, kind))
    out.append("\trailroad=\n\t{\n\t\tlevel=%d\n\t}\n" % rng.randrange(0, 6))
    out.append("}\n")
    return "".join(out)


def a_country(rng, tag):
    techs = "".join("\t\ttech_%d=\n\t\t{\n\t\t\t1 %.3f\n\t\t}\n" % (i, rng.random())
                    for i in range(rng.randrange(20, 90)))
    inventions = " ".join(str(rng.randrange(1, 2000))
                          for _ in range(rng.randrange(20, 200)))
    regiments = "".join(
        '\t\tregiment=\n\t\t{\n\t\t\tname="%d Brigade"\n\t\t\ttype=%s\n'
        "\t\t\tcount=%d\n\t\t\tstrength=%.3f\n\t\t}\n"
        % (i, rng.choice(UNITS), rng.randrange(1000, 3000), rng.random())
        for i in range(rng.randrange(3, 30)))
    stock = "".join("\t\t%s=%.5f\n" % (g, rng.uniform(0, 5000)) for g in GOODS)
    return (
        "%s=\n{\n"
        '\tprimary_culture="%s"\n\treligion="%s"\n\tgovernment=democracy\n'
        "\tprestige=%.3f\n\tmoney=%.5f\n\tbadboy=%.3f\n"
        "\tconscription=mandatory_service\n"
        "\ttechnology=\n\t{\n%s\t}\n"
        "\tactive_inventions=\n\t{\n\t\t%s\n\t}\n"
        "\tstockpile=\n\t{\n%s\t}\n"
        '\tarmy=\n\t{\n\t\tname="Army"\n%s\t}\n'
        "}\n"
    ) % (tag, rng.choice(CULTURES), rng.choice(RELIGIONS), rng.uniform(0, 300),
         rng.uniform(0, 9e5), rng.random() * 25, techs, inventions, stock,
         regiments)


def main():
    ap = argparse.ArgumentParser(description="Write a save-shaped file.")
    ap.add_argument("path")
    ap.add_argument("--mb", type=float, default=25.0,
                    help="how big to make it (default: %(default)s)")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    want = int(args.mb * 1024 * 1024)

    with open(args.path, "w", encoding="latin-1") as fh:
        fh.write('date="1881.3.24"\nplayer="SWE"\ngovernment=3\n')
        fh.write("flags=\n{\n%s}\n" % "".join(
            "\t%s=yes\n" % f for f in
            ("the_great_trek", "crimean_war_has_begun", "MozartFest1838",
             "sonderbund_crisis", "risorgimento_started", "opium_war_started")))
        fh.write('start_date="1836.1.1"\nstart_pop_index=152437\n')

        written, pid = 0, 0
        # Provinces first and in bulk, which is how a save is shaped: they are
        # the overwhelming majority of it.
        while written < want * 0.82:
            pid += 1
            block = a_province(rng, pid)
            fh.write(block)
            written += len(block)
        for i in range(200):
            block = a_country(rng, tag_for(i) if i >= len(TAGS) else TAGS[i])
            fh.write(block)
            written += len(block)
        print("wrote %s: %.1f MB, %d provinces, 200 countries"
              % (args.path, written / 1048576.0, pid))
    return 0


if __name__ == "__main__":
    sys.exit(main())

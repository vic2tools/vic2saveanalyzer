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
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import savefmt                                             # noqa: E402

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


def lines(part):
    """One block as text, CRLF, the way the game writes one.

    Written a block at a time rather than joined at the end: this file
    makes twenty-five megabytes and there is no reason for all of it to
    be in memory at once.
    """
    return "\r\n".join(part) + "\r\n"


def a_pop(rng, kind, pid):
    """
    One pop with everything a real one carries.

    The depth is not decoration: the parser's province regex is anchored
    on it -- one tab for a province's own fields and for a pop's opening
    line, two for the pop's numbers. Written a level deeper, as this was
    at first, every pop in the file is silently invisible and a profile of
    the parser measures it doing half its work.

    That is why the shape comes from `savefmt` now and not from a format
    string here. `savefmt.selfcheck` reads a pop of exactly this kind back
    through both readers, so a depth that drifts fails a test instead of
    quietly halving the benchmark.
    """
    return savefmt.pop(
        kind, rng.randrange(1, 900000), rng.randrange(80, 90000),
        culture=rng.choice(CULTURES), religion=rng.choice(RELIGIONS),
        literacy=rng.random(), life=rng.random(), nested_id=True,
        extra=["money=%.5f" % rng.uniform(0, 9000),
               "con=%.5f" % (rng.random() * 4),
               "mil=%.5f" % (rng.random() * 6),
               "bank=%.5f" % rng.uniform(0, 500)],
        blocks=[("ideology", ["\t\t\t%d=%.5f" % (i, rng.random())
                              for i in range(1, 7)]),
                ("issues", ["\t\t\t%d=%.5f" % (i, rng.random())
                            for i in range(1, 9)])])


def a_province(rng, pid):
    pops = [a_pop(rng, kind, pid)
            for kind in rng.sample(POPS, rng.randrange(4, 10))]
    return lines(savefmt.province(
        pid, owner=tag_for(rng.randrange(40)), pops=pops,
        name="Province %d" % pid,
        extra=['controller="%s"' % tag_for(rng.randrange(40)),
               'core="%s"' % tag_for(rng.randrange(40)),
               "garrison=%.3f" % (rng.random() * 100),
               "life_rating=%d" % rng.randrange(10, 40),
               "railroad=", "{", "\tlevel=%d" % rng.randrange(0, 6), "}"]))


def a_country(rng, tag):
    regiments = []
    for i in range(rng.randrange(3, 30)):
        regiments += savefmt.nest(
            "regiment", ['\t\t\tname="%d Brigade"' % i,
                         "\t\t\ttype=%s" % rng.choice(UNITS),
                         "\t\t\tcount=%d" % rng.randrange(1000, 3000),
                         "\t\t\tstrength=%.3f" % rng.random()], 2)
    return lines(savefmt.country(
        tag, culture=rng.choice(CULTURES), religion=rng.choice(RELIGIONS),
        techs=[("tech_%d" % i, rng.random())
               for i in range(rng.randrange(20, 90))],
        inventions=[rng.randrange(1, 2000)
                    for _ in range(rng.randrange(20, 200))],
        extra=["prestige=%.3f" % rng.uniform(0, 300),
               "money=%.5f" % rng.uniform(0, 9e5),
               "badboy=%.3f" % (rng.random() * 25),
               "conscription=mandatory_service"],
        blocks=[("stockpile", ["\t\t%s=%.5f" % (g, rng.uniform(0, 5000))
                               for g in GOODS]),
                ("army", ['\t\tname="Army"'] + regiments)]))


def a_campaign(one, folder, months, tag="SWE"):
    """
    One save turned into a campaign of monthly ones, dated in order.

    The header is the only thing that has to differ, and it is the first
    line, so this rewrites that and copies the rest -- which is the point:
    what a long campaign costs the analyzer is the *number* of saves, not
    what is in them. A thousand of these is what a century of monthly
    autosaves looks like from the outside, and it is how the scaling gets
    checked without owning a century of them.
    """
    raw = open(one, "rb").read()
    rest = raw[raw.index(b"\n", raw.index(b'date="')):]
    os.makedirs(folder, exist_ok=True)
    made = 0
    for year in range(1836, 1836 + months // 12 + 2):
        for month in range(1, 13):
            if made >= months:
                return made
            name = "%s%04d_%02d_01.v2" % (tag, year, month)
            with open(os.path.join(folder, name), "wb") as fh:
                fh.write(('date="%d.%d.1"' % (year, month)).encode("latin-1"))
                fh.write(rest)
            made += 1
    return made


def main():
    ap = argparse.ArgumentParser(description="Write a save-shaped file.")
    ap.add_argument("path")
    ap.add_argument("--mb", type=float, default=25.0,
                    help="how big to make it (default: %(default)s)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--campaign", type=int, metavar="MONTHS",
                    help="also write this many monthly saves, dated in "
                         "order, into a folder beside `path` -- a long "
                         "campaign to measure the analyzer against")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    want = int(args.mb * 1024 * 1024)

    with open(args.path, "w", encoding="latin-1", newline="") as fh:
        fh.write(lines(savefmt.head(
            "1881.3.24", player="SWE",
            flags=("the_great_trek", "crimean_war_has_begun", "MozartFest1838",
                   "sonderbund_crisis", "risorgimento_started",
                   "opium_war_started"))
            + ["start_pop_index=152437"]))

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

    if args.campaign:
        folder = os.path.splitext(args.path)[0] + "-campaign"
        made = a_campaign(args.path, folder, args.campaign)
        print("wrote %d monthly saves into %s (%.1f GB)"
              % (made, folder, made * written / 1073741824.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())

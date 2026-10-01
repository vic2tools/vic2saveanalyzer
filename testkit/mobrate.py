#!/usr/bin/env python3
"""
The mobilisation rate rule, which two paths have to agree about.

A nation's mobilisation size decides how many brigades the report says it
could raise, and it comes out of `modrules.rate_for`: the sum of every
technology, invention, national value, reform and triggered modifier the
mod grants it, floored at zero.

The subtle part is what an empty sum means. It means **zero** -- an
uncivilized nation has no technology or invention granting mobilisation
size, and in IGoR no national value grants it either. It does not mean
"unknown, use the command line". The command-line rate is only for a run
with no mod at all.

Getting that backwards is a bug this codebase has had twice. The second
time, `--explain-mob-pool` wrote `rate_for(...) or args.mob_rate`, and
because `--mobilisation-size` defaults to 1.0, it printed **100%** and a
matching brigade ceiling for every nation the report itself scored at
**0%**. It survived because the only campaign it was ever run against had
no uncivilized nation in it, and `smoke.py` only ever asks about ENG.

    python3 testkit/mobrate.py

A synthetic mod and one save with a nation for each case a real campaign
does not happen to contain, run through the analyzer with
`--mobilisation-size 1.0` -- the command-line rate that must never rescue a
mod run -- and every nation's rate read back out of the table, and out of
`--explain-mob`, which has to explain the same number.
"""

import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "testkit"))

import matching                                            # noqa: E402
import savefmt                                             # noqa: E402

TECHS = """folder = army_tech
flintlock_rifles = {
	area = army_tech
	year = 1836
	cost = 100
	mobilisation_size = 0.03
}
a_tech = {
	area = army_tech
	year = 1836
	cost = 100
	mobilisation_size = 0.05
}
china_nerf = {
	area = army_tech
	year = 1836
	cost = 100
	mobilisation_size = -1.0
}
"""

# A trigger asking whether the nation is at war, which has to be asked of
# the war's sides as they stand -- not of who the history says joined.
TRIGGERED = """war_footing = {
	icon = 1
	trigger = {
		war = yes
	}
	mobilisation_size = 0.05
}
"""

# (tag, what it holds, its rate, why)
NATIONS = [
    ("ZUL", {"civilized": False}, 0.0,
     "uncivilized and granted nothing: an empty sum is zero, not unknown -- "
     "the case that once printed 100%, the command line's rate"),
    ("ENG", {"techs": ["flintlock_rifles"]}, 0.08,
     "a technology's 3% and the war's 5%: the war lists it as an attacker"),
    ("CHI", {"techs": ["a_tech", "china_nerf"]}, 0.0,
     "5% and -100% is floored at nought, not wrapped"),
    ("FRA", {}, 0.05, "at war: the war lists it as a defender"),
    ("SPA", {}, 0.05, "at war: listed as an attacker, put in by hand with no join"),
    ("GER", {}, 0.0, "not at war: it joined and made a separate peace"),
]

WAR = ["active_war=", "{", '\tname="The Merged War"', "\thistory=", "\t{",
       "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_attacker="ENG"', "\t\t}",
       "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_defender="GER"', "\t\t}",
       "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_defender="FRA"', "\t\t}",
       "\t\t1869.9.1=", "\t\t{", '\t\t\trem_defender="GER"', "\t\t}",
       "\t}",
       '\tattacker="ENG"', '\tattacker="SPA"', '\tdefender="FRA"',
       '\toriginal_attacker="ENG"', '\toriginal_defender="GER"',
       '\taction="1869.5.1"', "}"]


def a_world(holding):
    """(the mod, a folder of two saves a year apart)."""
    tags = [t for t, _h, _r, _w in NATIONS]
    mod = matching.a_mod_in_a_game(holding, "mod", tags=tags, pop_per_regiment=1000)
    with open(os.path.join(mod, "technologies", "army_tech.txt"), "w") as fh:
        fh.write(TECHS)
    with open(os.path.join(mod, "common", "triggered_modifiers.txt"), "w") as fh:
        fh.write(TRIGGERED)
    saves = os.path.join(holding, "saves")
    os.makedirs(saves)
    for n, date in enumerate(("1870.1.1", "1871.1.1")):
        parts = [savefmt.head(date)]
        for pid, (tag, _h, _r, _w) in enumerate(NATIONS, 1):
            parts.append(savefmt.province(pid, tag, [savefmt.pop("farmers", pid, 60000)]))
        for pid, (tag, holds, _r, _w) in enumerate(NATIONS, 1):
            country = savefmt.country(tag, capital=pid, techs=holds.get("techs", ()),
                                      inventions=[1])
            if holds.get("civilized") is False:
                country[country.index("\tcivilized=yes")] = "\tcivilized=no"
            parts.append(country)
        parts.append(WAR)
        savefmt.write(os.path.join(saves, "s%d.v2" % n), *parts)
    return mod, saves


def main():
    holding = tempfile.mkdtemp(prefix="vic2mobrate")
    wrong = []
    try:
        mod, saves = a_world(holding)
        out = os.path.join(holding, "out")
        env = dict(os.environ, TMPDIR=holding)
        run = [sys.executable, os.path.join(HERE, "vic2_analyzer.py"), saves, "--mod-path", mod,
               "--out", out, "--no-cache", "-q", "--mobilisation-size", "1.0"]
        done = subprocess.run(run, cwd=HERE, env=env, capture_output=True, text=True)
        if done.returncode:
            print("the run failed:\n" + (done.stdout + done.stderr)[-2000:])
            return 1
        with open(os.path.join(out, "nations_timeseries.csv"), newline="") as fh:
            rows = list(csv.DictReader(fh))
        last = max(r["date"] for r in rows)
        rates = {r["tag"]: float(r["mobilisation_size"]) for r in rows if r["date"] == last}
        width = max(len(t) for t, _h, _r, _w in NATIONS)
        for tag, _holds, want, why in NATIONS:
            got = rates.get(tag)
            said = subprocess.run(run + ["--explain-mob", tag], cwd=HERE, env=env,
                                  capture_output=True, text=True).stdout
            total = re.search(r"TOTAL[^\n%]*?\s(-?[\d.]+)%", said)
            explained = float(total.group(1)) / 100 if total else None
            bad = []
            if got is None or abs(got - want) > 1e-9:
                bad.append("%s: the report gave %s, where %.2f%% is right -- %s"
                           % (tag, got, want * 100, why))
            if explained is None or got is None or abs(explained - got) > 1e-9:
                bad.append("%s: --explain-mob explains %s where the report shows %s"
                           % (tag, "nothing" if explained is None else "%.2f%%" % (explained * 100),
                              got))
            print("  %-*s %s   %s" % (width, tag, "ok  " if not bad else "FAIL",
                                      "%.2f%%" % (got * 100) if got is not None else "-"))
            wrong += bad
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("the rate means the same thing everywhere it is asked for")
    return 0


if __name__ == "__main__":
    sys.exit(main())

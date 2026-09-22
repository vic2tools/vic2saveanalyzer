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

Synthetic nations and a synthetic mod, so the cases a real campaign does
not happen to contain can be asked about directly. Nothing here needs a
save file or a mod folder.
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def a_nation(**over):
    """A blank nation with whatever the case needs written over it."""
    import nation
    import v2parse
    v2parse.register_pop_types([])
    nat = nation.blank_nation()
    nat.update(tag="ZUL", tech_list=[], invention_ids=[], civilized="no",
               primary_culture="zulu", government="absolute_monarchy",
               modifiers=[], reforms={}, nationalvalue="")
    nat.update(over)
    return nat


def a_mod(**over):
    """The smallest mod `rate_for` will read."""
    mod = {"tech_mob": {}, "invention_rules": {}, "event_mob": {},
           "nv_mob": {}, "triggered_mob": [], "reform_mob": {},
           "static_mob": {}, "invention_sequence": [], "index_base": None,
           "technologies": frozenset(), "modifier_impacts": {},
           "mob_impacts": {}}
    mod.update(over)
    return mod


CASES = []


def case(name):
    def keep(fn):
        CASES.append((name, fn))
        return fn
    return keep


@case("no mod at all: the command line is the only source")
def _(rate_for):
    got = rate_for(a_nation(), None, None, None, 0.05)
    return got, 0.05, "without a mod there is nothing else to go on"


@case("a mod, and nothing grants the nation anything")
def _(rate_for):
    got = rate_for(a_nation(), a_mod(), set(), None, 1.0)
    return got, 0.0, ("an empty contribution list is zero, not unknown -- "
                      "this is the case that printed 100%")


@case("a mod, and one technology grants 3%")
def _(rate_for):
    nat = a_nation(civilized="yes", tech_list=["flintlock_rifles"])
    mod = a_mod(tech_mob={"flintlock_rifles": 0.03})
    return rate_for(nat, mod, set(), None, 1.0), 0.03, "the sum of one thing"


@case("contributions below zero are floored, not wrapped")
def _(rate_for):
    nat = a_nation(civilized="yes", tech_list=["a_tech", "china_nerf"])
    mod = a_mod(tech_mob={"a_tech": 0.05, "china_nerf": -1.0})
    return rate_for(nat, mod, set(), None, 1.0), 0.0, \
        "IGoR nerfs China by -100 and the engine does not pay out negative"


@case("the fallback never rescues a mod run")
def _(rate_for):
    # The whole bug in one line: a mod is present, the sum is zero, and the
    # command line says 100%. The answer is zero.
    got = rate_for(a_nation(), a_mod(), set(), None, 1.0)
    return got, 0.0, "a mod run answers from the mod, whatever the flag says"


def both_paths_agree():
    """
    [what went wrong] when the report's rate and the diagnostic's differ.

    They are the same call now. They were not, and nothing noticed,
    because the two live in different modules and only one of them is
    reachable from a campaign that has an uncivilized nation in it.
    """
    import explain
    import modrules
    import vic2_analyzer

    wrong = []
    src = open(explain.__file__).read()
    if "or args.mob_rate" in src:
        wrong.append("explain.py still falls back with `or args.mob_rate`, "
                     "which turns a real zero into the command-line rate")
    if hasattr(vic2_analyzer, "mob_rate"):
        wrong.append("vic2_analyzer.mob_rate is back: a second definition of "
                     "the rule that can drift from modrules.rate_for, which "
                     "is exactly how this broke")
    if not hasattr(modrules.rate_for, "__call__"):
        wrong.append("modrules.rate_for is gone")
    return wrong


def main():
    from modrules import rate_for

    width = max(len(n) for n, _ in CASES)
    wrong = []
    for name, fn in CASES:
        got, want, why = fn(rate_for)
        ok = abs(got - want) < 1e-9
        print("  %-*s %s   %.2f%%" % (width, name, "ok  " if ok else "FAIL",
                                      got * 100))
        if not ok:
            wrong.append("%s: got %.4f, wanted %.4f -- %s"
                         % (name, got, want, why))

    said = both_paths_agree()
    print("  %-*s %s" % (width, "one definition of the rule, not two",
                         "ok" if not said else "FAIL"))
    wrong += said

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

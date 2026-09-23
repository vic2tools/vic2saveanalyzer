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
    import readsave
    readsave.PLAIN.apply()
    nat = nation.blank_nation()
    nat.update(tag="ZUL", tech_list=[], invention_ids=[], civilized="no",
               primary_culture="zulu", government="absolute_monarchy",
               modifiers=[], reforms={}, nationalvalue="")
    nat.update(over)
    return nat


def a_mod(**over):
    """
    The smallest mod `rate_for` will read.

    Built through `Mod` rather than as a dict, so a field this forgets is a
    failure here and not a wrong number somewhere downstream. The indices
    are decoded against no nations, which is how a mod that has been asked
    and could not tell differs from one nobody asked.
    """
    import mod_reader
    blank = {name: () for name in mod_reader.MOD_FIELDS}
    blank.update(path="", tech_count=0, invention_count=0,
                 tech_mob={}, invention_rules={}, event_mob={}, nv_mob={},
                 triggered_mob=[], reform_mob={}, static_mob={},
                 invention_sequence=[], technologies=frozenset(),
                 modifier_impacts={}, mob_impacts={}, defines={})
    blank.update(over)
    mod = mod_reader.Mod(**blank)
    mod.decode_indices([])
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


def undecoded_indices_refuse():
    """
    [what went wrong] when a mod is asked before its indices are decoded.

    A save writes each nation's inventions as bare numbers into an array
    the engine builds at load time. Which number means which invention is
    only decidable against a save, so a freshly loaded mod does not know --
    and used to say so with `index_base = None`, which is also what it says
    when the indices have been checked and do not decode.

    The two are not the same answer and the difference is a number. Decoded,
    a nation's mobilisation size counts the inventions the save says it
    rolled. Undecodable, `breakdown` falls back to every invention whose
    requirements the nation meets, which its own comment calls an upper
    bound that "overstates nations with poor luck". So a caller that simply
    forgot to decode got the upper bound, silently, for every nation.

    Two callers remembered. Nothing made a third, and nothing would have
    said so. Now the mod refuses the question until it has been asked.
    """
    import mod_reader
    import modrules

    wrong = []
    blank = {name: () for name in mod_reader.MOD_FIELDS}
    blank.update(path="", tech_count=0, invention_count=0, tech_mob={},
                 invention_rules={}, event_mob={}, nv_mob={},
                 triggered_mob=[], reform_mob={}, static_mob={},
                 invention_sequence=[], technologies=frozenset(),
                 modifier_impacts={}, mob_impacts={}, defines={})
    fresh = mod_reader.Mod(**blank)
    if fresh.indices_read:
        wrong.append("a mod says its indices are decoded before anyone has "
                     "decoded them")
    try:
        modrules.rate_for(a_nation(civilized="yes"), fresh, set(), None, 1.0)
    except RuntimeError:
        pass
    else:
        wrong.append("a mod nobody decoded answered anyway, which is the "
                     "upper bound served as though it were the real count")

    # And the other case really is an answer: asked, and it does not decode.
    asked = mod_reader.Mod(**blank)
    asked.decode_indices([])
    if not asked.indices_read:
        wrong.append("decode_indices ran and the mod still says nobody asked")
    if asked.index_base is not None:
        wrong.append("nothing to decode against came back as a base anyway")
    try:
        modrules.rate_for(a_nation(civilized="yes"), asked, set(), None, 1.0)
    except RuntimeError:
        wrong.append("a mod that was asked and could not tell refuses the "
                     "question instead of falling back, so a campaign whose "
                     "indices do not decode cannot be read at all")
    return wrong


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


def at_war_is_who_is_fighting():
    """
    [what went wrong] when "at war" is not who the war says is in it now.

    A trigger's `war = yes` is asked of the war's current sides, which the
    war block lists outright. It used to be answered from the history's
    joins, which is a different list twice over: a nation that made a
    separate peace keeps its join, and one put into the war by hand -- in
    this campaign the host merged two wars, and seven nations, the player's
    among them, have no join at all -- never had one. The save here has one
    of each: GER joined and left, SPA was never logged joining.
    """
    import shutil
    import tempfile
    sys.path.insert(0, os.path.join(HERE, "testkit"))
    import explain
    import readsave
    import savefmt

    readsave.PLAIN.apply()
    holding = tempfile.mkdtemp(prefix="vic2atwar")
    try:
        path = savefmt.write(
            os.path.join(holding, "war.v2"),
            savefmt.head("1870.1.1"),
            savefmt.province(1, "ENG", [savefmt.pop("farmers", 1, 9000)]),
            savefmt.country("ENG"),
            ["active_war=", "{", '\tname="The Merged War"', "\thistory=", "\t{",
             "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_attacker="ENG"', "\t\t}",
             "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_defender="GER"', "\t\t}",
             "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_defender="FRA"', "\t\t}",
             "\t\t1869.9.1=", "\t\t{", '\t\t\trem_defender="GER"', "\t\t}",
             "\t}",
             '\tattacker="ENG"', '\tattacker="SPA"', '\tdefender="FRA"',
             '\toriginal_attacker="ENG"', '\toriginal_defender="GER"',
             '\taction="1869.5.1"', "}"])
        meta, _nations = readsave.analyze_save(path, verbose=False)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    got = sorted(explain.save_world(meta, a_mod())["at_war"])
    if got != ["ENG", "FRA", "SPA"]:
        return ["at war: %s, where the war lists ENG, SPA and FRA -- GER has "
                "made peace and SPA was put in by hand" % " ".join(got)]
    return []


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

    said = at_war_is_who_is_fighting()
    print("  %-*s %s" % (width, "at war is who the war lists now",
                         "ok" if not said else "FAIL"))
    wrong += said

    said = undecoded_indices_refuse()
    print("  %-*s %s" % (width, "a mod nobody decoded refuses to guess",
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

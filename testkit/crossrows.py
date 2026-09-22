#!/usr/bin/env python3
"""
`--cross` and the report, measuring the same campaign.

`--cross` reads several campaigns at once, puts a block comparing them into
the report, and then builds the rest of that report out of the largest of
them. The primary campaign is therefore measured twice on one page -- and
for a long time the two measurements were made by two copies of one recipe
that had quietly drifted apart in five places.

The worst was the regiment size. The cross copy never applied the mod's
POP_SIZE_PER_REGIMENT, so a nation's brigades were divided by the vanilla
3000 in the cross block and by the mod's own number in the chart directly
above it, with nothing on the page to say which was which. It also
overrode `--mob-types` where the report deferred to it; it read the mod's
pop list while parsing and the command line's while counting, which is two
lists deciding one number; it counted only `human=yes` as a player, so
`--player-nations` and the save's own `player=` went unread; and it dropped
every nation under one person, where the report keeps them.

    python3 testkit/crossrows.py

Two campaigns under two mods that disagree about every one of those,
built from `matching.a_mod` and `savefmt`, so nothing here needs a real
save folder or a real mod. The real program is then run once per case with
the finishing watched, because what is being checked is not what a function
returns on its own -- it is that two callers ask it the same question.
"""

import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import matching                                            # noqa: E402
import savefmt                                             # noqa: E402
import vic2_analyzer as vic2                               # noqa: E402
import nation                                               # noqa: E402
from mod_reader import load_mod                             # noqa: E402


# The mod alpha was played on. A regiment costs a third of what vanilla
# charges, and `serfs` are a poor stratum the vanilla list has never heard
# of -- so a run that falls back to the built-in defaults gets both the
# divisor and the eligible pops wrong, and says so in the brigade count.
ALPHA_REGIMENT = 1000
BETA_REGIMENT = 5000
MOD_POPS = matching.POPS + ["serfs"]
RATE = 0.5


def a_campaign_save(path, date, scale):
    """
    One save with nothing a person marked as theirs.

    No `human=yes` anywhere, which is the ordinary case for a
    single-player save and the one that separates the two readings: the
    report falls back to the save's own `player=`, and the cross path used
    to fall back to nobody.

    PRU holds one province and nobody in it, so it has no people at all.
    The report measures it -- `--min-pop` defaults to nought -- and the
    cross path used to raise that floor to one behind the caller's back.
    The province is the point: without it PRU has neither land nor people,
    which is what `analyze_save` drops as a released-nation stub, and the
    `--min-pop` case had nothing to measure either way.
    """
    def people(pid, kinds):
        out = []
        for i, (kind, size, culture) in enumerate(kinds):
            out.append(savefmt.pop(kind, pid * 100 + i, int(size * scale),
                                   culture=culture,
                                   religion="protestant"
                                   if culture == "british" else "catholic"))
        return out

    parts = [savefmt.head(date, player="ENG")]
    parts.append(savefmt.province(1, "ENG", people(1, [
        ("farmers", 12000, "british"), ("labourers", 7000, "british"),
        ("serfs", 3500, "british"), ("soldiers", 2000, "british")])))
    parts.append(savefmt.province(2, "ENG", people(2, [
        ("craftsmen", 9000, "british"), ("farmers", 4500, "british")])))
    # Irish under English rule: poor, mobilizable by type, and of no
    # accepted culture, so nothing may count them.
    parts.append(savefmt.province(3, "ENG", people(3, [
        ("farmers", 2500, "irish")])))
    parts.append(savefmt.province(4, "FRA", people(4, [
        ("farmers", 11000, "french"), ("serfs", 6000, "french")])))
    parts.append(savefmt.province(5, "FRA", people(5, [
        ("labourers", 5000, "french")])))
    # Prussia's one province, with nobody in it. It has to hold *land* to be
    # measured at all: `analyze_save` drops a tag with neither land nor people
    # as a released-nation stub, so the PRU this check used to build -- a
    # country block and nothing else -- never reached either path, and the
    # `--min-pop` case below had no subject. With a province and no pops it
    # survives that filter and is then exactly what `--min-pop 0` is about: a
    # nation of nought people that the caller has asked to see.
    parts.append(savefmt.province(6, "PRU", []))

    parts.append(savefmt.country("ENG", techs=matching.TECHS, inventions=[1]))
    parts.append(savefmt.country("FRA", culture="french", capital=4,
                                 techs=matching.TECHS[:2], inventions=[1]))
    parts.append(savefmt.country("PRU", culture="prussian", capital=1))
    return savefmt.write(path, *parts)


def a_world(holding):
    """Two campaigns, two mods, and the folder that holds them both."""
    mod_a = matching.a_mod(os.path.join(holding, "mod-alpha"),
                           pops=MOD_POPS,
                           pop_per_regiment=ALPHA_REGIMENT, mob_size=RATE)
    mod_b = matching.a_mod(os.path.join(holding, "mod-beta"),
                           pop_per_regiment=BETA_REGIMENT, mob_size=RATE)
    parent = os.path.join(holding, "campaigns")
    alpha = os.path.join(parent, "alpha")
    beta = os.path.join(parent, "beta")
    os.makedirs(alpha)
    os.makedirs(beta)
    for i, date in enumerate(("1870.1.1", "1875.1.1", "1880.1.1")):
        a_campaign_save(os.path.join(alpha, "a%d.v2" % i), date, 1.0 + i * 0.1)
    for i, date in enumerate(("1871.1.1", "1876.1.1")):
        a_campaign_save(os.path.join(beta, "b%d.v2" % i), date, 0.9 + i * 0.1)
    return parent, mod_a, mod_b


def watched_run(argv):
    """
    One real run, with every finishing it does written down.

    `finish_nations` is the one place a parsed save becomes numbers, so
    wrapping it catches both callers -- the cross path through
    `campaign_rows`, the report path through `_finish_save` -- without this
    check having to rebuild either caller's setup and inherit the very drift
    it is here to notice.

    `-j 1` is not about speed. The finishing normally happens out in a
    worker process, where a wrapper installed here would never be called at
    all; on one core it happens in this interpreter.
    """
    seen = {"cross": [], "report": []}
    inside = []

    real_finish = vic2.finish_nations
    real_rows = vic2.campaign_rows

    def watch_finish(meta, nations, spec):
        out = real_finish(meta, nations, spec)
        where = "cross" if inside else "report"
        seen[where].append(
            (meta.get("date"), spec,
             {tag: done for tag, done in out.items()
              if vic2.kept_by(spec, tag, done)}))
        return out

    def watch_rows(parsed, mod, args, wanted=None):
        inside.append(True)
        try:
            return real_rows(parsed, mod, args, wanted)
        finally:
            inside.pop()

    argv_was, out_was = sys.argv, sys.stdout
    vic2.finish_nations = watch_finish
    vic2.campaign_rows = watch_rows
    try:
        sys.argv = ["vic2_analyzer.py"] + argv
        sys.stdout = io.StringIO()
        try:
            vic2.main()
        except SystemExit as exc:
            if exc.code:
                raise AssertionError("the run stopped: %s" % exc.code)
    finally:
        vic2.finish_nations = real_finish
        vic2.campaign_rows = real_rows
        sys.argv, sys.stdout = argv_was, out_was
    return seen


def flatten(entries, dates):
    """{(date, tag): finished nation} for the saves of one campaign."""
    out = {}
    for date, _spec, kept in entries:
        if date not in dates:
            continue
        for tag, done in kept.items():
            out[(date, tag)] = done
    return out


def plain(value):
    """A Counter and the dict it was sent as are the same answer."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


# Everything that reaches a chart or a CSV column. `date` and `year` are
# built around a nation rather than held by one, so they are not here.
COLUMNS = [c for c in vic2.BASE_COLUMNS
           if c not in ("date", "year", "tag")] + ["pop_by_type",
                                                   "accepted_cultures"]


def rows_agree(cross, report):
    """[what disagreed] between the two readings of one campaign."""
    wrong = []
    if set(cross) != set(report):
        only_cross = sorted(set(cross) - set(report))
        only_report = sorted(set(report) - set(cross))
        if only_cross:
            wrong.append("the cross block measures %d nation-saves the report "
                         "does not, such as %s"
                         % (len(only_cross), only_cross[:4]))
        if only_report:
            wrong.append("the report measures %d nation-saves the cross block "
                         "does not, such as %s"
                         % (len(only_report), only_report[:4]))
    for key in sorted(set(cross) & set(report)):
        mine, theirs = cross[key], report[key]
        for col in COLUMNS:
            if col not in mine or col not in theirs:
                continue
            if plain(mine[col]) != plain(theirs[col]):
                wrong.append(
                    "%s %s: %s is %r through --cross and %r through the report"
                    % (key[0], key[1], col,
                       plain(mine[col]), plain(theirs[col])))
    return wrong


SPEC_FIELDS = ("rate", "pop_per_regiment", "mob_types", "include_occupied",
               "player_nations", "wanted", "min_pop")


def specs_agree(cross, report):
    """[what disagreed] between the two specs the same campaign was read on."""
    wrong = []
    for field in SPEC_FIELDS:
        mine, theirs = getattr(cross, field), getattr(report, field)
        if mine != theirs:
            wrong.append("the two paths disagree about %s: %r against %r"
                         % (field, mine, theirs))
    if sorted(cross.live or ()) != sorted(report.live or ()):
        wrong.append("the two paths disagree about which inventions are "
                     "obtainable")
    mine = cross.mod.path if cross.mod else None
    theirs = report.mod.path if report.mod else None
    if mine != theirs:
        wrong.append("the two paths read different mods: %r against %r"
                     % (mine, theirs))
    return wrong


ALPHA_DATES = {"1870.1.1", "1875.1.1", "1880.1.1"}


def measured(rows):
    """The tags this reading actually measured."""
    return {tag for _date, tag in rows}


def playing(rows):
    """The tags this reading marked as run by a person."""
    return {tag for (_date, tag), nat in rows.items() if nat.get("is_player")}


# --- what each way of asking must actually have got -------------------------
#
# Comparing the two paths is most of this check, but on its own it is not
# enough, and for a while it was all there was. The four jobs merged the two
# paths into one `finish_nations` -- so a bug in what that one function does
# now moves *both* readings together, they go on agreeing, and a check that
# only compares them passes while the flag it is named after is ignored.
#
# Four of the five cases below were verified to do exactly that: the mod's
# pop list overriding `--mob-types`, `--player-nations` going unread, the
# save's own `player=` going unread, and the floor under `--min-pop` being
# raised to one, could each be put back with every case still printing `ok`.
# Only the regiment size was caught, because it was the only one asserting
# something about the answer rather than about the two paths matching.
#
# So each case now says what the run had to come back with. The comparison
# catches the two paths drifting apart again; these catch them being wrong
# together.


def must_be_the_mods_list(mod, spec, rows):
    """No `--mob-types`, so the mod's own poor strata decide it."""
    if set(spec.mob_types) != set(mod.mob_types):
        return ["the mod mobilizes %s but the run counted %s"
                % (sorted(mod.mob_types), sorted(spec.mob_types))]
    return []


def must_be_asked_for(*asked):
    """`--mob-types` was given, so it wins over whatever the mod says."""
    def check(mod, spec, rows):
        if set(spec.mob_types) != set(asked):
            return ["--mob-types asked for %s and the run counted %s"
                    % (sorted(asked), sorted(spec.mob_types))]
        if set(asked) == set(mod.mob_types):
            return ["this case no longer tests anything: the mod's own list "
                    "is now the same as the one asked for"]
        return []
    return check


def must_play(*tags):
    """Who the run decided was a person, and nobody else."""
    def check(mod, spec, rows):
        got = playing(rows)
        if got != set(tags):
            return ["the run played %s; it should have played %s"
                    % (sorted(got) or "nobody", sorted(tags))]
        return []
    return check


def must_measure_landless(mod, spec, rows):
    """
    `--min-pop 0` means a nation of nought people is still measured.

    PRU holds one province and nobody at all, which is the only shape that
    can tell a floor of nought from a floor of one.
    """
    if spec.min_pop != 0:
        return ["--min-pop 0 was asked for and the run used %r" % (spec.min_pop,)]
    if "PRU" not in measured(rows):
        return ["PRU has a province and no people, and --min-pop is nought, "
                "so it should have been measured; the run measured %s"
                % sorted(measured(rows))]
    return []


def must_use_regiment(size):
    """
    `--pop-per-regiment` was given, so it wins -- even at the vanilla value.

    The mod alpha sets 1000. Asking for 3000 used to be indistinguishable
    from not asking at all, because "the caller left it alone" was decided
    by comparing the value against the built-in default rather than by
    whether the flag was there. So the one run that most wants to be told
    3000 -- a modded campaign held against vanilla numbers -- was the one
    run that could not ask for it.
    """
    def check(mod, spec, rows):
        if spec.pop_per_regiment != size:
            return ["--pop-per-regiment %d was asked for and the run divided "
                    "by %d" % (size, spec.pop_per_regiment)]
        if size == ALPHA_REGIMENT:
            return ["this case no longer tests anything: the mod's own "
                    "regiment size is now the one being asked for"]
        return []
    return check


def must_drop_landless(mod, spec, rows):
    """And the other side of it, so the floor cannot be removed altogether."""
    got = measured(rows)
    if "PRU" in got:
        return ["--min-pop 1000 was asked for and PRU, with no people at "
                "all, was measured anyway"]
    if not {"ENG", "FRA"} <= got:
        return ["--min-pop 1000 dropped nations it should have kept: %s"
                % sorted(got)]
    return []


def both(*checks):
    def check(mod, spec, rows):
        out = []
        for one in checks:
            out += one(mod, spec, rows)
        return out
    return check


def one_case(name, holding, extra, must):
    """[what went wrong] for one way of asking."""
    parent, mod_a, _mod_b = a_world(os.path.join(holding, name))
    out = os.path.join(holding, name, "out")
    seen = watched_run([
        parent, "--cross", "--primary", "alpha",
        "--campaign-mod", "alpha=" + mod_a,
        "--campaign-mod", "beta=" + os.path.join(holding, name, "mod-beta"),
        "--out", out, "--no-html", "--no-cache", "-j", "1", "-q"] + extra)

    if not seen["cross"] or not seen["report"]:
        return ["%s: the run finished %d saves through --cross and %d through "
                "the report; it should have done both"
                % (name, len(seen["cross"]), len(seen["report"]))]

    wrong = []
    cross_spec = next(spec for date, spec, _k in seen["cross"]
                      if date in ALPHA_DATES)
    report_spec = seen["report"][0][1]
    cross_rows = flatten(seen["cross"], ALPHA_DATES)
    wrong += specs_agree(cross_spec, report_spec)
    wrong += rows_agree(cross_rows, flatten(seen["report"], ALPHA_DATES))

    # And the mod's own numbers really did arrive, rather than both paths
    # agreeing on the same wrong ones. This is the shape the bug had: the
    # cross block divided by 3000 because nothing had told it otherwise.
    # Unless this case is the one asking for a regiment size of its own.
    if ("--pop-per-regiment" not in extra
            and cross_spec.pop_per_regiment != ALPHA_REGIMENT):
        wrong.append("%s: alpha was read with a regiment of %d people, not "
                     "the %d its mod's defines.lua sets"
                     % (name, cross_spec.pop_per_regiment, ALPHA_REGIMENT))
    # What this particular way of asking had to come back with. Both paths
    # are read through one function now, so agreeing is no longer evidence
    # that either is right.
    wrong += must(load_mod(mod_a), cross_spec, cross_rows)
    return ["%s: %s" % (name, w) for w in wrong]


CASES = [
    # Nobody is marked human in these saves, so the only thing left that can
    # say who was playing is the save's own `player=`, which is ENG. The
    # cross block used to fall back to nobody.
    ("as it comes", [], both(must_be_the_mods_list, must_play("ENG"),
                             must_measure_landless)),
    # The mod names five mobilizable pop types and the caller names one of
    # them. The report obeyed the caller and the cross block obeyed the mod.
    ("--mob-types honoured", ["--mob-types", "farmers"],
     must_be_asked_for("farmers")),
    # And one the mod's own list leaves out. Which pops are *read* out of a
    # save is settled once, when it is parsed, and which are *counted* is
    # settled again when it is finished -- so the two coming from different
    # places is a pool that is empty for no reason a number can show. The
    # cross path took the mod's list for the first and the caller's for the
    # second, and soldiers are in neither list by default.
    ("--mob-types outside the mod's list", ["--mob-types", "soldiers"],
     must_be_asked_for("soldiers")),
    # `--player-nations` overrides the lot, including the save's own player.
    # The cross block never asked, so it went on reading ENG.
    ("--player-nations honoured", ["--player-nations", "FRA"],
     must_play("FRA")),
    # A floor the cross block used to raise to one on its own, which drops
    # exactly the nations that have nobody in them.
    ("--min-pop honoured", ["--min-pop", "0"], must_measure_landless),
    # And the floor still works when it is asked for, so the case above
    # cannot be satisfied by having no floor at all.
    ("--min-pop excludes", ["--min-pop", "1000"], must_drop_landless),
    # The vanilla regiment size, asked for out loud, under a mod that sets
    # its own. Naming the value the program would have used anyway must not
    # read as saying nothing.
    ("--pop-per-regiment at the default",
     ["--pop-per-regiment", str(nation.POP_SIZE_PER_REGIMENT)],
     must_use_regiment(nation.POP_SIZE_PER_REGIMENT)),
]


def main():
    holding = tempfile.mkdtemp(prefix="vic2cross")
    wrong = []
    try:
        width = max(len(n) for n, _e, _m in CASES)
        for name, extra, must in CASES:
            said = one_case(name, holding, extra, must)
            print("  %-*s %s" % (width, name, "ok" if not said else "FAIL"))
            wrong += said
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("the cross block and the report measure the primary campaign "
          "the same way")
    return 0


if __name__ == "__main__":
    sys.exit(main())

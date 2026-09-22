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

    PRU holds no province, so it has no people at all. The report measures
    it -- `--min-pop` defaults to nought -- and the cross path used to
    raise that floor to one behind the caller's back.
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


def one_case(name, holding, extra):
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
    wrong += specs_agree(cross_spec, report_spec)
    wrong += rows_agree(flatten(seen["cross"], ALPHA_DATES),
                        flatten(seen["report"], ALPHA_DATES))

    # And the mod's own numbers really did arrive, rather than both paths
    # agreeing on the same wrong ones. This is the shape the bug had: the
    # cross block divided by 3000 because nothing had told it otherwise.
    if cross_spec.pop_per_regiment != ALPHA_REGIMENT:
        wrong.append("%s: alpha was read with a regiment of %d people, not "
                     "the %d its mod's defines.lua sets"
                     % (name, cross_spec.pop_per_regiment, ALPHA_REGIMENT))
    return ["%s: %s" % (name, w) for w in wrong]


CASES = [
    ("as it comes", []),
    # The mod names five mobilizable pop types and the caller names one of
    # them. The report obeyed the caller and the cross block obeyed the mod.
    ("--mob-types honoured", ["--mob-types", "farmers"]),
    # And one the mod's own list leaves out. Which pops are *read* out of a
    # save is settled once, when it is parsed, and which are *counted* is
    # settled again when it is finished -- so the two coming from different
    # places is a pool that is empty for no reason a number can show. The
    # cross path took the mod's list for the first and the caller's for the
    # second, and soldiers are in neither list by default.
    ("--mob-types outside the mod's list", ["--mob-types", "soldiers"]),
    # Nobody is marked human in these saves, so this is the only thing
    # that can say who was playing. The cross block never asked.
    ("--player-nations honoured", ["--player-nations", "FRA"]),
    # A floor the cross block used to raise to one on its own.
    ("--min-pop honoured", ["--min-pop", "0"]),
]


def main():
    holding = tempfile.mkdtemp(prefix="vic2cross")
    wrong = []
    try:
        width = max(len(n) for n, _e in CASES)
        for name, extra in CASES:
            said = one_case(name, holding, extra)
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

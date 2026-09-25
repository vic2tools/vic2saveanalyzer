#!/usr/bin/env python3
"""
Every source file must be able to make the report stale.

A finished run writes a stamp beside the report, and a later run that
matches it skips everything and says "Nothing has changed since this was
built." That is the difference between pressing Analyze and waiting, and
pressing Analyze and reading -- and it is also the most dangerous switch
in the program, because when it is wrong nothing looks wrong. The report
opens, every number in it is plausible, and every number in it is from
the last time somebody looked.

It has been wrong. The stamp used to hash a hand-written list of five
filenames. `modrules.py`, which decides every nation's mobilisation size,
was lifted out of `mod_reader.py` -- which was on that list -- and did not
inherit its place. Doubling every rate in it then changed nothing the
stamp could see, and the next run served the old report. Nothing in the
suite could catch that, because the suite tested that the skip *happens*
and never what it is keyed on.

So this checks the property rather than the list: touch any source file
the program has, and the stamp must move.

    python3 testkit/staleness.py

The touching happens to a **copy** of the program in a temp folder, never
to the real tree, so a failure here cannot leave the working copy edited.

Then the same question for `--cross`, which compares several campaigns and
builds the rest of the report from the largest. Its stamp covered only that
one: a new save in any other campaign was read, and then answered "nothing
has changed" with the old comparison. So two small campaigns are built, each
under its own mod, and the smaller one is given a save, and then its mod is
edited -- and each time the report has to be built again.

And last, a run that rewrites the files and does not finish. A table open
in Excel cannot be written on Windows, and that run used to die in a stack
trace after rewriting the report, leaving the previous run's stamp behind --
so the previous run's settings, asked for again, were answered with this
run's report. `--no-html` did the same without dying. Both have to leave
nothing for the next run to skip on, and the locked table has to be named
in a sentence.

And a table has to be from this run even when this run has nothing to put
in it: an empty one used to be skipped, and the last run's copy stayed in
the folder beside the new ones.

And the settings. The stamp used to hash fifteen of them by name, from a
list nothing checked -- taking `min_pop` off it passed every check there
was, and a later `--min-pop` would have been answered with the old report.
Each setting is now declared in `vic2_analyzer.Run` with whether it
changes the report, and this holds the declaration to account: every
setting that does moves the stamp, and every one that is left out is on a
list below that says why it may be.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Run inside the copy, so `report_stamp` hashes the copy's own folder.
INSIDE = r'''
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stamp


class Settings:
    """Whatever `report_stamp` asks for, answered with a default."""
    def __getattr__(self, name):
        return None


here = os.path.dirname(os.path.abspath(__file__))
saves = [os.path.join(here, "a.v2")]
with open(saves[0], "w") as fh:
    fh.write("date=\"1836.1.1\"\n")

args = Settings()
first = stamp.report_stamp(saves, args, "no-mod")
if not first:
    print("BLANK|the stamp came back empty, so nothing below means anything")
    raise SystemExit(0)

for name in sorted(os.listdir(here)):
    if not name.endswith(".py"):
        continue
    path = os.path.join(here, name)
    was = open(path, "rb").read()
    try:
        with open(path, "ab") as fh:
            fh.write(b"\n# touched\n")
        now = stamp.report_stamp(saves, args, "no-mod")
    finally:
        with open(path, "wb") as fh:
            fh.write(was)
    print("%s|%s" % ("MOVED" if now != first else "SAME", name))

# And the other direction: nothing touched, nothing moved.
print("%s|%s" % ("MOVED" if stamp.report_stamp(saves, args, "no-mod") != first
                 else "SAME", "(nothing touched)"))
'''


def cross_campaigns():
    """[what went wrong] in what makes a `--cross` report stale."""
    sys.path.insert(0, os.path.join(HERE, "testkit"))
    import matching
    import savefmt

    holding = tempfile.mkdtemp(prefix="vic2xstale")
    try:
        mods = {name: matching.a_mod(os.path.join(holding, "mod-" + name),
                                     pop_per_regiment=1000)
                for name in ("alpha", "beta")}
        parent = os.path.join(holding, "campaigns")

        def a_save(folder, n, year):
            os.makedirs(folder, exist_ok=True)
            savefmt.write(os.path.join(folder, "s%d.v2" % n),
                          savefmt.head("%d.1.1" % year),
                          savefmt.province(1, "ENG", [savefmt.pop(
                              "farmers", 100 + n, 20000 + 100 * n)]),
                          savefmt.country("ENG", techs=matching.TECHS))

        for n in range(3):
            a_save(os.path.join(parent, "alpha"), n, 1840 + n)
        for n in range(2):
            a_save(os.path.join(parent, "beta"), n, 1850 + n)
        out = os.path.join(holding, "out")
        env = dict(os.environ, TMPDIR=holding)

        def run():
            done = subprocess.run(
                [sys.executable, os.path.join(HERE, "vic2_analyzer.py"),
                 parent, "--cross", "--out", out, "--no-cache",
                 "--campaign-mod", "alpha=" + mods["alpha"],
                 "--campaign-mod", "beta=" + mods["beta"]],
                capture_output=True, text=True, cwd=HERE, env=env)
            if done.returncode:
                return None
            return "Nothing has changed" in done.stdout

        wrong = []
        steps = [("built once", None, False),
                 ("run again, nothing changed", None, True),
                 ("the smaller campaign gains a save",
                  lambda: a_save(os.path.join(parent, "beta"), 2, 1852), False),
                 ("run again, nothing changed", None, True),
                 ("the smaller campaign's mod is edited",
                  lambda: open(os.path.join(mods["beta"], "common",
                                            "defines.lua"), "a").write(
                      "-- edited\n"), False)]
        for what, change, skipped in steps:
            if change:
                change()
            said = run()
            if said is None:
                wrong.append("--cross failed outright after: %s" % what)
                break
            ok = said == skipped
            print("  --cross, %-38s %s" % (what, ("skipped" if said else
                                                  "rebuilt") if ok else
                                          "FAILED"))
            if not ok:
                wrong.append(
                    "--cross after %s: %s" % (what,
                    "answered \"nothing has changed\" with the old report"
                    if said else "rebuilt a report nothing had changed"))
        return wrong
    finally:
        shutil.rmtree(holding, ignore_errors=True)


def unfinished_runs():
    """[what went wrong] when a run rewrites the files and does not finish."""
    sys.path.insert(0, os.path.join(HERE, "testkit"))
    import savefmt

    holding = tempfile.mkdtemp(prefix="vic2ustale")
    try:
        saves = os.path.join(holding, "saves")
        os.makedirs(saves)
        for n in range(2):
            savefmt.write(
                os.path.join(saves, "s%d.v2" % n),
                savefmt.head("%d.1.1" % (1840 + n)),
                savefmt.province(1, "ENG", [savefmt.pop("farmers", 10, 20000)]),
                savefmt.province(2, "FRA", [savefmt.pop("farmers", 20, 20000,
                                                        culture="french")]),
                savefmt.country("ENG"),
                savefmt.country("FRA", culture="french", capital=2))
        out = os.path.join(holding, "out")
        table = os.path.join(out, "nations_timeseries.csv")
        env = dict(os.environ, TMPDIR=holding)

        def run(*extra):
            return subprocess.run(
                [sys.executable, os.path.join(HERE, "vic2_analyzer.py"), saves,
                 "--out", out, "--no-cache"] + list(extra),
                capture_output=True, text=True, cwd=HERE, env=env)

        wrong = []
        run("--tags", "ENG")
        # The lock, as far as this machine can make one: a table that cannot
        # be opened for writing, which is what Excel's lock is to Python.
        os.chmod(table, 0o444)
        if os.access(table, os.W_OK):
            os.chmod(table, 0o644)
            print("  a locked table: cannot make one here (running as root?)")
        else:
            try:
                locked = run()
            finally:
                os.chmod(table, 0o644)
            said = locked.stdout + locked.stderr
            if "Traceback" in said:
                wrong.append("a locked table ended the run in a stack trace")
            elif locked.returncode == 0 or "nations_timeseries.csv" not in said:
                wrong.append("a locked table was not named: %s"
                             % said.strip()[-120:])
            again = run("--tags", "ENG")
            fine = "Nothing has changed" not in again.stdout
            print("  %-48s %s" % ("a locked table, then the run before it again",
                                  "rebuilt" if fine else "FAILED"))
            if not fine:
                wrong.append("after a run that could not write a table, the "
                             "run before it was answered with that run's "
                             "report")
        run("--no-html")
        again = run("--tags", "ENG")
        fine = "Nothing has changed" not in again.stdout
        print("  %-48s %s" % ("--no-html, then the run before it again",
                              "rebuilt" if fine else "FAILED"))
        if not fine:
            wrong.append("after --no-html rewrote the tables, the run before "
                         "it was answered as if they were its own")
        return wrong
    finally:
        shutil.rmtree(holding, ignore_errors=True)


def leftover_tables():
    """[what went wrong] when a table in the folder is from an earlier run."""
    import csv
    sys.path.insert(0, os.path.join(HERE, "testkit"))
    import savefmt

    holding = tempfile.mkdtemp(prefix="vic2lstale")
    try:
        saves = os.path.join(holding, "saves")
        os.makedirs(saves)
        fleet = ('navy', ['\t\tname="Home Fleet"'] + savefmt.nest(
            "ship", ['\t\t\tname="Vasa"', "\t\t\ttype=frigate",
                     "\t\t\tstrength=100.000"], 2))
        for n in range(2):
            savefmt.write(
                os.path.join(saves, "s%d.v2" % n),
                savefmt.head("%d.1.1" % (1840 + n)),
                savefmt.province(1, "ENG", [savefmt.pop("farmers", 10, 20000)]),
                savefmt.province(2, "FRA", [savefmt.pop("farmers", 20, 20000,
                                                        culture="french")]),
                savefmt.country("ENG", blocks=[fleet]),
                savefmt.country("FRA", culture="french", capital=2))
        out = os.path.join(holding, "out")
        env = dict(os.environ, TMPDIR=holding)
        for extra in ([], ["--tags", "FRA"]):
            subprocess.run([sys.executable, os.path.join(HERE, "vic2_analyzer.py"),
                            saves, "--out", out, "--no-cache", "-q"] + extra,
                           capture_output=True, text=True, cwd=HERE, env=env)
        wrong = []
        for name in sorted(os.listdir(out)):
            if not name.endswith(".csv"):
                continue
            with open(os.path.join(out, name), newline="") as fh:
                rows = list(csv.DictReader(fh))
            others = sorted({r["tag"] for r in rows if r.get("tag") not in
                             (None, "FRA")})
            if others:
                wrong.append("%s still holds %s from the run before, beside "
                             "tables of FRA alone" % (name, " ".join(others)))
        print("  %-48s %s" % ("a rerun with nothing for one of the tables",
                              "FAILED" if wrong else "all from this run"))
        return wrong
    finally:
        shutil.rmtree(holding, ignore_errors=True)


# The settings allowed to stay out of the report stamp, and why. A setting
# declared as not changing the report and not named here is a failure: it
# has to be decided twice, once there and once here, before it can skip.
OUT_OF_STAMP = {
    "saves": "each save is hashed on its own, by path, size and time",
    "out": "where the report goes, not what it says",
    "check_inventions": "prints and exits; `asked` keeps it from skipping",
    "inventions": "prints and exits; `asked` keeps it from skipping",
    "explain_mob": "prints and exits; `asked` keeps it from skipping",
    "explain_mob_pool": "prints and exits; `asked` keeps it from skipping",
    "jobs": "how many cores read the saves",
    "no_cache": "a save read again is the same save",
    "rebuild": "asks for exactly the rebuild",
    "peek": "prints one save's shape and exits",
    "verify": "checks the saves and exits",
    "quiet": "what is printed, not what is written",
}


def the_settings_the_stamp_covers():
    """[what went wrong] in which settings the report stamp covers."""
    import dataclasses
    sys.path.insert(0, HERE)
    import run as settings
    import stamp

    wrong = []
    declared = dataclasses.fields(settings.Run)
    for setting in declared:
        if "report" not in setting.metadata:
            wrong.append("%s does not say whether it changes the report"
                         % setting.name)
    left_out = {f.name for f in declared if not f.metadata.get("report")}
    for name in sorted(left_out - set(OUT_OF_STAMP)):
        wrong.append("%s is left out of the report stamp, and nothing says it "
                     "may be -- a run that changes it would be answered with "
                     "the report made before" % name)

    def other(value):
        if isinstance(value, bool):
            return not value
        if isinstance(value, (int, float)):
            return value + 1
        if isinstance(value, tuple):
            return value + (("X", "Y"),)
        return "x" if value is None else value + "x"

    holding = tempfile.mkdtemp(prefix="vic2sstale")
    try:
        save = os.path.join(holding, "a.v2")
        open(save, "w").write('date="1836.1.1"\n')
        base = settings.Run(saves=holding)
        first = stamp.report_stamp([save], base, "no-mod")
        for setting in declared:
            if not setting.metadata.get("report"):
                continue
            moved = dataclasses.replace(
                base, **{setting.name: other(getattr(base, setting.name))})
            if stamp.report_stamp([save], moved, "no-mod") == first:
                wrong.append("changing %s does not move the report stamp, so "
                             "a run that changes it is answered with the old "
                             "report" % setting.name)
        old = sys.argv
        try:
            sys.argv = [old[0], holding]
            parsed = settings.Run.from_command_line(settings.command_line())
        finally:
            sys.argv = old
        if parsed != base:
            wrong.append("a Run with nothing set is not what the command line "
                         "makes with nothing given: %s" % sorted(
                             f.name for f in declared
                             if getattr(parsed, f.name) != getattr(base, f.name)))
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print("  %-48s %s" % ("every setting that changes the report moves it",
                          "FAILED" if wrong else "ok (%d of %d)" % (
                              len(declared) - len(left_out), len(declared))))
    return wrong


def main():
    holding = tempfile.mkdtemp(prefix="vic2stale")
    copy = os.path.join(holding, "program")
    os.makedirs(copy)
    try:
        for name in os.listdir(HERE):
            if name.endswith(".py"):
                shutil.copy2(os.path.join(HERE, name),
                             os.path.join(copy, name))
        driver = os.path.join(copy, "_stale_driver.py")
        with open(driver, "w") as fh:
            fh.write(INSIDE)
        # The driver is itself a .py in the folder, so it is one of the
        # files under test, which is fine and one more than we need.
        done = subprocess.run([sys.executable, driver], capture_output=True,
                              text=True, cwd=copy)
        if done.returncode:
            print("the stamp could not be taken at all:")
            print((done.stdout + done.stderr).strip()[-1500:])
            return 1

        deaf = []
        counted = 0
        for line in done.stdout.strip().splitlines():
            if "|" not in line:
                continue
            verdict, name = line.split("|", 1)
            if verdict == "BLANK":
                print("  %s" % name)
                return 1
            if name == "(nothing touched)":
                if verdict == "MOVED":
                    deaf.append("the stamp moved when nothing was touched, "
                                "so it can never skip anything")
                continue
            counted += 1
            if verdict == "SAME":
                deaf.append("editing %s does not change the stamp, so a run "
                            "after that edit serves the old report" % name)

        print("  %d source files, each touched in a copy of the program"
              % counted)
        print("  %-46s %s" % ("every one of them moves the stamp",
                              "FAILED" if deaf else "ok"))
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    deaf += cross_campaigns()
    deaf += unfinished_runs()
    deaf += leftover_tables()
    deaf += the_settings_the_stamp_covers()
    print()
    if deaf:
        print("PROBLEMS:")
        for one in deaf:
            print("  %s" % one)
        return 1
    print("nothing the program is made of can change behind the stamp's back")
    return 0


if __name__ == "__main__":
    sys.exit(main())

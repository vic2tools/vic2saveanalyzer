"""
What can make the report stale, and the stamp that has to notice.

A finished run writes a stamp beside the report, and a later run that
matches it skips everything and says "Nothing has changed since this was
built." That is the difference between pressing Analyze and waiting, and
pressing Analyze and reading -- and it is also the most dangerous switch
in the program, because when it is wrong nothing looks wrong. The report
opens, every number in it is plausible, and every number in it is from
the last time somebody looked.

It has been wrong. The stamp used to hash a hand-written list of five
source files, and a sixth that decided every nation's mobilisation size was
not on it. So this checks the property rather than the list. The stamp
names the program by the scanner's build id (`scanner/build.rs`): the build
script is compiled against a copy of the sources, every one of them is
edited in turn, and the id must move each time -- and not move when nothing
was.

    python3 testkit/staleness.py

Then the same question for `--cross`, which compares several campaigns and
builds the rest of the report from the largest. Its stamp covered only that
one: a new save in any other campaign was read, and then answered "nothing
has changed" with the old comparison. So two small campaigns are built, each
under its own mod, and the smaller one is given a save, and then its mod is
edited -- and each time the report has to be built again.

And a run that rewrites the files and does not finish. A table open in
Excel cannot be written on Windows, and that run used to die after
rewriting the report, leaving the previous run's stamp behind -- so the
previous run's settings, asked for again, were answered with this run's
report. `--no-html` did the same without dying. Both have to leave nothing
for the next run to skip on, and the locked table has to be named in a
sentence.

And a table has to be from this run even when this run has nothing to put
in it: an empty one used to be skipped, and the last run's copy stayed in
the folder beside the new ones.

And the settings. Each is declared in `run.Run` with whether it changes the
report, and the stamp hashes those by name. This holds the declaration to
account through real runs: a run that changes any setting declared to
change the report must be built again, and every setting left out is on a
list below that says why it may be.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def the_build_id_covers_every_source():
    """
    [what went wrong] in which files name the build. The build script is
    compiled on its own against a copy of the scanner's sources and run
    with each file edited in turn; the id it gives must move every time.
    """
    rustc = shutil.which("rustc") or os.path.expanduser("~/.cargo/bin/rustc")
    if not os.path.isfile(rustc):
        print("  the build id: no rustc here, so not checked")
        return []
    holding = tempfile.mkdtemp(prefix="vic2buildid")
    try:
        copy = os.path.join(holding, "tree")
        shutil.copytree(os.path.join(HERE, "scanner"), os.path.join(copy, "scanner"),
                        ignore=shutil.ignore_patterns("target"))
        shutil.copy2(os.path.join(HERE, "template.py"), os.path.join(copy, "template.py"))
        script = os.path.join(holding, "build")
        made = subprocess.run([rustc, "--edition", "2021", "-O", "-o", script,
                               os.path.join(copy, "scanner", "build.rs")],
                              capture_output=True, text=True,
                              env=dict(os.environ, CARGO_MANIFEST_DIR=os.path.join(copy, "scanner")))
        if made.returncode:
            return ["the build script would not compile on its own: %s" % made.stderr[-500:]]
        out_dir = os.path.join(holding, "out")
        os.makedirs(out_dir)

        def build_id():
            done = subprocess.run([script], capture_output=True, text=True,
                                  env=dict(os.environ, OUT_DIR=out_dir))
            found = [l.split("=", 2)[2] for l in done.stdout.splitlines()
                     if l.startswith("cargo:rustc-env=VIC2_BUILD_ID=")]
            return found[0] if found else None

        first = build_id()
        if not first:
            return ["the build script names no VIC2_BUILD_ID"]
        sources = [os.path.join(copy, "template.py")]
        for root, _dirs, names in os.walk(os.path.join(copy, "scanner")):
            # Cargo.lock pins the crates the scanner uses, and it uses none.
            sources += [os.path.join(root, n) for n in names if n != "Cargo.lock"]
        deaf = []
        for path in sorted(sources):
            with open(path, "rb") as fh:
                was = fh.read()
            try:
                with open(path, "ab") as fh:
                    fh.write(b"\n// touched\n")
                if build_id() == first:
                    deaf.append(os.path.relpath(path, copy))
            finally:
                with open(path, "wb") as fh:
                    fh.write(was)
        wrong = ["editing %s does not change the build id, so a run after that edit "
                 "serves the old report" % name for name in deaf]
        if build_id() != first:
            wrong.append("the build id moved when nothing was touched, so it can never skip "
                         "anything")
        print("  %-48s %s" % ("every one of %d source files moves the build id" % len(sources),
                              "FAILED" if wrong else "ok"))
        return wrong
    finally:
        shutil.rmtree(holding, ignore_errors=True)


def cross_campaigns():
    """[what went wrong] in what makes a `--cross` report stale."""
    sys.path.insert(0, os.path.join(HERE, "testkit"))
    import matching
    import savefmt

    holding = tempfile.mkdtemp(prefix="vic2xstale")
    try:
        mods = {name: matching.a_mod_in_a_game(holding, "mod-" + name,
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

        # Alpha stays the larger by more than the save beta gains, so the
        # campaign that changes is never the one the report is about.
        for n in range(5):
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
    import matching
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
        game = matching.a_vanilla(os.path.join(holding, "Victoria 2"))

        def run(*extra):
            return subprocess.run(
                [sys.executable, os.path.join(HERE, "vic2_analyzer.py"), saves,
                 "--out", out, "--game-root", game, "--no-cache"] + list(extra),
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
            elif (locked.returncode == 0 or "nations_timeseries.csv" not in said
                  or "open in another program" not in said):
                wrong.append("a locked table was not named in a sentence: %s"
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
    import matching
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
        game = matching.a_vanilla(os.path.join(holding, "Victoria 2"))
        for extra in ([], ["--tags", "FRA"]):
            subprocess.run([sys.executable, os.path.join(HERE, "vic2_analyzer.py"),
                            saves, "--out", out, "--game-root", game,
                            "--no-cache", "-q"] + extra,
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


# How each setting that changes the report is changed from the command line,
# against a plain run (`a`) or a --cross run (`x`). A setting declared to
# change the report and not here is a failure: it has to be decided here too.
CHANGED_BY = {
    "tags": ("a", ["--tags", "ENG"]),
    "mod_path": ("a", "OTHER MOD"),
    "mob_rate": ("a", ["--mobilisation-size", "0.5"]),
    "pop_per_regiment": ("a", ["--pop-per-regiment", "1500"]),
    "mob_types": ("a", ["--mob-types", "farmers"]),
    "mob_include_occupied": ("a", ["--mob-include-occupied"]),
    "map_scale": ("a", ["--map-scale", "2"]),
    "player_nations": ("a", ["--player-nations", "FRA"]),
    "min_pop": ("a", ["--min-pop", "5000"]),
    "split": ("a", ["--split"]),
    "game_root": ("a", "GAME TOO"),
    "no_html": (None, "never skips, and what it leaves is held by unfinished_runs"),
    "cross": ("x", "PLAIN"),
    "campaign_mod": ("x", "OTHER CAMPAIGN MOD"),
    "primary": ("x", ["--primary", "beta"]),
}


def the_settings_the_stamp_covers():
    """[what went wrong] in which settings the report stamp covers."""
    import dataclasses
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(HERE, "testkit"))
    import run as settings
    import matching
    import savefmt

    wrong = []
    declared = dataclasses.fields(settings.Run)
    for setting in declared:
        if "report" not in setting.metadata:
            wrong.append("%s does not say whether it changes the report" % setting.name)
    left_out = {f.name for f in declared if not f.metadata.get("report")}
    for name in sorted(left_out - set(OUT_OF_STAMP)):
        wrong.append("%s is left out of the report stamp, and nothing says it may be -- a run "
                     "that changes it would be answered with the report made before" % name)
    reported = [f.name for f in declared if f.metadata.get("report")]
    for name in reported:
        if name not in CHANGED_BY:
            wrong.append("%s changes the report and nothing here changes it to see the "
                         "stamp move" % name)

    holding = tempfile.mkdtemp(prefix="vic2sstale")
    try:
        mods = {n: matching.a_mod_in_a_game(holding, n, pop_per_regiment=1000)
                for n in ("Mod", "Other")}
        game = os.path.join(holding, "game")
        parent = os.path.join(holding, "campaigns")
        for camp, years in (("alpha", (1840, 1841, 1842)), ("beta", (1850, 1851))):
            for n, year in enumerate(years):
                os.makedirs(os.path.join(parent, camp), exist_ok=True)
                savefmt.write(os.path.join(parent, camp, "s%d.v2" % n),
                              savefmt.head("%d.1.1" % year),
                              savefmt.province(1, "ENG", [savefmt.pop("farmers", 10, 20000)]),
                              savefmt.province(2, "FRA", [savefmt.pop("farmers", 20, 20000,
                                                                      culture="french")]),
                              savefmt.country("ENG", techs=matching.TECHS),
                              savefmt.country("FRA", culture="french", capital=2))
        out = os.path.join(holding, "out")
        env = dict(os.environ, TMPDIR=holding)
        plain = [os.path.join(parent, "alpha"), "--mod-path", mods["Mod"]]
        crossed = [parent, "--cross", "--campaign-mod", "alpha=" + mods["Mod"],
                   "--campaign-mod", "beta=" + mods["Mod"]]

        def skipped(argv):
            done = subprocess.run([sys.executable, os.path.join(HERE, "vic2_analyzer.py")]
                                  + argv + ["--out", out],
                                  capture_output=True, text=True, cwd=HERE, env=env)
            if done.returncode:
                raise AssertionError("a run failed: %s\n%s" % (argv, (done.stdout + done.stderr)[-800:]))
            return "Nothing has changed" in done.stdout

        for name in reported:
            base, how = CHANGED_BY.get(name, (None, None))
            if base is None:
                continue
            before = plain if base == "a" else crossed
            if how == "OTHER MOD":
                after = [plain[0], "--mod-path", mods["Other"]]
            elif how == "GAME TOO":
                after = plain + ["--game-root", game]
            elif how == "PLAIN":
                after = [os.path.join(parent, "beta"), "--mod-path", mods["Mod"]]
            elif how == "OTHER CAMPAIGN MOD":
                after = crossed[:-1] + ["beta=" + mods["Other"]]
            else:
                after = before + how
            skipped(before)
            if not skipped(before):
                wrong.append("%s: the same run twice was built twice, so this case tests "
                             "nothing" % name)
            if skipped(after):
                wrong.append("changing %s does not move the report stamp, so a run that "
                             "changes it is answered with the old report" % name)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print("  %-48s %s" % ("every setting that changes the report moves it",
                          "FAILED" if wrong else "ok (%d of %d)" % (
                              len(declared) - len(left_out), len(declared))))
    return wrong


def main():
    deaf = the_build_id_covers_every_source()
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

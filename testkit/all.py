#!/usr/bin/env python3
"""
Run every check, fastest first, and say what held and what did not.

The checks run in dependency order: the
save-builder the tests themselves are written on, then the ones that need
nothing, then the ones that need saves, then the ones that need a built
report, then the slow ones. Doing that by hand means doing it wrong or not
at all.

    python3 testkit/all.py "/path/to/saves" [--mod "/path/to/mod"] [--quick]

`--quick` leaves out the two that take minutes rather than seconds: the
smoke matrix and, within it, `--verify`. Everything else runs in about a
minute on a campaign of a hundred saves.

A check that cannot run here -- no Firefox, no display, no mod, no saves --
says so and does not count against the total. A check that fails prints its
own output in full, because the point of a suite is the one that broke.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(HERE, "testkit")

sys.path.insert(0, KIT)
from outcome import SKIPPED                                 # noqa: E402


def run(name, argv, why=""):
    """One check. (name, ok, skipped, seconds, output)."""
    began = time.monotonic()
    try:
        done = subprocess.run([sys.executable] + argv, capture_output=True,
                              text=True, cwd=HERE, timeout=900)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        return name, False, False, time.monotonic() - began, output + "\nTimed out after 900 seconds", why
    took = time.monotonic() - began
    out = done.stdout + done.stderr
    # A check that cannot run all of itself here says so with its exit
    # status, not its words. See `outcome.py`.
    skipped = done.returncode == SKIPPED
    return name, done.returncode in (0, SKIPPED), skipped, took, out, why


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("saves", nargs="?", default="",
                    help="a folder of .v2 saves from one campaign")
    ap.add_argument("--mod", default="", help="a mod folder, if there is one")
    ap.add_argument("--quick", action="store_true",
                    help="leave out the checks that take minutes")
    ap.add_argument("--update-expected", action="store_true",
                    help="record what the program answers now as the answers the checks "
                         "hold it to, after a deliberate change")
    args = ap.parse_args()

    holding = tempfile.mkdtemp(prefix="vic2all")
    out = os.path.join(holding, "out")
    report = os.path.join(out, "report.html")
    table = os.path.join(out, "nations_timeseries.csv")

    checks = [
        # First, because every check below that writes a save writes it
        # with `savefmt`. If the builder is wrong their passes mean
        # nothing, and one of them did pass for the wrong reason once.
        ("the save-builder the tests use", [os.path.join(KIT, "savefmt.py")]),
        ("names read before they exist", [os.path.join(KIT, "tooearly.py")]),
        ("the shapes a save can take", [os.path.join(KIT, "saveshapes.py")]),
        ("the keeper", [os.path.join(KIT, "keeping.py")]),
        ("one game's saves told from another's",
         [os.path.join(KIT, "histories.py")]),
        ("campaigns nobody has", [os.path.join(KIT, "edges.py")]),
        ("damaged saves", [os.path.join(KIT, "mangled.py")]),
        ("sharing a report", [os.path.join(KIT, "sharing.py")]),
        ("what the executable carries", [os.path.join(KIT, "packing.py")]),
        ("matching a campaign to its mod", [os.path.join(KIT, "matching.py")]),
        ("the engine process and test fixtures", [os.path.join(KIT, "engine_runtime.py")]),
        ("the mod reader", [os.path.join(KIT, "modread.py")]
         + (["--mod", args.mod] if args.mod else [])),
        ("the run's front end", [os.path.join(KIT, "frontcheck.py")]),
        ("the engine's number formatting", [os.path.join(KIT, "enginefmt.py"),
         os.path.join(HERE, "scanner", "target", "release", "vic2scan" + (".exe" if os.name == "nt" else "")), "20000"]),
        ("the engine's compression", [os.path.join(KIT, "enginecompress.py"),
         os.path.join(HERE, "scanner", "target", "release", "vic2scan" + (".exe" if os.name == "nt" else ""))]),
        ("the map's province bitmap", [os.path.join(KIT, "raster.py")]),
        ("what the engine keeps between runs", [os.path.join(KIT, "caching.py")]),
        ("what can make a report stale", [os.path.join(KIT, "staleness.py")]),
        ("the mobilisation rate rule", [os.path.join(KIT, "mobrate.py")]),
        ("the cross block against the report",
         [os.path.join(KIT, "crossrows.py")]),
    ]

    if args.update_expected:
        # The checks held to recorded answers, each told to write what the
        # program answers now as its record. For after a deliberate change:
        # `git diff testkit/expected` then shows what it changed.
        recorded = [("frontcheck.py",), ("crossrows.py",), ("saveshapes.py",),
                    ("mangled.py",),
                    ("modread.py",) + (("--mod", args.mod) if args.mod else ()),
                    ("enginecheck.py",) + ((args.saves,) if args.saves else ())
                    + (("--mod", args.mod) if args.mod else ())]
        bad = 0
        for script, *rest in recorded:
            done = subprocess.run([sys.executable, os.path.join(KIT, script)] + list(rest)
                                  + ["--update"], capture_output=True, text=True, cwd=HERE)
            ok = done.returncode in (0, SKIPPED)
            bad += not ok
            print("  %-16s %s" % (script, "recorded" if ok else "FAILED"))
            if not ok:
                print((done.stdout + done.stderr)[-3000:])
        print("\nsee `git diff testkit/expected testkit/expected-real`; the real campaign's "
              "answers are in %s" % os.environ.get("VIC2_EXPECTED_REAL", "testkit/expected-real"))
        shutil.rmtree(holding, ignore_errors=True)
        return 1 if bad else 0

    try:
        if args.saves and os.path.isdir(args.saves):
            # One report, built once, for the three checks that read one.
            built = subprocess.run(
                [sys.executable, os.path.join(HERE, "vic2_analyzer.py"),
                 args.saves, "--out", out, "--rebuild", "-q"]
                + (["--mod-path", args.mod] if args.mod else []),
                capture_output=True, text=True, cwd=HERE)
            if built.returncode:
                print("could not build a report to check:\n%s"
                      % (built.stdout + built.stderr)[-2000:])
                return 1
            one = next((os.path.join(args.saves, f)
                        for f in sorted(os.listdir(args.saves))
                        if f.endswith(".v2")), "")
            checks += [
                ("a real save, damaged", [os.path.join(KIT, "mangled.py"), one, "4"]),
                ("the numbers against each other",
                 [os.path.join(KIT, "invariants.py"), table, report]),
                ("the payload split", [os.path.join(KIT, "facts.py"), report]),
                ("the report in a browser",
                 [os.path.join(KIT, "boots.py"), report]),
                ("state history decoded in the browser",
                 [os.path.join(KIT, "state_history_ui.py"), report]),
                ("the window", [os.path.join(KIT, "window.py"), args.saves]),
                ("the report engine against its recorded answers",
                 [os.path.join(KIT, "enginecheck.py"), args.saves]
                 + (["--mod", args.mod] if args.mod else [])),
            ]
            if not args.quick:
                smoke = [os.path.join(KIT, "smoke.py"), args.saves]
                if args.mod:
                    smoke += ["--mod", args.mod]
                checks.append(("every way of running it", smoke))
        else:
            print("no saves given, so only the checks that need none ran\n")

        width = max(len(n) for n, _ in checks)
        results = []
        for name, argv in checks:
            got = run(name, argv)
            results.append(got)
            _n, ok, skipped, took, _out, _why = got
            print("  %-*s %s %6.1fs" % (width, name,
                                        "skip" if skipped else
                                        "ok  " if ok else "FAIL", took))

        bad = [r for r in results if not r[1]]
        print()
        for name, _ok, _sk, _t, out_text, _why in bad:
            print("=" * 70)
            print("%s said:" % name)
            print(out_text.rstrip()[-3000:])
            print()
        skipped = sum(1 for r in results if r[2])
        if bad:
            print("%d of %d checks failed: %s"
                  % (len(bad), len(results), ", ".join(r[0] for r in bad)))
            return 1
        print("all %d checks hold%s"
              % (len(results),
                 " (%d skipped)" % skipped if skipped else ""))
        return 0
    finally:
        shutil.rmtree(holding, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

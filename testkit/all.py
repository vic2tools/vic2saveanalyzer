#!/usr/bin/env python3
"""
Run every check, fastest first, and say what held and what did not.

There are seventeen of these now and they want running in an order: the
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


def run(name, argv, why=""):
    """One check. (name, ok, skipped, seconds, output)."""
    began = time.monotonic()
    done = subprocess.run([sys.executable] + argv, capture_output=True,
                          text=True, cwd=HERE)
    took = time.monotonic() - began
    out = done.stdout + done.stderr
    # A check says so itself when it cannot run, and exits 0 for it.
    skipped = done.returncode == 0 and any(
        phrase in out for phrase in
        ("no firefox here", "no tkinter or no display", "no scanner built",
         "carries no payload"))
    return name, done.returncode == 0, skipped, took, out, why


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("saves", nargs="?", default="",
                    help="a folder of .v2 saves from one campaign")
    ap.add_argument("--mod", default="", help="a mod folder, if there is one")
    ap.add_argument("--quick", action="store_true",
                    help="leave out the checks that take minutes")
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
        ("awkward save layouts", [os.path.join(KIT, "awkward.py")]),
        ("awkward country blocks", [os.path.join(KIT, "countries.py")]),
        ("the keeper", [os.path.join(KIT, "keeping.py")]),
        ("campaigns nobody has", [os.path.join(KIT, "edges.py")]),
        ("sharing a report", [os.path.join(KIT, "sharing.py")]),
        ("what the executable carries", [os.path.join(KIT, "packing.py")]),
        ("matching a campaign to its mod", [os.path.join(KIT, "matching.py")]),
    ]

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
                ("damaged saves", [os.path.join(KIT, "mangled.py"), one, "4"]),
                ("the scanner against the parser",
                 [os.path.join(KIT, "parity.py"), args.saves, "8"]),
                ("the numbers against each other",
                 [os.path.join(KIT, "invariants.py"), table, report]),
                ("the payload split", [os.path.join(KIT, "facts.py"), report]),
                ("the report in a browser",
                 [os.path.join(KIT, "boots.py"), report]),
                ("the window", [os.path.join(KIT, "window.py"), args.saves]),
                ("the way Windows starts workers",
                 [os.path.join(KIT, "spawned.py"), args.saves]
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

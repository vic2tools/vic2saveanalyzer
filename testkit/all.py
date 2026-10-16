#!/usr/bin/env python3
"""
Run every check in `suite.py` and say what held and what did not.

    python3 testkit/all.py ["/path/to/saves" --mod "/path/to/mod"]
    python3 testkit/all.py "/path/to/saves" --mod "/path/to/mod" --update-expected

Given saves, it builds one report from them first, for the checks that read
one. Checks that share nothing run side by side; the ones that drive a
window or a browser run alone, after them. Each check gets a temp folder of
its own, so none writes the real engine cache.

A check that cannot run here -- no Firefox, no display, no mod, no saves --
is skipped, says which, and does not count against the total. One that
fails prints its own output, because the point of a suite is the one that
broke.

`--update-expected` re-records the checks that hold recorded answers, after
a deliberate change; `git diff testkit/expected` then shows what changed.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import suite
from outcome import SKIPPED

ROOT = suite.ROOT
_SAY = threading.Lock()


def say(text):
    """One whole line, never interleaved with another thread's."""
    with _SAY:
        print(text, flush=True)


def env_in(folder):
    """The environment with every temp-folder variable pointing into
    `folder`, so nothing run under it touches the real caches."""
    os.makedirs(folder, exist_ok=True)
    return dict(os.environ, TMPDIR=folder, TEMP=folder, TMP=folder)


def run(check, argv, holding, verbose):
    """(check, "ok" | "skip" | "FAIL", seconds, output)."""
    began = time.monotonic()
    if verbose:
        say("  start %s" % check.title)
    try:
        done = subprocess.run([sys.executable] + argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=ROOT, timeout=900,
                              env=env_in(os.path.join(holding, "tmp-" + check.script
                                                      + "-" + str(id(check)))))
        code, out = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as late:
        code, out = None, "%s\nTimed out after 900 seconds" % (late.stdout or "")
    took = time.monotonic() - began
    if verbose:
        say("  end   %s" % check.title)
    state = "ok" if code == 0 else "skip" if code == SKIPPED else "FAIL"
    return check, state, took, out


def build_report(saves, mod, holding):
    """The report the after_report checks read, or exit with why not."""
    out = os.path.join(holding, "out")
    built = subprocess.run(
        [sys.executable, os.path.join(ROOT, "vic2_analyzer.py"), saves, "--out", out,
         "--rebuild", "-q"] + (["--mod-path", mod] if mod else []),
        capture_output=True, text=True, cwd=ROOT, env=env_in(os.path.join(holding, "tmp-report")))
    if built.returncode:
        sys.exit("could not build a report to check:\n%s" % (built.stdout + built.stderr)[-2000:])
    return os.path.join(out, "report.html")


def update_expected(args):
    bad = 0
    for check in suite.CHECKS:
        if not check.records:
            continue
        argv = suite.argv_for(check, saves=args.saves, mod=args.mod)
        if argv is None:
            print("  %-16s skipped (needs %s)" % (check.script, ", ".join(
                suite.unmet(check, saves=args.saves, mod=args.mod))))
            continue
        done = subprocess.run([sys.executable] + argv + ["--update"],
                              capture_output=True, text=True, cwd=ROOT)
        ok = done.returncode in (0, SKIPPED)
        bad += not ok
        print("  %-16s %s" % (check.script, "recorded" if ok else "FAILED"))
        if not ok:
            print((done.stdout + done.stderr)[-3000:])
    print("\nsee `git diff testkit/expected`")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("saves", nargs="?", default="", help="a folder of .v2 saves")
    ap.add_argument("--mod", default="", help="that campaign's mod folder")
    ap.add_argument("--quick", action="store_true", help="leave out the slow smoke matrix")
    ap.add_argument("--update-expected", action="store_true",
                    help="re-record the checks that hold recorded answers")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="say when each check starts and ends")
    args = ap.parse_args()
    args.saves = args.saves if args.saves and os.path.isdir(args.saves) else ""
    if args.update_expected:
        return update_expected(args)

    have = suite.tools_here()
    if "scanner" not in have:
        print("no scanner built, so most checks are skipped. Build it:\n"
              "  cargo build --release --manifest-path scanner/Cargo.toml\n")
    holding = tempfile.mkdtemp(prefix="vic2all")
    try:
        report = build_report(args.saves, args.mod, holding) if args.saves else ""
        if not args.saves:
            print("no saves given, so only the checks that need none run\n")
        chosen = [c for c in suite.CHECKS if not (args.quick and c.script == "smoke.py")]
        planned, skipped = [], []
        for c in chosen:
            argv = suite.argv_for(c, saves=args.saves, mod=args.mod, report=report, have=have)
            if argv is None:
                skipped.append((c, "skip", 0.0, "needs " + ", ".join(suite.unmet(
                    c, saves=args.saves, mod=args.mod, report=report, have=have))))
            else:
                planned.append((c, argv))

        width = max(len(c.title) for c in chosen)

        def show(result):
            c, state, took, out = result
            why = "  (%s)" % out if state == "skip" and out.startswith("needs ") else ""
            say("  %-*s %-4s %6.1fs%s" % (width, c.title, state, took, why))
            return result

        results = [show(s) for s in skipped]
        together = [(c, a) for c, a in planned if not c.exclusive]
        alone = [(c, a) for c, a in planned if c.exclusive]
        # Four at most: each check may start a scanner that fans out over every
        # core itself, and sizes what it reads at once by the memory free.
        with ThreadPoolExecutor(4) as pool:
            for result in pool.map(lambda ca: run(ca[0], ca[1], holding, args.verbose), together):
                results.append(show(result))
        for c, a in alone:
            results.append(show(run(c, a, holding, args.verbose)))

        bad = [r for r in results if r[1] == "FAIL"]
        print()
        for c, _s, _t, out in bad:
            print("=" * 70)
            print("%s said:" % c.title)
            print(out.rstrip()[-3000:])
            print()
        n_skipped = sum(1 for r in results if r[1] == "skip")
        if bad:
            print("%d of %d checks failed: %s"
                  % (len(bad), len(results), ", ".join(r[0].title for r in bad)))
            return 1
        print("all %d checks hold%s" % (len(results),
                                        " (%d skipped)" % n_skipped if n_skipped else ""))
        return 0
    finally:
        shutil.rmtree(holding, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

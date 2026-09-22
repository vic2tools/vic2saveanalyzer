#!/usr/bin/env python3
"""
Read a campaign the way Windows reads it, and check it comes out the same.

Linux starts worker processes by forking, so a worker begins life with the
parent's memory already in it -- every module imported, every global set.
Windows cannot do that. It spawns a fresh interpreter and the worker
re-imports everything from scratch, which is a different program in two
ways that matter: anything passed to a worker has to survive pickling by
name, and anything a worker needs that was set up after import has to be
handed over rather than inherited.

The analyzer is developed here and shipped there. Every measurement and
every check in this directory runs under fork; the executable people
download runs under spawn, and nothing had ever run it that way.

    python3 testkit/spawned.py "/path/to/saves" [--mod "/path/to/mod"]

Builds the same campaign both ways and compares every file byte for byte,
and fails if either way had to read the saves one at a time because its
workers would not start.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A worker under spawn re-imports and re-runs this, so it has to be a
# module-level program with its own `__main__` guard, exactly as the
# executable is.
DRIVER = '''
import multiprocessing, sys
if __name__ == "__main__":
    multiprocessing.set_start_method(%r, force=True)
    sys.path.insert(0, %r)
    sys.argv = [%r] + sys.argv[1:]
    import vic2_analyzer
    sys.exit(vic2_analyzer.main() or 0)
'''


def build(how, saves, out, mod, holding):
    """Build the campaign with one start method. Returns what it printed."""
    driver = os.path.join(holding, "drive_%s.py" % how)
    with open(driver, "w") as fh:
        fh.write(DRIVER % (how, HERE, "vic2_analyzer.py"))
    argv = [sys.executable, driver, saves, "--out", out, "--rebuild", "-q"]
    if mod:
        argv += ["--mod-path", mod]
    cache = os.path.join(holding, how + "-cache")
    os.makedirs(cache)
    return subprocess.run(argv, capture_output=True, text=True, cwd=HERE,
                          env={**os.environ, "TMPDIR": cache, "TEMP": cache,
                               "TMP": cache})


def fingerprints(folder):
    """{file name: hash} for everything a run wrote."""
    out = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                out[name] = hashlib.sha256(fh.read()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("saves")
    ap.add_argument("--mod", default="")
    args = ap.parse_args()
    if not os.path.isdir(args.saves):
        print("no such folder: %s" % args.saves)
        return 2

    holding = tempfile.mkdtemp(prefix="vic2spawn")
    try:
        made = {}
        for how in ("fork", "spawn"):
            if how not in __import__("multiprocessing").get_all_start_methods():
                print("  %s is not available here, so it was not tried" % how)
                continue
            out = os.path.join(holding, how)
            done = build(how, args.saves, out, args.mod, holding)
            said = done.stdout + done.stderr
            if done.returncode:
                print("  %s: the run failed\n%s" % (how, said[-1500:]))
                return 1
            # A pool that will not start is not an error to the analyzer: it
            # says so and reads every save itself, and the files come out
            # the same. So comparing them cannot tell a worker that started
            # under spawn from one that never did -- and a job that cannot be
            # sent to a fresh interpreter by name is exactly what spawn breaks
            # and fork does not. Measured: with the finishing handed over as a
            # lambda, spawn fell back to one save at a time and this check
            # said "all 10 files identical" and passed.
            if "reading one at a time" in said:
                print("  %s: the workers never started, so every save was "
                      "read one at a time and nothing was read the way %s "
                      "reads it\n%s" % (how, how, said[-1500:]))
                return 1
            made[how] = fingerprints(out)
            print("  %-6s wrote %d files" % (how, len(made[how])))

        if len(made) < 2:
            print("\nonly one start method here, so there was nothing to "
                  "compare")
            return 0

        fork, spawn = made["fork"], made["spawn"]
        wrong = []
        for name in sorted(set(fork) | set(spawn)):
            if name not in fork:
                wrong.append("%s only appeared under spawn" % name)
            elif name not in spawn:
                wrong.append("%s only appeared under fork" % name)
            elif fork[name] != spawn[name]:
                wrong.append("%s differs between fork and spawn" % name)
        print()
        if wrong:
            print("PROBLEMS:")
            for one in wrong:
                print("  %s" % one)
            return 1
        print("all %d files identical whichever way the workers start"
              % len(fork))
        return 0
    finally:
        shutil.rmtree(holding, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

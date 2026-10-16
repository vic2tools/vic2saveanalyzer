#!/usr/bin/env python3
"""
Does a check actually catch the bug it was written for?

A check is only worth what it refuses. This puts each known bug in
`mutations.py` back into a copy of the tree, one at a time, runs the check
that claims to catch it, and says what happened:

    CAUGHT    the check failed with the bug in place
    BLIND     the check still passed: it is not doing its job
    TIMEOUT   the check did not finish in time; the bug may hang the program
    SKIPPED   the check could not run here (exit 77), so it saw nothing
    NOAPPLY   the bug's text is no longer in the file: move the mutation
    NOBUILD   the scanner did not build with the bug in it
    UNTESTED  the check does not hold on the tree without the bug, or its
              inputs were not given, so failing with it would prove nothing

    python3 testkit/mutate.py [--saves DIR] [--mod DIR] [--baseline DIR] [name ...]
    python3 testkit/mutate.py --dry       # does every mutation still apply?
    python3 testkit/mutate.py --list

It makes its own git worktree of HEAD in the temp folder, copies the built
scanner into it, and removes it when done, so the tree you work in is never
touched; commit what you want tested. A bug put into `scanner/` or the page
is built first, with a light release profile (no LTO, sixteen codegen
units, incremental): seconds, where the shipped profile takes the better
part of a minute. The scanner as committed is put back after each.

It exits 1 on any BLIND, NOAPPLY or NOBUILD; with `--strict`, on TIMEOUT,
SKIPPED and UNTESTED too. `all.py` does not run it: reach for it after
writing a check, to see that the check fails on the code it should reject.
"""
import argparse
import enum
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

from mutations import MUTATIONS
from outcome import SKIPPED

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNER = os.path.join("scanner", "target", "release",
                       "vic2scan" + (".exe" if os.name == "nt" else ""))

# Set in the environment rather than Cargo.toml, so the build id the
# scanner stamps into its reports is the committed one's.
FAST_BUILD_ENV = {"CARGO_PROFILE_RELEASE_LTO": "false",
                  "CARGO_PROFILE_RELEASE_CODEGEN_UNITS": "16",
                  "CARGO_PROFILE_RELEASE_INCREMENTAL": "true"}

# Checks that drive a window or a browser run on their own, never beside
# another.
ALONE = {"window.py", "boots.py", "war_legacy_ui.py", "state_history_ui.py"}

Outcome = namedtuple("Outcome", "code timed_out output")


class Verdict(enum.Enum):
    CAUGHT = "caught"
    BLIND = "BLIND"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"
    NOAPPLY = "NOAPPLY"
    NOBUILD = "NOBUILD"
    UNTESTED = "UNTESTED"


def holds(outcome):
    return not outcome.timed_out and outcome.code == 0


def verdict(control, mutated):
    """What the check's run with the bug says, given its run without."""
    if not holds(control):
        return Verdict.UNTESTED
    if mutated.timed_out:
        return Verdict.TIMEOUT
    if mutated.code == SKIPPED:
        return Verdict.SKIPPED
    return Verdict.BLIND if mutated.code == 0 else Verdict.CAUGHT


# ------------------------------------------------------------ the tree

class Unapplied(Exception):
    pass


def patch(tree, path, old, new, count=1):
    """Replace `old` with `new` in tree/path; `old` must appear `count`
    times (0: at least once)."""
    full = os.path.join(tree, path)
    with open(full, encoding="utf-8", newline="") as fh:
        src = fh.read()
    n = src.count(old)
    if n < 1:
        raise Unapplied("%r not found in %s" % (old[:70], path))
    if count and n != count:
        raise Unapplied("%r appears %d times in %s, not %d" % (old[:70], n, path, count))
    with open(full, "w", encoding="utf-8", newline="") as fh:
        fh.write(src.replace(old, new))


def revert(tree):
    subprocess.run(["git", "checkout", "--", "."], cwd=tree, check=True)


def rebuilds(mutation):
    """Whether the bug is in the scanner, or in the page it builds in."""
    return any(p[0].startswith("scanner/") or p[0] == "template.py"
               for p in mutation.patches)


def cargo():
    found = shutil.which("cargo")
    if found:
        return found
    home = os.path.join(os.path.expanduser("~"), ".cargo", "bin", "cargo")
    return home + ".exe" if os.name == "nt" else home


def build(tree):
    """Build the tree's scanner the fast way. (built, what cargo said)."""
    done = subprocess.run([cargo(), "build", "--release"],
                          cwd=os.path.join(tree, "scanner"),
                          env=dict(os.environ, **FAST_BUILD_ENV),
                          capture_output=True, text=True, errors="replace")
    return done.returncode == 0, done.stderr[-2000:]


def put_back(pristine, binary):
    """The committed scanner back in place, renamed over the built one, so
    a process still running the old file is left alone."""
    fresh = binary + ".next"
    shutil.copyfile(pristine, fresh)
    shutil.copymode(pristine, fresh)
    os.replace(fresh, binary)


def remove_tree(path):
    """Delete a folder whose build output nests past Windows' 260-character
    limit, which plain deletion fails on."""
    if os.name == "nt":
        path = "\\\\?\\" + os.path.abspath(path)
    shutil.rmtree(path, ignore_errors=True)


class Worktree:
    """A worktree of HEAD in the temp folder, with the built scanner in it,
    removed again however the run ends."""

    def __init__(self, need_scanner=True):
        self.need_scanner = need_scanner
        self.path = None

    def __enter__(self):
        built = os.path.join(ROOT, SCANNER)
        if self.need_scanner and not os.path.isfile(built):
            raise SystemExit("no scanner built at %s, so every run would be refused. "
                             "Build it: cargo build --release --manifest-path "
                             "scanner/Cargo.toml" % SCANNER)
        self.path = tempfile.mkdtemp(prefix="vm")
        os.rmdir(self.path)
        subprocess.run(["git", "worktree", "add", "-q", "--detach", self.path, "HEAD"],
                       cwd=ROOT, check=True)
        if self.need_scanner:
            target = os.path.join(self.path, SCANNER)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(built, target)
        return self.path

    def __exit__(self, *exc):
        done = subprocess.run(["git", "worktree", "remove", "--force", self.path],
                              cwd=ROOT, capture_output=True)
        if done.returncode or os.path.exists(self.path):
            remove_tree(self.path)
        subprocess.run(["git", "worktree", "prune"], cwd=ROOT)


# ------------------------------------------------------------ the checks

def kill_tree(proc):
    """The check and everything it started: a hung scanner would otherwise
    hold the binary that has to be put back."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGKILL)


def check(tree, script, argv, timeout):
    """Run one check in the tree. An Outcome, never an exception."""
    proc = subprocess.Popen([sys.executable, os.path.join("testkit", script)] + list(argv),
                            cwd=tree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            start_new_session=os.name != "nt")
    try:
        out, _ = proc.communicate(timeout=timeout)
        return Outcome(proc.returncode, False, out)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        out, _ = proc.communicate()
        return Outcome(None, True, (out or "") + "\n(timed out after %d s)" % timeout)


def argv_for(needs, saves, mod, baseline):
    """What a catcher is handed, or a sentence saying which input is missing."""
    argv = []
    for need in needs:
        if need == "saves":
            if not saves:
                return "needs --saves"
            argv.append(saves)
        elif need == "mod":
            if not mod:
                return "needs --mod"
            argv += ["--mod", mod]
        elif need == "baseline":
            if not baseline:
                return "needs --baseline or $VIC2_BASELINE"
            argv += ["--from", baseline]
        elif need == "one-save":
            first = next((f for f in sorted(os.listdir(saves)) if f.endswith(".v2")),
                         "") if saves else ""
            if not first:
                return "needs --saves with a save in it"
            argv += [os.path.join(saves, first), "1"]
        else:
            argv.append(need)
    return argv


def tail(text, lines=25):
    return "\n".join("      " + l for l in text.rstrip().splitlines()[-lines:])


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("names", nargs="*", help="only these mutations")
    ap.add_argument("--saves", default="", help="a folder of .v2 saves")
    ap.add_argument("--mod", default="", help="the campaign's mod folder")
    ap.add_argument("--baseline", default=os.environ.get("VIC2_BASELINE", ""),
                    help="a recorded baseline (default $VIC2_BASELINE)")
    ap.add_argument("--timeout", type=int, default=120,
                    help="seconds a check may take (default 120)")
    ap.add_argument("--strict", action="store_true",
                    help="fail on TIMEOUT, SKIPPED and UNTESTED too")
    ap.add_argument("--dry", action="store_true",
                    help="only apply and revert each mutation")
    ap.add_argument("--list", action="store_true", help="list the mutations")
    args = ap.parse_args()

    unknown = set(args.names) - {m.name for m in MUTATIONS}
    if unknown:
        raise SystemExit("no such mutation: %s" % ", ".join(sorted(unknown)))
    chosen = [m for m in MUTATIONS if not args.names or m.name in args.names]
    if args.list:
        for m in chosen:
            print("%-38s %-20s %s" % (m.name, m.catcher, " ".join(m.needs)))
        return 0

    saves = os.path.abspath(args.saves) if args.saves else ""
    mod = os.path.abspath(args.mod) if args.mod else ""
    baseline = os.path.abspath(args.baseline) if args.baseline else ""
    results = []
    with Worktree(need_scanner=not args.dry) as tree:
        if args.dry:
            for m in chosen:
                try:
                    for p in m.patches:
                        patch(tree, *p)
                    got = Verdict.CAUGHT
                except Unapplied as why:
                    got = Verdict.NOAPPLY
                    print("%-38s NOAPPLY  %s" % (m.name, why))
                revert(tree)
                results.append((m, got, ""))
            bad = sum(1 for _m, v, _o in results if v is Verdict.NOAPPLY)
            print("%d mutations: %d apply, %d do not" % (len(results), len(results) - bad, bad))
            return 1 if bad else 0

        binary = os.path.join(tree, SCANNER)
        pristine = binary + ".pristine"
        shutil.copy2(binary, pristine)

        # Each check first runs on the tree without the bug, and has to
        # hold there: failing anyway, its failing with the bug says nothing.
        controls, unmet = {}, {}
        for m in chosen:
            key = (m.catcher, m.needs)
            argv = argv_for(m.needs, saves, mod, baseline)
            if isinstance(argv, str):
                unmet[key] = argv
            else:
                controls[key] = argv
        def control(key):
            return key, check(tree, key[0], controls[key], args.timeout)
        together = [k for k in controls if k[0] not in ALONE]
        alone = [k for k in controls if k[0] in ALONE]
        with ThreadPoolExecutor(4) as pool:
            held = dict(pool.map(control, together))
        held.update(map(control, alone))
        for (catcher, needs), outcome in held.items():
            if not holds(outcome):
                print("CONTROL %s: %s %s, so its mutations are untested:\n%s\n"
                      % ("TIMED OUT" if outcome.timed_out else
                         "SKIPPED" if outcome.code == SKIPPED else "FAILED",
                         catcher, " ".join(needs), tail(outcome.output)))

        print("%-38s %-9s %s" % ("MUTATION", "VERDICT", "BUG PUT BACK"))
        print("-" * 100)
        for m in chosen:
            key = (m.catcher, m.needs)
            output = ""
            if key in unmet:
                got, output = Verdict.UNTESTED, unmet[key]
            elif not holds(held[key]):
                got = Verdict.UNTESTED
            else:
                revert(tree)
                try:
                    for p in m.patches:
                        patch(tree, *p)
                except Unapplied as why:
                    got, output = Verdict.NOAPPLY, str(why)
                else:
                    rust = rebuilds(m)
                    built, said = build(tree) if rust else (True, "")
                    if not built:
                        got, output = Verdict.NOBUILD, said
                    else:
                        outcome = check(tree, m.catcher, controls[key], args.timeout)
                        got, output = verdict(held[key], outcome), outcome.output
                    if rust:
                        revert(tree)
                        put_back(pristine, binary)
            print("%-38s %-9s %s  [%s]" % (m.name, got.value, m.bug, m.catcher))
            results.append((m, got, output))
        revert(tree)

    print("\n" + "=" * 100)
    counts = {v: sum(1 for _m, g, _o in results if g is v) for v in Verdict}
    print("%d mutations: %s" % (len(results), ", ".join(
        "%d %s" % (n, v.value) for v, n in counts.items() if n)))
    for m, got, output in results:
        if got in (Verdict.BLIND, Verdict.TIMEOUT, Verdict.SKIPPED,
                   Verdict.NOAPPLY, Verdict.NOBUILD):
            print("\n--- %s: %s (%s)\n    bug: %s\n%s"
                  % (got.value, m.name, m.catcher, m.bug, tail(output)))
    failing = {Verdict.BLIND, Verdict.NOAPPLY, Verdict.NOBUILD}
    if args.strict:
        failing |= {Verdict.TIMEOUT, Verdict.SKIPPED, Verdict.UNTESTED}
    return 1 if any(counts[v] for v in failing) else 0


if __name__ == "__main__":
    sys.exit(main())

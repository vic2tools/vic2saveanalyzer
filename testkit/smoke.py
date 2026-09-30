#!/usr/bin/env python3
"""
Run every way the analyzer can be asked to run, and see that it survives.

The parity and shape tests check what comes *out* of a run. Nothing checked
that a run happens at all, and twice now a path has been broken by a change
that was tested only one way -- most recently `--mod-path` without `-q`,
which crashed on a name the quiet path never reaches, so every test passed
and the window the user actually clicks did not.

Most of these are one flag away from each other on purpose. A flag that only
changes what is printed still runs code, and the code it runs is the code
nobody exercises.

    python3 testkit/smoke.py "/path/to/saves" [--mod "/path/to/mod"]

Each case runs the analyzer in a fresh process and passes if it exits 0 and
prints no traceback. Says nothing on success beyond a tick per case.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYZER = os.path.join(HERE, "vic2_analyzer.py")


def cases(saves, mod, out, analyzer, game=None):
    """
    (name, argv, wants) for everything worth running, quiet and loud.

    The quiet ones are here too. `-q` and no `-q` take different branches --
    that is the whole reason this file exists -- so a case that only appears
    in one of them is a case only half tested.

    Most carry `--rebuild`. Without it the stamp answers the second run
    with the report the first one wrote, in a hundredth of a second, and
    the case tests nothing at all -- which is what `--no-cache`, `--jobs 1`
    and `--jobs 2` were quietly doing. The cases that are *about* the skip
    say so in their names.

    `wants` is what the run has to say for itself. Exiting 0 is not enough
    for a diagnostic: `--inventions` and `--check-inventions` both exited 0
    while answering zero of everything, because the trim had taken the
    fields they read out from under them, and `--explain-mob` exited 0 after
    answering "nothing has changed" and explaining nothing. Each of those is
    a run that looked fine from the outside.

    A `wants` entry is a string the output must contain, or a `not:` prefix
    for one it must not. `refuses` marks a case whose non-zero exit is the
    right answer.
    """
    base = [sys.executable, analyzer, saves, "--out", out]
    if game:
        base += ["--game-root", game]
    without_game = [sys.executable, analyzer, saves, "--out", out]
    unchanged = "Nothing has changed"
    got = [
        ("plain, quiet", base + ["-q"], []),
        ("plain, verbose", base + ["--rebuild"], ["nation-rows across"]),
        ("rebuild", base + ["--rebuild", "-q"], []),
        ("unchanged (the skip)", base + ["-q"], []),
        ("unchanged, verbose", base, [unchanged]),
        ("no cache", base + ["--no-cache", "--rebuild", "-q"], []),
        ("one worker", base + ["--jobs", "1", "--rebuild", "-q"], []),
        ("two workers", base + ["--jobs", "2", "--rebuild", "-q"], []),
        ("no html", base + ["--no-html", "-q"], []),
        ("split payload", base + ["--split", "--rebuild", "-q"], []),
        ("tag filter", base + ["--tags", "ENG", "FRA", "--rebuild", "-q"], []),
        ("tag filter, verbose", base + ["--tags", "ENG", "--rebuild"],
         ["nation-rows across"]),
        ("min pop", base + ["--min-pop", "1000000", "--rebuild", "-q"], []),
        ("player nations", base + ["--player-nations", "ENG", "--rebuild",
                                   "-q"], []),
        ("mob rate", base + ["--mobilisation-size", "0.05", "--rebuild",
                             "-q"], []),
        ("mob types", base + ["--mob-types", "farmers", "labourers",
                              "--rebuild", "-q"], []),
        ("mob includes occupied", base + ["--mob-include-occupied",
                                          "--rebuild", "-q"], []),
        ("pop per regiment", base + ["--pop-per-regiment", "1000",
                                     "--rebuild", "-q"], []),
        ("unmodded, explain mob", base + ["--explain-mob", "ENG"],
         ["Mobilisation size for ENG", "TOTAL"]),
        ("inventions needs an install", without_game + ["--inventions", "ENG"],
         ["refuses", "Say where Victoria II is installed"]),
        ("explain mob pool", base + ["--explain-mob-pool", "ENG"],
         ["Mobilization pool for ENG", "not:" + unchanged]),
        ("peek", base + ["--peek"], []),
        ("verify", base + ["--verify"], []),
    ]
    if mod:
        got += [
            ("mod, quiet", base + ["--mod-path", mod, "--rebuild", "-q"], []),
            # The one that crashed. It reaches `index_coverage`, which the
            # quiet path never calls.
            ("mod, verbose", base + ["--mod-path", mod, "--rebuild"],
             ["Invention indices decoded", "Mod scan:"]),
            ("mod, unchanged", base + ["--mod-path", mod], [unchanged]),
            # These four print something about a nation. Each has to reach
            # the saves to do it, so none of them may be answered with the
            # report that is already sitting there.
            ("mod, explain mob", base + ["--mod-path", mod, "--explain-mob",
                                         "ENG"],
             ["Mobilisation size for ENG", "TOTAL", "not:" + unchanged]),
            ("mod, explain mob pool", base + ["--mod-path", mod,
                                              "--explain-mob-pool", "ENG"],
             ["Mobilization pool for ENG", "not:" + unchanged]),
            ("mod, inventions", base + ["--mod-path", mod, "--inventions",
                                        "ENG"],
             ["this save names", "not:names 0 of them", "not:" + unchanged]),
            ("mod, check inventions", base + ["--mod-path", mod,
                                              "--check-inventions"],
             ["indices held often enough to judge",
              "not:only 0 indices", "not:" + unchanged]),
            ("mod, map", base + ["--mod-path", mod, "--map-scale", "2",
                                 "--rebuild", "-q"], []),
            ("mod, one worker", base + ["--mod-path", mod, "--jobs", "1",
                                        "--rebuild", "-q"], []),
        ]
    return got


def cross_cases(saves, mod, out, holding, analyzer):
    """
    The same, for --cross, which wants a folder of campaign folders.

    Built here rather than asked for: one campaign split in two is not a real
    cross-campaign comparison, but it is two campaigns as far as every line
    of code between here and the report is concerned.
    """
    files = sorted(f for f in os.listdir(saves) if f.endswith(".v2"))[:8]
    if len(files) < 4 or not mod:
        return []
    for i, name in enumerate(files):
        side = "alpha" if i % 2 else "beta"
        os.makedirs(os.path.join(holding, side), exist_ok=True)
        os.symlink(os.path.join(saves, name),
                   os.path.join(holding, side, name))
    base = [sys.executable, analyzer, holding, "--out", out, "--cross",
            "--mod-path", mod]
    return [("cross, quiet", base + ["--rebuild", "-q"], []),
            ("cross, verbose", base + ["--rebuild"], []),
            ("cross, primary named", base + ["--primary", "alpha",
                                             "--rebuild", "-q"], [])]


def run(name, argv, wants, width):
    """One case. True if it lived and said what it was supposed to."""
    refuses = "refuses" in wants
    began = time.monotonic()
    done = subprocess.run(argv, capture_output=True, text=True)
    took = time.monotonic() - began
    out = done.stdout + done.stderr
    why = []
    if "Traceback (most recent call last)" in out:
        why.append("it crashed")
    elif refuses and done.returncode == 0:
        why.append("it was supposed to refuse and did not")
    elif not refuses and done.returncode != 0:
        why.append("exit %s" % done.returncode)
    for want in wants:
        if want == "refuses":
            continue
        if want.startswith("not:"):
            if want[4:] in out:
                why.append("said %r and should not have" % want[4:])
        elif want not in out:
            why.append("never said %r" % want)
    print("  %-*s %s  %5.1fs" % (width, name, "FAIL" if why else "ok  ", took))
    if why:
        print("      %s" % " ".join(argv[2:]))
        for one in why:
            print("      └ %s" % one)
        for line in out.strip().splitlines()[-10:]:
            print("      | %s" % line)
    return not why


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("saves", help="a folder of .v2 saves")
    ap.add_argument("--mod", default="", help="a mod folder, if there is one")
    ap.add_argument("--only", default="", help="run cases matching this text")
    # So one tree's cases can be run against another tree's code, which
    # is how a case is shown to fail on the version it was written for.
    ap.add_argument("--analyzer", default=ANALYZER,
                    help="the vic2_analyzer.py to run")
    args = ap.parse_args()

    holding = tempfile.mkdtemp(prefix="vic2smoke")
    out = os.path.join(holding, "out")
    xout = os.path.join(holding, "xout")
    xin = os.path.join(holding, "campaigns")
    try:
        import matching
        game = matching.a_vanilla(os.path.join(holding, "vanilla"))
        todo = cases(args.saves, args.mod, out, args.analyzer, game)
        # Explicit mods carry their own install; do not pair them with the
        # synthetic vanilla install used by the otherwise mod-free cases.
        for _name, argv, _wants in todo:
            if "--mod-path" in argv:
                at = argv.index("--game-root")
                del argv[at:at + 2]
        todo += cross_cases(args.saves, args.mod, xout, xin,
                            args.analyzer)
        if args.only:
            todo = [c for c in todo if args.only.lower() in c[0].lower()]
        if not todo:
            print("nothing matched %r" % args.only)
            return 2
        width = max(len(n) for n, _a, _w in todo)
        print("%d case(s)\n" % len(todo))
        bad = [n for n, argv, wants in todo if not run(n, argv, wants, width)]
        print()
        if bad:
            print("FAILED: %s" % ", ".join(bad))
            return 1
        print("every way of running it survives")
        return 0
    finally:
        shutil.rmtree(holding, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

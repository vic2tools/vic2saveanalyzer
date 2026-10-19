#!/usr/bin/env python3
"""
The rules the window and the scanner both implement, held to each other.

The window asks two things before a run, so that a wrong folder is a
dialog there and then rather than a line in a log: which install and which
mod the run is read on (`report_tab.settle_game`), and which folders hold
campaigns, which decides whether the run is `--cross`
(`report_tab.campaigns_in`). The scanner answers both again for the run
itself (`settle_game` in `scanner/src/front/mod.rs`, `campaigns_in` in
`scanner/src/front/survey.rs`). Each case here asks both sides the same
question and fails on any difference.

    python3 testkit/pairs.py

- `settle_game`: the window's folder pair, said the way the scanner says it
  ("Victoria II at <install>, with <mod>."), or its refusal, which must be
  the start of the scanner's.
- `campaigns_in`: each campaign's name and count of saves, in order, against
  the "Campaigns found under" block a verbose `--cross` run prints.

The save-date sort has no pair. The scanner orders a run's saves by the date
inside each (`front::in_date_order`); nothing in Python sorts saves by
in-game date for a run. The keeper sorts its own file names, which it wrote
with the date in them, and only to find the newest it holds.
"""
import os
import re
import shutil
import sys

import kit
import fixtures
import frontcheck


def settle_cases(holding):
    """(what, --mod-path or None, --game-root or None), on fixture installs."""
    game = fixtures.a_vanilla(os.path.join(holding, "game"))
    mod = fixtures.a_mod(os.path.join(game, "mod", "Mod"))
    other = fixtures.a_vanilla(os.path.join(holding, "other"))
    away = os.path.join(holding, "elsewhere", "mod", "Away")
    shutil.copytree(mod, away)
    return [
        ("a mod in an install", mod, None),
        ("a mod in an install, the install named", mod, game),
        ("a mod outside any install", away, None),
        ("an install named as its own mod", game, None),
        ("a mod in another install than --game-root", mod, other),
        ("a game root that is not an install", None, away),
        ("the game alone", None, game),
        ("no game root and no mod", None, None),
    ]


def scanner_says(saves, out, env, mod, game):
    """The scanner's answer: ("settled", its line) or ("refused", its sentence)."""
    argv = [saves, "--out", out, "--rebuild"]
    argv += ["--mod-path", mod] if mod else []
    argv += ["--game-root", game] if game else []
    done = kit.analyze(*argv, env=env)
    if done.returncode:
        return "refused", done.stderr.strip()
    line = next((l for l in done.stdout.splitlines() if l.startswith("Victoria II at ")), None)
    return "settled", line


def window_says(report_tab, mod, game):
    """The window's answer, said the way the scanner says it."""
    try:
        mod_path, home = report_tab.settle_game(mod, game)
    except ValueError as refused:
        return "refused", str(refused)
    return "settled", "Victoria II at %s, %s" % (
        home, "unmodded." if report_tab.is_install(mod_path)
        else "with %s." % os.path.basename(os.path.normpath(mod_path)))


def settle_problems(report_tab, holding, env):
    """[what went wrong] between the two settle_games."""
    saves = os.path.join(holding, "saves")
    os.makedirs(saves)
    fixtures.a_save(os.path.join(saves, "1.v2"))
    wrong = []
    for what, mod, game in settle_cases(holding):
        window = window_says(report_tab, mod, game)
        scanner = scanner_says(saves, os.path.join(holding, "out"), env, mod, game)
        same = (window[0] == scanner[0] and
                (window[1] == scanner[1] if window[0] == "settled"
                 else (scanner[1] or "").startswith(window[1])))
        print("  %-48s %s" % (what, "ok" if same else "DIFFERS"))
        if not same:
            wrong.append("%s: the window says %s %r, the scanner %s %r"
                         % (what, window[0], window[1], scanner[0], scanner[1]))
    return wrong


def surveyed(parent, game, env):
    """[(name, saves)] from the scanner's "Campaigns found under" block."""
    done = kit.analyze(parent, "--cross", "--game-root", game, "--out",
                       os.path.join(os.path.dirname(parent), "cross-out"), "--rebuild", env=env)
    lines = done.stdout.splitlines()
    head = "Campaigns found under %s:" % parent
    if head not in lines:
        return None, (done.stdout + done.stderr)[-1500:]
    found = []
    for line in lines[lines.index(head) + 1:]:
        if not line.startswith("  ") or line.startswith("   "):
            if line.startswith("  "):
                continue                         # a campaign's own notes
            break
        name, count = re.match(r"^  (.+?) +(\d+) saves", line).groups()
        found.append((name, int(count)))
    return found, None


def survey_problems(report_tab, holding, env):
    """[what went wrong] between the two campaigns_ins."""
    game, top = frontcheck.cross_world(holding)
    single = os.path.join(top, "onlybeta")
    wrong = []
    for what, parent in (("a folder of campaigns", top), ("one campaign's own folder", single)):
        window = [(name, len(files)) for name, _path, files in report_tab.campaigns_in(parent)]
        scanner, said = surveyed(parent, game, env)
        same = window == scanner
        print("  %-48s %s" % (what, "ok" if same else "DIFFERS"))
        if not same:
            wrong.append("%s: the window finds %s, the scanner %s"
                         % (what, window, scanner if scanner is not None else said))
    return wrong


def main():
    kit.need_scanner()
    try:
        from vic2tools import report_tab
    except ImportError:
        kit.skip("needs tkinter, which the window's report tab is built with")
    with kit.holding("vic2pairs") as (holding, env):
        wrong = settle_problems(report_tab, holding, env)
        wrong += survey_problems(report_tab, holding, env)
    if wrong:
        print("\nPROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("\nthe window settles the game and finds campaigns as the scanner does")
    return 0


if __name__ == "__main__":
    sys.exit(main())

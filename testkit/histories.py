#!/usr/bin/env python3
"""
Tell one game's saves from another's by the event flags they carry.

Global event flags accumulate as a game runs, so an earlier save's flags are
all in a later save of the same game, and two different games lose many of
each other's. `savehead` holds that rule and the measured numbers behind it,
and two parts of the program lean on it:

- the keeper, which files an autosave under the campaign it continues, and
  must put a second game played as the same nation from the same start in a
  folder of its own rather than into the first game's;
- `--cross`, whose `history_breaks` (`scanner/src/front/cross.rs`) names a save in a campaign folder that
  cannot share a history with the saves after it.

Each used to carry its own copy of the rule, and neither copy had a check.

    python3 testkit/histories.py
"""

import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import fake_game                                           # noqa: E402
import keeper                                              # noqa: E402

# Another game's history: as many flags as the fake game grants, and none of
# the same ones.
OTHER = ["other_game_flag_%02d" % i for i in range(len(fake_game.FLAGS))]


def two_games_one_nation(holding):
    """
    [what went wrong] when the keeper is handed a second game, played as the
    same nation from the same start, after the first.
    """
    saves = os.path.join(holding, "save games")
    out = os.path.join(holding, "kept")
    os.makedirs(saves)
    args = keeper.Options(saves=saves, out=out, once=True)
    for flags, year in ((fake_game.FLAGS, 1840), (OTHER, 1841)):
        for month in (1, 2, 3):
            fake_game.rotate(saves)
            with open(os.path.join(saves, "autosave.v2"), "wb") as fh:
                fh.write(fake_game.a_save(year, month, "PRU", 20000,
                                          n=12, flags=flags))
            keeper.watch(args, report=lambda line: None, tally=[0, 0])
    folders = sorted(os.listdir(out))
    print("  two games as PRU from 1836 -> %s" % ", ".join(folders))
    if len(folders) != 2:
        return ["two games played as the same nation went into %d folder(s), "
                "not two: %s" % (len(folders), ", ".join(folders))]
    return []


def a_stray_save(holding):
    """
    [what went wrong] when `--cross` surveys a campaign folder whose first
    save is from another game, beside one that is all one game.
    """
    import matching
    import subprocess
    parent = os.path.join(holding, "campaigns")
    for name, first in (("stray", OTHER), ("whole", fake_game.FLAGS)):
        folder = os.path.join(parent, name)
        os.makedirs(folder)
        for n, (flags, month) in enumerate(((first, 1), (fake_game.FLAGS, 2),
                                            (fake_game.FLAGS, 3), (fake_game.FLAGS, 4))):
            with open(os.path.join(folder, "save%d.v2" % n), "wb") as fh:
                fh.write(fake_game.a_save(1840, month, "PRU", 20000, n=12, flags=flags))
    game = matching.a_vanilla(os.path.join(holding, "Victoria 2"))
    env = dict(os.environ, TMPDIR=os.path.join(holding, "tmp"))
    os.makedirs(env["TMPDIR"])
    done = subprocess.run([sys.executable, os.path.join(HERE, "vic2_analyzer.py"), parent,
                           "--cross", "--game-root", game, "--out", os.path.join(holding, "out"),
                           "--no-html", "--no-cache"], capture_output=True, text=True, env=env)
    said = done.stdout + done.stderr
    if "Traceback" in said or "panicked" in said:
        return ["--cross crashed:\n" + said[-1500:]]
    survey = said.split("Reading ")[0]
    named = re.findall(r"note: (\S+) disagrees with", survey)
    print("  a folder with another game's save first -> %s named"
          % (", ".join(named) or "nothing"))
    wrong = []
    if named != ["save0.v2"]:
        wrong.append("the save from another game was not named alone: %s\n%s"
                     % (named or "nothing named", survey))
    # Under the campaign it belongs to, not wherever the survey ends.
    block = re.search(r"(?ms)^  stray .*?(?=^  \S)", survey + "  .")
    if not block or "save0.v2 disagrees" not in block[0]:
        wrong.append("the note was not said under the campaign it is about:\n%s" % survey)
    return wrong


def main():
    holding = tempfile.mkdtemp(prefix="vic2histories")
    try:
        wrong = (two_games_one_nation(os.path.join(holding, "keeper"))
                 + a_stray_save(os.path.join(holding, "cross")))
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("one game's saves are told from another's, by the keeper and by "
          "--cross alike")
    return 0


if __name__ == "__main__":
    sys.exit(main())

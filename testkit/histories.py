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
- `--cross`, whose `history_breaks` names a save in a campaign folder that
  cannot share a history with the saves after it.

Each used to carry its own copy of the rule, and neither copy had a check.

    python3 testkit/histories.py
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import cross                                               # noqa: E402
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
    [what went wrong] when `history_breaks` is shown a campaign folder whose
    first save is from another game, and one that is all one game.
    """
    folder = os.path.join(holding, "campaign")
    os.makedirs(folder)
    paths = []
    for n, (flags, month) in enumerate(((OTHER, 1), (fake_game.FLAGS, 2),
                                        (fake_game.FLAGS, 3),
                                        (fake_game.FLAGS, 4))):
        path = os.path.join(folder, "save%d.v2" % n)
        with open(path, "wb") as fh:
            fh.write(fake_game.a_save(1840, month, "PRU", 20000, n=12,
                                      flags=flags))
        paths.append(path)
    wrong = []
    named = [name for name, _worst, _of in cross.history_breaks(paths)]
    print("  a folder with another game's save first -> %s named"
          % (", ".join(named) or "nothing"))
    if named != ["save0.v2"]:
        wrong.append("the save from another game was not named alone: %s"
                     % (named or "nothing named"))
    named = [name for name, _worst, _of in cross.history_breaks(paths[1:])]
    if named:
        wrong.append("saves from one game were named as strays: %s" % named)
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

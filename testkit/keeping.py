#!/usr/bin/env python3
"""
Drive the keeper through a whole campaign, without the game and without waiting.

The keeper is the part that loses data when it is wrong. Victoria 2 keeps
three autosaves and drops the fourth, so a month the keeper misses is a
month nobody has any more -- and unlike a wrong number in a report, nothing
later can notice. It also had no test at all.

    python3 testkit/keeping.py

`fake_game.py` writes the saves and rotates them the way the game does;
this drives the pair a month at a time, synchronously, so the whole
campaign runs in a second and the answer never depends on a sleep being
long enough. It checks that every month written comes out the other side,
that nothing is copied twice, that the campaign is named after the nation
that played it, and that a nation forming another one keeps one folder
rather than starting a second.
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import fake_game                                           # noqa: E402
import keeper                                              # noqa: E402


def play(folder, out, months=18, forms_at=9, size=40000):
    """
    Play a campaign a month at a time, running the keeper after each.

    The keeper sees exactly what it would see if it were keeping up with
    the game: one new autosave, the previous two shuffled along. Running it
    between months rather than beside them is the point -- a test that
    races the game tests the sleep, not the keeper.

    Returns (what the keeper reported, [months written]).
    """
    said, written = [], []
    args = keeper.Options(saves=folder, out=out, once=True)
    tally = [0, 0]
    year, month = 1836, 1
    for n in range(months):
        tag = "GER" if n >= forms_at else "PRU"
        fake_game.rotate(folder)
        with open(os.path.join(folder, "autosave.v2"), "wb") as fh:
            fh.write(fake_game.a_save(year, month, tag, size, n))
        written.append((year, month, tag))
        keeper.watch(args, report=said.append, tally=tally)
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return said, written, tally


def catches_up(folder, out, size=40000):
    """
    [what went wrong] when the keeper runs only once every three months.

    The game keeps three: `autosave.v2`, `oldautosave.v2`,
    `olderautosave.v2`. So a keeper that is two months behind has lost
    nothing yet, and one that reads only the newest name has lost two
    without any sign of it. This writes three months with the keeper
    switched off and then runs it once; all three must arrive.
    """
    os.makedirs(folder, exist_ok=True)
    want = []
    for n, month in enumerate((1, 2, 3)):
        fake_game.rotate(folder)
        with open(os.path.join(folder, "autosave.v2"), "wb") as fh:
            fh.write(fake_game.a_save(1840, month, "PRU", size, n))
        want.append("PRU1840_%02d_01.v2" % month)

    args = keeper.Options(saves=folder, out=out, once=True)
    keeper.watch(args, report=lambda line: None, tally=[0, 0])
    got = sorted(f for files in kept_under(out).values() for f in files)
    print("  three months written with the keeper off, then one pass: "
          "%d of 3 arrived" % sum(1 for w in want if w in got))
    return ["%s was lost while the keeper was behind" % w
            for w in want if w not in got]


def kept_under(out):
    """{folder name: [file names]} for whatever the keeper made."""
    found = {}
    for name in sorted(os.listdir(out)):
        where = os.path.join(out, name)
        if os.path.isdir(where):
            found[name] = sorted(f for f in os.listdir(where)
                                 if f.endswith(".v2"))
    return found


def main():
    holding = tempfile.mkdtemp(prefix="vic2keep")
    saves = os.path.join(holding, "save games")
    out = os.path.join(holding, "kept")
    os.makedirs(saves)
    wrong = []
    try:
        said, written, tally = play(saves, out)
        found = kept_under(out)

        print("  played %d months, keeper copied %d saves into %d folder(s)"
              % (len(written), tally[0], len(found)))
        for name, files in found.items():
            print("    %s: %d files, %s .. %s"
                  % (name, len(files), files[0] if files else "-",
                     files[-1] if files else "-"))

        # One campaign, not two. The nation forms another one halfway and
        # the tag in every later save changes; the keeper follows it across
        # by the event flags the saves share.
        if len(found) != 1:
            wrong.append("expected one campaign folder, found %d: %s"
                         % (len(found), ", ".join(found) or "none"))
        else:
            name = next(iter(found))
            if "PRU" not in name or "GER" not in name:
                wrong.append("the folder is called %r; it should name both "
                             "the nation that started and the one it became"
                             % name)

        kept = sorted(f for files in found.values() for f in files)
        if len(kept) != len(written):
            wrong.append("%d months were played and %d kept"
                         % (len(written), len(kept)))
        # Named for the month they are of, so a folder sorts into the order
        # the campaign was played in.
        for (year, month, tag) in written:
            want = "%s%04d_%02d_01.v2" % (tag, year, month)
            if want not in kept:
                wrong.append("%s never arrived" % want)
        if len(set(kept)) != len(kept):
            wrong.append("something was kept twice")

        # And running again with nothing new must copy nothing.
        before = tally[0]
        args = keeper.Options(saves=saves, out=out, once=True)
        again = [0, 0]
        keeper.watch(args, report=lambda line: None, tally=again)
        if again[0]:
            wrong.append("a second pass over an unchanged folder copied %d "
                         "more" % again[0])
        else:
            print("  a second pass over the same folder copies nothing")
        if before != len(written):
            wrong.append("the keeper counted %d copies for %d months"
                         % (before, len(written)))

        wrong += catches_up(os.path.join(holding, "behind"),
                            os.path.join(holding, "behind-kept"))
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("every month played came out the other side, once, in one campaign")
    return 0


if __name__ == "__main__":
    sys.exit(main())

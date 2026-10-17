# Testing it

Checks that hold the analyzer to what it is supposed to do, a baseline of a
real campaign to compare engine changes against, a harness that proves the
checks catch the bugs they were written for, and stand-ins for the parts of
the world the analyzer talks to.

## The suite

```
python3 testkit/all.py                                   # what needs no saves
python3 testkit/all.py "/path/to/saves" --mod "/path/to/mod"
python3 testkit/all.py "/path/to/saves" --mod "/path/to/mod" --update-expected
```

Every check, what it is for and what it needs, is listed in one place:

```
python3 testkit/suite.py --list
```

A check needs some of: the scanner built (`cargo build --release` in
`scanner/`), a folder of saves and its mod, a report built from them (the
suite builds one), Firefox (run headless), a desktop for a window, the Rust
compiler, or a recorded baseline. One whose needs are not met here is
skipped and says which; it does not count against the total. A check that
fails prints its own output. Checks that share nothing run four at a time;
the ones that drive a window or a browser run alone, after them. Each runs
in a temp folder of its own, so none writes the real engine cache.

Most checks build what they run on (`fixtures.py`, `savefmt.py`) and need
only the scanner. The unit tests of the test kit itself:

```
python -m unittest discover -s testkit -p "test_*.py"
```

## Recorded answers

`frontcheck.py`, `saveshapes.py`, `mangled.py`, `crossrows.py`, `modread.py`
and `enginecheck.py` hold each run -- the exit status, stdout and stderr,
every file it wrote, and the page as what it carries (its payload as indented
JSON, its state snapshots decoded, the page around them as a difference from
the template) -- to an answer recorded in `testkit/expected/` (`expected.py`).
After a deliberate change, `--update-expected` records the present answers
and `git diff testkit/expected` shows what changed. Read that diff: a record
is only as right as the run it was taken from.

## A campaign's baseline

The checks above run on worlds made up here. A real campaign meets more
than they do, so an engine change is also compared with a campaign's
verified answers:

```
python3 testkit/baseline.py record  "/path/to/saves" --mod "/path/to/mod" --into ~/vic2-baseline [--match "NET*.v2"]
python3 testkit/baseline.py compare "/path/to/saves" --mod "/path/to/mod" --from ~/vic2-baseline
```

`record` picks eight saves spaced through the campaign and the last, writes
down exactly which (name, size, SHA-256), and keeps two dozen runs' answers
and the mod as the program reads it. `compare` finds those saves by name --
saves added since do not matter -- and holds a run now to every answer. A
save missing or changed under its name is named and nothing is compared.
`--ignore payload.wars[].side_losses` leaves out a payload key a change
removes on purpose.

Record a baseline before changing the engine, keep it outside the
repository (it is your campaign), and set `VIC2_BASELINE` to it: the suite
and the mutation run then use it.

## Does a check catch its bug?

```
python3 testkit/mutate.py --saves "/path/to/saves" --mod "/path/to/mod" [--baseline DIR] [name ...]
python3 testkit/mutate.py --dry       # does every mutation still find its text?
```

`mutations.py` lists bugs that were fixed, each with the check that should
catch it. `mutate.py` builds HEAD's scanner in a worktree of HEAD, puts each
bug back there, rebuilds the scanner if the bug is in it (a light build, a
few seconds), runs the check, and says CAUGHT, BLIND (the check passed with
the bug in), TIMEOUT, SKIPPED, NOAPPLY (the code moved: move the mutation),
NOBUILD or UNTESTED, with what an untested one needs. The full run takes
about ten minutes without a baseline and about eighteen with one, since the
sixteen mutations only a real campaign catches each run the campaign's two
dozen cases. Commit first: it tests HEAD. A fix that comes
with a check comes with a row in `mutations.py`, run once by hand with its
failure read.

## On Windows

Every check holds on Windows. Firefox is found in Program Files by
`browser.py`, since its installer does not put it on PATH. `frontcheck.py`
locks a save by holding it open with no sharing. Windows cannot make a
symbolic link without Developer Mode or administrator rights, so
`engine_runtime.py` makes a junction instead for the fixture builder's
refusal of linked folders; only its second half, a link to a file, is not
run there. What a run prints with backslashes is held to the record's
slashes by `expected.stand_in_for`.

## The stand-ins

For working on this on a machine that has no saves, or no Windows. Neither
is needed to use the analyzer, and neither is in the executable.

**`fake_game.py`** pretends to be the game: it writes autosaves into a folder
and rotates them the way Victoria 2 does, three deep and then gone. Halfway
through, Prussia forms Germany and every later save says `GER`, so the
keeper's folder should rename itself to `PRU-GER 1836` rather than starting
a second campaign.

```
python3 testkit/fake_game.py ~/vic2-testkit/saves --months 12 --every 3
```

Then point **Keep autosaves** at that folder and press Start. On anything
but Windows the keeper polls, so leave `--every` above the poll interval.

**`fake_save.py`** writes one save-shaped file in roughly a real save's
proportions, and with `--campaign N` a campaign of N monthly saves, to
measure the analyzer on a campaign nobody here owns:

```
python3 testkit/fake_save.py /tmp/base.v2 --mb 2 --campaign 1000
python3 vic2_analyzer.py /tmp/base-campaign --out /tmp/out
```

**`mock_host.py`** pretends to be the report host in `host/`, with the same
two endpoints and the same checks, reading the Content-Security-Policy out
of `worker.js` so the two cannot drift apart.

```
python3 testkit/mock_host.py 8753
```

Then put `http://127.0.0.1:8753` into **Share → Upload to a report host**.

**`looks.py`** takes a picture of a report for a person to look at; nothing
passes or fails on it.

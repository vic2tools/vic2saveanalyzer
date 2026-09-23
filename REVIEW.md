# Adversarial review of `32ce85d..403dcc4`

An independent review of the four-job architecture pass. The session that wrote
those six commits also wrote the checks that say they are fine, so nothing here
takes either at its word: every claim below was put to a machine, and the way it
was put is written down so it can be repeated.

**Method.** Twenty-one bugs were put back into a worktree of `403dcc4`, one at a
time, and the check that claims to catch each one was run. A check that still
passes with the bug in place is not doing its job. The worktree had
`scanner/target/release/vic2scan` copied into it first, so nothing here is the
"HEAD in Python against yours in Rust" comparison the handoff warns about.

**The headline.** The production code is in good shape and the four jobs did
what they said. The problem is on the other side: **six of the twenty-one bugs
went straight through the suite**, and one of them changes a shipped CSV on 114
lines while all 24 checks still pass.

---

## 1. `testkit/crossrows.py` is blind to four of the five bugs it names

This is the most serious finding, because it is the newest check and the one
standing guard over the most recently fixed bug.

`crossrows.py` compares the `--cross` path against the report path. That is the
right idea, but it is *only* a comparison. The four jobs merged those two paths
into one `finish_nations`, so breaking the behaviour now breaks **both sides
at once**, the two readings still match, and the check still passes.

Put back, one at a time, into the merged code:

| bug put back | check says |
|---|---|
| the mod's `POP_SIZE_PER_REGIMENT` is ignored | **caught** |
| the mod's pop list overrides `--mob-types` instead of deferring | **passes** |
| only `human=yes` counts, so `--player-nations` goes unread | **passes** |
| the filter silently raises `--min-pop` to 1 | **passes** |
| the save's own `player=` marker goes unread | **passes** |

Only the first is caught, and only because it is the one case with an
assertion about the *answer* rather than about the two paths agreeing:

```python
if cross_spec.pop_per_regiment != ALPHA_REGIMENT:
```

The other four cases are named `--mob-types honoured`, `--player-nations
honoured` and `--min-pop honoured`, and they print `ok`. What they actually
assert is that the two paths are *equally wrong*. The names promise more than
the code delivers, which is worse than no check, because the printed `ok` is
read as "the flag is honoured".

The commit message's claim — "Putting any one of the five divergences back
fails it; all five were checked that way" — is true only if you put the
divergence back by **re-duplicating the code first**. As a guard against
someone re-splitting the two paths, the check works. As a guard against the
five behaviours it names, four fifths of it is decorative.

### 1b. The `--min-pop` case has no test subject at all

Worse, and independent of the above. The case is built around PRU:

> `PRU` holds no province, so it has no people at all. The report measures it
> — `--min-pop` defaults to nought — and the cross path used to raise that
> floor to one behind the caller's back.

PRU never arrives. `readsave.analyze_save` ends with

```python
live = {tag: nat for tag, nat in nations.items()
        if nat["provinces"] > 0 or nat["total_pop"] > 0}
```

which drops released-nation stubs — and PRU, having neither land nor people, is
exactly that shape. Measured on the unmutated tree, both paths report `['ENG',
'FRA']` and PRU is in neither. So the `--min-pop 0` case compares two nations
of 40,500 and 22,000 people against a floor of nought: nothing it does could
ever fail.

This is the case `testkit/savefmt.py` documents from the other direction — a
check that passed for an entirely different reason for months. To make PRU a
real subject it needs to own a province with no pops in it, so that
`provinces > 0` keeps it alive while `total_pop` stays at nought.

## 2. Nothing catches a change to a shipped number's *type*

`nation._add_if` exists for one reason, and its comment says so:

> `naval_base_levels` starts as int 0 and is left alone by a province with no
> naval base, so a nation without one carries `0` and not `0.0`. The report
> never notices; the CSV writes the number out and does.

Changing that one rule from `_add_if` to `_add`:

- **all 24 checks pass**, including `record.py` and `parity.py`
- `nations_timeseries.csv` **differs on 114 lines**, `0` becoming `0.0`

Both checks are blind for the same reason: in Python `0 == 0.0` is true, so
every value comparison in the suite steps straight over it. The only thing that
catches this is the "nine outputs byte-identical" step in the handoff contract,
which is a person running two commands and comparing, not a check.

The author knew the risk and wrote the comment. What is missing is anything
that enforces it.

## 3. `record.py` checks for a field claimed twice, but only within one table

`SCANNED_PROVINCES` and `SCANNED_COUNTRY` both fold into the same nation
record. Pointing a province rule at a country field —

```python
("ports", "states", _add),
```

— is accepted without complaint. Within one table the check works (verified:
pointing `armies` at `brigades` is caught). Across the two it does not look.
Both folds write the same dict, so the two tables must be disjoint.

## 4. `mod_defaults` cannot tell "left alone" from "explicitly asked for"

A real bug in shipped behaviour, not a test problem.

`mod_defaults` decides whether the caller wants the mod's numbers by comparing
the value it was given against the built-in default:

```python
if ("POP_SIZE_PER_REGIMENT" in defines
        and pop_per_regiment == POP_SIZE_PER_REGIMENT):
```

So `--pop-per-regiment 3000` on the command line is indistinguishable from not
passing the flag, and the mod overrides it. Measured against a mod whose
`defines.lua` says 1000:

| what was asked | what was used |
|---|---|
| nothing | 1000 |
| `--pop-per-regiment 3000` | **1000** |
| `--pop-per-regiment 2000` | 2000 |
| `--mob-types craftsmen farmers labourers` | **the mod's list** |
| `--mob-types farmers` | farmers |

The docstring says these "fill in what the caller left alone and give way to
`--pop-per-regiment` and `--mob-types`". They give way to every value except
the one the flag shares with the default. Someone comparing a modded campaign
against vanilla numbers — which is the obvious reason to type that flag — gets
the mod's numbers and no warning.

The standard fix is for argparse to default these to `None` and for
`mod_defaults` to read `None` as "not given", so the sentinel is the absence of
a value rather than a value that happens to match.

## 5. `keep_pools` is protected only by the order of two lines

`finish_nations` keeps a nation's raw mobilizable pools when `spec.keep_pools`
is set. `_finish_save`, the worker-side wrapper, then drops every name in
`SPENT_ON_FINALIZE` — and `mobilizable_pops` is the first of them. So
`_finish_save` would silently undo `keep_pools`.

It never does, because ninety lines apart:

```python
keep_whole = keep_pools or bool(args.explain_mob)
...
in_workers = not keep_whole      # and _finish_save is only used when in_workers
```

That is correct today and nothing asserts it. Two expressions of one fact, held
together by reading order.

## 6. `Mod.__getstate__` / `__setstate__` are machinery this Python does not need

Since 3.11 `object.__getstate__` handles `__slots__` on its own; this machine
runs 3.14. Removing the two hand-written methods was measured against the real
mod:

| | size | dump | load |
|---|---|---|---|
| hand-written (list) | 298.8 KB | 2.0 ms | 2.5 ms |
| default (slots dict) | 299.4 KB | 1.6 ms | 2.2 ms |

Twelve lines buying 0.6 KB, and marginally slower. The disk cache is keyed on a
hash of `mod_reader.py`'s own source, so changing this invalidates old entries
by itself.

**Decided: left in place.** Dead weight is still not worth removing here. The
measurement says the gain is zero — the default form is very slightly *larger*
— and deleting them makes the program quietly require Python 3.11 on the
Windows machine that builds `dist/vic2saveanalyzer.exe`, which cannot be tested
from this one. Nothing in the tree states a minimum version. Zero gain against
an untestable floor is not a trade worth making.

**On the wider question — would a dataclass do the same work with less?** No,
and the measurement says why. A generated `__repr__` on `Mod` would print
**348,505 characters**; the hand-written one prints 53:

```
<Mod Modus Omnino Demens 1.6, 150 techs, 4 inventions>
```

So `repr=False` and a custom `__repr__` survive either way. And `MOD_FIELDS` as
an eleven-line tuple of names would become thirty-seven annotated declarations.
The dataclass is the bigger object, not the smaller one. `__slots__` is the
right call here; only the pickle pair is dead weight.

## 7. The fold table: earning its keep, with one column of pure redundancy

`nation.py` went 317 → 596 lines on a 51-row table and 17 rule functions. The
brief asked whether this is "generic magic hiding simple structure".

**Mostly it is not, and the evidence is that it works.** Five of the seven ways
of breaking the table were caught by `record.py` — an undeclared field, a
missing rule, a field claimed twice, a container replaced instead of filled, a
name drifting from `scanner/src/country.rs`. Straight-line code in `fastscan`
could not be checked that way at all, and `fastscan` lost 104 lines and no
longer contains the string `nat[`. That is a real trade, not a wash.

Two things are worth saying against it:

**The field column is redundant in 48 of 51 rows.** Every entry is
`(wire key, record field, rule)` and the first two are the same string except
for three deliberate renames — `cores`→`core_provinces`,
`occupied`→`occupied_provinces`, `colonial`→`province_colonial`. Letting the
field default to the key, with those three in a small rename map, drops 48
repeated strings.

**Nine of the seventeen rules are used exactly once**: `_add_if`, `_highest`,
`_pairs_extend`, `_pairs_put_interned`, `_replace`, `_replace_list_interned`,
`_replace_set_interned`, `_replace_dict_interned`, `_extend_interned`.

The tempting move is to collapse the four `_replace*` rules into one that picks
its container from whatever `blank_nation` put there. **That would be a
mistake** and it is worth writing down so it is not suggested again: it
replaces four named, checkable decisions with one function that infers a data
shape at runtime, which is precisely the magic the table is supposed to
prevent. A single-use rule with a name is not waste — it is the unit
`record.py` checks. Leave the seventeen alone.

## 8. File sizes

Flagged because the review asks for it, not because this diff caused it. Three
of these were already far over any sane threshold before the range started:

| file | before | after |
|---|---|---|
| `vic2_analyzer.py` | 2497 | 2545 |
| `mod_reader.py` | 2159 | 2270 |
| `readsave.py` | 1013 | 1102 |
| `nation.py` | 317 | 596 |
| `fastscan.py` | 423 | **319** |

No file crossed 1000 lines because of this diff. `nation.py` at 596 is the
newest structure and the one with room left.

**Where the five new functions belong.** `mod_defaults`, `finish_spec`,
`players_in`, `kept_by` and `finish_nations` went into `vic2_analyzer.py`.
`kept_by` and `players_in` are pure functions of a nation and a save's meta and
would sit naturally in `nation.py`, which already owns that record and imports
nothing of ours. `finish_nations` cannot follow them: it calls `finalize`,
`rate_for` and `save_world`, all of which live in `vic2_analyzer.py`, and
moving it would create the import circle `nation.py` exists to avoid. So the
honest answer is that two of the five could move and three could not, and
moving two functions is not worth a new module.

## Two things left alone, as instructed

`template.py` and the eager report stamp were not touched and are not findings.
Both are recorded as deliberate in `HANDOFF.md`, and the reasoning holds: the
stamp's predecessor was a hand-written list of five filenames that was wrong
within a day, and splitting `template.py` trades no plumbing at all for
PyInstaller data files and `sys._MEIPASS` handling on a platform this machine
cannot test.

## What was checked and found sound

So the record is not only complaints. These were attacked and held up:

- **`record.py`** caught 5 of 7 drift mutations (see §3 and §2 for the gaps).
- **`caching.py`** caught all five ways of making the cache key and the parse
  state disagree — an `apply` that forgets a global, a `register_pop_types`
  that accumulates again, and a key that stops naming the mod, the pop types or
  the mobilizable types.
- **`mobrate.py`** caught both halves of the `Mod` rule: a mod answering
  `index_base` before anyone decoded, and a mod born claiming it had been.
- **`parity.py`** caught the scanner being switched back on during the "slow"
  read. The guard on the guard works.
- **`Reading`** is not a thin wrapper. It is the only thing holding the cache
  key and the three parser globals to one state, and `caching.py` proves it.
- The report stamp's unresolved `args.pop_per_regiment` looked like a staleness
  hole — the stamp is computed before `main` writes the mod's numbers back onto
  `args` — but `mod_signature` hashes every file in the mod folder by size and
  mtime, so editing `defines.lua` rebuilds the report anyway. Not a bug.

## Ranked, if only some of this gets done

1. **§1 + §1b** — `crossrows.py`, four of five cases asserting nothing and one
   with no subject. Newest check, most recently fixed bug.
2. **§2** — nothing catches a shipped number changing type. 114 CSV lines moved
   with 24/24 passing.
3. **§4** — `--pop-per-regiment 3000` silently ignored. The only finding a user
   could hit without touching the code.
4. **§3** — cross-table field collision unchecked.
5. **§5**, **§6**, **§7 field column** — tidying, no behaviour at stake.

---

## What was done about it

`bd0d9c2` fixes §1, §1b, §2, §3 and §4 and leaves §5, §6 and §7 as they are.
Re-running the harness against that commit:

```
22 mutations: 22 caught, 0 BLIND
```

against 15 of 21 before it. The six that used to go through are the four
`crossrows.py` cases, the cross-table collision, and the naval-base int. The
twenty-second is new: it puts back the `--pop-per-regiment` bug from §4.

Still open, and all of them cosmetic:

- **§5** `keep_pools` and `in_workers` are still two expressions of one fact
  held together by reading order. Correct today; nothing asserts it.
- **§6** decided against, above.
- **§7** the fold table's field column still repeats the wire key in 48 of 51
  rows. The seventeen rules should stay as they are.
- `nation._unknown` rebuilds a constant key set on every nation of every save.
  Hoisting it is 2.7x faster per call and saves 12 ms on a campaign of 103
  saves, which is nothing against a 1.6 s parse. Worth doing because it is
  simpler, not because it is faster — and not worth doing on its own.

### How to re-run any of this

```bash
git worktree add /tmp/mut HEAD
mkdir -p /tmp/mut/scanner/target/release
cp scanner/target/release/vic2scan /tmp/mut/scanner/target/release/
python3 testkit/mutate.py --tree /tmp/mut --saves "/path/to/saves"
```

The scanner copy is not optional: a fresh worktree has no `scanner/target/`,
so every save is read in Python and `parity.py` has nothing to compare.

---

## 9. The parse cache key did not hash `nation.py`

Found after the review above, and the worst thing in this file: it serves
wrong numbers from an ordinary run, and nothing in the suite noticed.

A parsed save is cached under a key that includes a hash of the code that
parsed it, so that editing the parser throws the old entries away. That code
was six files named by hand in `_parser_fingerprint`: `vic2_analyzer.py`,
`readsave.py`, `v2parse.py`, `fastscan.py`, `tech_groups.py`, `cacheio.py`.
Commit `549fd6e` then moved the fold that fills every parsed save --
`fold_provinces`, `fold_country`, the rules table, `blank_nation`,
`COUNTRY_SCALARS` -- out of `fastscan.py`, which was on the list, into
`nation.py`, which was not.

**The experiment**, on `f09e2f4`, with `TMPDIR=/tmp/nc` so the real cache was
not touched. Warm the cache on the 103-save campaign under the mod. Change
one fold rule in `nation.py` -- `_add_if` to `_add` on `naval_base_levels`,
the one §2 is about. Run again with the cache on and without `--rebuild`.

| | `nations_timeseries.csv` |
|---|---|
| the report rebuilt? | yes -- the stamp hashes every `.py` and saw the edit |
| against the code *before* the edit | **identical** |
| against `--no-cache` of the same code | **1,999 of 4,271 rows differ**, all in `naval_base_levels` |

So the report was rebuilt, and rebuilt out of parses the old rule had made:
numbers from the last time somebody looked, which is the one thing the stamp
exists to prevent. The shipped executable is not affected -- frozen, the key
covers the whole executable -- but every run from source was.

It also meant the handoff contract could not see it. Step 1 ran the nine
outputs *with* the cache, so for any edit to `nation.py` it compared a run
against the old parses with a run against the old parses, and said
"byte-identical". The contract now runs both sides with `--no-cache`.

On the figure: §2 and the brief that reported this said 114 lines. With
`--no-cache` on both sides, with the mod or without it, the same rule change
moves 1,999. A comparison made with the cache on -- which is what the
contract did at the time -- undercounts it for exactly the reason in this
section.

**Fixed** by deriving the list rather than writing it.
`cacheio.sources_reached` follows imports from `readsave.py` -- including
the ones made inside a function, since `readsave` reaches `fastscan` that way
and `fastscan` reaches `nation` -- and the key hashes what it finds, plus the
file that writes the entry and `cacheio.py`. It reads import lines off the
source rather than parsing it, because a real parse costs 12 ms on the path
of a run with nothing to do, which takes 80 ms in all; the line scan costs
under one, and agrees with the parsed walk on all nineteen modules.

The same experiment after the fix: the cached run matches `--no-cache` on
every row, and the cache stands a second generation up beside the first
(207 entries against 104), as it should.

**The check** is in `testkit/caching.py` and does not read the list. It
edits every file of the program in turn, in a copy, and watches which edits
move the key: they must be exactly what `readsave` reaches (walked off the
syntax tree, the same walk `packing.py` uses) plus the two files that write
an entry. Too few is this bug; too many is the other mistake INTERNALS
records, a key that throws every cached save away for a reworded label in
`explain.py`. `testkit/mutate.py` has a mutation for each -- the key put
back to the six hand-written files, and the key walked from the analyzer
instead of the reader -- and both are caught.

`mod_reader._reader_fingerprint` is also a hand-written list: itself,
`v2parse.py`, `cacheio.py`. It is complete today, because those are the only
files of ours `mod_reader` imports, so it was left alone. It is the same
shape of hazard, and `sources_reached(__file__)` is the one-line fix the day
it is not.

## 10. The harness counted five mutations as caught without running the check

`testkit/mutate.py` said 22 of 22 caught. Five of them were not tested at
all.

The five `reading-*` mutations name `caching.py` as their catcher and were
declared to want the save folder, so the harness ran
`python3 testkit/caching.py "/path/to/saves"`. `caching.py` is a `unittest`
script. `unittest.main()` read the folder as the name of a test to run,
found no such test, and failed -- every time, before any real test had been
tried, bug or no bug:

```
ERROR: /path/to/saves/1870s (unittest.loader._FailedTest...)
AttributeError: module '__main__' has no attribute '/path/to/...'
Ran 1 test in 0.000s
```

A check that fails with no bug in place fails for some reason of its own, so
its failing with a bug in place is not evidence of anything. The verdicts
said "caught" because the harness only ever looked at whether the check
failed.

Run the way the suite runs it, with no argument, `caching.py` does catch all
five -- each one fails a named test for the right reason -- so what §"What
was checked and found sound" says about `caching.py` holds. It was not the
harness that showed it.

**Fixed** in `testkit/mutate.py`: `caching.py` is run with no argument, and
every check is first run on the tree with no bug in it and must pass there.
One that does not is reported `CONTROL FAILED`, and its mutations `UNTESTED`
rather than caught. The harness also exits non-zero unless every mutation is
caught. Re-run on the tree with both fixes: 24 mutations, 24 caught.

## 11. `testkit/spawned.py` passed with no worker started under spawn

Found while moving the parallel reader into `readfolder.py`, the move for
which this is the check that matters: Windows starts every worker as a fresh
interpreter, so everything handed to one has to be found again by name.

`spawned.py` builds the campaign under fork and under spawn and compares the
files. But a pool that will not start is not an error to the analyzer -- it
prints `reading one at a time (...)` and reads every save itself, which is
the right thing for a user and gives exactly the same files. So the
comparison cannot tell a worker that started under spawn from one that never
did.

Measured on `5a4a685`: hand the finishing to the workers as a lambda instead
of a `partial`. Fork inherits it and is untouched. Spawn cannot pickle it,
fails at the first submit, and reads all 103 saves on one core:

```
spawn  stderr: reading one at a time (Can't pickle local object <function main.<locals>.<lambda> ...>)
all 10 files identical whichever way the workers start
```

and the check passed. That is a failure only Windows would see, as a
campaign that takes many times longer and no error.

**Fixed**: `spawned.py` fails when either run says it read one save at a
time. `testkit/mutate.py` gains `spawn-job-not-picklable`, which puts the
lambda back; it is caught.

---

# Thermonuclear review of `26f3680`

## 12. How this one was done, and what it covered

Every file, not only `vic2_analyzer.py`, on the assumption that nothing works
until a machine has shown it does. At `26f3680` all 24 checks pass (2 min 27 s)
and the harness catches 25 of 25. Every finding below was reproduced on this
machine, and each gives the command and what it printed. Anything suspected and
not reproduced is under §27, "Leads". Five independent reviewers were started
in parallel; all five stopped at a usage limit before reporting anything, so
nothing here rests on their word.

Experiments ran with `--no-cache` or a private `TMPDIR=/tmp/nc`, in worktrees
with the scanner copied in. The real cache was never touched. (The machine
rebooted mid-review, which empties `/tmp` and with it the real cache. That
was the reboot, not an experiment.)

Ranked by what they cost someone using the program: wrong numbers nobody is
told about first, then crashes, then Windows-only, then checks, then security.

## 13. The Wars tab leaves out belligerents the game did not log joining

`readsave.py:671`, `read_war`. A war's sides are built only from its history's
`add_attacker`/`add_defender` entries. The war's own `attacker=`/`defender=`
lines, which the game writes for every nation currently in it, are never read.
A nation in the war with no join entry therefore never appears.

In this campaign, the *3rd American War of Independence*, as the save itself
lists it (`NET1874_08_01.v2`):

| | |
|---|---|
| `attacker=` lines | ENG BIK BUN GWA JAS MEW SCA AST **SAR TUR SPA NET FRA RUS WAL** |
| `defender=` lines | USA MEX BRZ |
| history `add_*` entries | ENG BIK BUN GWA JAS MEW SCA AST · USA GER MEX BRZ KUK SIC ALD |
| history `rem_*` entries | GER KUK ALD SIC |

The seven in bold have no history entry at all. Spain fought battles in this
war as an attacker. The report built from the campaign (40 saves, the mod,
`--no-cache`) lists the war's attackers as `AST BIK BUN ENG GWA JAS MEW SCA` and
its defenders as `ALD BRZ GER KUK MEX SIC USA`: seven of fifteen attackers
missing, **the player's own Netherlands among them**. The same happened in the
first save of the campaign, so no reading of this campaign ever gets them
back.

The same lists decide who counts as at war when a triggered modifier asks
`war = yes` (`explain.save_world`). So Germany, Austria, ALD and Sicily count
as at war after they left, and the seven above do not count though they are.
The mod here has no war-triggered modifier, so no mobilisation number in this
campaign moves. Under a mod that has one, it would.

**Fix.** Read `attacker=`/`defender=` as the current sides. The table lists the
union of those and the history across saves. `at_war` uses the current sides
only. This changes what the Wars tab shows, so it is the maintainer's call (§29).

**Correction, from the maintainer.** The seven are not a gap in the game's logging. The
host of the game merged the wars by hand, editing the save to add those
participants, and that is why they have no join entries. The finding narrows
to hand-edited saves. The Wars tab is left as it is; the maintainer explained the cause
and did not ask for a change. The `at_war` half does not depend on the hand
edit. A nation with a `rem_*` entry has left, and the engine judges
`war = yes` on the current sides. So that half is fixed (§30), and it moves no
number in this campaign.

## 14. A save that was cut short is read as if it were whole

`readsave.py:847`, `analyze_save`. The first two thirds of
`NET1872_09_01.v2`, the rest cut off (a crash while the game was writing, a
sync client, a full disk), reads without a word:

```
parity.py on the cut save:  identical across 41 nations
against the whole save:     34 of 41 nations changed
                            SCA 86 -> 0 brigades, SPA 94 -> 0, AST 70 -> 0, NET 1 -> 0 ...
                            and their ships, technologies, treasury and prestige
                            wars: 153 -> 0
```

Both readers agree, because both are wrong the same way, so the parity check
passes. `testkit/mangled.py` checks only that a damaged save never raises a
stack trace. Reading it and refusing it both count as passing, so it passes
too. In a report this looks like every army in the world disbanding for one
month.

**Fix.** A complete save ends with a lone `}` line. All 103 here do, checked. A
file that does not is refused in a sentence, the way a zip or a binary save
already is. Reading the last few bytes costs nothing. Only a damaged save's
output changes; the check's docstring already allows refusing one.

## 15. `--cross` serves an old report when any campaign but the largest changes

`vic2_analyzer.py:1436`. The report stamp is computed after `run_cross` has
returned only the primary campaign's saves and mod, so the other campaigns'
saves and mods are not in it.

```
/tmp/xc/Alpha (4 saves), /tmp/xc/Beta (2 saves), --cross --mod-path MOD
run 1:                    cross block: Alpha 4 saves, Beta 2
add a third save to Beta
run 2 (no --rebuild):     Reading Beta (3 saves) ...
                          Cross-campaign: 2 campaigns, 41 nations in two or more of them.
                          Nothing has changed since this was built. Opening it as it is.
                          cross block: Alpha 4, Beta 2       <- still the old one
run 3 (--rebuild):        cross block: Alpha 4, Beta 3
```

It also reads every campaign before deciding there is nothing to do. The window
takes this path whenever the saves folder holds several campaigns
(`gui.py:653`), so a window user playing anything but their longest campaign
never sees its new saves in the comparison. No check covers `--cross`
staleness.

**Fix.** Hash every campaign's files and mod into the stamp, and take the stamp
before `run_cross` reads anything, using the survey `run_cross` already makes.

## 16. A table that cannot be written crashes the run, and then the wrong report is served

`vic2_analyzer.py:443` and `:1663`. On Windows, a CSV open in Excel cannot be
opened for writing. Simulated here by making `nations_timeseries.csv`
read-only:

```
A  --tags YNN                     report: 1 tag
B  all nations, table locked      PermissionError: [Errno 13] ... nations_timeseries.csv
                                  (stack trace; report.html already rewritten, 41 tags;
                                   report.stamp still A's)
A  again, no --rebuild            Nothing has changed since this was built.
                                  report: 41 tags           <- B's report, served as A's
```

Two problems. The run ends in a stack trace for an ordinary situation. And the
stamp from the last good run outlives the report it described. The next run
with those settings trusts it and serves a report built with different ones.

**Fix.** Delete the stamp before anything is written, so a run that dies
half-way leaves no stamp to match. A table that cannot be written gets a plain
message ("close it in Excel") rather than a trace.

## 17. `--explain-mob` judges war triggers after the wars have been thrown away

`vic2_analyzer.py:1043` clears `meta["wars"]` as each save is folded.
`explain.py:160` and `:286` then build `save_world` from those emptied metas.
So the two diagnostics that exist to explain a nation's mobilisation size see
nobody at war, while the report, finished before the wars were folded, did.

```
mod: triggered modifier war_footing { trigger = { war = yes } mobilisation_size = 0.05 }
save: ENG at war with FRA (two saves)
report, nations_timeseries.csv:  ENG mobilisation_size 0.05, 0.05
--explain-mob ENG:               TOTAL 0.00%   ... 0 sources grant it mobilisation size.
```

**Fix.** Keep the wars on saves that are kept whole. Those are the diagnostics'
own runs, which already keep everything else.

## 18. The mobilisation cap can come out one brigade short

`finishing.py:385`, `cap = int(max(standing, MIN) * (1.0 + impact))`. The
documented formula is floor(max(standing, MIN_MOBILIZE_LIMIT) × (1 + impact)).
`impact` is the party's war policy plus the sum of the modifiers, in floats.
Where the exact product is a whole number, the float lands a hair under it
and `int()` drops one:

```
policy 1, modifiers +0.1 +0.2, 50 standing:   formula 115, program 114
policy 4, modifiers -0.2 -0.1, 10 standing:   formula  47, program  46
```

75 such cases turned up in a small sweep, all needing two or more
modifiers. The game keeps these numbers to three decimals. **Fix.** Round the
product to a few decimal places before taking the floor. This changes the
number in exactly those cases, so it is the maintainer's call (§29).

## 19. A table from an earlier run survives beside the new ones

`vic2_analyzer.py:480`, `if not data: continue`. A table with no rows this run
is not written, so last run's copy stays:

```
3 saves -> out/             ships_by_type.csv: 40 nations
same saves, --tags YNN      Wrote: ... (no ships_by_type.csv)
                            out/ships_by_type.csv: still the 40 nations, beside a
                            nations_timeseries.csv holding YNN alone
```

The window reuses one output folder, so anyone opening the folder in Excel
reads numbers from a different run. **Fix.** Write a table even when it is empty
(its header alone), so every file in the folder is from this run.

## 20. Two saves with the same date are counted twice in the tables

Three saves plus a copy of one of them, under another name:
`nations_timeseries.csv` has 82 rows for `1872.10.1` against 41 without the
copy, and every per-save table doubles the same way. The report keeps one
reading per date, so the page and the tables disagree, and nothing says so.
This happens for real: every game's first save is `1836.1.1`, so a folder
holding two games has two of them, and a manual save can land on an autosave's
day. **Fix.** At least a warning naming both files. Dropping the second is a
change to the tables, so it is the maintainer's call (§29).

## 21. One worker that dies takes the whole run with it

`readfolder.py:447`. If a worker is killed mid-save (out of memory,
antivirus), every outstanding job raises `BrokenProcessPool`. The streaming
reader catches only `ValueError`/`OSError` there:

```
_worker_parse exits abruptly on the 6th save of 40:
concurrent.futures.process.BrokenProcessPool: A process in the process pool was
terminated abruptly while the future was running or pending.     (exit 1)
```

`parse_saves`, the other reader, falls back to one save at a time for the
very same failure. **Fix.** Do the same here: on a broken pool, finish the
remaining saves in this process, and say so.

## 22. Every analysis forgets the GitHub token and the report host

`gui.py:710` saves the window's settings by *replacing* the file with four
keys. `app.py` keeps the token and host in the same file. Driving the real
window (`App.start`, settings redirected to a scratch folder):

```
before a run:  ['github_token', 'report_host']
after a run:   ['mod', 'open_after', 'out', 'saves']
```

So the "asked for once and remembered" token is asked for again after every
analysis. The other way round is worse. A token that GitHub rejects (a typo,
or an expired one; GitHub's fine-grained tokens expire) is handed back by
`app.py:240` every time, with no way in the app to replace it, until an
analysis happens to erase it. No check drives `App.start`, because
`testkit/window.py` calls `work` directly. **Fix.** Merge into the settings
rather than replacing them, and forget a token GitHub answers 401 to, so the
next press asks for a new one.

## 23. Windows: a mod's file that differs only in letter case is read twice

`mod_reader.py:634`, `_resolved_files`, keys a folder's files by exact name.
Windows ignores case, so there a mod's `inventions/Army_Inventions.txt`
*replaces* the game's `inventions/army_inventions.txt`. Here both are read:

```
base  inventions/army_inventions.txt   base_one, base_two
mod   inventions/Army_Inventions.txt   mod_one
resolved: both files     invention array: [mod_one, base_one, base_two]
the game on Windows:     [mod_one]
```

Every invention index after it is then off, and that decides mobilisation
sizes and ship stats. **Fix.** Key by the lower-cased name, and keep the
winning file's own name for the ASCII sort the array depends on. Nothing
changes for the campaign here, because this machine has no game install under
the mod.

## 24. Windows: the scanner would open a console window for every save

`fastscan.py:177` starts the scanner with no `creationflags`. The scanner is a
console program: `scanner/src/main.rs` sets no `windows_subsystem`. The
executable is built `--windowed`. A windowed program that starts a console
program without `CREATE_NO_WINDOW` gets a new console window each time, so one
would flash per save read. That is an inference from how Windows starts
processes; this machine cannot show it.

It has not happened to anyone yet, because **the shipped
`dist/vic2saveanalyzer.exe` carries no scanner at all**. Its archive has 37
entries and no `vic2scan`, so Windows users read every save in Python, about
four times slower. It will happen on the first build made with the scanner.
**Fix.** Pass `CREATE_NO_WINDOW` on Windows. When rebuilding, run `cargo build
--release --manifest-path scanner/Cargo.toml` first, or the new exe will also
read in Python.

## 25. Checks that do not check

Thirteen checks that `mutate.py` had no mutation for were each given one
realistic bug. Twelve caught theirs, and each failure message was read and
names the bug (§28). The thirteenth:

**Nothing guards the stamp's list of settings.** `vic2_analyzer.py:169` names by
hand the fifteen settings that change a number. Take `min_pop` off that list
and `staleness.py` still says "every one of them moves the stamp: ok", and so
does every other check. A later run with a different `--min-pop` would then
answer "nothing has changed" with the old report. This is §9's hand-written
list again, for settings instead of files. `staleness.py` checks files only.
Neither §15's `--cross` staleness nor §22's `App.start` is exercised by any
check either.

**Fix.** Candidate 3 in `HANDOFF.md` (a declared `Run`) gives the settings one
declaration. A check then changes each output-affecting setting in turn and
requires the stamp to move.

## 26. Security

**Script in a name runs in the report.** `template.py:4838` writes
`<td class="warname">${w.name}` into `innerHTML`, as do about thirty other
sites, with names from saves and mod localisation. A two-save campaign whose
war is named `<img src=x onerror=dump(...)>`, opened in headless Firefox the
way `boots.py` does: the page reported `injected=1`, so the script ran when the
Wars tab drew. Reports get published to github.io and opened from disk, and
multiplayer saves come from other people. **Fix.** One escaping helper, used at
every `innerHTML` site that takes a name. That changes the bytes of
`report.html` (its script), not a number in it.

**The GitHub token follows redirects.** `publish.py:67` uses urllib's default
redirect handling, which sends the `Authorization` header on to wherever a
redirect points. A fake API on 127.0.0.1 answering 301 to a second local
server: the second server received `Authorization: Bearer ghp_SECRET_TOKEN`
three times. GitHub's API would have to redirect to another host for this to
bite, so it is low. **Fix.** Refuse cross-host redirects in `_call`.

**Two failures surface raw.** A 200 answer that is not JSON (a hotel's
log-in page) gives `JSONDecodeError: Expecting value: line 1 column 1`. An
answer that stalls mid-read gives `TimeoutError: timed out`. Both reach the
error box as those words. **Fix.** Turn both into `PublishError`s that say
what happened.

What is uploaded is the report and, for a split report, its data file, both
to the user's own repository or to a host they named. The report holds no
paths, user name or save file names. A report built here was searched for
`/home`, the user name, the saves folder, the mod folder, backslashes and
`/tmp`, in the payload, the page around it, the nine tables and the stamp,
and none of them was found.

## 27. Leads, not reproduced

- `mod_reader` ignores a mod's `.mod` descriptor, so `replace_path` goes
  unread. A mod that replaces a whole folder would still inherit the game's
  files in it. There is no second mod or game install here to test it.
- `nation.brigades_from_clusters` compares `size × rate` against the regiment
  cost in floats, with `rate` a sum of many contributions. The same kind of
  hair-under error as §18 could decide a regiment. The rule matched 184 of 185
  in-game readings; whether the one miss (Japan 1908, 467 against 468) is this
  is unknown.
- `cross._MOD_FACTS` and `_CAPACITY` are never cleared in a long-running
  window, so a mod updated while the window is open is matched on its old
  facts.
- `host/worker.js` deletes a report on a GET, so a chat app previewing the
  delete link would take the report down. And the "is this a report" test is
  three strings anyone can include, so a deployed host serves arbitrary pages
  under its CSP.
- GitHub Pages serving `report.data.gz` with `Content-Encoding: gzip` would
  break `--split` reports. Not checkable without the network.

## 28. Attacked and held up

- **Planted bugs, caught for the right reason.** `staleness.py` (a source
  file skipped), `noworkers.py` (no fallback when the pool will not start),
  `edges.py` (a refused file crashing the run), `matching.py` (the map test
  switched off), `modcache.py` (the mod key ignoring the files),
  `packing.py` (a module left off the list), `tooearly.py` (a name read
  early), `keeping.py` (copying twice: "51 copies for 18 months"),
  `sharing.py` (a 413 explained wrongly), `window.py` (Stop unwired),
  `invariants.py` (accepted share over primary culture: "90 of 205 rows"),
  `facts.py` (a field stripped and not named), `boots.py` (a tab that throws).
- The Rust scanner and Python agree exactly, types included, on the real save
  with Unix line endings. On a save reflowed onto single lines the scanner
  declines and Python reads it, as designed.
- The trigger evaluator's three-valued `AND`/`OR`/`NOT` is right, including
  `NOT` over several conditions reading as "none of them".
- `year_fraction` keeps dates in order within and across months. Growth rates
  skip zero readings. No `NaN` or `Infinity` reaches the payload.
- A split report finds its data under the name `publish.py` gives it.
- The keeper retakes a copy caught mid-write, because the next change to the
  file finds the kept copy the wrong size.
- `mod_reader._reader_fingerprint` is still complete: `mod_reader` imports
  exactly `cacheio` and `v2parse` of ours.
- Still true from `HANDOFF.md`: `keeper_gui.py:199` calls `os.startfile`,
  `explain.py:222` walks the invention files for nothing, and
  `report.merge_wars` is reached only from a fallback production never takes.

## 29. What to do, in order, and what needs the maintainer

Fixes that change no number for a correct campaign, safe to make: §15, §16,
§17, §19, §21, §22, §23, §24, §25, §26, §14 (only a damaged save's output
changes), and the known items in `HANDOFF.md`.

Fixes that change what a user sees, so the maintainer decides:

1. **§13**, the Wars tab listing every nation in a war. For this campaign it
   adds SAR, TUR, SPA, NET, FRA, RUS and WAL to one war.
2. **§18**, the cap rounded before the floor. It moves only the cases that
   were one short.
3. **§20**, whether a second save with the same date is dropped from the
   tables or only warned about.

## 30. What the maintainer decided

- **§13**: the missing belligerents came from a hand merge by the game's host.
  The Wars tab stays as it is. Who counts as at war for a trigger is taken
  from the war's current sides.
- **§18**: leave the cap arithmetic as it is.
- **§20**: warn, and keep one save per date (the later-named file) so the
  tables match the report.

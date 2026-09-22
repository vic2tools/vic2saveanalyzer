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

# Next session: finish what the architecture review started

Paste this whole file as the first message of a new session.

---

You are picking up `~/vic2saveanalyzer`, a Victoria 2 save-file
analyzer. It is a local-only git repo — **nothing has ever been pushed**, and
there is a verified backup bundle at `~/vic2saveanalyzer-backup.bundle`.
HEAD is `1a82b04`. The working tree is clean and all 22 checks pass.

The maintainer develops on Fedora and ships on Windows as `dist/vic2saveanalyzer.exe`,
so anything platform-specific gets written on the machine that cannot test it.
He is not a software engineer: explain in plain terms, and prefer doing the
work over asking design questions.

## How to verify anything you change

These three, in this order, are the contract. Do not report work as done
without them.

```bash
cd ~/vic2saveanalyzer
S="/path/to/saves/1870s"                       # 103 saves, 3.5 GB
M="/path/to/mod/Modus Omnino Demens 1.6"

# 1. the nine outputs must be byte-identical unless you meant to change them
python3 vic2_analyzer.py "$S" --out /tmp/after --mod-path "$M" --rebuild -q
#    compare /tmp/after against a run from a clean checkout of HEAD;
#    report.stamp is EXPECTED to differ, it hashes the source

# 2. the four diagnostics must be byte-identical
#    --explain-mob-pool NET / --explain-mob NET / --inventions NET / --check-inventions

# 3. all 22 checks
python3 testkit/all.py "$S" --mod "$M"
```

**Three traps that cost this session real time — do not repeat them.**

1. **Never edit the tree while `testkit/all.py` is running.** It reads files
   at exec time; a mid-run edit produces a mixed result. This happened three
   times and produced one entirely fictitious failure
   (`report.stamp differs between fork and spawn`).
2. **Never benchmark while anything else is running.** Two measurements were
   ruined by the suite competing for the same 16 cores.
3. **Keep `TMPDIR` short.** Python 3.14 starts workers through a forkserver
   whose socket lives in `TMPDIR`, and an `AF_UNIX` path cannot exceed 108
   bytes. A long one used to crash the run; it now degrades to serial
   reading, which silently makes every benchmark meaningless. Use `/tmp/xx`.

Measure interleaved against the previous commit — alternate before/after runs
in the same loop, three rounds — never a single run of each. Two trees can
never share a parse cache (the fingerprint hashes the source), so prime each
tree's cache first and compare steady state.

## What is already done, so you do not redo it

`nation.py` (317 lines) now owns the nation record: its 72 fields and their
empty values, `MOBILIZABLE_TYPES`, `POP_SIZE_PER_REGIMENT`, the pure
functions over one record (`accepted_cultures_of`, `mobilization_clusters`,
`brigades_from_clusters`), and the trim rules (`SPENT_ON_FINALIZE`,
`AS_PLAIN_DICTS`, `AS_PLAIN_DICTS_INSIDE`, `KEEP_META`, `KEEP_NATION`,
`KEEP_FOR_INVENTIONS`, `trim_save`). It imports nothing of ours.

`modrules.py` owns judging what a mod's rules are worth to one nation.
`mod_reader.py` reads mod files into tables and now exposes 36 names, not 53.
`cacheio.py` owns compressed atomic cache reads and writes.

---

# The work

Four jobs, in the order they should be done. Each is independently
committable. **Do 1 first — it is a correctness bug.**

## 1. `--cross` reports different numbers than the report, for the same campaign

**Files: `vic2_analyzer.py` only** (`run_cross` line 1513, `campaign_rows`
line 1475).

`--cross` reads several campaigns and puts a cross-campaign block in the
report. The largest campaign then also becomes the subject of the ordinary
report — so the *same campaign* is measured twice, by two code paths that do
not agree. `campaign_rows`'s own docstring claims "The same `finalize` the
single-campaign path runs, so a measure means here exactly what it means on
the report's own charts." It is not the same. Four verified divergences:

| | `main` | `run_cross` / `campaign_rows` |
|---|---|---|
| mod's `POP_SIZE_PER_REGIMENT` | applied (line 2250) | **never applied** — uses the 3000 default |
| `mob_types` from mod | only if user left the default | **overridden unconditionally**, so `--mob-types` is ignored |
| parse-time vs finalize-time pop filter | same source | `set_mob_candidates(mod's list)` but `finalize(mob_types=args.mob_types)` — **different sources** |
| who counts as a player | `--player-nations`, else `human=yes`, else `meta["player"]` | **only `human=yes`** |
| minimum population | `args.min_pop` | `max(1, args.min_pop)` |

Every one of these was confirmed by reading the code this session; none is
speculative. The pop-per-regiment one is the worst — brigade counts in the
cross block are computed against a different divisor than the same nation's
brigade counts in the chart above it.

**What to do.** There are four copies of the finishing recipe (pick players,
filter, compute the rate, call `finalize`, stamp `mobilisation_size`):
`_finish_save`, `_finalize_here`, the row loop inside `walk_campaign`, and
`campaign_rows`. `_finish_save`'s docstring even says the row loop
"repeat[s] exactly" its filter — by design, which is how they drifted.
Collapse them onto one function that takes (meta, nations, spec) and returns
finished nations. `Finish` (the namedtuple in `vic2_analyzer.py`) is already
the right shape for the spec.

**Test to add:** nothing currently tests `run_cross`'s per-campaign setup.
`testkit/matching.py` builds fake mods and `testkit/savefmt.py` builds fake
saves — use both to build two campaigns on two mods, run `--cross`, and
assert the primary campaign's rows are identical whether they came through
the cross path or the report path.

## 2. Narrow the seam between the two save readers

**Files: `readsave.py`, `fastscan.py`, `nation.py`, `testkit/parity.py`.**

There are two producers of a nation record: the Python reader in
`readsave.py` and the Rust scanner, folded in by
`fastscan.apply`/`apply_countries` (lines 281 and 359).
`fastscan.apply` takes **six half-built accumulators** and fills them in
place, and between the two functions they name ~53 of the record's 72 fields
directly. They must also preserve container *types* — a `Counter` must stay a
`Counter` — which `fastscan.py:364` documents.

`nation.py` now owns the record, which was the precondition for this. It
does **not** yet stop the two producers knowing the field names for
themselves; `nation.py`'s docstring says so explicitly. What actually holds
the two to the same shape is `testkit/parity.py` comparing their output byte
for byte, which needs a folder of real saves and a built Rust binary and
skips without either.

**What to do.** Give `analyze_save` one source interface — `source.read(path)`
returning a value — with the Rust-backed and Python-native sources
interchangeable behind it, and merge in one place in `readsave` rather than
field-by-field in `fastscan`. Then parity becomes "feed both sources the same
bytes, compare the two returned values" and can run against a synthetic save
from `testkit/savefmt.py` with no scanner present.

**This touches the Rust side's contract. Do not start it without doing job 1
first**, and expect it to be the longest of the four.

## 3. One object for "how this run reads a save"

**Files: `vic2_analyzer.py`, `readsave.py`, `v2parse.py`.**

Three mutable module globals decide how a save is parsed: `v2parse.POP_TYPES`,
`readsave.MOB_CANDIDATES`, `readsave.REFORM_KEYS`. They must be set in three
places — `main`, `run_cross`, and every worker (Windows spawns fresh
interpreters, so `_worker_setup` must redo it) — and then re-derived twice
more, into the cache key (`mod_fingerprint`) and into `parse_options` for the
pool. Six places that must agree about one thing.

`v2parse.py:46` records what happens when they do not: a set that only grew
carried one mod's `bankers` pop type into the next campaign, "read one anyway
**and then cached it under a key that said it had not**."

**Signal that this is badly shaped:** eight files in `testkit/` reach past the
interface to reset these globals by hand before they can run
(`edges.py`, `countries.py`, `noworkers.py`, `parity.py`, `savefmt.py`,
`awkward.py`, `mangled.py`, `mobrate.py`).

**What to do.** A profile object built once from a mod path, with
`apply()` (set the globals, here or in a worker), `fingerprint()` (the cache
key) and `pool_args()`. The point is that the fingerprint can no longer be
computed from a state different from what the parse will actually use,
because there is only one object. Job 1's `run_cross` divergences largely
disappear as a side effect, so **do job 1 first and see what is left**.

## 4. `load_mod` returns a bare dict with 31 keys, and one of them must be
   written back by the caller

**Files: `mod_reader.py`, `vic2_analyzer.py`, `modrules.py`.**

`load_mod`'s docstring documents five keys. Callers actually read **31**.
Worse, the returned mod is incomplete on purpose: `index_base` is `None`
until the caller walks the campaign and writes it back
(`vic2_analyzer.py` does this in two places). `modrules` branches hard on
that key — with it, inventions are exact; without it, it falls back to an
upper bound that its own comment says "overstates nations with poor luck."
A third caller that forgets the write-back silently gets wrong mobilisation
sizes with no error anywhere.

**What to do.** Return a small object with named accessors instead of 31 raw
keys, and make index decoding part of loading so it cannot be skipped. This
is the least urgent of the four.

---

## Two things to leave alone, with reasons

- **`template.py`, 5372 lines.** 5361 of them are one string holding the
  report page. Splitting it into real `.html`/`.css`/`.js` files means
  PyInstaller data files and `sys._MEIPASS` handling in a one-file
  executable, on Windows, which cannot be tested from this machine. The
  current design means the exe carries the page with no plumbing at all, and
  `testkit/boots.py` already runs it in headless Firefox with a console-error
  handler. If you want to close this, write it up as a decision record rather
  than doing it.
- **The report stamp is deliberately too eager.** It hashes every `.py`
  beside the program, so editing `gui.py` rebuilds a report that did not need
  rebuilding. That is on purpose: a needless 6-second rebuild is visible, a
  skipped one serves numbers from the last time somebody looked.
  `testkit/staleness.py` enforces it. Do not "optimise" it back into a list
  of filenames — that list was wrong within a day of being written.

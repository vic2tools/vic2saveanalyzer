# Next session: the reader and the finishing have their own files; here is what is left

Paste this whole file as the first message of a new session.

---

You are picking up `~/vic2saveanalyzer`, a Victoria 2 save-file
analyzer. It has a GitHub remote, `origin` (github.com/vic2tools/vic2saveanalyzer),
but its `main` is still `a78b1c3` from 2 September: **none of the 70-odd
commits since has been pushed**, and nothing should be without the maintainer saying
so. Earlier notes calling it "never pushed, no remote" were wrong about the
remote. The code is as of `f1a4d82`; the commit after it only writes this
file. The
working tree is clean, all 24 checks pass, and the mutation harness catches
25 of 25. Backup bundles sit in `~`, one per session:
`vic2saveanalyzer-backup.bundle` (`403dcc4`),
`vic2saveanalyzer-backup-f09e2f4.bundle`, and the newest,
`vic2saveanalyzer-backup-f1a4d82.bundle`, which also holds the commit that
wrote this file.

The maintainer develops on Fedora and ships on Windows as `dist/vic2saveanalyzer.exe`,
so anything platform-specific gets written on the machine that cannot test it.
He is not a software engineer: explain in plain terms, and prefer doing the
work over asking design questions. He hands work over for long stretches and
wants verified work, not check-ins.

**`dist/vic2saveanalyzer.exe` is out of date with the source** and has to be
rebuilt on Windows (`python build_exe.py`). Do not try to build it here.

Read `REVIEW.md` before changing anything it covers. It records what was found,
what was fixed, and what was decided against and why; do not re-open what it
marks decided. `INTERNALS.md` is the project's decision record, and is dense
with "we tried X, it was wrong, here is the measurement" — skim its *Speed*
section before touching anything that runs in workers.

## The contract. Nothing is done without all four.

```bash
cd ~/vic2saveanalyzer
S="/path/to/saves/1870s"                  # 103 saves, 3.3 GB
M="/path/to/mod/Modus Omnino Demens 1.6"

# A clean worktree of the previous commit, WITH the scanner copied in.
git worktree add --detach /tmp/base HEAD
mkdir -p /tmp/base/scanner/target/release
cp scanner/target/release/vic2scan /tmp/base/scanner/target/release/

# 1. the nine outputs, byte-identical -- --no-cache ON BOTH SIDES
for t in /tmp/base .; do (cd $t && python3 vic2_analyzer.py "$S" \
    --out /tmp/xx/$(basename $(realpath $t)) --mod-path "$M" --rebuild --no-cache -q); done
#    compare every file; report.stamp is EXPECTED to differ.

# 2. the four diagnostics, byte-identical, the same way (-q, --no-cache,
#    capture stdout): --explain-mob-pool NET / --explain-mob NET /
#    --inventions NET / --check-inventions

# 3. all the checks
python3 testkit/all.py "$S" --mod "$M"

# 4. the mutation harness, against a COMMITTED worktree: every mutation
#    caught -- none BLIND, none NOAPPLY, none UNTESTED -- and exit 0
git worktree add --detach /tmp/mut HEAD
mkdir -p /tmp/mut/scanner/target/release
cp scanner/target/release/vic2scan /tmp/mut/scanner/target/release/
python3 testkit/mutate.py --tree /tmp/mut --saves "$S"
git worktree remove --force /tmp/mut
```

Run step 1 on the same tree twice first if you have not before: it should
come out identical to itself, and it does, but a comparison you have not seen
fail proves nothing. All five runs of steps 1 and 2 take about 30 s together.

**Why `--no-cache` on both sides.** Until `5a4a685` the parse cache key did not
hash `nation.py`, so an edit to the fold was served out of old parses, and a
contract run *with* the cache compared stale against stale and said
"identical" (`REVIEW.md` §9). The key is derived now and a check guards it,
but the contract should not depend on the thing it is checking.

**Why step 4 changed.** The harness first runs every check on the unmutated
tree, and reports a check that fails there as `UNTESTED` rather than caught.
It used to hand `caching.py` the save folder as an argument, which made that
check fail on every run before any test started — five "caught" verdicts that
tested nothing (`REVIEW.md` §10).

## Traps that have cost real time

1. **Never edit the tree while `testkit/all.py` is running.** It reads files
   at exec time; a mid-run edit once produced an entirely fictitious failure.
2. **A fresh `git worktree` has no Rust scanner.** `scanner/target/` is
   untracked, so without the `cp` above everything is read in Python — four
   times slower, and `parity.py` compares Python with Python. Nothing says so.
3. **This is a desktop.** Firefox, VS Code and Discord hold the load up. Don't
   wait for idle; if you benchmark, interleave before/after runs in one loop,
   three to five rounds.
4. **Keep `TMPDIR` short or unset.** Python 3.14 starts workers through a
   forkserver whose socket path lives there and cannot exceed 108 bytes; a
   long one silently degrades to reading saves one at a time. For a private
   cache in an experiment, `TMPDIR=/tmp/nc` works.
5. **`mutate.py` refuses a worktree with uncommitted changes**, because it
   reverts with `git checkout` between mutations. Commit first.
6. **`caching.py` is a `unittest` script and takes no arguments.** Hand it a
   path and `unittest` reads the path as a test name and fails without running
   anything.
7. **A check that fails is not evidence either.** Before counting a mutation
   as caught, look at *why* the check failed. Every new mutation this session
   was run by hand once to read its failure message.

## What was done this session

Three commits, each verified against all four steps on its own.

- **`5a4a685`** — the parse cache key hashed six files named by hand, and
  `nation.py`, which `549fd6e` had filled with the fold every parsed save goes
  through, was not one of them. Measured: after editing one fold rule the
  report rebuilt out of stale parses, identical to before the edit and 1,999
  of 4,271 rows different from `--no-cache`. The key is now derived by
  `cacheio.sources_reached`, which follows imports (including those inside
  functions) with a line scan that costs under 1 ms where a real parse costs
  12. `testkit/caching.py` edits every file of the program in turn, in a copy,
  and fails unless exactly the right ones move the key — too few is this bug,
  too many throws the cache away for a reworded label. `mutate.py` gained its
  control run, lost the bogus `caching.py` argument, and gained two
  mutations. `REVIEW.md` §9 and §10.
- **`7c869e0`** — the parallel reader is `readfolder.py`: `Cancelled`, the
  Stop and progress hooks, the parse cache key and slots, the worker setup and
  job, `worker_count`, `parse_saves`, `parse_saves_stream`. Nothing outside it
  imports an underscore name from it; `campaign_slot` replaces the slot
  `campaign_inventions` used to build out of three private parts. The window
  still finds `Cancelled`, `set_cancel_check` and `set_progress` on
  `vic2_analyzer` (re-exported). The parse key is now what `readfolder`
  reaches, and `vic2_analyzer.py` is out of it. Also: `testkit/spawned.py`,
  the check that matters for a move like this, passed with **no worker ever
  started under spawn** — the analyzer falls back to reading one save at a
  time and writes identical files. It now fails on that fallback, and a
  mutation proves it. `REVIEW.md` §11.
- **`f1a4d82`** — the finishing is `finishing.py`: `Finish`, `mod_defaults`,
  `finish_spec`, `players_in`, `kept_by`, `finish_nations`, `brigade_cap`,
  `finalize`, and the worker adapter, now public as `finish_and_pack`. The
  analyzer calls it through the module (`finishing.finish_nations(...)`) so
  `testkit/crossrows.py` can replace it in one place and see both callers;
  shown the other way round too — with a from-import, crossrows fails saying
  it saw 0 saves through `--cross`.

Sizes now: `vic2_analyzer.py` 1702 lines (was 2561), `readfolder.py` 536,
`finishing.py` 440. `pyflakes` is clean on all three apart from the three
deliberate re-exports, which carry a `# noqa: F401` that flake8 would honour
and pyflakes does not read.

## What is left

In rough order of value.

1. **Candidate 3 of the architecture review: give the analyzer a front door.**
   The report is `/tmp/architecture-review-20260922-060934.html` — `/tmp` is
   a tmpfs here, so it is gone after a reboot; the gist is this. The argparse
   `Namespace` is the widest shared contract in the program: 31 settings read
   across four files, 13 of them in more than one, declared nowhere. `main`
   writes the mod's two numbers back onto it for later readers; `report_stamp`
   hashes 15 of its attributes *by name* to decide staleness, so a new setting
   that changes a number and is missing from that list silently fails to
   rebuild the report. And `gui.App.work` drives the analyzer by rewriting
   `sys.argv`, building `"name=path"` strings for the parser to split apart,
   and setting three module-level hooks. The proposal: keep `command_line()`
   as it is, then build a declared `Run` from the namespace with the mod's
   defaults already settled; `explain.py` and `report_stamp` read the `Run`;
   the window builds a `Run` instead of an argv. **The model is already in
   this repo**: `keeper.Options`, `keeper.trouble()`, and `keeper_gui.py`
   passing callbacks as parameters. This one changes what the stamp hashes,
   so expect `report.stamp` to differ and nothing else.
2. **Two small real bugs**, found by the review, deliberately left alone:
   - `keeper_gui.py:199`, the keeper's "Open the folder" button, calls
     `os.startfile`, which exists only on Windows, so on Fedora it always shows
     an error dialog. `gui.py` has the right three-way version (`startfile` /
     `open` / `xdg-open`); `keeper_gui.py` is the copy nobody updated, and
     `testkit/window.py` tests only the `gui.py` one.
   - `explain.py:222`, in the `--check-inventions` branch, walks the mod's
     invention files into `where` and never reads it; the only read is in the
     `--inventions` branch, which assigns its own at line 245.
3. **`mod_reader._reader_fingerprint` is a hand-written list** (itself,
   `v2parse.py`, `cacheio.py`). It is complete today, because those are the
   only files of ours `mod_reader` imports. It is the same shape of hazard as
   §9, and `cacheio.sources_reached(__file__)` is the one-line fix the day it
   is not.
4. **Smaller things the review listed**, all verified still true:
   `report.merge_wars` (23 lines) is reachable only from a
   `if book is None` fallback that cannot be taken; three different walkers
   decide "what counts as a folder of saves" (`cross.campaigns_in`, `main`'s
   flat listdir, `keeper.saves_under`); and "world" names two different things
   in the analyzer. `REVIEW.md` §5 (`keep_pools` and `in_workers` held
   together by line order) and §7 (the fold table's redundant field column)
   are still open and cosmetic.
5. **From the previous handoff, re-checked and still true:** `--cross` is
   exercised only on synthetic campaigns, and the one real campaign's mod
   mobilizes exactly the vanilla three pop types at 3000 a regiment, which is
   why the `--cross` bugs survived so long — worth asking the maintainer for an IGoR or
   GFM campaign. `walk_campaign` still reads `v2parse.POP_TYPES` directly for
   its pop columns (`vic2_analyzer.py:965`), the last place that reaches for a
   parser global rather than being handed one. `testkit/parity.py` builds one
   synthetic save when given no folder; it could build the awkward shapes
   `awkward.py` knows about.

## Leave these alone, with reasons (all recorded in the repo)

- `template.py` — one 5361-line string, deliberately; splitting it means
  PyInstaller data files and `sys._MEIPASS` on a platform nobody here can test.
- The report stamp hashing every `.py` — deliberately over-eager. A needless
  rebuild is visible; a skipped one serves old numbers. Do not turn it into a
  list of filenames; that list was wrong within a day.
- `Mod.__getstate__`/`__setstate__` — `REVIEW.md` §6, decided.
- The seventeen fold rules in `nation.py` — `REVIEW.md` §7, decided.
- `readfolder.py` must not import the finishing, or anything else that only
  uses a save: its parse cache key is everything it reaches, and
  `testkit/caching.py` will fail if that grows.

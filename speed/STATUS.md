# Status

Newest entry at the bottom. Each session adds one entry when it stops.

## 2026-10-01, before task 01 (profiling session)

- Main is at `11e1f21`. Nothing in this job is done yet.
- The profile in CONTEXT.md was taken on `11e1f21`.
- The worktree `~/.cache/vic2speed/rw/opt-probe` is at `11e1f21` with
  `../front-probes.diff` applied, uncommitted. It holds front-end timing
  points; reuse it for measuring or remove it, after `git worktree list`.
- `rw/retire-mut` is clean at `11e1f21`, ready for mutation runs.

## 2026-10-01, task 01 done (baseline, dead modes deleted)

- Commit `31a2931` on main: "Delete the scanner modes nothing calls". Gone:
  the bare save scan, `--serve`, its JSON and `--record` answers
  (`record.rs`, the pickler), `vic2scan report SPEC` and `--dump` (with
  `dump::write` and what only it read: `Kept.total_pop`, `Kept.is_player`,
  `model::SNAPSHOT_FIELDS`), and `mod_file`. ~1,330 lines.
  - `pickle.rs` is now `fx.rs` (only `Fx`, `FxMap`, `FxSet`); every
    `crate::pickle::` import is `crate::fx::`.
  - `clause.rs` keeps the tree and the conversions. `great_nations` returns
    `R<Vec<i64>>`; the `P`/`OMap`/`Key` pickle values no longer exist.
  - `engine::run_spec(&spec)` takes no `dump` and returns `report::Outcome`
    (no Option).
  - `engine/dump.rs` holds only `obj` and `int_keyed` (used by report.rs).
  - Kept: `analyze`, `mod-export`, `mod-signature`, `bench-engine`,
    `selftest-*`. Nothing in `country.rs`/`province.rs` became unused.
- Verified: 28/28 checks; real campaign byte-identical to the reference
  (CSVs, report.html, stdout, stderr); 57/57 mutations (run on `ab54aa7`,
  which is `31a2931` minus the INTERNALS.md note). No mutation needed
  re-aiming: none patched deleted code (`~/.cache/vic2speed/mutdry.py .`
  dry-runs them all).
- INTERNALS.md: "The scanner's dead modes are gone, 2026-10-01".
  Bundle: `~/vic2saveanalyzer-backup-31a2931.bundle`. Not pushed.
- Tools made this session, in `opt/`:
  - `bench.sh TREE [LABEL]`: empty scratch cache x3, warm rebuild x5,
    nothing changed x3, with walls and median phases. Scratch in
    `opt/benchtmp/LABEL` (~120 MB each; delete old ones freely). ~40 s.
  - `refrun.sh TREE NAME`: one run from an empty scratch cache, kept in
    `opt/runs/NAME/` (out/, stdout.txt, stderr.txt, status.txt).
  - `cmpruns.py A B [--payload]`: compares two of those (stdout/stderr
    with out path and "on N cores" normalised; `--payload` compares
    report.html by `testkit/expected.page`, for after task 05).
  - Logs: `opt/logs/all-01.out`, `opt/logs/mut-ab54aa7.out`.
- Reference outputs: `opt/runs/11e1f21/` (the baseline) and
  `opt/runs/31a2931/` (identical to it).

Numbers (median wall through `vic2_analyzer.py`, files in page cache):

| run | 11e1f21 | 31a2931 |
|---|---|---|
| empty scratch cache (x3) | 4.29 s | 4.16 s |
| warm rebuild (x5) | 1.42 s | 1.41 s |
| nothing changed (x3) | 63 ms | 60 ms |

Warm-rebuild phases on 11e1f21 (seconds since engine start): pass one
0.208, inventions 0.250, pass two 0.368, walked 0.465, map raster 0.599,
owners 0.693, capitals 0.709, sections 0.838, assembled 0.862, gzipped
0.971, page 0.990, tables written 1.006. So ~0.41 s of the 1.42 s wall is
after "tables written" plus the launcher: the target of task 02.
Empty-cache: pass one ends at 2.92 s; tables written 3.85 s.

Notes for task 02:
- The first empty-cache run of the baseline bench was slower (6.4 s, seen once; likely
  save files had dropped out of the page cache). The median absorbs it.
- `rw/retire-mut` is clean at `31a2931`. `rw/opt-probe` is untouched
  (still `11e1f21` + front-probes.diff); the diff may need re-applying on
  a newer commit, as front/mod.rs changed by one line (`run_spec(&spec)`).
- CONTEXT.md's "dead modes listed in CONTEXT.md" and "step 'exit without
  freeing'" are not in CONTEXT.md; the task files carry the details.

## 2026-10-02, task 02 done (exit without freeing, worker count)

- `dd9d3e1` "End a run without freeing the campaign": `report::run`
  `mem::forget`s `(c, prices, snaps)` after `@done`; `run_spec` forgets
  `(run, m, live)` after `report::run` returns. `--cross` parts return
  before either (the `run.cross_part` early return), so they still free.
  Checked through `| cat`, `| head -3`, and hosted (`analyze()`, relayed,
  `--protocol`): status 0, progress 265/265, `@ready` seen, no `@` lines
  leaked, no `vic2scan` left (`pgrep -x`). Script: `speed/pipecheck.sh
  TREE SCRATCH` (replaces SCRATCH/tmp, o1, o2).
- `a330484` "Size the reading threads by the memory the system can give":
  `available_memory()` (MemAvailable; Windows `avail_phys`, unchanged and
  type-checked for x86_64-pc-windows-gnu, NOT run on Windows); per thread
  `biggest + biggest/4`; threads get `avail / 2`. Cores bar one kept. On
  this machine: 15 threads every run (6 of 6 empty-cache runs checked).
  INTERNALS.md section "A run ends without freeing, and reads on a steady
  count of threads, 2026-10-02" is in this commit (amended in after the
  mutations ran on `806c898`, the same code without it).
- Verified: 28/28 checks after each commit (`logs/all-02a.out`,
  `logs/all-02b.out`); real campaign identical to `runs/31a2931` and
  `runs/11e1f21` bar "on N cores" (`runs/02a`, `runs/02b`); 57/57
  mutations on `806c898` (`logs/mut-806c898.out`); `mutdry.py` showed all
  57 still apply. Bundle `~/vic2saveanalyzer-backup-a330484.bundle`. Not
  pushed. `rw/retire-mut` is clean at `a330484` with its scanner built.

| run (median wall) | 31a2931 | dd9d3e1 | a330484 |
|---|---|---|---|
| empty scratch cache (x3) | 4.16 s | 3.89 s | 3.45 s |
| warm rebuild (x5) | 1.41 s | 1.15 s | 1.14 s |
| nothing changed (x3) | 60 ms | 62 ms | 62 ms |

Measurements (logs in `opt/logs/`):
- Memory vs `-j` (`memj-dd9d3e1.out`, `memj-read-dd9d3e1.out`): heap at
  the end of pass one 762 MB (j1) -> 854 MB (j16) with mmap; 802 -> 1447
  MB with `VIC2_ENGINE_READ=1` (buffers, as Windows). Run peak ~1.25-1.3 GB
  comes after pass one and does not depend on j.
- Threads (`cores-dd9d3e1.out`, 3 interleaved rounds): 8 -> 3.83 s,
  12 -> 3.62, 14 -> 3.52, 15 -> 3.50, 16 -> 3.47. SMT helps; 16 vs 15 is
  ~1%, kept 15 (a core for the window).
- Warm rebuild missed the expected ~1.1 s (1.14 s). With temporary probes
  (reverted; rebuilt binary byte-identical to the commit's): ~1 ms from
  the last line to `exit()`; ~60-80 ms between `exit()` and the parent
  seeing it go, i.e. the kernel tearing down 1.3 GB. Not ours to free any
  faster; it shrinks with the data model (tasks 05-09).

Tools changed or added in `opt/`:
- `cmpruns.py` now normalises any `.../opt/runs/<name>/out` path, so
  `runs/31a2931` (made as `task01-pre`) compares cleanly. Before this
  fix, comparing against `31a2931` always reported stdout different.
- `memj.py TREE J...`: one empty-cache run per J, samples the scanner's
  RssAnon/RssFile/VmHWM every 5 ms, and the anon peak up to "pass one".

Notes for task 03:
- Empty-cache pass one now ends at ~2.45-2.5 s (15 threads); countries
  from bytes (task 03) is CPU work in it, so its gain shows there.
- Bench timings are only clean when nothing else runs: my first tail
  timings overlapped the mutation run and were discarded.

## 2026-10-02, after task 02: history rewritten for a push (no task work)

- The maintainer wants to push to GitHub (public repo `vic2tools/vic2saveanalyzer`)
  and get the code on his Windows PC from there; the personal paths had
  to go first. `git filter-branch` rewrote the 95 commits from `88ac80d`
  (21 Sep) on: in every .md file, the absolute path of the 1870s save
  folder -> `/path/to/saves/1870s`, the mod folder -> `/path/to/mod/`, any
  other path into the Downloads folder -> `/path/to/`, the rest of the home
  folder -> `~/`; and every
  hash of a rewritten commit named in a .md file or a commit message was
  replaced by its new hash. Nothing else changed.
- main became `331f8d3` (was `a330484`); superseded by the second
  rewrite below. Old hashes in this file stay as written.
- Verified: for all 95 pairs, authors and dates identical, messages equal
  to the old ones with the hash map applied, every non-.md file identical,
  every .md file equal to the old one with the rules applied. No file
  version and no message reachable from main past `origin/main` contains
  a home-folder path. Only HANDOFF.md, INTERNALS.md and REVIEW.md differ between
  the old and new main, so the checks were not rerun. The tags
  (`pre-optimize`, `pre-tech-war`, `pre-warpolish`) are August commits
  already on GitHub and do not contain the paths.
- Bundles: `~/vic2saveanalyzer-backup-331f8d3.bundle` (that main);
  `~/vic2saveanalyzer-backup-a330484.bundle` keeps the old history (with
  the paths) as the undo. `refs/original` was deleted. `rw/retire-mut` is
  clean at `331f8d3`; the other `rw/` worktrees are still on old commits.
- Not pushed. No GitHub credentials on this laptop (no gh, no credential
  helper, no SSH key); the maintainer pushes himself, or sets up a token.
- Not removed: the name "the maintainer" (~25 mentions in HANDOFF.md, REVIEW.md,
  INTERNALS.md and commit messages such as "Record what the maintainer decided"),
  and `~/.cache/vic2speed/...` paths (home-relative, no user name). Asked
  the maintainer about the name: remove every mention (next entry).

## 2026-10-02, the name taken out too (no task work)

- The maintainer asked for every mention of the name to go. Second `git filter-branch` over
  the same 95 commits (first: `e71fe21`, originally `88ac80d`): in every
  .md file and commit message, the name became "the maintainer" (and its
  possessive "the maintainer's"), capitalised at a sentence start (only
  "The maintainer develops on Fedora" in HANDOFF.md); hashes of rewritten commits named
  in .md files and messages remapped. Matched as a whole word, so game
  names would have survived; there were none. Pronouns ("whether he has",
  "put to him") were left.
- **main is now `a47e98f`**; task 02's commits are `a2b8c02` and
  `a47e98f`. `speed/rewrite-map-2026-10-02.txt` rows are "original
  after-paths final"; CONTEXT.md lists the common ones and now carries the
  rule: no name and no home-folder paths in anything committed.
- Verified as before: 95 pairs, identities and dates identical, messages
  and .md files exactly the old ones with the rules applied, every other
  file identical. The name, in any case, in any unpushed file version or
  message: 0. Home-folder paths: 0. Nothing on `origin/main` ever had the name.
  Author and committer are `vic2tools <vic2tools@users.noreply.github.com>`.
- Bundle `~/vic2saveanalyzer-backup-a47e98f.bundle` (current main).
  `a330484` (original, with paths and name) and `331f8d3` (name, no paths)
  bundles kept as undo copies; neither is for sharing. `refs/original`
  deleted. `rw/retire-mut` clean at `a47e98f`.
- Still not pushed: no credentials here; the maintainer pushes.

## 2026-10-02, pushed to GitHub (no task work)

- The maintainer logged in with `gh auth login` (account vic2tools; git uses it via
  `gh auth git-credential`) and asked for the push. Pre-push check
  (now `speed/prepush.sh`): 0 hits.
  `git push origin main`: `a78b1c3..a47e98f`, a fast-forward, main only
  (no tags, no other refs). GitHub's main = local main = `a47e98f`.
- From here, the maintainer takes the code on the Windows PC with
  `git clone https://github.com/vic2tools/vic2saveanalyzer` / `git pull`.
  The tracked `dist/vic2saveanalyzer.exe` is still the 2 Sep build.
- Whether to push after each session was asked, not yet answered: until
  it is, don't push without being asked.

## 2026-10-02, the notes moved into the repo (no task work)

- The maintainer wanted these notes on GitHub too. They are now `speed/`
  in the repo: CONTEXT.md, STATUS.md, README.md, the ten task files, the
  tools (`bench.sh`, `refrun.sh`, `cmpruns.py`, `memj.py`, `pipecheck.sh`)
  and `rewrite-map-2026-10-02.txt`. Cleaned for a public repo: the name is
  "the maintainer" throughout, and no path into a home folder is left.
- The scripts read `speed/local.env` (ignored by git): `VIC2_SAVES`,
  `VIC2_MOD`, `VIC2_SPEED_WORK` (default `~/.cache/vic2speed/opt`) and
  `VIC2_PRIVATE`. A new machine needs its own. Checked on the laptop:
  `refrun.sh` + `cmpruns.py` (a run of main `a47e98f` identical to
  `runs/11e1f21` and `runs/31a2931`), `memj.py` (j=15: 3.38 s), the other
  scripts' syntax.
- New `speed/prepush.sh`: greps the working files (tracked and new), the
  index and every commit not on `origin/main` for `VIC2_PRIVATE`; prints
  "clean" or the hits. Shown to catch a new file and a staged one, and to
  fail rather than say "clean" when a search errors (its first version
  did say "clean" with two searches broken; fixed before use).
- `~/.cache/vic2speed/opt/` keeps runs/, logs/, benchtmp/; its
  CONTEXT.md, STATUS.md and README.md are pointers here, and
  `old-notes-2026-10-02.tar.gz` holds the notes as they were.
- Start a session with: "Read speed/CONTEXT.md and speed/STATUS.md in
  ~/vic2saveanalyzer, then do the next task file in speed/ that STATUS.md
  says is not done." The old prompt still works through the pointers.
- Next: task 03 (`03-countries-from-bytes.md`).

## 2026-10-02, task 03 done on the Windows PC (countries from bytes)

- **Made on the Windows PC, not the laptop.** It had no Rust: rustup with
  the `x86_64-pc-windows-gnu` toolchain was installed (stable 1.99.0, in
  `~/.cargo/bin`, not on PATH; no Visual Studio needed). gdb came later,
  from MSYS2 (`C:\msys64\mingw64\bin\gdb.exe`, `mingw-w64-x86_64-gdb`,
  18.1). No Victoria 2, no 1880s campaign, no `expected-real` there. Its own
  `speed/local.env` was written (ignored); its `VIC2_PRIVATE` is a guess at
  that machine's words, so run `prepush.sh` on the laptop before any push.
- `cd7e575` "Read the countries from the save's bytes, not a decoded copy
  of them": `read_country(bytes, at, stop, tag, tables)` takes the save's
  bytes; `Tokens`, `parse_fields`, `Value<'a>`, `Dict<'a>` and the unit
  `Tally<'a>` borrow from them; only what a `Country` keeps is decoded
  (`latin1`). `space_len` is gone: `is_space(u8)` takes `09-0d 20 85 a0`.
  Names against the mod's tables go through `eq_latin1` (by character).
  Both callers in `engine/mod.rs` (`read_flat`, `bench`) pass a slice.
  `walk.rs` untouched. INTERNALS.md: "Countries are read from the save's
  bytes, 2026-10-02".
- **A quirk kept, for the maintainer to decide:** `skip_to_close` on the
  UTF-8 copy took the second byte of a no-break space or NEL for a letter,
  so a `"` right after one did not open a quoted name (where `next()`
  would). Kept exactly (`is_space(c) && c < 0x80`), with a unit test that
  was also run against the old code. Fixing it could move a number, so it
  needs a check, a mutation and the maintainer's say.
- Verified on Windows:
  - `testkit/all.py --quick` (no saves): 13/20 hold *on `main` before the
    change too*; the 7 that fail there fail identically after (recorded
    answers written on Linux: `/` vs `\` in paths and the like). The whole
    suite log, before vs after, is identical bar timings and the worktree
    path. **The full 28 checks with the campaign were not run.** Making
    the checks pass on Windows is its own job, not done.
  - `cargo test`: 6/6 (three new in `country.rs`).
  - Real saves: three 1836-41 saves on that PC, on a stand-in vanilla game
    (`testkit/matching.a_vanilla`), both trees, ten ways (report, `--tags`,
    `--split`, one save, `--peek`, `--verify`, four diagnostics): status,
    stdout, stderr, every file byte-identical.
  - Mutations, the full run on `e1e5d0a` (`--saves` the three saves):
    57 applied; **27 caught, 29 UNTESTED, 1 BLIND, 0 did not apply.** The
    29 are every mutation whose check already fails on Windows before any
    bug goes in (the 7 above, and `boots.py`, which wants a browser), so
    they say nothing either way. The BLIND one is
    `keeper-folder-windows-only`, which puts back a call to
    `os.startfile` -- harmless on Windows by its nature, so it can only be
    caught on Linux. None patches `country.rs`. `testkit/mutate.py` looked
    for `vic2scan` without `.exe` and refused to start on Windows; fixed
    (the commit after this entry's first version).
- Numbers, `vic2scan bench-engine` on the three saves, alternated, 15
  rounds, median per save (Ryzen 9 7950X): countries 6.5 -> 4.9 ms,
  read+scan+build 35.3 -> 33.7 ms, every other part unchanged. Empty-cache
  runs through `vic2_analyzer.py`, `-j 1`, 15 rounds: pass one 158 -> 153
  ms, wall 245 -> 240 ms.
- gdb samples, new `speed/gdbsample.py` (the Windows counterpart of
  `sample_run.sh` + `gdbreport.py`): `bench-engine` over the three saves
  listed 400 times, 100 samples per build, `d23d16b` vs `cd7e575`. Before,
  `text::latin1` was sampled straight under `read_flat` -- the country
  copy; after, every `latin1` sample is under `model::build` or
  `read_war`, decoding names they keep, and none under `read_flat` or
  `country::`. Share of samples (100 each, so +-3-4 points): countries
  14% -> 11%, provinces 33 -> 36%, prepare 28 -> 26% (its gzip 24 -> 23%),
  top-level blocks 6 -> 7%, malloc/free 24 -> 21%, reading the file 4 ->
  6%. On Windows the per-save gzip is a bigger share than the laptop's
  ~14%, and `deflate_raw` is the one hottest function: task 04's target.
- `dist/vic2saveanalyzer.exe` rebuilt on Windows from `cd7e575`, **with the
  Rust scanner bundled** (the 2 Sep build had none and predates the
  rewrite). Checked: its report from the three saves is byte-identical to
  the source's, every file; its `--help` matches the source's bar the usage
  line's wrapping (the program's name). Committed with this entry.
- **For the laptop, before task 04:** pull; rebuild the scanner; run the
  real-campaign comparison against `opt/runs/31a2931` (`refrun.sh` +
  `cmpruns.py`), `all.py` with the campaign (28/28), the mutation run in
  `rw/retire-mut` (the 29 UNTESTED here and the BLIND one get their real
  answer only there: 57/57 expected), and the bench on the 1880s campaign
  (empty-cache pass one should drop). Record them here. If any fails,
  task 03 is not done.
- Not pushed. No bundle in the laptop's `~` (made one on the Windows PC:
  `~/vic2saveanalyzer-backup-<hash>.bundle`, named for this commit).
- Next: the laptop checks above, then task 04 (`04-state-chunk.md`).

## 2026-10-03, the real campaign's answers and the reference run in the repo (no task work)

- The maintainer wants to run the checks and the speed comparisons on the
  Windows PC, so both went to GitHub:
  - `testkit/expected-real/` (48 MB, 278 files): the real campaign's and
    the real mod's recorded answers, copied from
    `~/.cache/vic2speed/expected-real` (identical; that folder is no longer
    read). `testkit/expected.py` now defaults to the repo copy;
    `VIC2_EXPECTED_REAL` still overrides. The campaign cases were already
    machine-independent (keyed by save file names and sizes, run on copies
    in a scratch folder).
  - The real mod's answer held absolute paths. `modread.portable()` now
    writes the folders it was read from as MOD and GAME and their
    separators as `/`, on the record and on each fresh answer; the record
    was converted with it. Tested: a Linux answer, the same answer with
    Windows backslashes and with a non-ASCII user folder come out
    identical; other backslashes are untouched; idempotent.
  - `speed/runs/11e1f21/` (65 MB): one reference run (02a, 02b and
    31a2931 are identical to it, so they stay local), `report.stamp` left
    out, stdout with `<GAME>` and `<OUT>/name` where the folders were.
    `cmpruns.py` finds a name in `opt/runs/` or else in `speed/runs/`, and
    normalises both sides the same way. Tested: repo copy vs the laptop's
    original and vs a fresh run of main: identical; the same run printed
    with Windows paths: identical; one byte added to a CSV, or "Found 264":
    caught.
- `.gitattributes`: both folders `-text`, so git keeps the tables' CRLF
  byte for byte (as `testkit/expected/**` already was). `.gitignore`
  let in their CSVs and the reference `report.html`.
- `local.env`'s `VIC2_PRIVATE` now matches the name as a whole word: the
  game data has "Prince Aleksandar" and the province "Balekungomi", which
  the old pattern would have flagged forever. (Set it the same way in a
  Windows `local.env`.)
- On Windows: the campaign checks need the same 265 saves (same names and
  sizes) and the same mod folder name. Untested there; the first Windows
  run of `testkit/all.py` is the test.

## 2026-10-03, task 03 checked on the real campaign, on Windows

- The Windows PC now has the game (Steam), the mod in its `mod/` folder
  and the 265 saves (9.1 GB, same names and sizes), and the answers and the
  reference run came with `a9aed25`. Its `local.env` points at them;
  `VIC2_PRIVATE` there is now whole-word, as above.
- History: the three Windows commits were rebased onto `a9aed25` (they had
  been made on `d23d16b`, not pushed). New hashes: `e9da15c` ->
  `cd7e575`, `7325f60` -> `e1e5d0a`, `86cad27` -> `2ce03a2`. The entries
  above name the new ones; the exe commit's message still says it was
  built "from e9da15c", which is `cd7e575`. The exe is that build, and
  the source it bundles is unchanged by the rebase.
- **`testkit/all.py` with the campaign and the mod: 19 of 28 hold.** The
  9 that fail are all Windows-only, none from task 03:
  - the 7 that fail on Windows without saves too (recorded answers with
    `/` where Windows prints `\`, and the like);
  - `enginecheck.py`, the real campaign against `expected-real`: **17 of
    27 cases identical; the other 9 differ only in `stdout.txt`, and all 54
    changed lines differ only by `/` against `\`** (`HOLDING/game` against
    `HOLDING\game`; the verbose runs and the diagnostics print folders).
    No table and no decoded page differs in any case;
  - `smoke.py` stops at its first step: `os.symlink` needs administrator
    rights or Developer Mode on Windows (WinError 1314).
  - The two browser checks skip (Firefox is installed; why they skip is
    not looked into yet).
- **The reference run:** all 265 saves through `vic2_analyzer.py` from an
  empty scratch cache (`~/vic2speed/opt/runs/03win`), against
  `speed/runs/11e1f21`: every CSV and `report.html` byte-identical;
  stdout's 317 lines identical once the Windows game and out folders are
  written `<GAME>` and `<OUT>` (`cmpruns.py` normalises only the Unix
  spelling of them, so it reported stdout different) and "on N cores";
  stderr empty on both; status 0 on both. Wall 2.8 s.
- `testkit/enginefmt.py` hung on Windows every time (900 s, the suite's
  limit): its input went to the scanner in the locale's code page, which
  cannot encode `\x85`, so Python stopped half-way through writing and
  waited on a scanner waiting for the rest. Now UTF-8 both ways: 72,340
  checks, 0 differ, 0.3 s.
- So task 03 is done: checks, real campaign against its answers and the
  reference, mutations (Windows' share, above), gdb, notes. What only
  Linux can answer: the 29 mutations UNTESTED here and the BLIND one.
- Worth a session of its own, for a program that ships on Windows: make
  the 7 checks hold on Windows (paths printed with `\`), `cmpruns.py`
  normalise Windows folders, `smoke.py` copy where it cannot link, and
  find why the browser checks skip.
- Not pushed. Bundle `~/vic2saveanalyzer-backup-<hash>.bundle` on the
  Windows PC, named for this commit.
- Next: task 03b (`03b-checks-on-windows.md`), then task 04
  (`04-state-chunk.md`).

## 2026-10-03, task 03b done on the Windows PC (the checks hold on Windows)

- **`testkit/all.py` with the campaign and the mod: 28 of 28 hold on
  Windows, none skipped** (`2697c57`; the baseline at `a80ec11` was 19 of
  28, with two browser checks skipping). The program and the recorded
  answers are untouched: no `--update-expected`, no change to anything the
  program prints or writes. INTERNALS.md: "The checks hold on Windows,
  2026-10-03"; `testkit/README.md` has an "On Windows" section.
- Commits (new hashes, not pushed):
  - `15a79c8` paths and wording: `expected.stand_in_for` (separators below
    a stand-in become `/`, as written or doubled; no other backslash),
    `modread.below_holding` (the same for JSON), `expected.os_wording`
    (Windows' "Permission denied" for a folder opened as a file, and
    "Cannot create a file when that file already exists", said as the
    record has them), USERPROFILE beside HOME in `frontcheck.py`, and
    `frontcheck.shut` (a save held open with no sharing, since a mode of 0
    does nothing). Fixes saveshapes, mangled, frontcheck, crossrows,
    enginecheck (all 27 cases, the real campaign included) and modread.
  - `4325f38` `engine_runtime.py`: the stand-in scanners wrote CR LF (a
    Python in a pipe, on Windows); the relay passes bytes as they are and
    the Rust scanner writes a bare newline, so **not a program bug**. Also
    `edges.py` (printed a mark no Windows code page has) and `all.py`
    (read the checks' output in that code page): UTF-8.
  - `cc909a9` `smoke.py` copies the eight saves where it may not link.
  - `17f76b7` `browser.py` finds Firefox in Program Files; boots.py,
    state_history_ui.py and looks.py use it. Both browser checks now run
    and pass on Windows.
  - `62d292b` `speed/cmpruns.py` sets aside a byte-order mark, CR LF and
    backslashes in the folders a run wrote.
  - `cf16767` the fixture builder's refusal of links did not see a
    junction (`os.path.islink` is false for one). `matching._linked` does;
    `engine_runtime.py` makes a junction where it cannot make a symlink
    (the second half, a link to a file, is not run on Windows);
    `mutate.py`'s `fixture-writes-through-link` is aimed at the new line.
  - `2697c57` `mutate.py` read the files it patches in the code page and
    died at `template.py` on Windows; UTF-8 now.
- **Not masks:** with a changed number and a changed path put into records
  by hand, `frontcheck.py` still fails and names the cases; with the
  junction guard removed the link test fails; `cmpruns.py` still reports
  a changed CSV or `Found 264`.
- **Mutations** (`logs/mut-03b.out`, a clean worktree
  `~/vic2speed/rw/mut03b` at `2697c57` with its scanner copied in, the
  campaign as `--saves`): **57 mutations, 56 caught, 1 BLIND, 0 did not
  apply, 0 untested.** The BLIND one is `keeper-folder-windows-only`, which
  puts back `os.startfile` and can only be caught off Windows, as the task
  said. (The 29 untested on Windows after task 03 are all judged now.)
- **The reference run:** `refrun.sh` + `cmpruns.py` against
  `speed/runs/11e1f21`: IDENTICAL, 12 files (`runs/03b`), and the older
  PowerShell-made `runs/03win` is now identical too. The exe in
  `dist/` run on the campaign gave the same, in 3.6 s.
- **The exe:** `dist/vic2saveanalyzer.exe` is modified in the working tree
  and not committed. It was already modified (10:05 today) when this
  session began, by nothing in this session; the committed one is `e1e5d0a`.
  It carries the Rust scanner (`build_exe.py` refuses to build without it;
  it unpacks `vic2scan.exe` and starts it as a child, which does the run)
  and produces the reference report byte for byte. Not rebuilt: no program
  code changed. Rebuild before committing it, as for any change.
- **Seen, not fixed:** `testkit/window.py` exits 0 when the "analysis did
  not finish" dialog it traps raises inside a Tk callback (the refused-run
  case), which Tk swallows; the traceback is printed. Is that so on Linux?
- **For the laptop, before the next push** (nothing here could be run on
  Linux, so every change was kept to `os.name == "nt"`, `os.sep` or
  something that is a plain no-op there): pull; `all.py` with the campaign
  (28/28); the mutation run (57/57, with `keeper-folder-windows-only` now
  caught). The checks touched: saveshapes, mangled, frontcheck, crossrows,
  enginecheck, modread (through `expected.py` / `modread.py`),
  engine_runtime (the relay stand-ins' newline; the link test, which on
  Linux still makes a symlink; `matching._linked`), edges, smoke (an
  `except OSError` around its link), boots, state_history_ui, looks (the
  Firefox lookup, `browser.py` -- on Linux still `shutil.which`), all.py
  (UTF-8 for the output it reads), `mutate.py` (UTF-8 for what it patches
  and the re-aimed mutation). Linux-specific things to look at: the
  new `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in
  edges.py and smoke.py, and `matching._linked` using `os.path.isjunction`
  where Python has it.
- Not pushed. Bundle `~/vic2saveanalyzer-backup-<hash>.bundle` on this PC,
  named for the last commit. `~/vic2speed/rw/mut03b` is a worktree here.
- Next: task 04 (`04-state-chunk.md`). The two browser checks it relies on
  now run on this PC.

## 2026-10-03, task 04 done on the Windows PC (the state chunk)

- **Made on the Windows PC** (Ryzen 9 7950X), the campaign and mod there.
  Commits (not pushed): `87f8a4d` "Compress each save's state chunk at
  level 5", then three small ones for `mutate.py` (below). INTERNALS.md:
  "The state chunk is compressed at level 5, 2026-10-03".
- **What the chunk costs** (265 saves, one thread, quiet machine, a probe
  dumping every chunk's JSON, `vic2scan selftest-deflate levels DIR`): per
  save JSON 0.57 ms, gzip at level 6 5.1 ms, base64 0.08 ms; 91 KB raw, 37 KB
  gzipped. It is its compression, so nothing was tried on the JSON. The
  chunks are 13 MB of the 18.6 MB page, so a faster level shows in the page.
- **What was kept:** `deflate.rs` takes a `Level` (zlib's good/lazy/nice/
  chain row); `deflate_raw` is level 6 as before, byte for byte (the real
  campaign's page with the chunks at 6 is identical to `speed/runs/11e1f21`);
  `Snapshot::pack` uses `LEVEL5`. `selftest-deflate` has `gz4`, `gz5` and
  `levels DIR`. **Dropped:** zlib's levels 1-3 (`deflate_fast`) were written
  and removed: no faster end to end than 5, and up to +6.8% page.

| chunk level | chunk bytes | ms a chunk | pass one | wall | report.html |
|---|---|---|---|---|---|
| 6 | 9.88 MB | 5.1 | 1.521 s | 2.468 s | 18,603,225 |
| 5 (kept) | +0.8% | 2.8 | 1.477 s | 2.419 s | +0.55% |
| 4 | +3.3% | 1.3 | 1.477 s | 2.423 s | +2.3% |
| 3 | +5.0% | 1.5 | 1.473 s | 2.443 s | +3.5% |
| 1 | +9.6% | 0.6 | 1.476 s | 2.450 s | +6.8% |

  (Seven interleaved rounds each, empty scratch cache, medians.) Final A/B,
  the previous commit's build against `87f8a4d`, ten interleaved rounds:
  empty cache wall 2.534 -> 2.446 s, pass one 1.535 -> 1.497 s. Warm rebuild
  (six rounds) 1.098 -> 1.070 s, which reads chunks from the cache and
  compresses none: noise. Nothing-changed not measured (no code on its path).
- **Verified:** `testkit/all.py` with the campaign and mod: 28 of 28 hold
  (`logs/all-04b.out`). The real campaign (`runs/04`) against
  `speed/runs/11e1f21`: every CSV byte-identical; `report.html` differs in
  bytes (the chunks) and `cmpruns.py --payload` says IDENTICAL, 12 files,
  chunks decoded. The rebuilt `dist/vic2saveanalyzer.exe` run on the campaign
  gives files byte-identical to the source's run. `enginecompress.py`
  round-trips levels 4 and 5 through `gzip.decompress`.
- **Mutations** (`logs/mut-04.out`, clean worktree `~/vic2speed/rw/mut04`
  at `87f8a4d`): 59 now, with two new: `level-five-stream-cut`
  (`enginecompress.py`) and `chunk-stream-cut` (`enginecheck.py` with the
  campaign and mod). First run: 57 caught, 1 BLIND (`keeper-folder-windows-
  only`, as before, Linux only), 1 untested: `chunk-stream-cut`, because
  `enginecheck.py` skips its real-campaign half without the mod, which
  `mutate.py` could not hand it. Fixed in `mutate.py` (`--mod`, and the
  `"saves-and-mod"` argument; two commits got there, the first aimed it at
  `frontcheck.py`, which does not decode chunks and was BLIND). Run alone
  on the fixed harness: caught. So 58 of 59 caught, the BLIND one being
  Linux's to answer. The 57 others were run before the harness fix, which
  touched only the new mutation's catcher.
- **My mistake:** my first full-suite run set `PYTHONIOENCODING=utf-8` and one
  front-end case ("a region naming a superscript") failed with `Â²` for `²`.
  Without the variable it passes, and 28/28 hold; not looked into further.
- **For the laptop:** pull; build; `all.py` (28/28), the mutation run (59,
  `--mod` now); measure pass one on the 1880s campaign, where the gain may
  differ (the profile put the chunk at ~14% of a worker there). Nothing
  here is Windows-only in the program.
- Next: task 05 (`05-model-survey.md`). Bundle `~/vic2saveanalyzer-backup-
  <hash>.bundle` on this PC, named for the last commit.

## 2026-10-03, task 05 done on the Windows PC (the survey and the design), and the order of what follows

(Committed as `4fb867f`, then rewritten later the same day once the stages
had been put in order. The first version put units and ships first and called
the order of payoff "08b, 08, 06, 07". The order below replaces it.)

- **Made on the Windows PC** (Ryzen 9 7950X: 16 cores, 32 logical, so the
  engine runs 31 workers here; the laptop ran 15), the 1880s campaign and mod
  there. **No engine code changed** and none of the checks was run: the
  commits are `speed/` only (notes, task files, a diff, small scripts). The
  design is `speed/MODEL.md`; the raw numbers are
  `speed/model-census-2026-10-03.txt`.

### What the survey found (MODEL.md sections 0-4)

- **`Meta` is 70% of what a campaign holds after pass one**, not the nation
  fields: 9.49 M live allocations (36,000 a save), `Meta` 6.61 M (`wars` 4.14 M,
  `province_owner` 1.35 M, `market` 1.12 M), `Nation` 2.34 M, `Held` 0.52 M. A
  save costs 221,000 allocations in pass one (`read_rest` 85,200, provinces
  45,600, countries 38,100, `build` 35,200, `prepare` 14,500, store 2,400); the
  warm cache load is 38,200 a save.
- **`Row` carries a whole `Nation`** (2.34 M) through the walk and the page,
  and `Held` copies what the nation already holds: dropped, not converted.
- **The names are few** (about 600 in the nation fields, at most about 7,400
  in a run). Design: one run-wide table, `Sym(u32)`, a per-thread cache in
  front; containers keep their shape and order and change only their keys; no
  `Ord` on `Sym`; a per-entry name table in the cache; a
  `VIC2_ENGINE_NAMES_SHIFT` knob that moves every id, to show no output
  depends on one.
- **Order** (each field reversed in turn, the campaign compared with
  `speed/runs/11e1f21`) reaches the output for 13 fields (the nations in a
  save, both levels of `units_at`, `pop_by_culture`'s ties, `goods_supply`,
  `population_by_state`, `Group.types` / `cultures`, `great_nations`, `wars`,
  battles, goals, a side's units) and not for 19; reasons in MODEL.md 3.2.
- **The clocks** (MODEL.md 4.2). A warm rebuild is 1.17 s, about 0.2 s of it
  outside the engine. **The walk is 0.197 s and two thirds of it is one thread
  freeing the saves' war records (0.131 s) that nothing needs after the Book
  has folded them, while the walk waits.** The cache load is 0.214 s, settle
  0.050 s on one thread, pass two 0.081 s. In an empty-cache run a save's
  thread time at 31 workers is 162.9 ms, three times its 54.1 ms alone:
  provinces 29.5%, countries 17.3%, **reading the file 17.1%** (a buffer copy;
  the mapping is Linux only), `read_rest` 7.3%, `prepare` 8.1%, `top_level_blocks`
  6.3%, `build` 5.2%, store 4.7%.

### The order of what follows: the order of the task files

Chosen for completion: each stage passes the suite alone and leaves a tree
that can ship; the unknown (the shared name table, its threads, the cache) is
met first, on the smallest surface; the biggest certain gains come before the
uncertain ones, so stopping anywhere has banked the most; after the plumbing the
stages are independent, so one that runs long or is judged not worth it can be
dropped; and nothing is converted that a later stage deletes.

| task file | what | why here | expected, warm / empty cache (estimates) |
|---|---|---|---|
| `06-model-names-owners-market.md` | `names.rs`, `Sym`, the cache's `Sym`, the shift knob; `Scan.owners`, `Meta.province_owner`; `Market`. **First commit: the quick win below** | the plumbing on the two parts with least in the way: order-free, built in one place each, 2.47 M of the 9.49 M | 0.05-0.07 s / 0.03-0.05 s |
| `07-model-wars.md` | `War`, `Goal`, `Battle`, `Side`, `wars::Held`, `Book`, `save_world`, `wars::build` | the largest holder (44%); the warm cache load, the Book's fold (0.066 s) and its free | 0.07-0.10 s beyond the quick win / 0.01-0.03 s |
| *the gate* | below | | |
| `08-model-pops-and-cultures.md` | `Counter` and `Interner` in `province.rs`, `pop_by_*`, `accepted_cultures`, `primary_culture`, `Group`, `mobilizable_pops`, `Snapshot`, `Spec.mob_types` | the first-run lever: about 50,000 of a save's 221,000 allocations, in the stage that is 30% of the thread time | 0.01 s / 0.08-0.18 s |
| `09-model-techs-held-and-the-rates.md` | first half: `Held` gone, `Row.nat` slimmed, `Kept` moved; second: `tech_list`, `modifiers`, `reforms`, `nationalvalue`, the mod's dense lookups; optional: `goods_supply`, `country_flags`, the scalars | settle is 0.050 s on one thread in every run; the carried `Nation` is 2.34 M | 0.04 s / 0.04 s |
| `10-model-units-and-ships.md` | `Ship`, `Stack`, both readers, `report.rs:345` | the smallest payoff of the nation stages, two readers, two orders that reach the page | 0.02 s / 0.02-0.03 s |
| `11-model-wars-and-market-from-bytes.md` | `read_rest` without `clause::Tree`. **Optional** | 85,000 allocations a save but 7.3% of the empty-cache thread time; a reader to rewrite; needs 07 | / 0.04-0.08 s |
| `12-model-cache-and-result.md` | the cache's final form, arenas only if needed, teardown, re-measure everything | the close | 0.01-0.03 s / |
| `13-reprofile-and-next.md` | re-profile; a Windows file mapping and the worker count head its list | | |

Summed, the estimates are a warm rebuild from 1.17 s to about 0.8 s and an
empty-cache run from 2.46 s to about 2.15 s. They scale each stage's share of
the allocations by its share of the clocks; only the quick win was measured.

- **06 is not units and ships** (the first draft's choice): the owners and the
  market are order-free (reversing them moved nothing) and built in one place
  each; units and ships have two readers (`country.rs`, `walk.rs`' own), two
  orders that reach the page and the smallest payoff of the nation stages.
- **Wars second:** the biggest holder and the biggest warm-rebuild cost the
  model can reach; it needs only `names.rs`.
- **Pops before techs and units:** the empty-cache run is what the `Meta`
  stages hardly help, and pops are what the scanner, `build` and `prepare` make
  and throw away. It is also the stage with the chunk's exactness to get right,
  so it is done while there is budget.
- **`Held` is not a stage of its own:** deleting it saves memory, not time
  (settle hashes the same strings), and it is cheaper to delete with the tech
  lists it copies. Task 09 is two halves and may stop between them.
- **Task 11 is optional and last before the close:** the lowest payoff for the
  work, and it would be written twice if it came before 07. The scalar names
  (`tag`, `government`, ...) stay Strings unless the numbers ask.
- **Not taken:** the nation fields first; "carry less" as a first stage; all of
  `Meta` in one session; flattening before converting; the typed reader before
  the types.

### The quick win (not a stage; do it first, on its own or as task 06's first commit)

- **What:** `report.rs`, `walk()`. The closure that folds the saves' war records
  into the `Book` returns with `wars` (a `Vec<Vec<War>>`, 4.1 M allocations)
  still in it, so they are dropped there, and the walk's scope waits. Hand the
  drop to a `std::thread::spawn(move || drop(wars))` that nothing joins.
- **Measured** (a warm rebuild, six interleaved rounds, medians, in the probe
  tree): as it is 1.172 s; the free on a thread of its own **1.042 s** (-0.130 s,
  -11%; the walk 0.197 s to 0.069 s; heap peak 666.8 MB, unchanged);
  `mem::forget` 0.999 s (-0.173 s, -15%) but a peak of 856.0 MB (+189 MB). The
  thread is recommended; the forget is the maintainer's to choose.
- **Check it as task 02 did:** a run that ends differently is checked through a
  pipe with nothing left running (`speed/pipecheck.sh`), plus the suite and the
  reference run. Not applied in this session, which was asked for the order.
  Task 07 makes the free cheaper at its source (4.1 M allocations to about 1 M),
  but until then this is worth more to a warm rebuild than any stage.

### The gate (after task 07)

Tasks 06 and 07 carry 70% of the allocations. Measure the warm rebuild's pass
one (0.214 s now; about 0.13 s expected) and the walk. **If pass one is above
0.17 s, the allocation counts are not what the cache load costs, and the
estimates for 08-10 fall with it: re-profile (task 13's method) and re-rank
before starting 08.** In every stage's entry put expected beside measured; if a
stage gained under half of what was expected, re-rank what remains by the
numbers before the next. (The standing rule is to keep going when the
maintainer is away; this is about choosing what to do next, not stopping.)

### The task files were renumbered

`git mv` kept their history. The first version of this entry, MODEL.md in
`4fb867f` and that commit's message use the old numbers: old 06 (units and
ships) is now 10; old 07 (pops) 08; old 08 (techs, flags, the rest) 09; old 08b
(meta) split into 07 (the types) and 11 (the reader); old 09 (cache) 12; old 10
(re-profile) 13; 06 and 07 are new. `05-model-survey.md` is the task as given
and still says "tasks 06-09". MODEL.md's section 6 and its stage references
were brought to the new numbers.

### The rest

- Numbers on this PC, `398de81`, no probe (`speed/minibench.py`: `bench.sh`
  needs `bc`, `uptime` and `pgrep`, which this shell lacks): empty cache 2.465 s
  wall (pass one ends 1.469 s), warm 1.206 s (pass one 0.213 s); a second run
  2.459 s and 1.138 s.
- **The worker count** (a constant, not a model matter), empty cache, three
  interleaved rounds each: 8 workers 3.21 s, 12 2.77 s, 16 2.65 s, **20 2.54 s**,
  24 2.62 s, 31 (the default) 2.68 s. Flat from 20 up, about 0.15 s better at 20
  than at the default, within what three rounds can say. On task 13's list.
- Tools in `speed/`: `model-probe.diff` (applies to `398de81`, and so to
  `4fb867f`: a counting global allocator, a census, reverse-this-field switches
  and, new, the stage clocks; env `VIC2_ALLOC`, `VIC2_STAGES`, `VIC2_STATS`,
  `VIC2_TIMES`, `VIC2_PERMUTE`, `VIC2_WARDROP`), `permute.sh TREE FIELD...`,
  `permexample.py TREE FIELD`, `minibench.py TREE`, `cmpruns_env.py`. The probe
  tree is `~/vic2speed/rw/model05` (`398de81` plus the diff, uncommitted, its
  release build there). A stage's session applies the diff to its own tree and
  puts the same numbers beside MODEL.md's.
- **My mistakes, and what was not clean:**
  - The first version of the order was reasoned from allocation counts and from
    the lines to change, and was wrong about where the time is: the clocks put
    the biggest warm cost in `Meta` and made units and ships the least valuable
    nation stage. It was committed before the clocks were taken.
  - My first stage table was polluted by the census's own allocations (it showed
    `prepare` at 32 M); the file's numbers come from a run without the census.
    My first background batch of reversals looked empty because its launcher
    exited while the loop ran on. The 'what is held' tables count a `Box` per
    call, which MODEL.md subtracts. Two polling loops I started were killed at
    their time limit; they changed nothing.
  - One default-workers timing run read 174 ms a save for the read against 142
    in the three I kept; I discarded it (the first run after a rebuild) and did
    not look into it. An explicit `-j 15` run read 81 ms: that is the worker
    count, not noise.
  - IDENTICAL after a reversal means only that this campaign's output did not
    move; MODEL.md says why per field and keeps the order wherever that is free.
- Not verified: Linux and the mmap path (the allocation counts do not depend on
  them; the times do); a campaign with many more nations a save, where the
  weights move toward the nation fields; the cost of the `Group`s of nations
  that are not kept (every nation is kept here); every estimate in the table
  above, which is why there is a gate.
- **For the maintainer:**
  - The quick win is yours to approve as it stands (the thread) or to take as
    the forget, at 189 MB more at its peak. It is the cheapest saving found.
  - If the first run matters more than the model, **a Windows file mapping may
    be worth more than tasks 08-11 together**: reading the saves is 17% of the
    empty-cache thread time, as much as the countries. It is on task 13's list
    because it is not a model change; it needs no `names.rs` and can be done at
    any point.
  - The pass-one gain of the nation stages is the most uncertain estimate here;
    the gate after 07 exists for that.
- Not pushed. Bundle `~/vic2saveanalyzer-backup-<hash>.bundle` on this PC,
  named for the last commit.
- Next: the quick win (alone, or as the first commit of task 06), then task 06
  (`06-model-names-owners-market.md`): `names.rs` first (MODEL.md 5.2).

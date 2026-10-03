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
- Next: task 04 (`04-state-chunk.md`).

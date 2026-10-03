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

# Speeding up the scanner: shared context

Every session of this job reads this file (`speed/CONTEXT.md` in the repo),
then `STATUS.md` beside it, then its own task file (`NN-*.md`). The tasks are numbered and meant to be done in
order, one per session.

## Where this lives, and what stays private

These notes, the task files and the tools (`bench.sh`, `refrun.sh`,
`cmpruns.py`, `memj.py`, `pipecheck.sh`, `prepush.sh`) are in `speed/` in
the repo, which is public on GitHub, and so are the answers the checks
hold the real campaign to (`testkit/expected-real/`) and one reference run
of it (`speed/runs/11e1f21/`, made by `11e1f21`, now `374ac35`, and
identical through `a47e98f`), so that a clone on Windows can run both.
What else a run produces stays outside the repo, in `~/.cache/vic2speed/opt/`
(`opt/` below): `runs/` (more runs), `logs/` and `benchtmp/`. So do the gdb
tools and worktrees under `~/.cache/vic2speed/`.

The machine's own settings are in `speed/local.env`, which is not
committed (`.gitignore`): `VIC2_SAVES` (the campaign), `VIC2_MOD` (its
mod), and `VIC2_PRIVATE`, the words that must never be committed. The
scripts read it; on another machine, write one there.

**In anything committed** (these notes, INTERNALS.md, commit messages,
docs, test output pasted into them): never the maintainer's name and never
an absolute path into a home folder. Write "the maintainer", `~/...`,
`$VIC2_SAVES`, `$VIC2_MOD`, `/path/to/saves`. `speed/prepush.sh` greps
everything not yet on GitHub for `VIC2_PRIVATE` and must print nothing
before a commit of these notes or any push.

## Commit hashes changed on 2 Oct 2026

The then-unpushed history was rewritten twice on 2 Oct 2026, before its
first push to GitHub, to take personal paths and the maintainer's name out
of HANDOFF.md, INTERNALS.md, REVIEW.md and the commit messages. Every
commit from 21 Sep on has a new hash. STATUS.md and the task files name
the **original** hashes up to that day, and so do folder names in `opt/`
(`runs/11e1f21`, `runs/31a2931`, `logs/mut-ab54aa7.out`) and the bundles
in `~`. `speed/rewrite-map-2026-10-02.txt` has every row "original
intermediate final". The ones cited most (original -> final): 11e1f21 ->
374ac35, 31a2931 -> 79499d1, dd9d3e1 -> a2b8c02, a330484 -> a47e98f,
f6fa09c -> 35c8933, c262f94 -> 7ec68d4, 288813c -> bc19f16. The original
commits exist only on the laptop (worktrees `rw/base`, `head`, `mut`,
`mutbase`, `opt-probe` sit on them, and
`~/vic2saveanalyzer-backup-a330484.bundle` holds them all). Name new
commits by their new hashes.

## Where things stand

~/vic2saveanalyzer is a Victoria 2 campaign analyzer. As of 1 Oct 2026
(commit `11e1f21`) every run is made by the Rust scanner in `scanner/`
(`vic2scan analyze`: front end in `scanner/src/front/`, engine in
`scanner/src/engine/`). Python is only the window, the keeper and the
launcher that hands the run to the scanner. No crate dependencies: the maintainer
wants everything hand-written, so no mimalloc, no flate2, no rayon.

The maintainer wants it "cutting edge, blazing fast parsing". He has agreed to the
data-model rewrite (tasks 05-09), after the cheaper fixes.

The checks hold every run to **recorded answers** (`testkit/expected/`, and
for the real campaign `testkit/expected-real/`): exit status,
stdout, stderr, all nine CSV tables, and the page as what it carries (the
payload decoded, not its compressed bytes). That is the safety net for this
whole job. Any change to output, including a reordered column, fails a check
and prints the difference.

## What the profile found (1 Oct 2026, AMD Ryzen 7 6800H, 8 cores / 16 threads, 30 GB)

Campaign: `$VIC2_SAVES` (the 1880s campaign), 265 saves, 9.1 GB. Mod
(`$VIC2_MOD`): `Modus Omnino Demens 1.6`, in the Steam install's `mod/`.

Baselines on `11e1f21`:
- truly cold first run 5.16 s (measured 30 Sep);
- empty engine cache, files in page cache: 4.0-4.4 s;
- rebuild from a warm cache: 1.42-1.58 s;
- nothing changed: 50-60 ms.

**Warm rebuild (1.4 s):**
- ~0.30 s after "tables written": freeing the campaign's memory at the end
  of `engine::report::run` / `run_spec` before the process exits (seen as
  `drop_glue::<OMap<String, OMap<String, f64>>>` and `Vec<finish::Kept>` in
  gdb samples);
- 0.2-0.3 s loading 265 entries (54 MB) from the engine cache
  (`engine/cache.rs`, `Store::load`, `Pre::get`), which rebuilds every
  string and map;
- ~0.25 s map: "raster decoded, spots placed" 0.10-0.14 s and "owners"
  ~0.1 s, every run (`engine/mapflags.rs`, `report.rs`; anchors depend only
  on the mod);
- ~0.25 s payload sections, assembly, parallel gzip;
- front end before the engine ~20 ms; Python launcher ~30 ms.

**First run, pass one (~2.6-3.1 s, CPU-bound):**
- ~68 ms CPU per save; it scales linearly to 8 threads, then flattens
  (j=2 8.97 s, 4 4.72, 8 2.85, 12 2.66, 15 2.52). At the physical-core
  limit, so only less work per save helps.
- Worker-thread split, from gdb samples:
  - provinces and pops ~36% (`province::read_province`, `accumulate`);
  - countries ~23% (`country::read_country`, `parse_fields`, `Tokens`). About
    a third of that is `text::latin1` copying every country block into a
    `String` before parsing (`engine/mod.rs`, `read_flat`, around line 629);
  - ~14% compressing each save's state-history chunk in the worker
    (`finish.rs` ~line 250: JSON built, then `deflate::gzip` with the
    hand-written zlib-level-6 compressor, then base64);
  - ~15-20% malloc/free spread through the readers;
  - ~8% `province::top_level_blocks`.

**The worker count is still the Python rule** (`engine::worker_count`):
cores minus one, capped by **MemFree** × 0.6 / (3 × biggest save). On Linux
MemFree ignores the page cache, so with 18 GB of buff/cache it allowed 8, 13
or 15 threads on different runs. It happens to land near 8 physical cores
here. Use available memory (MemAvailable; Windows already uses `avail_phys`)
and size per-thread memory for Rust threads, not Python processes. Measure
whether more threads than physical cores ever helps.

**The structural cause** of the malloc share, the cache-load time and the
teardown: `engine::model::Nation` (`model.rs:126`) and what is built from it
(`finish::Pre`, `Kept`, `Row`, `Market`, the walk's tables) hold data as
`OMap<String, …>`, `Vec<String>` and `FxSet<String>`, mirroring Python dicts.
Every nation in every save owns its own copies of "cruiser", "infantry",
culture names, tech names, and so on.

## How to measure and profile

- `cargo` is at `~/.cargo/bin/cargo`, not on `PATH`. Build with
  `~/.cargo/bin/cargo build --release --manifest-path scanner/Cargo.toml`
  and check the binary's mtime: a failed build leaves the old one in place.
- Phase times: `VIC2_ENGINE_TIMES=1` prints engine phases on stderr. The
  front end has no phases of its own. `~/.cache/vic2speed/front-probes.diff`
  adds them, plus timing points after `run_spec` returns and at exit. It is
  applied, uncommitted, in the worktree `~/.cache/vic2speed/rw/opt-probe`.
- No `perf` or `strace` on this machine. gdb sampling:
  `~/.cache/vic2speed/sample_run.sh TREE OUTFILE [N]` attaches to a real
  `vic2scan analyze` run and dumps all thread stacks N times. Set `WARM=1` to
  keep its cache and `DELAY=` to set when sampling starts.
  `~/.cache/vic2speed/gdbreport.py OUTFILE` summarises the samples. gdb
  attaches are slow (~0.1 s each), so take samples across several runs.
- Always run with `TMPDIR` pointed at a scratch folder, so the real cache
  `/tmp/vic2_analyzer_cache` is never touched.
- "Cold" means truly cold to the maintainer: nothing cached and the files evicted
  from the page cache. `~/.cache/vic2speed/trulycold.py` does this, but it
  deletes the real `/tmp/vic2_analyzer_cache`. Ask the maintainer before running it,
  or adapt it to a scratch `TMPDIR` first. An empty scratch cache with files
  in the page cache is a different number; label it as such.
- Check `uptime` before trusting a benchmark. The maintainer's own window
  (`python3 app.py`) may be running; leave it alone.

## How to verify each step

- `python3 testkit/all.py "$VIC2_SAVES" --mod "$VIC2_MOD"`:
  all 28 checks must hold.
- Mutations: `testkit/mutate.py` on a worktree, never the main tree. Copy
  `scanner/target/release/vic2scan` into the worktree first. The worktree
  `~/.cache/vic2speed/rw/retire-mut` exists for this: check it out at the
  commit to test (it must be clean). Run with `--saves` pointing at the
  campaign. All 57 must be caught; a mutation that no longer applies after
  a rewrite must be re-aimed at the new code, not dropped.
- The real campaign, before and after each step: run
  `python3 vic2_analyzer.py SAVES --mod-path MOD --out DIR` with a scratch
  `TMPDIR`. Every CSV must be byte-identical. `report.html` must be
  byte-identical, except after step 5, where only its decoded payload must be
  identical; compare it with the testkit's decoding (`testkit/expected.py`).
  stdout and stderr must be identical apart from the machine's folders and
  "on N cores". Keep the before outputs under `opt/runs/<commit>/`
  (`speed/refrun.sh`, compared with `speed/cmpruns.py`); a name not found
  there is looked up in `speed/runs/`, so `cmpruns.py 11e1f21 NEW` works
  on any machine.
- The full mutation run takes about an hour. Start it in the background
  as soon as a commit is ready, and work on the write-up meanwhile.
- If a step deliberately changes output (it should not), stop and ask the maintainer
  before running `testkit/all.py --update-expected`.

## Rules for the laptop (learned the hard way)

- Real data, read only, never write:
  - saves: `$VIC2_SAVES`;
  - the game: `~/.local/share/Steam/steamapps/common/Victoria 2`;
  - the real cache: `/tmp/vic2_analyzer_cache`;
  - settings: `~/.config/vic2saveanalyzer/settings.json`.

  Never build a test world out of symlinks to real files; copy instead.
- `~/.cache/vic2speed/rw/` holds long-lived worktrees (`base`, `head`, `mut`,
  `mutbase`, `retire-mut`, `opt-probe`). Run `git worktree list` before
  creating or deleting anything there, and give new ones names that cannot
  collide. A previous session deleted `rw/base` by accident.
- A change to how the program ends must be checked with its output going
  through a pipe, looking for leftover processes afterwards.
- The maintainer develops on Fedora and ships `dist/vic2saveanalyzer.exe` on Windows.
  The exe can only be rebuilt on Windows. Anything platform-specific (thread
  counts, memory queries, mmap) is unverified on Windows; say so.
- Work goes straight to `main`, one commit per step, in the repo's
  commit-message style (see `git log`). `origin` (public GitHub) was
  brought level with main on 2 Oct 2026 (`a47e98f`), at the maintainer's request, and
  this laptop is logged in to GitHub (`gh`, account vic2tools). Don't push
  again unless the maintainer asks; when pushing, run `speed/prepush.sh`
  first. The maintainer clones on the Windows PC from GitHub. After a batch of commits, make a
  fresh bundle in `~` named for its commit
  (`vic2saveanalyzer-backup-<hash>.bundle`).
- Add a dated section to `INTERNALS.md` under "## Speed" (newest first)
  with the before/after table for each step and what was tried and dropped.
- The maintainer wants verified work, not check-ins. If he is away, keep going. Report
  failures and your own mistakes plainly, including speedups that did not
  pan out.

## How a session ends

- `speed/STATUS.md` is committed with the session's last commit, after
  `speed/prepush.sh` prints nothing.
- Every step that is finished is committed, with the checks, the real
  campaign comparison and (where the task says so) the mutations done.
- `STATUS.md` gets a dated entry: what was done (commits), the numbers
  before and after, what was tried and dropped, anything left half done and
  exactly where, and anything the next task needs to know.
- If a task turns out bigger than one session, stop at a clean, committed,
  passing point, and say in `STATUS.md` what is left. Don't start the next
  task file.

# Repo cleanup: design

Date: 2026-10-16. Status: draft for the maintainer's approval.

## Why

The public repo (github.com/vic2tools/vic2saveanalyzer) has become hard to
read and slow to work in. The Rust rewrite finished on 1 Oct and the speed
job after it, but the repo still carries both jobs' scaffolding:

- working notes;
- benchmark tools;
- a committed exe;
- the maintainer's own campaign as test data;
- a 6,500-line web page held inside a Python string;
- Python files that now only launch the Rust scanner.

The full mutation run takes 40+ minutes, almost all of it spent recompiling.

Three kinds of reader should be served (the maintainer's words, lightly
condensed):

1. **Someone who wants to download the tool.** They find the download, what it
   does and how to run it within a minute.
2. **Someone forking it to adapt it, often with an AI assistant.** "The AI
   would know exactly where to look for what they want."
3. **A developer reading the code alone.** They understand it unaided.

## Goals

- A top level a stranger reads in seconds, with one map of where everything
  lives, and every file and folder saying what it owns.
- Nothing stale or historical in the tree. An AI takes every line as current;
  history stays in git.
- A short test loop: one command for the suite, a mutation run of minutes not
  an hour, verdicts that cannot mislead.
- Structurally simpler code, by the thermo-nuclear review's standard:
  - delete layers rather than rearrange them;
  - one owner per rule;
  - no file over 1,000 lines without a reason.
- A real-campaign baseline the maintainer can record and compare against
  whenever the engine changes.

## Non-goals

- New features, or any change to what the report shows.
- Making the scanner faster. Speed tasks 11-13 are dropped; the maintainer
  was told their gain is marginal.
- Rewriting git history.

## Anti-goals (failure even if the code "works")

- Any change in output. Every CSV, the report payload, stdout and stderr stay
  identical, apart from the explicit exceptions under "Decisions". A cleanup
  that shifts a number is a failed cleanup.
- Weakening the privacy guard. Nothing may push the maintainer's name or
  home paths.
- Losing test coverage silently. A check removed is either repeated elsewhere
  or named as dropped.
- Moving complexity around without deleting any.

## Constraints

- **No crate dependencies in `scanner/`**, by the maintainer's standing choice.
- **Privacy.**
  - The repo is published under a separate GitHub identity. Check
    `gh auth status` before any push. Never push the `.bundle` files.
  - `prepush.sh` (grep for `VIC2_PRIVATE`) must keep working and must pass
    before any push.
  - Nothing committed may name the maintainer or an absolute home path. Write
    `~/...`, `$VIC2_SAVES` and so on.
- **The machine.**
  - Windows 11, Python 3.14. Rust is the GNU toolchain from rustup, in
    `~/.cargo/bin` and not on PATH.
  - Git Bash has no `bc`, `uptime` or `pgrep`.
  - The real saves and mod are in `speed/local.env`, which is not committed.
  - The checks must hold on Windows. Linux-only paths may stay, but must be
    named.
- **No pushes, releases or exe uploads without the maintainer saying so.**
  Work happens on a local branch; commits there are fine.
- **Every commit passes the suite on its own.**

## Decisions

### Made by the maintainer

- All five workstreams are in scope, in the order below.
- The speed job is over. Its notes and benchmark tools leave the tree.
- The exe ships through GitHub Releases only. `dist/vic2saveanalyzer.exe` is
  no longer tracked, and "rebuild the exe before committing" stops being a
  step.
- The real campaign stays a verified baseline for engine changes, in two
  parts:
  - **The public repo** carries the mechanism: record a baseline from any
    campaign, then compare later.
  - **The maintainer's own record** lives outside the public repo (a private
    location, via an environment variable).
  - Forkers get the tool, not the maintainer's answers.

### Proposed by me and accepted by the maintainer

- `python gui.py`, `python keeper_gui.py` and `python keeper.py` stop being
  standalone entry points. The exe and `vic2_analyzer.py` (or its successor,
  see 5) stay.
- `md5.rs` and the `mod-signature` mode are replaced by the scanner's own
  two-lane hash. The mod cache goes cold once. The bytes of `report.stamp`
  change, as they already do on every build.
- No history rewrite. Old exes and campaign data stay in past commits, and
  the clone stays about 71 MB.

### Settled during the builder check (my calls unless marked)

- **Releases already exist.** v1.0 (2026-10-16) carries
  `vic2saveanalyzer.zip`. The README's download section links to
  `releases/latest`. The builder does not create releases.
- **`python vic2_analyzer.py …` keeps working**, through a thin root shim
  into the package. The maintainer accepted "the exe and `vic2_analyzer.py`
  stay".
- **Visible differences in the page (the maintainer's call).** In phase 2 of
  workstream 3, a merge may change what a viewer sees in small ways, such as
  sort order of blanks, a shade, or a flag's size. Each one is listed in its
  commit. At the end of phase 2 the builder stops and shows the maintainer
  before-and-after screenshots of every changed spot. Each change is
  approved or reverted before workstream 4 starts. That is the only planned
  pause in the job.
- **Stale checks may be repaired.** Tests are not output: a UI check that
  fails only because the page drifted (selectors, probe patching) is
  repaired, not deleted. A check that exposes a real product bug is not
  fixed in this job. The builder stops and reports it to the maintainer,
  and the check is marked as a known failure.
- **The baseline keeps one anchor.** `baseline.py compare` takes a named,
  narrow exclusion (`--ignore payload.wars[].side_losses`), used only from
  the commit that drops that key onward. The baseline recorded from
  `30ed940` is never overwritten during this job.

## Verification bar (applies to every step)

1. **Before any product code changes**, record the maintainer's campaign
   baseline with the current HEAD (`30ed940`). This uses the new
   `baseline.py` from workstream 1, which only touches `testkit/`.
2. **After each commit:**
   - `python testkit/all.py "$VIC2_SAVES" --mod "$VIC2_MOD"` passes;
   - `baseline.py compare` is identical;
   - for a commit that moves code a mutation patches, the mutation run for
     the affected mutations is all CAUGHT.
3. **At the end of each workstream**, the full mutation run is all CAUGHT,
   apart from known Linux-only ones (`keeper-folder-windows-only`).
4. **The page.** "Identical" means the built `template.html` is byte-identical
   while the page is only being moved (workstream 3, phase 1). After that,
   the decoded payload is identical, and the change to the page around it is
   reviewed and re-recorded deliberately.

## The work, in order

### 1. A fast, honest test loop (`testkit/`)

**The mutation harness (`mutate.py`):**

- **Fast build.** Build mutated scanners with:
  - `CARGO_PROFILE_RELEASE_LTO=false`
  - `CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16`
  - `CARGO_PROFILE_RELEASE_INCREMENTAL=true`

  These are set in the environment, not in `Cargo.toml`. Measured: 37 s
  becomes about 4 s per rebuild. The committed binary is put back after each
  mutation, as today.
- **Honest verdicts.** `check()` returns `(exit code, timed out, output)`.
  - The verdicts are CAUGHT, BLIND, TIMEOUT, SKIPPED, NOAPPLY, NOBUILD, and
    UNTESTED with its reason.
  - CAUGHT means exit not 0, not 77, and no timeout. Today a SKIPPED (77)
    counts as caught and a timeout as BLIND.
  - A control-run timeout must not crash the run.
  - Exit 1 on any BLIND. `--strict` also fails on TIMEOUT and SKIPPED.
  - Lower the timeout from 900 s to something proportionate. The slowest
    check is about 12 s; the builder picks the value.
- **The mutations become data.** `mutations.py` holds a table of
  `Mutation(name, bug, catcher, needs, patches=[(path, old, new)])`. Every one
  of the 83 is only `patch()` calls today. The harness stays in `mutate.py`.
- **Its own worktree.** The harness creates and cleans up its own worktree,
  copying the scanner in. That removes the `--tree` hazard and the dirty-tree
  instructions.
- **Parallel controls.** Control runs go in parallel.

**One list of checks.** `suite.py` declares each check with:

- what it needs: scanner, saves, report, mod, Firefox, display, rustc;
- whether it holds a record;
- whether it is slow.

`all.py`'s order and filtering, `--update-expected`, `mutate.py`'s arguments
and the README's command list all come from it. The six UI checks nothing
runs today each either join the list (if they pass) or are deleted:

- `compare_ui`
- `export_ui`
- `war_export_ui`
- `military_ui`
- `population_history_ui`
- `map_rendering`

**Shared basics: `testkit/kit.py`.**

- It holds `ROOT`, `SCANNER`, `analyze(saves, out, *flags, …)`,
  `need_scanner()`, `need_firefox()`, `need_display()` (each exits 77), and a
  `holding()` temp context with its own `TMPDIR`. This replaces about 15
  copies of the analyzer launch, 41 `sys.path.insert` lines and five
  "needs a scanner" variants.
- One meaning of "skipped": a missing tool skips (77), never passes silently.
- The world builders move from `matching.py` (a check that ten files use as
  a library) into `fixtures.py`.
- `expected.hold_cases(...)` replaces the record/compare loop copied in five
  checks.

**Overlap goes.**

- **`smoke.py`** is deleted, and `--quick` with it. Its flag matrix is
  already held to exact answers by `enginecheck` and `frontcheck`.
- **`edges.py`'s unique cases** move into `frontcheck`'s recorded table, and
  `edges.py` is deleted. The unique cases are:
  - a first-month save;
  - a war over before the first save;
  - nations with no pops;
  - out-of-order saves;
  - a war with no battles;
  - bad numbers.
- **`facts.py`'s self-comparison** (Python twin against Python twin) is
  replaced by reading the rebuilt `DATA.facts` in the browser probe and
  comparing it with `nations_timeseries.csv`.
- **The browser checks** share one Firefox session per report through
  `boots.looked(path, probes=[...])`. They no longer patch `boots.WATCHER`
  with `str.replace`.
- **`frontcheck`'s Python twin of the mod signature** is replaced by a
  property test (it changes when a covered file changes, and not otherwise).

**`all.py`** runs independent checks in parallel (about cores/4, since the
scanner fans out itself), each with its own `TMPDIR`. No check writes the
user's real cache.

**The baseline: `testkit/baseline.py`.**

- `record CAMPAIGN_DIR --mod MOD [--into DIR] [--count N]` picks evenly
  spaced saves plus the last one. It freezes them in `manifest.json`: name,
  size, sha256, mod name, extra modifier, git commit. It then records
  today's `enginecheck` real `RUNS`.
- `compare CAMPAIGN_DIR [--from DIR]` finds each manifest save by name.
  Extra saves in the folder don't matter. A missing or changed save gives
  SKIPPED, and the message names it.
- `DIR` defaults to `$VIC2_BASELINE`.
- `enginecheck.py` keeps only the synthetic edge world, extended with armies
  and ships so its mutations can be caught without real saves. The real half
  moves into the baseline. Mutations the synthetic world cannot catch run
  against the baseline. The same split applies to `modread.py`'s real-mod
  half.
- The maintainer's existing `testkit/expected-real/` (48 MB, recorded from an
  older save set) is not migrated. A fresh baseline is recorded from HEAD
  `30ed940` (verification bar, point 1).

### 2. The repo's shape

- **`speed/` leaves the tree.**
  - `prepush.sh` moves to `tools/prepush.sh` and reads `VIC2_PRIVATE` from a
    non-committed `tools/local.env` (or the same variables in the
    environment). It is also offered as a git pre-push hook.
  - What `pipecheck.sh` checks (exit through a pipe, no leftover process)
    moves into `engine_runtime.py`.
  - Everything else goes. `refrun.sh` and `cmpruns*.py` are superseded by
    the baseline. `minibench.py`, the notes, the censuses and `runs/` also
    go.
- **The exe.**
  - `dist/vic2saveanalyzer.exe` is untracked and `.gitignore` drops the
    negation.
  - `build_exe.py` remains the way to build it for a release. The README's
    download section points at Releases.
  - The `vic2.ico` that `build_exe.py` draws pixel by pixel becomes a
    committed file, byte-identical to the one drawn today, and the drawing
    code goes.
- **`testkit/expected-real/` leaves the tree.** `testkit/expected/` (the
  synthetic records) stays.
- **Docs.**
  - `README.md` is for players: what it does, download, how to use it, the
    tabs, accuracy, licence.
  - `DEVELOPING.md` (name is the builder's call) opens with a "where things
    live" map: one line per folder and per major file. Then come:
    - how a run flows (window → launcher → `vic2scan analyze` → front →
      engine → page);
    - how to check a change (one command, and what each kind of check
      needs);
    - how to record and compare a baseline;
    - how to build a release.
  - The still-true technical knowledge in `INTERNALS.md` (save-format quirks,
    why numbers are formatted Python-style, the cache, the build id) is
    rewritten as present-tense reference, either inside the guide or as
    `docs/` pages it links. The rest of `INTERNALS.md`, and all of
    `HANDOFF.md` and `REVIEW.md`, leave the tree.
  - Each folder (`scanner/`, `testkit/`, `host/`, the Python package) gets a
    few lines saying what it owns, in a short README or a module header.
- **Leftover worktrees.** About 30 worktrees under `~/vic2speed/rw/` are
  local clutter, not repo content. List them for the maintainer; remove them
  only with their go-ahead.
- **Assistant memory.** The notes about rebuilding the exe before committing
  and about `speed/minibench.py` are updated at the end.

### 3. The report page (`template.py`)

**Phase 1: move only, byte-identical.**

- The page becomes real files under `scanner/src/page/`, split at existing
  line boundaries in the original order. The review's table gives about 25
  files: `head.html`, `css/*.css`, `body.html`, and one `js/*.js` per area
  (boot, core, widgets, map, wars, wars-legacy, market, tech, military, …).
- `build.rs` concatenates an explicit ordered list. Being under `src/`, the
  files are already covered by the build id and `rerun-if-changed`.
- The `testkit/expected.template()` reader, `facts.py`'s loop extraction,
  `staleness.py`'s special case and the six Wars mutations are retargeted.
- `template.py` is deleted.
- Proof: the sha256 of the built `template.html` is unchanged.
- All JS stays inside the one async IIFE; turning it into modules is out of
  scope.

**Phase 2: restructure, payload identical.**

- Each tab's code gathers into its own file. Fix the misleading banners:
  NATIONS is really Compare's trends, and Population is split in two today.
- One sortable table (`sortRows` plus `sortableHead`) replaces five.
- One flag helper replaces four.
- `fillSelect`, `toggleButton`, `svgMessage`, `parseDate` and
  `sumFact(tags, date, key)` replace their copies.
- One cached province-geometry pass in `map.js` replaces three raster scans,
  and the atlas uses the named map colours.
- One pie and one `downloadBlob`.
- Tabs register `{available, init, exportSubtitle}`, and boot loops over
  them.
- Dead code goes:
  - the hidden culture table and `#poptag`;
  - about 35 lines of unused CSS;
  - `isPlayer`;
  - `mapShowBattles`;
  - the `belParties` and `Array.isArray` shims for data that predates the
    present payload;
  - `DATA.x || {}` guards on keys the engine always writes;
  - `ibLosses`.
- War losses get one owner. The page computes them (it needs the side rule
  anyway), and `side_losses` is dropped from `wars.rs`. This is the one
  payload change in scope: the payload diff is that key only.
- `drawMilPies` (313 lines) and `mapRender` (241 lines) split into data,
  text and draw steps. The population detail code, written in minified
  style, is reformatted.
- Proof for phase 2: identical payload (except `side_losses`), the UI
  checks, and a deliberately re-recorded page diff.

### 4. The Rust scanner

- **A typed `Run` instead of a JSON round trip.**
  - Today the front builds a JSON spec (`front/mod.rs` `spec_for`, patched
    by key in `front/mod.rs` and `cross.rs`) that the engine parses back in
    the same process (`engine/mod.rs` `parse_run`, `tables.rs` `from_spec`,
    `explain.rs` `Ask::from_json`).
  - The front builds `engine::Run` directly instead. The diagnostics become
    an enum, and the cache contexts hash typed fields using one shared hash.
  - Remove `own_refusals` (always true) and its arms, the never-sent
    `tables`/`template` spec path, and the double `protocol`.
  - `bench-engine` takes RUN.json through the front's setup.
  - Cache keys already include `VIC2_BUILD_ID`, so changing their format
    costs nothing.
- **Dead code.**
  - `out.rs` `HELD` and `release()`: nothing ever holds.
  - `report::run`'s unused `live` and the `raster` None fallback.
  - `Nation.money_total` and `Nation.province_state`, with their producers.
  - `Market.snapshot[5]`, `Nation::blank()`, and the cache shims for the old
    fleet and stack layouts.
  - The `selftest-deflate huff`/`levels` modes, and `LEVEL4` if only `gz4`
    uses it.
- **Stringly variants become enums.**
  - `Decline`'s `"\u{1}raised: "` prefix → `enum Decline { Raised, Unreadable }`.
  - `cross`'s verdict strings → `enum Verdict`.
  - `front::run`'s peek/verify/cross bools → a `Mode` enum. Keep today's
    print order.
  - `Settle::{Refused, Back}` gets names that are true now.
- **One owner per rule.**
  - A crate-level `py/` module holds the Python-semantics helpers:
    - `py_float` and `py_int`;
    - `repr` over both trees;
    - `os.path` join, dirname and basename;
    - `pyfmt`, `pyre` and `jsonr`.

    Where two copies really differ (overflow bounds 9.0e18 vs 9.2e18,
    None vs decline), keep both as named variants.
  - One tokenizer.
  - `clause::V` accessors become methods; `SCALARS` and `NUMERICS` become
    one table.
  - The trigger-key list in `report.rs` `unreadable` moves into `rules.rs`
    and is derived from the same const as `condition_ok`.
  - `explain.rs` calls finish's brigades and cluster filter instead of
    copying them.
  - A small JSON writer in `dump.rs` replaces about 40 hand-placed separators.
  - `csv_line` and `line`, and `name_for`, are each written once.
  - Magic table indices 100 and 101 become an enum.
- **Layout.**
  - The `src/` root splits into:
    - `save/` (country, province, clause, text, names, walk);
    - `py/`;
    - `util/` (fx, omap, deflate);
    - the existing `front/` and `engine/`.
  - Selftests move to `selftest.rs`.
  - `engine/mod.rs` splits into an orchestrator plus `readsave.rs` and
    `pool.rs`. `bench` uses the shared readers (today's copy has drifted).
  - `modread.rs` (2,315 lines) splits into `modread/` with `reader.rs`,
    `pieces.rs` (one function per game file) and `export.rs` (writer and
    reader of the mod JSON together).
  - `report.rs` (1,680 lines) splits into `report/` with `mod.rs`, `map.rs`,
    `csv.rs`, `say.rs` and `sections.rs`.
  - `cross.rs` splits into survey and payload.
  - `model::read_war` moves into `wars.rs`.
  - `Mod` stops being a three-phase object with `Option` fields: it becomes
    `settle_campaign(Mod) -> Rules`, and the duplicated string-keyed rate
    maps beside `Dense` go.
- **`md5.rs` and `mod-signature`** go (see Decisions).
- **`pypath::gettempdir`** goes. The launcher passes `cache_dir` in RUN.json,
  so the two sides can't disagree.
- **Comments** that describe the deleted Python handover are rewritten:
  - `front/mod.rs` header;
  - `diagnose.rs`;
  - `jsonr`;
  - `rules.rs`, `modread.rs`, `tables.rs`, `report.rs`;
  - "a faster province scanner".

### 5. The Python app

- **One package for the 13 runtime modules.** The package name is the
  builder's call (`vic2tools/` was suggested). It holds:
  - `launch.py`: `vic2_analyzer` + `run` + `fastscan` + the readfolder
    callbacks.
  - `report_tab.py`: `gui` + `cross` + `mod_reader` + readfolder's cache
    functions.
  - `keeper.py`: `keeper` + `savehead` + `dates`.
  - `keeper_tab.py`.
  - `share.py`, formerly `publish`.
  - `settings.py`.
  - `__main__.py`, formerly `app`.

  `build_exe.py` stays at the root. If the documented
  `python vic2_analyzer.py …` must keep working, a three-line root shim
  stays; otherwise the docs say `python -m <package>`.
- **Callbacks become arguments.**
  `analyze(run, *, say, cancel, progress, ready)` replaces the module-global
  callbacks in `readfolder.py` and `vic2_analyzer.py`. `gui.py`'s `Pipe` and
  its swap of the process-wide stdout and stderr go.
- **Dead worker setup goes:**
  - the three `freeze_support()` calls;
  - the import-order rule;
  - imports placed inside functions "for workers";
  - `build_exe.py`'s hidden-import list, and `packing.py`'s policing of it.

  Verify by comparing the PyInstaller archive listing before and after.
- **Duplicates collapse.**
  - The two share flows in `app.py` become one worker.
  - One "first existing folder" helper in `settings.py`.
  - The scanner's location is written once and imported by `build_exe.py`.
  - `run.py`'s unused `REPORTED` goes, and its stale prose is rewritten.
  - `gui.py` lines 607-615 become two plain checks: `is_install` and
    `_same_folder`.
- **`mock_host.py`** parses the worker's accepted marks from `worker.js`
  instead of copying them.
- **Rules both Python and Rust implement get one owner each, or a check
  holding the pair together:**
  - `settle_game`;
  - `campaigns_in`;
  - the save-date sort.

## Left to the builder

- The order of commits inside each workstream, and how to group them.
- Every new file and module name not fixed above.
- The mutation timeout value.
- The parallelism level in `all.py`.
- Whether the developer guide is one file or a guide plus a few `docs/`
  pages.
- Where any review finding turns out wrong on closer reading: skip it, and
  say so in the commit.

## Where these documents live

This design, and the plan that follows, sit in `docs/superpowers/` during the
work. They describe a job, not the code. By the "nothing historical in the
tree" goal, they leave the tree in the final commit, and git keeps them.

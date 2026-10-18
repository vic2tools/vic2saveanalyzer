# Workstream 5: The Python App. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The 15 Python files at the repository's root (3,496 lines)
become one package, `vic2tools/`, of seven modules. Along the way:
- the module-global callbacks become arguments;
- the multiprocessing-era setup and the bundler's hidden-import list go;
- duplicates collapse;
- each rule both Python and the Rust scanner implement gets one owner, or a
  check that holds the two together.

Nothing a user sees changes:
- the window, the command line, the exe, the recorded answers, and every
  CSV, payload and line of output;
- `python vic2_analyzer.py …` keeps working.

**Architecture:**
- **The package.** `vic2tools/` sits at the root beside `scanner/`. Its
  modules import each other absolutely (`from vic2tools import settings`).
- **Two entry points stay at the root:**
  - `vic2_analyzer.py` is a three-line shim into `vic2tools.launch`, which
    every document and check uses;
  - `build_exe.py` packs `vic2tools/__main__.py`.
- **The move comes first and changes no logic** (Task 1), as in workstream 4.
  Later tasks rewrite code in its final home.

**Tech Stack:**
- Python 3 standard library, tkinter.
- PyInstaller, for releases only.
- The test kit: `all.py`, `mutate.py` with `mutations.py`, `window.py`,
  `keeping.py`, `sharing.py`, `packing.py`, `docrefs.py`, and the unit tests.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-cleanup-design.md` (workstream 5, Decisions, Anti-goals, Verification bar, "Where these documents live").

## Global Constraints

- **No output change.** Every CSV, the report payload, stdout and stderr stay
  identical. The window's log says what it says now.
  - The one exception is in Task 2. A line the scanner prints now reaches
    the log whole rather than in chunks; the text is the same.
- **Entry points:**
  - `python vic2_analyzer.py …` keeps working, through a root shim;
  - `python gui.py`, `python keeper_gui.py` and `python keeper.py` stop
    being entry points (Decisions);
  - the exe and `vic2_analyzer.py` stay.
- **After every commit:**
  - `python testkit/all.py "$S" --mod "$M" --baseline ~/vic2-baseline`
    holds: all checks, with the baseline still run with its
    `--ignore payload.wars[].side_losses`;
  - `python testkit/mutate.py --dry` shows 0 NOAPPLY;
  - the unit tests pass;
  - every mutation whose patched code moved or changed is run and CAUGHT.
- **At the end:** the full mutation run catches everything except
  `keeper-folder-windows-only`.
- **No file over 1,000 lines** without its reason at the top.
- **The exe's contents are compared**, not trusted. Before Task 1, record the
  PyInstaller archive listing of a release build: its module names. After
  Task 3, the listing holds the same standard-library and program modules.
  Program modules may carry new names; nothing else may change.
- **Where a spec item turns out wrong on closer reading,** skip it. Say so in
  the commit message and the ledger.
- **Machine.**
  - Windows. Run one heavy command at a time: the PC hard-resets under heavy
    load.
  - cargo is at `~/.cargo/bin`.
  - Nothing is pushed or released.
- **Branch and commits.**
  - Work on local branch `cleanup/python-app` from `main` (`f64ffab`).
  - Commit messages are plain sentences, ending with
    `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The exe started with arguments** (a folder dropped on it, or a
   terminal) runs the command line, with its output in the console. Started
   bare, it opens the window and never a second one. `freeze_support` goes
   in Task 3: confirm nothing in the program starts a `multiprocessing`
   worker any more (the scanner is a subprocess), and that the frozen exe
   started with `--help` prints and exits. Task 3 tests this.
2. **The Stop button.** It kills the scanner, the log says the run stopped,
   and the cache keeps what was read. This must still happen once `cancel`
   is an argument rather than a global (Task 2). `window.py` holds it; Task 2
   runs `window.py` before and after.
3. **A window closed during a run, and a share that fails.** No callback may
   fire into a destroyed window, and none may write to a widget from a
   worker thread. Once the stdout swap goes (Task 2), every line still
   arrives through the log queue. Task 2 adds a check that `analyze` writes
   nothing to `sys.stdout` when `say` is given.
4. **Settings written before this change.** The settings files and their
   keys stay exactly as they are (`settings.py` only moves), so a user's
   remembered folders and token survive the update. Task 1 asserts the paths
   `settings.ANALYZER`/`KEEPER` resolve unchanged.
5. **The cache's "empty" button.** `cache_stats`/`clear_cache` count the
   scanner's entries by their file suffix. Their move (Task 1) and the
   callbacks change (Task 2) must keep them pointed at the folder
   `vic2_analyzer.py` writes into RUN.json. `caching.py` and `window.py`
   hold this.

---

## Before Task 1

- [ ] Build a release the way a maintainer does:
  `cargo build --release …`, then `python build_exe.py`.
- [ ] Record the archive's module list:
  ```
  python -m PyInstaller.utils.cliutils.archive_viewer -r -b dist/vic2saveanalyzer.exe
  ```
  The list goes to the workspace (`.superpowers/sdd/…/archive-before.txt`),
  not the repo.
- [ ] Note the settings paths: `settings.ANALYZER` and `settings.KEEPER`.

### Task 1: One package, `vic2tools/` (moves only)

**Files:**
- Create: `vic2tools/__init__.py`, holding a one-paragraph docstring that
  names each module.
- Create the modules, each concatenated from the old files with only
  import lines changed:

| New module | From |
|---|---|
| `vic2tools/launch.py` | `vic2_analyzer.py` (all but the `if __name__` block), `run.py`, `fastscan.py`, and `readfolder.py`'s cache folder functions (`cache_dir`, `cache_stats`, `clear_cache`) and callbacks |
| `vic2tools/report_tab.py` | `gui.py` (less its `main`), `cross.py`, `mod_reader.py` |
| `vic2tools/keeper.py` | `keeper.py` (less `main` and its argparse), `savehead.py`, `dates.py` |
| `vic2tools/keeper_tab.py` | `keeper_gui.py` (less `main`) |
| `vic2tools/share.py` | `publish.py` |
| `vic2tools/settings.py` | `settings.py` |
| `vic2tools/__main__.py` | `app.py` |

- Replace `vic2_analyzer.py` with the shim:
  ```python
  """The command line: python vic2_analyzer.py SAVES [options]. See README.md."""
  from vic2tools.launch import main
  main()
  ```
- Delete the other 14 root `.py` files except `build_exe.py`.
- Modify:
  - `build_exe.py`: the entry script is `vic2tools/__main__.py`, with
    `--paths` set to the root;
  - every `testkit/*.py` that imports or names these modules;
  - `testkit/mutations.py` paths;
  - `README.md`, `DEVELOPING.md`, `testkit/README.md`.

  `docrefs.py` holds these.

**Rulings this task takes:**
- **The cache folder functions go to `launch.py`, not `report_tab.py`.** The
  cache is the scanner's, and `launch` names its folder in RUN.json. A tab
  that drives the launcher should not be what the launcher imports.
- **`keeper.py`'s command line goes,** as Decisions says `python keeper.py`
  stops being an entry point. So does the `main` in `gui.py` and
  `keeper_gui.py`. If a check starts one of them, it moves to the package
  API (`keeping.py` drives `keeper.watch`).
- **`report_tab.py` is about 950 lines.** If it comes out over 1,000, put
  `cross.py`'s and `mod_reader.py`'s functions in `vic2tools/campaigns.py`
  instead, and say so.

**Interfaces:**
- Produces the module names above. Every later task works in them.
- `vic2tools.launch` exports:
  - `main(run=None)`;
  - `analyze(run, …)`, whose callbacks become arguments in Task 2;
  - `Run`, `RunError`, `Cancelled`;
  - `command_line()`;
  - `cache_dir()`, `cache_stats()`, `clear_cache()`.

**Steps:**
- [ ] **Failing test.** Add `testkit/test_package.py`:
  - `test_the_package_names_each_module`: `import vic2tools.launch,
    vic2tools.report_tab, vic2tools.keeper, vic2tools.keeper_tab,
    vic2tools.share, vic2tools.settings` succeeds.
  - `test_settings_files_stay_where_they_were`: `vic2tools.settings.ANALYZER`
    ends with `vic2saveanalyzer/settings.json`, and `KEEPER` is
    `keeper.json` beside it (Review Focus 4).
  - `test_no_program_module_is_left_at_the_root`: the root's `*.py` files
    are exactly `{"vic2_analyzer.py", "build_exe.py"}`.

  Run it. Expected: it fails on the import.
- [ ] Make the move with a throwaway script. It concatenates in the order
  above, rewrites the imports, and `git mv`s where a file moves whole, so
  history follows. Prove the move is pure: added and removed lines are equal
  as a multiset, once import lines, the deleted `main`s and the entry-point
  boilerplate are dropped.
- [ ] Repoint the test kit, the mutation rows (`mutate.py --dry` shows 0
  NOAPPLY) and the docs.
- [ ] Run the unit tests, `all.py` with the baseline, and `docrefs.py`. Run
  the mutations whose file moved.
- [ ] Commit: "The Python app is one package, vic2tools/, of seven modules;
  nothing in them changes".

### Task 2: The callbacks are arguments

**Files:** `vic2tools/launch.py`, `vic2tools/report_tab.py`,
`vic2tools/__main__.py`, `testkit/window.py` (only if it reaches the
globals).

**Interfaces:**
- Produces
  `analyze(run, *, say=None, cancel=None, progress=None, ready=None) -> int`.
  - `say(text)` takes each line the scanner prints, stdout and stderr alike,
    in order of arrival.
  - With `say` None, lines go to `sys.stdout`/`sys.stderr` as now.
- `_relayed(argv, flags, *, say, cancel, progress, ready)` takes them
  explicitly. `set_cancel_check`, `set_progress`, `set_report_ready`,
  `stop_if_asked`, `tell_progress`, `_tell_report_ready` and the module
  globals `_STOP`, `_PROGRESS` and `_REPORT_READY` go.
- `report_tab.App.work` calls
  `analyze(run, say=self.log_queue.put, cancel=self.stop.is_set,
  progress=self.on_progress, ready=self.on_report_ready)`.
  - `Pipe` and the swap of `sys.stdout`/`sys.stderr` go.
  - What the window's own code prints during a run goes through
    `self.log_queue.put`.

**Steps:**
- [ ] **Failing test (Review Focus 3).** Add
  `test_package.test_analyze_hands_every_line_to_say`. Run `analyze` on a
  stub scanner, a tiny script set as the binary through
  `launch.fastscan`'s lookup. It prints two lines to stdout, one to stderr,
  and `@progress 1 2`. Assert:
  - `say` received the three lines in order;
  - `progress` got `(1, 2)`;
  - nothing reached the real `sys.stdout` (capture it with
    `contextlib.redirect_stdout`).

  Expected: it fails on the `say` keyword.
- [ ] Make the change. The relay threads call `say`; there is no global
  state.
- [ ] Run `window.py` (Review Focus 2) and `caching.py`: they pass. Run
  `all.py`, then the mutations in `launch.py`/`report_tab.py`.
- [ ] Commit: "A run's callbacks are arguments; the window no longer swaps
  the process's stdout to read a run's log".

### Task 3: The worker-era setup goes

**Files:** `vic2tools/__main__.py`, `vic2tools/report_tab.py`,
`vic2tools/launch.py`, `vic2tools/keeper.py`, `build_exe.py`,
`testkit/packing.py`, `testkit/suite.py`.

- Remove:
  - every `multiprocessing.freeze_support()` call and its import;
  - the "before anything else is imported" ordering rule in `__main__.py`
    and its comment;
  - imports placed inside functions "for workers", or to keep the import
    order. These move to the top of their module (`cross`, `traceback`,
    `ctypes` on Windows only where it is, `subprocess`, `json`, `tempfile`,
    `dataclasses`, `vic2_analyzer`, …).

    An import kept inside a function for a real reason (`ctypes` on Windows
    only) stays, with that reason in a comment.
  - `build_exe.py`'s `carried` hidden-import list. With one package reached
    from `__main__.py`, PyInstaller's own scan finds every module.
  - `testkit/packing.py`, which policed that list. The check it made, that
    the exe carries every program module, becomes Task 3's archive
    comparison.

    Before deleting it, read what else `packing.py` holds. Anything that is
    not the hidden-import check moves to a check that survives. Take
    `packing.py` out of `suite.py`'s list and name it as dropped in the
    commit message.

**Steps:**
- [ ] **Failing test (Review Focus 1).** Add
  `test_package.test_nothing_starts_a_python_worker`. No module of
  `vic2tools` imports `multiprocessing` (an `ast` walk over the package).
  Expected: it fails on `__main__.py`.
- [ ] Make the removals.
- [ ] Build a release (`python build_exe.py`) and record
  `archive-after.txt` the same way. Diff it against `archive-before.txt`:
  - the standard-library and tkinter modules match;
  - the program's modules are now `vic2tools.*`;
  - no program module is missing.

  Run `dist/vic2saveanalyzer.exe --help`: it prints the usage and exits 0.
  Run it on the nine baseline saves into a temporary folder: its
  `report.stamp` and CSVs match `vic2_analyzer.py`'s. Do not commit
  `dist/` or `build/`.
- [ ] Run `all.py` and the unit tests.
- [ ] Commit: "The setup for Python worker processes goes: no
  freeze_support, no import-order rule, no hidden-import list".

### Task 4: Duplicates collapse

Make one commit per bullet. Each runs `all.py`, plus the mutations in what
it touched.

- **One share worker.** `__main__.Tools._upload` and `_publish` become
  `_share(self, verb, send)`. `send` is a callable that does the upload or
  the publish and returns the URL. The `TokenRefused` handling stays with
  the publish caller, which passes a `forget` callback.

  Test: `sharing.py` passes. It holds both flows against `mock_host.py` and
  a stub GitHub.
- **One "first existing folder" helper:**
  `settings.first_folder(candidates) -> str`. It is `report_tab`'s
  `_first_folder`. `keeper_tab.default_saves`/`default_out` and
  `report_tab`'s four `default_*` use it.
  - The keeper's fallbacks (`keeper.SAVES`, `keeper.EXPORT`, used when
    nothing exists) stay as its callers' `or` defaults.
  - Test: `test_package.test_first_folder_skips_what_is_not_there`.
- **The scanner's location is written once.**
  - `launch.BINARY` and `launch.built_scanner() -> str | None` (the crate's
    `target/release` copy) are what `build_exe.py` imports, instead of its
    own `scanner_binary()`.
  - `build_exe.py` imports `vic2tools.launch` only for those two names, so
    building needs no tkinter. Check that `launch` imports no tkinter.
- **`run.py`'s leftovers, now in `launch.py`:**
  - `REPORTED`, which nothing reads since the stamp moved to the scanner,
    goes. Check with a grep across `testkit/` first.
  - The `Run` docstring's history ("This was argparse's namespace…")
    becomes what `Run` is now.
  - `RunError`'s "`vic2_analyzer.main` turns it into…" stays true; check
    every name it cites.
- **The window's settle checks.** `report_tab.App.start`'s block runs
  `settle_game(None, where)` and then compares `realpath`s for "the mod
  folder of another install". It becomes two plain checks:
  `is_install(where)` and `_same_folder(where, game)`, as `mod_reader` names
  them. The sentences shown stay word for word; `window.py` holds them.

### Task 5: The mock host reads the worker's marks from the worker

**Files:** `testkit/mock_host.py`.

- `MAX_BYTES`, `HEAD_BYTES` and `WANTED_HEAD` are copies of `host/worker.js`'s
  constants. Read them out of `worker.js` at startup, as the
  Content-Security-Policy already is. `sharing.py` holds the mock to them.
- [ ] **Failing test.** Add `test_package.test_mock_host_takes_its_marks_from_the_worker`.
  It loads `mock_host` with a temporary copy of `worker.js` whose size cap
  is edited, and asserts `mock_host.MAX_BYTES` follows the edit. Expected:
  it fails, since the constant is hard-coded.
- [ ] Parse the three values out of `worker.js`, with one regex each, and
  fail loudly if one is not found. Run `sharing.py`.
- [ ] Commit: "The mock report host takes its size cap and marks from
  host/worker.js".

### Task 6: Rules both sides implement are held together

For each pair, read both sides first, then take the cheaper of these:
- one owner: the Python asks the scanner, or the Python copy goes;
- a check that runs both sides on the same inputs and fails on any
  difference.

Record the choice and why in the ledger.

- **`settle_game`:** `report_tab` (from `mod_reader.py`) and
  `scanner/src/front/mod.rs`.
  - The window asks before a run so a wrong folder is a dialog, not a log
    line. Expected choice: a check.
  - Add `testkit/pairs.py`, in `suite.py`, needing the scanner. It builds
    the fixture installs `frontcheck` builds:
    - a mod in an install;
    - a mod outside any install;
    - an install named as its own mod;
    - a mod in another install than `--game-root`;
    - no game root.
  - For each case it compares the Python verdict (the folder pair, or the
    `ValueError`) with a scanner run's (`settled` line, or the refusal
    sentence) on the same arguments. Equal means the same folder pair, or
    a Python sentence that is a prefix of the scanner's refusal.
- **`campaigns_in`:** `report_tab` (from `cross.py`) and
  `scanner/src/front/survey.rs`.
  - The window counts campaigns to decide whether a run is `--cross`.
  - In `pairs.py`, run both over `frontcheck.cross_world`'s tree, and over
    one with a name shared by two folders and one past the depth limit.
  - The scanner's side is the "Campaigns found under …:" block a verbose
    `--cross` run prints: one line per campaign, its name and its save
    count. Compare (name, number of saves), in order, with Python's
    `campaigns_in`.
- **The save-date sort.** Find the Python side first.
  - `keeper.folder_saves` sorts the keeper's own file names. The scanner's
    `front::in_date_order` sorts saves by the date in each. If no Python
    code sorts saves by in-game date for a run, there is no pair. Say so.

**Steps:**
- [ ] **Failing test.** Write `pairs.py` with the cases above. Run it
  against a deliberately broken Python copy (a sentence edited by one word
  in a scratch copy): it fails. Restore, and it passes.
- [ ] Add it to `suite.py` and `docrefs`'s list where needed. Add a
  mutation to `mutations.py`: `settle-game-sentence-drifts`, editing one
  word of the Python `settle_game`'s "not in a Victoria II install's mod
  folder" sentence, caught by `pairs.py`.
- [ ] Commit: "pairs.py holds the window's settle_game and campaigns_in to
  the scanner's".

### Task 7: Workstream 5 verification, and the job's last commit

- [ ] `wc -l vic2tools/*.py`: no file over 1,000 lines without its reason.
- [ ] Run the full mutation run (everything caught but
  `keeper-folder-windows-only`), then `all.py` with the baseline,
  `docrefs.py`, the unit tests, `cargo test`, and `prepushcheck.py`.
- [ ] Re-read `README.md`, `DEVELOPING.md` and `testkit/README.md` as a
  stranger. Every file and module named exists, and the "where things are"
  map names `vic2tools/` and its seven modules.
- [ ] **The job's last commit** ("Where these documents live"): take
  `docs/superpowers/` out of the tree. The design and the five plans
  describe a job, not the code, and git keeps them. `docrefs.py` must
  still pass: no document may cite them.
- [ ] Record the before and after line counts in the ledger.

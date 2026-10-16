# Workstream 1: A Fast, Honest Test Loop. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `testkit/` one short, honest loop:
- a mutation run of minutes rather than an hour, with verdicts that cannot
  mislead;
- one list of checks;
- shared basics instead of copies;
- a real-campaign baseline keyed to explicit saves.

**Architecture:** Only `testkit/` changes. No product code changes in this
workstream, so the baseline recorded at the end is the product as of
`30ed940`.

New modules:
- `kit.py`: paths, launching the analyzer, need-checks.
- `fixtures.py`: worlds to test against.
- `suite.py`: the one list of checks.
- `mutations.py`: the mutation table.
- `baseline.py`: record and compare.

Existing checks shrink onto these.

**Tech Stack:**
- Python 3 standard library only. Checks are scripts that exit 0, 77 or 1.
- The pure logic gets `unittest` files, run with `python -m unittest`.
- Rust scanner built with cargo: GNU toolchain, `~/.cargo/bin`, not on
  PATH.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-cleanup-design.md`
(workstream 1 and the "Verification bar").

## Global Constraints

- **Output.** No change to any product file: nothing outside `testkit/`,
  apart from `.gitignore` if needed. Every CSV, payload and stdout stays
  identical.
- **No new dependencies.** No third-party Python packages, no crates.
- **Exit codes.** Exit 0 means holds, 77 (`outcome.SKIPPED`) means could not
  all run here, anything else means fails. A missing tool or input skips
  (77); it never passes silently.
- **Windows first.**
  - Every check holds on Windows. Linux-only parts are named in the check's
    output.
  - Git Bash has no `bc`, `uptime` or `pgrep`.
  - Windows paths can exceed MAX_PATH under `scanner/target`.
- **Privacy.** Nothing committed names the maintainer or an absolute home
  path. Use `$VIC2_SAVES`, `$VIC2_MOD`, `$VIC2_BASELINE`, `~/...`.
- **Branching and history.**
  - Work on local branch `cleanup/test-loop` from `main` (`30ed940`).
  - No push.
  - Every commit passes `python testkit/all.py "$VIC2_SAVES" --mod "$VIC2_MOD"`.
- **Commit messages.** Follow the repo's style (a plain sentence saying what
  is now true, no `feat:` prefix), ending with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- **Machine paths.** The real saves and mod are in `speed/local.env`. For
  Windows Python, convert MSYS paths (`/c/...`) to `C:/...`.

## Review Focus

1. **Removing a worktree with a built `scanner/target` hits Windows' path
   length limit.** Earlier this session `git worktree remove` failed with
   "Filename too long". Expected: the mutation harness always cleans up its
   worktree, even on error or Ctrl-C. Test in Task 1.
2. **A baseline save replaced by a same-named file with different content.**
   For example, the keeper re-copies one. Expected: `compare` exits 77 and
   names the save and "content changed". It never reports identical. Test in
   Task 5.
3. **No `$VIC2_BASELINE` on this machine (any forker).** Expected: baseline
   cases skip with one line saying how to record one. The suite still holds.
   Test in Task 5.
4. **Checks that share a desktop or browser run in parallel.** This applies
   to `window.py` (Tk focus) and to Firefox profile collisions. Expected:
   checks marked `exclusive` never overlap anything. Test in Task 2.
5. **A mutation that hangs the scanner.** Expected: verdict TIMEOUT after
   the configured limit, and the next mutation starts from the committed
   binary. Test in Task 1.

---

### Task 1: Honest, fast mutation harness

**Files:**
- Create: `testkit/mutations.py` (the table)
- Create: `testkit/test_mutate.py`
- Modify: `testkit/mutate.py` (harness only; shrinks to roughly 300 lines)

**Interfaces:**
- Produces:
  - `mutations.Mutation(name: str, bug: str, catcher: str, needs: tuple[str, ...], patches: list[tuple[str, str, str]] | list[tuple[str, str, str, int]])`.
    A frozen dataclass. `needs` uses the vocabulary of `suite.Check.needs`
    (Task 2): `"saves"`, `"mod"`, `"one-save"`, `"baseline"`, or extra argv
    strings.
  - `mutations.MUTATIONS: list[Mutation]`, all 83, in today's order.
  - `mutate.Outcome(code: int | None, timed_out: bool, output: str)`, where
    `code` is None when timed out.
  - `mutate.Verdict`: an Enum with members `CAUGHT`, `BLIND`, `TIMEOUT`,
    `SKIPPED`, `NOAPPLY`, `NOBUILD`, `UNTESTED`.
  - `mutate.verdict(control: Outcome, mutated: Outcome) -> Verdict`.
  - `mutate.FAST_BUILD_ENV`:
    ```python
    {"CARGO_PROFILE_RELEASE_LTO": "false",
     "CARGO_PROFILE_RELEASE_CODEGEN_UNITS": "16",
     "CARGO_PROFILE_RELEASE_INCREMENTAL": "true"}
    ```

- [ ] **Step 1: Write the failing tests** in `testkit/test_mutate.py`:

```python
from mutate import Outcome, Verdict, verdict
OK, FAIL, SKIP = Outcome(0, False, ""), Outcome(1, False, ""), Outcome(77, False, "")
HUNG = Outcome(None, True, "")

class Verdicts(unittest.TestCase):
    def test_failure_is_caught(self):      self.assertIs(verdict(OK, FAIL), Verdict.CAUGHT)
    def test_pass_is_blind(self):          self.assertIs(verdict(OK, OK), Verdict.BLIND)
    def test_skip_is_not_caught(self):     self.assertIs(verdict(OK, SKIP), Verdict.SKIPPED)
    def test_timeout_is_not_blind(self):   self.assertIs(verdict(OK, HUNG), Verdict.TIMEOUT)
    def test_bad_control_untested(self):
        for control in (FAIL, SKIP, HUNG):
            self.assertIs(verdict(control, FAIL), Verdict.UNTESTED)

class Table(unittest.TestCase):
    def test_83_unique_names(self):
        names = [m.name for m in mutations.MUTATIONS]
        self.assertEqual(len(names), 83); self.assertEqual(len(set(names)), 83)
    def test_every_patch_applies_once_to_head(self):
        # read each patched file from the repo; `old` must occur exactly
        # `count` times (default 1), as patch() requires today
        ...
```

- [ ] **Step 2: Run them and see them fail**

Run: `cd testkit && python -m unittest test_mutate -v`

Expected: an ImportError for `Outcome`/`Verdict`/`mutations`.

- [ ] **Step 3: Move the 83 mutations into `mutations.py` as `Mutation(...)` rows**

- Each row's `patches` holds the exact `(path, old, new[, count])`
  arguments of today's `patch()` calls, in the same order.
- Names, bug text and catcher stay unchanged.
- Today's `args` become `needs`:
  - `"saves"` → `("saves",)`
  - `"saves-and-mod"` → `("saves", "mod")`
  - `"one-save"` → `("one-save",)`
  - a tuple of argv strings stays as the tuple.

Convert mechanically with a throwaway script, not by hand, then delete the
script. Then delete the stale section headers.

- [ ] **Step 4: Rework `mutate.py`**

- `check(script, argv, timeout) -> Outcome`. The default timeout is 120 s,
  set by `--timeout`.
- The controls run once per `(catcher, needs)` in a `ThreadPoolExecutor`
  (4 workers). A control timeout gives `Outcome(None, True, …)` and never
  raises.
- Builds run `cargo build --release` with `env = os.environ | FAST_BUILD_ENV`.
  Cargo is `~/.cargo/bin/cargo` when not on PATH. A build failure gives
  `NOBUILD`.
- **Own worktree.**
  - `--tree` goes.
  - The harness runs `git worktree add --detach <tmp> HEAD`, where `<tmp>`
    is `tempfile.mkdtemp(prefix="vm")` under `%TEMP%` (short path).
  - It copies the built scanner in, refusing with a clear message when
    there is none.
  - It cleans up in `finally`:
    1. `git worktree remove --force`;
    2. on failure, `shutil.rmtree` on the `\\?\`-prefixed path (Windows);
    3. `git worktree prune`.
  - It refuses only when HEAD's own scanner is missing. Uncommitted changes
    in the user's tree no longer matter: the worktree is HEAD.
- `put_back(pristine, binary)` stays. Drop its Linux `/proc` scan.
- **Exit status and report.** Exit 1 if any BLIND, NOAPPLY or NOBUILD.
  `--strict` also fails on TIMEOUT, SKIPPED and UNTESTED. The summary line
  counts every verdict. BLIND, TIMEOUT and SKIPPED each print the last 25
  lines of output.
- `--saves`, `--mod` and `--baseline` (default `$VIC2_BASELINE`) supply
  `needs`.
- `--list` prints name, catcher and needs.
- `--dry` applies and reverts each mutation without building, and reports
  NOAPPLY. This replaces the laptop-only `mutdry.py`.

- [ ] **Step 5: Run the unit tests**

Run: `cd testkit && python -m unittest test_mutate -v`

Expected: all PASS.

- [ ] **Step 6: Prove the Review Focus items 1 and 5 by hand, once**

- `python testkit/mutate.py --dry`: expect 83 applied, 0 NOAPPLY, and no
  worktree left in `git worktree list`.
- Run one Rust mutation, e.g. `python testkit/mutate.py ship-crew-dropped --saves "$S" --mod "$M"`.
  Expect a build of under 15 s after the first, the verdict, and the
  worktree gone.
- Press Ctrl-C during a build. Expect the worktree gone and nothing left in
  `git worktree list`.
- `--timeout 1` on `window-shows-refusal-as-traceback`: expect TIMEOUT, not
  BLIND, and the next mutation running normally.

- [ ] **Step 7: Run the full mutation run and record its time**

Run: `python testkit/mutate.py --saves "$S" --mod "$M"`, in the background.

Expected:
- CAUGHT for every mutation except the 21 `enginecheck.py` ones. Those are
  UNTESTED with the reason "control skipped" until Task 5.
- `keeper-folder-windows-only` is BLIND: it is Linux only, as today.
- Total wall time under 15 minutes. Note the time in the commit message.

- [ ] **Step 8: Commit**

Message: "The mutation run builds fast, keeps its own worktree, and says
TIMEOUT and SKIPPED instead of BLIND and caught."

---

### Task 2: One list of checks

**Files:**
- Create: `testkit/suite.py`
- Modify: `testkit/all.py` (rewritten onto `suite.py`)
- Modify: `testkit/README.md`: its hand-written command list is replaced by
  `python testkit/suite.py --list` and a short "what each kind of check
  needs".
- Modify or delete: the six unrun checks `compare_ui.py`, `export_ui.py`,
  `war_export_ui.py`, `military_ui.py`, `population_history_ui.py`,
  `map_rendering.py`.

**Interfaces:**
- Produces:
  - `suite.Check(script: str, title: str, needs: frozenset[str], records: bool = False, exclusive: bool = False, after_report: bool = False, extra: tuple[str, ...] = ())`.
  - `needs` is a subset of `{"scanner", "saves", "mod", "report", "firefox", "display", "rustc", "baseline"}`.
  - `suite.CHECKS: list[Check]`, in today's dependency order.
  - `suite.argv_for(check, *, saves, mod, report, baseline) -> list[str] | None`.
    Returns None when a need is unmet; the runner then reports skip with the
    unmet need named.
- Consumes: `mutate.py` (Task 1) uses `suite.argv_for` for a catcher's
  arguments in place of its own `argv_for`.

- [ ] **Step 1: Triage the six unrun UI checks**

Run each against a fresh report, built once:
`python vic2_analyzer.py "$S" --out <tmp> --rebuild -q --mod-path "$M"`.

For each one:
- passes → it joins `CHECKS`;
- fails only from page drift (a selector, `boots.WATCHER` text) → repair it,
  then it joins;
- fails on a real page bug → stop and report it to the maintainer, and
  leave it out with the reason recorded in `suite.py`;
- wholly covered by another check → delete it, naming that check in the
  commit.

Fix `if not result: return 1` on a missing Firefox to return 77.

- [ ] **Step 2: Write `suite.py`** with every check `all.py` runs today plus
  the triaged ones.
  - `window.py` and every Firefox check are `exclusive=True`.
  - Checks that read the shared report are `after_report=True`.
  - Records: `frontcheck`, `crossrows`, `saveshapes`, `mangled`, `modread`,
    `enginecheck`.
  - `suite.py --list` prints a table: title, script, needs.

- [ ] **Step 3: Rewrite `all.py` on top of `suite.py`**

- Each check gets its own `TMPDIR` under one holding folder. The shared
  report is built with its own `TMPDIR` too, so the real engine cache is
  never written.
- Non-exclusive checks run in a `ThreadPoolExecutor(max(2, os.cpu_count() // 4))`.
  Exclusive checks run alone, after the pool drains.
- `--update-expected` runs every `records=True` check with `--update`.
- A skip prints its unmet need, for example `skip (needs firefox)`.
- If the scanner is missing, print once:
  `build it: cargo build --release --manifest-path scanner/Cargo.toml`.
- `--quick` stays until Task 4 removes `smoke.py`.

- [ ] **Step 4: Prove Review Focus item 4 and the cache claim**

- Run `all.py` with `--saves` and `--mod`. Expect the same set of passes as
  `main` plus the triaged checks. Expect wall time below `main`'s; note
  both.
- While it runs, confirm no two exclusive checks overlap. `all.py -v`
  prints start and end stamps; check them.
- Compare the real cache folder's modified time before and after. Expect
  it unchanged.

- [ ] **Step 5: Commit**

Message: "One list of checks: all.py, --update-expected, mutate.py and the
README read it, and the checks that can run in parallel do."

---

### Task 3: Shared basics (`kit.py`, `fixtures.py`, `expected.hold_cases`)

**Files:**
- Create: `testkit/kit.py`
- Create: `testkit/fixtures.py`
- Modify: `testkit/expected.py` (add `hold_cases`)
- Modify: every check that launches the analyzer, builds a world, or
  inserts into `sys.path`. Today that is 41 `sys.path.insert` lines and
  about 15 launch copies.
- Modify: `testkit/matching.py`, which keeps only its own check.
- Modify: `testkit/mutations.py`. Retarget the one mutation that patches
  `testkit/matching.py` to wherever its line now lives.

**Interfaces:**
- Produces, in `kit.py`:
  - `ROOT: str` (the repo) and `SCANNER: str` (the built binary, with
    `.exe` on Windows).
  - `analyze(saves: str, out: str, *flags: str, game: str | None = None, mod: str | None = None, env: dict | None = None, timeout: int = 900) -> subprocess.CompletedProcess`.
    It runs `vic2_analyzer.py` with `capture_output=True`, `text=True`,
    `encoding="utf-8"` and `errors="replace"`.
  - `need_scanner()`, `need_firefox()`, `need_display()`, `need_rustc()`.
    Each prints one line and exits 77 when unmet.
  - `holding(prefix: str)`: a context manager yielding a temp folder whose
    `TMPDIR`/`TEMP`/`TMP` env (`kit.env_in(folder) -> dict`) points inside
    it.
- Produces, in `fixtures.py`:
  - `a_mod`, `a_game`, `a_mod_in_a_game`, `a_vanilla`, `a_save`, moved
    unchanged from `matching.py`.
  - The `TAGS`, `POPS` and `TECHS` constants.
  - `edge_save` (today's `edges.a_save`) and `vanilla()` (today's
    `edges.vanilla`, cached once per process).
- Produces, in `expected.py`:
  - `hold_cases(root: str, check: str, cases: list[tuple[str, Callable[[], dict]]], update: bool, ignore: tuple[str, ...] = ()) -> int`.
    It holds each case through `Book`, prints with `report`, calls
    `finish`, and returns 0, or 1 if anything differs or is missing.
    `ignore` is handed through `Book(…, ignore=)` to
    `differences(want, got, ignore=())`. It is empty everywhere except
    `baseline.compare` (Task 5).

- [ ] **Step 1: Move the world builders.** Move the code into
  `fixtures.py` verbatim. Point every importer of `matching.a_*` and
  `edges.a_save`/`vanilla` at it. `frontcheck.py` stops importing from
  `edges.py`.

- [ ] **Step 2: Add `kit.py`.** Replace each analyzer launch with
  `kit.analyze`, each scanner-path computation with `kit.SCANNER`, and each
  "needs a scanner" variant with `kit.need_scanner()`.
  - Replace each `sys.path.insert` of the `testkit` folder: running
    `python testkit/x.py` already puts it first.
  - The repo root goes on `sys.path` once, inside `kit.py`.
  - Checks that failed on a missing scanner now skip: `crossrows`,
    `saveshapes`, `mangled`, `caching`, `raster`, `mobrate`, `histories`,
    `staleness`.
  - Missing `rustc` in `staleness.py` and missing quickjs in `facts.py`
    skip with 77 instead of passing.

- [ ] **Step 3: Add `expected.hold_cases`** and move these onto it:
  - `saveshapes`
  - `crossrows`
  - `frontcheck`
  - `mangled`
  - `enginecheck`'s synthetic half

  `modread`'s JSONL record format stays as it is. It is a different shape;
  note it in its docstring.

- [ ] **Step 4: Verify**

- `grep -c "sys.path.insert" testkit/*.py`: expect a total of 1, in
  `kit.py`.
- `grep -l "vic2_analyzer.py" testkit/*.py`: expect only `kit.py`, plus
  `staleness.py` if it reads the file as a build input (it does). Name any
  other in the commit.
- `all.py` gives the same results as after Task 2.
- `mutate.py --dry` shows 0 NOAPPLY.
- Rerun the mutations whose catcher changed shape:
  `mutate.py <names> --saves … --mod …`. Expect all CAUGHT.

- [ ] **Step 5: Commit**

Message: "One home for what every check needs: kit.py launches and skips,
fixtures.py builds worlds, hold_cases holds records."

---

### Task 4: Remove the overlap

**Files:**
- Delete: `testkit/smoke.py`, `testkit/edges.py`
- Modify:
  - `testkit/frontcheck.py`: gains `edges.py`'s unique cases as recorded
    cases, and loses `mod_signature`/`_sign_folder`.
  - `testkit/facts.py`
  - `testkit/boots.py`
  - every `*_ui.py` that patches `boots.WATCHER`
  - `testkit/suite.py`
  - `testkit/all.py` (drop `--quick`)
  - `testkit/mutations.py`: retarget the three `edges.py` mutations to
    `frontcheck.py`.

**Interfaces:**
- Produces:
  - `boots.looked(html_path: str, probes: list[tuple[str, str]], seconds: int = 90) -> dict[str, object] | None`.
  - Each probe is `(name, javascript_function_source)`. The function
    returns a JSON-able verdict.
  - One Firefox session per call. None means Firefox is unavailable; the
    caller exits 77.

- [ ] **Step 1: Move `edges.py`'s unique cases into frontcheck's recorded table**

The cases:
- a first-month save;
- a war over before the first save;
- nations with no pops;
- out-of-order saves;
- a war with no battles;
- bad numbers.

Record them with `frontcheck.py --update`. Read the new records by eye:
each must show today's behaviour, with no traceback anywhere.

- [ ] **Step 2: Delete `edges.py`, retarget its mutations, and delete
  `smoke.py` and `--quick`.**
  - Run the three retargeted mutations. Expect CAUGHT.
  - If one is BLIND, add the case that catches it to frontcheck before
    deleting.

- [ ] **Step 3: Replace frontcheck's Python mod-signature twin with a
  property test**
  - Sign a fixture mod with `vic2scan mod-signature`.
  - Edit one covered file: the signature changes.
  - Touch one uncovered file: it stays the same.
  - Restore the edit: it is the same as at first.

  This test must survive workstream 4 replacing md5.

- [ ] **Step 4: `facts.py` reads the page itself**

- Drop `rebuild_facts`, `thin_facts`, the quickjs path and
  `the_template_loop`.
- Add a probe to `boots.looked` that returns `DATA.facts` after the page
  rebuilt it. Compare that with `nations_timeseries.csv` through the
  existing `against_the_table`.
- `made_up()` stays only if it still feeds a case; otherwise delete it.

- [ ] **Step 5: Probes instead of `str.replace` on `boots.WATCHER`**

Each `*_ui.py` passes its probe function to `boots.looked`. Where several
checks read the same report, `all.py` may later share a session; that is
not required now.

- [ ] **Step 6: Verify**

- `all.py` holds.
- Mutations with catchers `frontcheck.py`, `boots.py`, `war_legacy_ui.py`
  and `state_history_ui.py`: all CAUGHT.
- `grep -n "WATCHER.replace" testkit/*.py` returns nothing.

- [ ] **Step 7: Commit**

Message: "No check repeats another: edges' own cases live in frontcheck,
smoke and the Python twins are gone, browser checks pass probes."

---

### Task 5: The baseline

**Files:**
- Create: `testkit/baseline.py`
- Create: `testkit/baselinecheck.py` (a check, added to `suite.py`)
- Modify:
  - `testkit/enginecheck.py`: synthetic only. Its edge world gains what the
    retargeted mutations need. It returns 0, not 77, on success.
  - `testkit/modread.py`: the real-mod half goes; the baseline covers it.
  - `testkit/mutations.py`: the 21 `enginecheck` mutations.
  - `testkit/suite.py`

**Interfaces:**
- Produces, in `baseline.py`:
  - `record(campaign: str, mod: str, into: str, *, match: str = "*.v2", count: int = 8, nations: dict[str, str] | None = None) -> int`
  - `compare(campaign: str, mod: str, source: str, *, ignore: tuple[str, ...] = ()) -> int`

  It runs from the command line as:

  ```
  python testkit/baseline.py record  CAMPAIGN --mod MOD [--into DIR] [--match GLOB] [--count N] [--nations explain=NET,pool=ENG,inventions=FRA]
  python testkit/baseline.py compare CAMPAIGN --mod MOD [--from DIR] [--ignore KEY ...]
  ```

  - `DIR` defaults to `$VIC2_BASELINE`. When neither is given, print
    "no baseline: record one with `python testkit/baseline.py record …`"
    and exit 77.
  - `manifest.json` holds `{"saves": [[name, size, sha256], …], "mod": basename, "modifier": str|None, "nations": {...}, "commit": str, "runs": [names]}`.
  - The cases are today's `enginecheck.RUNS` (moved here), plus
    `"the mod as read"`: `vic2scan mod-export MOD` held as text. This moves
    `modread.py`'s real-mod half.
  - Records go through `expected.hold_cases` into `DIR`, which is used as
    the `root`.
- `nations` defaults: `explain=NET`, `pool=ENG`, `inventions=FRA` for each
  tag present in the last chosen save. Otherwise `record` refuses and names
  the `--nations` key that needs a tag.
- `--ignore payload.wars[].side_losses` is honoured by `differences()` as a
  dotted path with `[]` meaning every element. It is only for the
  workstream 3 commit that drops that key.

- [ ] **Step 1: Write `baselinecheck.py` first; it must fail**

Build a synthetic campaign with `fixtures` and `savefmt`: 6 saves, with
war, army and navy blocks. Then:

```
record(c, mod, d, count=4)                      -> 0, manifest has 4+1 saves
compare(c, mod, d)                              -> 0
add an unrelated save to c; compare             -> 0          # extra saves are fine
overwrite a manifest save with other bytes, same name; compare -> 77, output names it and "content changed"
delete a manifest save; compare                 -> 77, output names it and "missing"
edit one recorded file in d; compare            -> 1, output shows the difference
compare with no DIR and no $VIC2_BASELINE       -> 77, output says how to record
```

Run: `python testkit/baselinecheck.py`

Expected: FAIL, because `baseline` does not exist yet.

- [ ] **Step 2: Implement `baseline.py`**

- Choose the saves: evenly spaced indices over the sorted matches, plus the
  last.
- `compare` copies the manifest saves into a holding folder. It then
  reuses `a_world` (moved from `enginecheck.py`) to build the private game
  and mod copy, and runs each case as `enginecheck.run` does today.
- Run `baselinecheck.py`. Expected: PASS.

- [ ] **Step 3: Make `enginecheck.py` synthetic only, and retarget its 21
  mutations**

- Run each of the 21 with the catcher switched to `enginecheck.py`
  (synthetic only).
- For each BLIND one, extend `an_edge_world` with the smallest addition
  that exercises the code:
  - a market block with three goods met out of name order;
  - two battles on one date;
  - two unit kinds with equal regiments in one province;
  - ships of two types with crews;
  - two cultures of equal size;
  - a reform with a mob size;
  - a national value;
  - an event modifier with an impact;
  - techs in two branches;
  - an invention trigger;
  - a `--cross` pair.

  Re-record with `enginecheck.py --update` and read the new record.
- A mutation the synthetic world still cannot catch after a reasonable try
  gets `catcher="baseline.py"` with `needs=("saves", "mod", "baseline")`,
  and its row carries a comment saying why.
- `suite.argv_for` maps that catcher to
  `["compare", saves, "--mod", mod, "--from", baseline]`.
- `baselinecheck.py` is the suite's entry for the mechanism.
  `baseline.py compare` itself joins `suite.CHECKS` with
  `needs={"saves", "mod", "baseline"}`, so `all.py` runs the maintainer's
  comparison when `$VIC2_BASELINE` is set.
- Expected: every one CAUGHT. Note in the commit how many need the
  baseline.

- [ ] **Step 4: Record the maintainer's baseline from the product as of `30ed940`**

Product code is unchanged on this branch. Confirm that with
`git diff --stat main -- . ':!testkit' ':!docs'`, which must be empty.

```bash
python testkit/baseline.py record "$VIC2_SAVES" --mod "$VIC2_MOD" --match "NET*.v2" --into ~/vic2-baseline
```

- The NET campaign is the one the old record used. The folder also holds
  `CLM*`.
- `~/vic2-baseline` is outside the repo; the maintainer may later make it a
  private git repo.
- Add `VIC2_BASELINE=~/vic2-baseline` to the untracked local env file, and
  tell the maintainer the path.

Then run `compare` with the same arguments. Expected: 0.

- [ ] **Step 5: Verify**

- `all.py` holds, and `baselinecheck` runs in it.
- The full mutation run is all CAUGHT, apart from
  `keeper-folder-windows-only`. Expect 0 UNTESTED and 0 TIMEOUT. Note the
  wall time.
- `testkit/expected-real/` is no longer read by anything:
  `grep -rn "expected-real\|EXPECTED_REAL" testkit` shows only docs. It is
  deleted in workstream 2.

- [ ] **Step 6: Commit**

Message: "A baseline keyed to named saves replaces every-17th-save:
enginecheck is synthetic and catches its mutations on its own."

---

### Task 6: Close out workstream 1

**Files:**
- Modify: `testkit/README.md`. Rewrite it in the present tense:
  - what the suite is;
  - the one command;
  - `suite.py --list`;
  - the baseline;
  - the mutation run and its expected time.

  Remove the Python-era history: "until 1 Oct", "both ways", "the Python it
  replaced". The same goes for check docstrings that narrate Python parity:
  `enginecheck`, `mangled`, `crossrows`, `savefmt.selfcheck`, `fake_save`.
- Modify: `testkit/all.py`. Drop the unused `why` field.

- [ ] **Step 1: Rewrite the docs above.** Then grep for stale narration:
  `grep -rniE "python (path|twin|reader)|both ways|until 1 oct" testkit`.
  It must return nothing.
- [ ] **Step 2: Run the final verification**
  - `python -m unittest discover -s testkit -p "test_*.py"`
  - `all.py` with saves and mod
  - the full mutation run
  - `baseline.py compare`

  Each must show its expected result. Paste the summaries into the commit
  message.
- [ ] **Step 3: Commit.** Then stop and report to the maintainer:
  - the mutation-run time before and after;
  - `all.py` time before and after;
  - lines deleted from `testkit/`;
  - the baseline path.

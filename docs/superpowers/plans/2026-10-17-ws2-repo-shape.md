# Workstream 2: The Repo's Shape. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A top level a stranger reads in seconds, with nothing historical in the tree:
- `speed/`, the committed exe, the old real-campaign record, `HANDOFF.md`, `REVIEW.md` and the history in `INTERNALS.md` leave;
- the README is for players;
- one developer guide maps where everything lives;
- a check keeps the docs from naming files that do not exist.

**Architecture:** No product behaviour changes. Every byte the scanner and the
window produce stays the same. The privacy guard moves to `tools/`, and the
pipe check moves into the suite. The still-true parts of `INTERNALS.md` become
present-tense pages under `docs/how-it-works/`. A new check, `docrefs.py`, holds
every repo path named in the docs to existing.

**Tech Stack:** Python 3 standard library, Git Bash, the existing test kit (`testkit/kit.py`, `suite.py`).

**Spec:** `docs/superpowers/specs/2026-10-16-repo-cleanup-design.md` (workstream 2, the Verification bar, Decisions).

## Global Constraints

- **No product changes.**
  - No change to `scanner/`, `template.py` or the runtime Python modules. `build_exe.py` changes only as Task 4 says.
  - After every commit, `python testkit/all.py "$S" --mod "$M" --baseline ~/vic2-baseline` holds 35+ checks with none failing.
- **Privacy.**
  - Nothing committed names the maintainer or an absolute home path.
  - `tools/prepush.sh` must print `clean` before any push. This plan pushes nothing.
- **Releases.**
  - GitHub Releases already carry `vic2saveanalyzer.zip` (v1.0). This plan creates no release and uploads nothing.
- **Machine.**
  - Windows 11, Git Bash (no `bc`, `uptime` or `pgrep`).
  - Run one heavy command at a time: this PC hard-resets under heavy parallel load.
- **Branch.** Work on local branch `cleanup/repo-shape` from `main` (`19f8ac1`).
- **Commits.**
  - Each is a plain sentence of what is now true.
  - Each ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Stop points.** Removing anything outside the repository needs the maintainer's yes first: the ~30 old worktrees under `~/vic2speed/rw/`, and installing a git hook.

## Review Focus

1. **The privacy guard with nothing to guard against.** If `tools/prepush.sh` runs with no `tools/local.env` and no `VIC2_PRIVATE`, it must refuse (exit 2) and never print `clean`. Test in Task 1.
2. **Untracking the exe must not delete it.** `git rm --cached` leaves the maintainer's local `dist/vic2saveanalyzer.exe` in place. Test in Task 4.
3. **The committed icon is the one releases had.** `vic2.ico` must be byte-identical to what `build_exe.write_icon()` draws today. Test in Task 4.
4. **A doc names a file that a later workstream moves or deletes.** `docrefs.py` fails, and names the doc and the path. Test in Task 5.
5. **The pipe check on a machine with no way to list processes.** It skips (77). It never says "no leftovers". Test in Task 2.

---

### Task 1: The privacy guard lives in `tools/`

**Files:**
- Create: `tools/prepush.sh`, which is `speed/prepush.sh` with its settings read from `tools/local.env`
- Create: `tools/README.md`: what the guard is for, `tools/local.env`'s three variables, and how to run it before a push
- Create: `testkit/prepushcheck.py`, added to `suite.py` with `needs={"bash"}`. "bash" is a new need, found by `shutil.which("bash")`, with a `HOW` hint.
- Modify: `.gitignore`. `speed/local.env` becomes `tools/local.env`.
- Local only: move the maintainer's `speed/local.env` to `tools/local.env` (untracked). Keep its four variables and add `VIC2_BASELINE`.

**Interfaces:**
- Produces: `tools/prepush.sh`, which exits 0 and prints `clean`; exits 1 and prints each match; or exits 2 when it cannot look. `VIC2_PRIVATE` comes from the environment, or else from `tools/local.env`.

- [ ] **Step 1: Write `testkit/prepushcheck.py`.** It makes a throwaway git repo in `kit.holding()`, copies `tools/prepush.sh` in, and asserts:
  - `VIC2_PRIVATE=zzsecretzz` with a committed file containing `zzsecretzz` → exit 1, and the output names the file;
  - the same with the file clean → exit 0, output `clean`;
  - no `VIC2_PRIVATE` and no `local.env` → exit 2, and `clean` is not in the output.

  Before step 3 it has nothing to run: `python testkit/prepushcheck.py` must FAIL.
- [ ] **Step 2: Run it.** Expected: FAIL (no `tools/prepush.sh`).
- [ ] **Step 3: Create `tools/prepush.sh`** from `speed/prepush.sh`, changing only where `local.env` is looked for. In the throwaway repo there is no `origin/main`, so the "unpushed commits" part compares against the empty tree when `origin/main` is missing.
- [ ] **Step 4: Run the check.** Expected: PASS. Run `bash tools/prepush.sh` on the real repo. Expected: `clean`.
- [ ] **Step 5: Commit.** "The privacy guard is tools/prepush.sh, checked by the suite".

### Task 2: The pipe and leftover check is part of the suite

**Files:**
- Modify: `testkit/engine_runtime.py`. Add a `Pipes` test case on a made-up campaign, using `fixtures.a_vanilla` and `fixtures.edge_save`.

**Interfaces:**
- Consumes: `kit.analyze` (for the argument shape), `kit.SCANNER`, `vic2_analyzer.analyze` (as `pipecheck.sh` called it).

- [ ] **Step 1: Write three tests:**
  - `test_a_reader_that_goes_away_early`: the analyzer's stdout is read for three lines, then the pipe is closed. The process must exit, within 60 s, with no `Traceback` on stderr.
  - `test_a_hosted_run_leaks_no_protocol_lines`: `vic2_analyzer.analyze(run)` with stdout captured. No captured line starts with `@`.
  - `test_no_scanner_is_left_running`: after both, `tasklist` (Windows) or `pgrep -x vic2scan` lists no scanner started by this test. Tell them apart by the tests' own temp folder in the command line. With neither tool, `self.skipTest(...)`, which makes `engine_runtime.py` exit 77 for that part.
- [ ] **Step 2: Run them.** They should pass on the current product, since `pipecheck.sh` passed. Prove each can fail before trusting it:
  - for the first, temporarily make the reader wait without closing the pipe, and confirm the 60 s guard trips;
  - for the third, start a `vic2scan` that sleeps (`vic2scan bench-engine` on nothing, or a copied binary run with a long-running mode) and confirm it is listed.

  Note what was done in the commit.
- [ ] **Step 3: Commit.** "The checks run a report through a pipe that closes early, and look for a scanner left running".

### Task 3: `speed/` and the old real record leave

**Files:**
- Delete: `speed/` (every tracked file) and `testkit/expected-real/`.
- Modify:
  - `.gitattributes`: drop the `testkit/expected-real/**` and `speed/runs/**` lines.
  - `.gitignore`: drop the `speed/` lines.

- [ ] **Step 1:** `git rm -r -q speed testkit/expected-real`, and edit the two attribute files.
- [ ] **Step 2: Check what still names them.** `git grep -n -e "speed/" -e "expected-real" -- ':!docs/superpowers'` lists only `INTERNALS.md`, `HANDOFF.md` and `REVIEW.md`, which Task 5 removes or rewrites. Anything else gets fixed now.
- [ ] **Step 3: Run the suite.** `all.py` with saves, mod and baseline. Expected: all hold.
- [ ] **Step 4: Commit.** "The speed job's notes, tools and reference run, and the old real-campaign record, leave the tree". Say in the message that git history keeps them, and name the commit before this one.

### Task 4: The exe ships through Releases only, and the icon is a file

**Files:**
- Modify: `.gitignore`. `dist/` is ignored whole: drop the `!dist/vic2saveanalyzer.exe` negation, and drop `vic2.ico` from the ignore list.
- Untrack: `dist/vic2saveanalyzer.exe` (`git rm --cached`).
- Add: `vic2.ico`.
- Modify: `build_exe.py`.
  - Delete `write_icon` and its drawing helpers.
  - Point `--icon` at the committed `vic2.ico`.
  - The docstring says it packs `dist/vic2saveanalyzer.exe` for a release, to be zipped and attached to a GitHub Release.
  - The hidden-import list stays; workstream 5 handles it.
- Modify: `testkit/packing.py`, only if it reads `write_icon` or `vic2.ico`.

- [ ] **Step 1: Prove the icon is the same.** Before deleting the drawing code, run `write_icon` with `ICON` pointed at a temp file. Then `cmp` that file with the `vic2.ico` on disk. Expected: identical. If not, commit the freshly drawn one and say so.
- [ ] **Step 2: Make the changes above.** `git status` must show `dist/vic2saveanalyzer.exe` as deleted from the index only. `ls dist/vic2saveanalyzer.exe` must still find it (Review Focus 2).
- [ ] **Step 3: Build an exe to prove the build still works.** Close any running instance first; if one is running, ask the maintainer to close it.
  - Run `python build_exe.py`. Expected: exit 0, and `dist/vic2saveanalyzer.exe` is written.
  - Run `dist/vic2saveanalyzer.exe --help`. Its output from "positional arguments" down must match `python vic2_analyzer.py --help`'s.
  - Then `git status` shows nothing under `dist/`.
- [ ] **Step 4: Commit.** "The executable is built for a release and attached to it, not committed; the icon is a file".

### Task 5: Docs a stranger, or their assistant, can trust

**Files:**
- Create: `testkit/docrefs.py`, added to `suite.py` with no needs.
- Create: `DEVELOPING.md`.
- Create: `docs/how-it-works/` pages, moved from `INTERNALS.md`.
- Create: `scanner/README.md`.
- Modify: `README.md`, which becomes player-facing.
- Delete: `INTERNALS.md`, `HANDOFF.md`, `REVIEW.md`.

**Interfaces:**
- Produces: `docrefs.py` exits 1 and lists `doc:line path` for every backticked or linked repo path that does not exist. A path counts when it ends in one of `.py .rs .md .js .css .html .toml .sh .json .lua` or ends in `/`, and its first part is a top-level folder or file of the repo. It reads `README.md`, `DEVELOPING.md`, `docs/how-it-works/*.md`, and every `README.md` below the root. It does not read `docs/superpowers/`.

- [ ] **Step 1: Write `docrefs.py`** and run it on today's tree. Expected: FAIL, listing at least the dead names in `HANDOFF.md`'s section that sends readers to files that don't exist (`stamp.py`, `readsave.py`, …), since `HANDOFF.md` is read while it exists. This is the red run.
- [ ] **Step 2: Write `DEVELOPING.md`.** Present tense, about 150–250 lines:
  - **Where things live.** One line per top-level folder and per major file: the Python modules, `template.py`, `scanner/` (pointing to `scanner/README.md`), `testkit/`, `host/`, `tools/`, `docs/how-it-works/`, `build_exe.py`.
  - **How a run flows.** The window or the command line → `vic2_analyzer.py` → `vic2scan analyze` → the front end (`scanner/src/front/`) → the engine (`scanner/src/engine/`) → the page.
  - **Checking a change.** `all.py`, `suite.py --list`, what each kind of check needs, the baseline and when to record it, the mutation run and its time, and the rule that a fix comes with a check and a mutation.
  - **Building a release.** `cargo build --release`, `python build_exe.py`, then zip `dist/vic2saveanalyzer.exe` and attach it to a GitHub Release.
  - **Privacy.** The separate identity, `tools/prepush.sh` before every push, and no names or home paths in anything committed.
  - It takes in what stays true from README's "The Rust scanner", "Building the executable" and "Files" sections. Fix that "Files" table's stale entries: `template.py` is not Python run at runtime, and so on.
- [ ] **Step 3: Write `scanner/README.md`** (about 30–60 lines). What `src/`, `src/front/` and `src/engine/` own, file by file in one line each. The crate has no dependencies, on purpose. How to build it, and where the binary lands.
- [ ] **Step 4: Move the still-true parts of `INTERNALS.md` into `docs/how-it-works/`.** These are the sections outside "Speed" (lines 1–504 and 2252–3029 today):
  - `map.md`: the deployment map, occupation, playing back;
  - `nations.md`: one nation becoming another, great powers, states, charts, hulls, names, mod layers, pop types, players, layout;
  - `wars.md`;
  - `prices-and-supply.md`;
  - `fleet-power.md`;
  - `stopping.md`;
  - `mobilisation.md`;
  - `military-tech.md`.

  For each page:
  - keep the explanation, and every number that describes the game;
  - drop dates, commit hashes and "was/used to" narration;
  - check every named file, function and flag still exists (`git grep`), and rename or drop the ones that don't;
  - add one line at the top saying what the page explains.

  "Speed" (lines 505–2251) and "What was removed" leave with `INTERNALS.md`, kept by git history.
- [ ] **Step 5: Make `README.md` player-facing.**
  - Getting started says to download `vic2saveanalyzer.zip` from https://github.com/vic2tools/vic2saveanalyzer/releases/latest, unzip it, and double-click the exe.
  - The sections "The Rust scanner", "Building the executable" and "Files" are replaced by one line pointing to `DEVELOPING.md`.
  - Everything about using the tool stays: the tabs, the terminal, multiplayer, accuracy, licence. Read it once for stale claims (the Python pipeline, `--quick`, the speed job) and fix them.
- [ ] **Step 6: Delete `INTERNALS.md`, `HANDOFF.md`, `REVIEW.md`.** Run `docrefs.py`. Expected: PASS. Run `all.py` (docrefs is in it). Expected: all hold.
- [ ] **Step 7: Commit.** "README is for players, DEVELOPING.md maps the code, docs/how-it-works explains it, and a check keeps the docs to files that exist". Name the commit before this one, where the old documents can be read.

### Task 6: Local housekeeping, and the maintainer's go-ahead

**Files:** none tracked.

- [ ] **Step 1: Restore LF line endings in the working copy.** Five working files are CRLF while git stores LF: `scanner/src/engine/{cache,explain,mod,report,rules}.rs`. For each one with no diff (`git diff --quiet -- FILE`), delete it and run `git checkout -- FILE`. Then rebuild the scanner, since the build id hashes source bytes. Run `git ls-files --eol | awk '$1=="i/lf" && $2=="w/crlf"'`. Expected: empty.
- [ ] **Step 2: Update the assistant's notes.**
  - `rebuild-exe-before-committing` becomes "the exe is built for releases only".
  - `windows-rust-setup` drops `speed/minibench.py` and names `tools/local.env`.
  - `vic2-baseline` names `tools/local.env`.
- [ ] **Step 3: Run the final verification.** One at a time:
  - the unit tests;
  - `all.py` with saves, mod and baseline;
  - `mutate.py --dry`;
  - `bash tools/prepush.sh`.

  Each shows its expected result. No full mutation run is needed: no product code and no patched text changed, and `--dry` proves every patch still applies.
- [ ] **Step 4: Stop and ask the maintainer.**
  - **Worktrees.** List `git worktree list` (about 30 under `~/vic2speed/rw/`, each a detached old commit) and their total size. Ask whether to remove them with `git worktree remove --force` and `git worktree prune`.
  - **Git hook.** Ask whether to install `tools/prepush.sh` as a pre-push hook (`git config core.hooksPath tools/hooks` with a one-line `tools/hooks/pre-push`). That is a standing configuration change, so do it only on their yes.

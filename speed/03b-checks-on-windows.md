# Task 03b: make the checks hold on Windows

Read `CONTEXT.md` and `STATUS.md` first.

The program ships on Windows, and on Windows nine of `testkit/all.py`'s 28
checks fail and two skip, every one for a reason in the check and none in
the program (STATUS.md, 2026-10-03). Until they hold, every check run on
the Windows PC needs reading line by line to tell a real difference from a
slash, and the mutation harness can judge only 27 of its 57 mutations
there. This task makes `all.py` a plain pass or fail on Windows, as it is
on Linux.

**The rule for the whole task: change the checks, never what the program
prints or writes, and never the recorded answers.** A Windows answer must
be held to the *same* record a Linux answer is: normalise what a run gives
before comparing (the way `modread.portable()` already does for the real
mod), so the record keeps `HOLDING/game`. No `--update-expected`; if a
record seems to need changing, stop and ask the maintainer. Every change
must leave Linux exactly as it is -- it cannot be run here, so keep each
change small enough to be sure of by reading, and say in STATUS.md what
the laptop must confirm.

## The Windows PC

Rust (GNU toolchain) in `~/.cargo/bin`, not on PATH; gdb from MSYS2;
Victoria 2 in Steam with *Modus Omnino Demens 1.6* in its `mod/`; the
campaign in `~/Documents/Paradox Interactive/Victoria II/Modus Omnino
Demens 1.6/save games`. `speed/local.env` (not committed) has
`VIC2_SAVES`, `VIC2_MOD`, `VIC2_SPEED_WORK` and a whole-word
`VIC2_PRIVATE`. Run everything with `TMPDIR` set to a scratch folder.
Firefox is installed at `C:\Program Files\Mozilla Firefox\firefox.exe`,
not on PATH. Windows PowerShell 5.1 and Git Bash are both there.

`all.py` prints only the last 3,000 characters of a failing check's output
(`all.py`, `[-3000:]`), so run a failing check on its own to see all of it.

## What fails, and why (measured 2026-10-03, `a80ec11`)

The baseline: `python testkit/all.py SAVES --mod MOD` gives 19 of 28.

1. **Folders printed with `\`** -- by far the most. A run prints a path
   the check built (`HOLDING\game`, `HOLDING\refused\0a_zip.v2`,
   `OUT\pops_by_type.csv`); the check swaps its folder for `HOLDING` or
   `OUT` (`expected.answer`'s `places`, `modread.answer_of`) but the
   separators after it stay Windows ones, and the record has `/`. Every
   paired difference in these checks was only that:
   - `saveshapes.py`, "the shapes a save can take" (29 lines);
   - `mangled.py`, "damaged saves" (6);
   - `frontcheck.py`, "the run's front end" (5);
   - `crossrows.py`, "the cross block against the report" (30);
   - `enginecheck.py`, "the report engine against its recorded answers"
     (54 lines across 9 of 27 cases, real campaign included; the other 17
     identical);
   - `modread.py`, "the mod reader": the synthetic worlds' JSON answers
     (`"HOLDING\\pristine\\game"`); the real mod already passes, through
     `portable()`.

   The likely fix is one place: where the stand-in is put in
   (`expected.answer`'s `clean`, and `modread.answer_of`), turn the
   separators of the *rest of that path* into `/` -- only those, never
   every backslash in the output, since a real message may hold one.
   `portable()` (`modread.py`) does this for JSON already; reuse its idea.
   Check whether paths printed *without* a stand-in (the save names a
   refusal quotes, say) also differ.

2. **`\r\n` where `\n` is expected** -- `engine_runtime.py`, "the engine
   process and test fixtures": `test_large_pipes_are_drained_and_progress_told`
   and `test_unhosted_lines_are_passed_on_as_they_are` get `'said\r\n'`
   and `'@progress 1 2\r\n'`. Find which side adds the `\r`: a text-mode
   stream on Windows (the relay in `vic2_analyzer.py`, or the test's own
   capture). **If it is the program's relay, that is a program bug the
   window's users would see** -- stop and describe it to the maintainer
   before fixing; it changes what the program does.

3. **Symbolic links need administrator rights on Windows** --
   `smoke.py`, "every way of running it", stops at its first step:
   `os.symlink` to the real saves raises WinError 1314. CONTEXT.md already
   says never to build a test world out of links to real files: copy
   instead (only the few saves it needs), or link where the system allows
   and copy where it does not.

4. **Firefox not on PATH** -- `boots.py` ("the report in a browser") and
   `state_history_ui.py` ("state history decoded in the browser") skip:
   both ask `shutil.which("firefox")`. Look in the standard Windows
   places too (`%ProgramFiles%`, `%ProgramFiles(x86)%`, `%LOCALAPPDATA%`
   `\Mozilla Firefox\firefox.exe`) and fix whatever then fails in a
   browser run on Windows. These are the checks task 04 relies on.

5. **Already fixed:** `enginefmt.py` hung on Windows (input encoded in the
   code page; now UTF-8, `a80ec11`).

Also, outside `all.py`: `speed/cmpruns.py` normalises only the Unix
spelling of the game and out folders, so on Windows it calls stdout
different when it is not. Make it normalise the Windows spelling too
(drive letters, `\`), and check it against `speed/runs/11e1f21` with a
fresh run of the campaign (`~/vic2speed/opt/runs/`).

## Verify

- `python testkit/all.py SAVES --mod MOD` on Windows: **28 of 28**, or
  every exception explained in STATUS.md. Run once at the start too, as
  the baseline.
- Each fix shown to be a fix, not a mask: put the difference it hides
  back by hand once (a wrong number in a table, a real path change) and
  see the check still fail, naming it.
- The mutation harness on a clean worktree (`testkit/mutate.py --tree
  WORKTREE --saves SAVES`; it needs the worktree's `vic2scan.exe` copied
  in): the 29 UNTESTED should now be judged. Expected: 56 caught, plus
  `keeper-folder-windows-only` BLIND by its nature (it can only fail off
  Windows). Any other BLIND is a check that does not do its job.
- The reference run: the campaign through `vic2_analyzer.py` against
  `speed/runs/11e1f21` with the fixed `cmpruns.py`: identical.
- Linux: nothing can be run here. List in STATUS.md every check touched
  and what the laptop must run (`all.py` with the campaign, 28/28, and
  the mutation run, 57/57) before the next push.

Commit in steps (one per kind of fix is fine), add INTERNALS.md notes
under the testkit's own section if there is one, a bundle, and a
`STATUS.md` entry. Don't push unless the maintainer asks. Then task 04.

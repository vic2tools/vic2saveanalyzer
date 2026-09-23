# Next session: the review's fixes are in; here is what is left

Paste this whole file as the first message of a new session.

---

You are picking up `~/vic2saveanalyzer`, a Victoria 2 save-file
analyzer. It has a GitHub remote, `origin` (github.com/vic2tools/vic2saveanalyzer),
but its `main` is still `a78b1c3` from 2 September: **none of the ninety-odd
commits since has been pushed**, and nothing should be without the maintainer saying
so. The code is as of `af1de71`; the two commits after it only write
`REVIEW.md` §31 and this file. The working tree is clean, all 24 checks
pass, and the mutation harness catches 45 of 45. Backup bundles sit in `~`,
one per session: `vic2saveanalyzer-backup.bundle` (`403dcc4`),
`vic2saveanalyzer-backup-f09e2f4.bundle`,
`vic2saveanalyzer-backup-f1a4d82.bundle`, and the newest,
`vic2saveanalyzer-backup-af1de71.bundle`, which also holds the two commits
after it.

The maintainer develops on Fedora and ships on Windows as `dist/vic2saveanalyzer.exe`,
so anything platform-specific gets written on the machine that cannot test it.
He is not a software engineer: explain in plain terms, and prefer doing the
work over asking design questions. He hands work over for long stretches and
wants verified work, not check-ins. Ask him only what is genuinely his, such
as a fix that would change a number the program shows.

**`dist/vic2saveanalyzer.exe` is out of date with the source** and has to be
rebuilt on Windows (`python build_exe.py`). Do not try to build it here. **It
also carries no Rust scanner** -- the 20 September build's archive has no
`vic2scan` in it -- so Windows users read every save in Python, about four
times slower. `build_exe.py` bundles the scanner only if
`scanner/target/release/vic2scan.exe` exists, so on the Windows machine run
`cargo build --release --manifest-path scanner/Cargo.toml` first. There is no
cargo on this machine; the Linux binary in `scanner/target/release/` cannot be
rebuilt here either.

Read `REVIEW.md` before changing anything it covers. §12-§31 are the
thermonuclear review of `26f3680` and what was done about it. Do not re-open
what it marks decided. `INTERNALS.md` is the project's decision record, dense
with "we tried X, it was wrong, here is the measurement".

## The contract. Nothing is done without all four.

```bash
cd ~/vic2saveanalyzer
S="/path/to/saves/1870s"                  # 103 saves, 3.3 GB
M="/path/to/mod/Modus Omnino Demens 1.6"

# Clean worktrees of the previous commit and of this one, WITH the scanner.
for t in base:HEAD~1 head:HEAD; do
  git worktree add --detach /tmp/${t%%:*} ${t#*:}
  mkdir -p /tmp/${t%%:*}/scanner/target/release
  cp scanner/target/release/vic2scan /tmp/${t%%:*}/scanner/target/release/
done

# 1. the nine outputs, byte-identical -- --no-cache ON BOTH SIDES
for t in base head; do (cd /tmp/$t && python3 vic2_analyzer.py "$S" \
    --out /tmp/xx/$t --mod-path "$M" --rebuild --no-cache -q); done
#    compare every file with cmp; report.stamp is EXPECTED to differ.

# 2. the four diagnostics, byte-identical, the same way (-q, --no-cache,
#    capture stdout): --explain-mob-pool NET / --explain-mob NET /
#    --inventions NET / --check-inventions

# 3. all the checks, from the repository itself
python3 testkit/all.py "$S" --mod "$M"

# 4. the mutation harness, against a COMMITTED worktree: every mutation
#    caught -- none BLIND, none NOAPPLY, none UNTESTED -- and exit 0
git worktree add --detach /tmp/mut HEAD
mkdir -p /tmp/mut/scanner/target/release
cp scanner/target/release/vic2scan /tmp/mut/scanner/target/release/
python3 testkit/mutate.py --tree /tmp/mut --saves "$S"
```

All four take about six minutes; step 3 is two and a half of them, step 4
about three. Commit first, then run the contract comparing `HEAD~1` with
`HEAD`, and amend if it fails; every commit has to pass on its own. Run step
1 on the same commit twice once, and see it flag a byte you changed by hand,
before trusting it.

**Every bug fix brings a check that fails without it, and a mutation in
`testkit/mutate.py` that proves it** -- run by hand once, with the failure
message read. `mutate.py` counts any failure as caught, so reading the message
is the only thing that tells a right failure from a wrong one. This session it
caught a new check of its own passing for the wrong reason (`REVIEW.md` §31).
`mutate.py` hands a check `"saves"` (the folder), `"one-save"` (the first save
and a round count of one), or any fixed arguments.

## Traps that have cost real time

1. **Never edit the tree while `testkit/all.py` is running.** It reads files
   at exec time; a mid-run edit once produced an entirely fictitious failure.
2. **A fresh `git worktree` has no Rust scanner.** `scanner/target/` is
   untracked, so without the `cp` above everything is read in Python -- four
   times slower, and `parity.py` compares Python with Python.
3. **This is a desktop.** Don't wait for idle; interleave before and after
   runs in one loop, three to nine rounds. The no-change run is about 82 ms
   and jumps to 120 on a busy moment; one round proves nothing.
4. **Keep `TMPDIR` short or unset.** Python 3.14 starts workers through a
   forkserver whose socket path lives there and cannot exceed 108 bytes.
   `TMPDIR=/tmp/nc` works for a private cache.
5. **`mutate.py` refuses a worktree with uncommitted changes.** Commit first.
6. **`caching.py` and `modcache.py` are `unittest` scripts and take no
   arguments.**
7. **A check that fails is not evidence either.** Read why it failed.
8. **`/tmp` is memory, and the machine reboots.** A reboot mid-session took
   every worktree, every test folder, the real cache and the notes kept in
   the session scratchpad. Keep anything you cannot rebuild outside `/tmp`
   (this session used `~/.cache/vic2review/`, since removed), and run
   `git worktree prune` after one.
9. **Reviewers started in parallel all stop at the same usage limit.** Five
   were started at once and all five stopped before reporting anything. They
   also wrote into the same scratchpad as the session that started them, and
   one overwrote a file there with its own of the same name. Start fewer,
   and give each a folder of its own.
10. **A script piped in on stdin cannot start workers.** The forkserver
    re-imports `__main__` by path, and `<stdin>` has none, so each worker
    prints a `FileNotFoundError` and the analyzer reads one save at a time.
    That is the harness, not the program; write the script to a file.

## What was done this session

A review of every file, `REVIEW.md` §12-§30, reproduced finding by finding,
then eighteen commits. §31 has the table: each commit, what its check says
with the fix taken out. In plain terms:

- A save cut short is refused instead of read as 34 nations with no army.
- `--cross` (the window's path for a folder of campaigns) no longer serves
  the old comparison when a smaller campaign gains a save, and no longer
  reads every campaign to find that nothing changed.
- A table open in Excel no longer ends the run in a stack trace, and a run
  that dies, or `--no-html`, no longer leaves a stamp that serves the wrong
  report later.
- `war = yes` is judged on who the war lists now, and `--explain-mob` sees
  the wars.
- Every table is written every run; one save per in-game date is read,
  with a note naming the rest.
- A dead worker drops the run to one save at a time instead of ending it.
- Pressing Analyze no longer erases the GitHub token and the report host,
  and a token GitHub refuses is forgotten so the next press asks again.
- A mod file named in other case replaces the game's, as on Windows; the
  scanner opens no console window on Windows; names from saves and mods
  cannot become script in the report; the GitHub token does not follow a
  redirect off GitHub, and publishing failures come out as sentences.
- The keeper's "Open the folder" works off Windows; the mod cache key is
  derived rather than listed; two pieces of dead code are gone.
- **Candidate 3 is done.** `vic2_analyzer.Run` declares every setting and
  whether it changes the report; the stamp hashes exactly those, and
  `staleness.py` holds the declaration to account. The window builds a `Run`
  and calls `vic2_analyzer.analyze(run, cancel=, progress=, ready=)` instead
  of rewriting `sys.argv`. `main(run=None)` still reads the command line when
  given nothing, so every check that drives it through `sys.argv` still does.

Speed: the no-change run 82 → 83 ms (noise), cold 5.75 → 5.71 s.

## What is left

In rough order of value.

1. **Two things the maintainer decided to leave**, `REVIEW.md` §30: the Wars tab's
   belligerent lists (§13 -- the missing seven were a hand merge by the game's
   host), and the mobilisation cap's float arithmetic (§18). Don't redo either
   without asking him.
2. **The leads in `REVIEW.md` §27**, none reproduced: a mod's `.mod`
   `replace_path` is never read; `brigades_from_clusters` compares floats
   against the regiment cost (could it be the one measured miss, Japan 1908,
   467 against 468?); `cross._MOD_FACTS` is never cleared in a long-running
   window; `host/worker.js` deletes a report on a GET; GitHub Pages and
   `.data.gz`. The first two need a second mod or a base game install, which
   this machine does not have -- worth asking the maintainer for one, as the previous
   handoff suggested for `--cross` too (an IGoR or GFM campaign).
3. **Small and cosmetic, all still true**: `walk_campaign` reads
   `v2parse.POP_TYPES` for its columns instead of being handed the reading's
   pop types; `REVIEW.md` §5 (`keep_pools` and `in_workers` held together by
   line order) and §7 (the fold table's redundant field column); "world"
   names two different things in the analyzer; `testkit/parity.py` builds one
   synthetic save when given no folder and could build the awkward shapes too.
4. **Looked at and declined**, with the reason in §31: folding the three
   "what is a folder of saves" walkers into one.

## Leave these alone, with reasons (all recorded in the repo)

- `template.py` -- one big string, deliberately; splitting it means
  PyInstaller data files and `sys._MEIPASS` on a platform nobody here can test.
- The report stamp hashing every `.py` -- deliberately over-eager. Do not turn
  it into a list of filenames; that list was wrong within a day.
- `Mod.__getstate__`/`__setstate__` -- `REVIEW.md` §6, decided.
- The seventeen fold rules in `nation.py` -- `REVIEW.md` §7, decided.
- `readfolder.py` must not import the finishing, or anything else that only
  uses a save: its parse cache key is everything it reaches, and
  `testkit/caching.py` will fail if that grows. `mod_reader.py`'s key is
  derived the same way now, and `testkit/modcache.py` holds it.

# Next session: the structure review is done; here is what is left

Paste this whole file as the first message of a new session.

---

You are picking up `~/vic2saveanalyzer`, a Victoria 2 save-file
analyzer. It has a GitHub remote, `origin` (github.com/vic2tools/vic2saveanalyzer),
but its `main` is still `a78b1c3` from 2 September: **none of the hundred-odd
commits since has been pushed**, and nothing should be without the maintainer saying
so. The code is as of `67d6c69`; the commit after it only writes
`REVIEW.md`, `INTERNALS.md`, `testkit/README.md` and this file. The working
tree is clean, all 26 checks pass, and the mutation harness catches 54 of
54. Backup bundles sit in `~`, one per session, never overwritten; the
newest is named for the last commit of the 25 September structure session.

The maintainer develops on Fedora and ships on Windows as `dist/vic2saveanalyzer.exe`,
so anything platform-specific gets written on the machine that cannot test it.
He is not a software engineer: explain in plain terms, and prefer doing the
work over asking design questions. He hands work over for long stretches and
wants verified work, not check-ins. Ask him only what is genuinely his, such
as a fix that would change a number the program shows.

**`dist/vic2saveanalyzer.exe` is out of date with the source** and has to be
rebuilt on Windows. **It also carries no Rust scanner**, so Windows users read
every save in Python: on this machine a cold run is 10.7 s without the scanner
and 3.6 s with it, and on a smaller machine the gap is wider. `build_exe.py`
bundles the scanner only if `scanner/target/release/vic2scan.exe` exists, so on
Windows run `cargo build --release --manifest-path scanner/Cargo.toml` first,
then `python build_exe.py`. Whether `build_exe.py` should refuse to build
without the scanner is the maintainer's call; it has been put to him and not decided.
Rust is installed here (rustup stable 1.98.1 in `~/.cargo/bin`, not on the
PATH: `export PATH="$HOME/.cargo/bin:$PATH"`), Linux target only, no Wine.
The scanner builds with no warnings.

Read `INTERNALS.md`, the **Speed** section, before changing anything for
speed: the two entries dated 2026-09-24 are where the time went and what was
done about it, dead ends included. `REVIEW.md` §12-§31 is the last bug
review and what it decided, and §32-§35 the structure review after it: what
moved where, and what was left on purpose and why. Do not reopen what either
marks decided.

## Where things are now

The 25 September session moved a good deal, so names in older notes may
point at the wrong file. The run is `vic2_analyzer.py` (the walk, the
tables, `_main`); its settings and command line are `run.py`, with
`RunError`, which every refusal raises; the report stamp is `stamp.py`.
Reading a save is `readsave.py` (`analyze_save(path, reading)` -- the
reading is an argument now, there are no parser globals), with
`readwar.py` for war blocks. The front of a save and the event-flag rule
are `savehead.py`, dates `dates.py`, the war book `wars.py`, the market
`market.py`, the tables' columns `spending.NARROW`. `--cross` lives whole
in `cross.py`, `--verify` and `--peek` in `explain.py`, what the windows
remember in `settings.py`. A run with no mod carries `mod_reader.NO_MOD`.
The scanner is `scanner/src/{main,province,country,text}.rs`.
`testkit/readboth.py` is the one way to read a save both ways, and a check
that cannot run here exits 77 (`testkit/outcome.py`).

## The contract. Nothing is done without all four.

```bash
cd ~/vic2saveanalyzer
S="/path/to/saves/1870s"                  # 103 saves, 3.3 GB
M="/path/to/mod/Modus Omnino Demens 1.6"
export PATH="$HOME/.cargo/bin:$PATH"

# Clean worktrees of the previous commit and of this one, each with a
# scanner built from its OWN source -- copying one binary into both makes
# step 1 compare a scanner change with itself.
for t in base:HEAD~1 head:HEAD; do
  git worktree add --detach /tmp/${t%%:*} ${t#*:}
  cargo build --release -q --manifest-path /tmp/${t%%:*}/scanner/Cargo.toml
done

# 1. the nine outputs, byte-identical -- --no-cache ON BOTH SIDES
for t in base head; do (cd /tmp/$t && python3 vic2_analyzer.py "$S" \
    --out /tmp/xx/$t --mod-path "$M" --rebuild --no-cache -q); done
#    compare every file with cmp; report.stamp is EXPECTED to differ.

# 2. the four diagnostics, byte-identical, the same way (-q, --no-cache,
#    capture stdout): --explain-mob-pool NET / --explain-mob NET /
#    --inventions NET / --check-inventions

# 3. all the checks, from the repository itself -- after a scanner change,
#    rebuild the repository's own scanner/target first
python3 testkit/all.py "$S" --mod "$M"

# 4. the mutation harness, against a COMMITTED worktree: every mutation
#    caught -- none BLIND, none NOAPPLY, none UNTESTED -- and exit 0
git worktree add --detach /tmp/mut HEAD
cargo build --release -q --manifest-path /tmp/mut/scanner/Cargo.toml
python3 testkit/mutate.py --tree /tmp/mut --saves "$S"
```

About ten minutes in all. Commit first, then run the contract comparing
`HEAD~1` with `HEAD`, and amend if it fails; every commit has to pass on its
own. `~/.cache/vic2speed/contract.sh` does all four exactly this way, and
`land.sh` beside it applies a diff, commits it, runs the contract and then the
benchmarks only if it passed.

The contract's third step runs the checks in the repository's own tree, so
nothing can be edited there for ten minutes at a time. The 25 September
session worked in a second worktree, `~/.cache/vic2speed/dev`, committed
there, and fast-forwarded `main` to each commit in turn to run its
contract while the next was being written. Two tools beside the contract
helped: `mutdry.py TREE` says in a second whether every mutation still finds
the text it patches, which is what moving code breaks; and `moveblocks.py`
cuts named top-level definitions, with the comments above them, out of a
file, so a move is a move and not a retyping.

**Every bug fix brings a check that fails without it, and a mutation in
`testkit/mutate.py` that proves it**, run by hand once with the failure
message read -- `mutate.py` counts any failure as caught. A change that moves
code a mutation patches has to move the mutation with it: two did this
session (`explain-without-wars`, `empty-table-left-stale`), and one of them
went BLIND rather than failing to apply, which only the harness noticed.

## Measuring

`~/.cache/vic2speed/` holds the harness this session used; keep it outside
`/tmp`, which does not survive the reboots this machine has.

- `bench.py MODE ROUNDS name=/tree name=/tree [-- args]` runs trees in
  alternation and prints medians, ranges and how many paired rounds each
  won. Modes: `cold` (a new empty `TMPDIR` every run), `warm` (`--rebuild`
  over a full cache), `nochange`, `newsave` (102 saves cached and reported,
  the 103rd appears -- the everyday run), `modcold` (saves cached, the mod
  not). `START=spawn` starts workers the Windows way; `CPUS=0,2,4,6` with
  `-- --jobs 3` imitates a four-core machine (siblings here are 0/1, 2/3...);
  `MOD=/tmp/fakegame/mod/...` uses a stand-in game install that
  `fakegame.py` builds, with 1,385 flags, because this mod had no game
  beneath it and so drew six.
- **Since 26 September the real game is installed here**, at
  `~/.local/share/Steam/steamapps/common/Victoria 2`, and a mod kept outside
  an install is now read on the one Steam has (`mod_reader.with_game`). So
  the Downloads mod reads the game's map and 138 flags: a warm rebuild went
  from 1.11 s to 1.84 s and the report from 1.7 MB to 2.7 MB, every CSV
  byte-identical. Every timing and contract log above that date was taken
  without the game. `HOME` pointed at an empty folder hides Steam, which
  is how to get the old conditions back for a comparison.
- `phases.py` + `timeline.py` time the parent's phases and every worker job
  on one clock, without touching the tree.
- Seven warm rounds cannot tell 10 ms apart: identical code has read 6 ms
  apart. For small differences use fifteen rounds and the paired count.

## Traps that have cost real time

1. **Never edit the tree while `testkit/all.py` is running.**
2. **A fresh `git worktree` has no Rust scanner**; build it in the worktree.
3. **This is a desktop.** Interleave, three to nine rounds at least.
4. **Keep `TMPDIR` short or unset** (the forkserver's socket path).
5. **`mutate.py` refuses a worktree with uncommitted changes.**
6. **`caching.py` and `modcache.py` take no arguments.**
7. **A check that fails is not evidence either.** Read why.
8. **`/tmp` is memory, and the machine reboots** -- it did twice this
   session, taking worktrees and uncommitted work with it. Keep scratch
   worktrees and anything unrebuildable elsewhere (`~/.cache/vic2speed/`).
9. **Do not start many subagents at once.**
10. **A script piped in on stdin cannot start workers.** Write it to a file.
11. **`python3 -m cProfile vic2_analyzer.py` breaks the workers.** Profile a
    worker's job in one process, and time the parent in phases.
12. **A background job does not stop because you stopped watching it.** A
    benchmark left running from a failed contract ran against worktrees the
    next contract was recreating.
13. **Pickle bytes are not a fair comparison across processes**: sets come
    out in a different order under each hash seed. Compare values, or fix
    `PYTHONHASHSEED`.
14. **Check a change to how the program ends with its output on a pipe**,
    not only redirected to a file. A fast `os._exit` passed every hand check
    written to files, and left workers holding the pipe open for ever: the
    contract caught it, and it was reverted (`INTERNALS.md`).

## What is left

0. **A finished, checked change not yet committed**:
   `~/.cache/vic2speed/parsespan-67d6c69.diff` reads the wars, the market and the
   great power list with one `findall` instead of a token at a time -- the
   same trees on all 16,280 such blocks in the campaign and on 100,000
   random token streams, 2.49 s of worker time to 1.66 over the campaign,
   and it helps the Python-only reading Windows users get today. Its commit
   message is `msg-parsespan.txt` beside it. It needs the contract, and a
   benchmark with `CPUS=0,2,4,6 -- --jobs 3`, where it should show. The
   original `parsespan.diff` no longer applies after the reader was
   restructured; the `-67d6c69` one is it ported to the new loop, and was
   checked to apply, keep `parity.py` identical, and leave a twelve-save
   run's outputs byte-identical with the scanner and without it.
1. **The wars, the market and the great power list in Rust** -- Python's
   whole remaining share of reading a save, about 25 ms of every save's CPU
   after this session. It barely shows here: past eight workers reading is
   bound by memory (4 / 8 / 15 workers: 4.78 / 3.70 / 3.57 s cold). On a
   four-core machine it would be worth about half a second of a 5.8 s cold
   run. Two things to settle first, both in `scanner/src/country.rs`, which
   has a Rust `parse_block` already: it folds a repeated key into an earlier
   bare-value list where Python keeps the two apart (`_MultiList`), and its
   tokenizer's whitespace is not Python's `\s` (NBSP, `\x1c`-`\x1f`). And
   `read_war` calls `str()` on whatever it finds, so a block where a name
   should be has to make the scanner refuse the save, not guess at repr.
2. **The payload's series and facts built in the workers**, as the narrow
   tables now are (`spending.save_rows`). About 40 ms of a warm rebuild, but
   only if the main table's rows stop travelling too, and the verbose
   summary reads them.
3. **One pool for both passes**, and started before it is needed: 35-80 ms
   of every run with a mod.
4. **Two things the maintainer decided to leave** (`REVIEW.md` §30), and the leads in
   `REVIEW.md` §27, as before.
5. **What the structure review left on purpose** (`REVIEW.md` §35): the
   window capturing `sys.stdout`, the three hook globals, and the Rust
   country reader's own number parsing -- which trims Unicode whitespace as
   Python does, and has to be settled before item 1 anyway.

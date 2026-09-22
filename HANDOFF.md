# Next session: the four jobs are done; here is what is left

Paste this whole file as the first message of a new session.

---

You are picking up `~/vic2saveanalyzer`, a Victoria 2 save-file
analyzer. It is a local-only git repo — **nothing has ever been pushed**, and
there is a verified backup bundle at `~/vic2saveanalyzer-backup.bundle`.
HEAD is `834da7f`. The working tree is clean and all 24 checks pass.

The maintainer develops on Fedora and ships on Windows as `dist/vic2saveanalyzer.exe`,
so anything platform-specific gets written on the machine that cannot test it.
He is not a software engineer: explain in plain terms, and prefer doing the
work over asking design questions.

## How to verify anything you change

These three, in this order, are the contract. Do not report work as done
without them.

```bash
cd ~/vic2saveanalyzer
S="/path/to/saves/1870s"                       # 103 saves, 3.3 GB
M="/path/to/mod/Modus Omnino Demens 1.6"

# 1. the nine outputs must be byte-identical unless you meant to change them
python3 vic2_analyzer.py "$S" --out /tmp/xx/after --mod-path "$M" --rebuild -q
#    compare against a run from a clean checkout of HEAD;
#    report.stamp is EXPECTED to differ, it hashes the source

# 2. the four diagnostics must be byte-identical
#    --explain-mob-pool NET / --explain-mob NET / --inventions NET / --check-inventions

# 3. all 24 checks
python3 testkit/all.py "$S" --mod "$M"
```

**Four traps. The first three cost the previous session real time; the fourth
cost this one an hour of believing a comparison that was not comparing.**

1. **Never edit the tree while `testkit/all.py` is running.** It reads files
   at exec time; a mid-run edit produces a mixed result.
2. **Never benchmark while anything else is running.** Note that this is a
   desktop: Firefox, VS Code and Discord hold the load average near 4 on
   their own, and it will never fall to zero. Interleave instead — alternate
   before/after runs inside one loop so the noise lands on both sides — and
   do three to five rounds, never one run of each.
3. **Keep `TMPDIR` short.** Python 3.14 starts workers through a forkserver
   whose socket lives in `TMPDIR`, and an `AF_UNIX` path cannot exceed 108
   bytes. A long one degrades the run to serial reading, which silently makes
   every benchmark meaningless. `TMPDIR` is unset here, so it is `/tmp`, which
   is also where the 375 MB parse cache lives — leave it alone.
4. **A clean `git worktree` of HEAD is not a working baseline.**
   `scanner/target/` is untracked, so a worktree has no built Rust scanner and
   reads every save in Python. That is four times slower and it silently makes
   the comparison "HEAD without the scanner against yours with it". Copy
   `scanner/target/release/vic2scan` into the worktree before you measure
   anything. (The outputs do match either way — that is what parity is for —
   but it is not the A/B you meant to run.)

**Benchmarking the parse specifically needs `--no-cache`.** The parse cache
key hashes the source of the six parser files, so editing any of them makes
the cache cold once and warm forever after; a warm run skips the parse
entirely and measures nothing you changed.

## What was done this session

Five commits on `main`, each independently verified against the contract
above. The four jobs the last handoff listed are all finished.

- **`c7c7c6d`** — `--cross` and the report measured the same campaign by two
  copies of one recipe that had drifted in five places, the worst being that
  the cross block never applied the mod's `POP_SIZE_PER_REGIMENT`. There is
  one `finish_nations` now, with `kept_by` for the filter and `finish_spec`
  deciding what either is given. `testkit/crossrows.py` is new.
- **`2680ab2`** — `testkit/parity.py`, the only thing holding the Rust scanner
  and the Python parser to the same output, had stopped comparing: it switched
  the scanner off by replacing `fastscan.scan`, which `analyze_save` does not
  call. It had been reporting "identical across 41 nations" for free. The two
  readers do agree; nothing was hiding behind it.
- **`549fd6e`** — the fold from the scanner's shapes into the nation record
  moved from `fastscan` into `nation.py`, beside the fields it fills.
  `testkit/record.py` is new and holds the record and both readers together
  from the sources alone — no save, no mod, no Rust compiler, not even the
  built binary.
- **`173834c`** — `readsave.Reading` is the one object for how a run reads a
  save. `apply` sets the three parser globals, `fingerprint` is the cache key,
  and the key can no longer describe a state the parse is not in.
- **`834da7f`** — `load_mod` returns a `Mod` with named fields instead of a
  dict with thirty-eight keys, and `decode_indices` must run before
  `index_base` will answer, so a caller who forgets no longer gets the
  invention upper bound served as though it were the real count.

Everything the last handoff said was already done is still true:
`nation.py` owns the record, `modrules.py` owns judging a mod's rules,
`mod_reader.py` reads mod files, `cacheio.py` owns the compressed caches.

## What is left

Nothing urgent. In rough order of value:

1. **`--cross` is thinly exercised on real data.** `testkit/crossrows.py`
   proves the two paths agree, on synthetic campaigns. The only real campaign
   here is one folder, and the mod it was played on happens to set
   `POP_SIZE_PER_REGIMENT` to exactly 3000 and to mobilize exactly the vanilla
   three pop types — which is *why* the job-1 bug survived so long. A campaign
   on IGoR or GFM would exercise it properly. Worth asking the maintainer whether he has
   one.

2. **`walk_campaign` still reads `v2parse.POP_TYPES` directly** for its pop
   columns (`vic2_analyzer.py`, in the accumulator setup). It is a read of the
   global the parse actually used, so it is correct — but it is the last place
   that reaches for a parser global rather than being handed one, and the
   `Reading` is right there in `spec`... except it is not, because `Finish`
   does not carry it. Either give `Finish` the reading or pass it alongside.

3. **The Python reader still names the record's fields for itself.**
   `549fd6e` stopped `fastscan` doing it; `readsave.read_province` and
   `read_country` still accumulate into `nat["..."]` by name, scattered through
   the hot loop. Narrowing that means restructuring the loop that is 55% of the
   parse, so measure before and after, with `--no-cache`, and expect it not to
   be worth it.

4. **`testkit/parity.py` builds one synthetic save when given no folder.**
   It could build several, with the shapes `awkward.py` knows about — an army
   on a transport, a province with no owner, a mod's own block inside a pop.

## Two things to leave alone, with reasons

- **`template.py`, 5372 lines.** 5361 of them are one string holding the
  report page. Splitting it into real `.html`/`.css`/`.js` files means
  PyInstaller data files and `sys._MEIPASS` handling in a one-file
  executable, on Windows, which cannot be tested from this machine. The
  current design means the exe carries the page with no plumbing at all, and
  `testkit/boots.py` already runs it in headless Firefox with a console-error
  handler. If you want to close this, write it up as a decision record rather
  than doing it.
- **The report stamp is deliberately too eager.** It hashes every `.py`
  beside the program, so editing `gui.py` rebuilds a report that did not need
  rebuilding. That is on purpose: a needless 6-second rebuild is visible, a
  skipped one serves numbers from the last time somebody looked.
  `testkit/staleness.py` enforces it. Do not "optimise" it back into a list
  of filenames — that list was wrong within a day of being written.

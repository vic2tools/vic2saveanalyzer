# Task 01: baseline, and delete the dead scanner modes

Read `CONTEXT.md` and `STATUS.md` first.

1. **Bench script.** Write `~/.cache/vic2speed/opt/bench.sh` that, for a
   given tree, runs the real campaign:
   - warm rebuild ×5 (stamp removed between runs);
   - empty scratch cache ×3;
   - nothing changed ×3.

   It prints wall times and the `VIC2_ENGINE_TIMES=1` phases (median per
   phase). It must use a scratch `TMPDIR`, never the real cache.
2. **Baseline.** Run it on `11e1f21`. Save the outputs as the reference in
   `opt/runs/11e1f21/`: the CSVs, report.html, stdout and stderr. Put the
   numbers in `STATUS.md`.
3. **Delete the dead modes** listed in CONTEXT.md:
   - `vic2scan report SPEC`;
   - the save scan's JSON and `--record` answers (`main.rs`, `record.rs`,
     `pickle.rs`, `clause.rs`);
   - `mod_file`, the mod read from a JSON export.

   Grep the Python, the testkit and `build.rs` first to prove nothing
   reaches them. Keep `analyze`, `mod-export` and every `selftest-*`.
   Delete what becomes unused in `country.rs` and `province.rs`, but no
   more. One commit.
4. **Verify.**
   - All checks.
   - Real-campaign outputs byte-identical to the reference.
   - Mutations: `testkit/mutate.py` may patch files you deleted. Re-aim or
     drop those mutations, and say which.
   - The bench again; it should not change speed.
5. Add an INTERNALS.md note, a bundle, and a `STATUS.md` entry.

Expected size: small. No speed change expected.

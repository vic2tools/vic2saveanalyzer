# Task 02: exit without freeing, and the worker count

Read `CONTEXT.md` and `STATUS.md` first.

1. **Exit without freeing** (CONTEXT.md, step "exit without freeing"). The
   ~0.3 s after "tables written" is freeing the campaign's memory.
   - Skip it for an ordinary run.
   - Keep freeing per campaign in `--cross`, which calls `run_spec` once per
     campaign in one process.
   - Check the window path (`--protocol`) and an ordinary run through a
     pipe, and look for leftover `vic2scan` processes afterwards.

   One commit.
2. **Worker count** (`engine::worker_count`).
   - Replace the MemFree rule with available memory (MemAvailable on Linux,
     `avail_phys` on Windows), and a per-thread memory estimate measured for
     Rust threads (measure peak RSS against `-j`).
   - Measure whether threads above the physical core count ever help on the
     empty-cache run.
   - The count must be stable from run to run.

   The "Reading N save(s) on K cores." line is recorded output in the
   testkit only where `-j` is given; check that nothing recorded changes.
   One commit. Windows memory logic is unverified; say so.
3. **Verify each commit:** checks, the real campaign against the
   reference, and the bench. Run mutations once, after both commits.
4. Add an INTERNALS.md section with before/after numbers, a bundle, and a
   `STATUS.md` entry.

Expected: warm ~1.4 → ~1.1 s.

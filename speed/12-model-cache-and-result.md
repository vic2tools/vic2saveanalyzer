# Task 12: data-model rewrite: the engine cache, and the result

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first, and what the tasks before
this one left in `STATUS.md`. Every stage so far moved its own fields into the
cache as it went, by `Sym` through the entry's own name table (MODEL.md 5.5).
This one finishes the format, decides what is left, and measures the whole.

1. **The cache's final form** from MODEL.md 5.5: sections with their lengths
   in front (`Meta`, the nations, the chunk), every `Vec` made with its exact
   length on load, no field the model no longer has (`Held` is gone), and the
   per-entry name table. The aim is as few allocations as possible a save and
   a load that is mostly reading bytes.
   - **Arenas, or not.** Look at the warm rebuild's pass one first. If it is
     already under about 50 ms (it was 0.214 s), leave the containers
     alone; if not, MODEL.md 5.3's per-save arenas (one `Vec` of entries per
     kind a save, a range each) are the next step, as their own commits.
   - Keep the safety properties `testkit/caching.py` checks: keyed by path,
     size, mtime and reading; damaged or cut-short entries rejected; a save
     rewritten to the same size within a second is re-read.
   - Bump nothing by hand: the build id changes the cache version. Check that
     a run over an old-format cache rebuilds correctly.
2. **Teardown.** With the war records already freed off the walk's path and
   the compact model, see whether the task-02 exit-without-freeing is still
   needed or whether freeing is now cheap. Keep whichever is simpler at equal
   speed, and check any change to how the run ends through a pipe
   (`speed/pipecheck.sh`).
3. **Dense lookups, finished** (MODEL.md 5.6): nothing in `finish` or `rules`
   should still hash a name per nation. Look at `VIC2_TIMES`'s `finish` parts.
4. **Re-measure everything** against task 01's baseline and MODEL.md 1.3's
   table: warm, empty cache, nothing changed, and a truly cold run if the
   maintainer agrees to `trulycold.py` (see CONTEXT.md). The probe's three
   numbers (allocations by stage, live at each phase, what is held) and its
   clocks (`VIC2_TIMES`) beside MODEL.md section 4. Re-profile with
   `sample_run.sh` on the laptop or `gdbsample.py` here.
5. Verify as always, including the full mutation run. Then add an INTERNALS.md
   section summarising the whole rewrite (before/after table for every stage,
   what was tried and dropped), a bundle, and a `STATUS.md` entry.

# Task 09: data-model rewrite: the engine cache, and the result

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first.

1. **The new engine-cache format** from MODEL.md: the compact model,
   written and loaded with as few allocations as possible, ideally close to
   a straight dump of a few large buffers per save.
   - Keep the safety properties `testkit/caching.py` checks: keyed by path,
     size, mtime and reading; damaged or cut-short entries rejected; a save
     rewritten to the same size within a second is re-read.
   - Bump nothing by hand: the build id changes the cache version. Check
     that a run over an old-format cache rebuilds correctly.
2. **Teardown.** With the compact model, see whether the task-02
   exit-without-freeing is still needed or whether freeing is now cheap.
   Keep whichever is simpler at equal speed.
3. **Re-measure everything** with the bench against task 01's baseline:
   warm, empty cache, nothing changed, and a truly cold run if the maintainer agrees
   to `trulycold.py` (see CONTEXT.md). Re-profile with `sample_run.sh`.
4. Verify as always, including the full mutation run. Then add an
   INTERNALS.md section summarising the whole rewrite (before/after table
   for every stage), a bundle, and a `STATUS.md` entry.

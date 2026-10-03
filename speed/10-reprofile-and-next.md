# Task 10: re-profile, and the next round

Read `CONTEXT.md` and `STATUS.md` first.

Profile the current tree (bench plus `sample_run.sh`, warm and empty-cache)
and rank what is left. Candidates from the 1 Oct profile:
- caching the map's anchors and spots per mod;
- the cache-load path, if still visible;
- province parsing itself: SWAR or `std::arch` SIMD scanning for `{`, `}`,
  `=` and newlines (`text::find_pair` is already SWAR);
- fewer passes over each save's bytes (`top_level_blocks`, then provinces,
  then countries);
- `mmap` instead of copying a save into a buffer. Measure; on btrfs with
  compression it may not help, and it is unverified on Windows.

Pick the one or two with the best measured payoff, do them as their own
commits with the usual verification, and write in `STATUS.md` where the
floor appears to be and what a further task would attack. If more work is
worth doing, write it as `11-*.md` in this folder, in the same shape as
these task files.

# Task 13: re-profile, and the next round

Read `CONTEXT.md` and `STATUS.md` first.

Profile the current tree (bench plus `sample_run.sh`, warm and empty-cache)
and rank what is left. Candidates from the 1 Oct profile:
- caching the map's anchors and spots per mod (`map: raster decoded, spots
  placed` is 0.131 s of every warm rebuild, and depends only on the mod);
- the cache-load path, if still visible;
- province parsing itself: SWAR or `std::arch` SIMD scanning for `{`, `}`,
  `=` and newlines (`text::find_pair` is already SWAR);
- fewer passes over each save's bytes (`top_level_blocks`, then provinces,
  then countries);
- `mmap` instead of copying a save into a buffer. Measure; on btrfs with
  compression it may not help, and it is unverified on Windows.

From the 3 Oct measurements on the Windows PC (16 cores, 32 logical, 31
workers by default; `speed/model-census-2026-10-03.txt` sections 8-10):
- **Mapping the saves on Windows.** Windows reads each save into a buffer
  (`Bytes::Mapped` is Linux only). The file load is 5.0 ms a save alone and
  28 ms at 31 workers, 17% of the empty-cache run's thread time and about as
  much as the countries; `top_level_blocks` another 6%. `CreateFileMapping` and
  `MapViewOfFile` are the first thing to try, with the same truncation guard
  the Linux mapping has (a save the game is rewriting).
- **The worker count.** The default is cores bar one, 31 here, on 16 cores of
  two threads; a save takes 54 ms of one thread and 163 ms at 31. An
  empty-cache scan on 3 Oct (three interleaved rounds each, the wall of the
  run): 8 workers 3.21 s, 12 2.77 s, 16 2.65 s, **20 2.54 s**, 24 2.62 s, 31
  2.68 s: flat from 20 up and about 0.15 s better there than at the default.
  Three rounds are not enough to pick a number (the noise is about 0.05 s);
  scan it properly, and find a rule that also gives the laptop's 15 of 16
  (task 02 measured 8 to 16 there and every step up helped).
- **Outside the engine.** About 0.2 s of a 1.0-1.2 s warm rebuild is not the
  engine's clock: the launcher, the process starting, the kernel taking its
  memory back.
- The integer tables (`core_provinces`, `province_state`, `colonial_*`,
  `soldier_pops_at`): hash inserts and small `Vec`s the model rewrite does not
  touch (MODEL.md 5.8).

Pick the one or two with the best measured payoff, do them as their own
commits with the usual verification, and write in `STATUS.md` where the
floor appears to be and what a further task would attack. If more work is
worth doing, write it as `14-*.md` in this folder, in the same shape as
these task files.

# Task 04: the per-save state-history chunk

Read `CONTEXT.md` and `STATUS.md` first.

Each save's state-history chunk is built as JSON, gzipped with the
hand-written deflate at zlib level 6, and base64'd in the worker
(`finish.rs` ~line 250, `deflate.rs`). That is ~14% of pass one.

1. Measure what the chunk costs: JSON building against compression. Use a
   microbenchmark over a few real saves' chunks (a `selftest`-style hidden
   mode, or timing inside a probe build).
2. Try, keeping what pays:
   - fewer allocations building the JSON;
   - a faster compression mode in `deflate.rs` (a lazy-match-free or
     shorter-chain level, as zlib's levels 1-3 do).

   Report bytes against time: how much `report.html` grows and how much
   faster pass one gets. If the trade is poor (for example +20% page size
   for −3% time), keep level 6 and say so.
3. `selftest-deflate` checks output against zlib byte for byte at level 6.
   Keep that check for level 6, and add a round-trip check (Python's
   `zlib.decompress`) for any new level.
4. Verify:
   - the checks; they compare the decoded page;
   - the real campaign: CSVs byte-identical, the payload decoded identical
     (use `testkit/expected.py`'s decoding);
   - mutations;
   - `testkit/boots.py` and `state_history_ui.py` on the new page (they
     run inside `all.py` with saves).

Commit, add INTERNALS.md notes, a bundle, and a `STATUS.md` entry.
Remember: the maintainer allowed report.html bytes to differ only if the decoded
content is identical.

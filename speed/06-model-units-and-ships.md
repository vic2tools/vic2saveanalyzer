# Task 06: data-model rewrite: units and ships

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first. MODEL.md, written
in task 05, is the design. Follow it, and if the code proves it wrong, fix
MODEL.md and say so in `STATUS.md`.

Do the units-and-ships stage as MODEL.md describes. String-keyed maps become id-indexed
storage; strings come back only where output is written. Keep every
observable order exactly as MODEL.md records it.

- The engine-cache format may change in this stage only as far as these
  fields need. The full redesign is task 09.
- Commit in pieces that each pass the checks, not as one big change.
- Verify:
  - the checks;
  - the real campaign: CSVs and payload identical to the reference;
  - mutations: re-aim any that patched code that moved, and never drop a
    mutation just because it no longer applies;
  - the bench, with the allocation count from the probe allocator against
    task 05's numbers.
- Add INTERNALS.md notes, a bundle, and a `STATUS.md` entry with numbers.

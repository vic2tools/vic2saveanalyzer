# Task 10: data-model rewrite: units and ships

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first, and what the tasks before
this one left in `STATUS.md`. MODEL.md, written in task 05, is the design. If
the code proves it wrong, fix it there and say so in `STATUS.md`.

The smallest payoff of the nation stages, and the one with two readers and the
most observable orders, so it comes last of them. `units_at` and `men_at` are
788,000 live allocations (two maps a province, each with a map of kinds), the
ships and regiments 93,000.

Do the units-and-ships stage as MODEL.md describes:
- `ships_by_type` and `ship_crew` become one `Vec<Ship { kind, count, crew }>`
  (same keys, same order, MODEL.md 1.2);
- `regiments_by_type` a `Vec<(Sym, i64)>`;
- `units_at` and `men_at` one flat `Vec<Stack { pid, kind, n, men }>`, grouped
  by province, in first-seen order: one allocation a nation instead of two and
  four a province. First the `Sym` change with the containers as they are,
  then the flattening, as separate commits;
- both readers: `country.rs` (`Tally`, `Units`, `count_units`) and `walk.rs`
  (its own `Tally`, `Units`, `count_units`). One `Tally` for both would be
  the tidy end;
- `finish.rs`'s ship and brigade tables, `PerNation`, `report.rs`'s armies,
  `Kept`.

- Order is observable twice (MODEL.md 3.2): the provinces of `units_at` (the
  page's armies come out in nation order, then province order) and the kinds
  inside one (a stable sort by count, so ties keep first-seen). The sorts of
  ships, regiments and pop types are by name: on the text, not the id.
- Verify: the checks; the real campaign; once with
  `VIC2_ENGINE_NAMES_SHIFT=7`; mutations: re-aim `walk-navy-not-entered` and
  `walk-colonies-ignored` (they patch `walk.rs`' `count_units`), add one that
  reverses `units_at`'s inner order; the probe and `VIC2_TIMES` against MODEL.md
  section 4.
- Expected (estimates): about 0.8 M fewer live allocations after pass one;
  the warm rebuild's pass one about 0.02 s quicker; the empty-cache run about
  0.02-0.03 s.
- Add INTERNALS.md notes, a bundle, and a `STATUS.md` entry with numbers.

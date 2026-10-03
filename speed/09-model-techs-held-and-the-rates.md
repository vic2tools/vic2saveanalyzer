# Task 09: data-model rewrite: techs, `Held` and the rates

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first, and what the tasks before
this one left in `STATUS.md`. MODEL.md, written in task 05, is the design. If
the code proves it wrong, fix it there and say so in `STATUS.md`.

Two halves, in this order. If the session runs out, stop at the end of the
first, committed and passing, and say so.

1. **Carry less** (MODEL.md 5.7): nothing converted, three things stopped.
   - `Held` goes: the invention pass (`rules::settle_campaign`,
     `holdings`, `violations`), `explain.rs` and `mod.rs`' `held_names` read
     slices of `PreNation` instead of a second copy of the tech list and the
     invention ids. 0.52 M live allocations, 28.5 MB, a field of every cache
     entry.
   - `Row.nat` goes: a `RowFacts` holds what `Row::get` reads (MODEL.md 1.1,
     `pop_by_type` included) and the rest of the nation is dropped after
     `finish` has built the tables. 2.34 M allocations carried through the
     walk and the page.
   - `Kept` is moved out of the nation, not cloned (`finish.rs`, `trim`).
2. **Techs and the rates**: `tech_list`, `invention_ids` (already ints),
   `modifiers`, `reforms`, `nationalvalue` on `Sym`, in both readers
   (`country.rs`, `walk.rs`) and the fold; and the mod's lookups the rates
   make per nation (`tech_mob`, `event_mob`, `nv_mob`, `reform_mob`,
   `Spec.tech_group`, `naval_tech_effects`) as dense tables indexed by `Sym`
   (MODEL.md 5.6), built once after pass one. `settle_campaign` is one thread
   and 0.050 s of every run (the tech sets 12 ms, `index_base_for` 37 ms).
   `rate_for`, `impact_for` and `naval_profile` are 0.50 s of pass two's
   1.55 s of thread time.

   Optional, last, only if the profile still asks: `goods_supply` (0.39 M),
   `country_flags`, and the seven scalar names. The scalars are 7 Strings a
   nation (74,000 allocations in all) and touch everything (`tag` is every
   table's key): leave them Strings unless the numbers say otherwise.

- Order: `tech_list`, `invention_ids`, `modifiers` and `reforms` reach the
  output only through `py_sum`'s last bit and did not move it here; keep them
  in the order the save gave them anyway, it is free (MODEL.md 3.2).
  `goods_supply` does reach the page (the goods' first-seen order).
- Verify as in task 06: the checks; the real campaign; once with
  `VIC2_ENGINE_NAMES_SHIFT=7`; mutations re-aimed (`finish.rs`'s, `explain.rs`'s,
  `rules.rs`'s); the probe and `VIC2_TIMES` against MODEL.md section 4.
- Expected (estimates): settle 0.050 s to about 0.02 s in every run; 28.5 MB
  less held after pass one without `Held`; live allocations after the walk
  down by about 2 M.
- Add INTERNALS.md notes, a bundle, and a `STATUS.md` entry with numbers.

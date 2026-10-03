# Task 05: data-model rewrite, part 1 of 5: the survey and the design

Read `CONTEXT.md` and `STATUS.md` first. **No code changes to `main` in
this task**; the output is a design document that tasks 06-09 follow.

Write `speed/MODEL.md`:

1. **Every string-keyed or string-holding field.** Go through
   `engine::model::Nation` (`model.rs`), `Meta`, `Market`, `finish::Pre`,
   `Kept`, `Row`, the war records, and whatever the walk and report build
   from them. For each one, give its type, roughly how many entries it has
   per nation per save (count them on a real save), and every place that
   reads or writes it.
2. **Where order is observable.** For each field, does its iteration order
   reach the output (CSV column order, payload order, printed lines)? Is
   that order first-seen, sorted, or the mod's? Back each answer with the
   code path and a real example. This is the part that decides whether the
   rewrite is right.
3. **Allocation counts** today: allocations per save in pass one, and live
   allocations after the walk. Use a counting global allocator in a probe
   build; `std::alloc::GlobalAlloc` wrapping `System` needs no crates.
4. **The design.**
   - The name tables: per run or per save? How are per-save ids merged
     across worker threads?
   - What replaces each field: `Vec<i64>` by id, a small sorted
     `Vec<(u32, i64)>`, or a bitset for flags.
   - How first-seen order is kept where it matters.
   - The new engine-cache format.
5. **The staging** for tasks 06-09. Check that the split below fits the
   code, and adjust it in MODEL.md if not:
   - 06: units and ships (`ships_by_type`, `ship_crew`,
     `regiments_by_type`, `units_at`, `men_at`);
   - 07: pops and cultures;
   - 08: techs, inventions, flags, modifiers, reforms and the rest;
   - 09: the engine-cache format and teardown, then re-measure.

   Each stage must pass the full suite on its own.

End with a `STATUS.md` entry pointing at MODEL.md.

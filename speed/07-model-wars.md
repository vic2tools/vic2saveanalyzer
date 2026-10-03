# Task 07: data-model rewrite: the wars

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first, and what task 06 left
in `STATUS.md`: `names.rs` exists now and this stage uses it.

`Meta.wars` is the largest single holder in the engine: 4.14 M of the 9.49 M
live allocations after pass one (44%). In a warm rebuild it is the cache
load's biggest part, 0.066 s of the walk's folding (`Book::fold_save` compares
every record with the last one of its name, Strings and all) and, unless
task 06's first commit is in, 0.131 s of freeing.

Do `War`, `Goal`, `FirstGoal`, `Battle` and `Side` (every name, tag, date and
leader a `Sym`; a side's `units` an `OMap<Sym, i64>`), `wars::Held`, `Book`
and its keys (`Key`, `BattleKey`, `join_dates`, `goalbook`), `wars::build`,
`rules::save_world`, `explain.rs`, the cache's `keep_struct!`s, and
`report.rs`'s use of them (the owners it hands `wars::build`).
`model::read_war` still builds them from the `clause::Tree`; reading the
bytes straight is task 11.

- Order is observable here, more than anywhere (MODEL.md 3.2): the wars, a
  war's battles, its goals and a side's units reach the page in the order the
  file gave them. Keep every `Vec` and `OMap` in that order.
- Every sort and every date parse works on the text: `sorted_names`
  (`model.rs`), `sorted_union` (`wars.rs`), `date_key`, `year_fraction`.
  `Sym` has no `Ord`, so a sort by id will not compile; a hash container
  keyed by `Sym` must not be iterated into an output.
- `War` is compared whole (`Book::fold_save`, `PartialEq`): interning is
  canonical, so equal text is an equal `Sym`, and the comparison gets
  cheaper, not different.
- Verify as in task 06, with `VIC2_ENGINE_NAMES_SHIFT=7` once, and the new
  mutations MODEL.md 7 asks for (reverse a side's units; reverse a war's
  battles). Re-aim `at-war-from-joins`, `explain-without-wars` and
  `goal-judged-before-first-save`.
- Expected (estimates): live allocations after pass one to about 4 M, then
  with the arenas MODEL.md 5.3 names, a few hundred thousand; the warm
  rebuild's pass one to about 0.13 s; the Book's fold about half; the
  walk's free 0.131 s to about 0.03 s if it is still there. **This is the
  stage that decides whether the rest is worth doing** (STATUS.md, "the
  gate"): put expected beside measured in the `STATUS.md` entry, and if the
  gain is under half of what is expected, re-rank what remains by the
  numbers before starting the next task.
- Add INTERNALS.md notes, a bundle, and a `STATUS.md` entry.

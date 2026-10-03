# Task 08b: data-model rewrite: what a save says that is not one nation's

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first. MODEL.md, written in
task 05, is the design; this stage was added by it (section 6). By live
allocations it is the biggest of all: `Meta` is 6.6 M of the 9.5 M a
campaign holds after pass one (wars 4.14 M, `province_owner` 1.35 M, the
market 1.12 M), and reading the wars and the market through `clause::Tree`
(`model::read_rest`) is 85,000 of a save's 221,000 pass-one allocations.

Do it in two halves, each its own commits, each passing the suite:

1. **The types.** `Meta.province_owner`, `Market` (`current`, `history`,
   `snapshot`), `War`, `Goal`, `FirstGoal`, `Battle`, `Side` and `wars::Held`
   / `Book` hold `Sym`s, not Strings (MODEL.md 5.3). `OMap<Sym, _>` and
   `Vec` first, flatten later. Keep every observable order in MODEL.md 3.2:
   `wars`, `battles`, `goals`, a side's `units` and `great_nations` reach the
   output and must stay as the file gave them; `joins`, `leaves`, the market's
   maps and `province_owner` did not move the campaign's output when reversed,
   and stay in order anyway. Stamps (4,403 distinct) and dates are `Sym`s
   too.
2. **The reading.** `read_rest` parses `active_war`, `previous_war` and
   `worldmarket` into a generic `clause::Tree` and then builds the structs
   from it. Read them straight from the save's bytes into the typed structs,
   as task 03 did for the countries. The Tree reader is also what the
   reflowed-layout path (`walk.rs`) shares; check what else calls it before
   deleting anything. `testkit/enginefmt.py` and the engine's recorded
   answers for wars and prices hold the result; add a check for any rule the
   Tree reader had that nothing holds yet (an unquoted date, a war with no
   history, a battle with one side) before replacing it.

Verify as in MODEL.md 7, with the new mutation it asks for in this stage
(reverse `Side.units`), and report the three probe numbers against
MODEL.md section 4. If the second half is more than the session has left,
stop at the end of the first, committed and passing, and say so in
`STATUS.md`.

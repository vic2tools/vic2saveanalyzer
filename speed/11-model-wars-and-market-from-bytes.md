# Task 11: reading the wars and the market from the bytes (optional)

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first, and what tasks 06 and 07
left in `STATUS.md`. **Do this one only if the numbers still ask for it**: it
is the largest single piece of pass-one churn by allocations (`read_rest`:
85,000 of a save's 221,000) but 7.3% of the empty-cache run's thread time
(3.9 ms of 54 ms a save alone, 12 ms of 163 at 31 workers), and a rewrite of a
reader that has all the Python reader's quirks. Measure `read_rest` with `VIC2_TIMES`
on the tree as it stands: if it is under about 5% of the pass-one thread time,
write in `STATUS.md` that it was judged not worth it, with the figures, and go
on to task 12.

`model::read_rest` parses `active_war`, `previous_war`, `worldmarket` and
`great_nations` into a generic `clause::Tree` and builds `War`, `Market` and
the great power list from it. Read them straight from the save's bytes into
those structs, as task 03 did for the countries, now with `Sym`s and no
`Tree`.

- Both readers of a save's layout (`read_flat` and `walk.rs`) end in
  `read_rest`; check what else calls the `clause` reader before removing
  anything.
- Hold it to the recorded answers first: add a check for any rule the Tree
  reader had that nothing holds yet (an unquoted date, a war with no history,
  a battle with one side, a repeated key) before replacing it.
  `testkit/enginefmt.py` and the engine's recorded answers for wars and
  prices are the net; run both readers over every war and market block of
  the campaign and compare the structs, not only the output.
- Keep every order the task 07 stage kept.
- Verify as in task 06, plus the comparison above; report `read_rest`'s
  allocations and clock before and after.
- Expected (estimates): `read_rest` 85,000 allocations a save to under
  20,000; the empty-cache run 0.04-0.08 s quicker.
- Add INTERNALS.md notes, a bundle, and a `STATUS.md` entry with numbers.

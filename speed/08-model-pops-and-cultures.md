# Task 08: data-model rewrite: pops and cultures

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first, and what tasks 06 and 07
left in `STATUS.md`: `names.rs` exists and the wars and the owners are done.
MODEL.md, written in task 05, is the design. If the code proves it wrong, fix
it there and say so in `STATUS.md`.

This is where the first run gets its share. What a nation's pops cost is not
what they hold (475,000 live allocations) but what building them makes: the
provinces copy each name twice in a `Counter` (about half of the scanner's
45,600 allocations a save), and `build` and `prepare` make 2.2 M + 2.3 M
Strings that are dropped again (`Group.types`, `Group.cultures`,
`mobilizable_pops`, and the snapshot, whose `word` makes a String on every
call): about 50,000 of the 221,000 allocations a save costs in pass one
(counted from the census and the code, not measured apart).

Do the pops-and-cultures stage as MODEL.md describes: `Interner` and
`Counter` in `province.rs`, `pop_by_type`, `pop_by_culture`,
`accepted_cultures`, `primary_culture`, `Group`, `mobilizable_pops`,
`Snapshot` (`words`, `layouts`), `Spec.mob_types`, `PopulationRules`, and the
mod lookups they feed (`strata`, `culture_groups`), as dense tables indexed
by `Sym` (MODEL.md 5.6). String-keyed maps become `Sym`-keyed; strings come
back only where output is written.

- Both readers fill the same `Scan`: `province.rs` and `walk.rs`' own
  `read_province`. Keep `Counter::add`'s signature (a name as bytes) and
  intern inside it, and `walk.rs` needs the least change.
- Order is observable in four places here (MODEL.md 3.2): `pop_by_culture`
  (a stable sort by size, so ties keep first-seen), `population_by_state`,
  `Group.types` and `Group.cultures` (they number the chunk's words and
  layouts, which the checks compare as text). Keep each in the order the
  reader met it; the first commit is the `Sym` change and nothing else.
- Verify: the checks; the real campaign against the reference (the state
  chunks are compared decoded, as text); once with
  `VIC2_ENGINE_NAMES_SHIFT=7`; the mutations MODEL.md 7 names for this stage
  (break a stable tie in `pop_by_culture`, reverse `Group.types`); the probe
  and `VIC2_TIMES` against MODEL.md section 4.
- Expected (estimates): the empty-cache run's pass one 1.47 s to about
  1.30-1.40 s; the warm run hardly changes. Put expected beside measured in
  the `STATUS.md` entry; if the first run gained under 0.05 s, say so and
  re-rank tasks 10 and 11 by the numbers before starting them.
- Add INTERNALS.md notes, a bundle, and a `STATUS.md` entry with numbers.

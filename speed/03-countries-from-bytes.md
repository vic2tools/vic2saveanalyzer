# Task 03: parse countries from bytes

Read `CONTEXT.md` and `STATUS.md` first.

`read_flat` (`engine/mod.rs`, near the `latin1(&text[*at..*stop])` call)
copies every country block into a latin-1 `String`, and `read_country`
parses that copy. Make `read_country` (`country.rs`, `Tokens`,
`parse_fields`) work on `&[u8]` directly, as `province::read_province` does.
Convert to `String` only for the values that are kept.

The walked path for saves not laid out the game's way (`engine/walk.rs`)
must still work. `frontcheck.py` and `saveshapes.py` cover it with reflowed
saves.

Measure with the bench on the empty-cache run; pass one should drop. Also
take gdb samples (`sample_run.sh`) to confirm `text::latin1` is gone from
pass one, and record the new split.

Verify: checks, the real campaign against the reference, mutations. Then
add INTERNALS.md notes, a bundle, and a `STATUS.md` entry. One or two
commits.

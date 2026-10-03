# Task 06: data-model rewrite: the name table, the province owners and the market

Read `CONTEXT.md`, `STATUS.md` and `MODEL.md` first. MODEL.md, written in
task 05, is the design; STATUS.md says why the stages come in the order they
do and what each is expected to buy. If the code proves MODEL.md wrong, fix
it there and say so in `STATUS.md`.

This is the first stage of the rewrite, so it brings the shared plumbing, on
the two parts of `Meta` that are simplest to change: neither's order reaches
the output (reversing them moved nothing), each is built in one place, and
together they are 26% of what a campaign holds after pass one
(`province_owner` 1.35 M live allocations, `market` 1.12 M).

0. **First commit, unless STATUS.md's quick win is already in** (it may have
   been done on its own): the walk waits for the Book's thread to drop the
   saves' war records (4.1 M allocations), 0.131 s of every warm rebuild.
   Drop them on a thread the walk does not wait for (`report.rs`, `walk`):
   measured 1.172 s to 1.042 s. Not `mem::forget`: it is 0.999 s but holds
   189 MB more at its peak. This changes how the run ends, so check it as
   task 02 did (`speed/pipecheck.sh`: through a pipe, no leftover process).
1. **`names.rs`** as MODEL.md 5.2 draws it: `Sym(u32)`, one run-wide table,
   a cache per thread in front, `intern` (a save's bytes), `intern_str`,
   `text`, `cmp`; no `Ord` on `Sym`. Add the knob
   `VIC2_ENGINE_NAMES_SHIFT=k` that interns `k` placeholders first, so every
   id and every hash order moves.
2. **The cache's `Sym`** (MODEL.md 5.5): written by its text through the
   entry's own string table (`W::s`), read back with `intern_str`. No run's
   id is ever written.
3. **`Scan.owners`** (`province.rs:425`, two `to_vec`s a province) and
   **`Meta.province_owner`** become `(i64, Sym, Sym)`; `report.rs` reads the
   text where it writes (the map's owners, the succession ledgers, the
   wars' owners).
4. **`Market`**: `current`, `history` and `snapshot` on `Sym`; `market.rs`,
   `mod.rs` (the verbose line that counts months).
5. Nothing here may reach an output as an id. The prices and the snapshot
   are sorted by date and good for every output: sort on `names::cmp`.

Keep the first commit of each part to the `Sym` change with the containers
as they are (`OMap<Sym, _>`, `Vec`); flatten afterwards only where the counts
say it pays.

- Verify:
  - the checks;
  - the real campaign: CSVs and decoded payload identical to the reference;
  - once more with `VIC2_ENGINE_NAMES_SHIFT=7`: identical again;
  - mutations: re-aim any that patched code that moved, never drop one;
    add one that sorts the market's goods by id and is caught;
  - the probe (`speed/model-probe.diff`, MODEL.md 1.3) against MODEL.md
    section 4, and `VIC2_TIMES` for the clocks.
- Expected, from the stage shares (estimates, to be replaced by what you
  measure): live allocations after pass one 9.49 M to about 7.0 M; the warm
  rebuild's pass one 0.214 s to about 0.17 s; `map: owners` 0.044 s to about
  0.02 s; the empty-cache run 0.03 to 0.05 s quicker.
- Add INTERNALS.md notes, a bundle, and a `STATUS.md` entry with numbers,
  expected beside measured.

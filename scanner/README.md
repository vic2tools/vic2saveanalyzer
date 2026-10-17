# scanner

The Rust that makes every run of the analyzer: `vic2scan analyze` reads a
campaign's saves, the game and the mod, and writes the nine tables and the
report page. The Python in the repository's root only fills in a run and
relays what this prints (`DEVELOPING.md` has the whole flow).

```
cargo build --release              # from here; the binary is target/release/vic2scan(.exe)
```

No crate dependencies, on purpose: it builds on a machine that has never
reached crates.io. `build.rs` cuts the page out of `../template.py`, builds
it in, and stamps the build with a hash of every source file, which keys the
cache so a new build never reads an old build's entries.

## src/

| | |
|---|---|
| `main.rs` | The modes: `analyze` (every run), and the self-tests and `mod-export`/`mod-signature` the checks call. |
| `province.rs`, `text.rs` | Reading a save's provinces and its pops, fast, from the bytes. |
| `country.rs` | Reading country blocks: everything a nation's row needs, its armies and its fleets. |
| `clause.rs` | A save block as a generic tree, for the parts read that way. |
| `names.rs` | Every name a run meets, interned once as a small number (`Sym`). |
| `fx.rs`, `omap.rs` | The hash every map uses, and a map that keeps insertion order. |
| `deflate.rs` | Deflate, gzip, zlib, CRC-32 and base64, for the page's packed data. |
| `md5.rs` | MD5, for the mod's signature. |
| `jsonr.rs` | JSON in, and out the way the recorded answers were written. |
| `pyfmt.rs`, `pyre.rs` | Numbers formatted, and the mod reader's patterns matched, exactly as the recorded answers expect. |

## src/front/

A run before the engine: what was asked, and of what.

| | |
|---|---|
| `mod.rs` | Reads the run, settles the game and the mod, finds the saves and puts them in date order, and hands the engine its run. |
| `cross.rs` | `--cross`: which folders hold campaigns, which mod each was played on, and the comparison across them. |
| `diagnose.rs` | The questions about saves instead of a report: `--peek`, `--verify`. |
| `pypath.rs` | Paths as the run was given them: `~`, `$VAR`, relative folders. |

## src/engine/

The campaign: from the saves to the report.

| | |
|---|---|
| `mod.rs` | A whole run: reading every save on every core, then finishing and writing. |
| `walk.rs`, `model.rs` | One save read into the typed form the engine holds (`walk.rs` for one laid out unusually). |
| `cache.rs` | A read save kept between runs, keyed by the build and the reading. |
| `modread.rs` | The mod and the game it sits on, read: technologies, inventions, modifiers, the map, flags, names. |
| `rules.rs` | What a mod's rules are worth to one nation: mobilisation, triggers, inventions held. |
| `finish.rs` | A nation once its save is read: its row in every table. |
| `wars.rs` | Every war, put together from the saves it passes through. |
| `market.rs` | The world market across the campaign. |
| `mapflags.rs` | The map's province bitmap and the nations' flags. |
| `report.rs`, `tables.rs`, `dump.rs` | The tables, the page's data, and the page. |
| `explain.rs` | `--explain-mob`, `--explain-mob-pool`, `--inventions`, `--check-inventions`. |
| `dates.rs` | The game's dates as things that sort and plot. |
| `out.rs` | What a run prints, and the protocol lines a host reads beside it. |

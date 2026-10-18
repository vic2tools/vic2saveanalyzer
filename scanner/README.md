# scanner

The Rust that makes every run of the analyzer: `vic2scan analyze` reads a
campaign's saves, the game and the mod, and writes the nine tables and the
report page. The Python in the repository's root only fills in a run and
relays what this prints (`DEVELOPING.md` has the whole flow).

```
cargo build --release              # from here; the binary is target/release/vic2scan(.exe)
```

No crate dependencies, on purpose: it builds on a machine that has never
reached crates.io. `build.rs` joins the report page from `src/page/`, in the
order `src/page/order.txt` gives, builds it in, and stamps the build with a
hash of every source file, which keys the cache so a new build never reads an
old build's entries.

## src/

`main.rs` turns the command line into a mode: `analyze` (every run), and the
self-tests and `mod-export` the checks call.

## src/save/

Reading a save.

| | |
|---|---|
| `province.rs`, `text.rs` | A save's provinces and its pops, fast, from the bytes. |
| `country.rs` | Country blocks: everything a nation's row needs, its armies and its fleets. |
| `walk.rs` | A save not laid out the way the game writes it, read token by token into the same record. |
| `clause.rs` | A save block as a generic tree, for the parts read that way. |
| `names.rs` | Every name a run meets, interned once as a small number (`Sym`). |

## src/py/

Python's behaviour, where the recorded answers depend on it.

| | |
|---|---|
| `fmt.rs` | Numbers spelled as Python spells them. |
| `re.rs` | The mod reader's patterns, matched as Python's `re` matches them. |
| `json.rs` | JSON in, and out the way `json.dumps` writes it. |
| `path.rs` | Paths as the run was given them: `~`, `$VAR`, relative folders. |

## src/util/

| | |
|---|---|
| `fx.rs`, `omap.rs` | The hash every map uses, and a map that keeps insertion order. |
| `deflate.rs` | Deflate, gzip, zlib, CRC-32 and base64, for the page's packed data. |
| `hash.rs` | The two-lane hash that names a mod's signature, the report's stamp and a cache entry's context. |

## src/page/

The report page: `head.html` and `body.html`, the stylesheets in `css/`, and
the script in `js/`, one file per part of the page. The script files are
fragments of one script, joined in order, not modules. Every file here is
named in `order.txt` exactly once, or the build stops.

## src/front/

A run before the engine: what was asked, and of what.

| | |
|---|---|
| `mod.rs` | Reads the run, settles the game and the mod, finds the saves and puts them in date order, and hands the engine its run. |
| `survey.rs` | `--cross`: which folders hold campaigns, and which mod each was played on. |
| `compare.rs` | `--cross`: each campaign read under its mod, and the nations they share compared. |
| `diagnose.rs` | The questions about saves instead of a report: `--peek`, `--verify`. |

## src/engine/

The campaign: from the saves to the report.

| | |
|---|---|
| `mod.rs` | A whole run: reading every save on every core, then finishing and writing. |
| `readsave.rs`, `pool.rs` | One save read (mapped or buffered, scanned or walked), and the threads saves are read on. |
| `model.rs` | One save read into the typed form the engine holds. |
| `cache.rs` | A read save kept between runs, keyed by the build and the reading. |
| `modread/` | The mod and the game it sits on, read: `reader.rs` finds and reads its files, `pieces.rs` has one function per game file, `export.rs` writes the mod as JSON and reads it back. |
| `rules.rs` | What a mod's rules are worth to one nation: mobilisation, triggers, inventions held. |
| `finish.rs` | A nation once its save is read: its row in every table. |
| `wars.rs` | Every war, read off each save and put together across the saves it passes through. |
| `market.rs` | The world market across the campaign. |
| `mapflags.rs` | The map's province bitmap and the nations' flags. |
| `report/` | The campaign walked into the tables (`csv.rs`) and the page: its map and flags (`map.rs`) and its data (`sections.rs`); and what a run says (`say.rs`). |
| `tables.rs`, `dump.rs` | The report's columns and measures, and the JSON the payload's maps are written as. |
| `explain.rs` | `--explain-mob`, `--explain-mob-pool`, `--inventions`, `--check-inventions`. |
| `dates.rs` | The game's dates as things that sort and plot. |
| `out.rs` | What a run prints, and the protocol lines a host reads beside it. |

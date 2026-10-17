# Developing the analyzer

How the code is laid out, how a run flows through it, how to check a
change, and how to make a release. `README.md` is the guide to using it;
`docs/how-it-works/` explains why the numbers come out as they do.

## Where things live

| | |
|---|---|
| `scanner/` | The Rust that makes every run: finding and reading the saves, reading the game and the mod, every number, the tables and the report. See `scanner/README.md`. |
| `template.py` | The report page -- its HTML, CSS and JavaScript -- in one string, cut out and built into the scanner by `scanner/build.rs`. No Python runs it. |
| `vic2_analyzer.py` | The command line. Hands a run to the scanner and relays what it says; `analyze()` is the same for the window, with the report-ready callback. |
| `run.py` | Every setting of a run, declared once, and the command line that fills them. |
| `fastscan.py` | Where the scanner binary is, and how to start it with no console window. |
| `readfolder.py` | The Stop and progress callbacks a hosted run calls, and the scanner's cache folder. |
| `app.py` | The executable's entry: the window, or the command line when given arguments. |
| `gui.py` | The window's report tab: the folder pickers, the log, Analyze and Stop. |
| `mod_reader.py`, `cross.py` | What the window asks before a run: which folder is a game install, where a mod may be read from, which folders hold campaigns. |
| `keeper.py`, `keeper_gui.py` | Keeping every autosave the game writes, and its tab. |
| `savehead.py`, `dates.py` | What the head of a save says, and the game's dates, for the keeper. |
| `publish.py`, `settings.py` | Sharing a report, and what the window remembers. |
| `build_exe.py`, `vic2.ico` | Packing the executable for a release, and its icon. |
| `host/` | An optional place to upload reports to: a Cloudflare worker. See `host/README.md`. |
| `testkit/` | Every check, the recorded answers they are held to, a campaign baseline, and the mutation run. See `testkit/README.md`. |
| `tools/` | The privacy guard run before a push. See `tools/README.md`. |
| `docs/how-it-works/` | What the analyzer had to work out about the game: the map, nations, wars, prices, fleet power, mobilisation, stopping a run, technology. |

## How a run flows

1. **The window or the command line** (`app.py` → `gui.py`, or
   `vic2_analyzer.py`) fills a `Run` (`run.py`): the saves, the game, the
   mod, the output folder and every setting.
2. **`vic2_analyzer.py`** writes the `Run` to a temporary JSON file and starts
   `vic2scan analyze --run FILE` (found by `fastscan.py`). It relays every
   line the scanner prints; a run hosted by the window turns the protocol
   lines (`@progress`, `@ready`, `@done`) into callbacks and never shows
   them.
3. **The scanner's front end** (`scanner/src/front/`) settles the game and the
   mod, finds and orders the saves, answers the diagnostics (`--peek`,
   `--verify`, `--explain-mob`, …) and lays out a `--cross` comparison.
4. **The engine** (`scanner/src/engine/`) reads the mod (`modread.rs`,
   `rules.rs`), reads every save on every core (`walk.rs`, `model.rs`, the
   readers in `scanner/src/`), keeps each read save in its cache (`cache.rs`),
   finishes each nation (`finish.rs`, `wars.rs`, `market.rs`), and writes the
   tables and the page (`report.rs`, `tables.rs`).
5. **The page** is the template with the campaign's data packed into it: one
   `report.html` that works offline.

## Checking a change

```
cargo build --release --manifest-path scanner/Cargo.toml   # after any change to scanner/ or template.py
python testkit/all.py "/path/to/saves" --mod "/path/to/mod" [--baseline ~/vic2-baseline]
```

`python testkit/suite.py --list` lists every check and what it needs. Without
saves, the checks that build their own campaigns still run. Run the suite
after every change; every commit should pass it on its own.

Before changing the engine, record a baseline of a campaign you know
(`testkit/baseline.py record`, kept outside the repository) and compare
against it afterwards: a change meant to leave the numbers alone must leave
every table and the page's payload identical.

A bug fix comes with a check that fails without it, and a row in
`testkit/mutations.py` that puts the bug back. `python testkit/mutate.py`
proves each check still catches its bug: about ten minutes, or eighteen
with a baseline. `testkit/README.md` has the details.

## Making a release

```
cargo build --release --manifest-path scanner/Cargo.toml
python build_exe.py                 # needs PyInstaller: pip install pyinstaller
```

That writes `dist/vic2saveanalyzer.exe`, about 14 MB, with the scanner
inside it and no Python needed to run it. Zip it as `vic2saveanalyzer.zip`
and attach it to a GitHub Release. The executable is not committed.

## Privacy

The repository is public, under an identity kept apart from the people who
work on it. Nothing committed may name them or a home folder: write `~/…`,
`/path/to/saves`, `$VIC2_SAVES`. Run `bash tools/prepush.sh` before every
push; it must print `clean`.

## Rules the code keeps

- The scanner has no crate dependencies, on purpose: it builds on a machine
  that has never reached crates.io.
- The numbers the scanner writes match the Python it replaced, which the
  recorded answers in `testkit/expected/` hold it to. Numbers are formatted
  the way Python formats them (`scanner/src/pyfmt.rs`) for that reason.
- Saves, the game and the mod are read, never written.

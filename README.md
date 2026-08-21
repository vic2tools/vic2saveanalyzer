# Victoria 2 campaign analyzer

Point it at a folder of saves from one campaign and it builds a single HTML
report: every nation's population, literacy, army, navy, industry, technology
and trade over the whole game, a political map with every army on it, and a
record of every war that was fought.

Works with vanilla and with mods, including total conversions.

---

## Getting started

Double-click **`vic2saveanalyzer.exe`**. A window asks for two folders:

| | |
|---|---|
| **Saves folder** | Where this campaign's `.v2` files are. |
| **Mod folder** | The mod's own folder — the one with `common/`, `map/` and `history/` inside. |

Then press **Analyze**. A minute later the report opens in your browser.

Both paths are remembered, so the next run is one click. The box at the bottom
shows progress, and there is a tick to stop it opening the report if you would
rather find it yourself.

### About the mod folder

Give it one. Without it the report loses the map, the technology tree, the great
power ranking and the war goals, and every nation is named by its three-letter
tag instead of its real name. The analyzer reads the mod for country names,
nation colours, the province map, the tech tree, pop types and the rules behind
the mobilization numbers, so a report built without it is a much thinner thing.

For an unmodded game, point it at the Victoria 2 install folder itself.

### Saves must be plaintext

Victoria 2 can write compressed saves. If you get *"does not look like a
plaintext Vic2 save"*, launch the game in debug mode and re-save. The file gets
roughly ten times bigger but becomes readable. Turning debug mode back off and
saving again returns it to normal size.

### How long it takes

About six seconds for a folder of thirty-eight saves, and two after that —
what a save was read as is remembered between runs, so only new or changed saves
cost anything. Saves are read on every core the machine can spare.

---

## Using the report

The report is one HTML file. It needs no server and no internet: open it in any
browser, keep it, mail it, put it on a stick.

Seven tabs across the top, and they share three habits worth knowing:

**Nation pickers.** Anything comparing nations uses a searchable dropdown rather
than a wall of tags. Type to filter by tag or by name, or use the presets:

- **Great powers** — the eight the game itself ranks, at the save being viewed
- **Top 8 by pop**
- **All** / **None**

**Save pickers.** Where a section shows one moment rather than a trend, there is
a **Save** dropdown beside it. The nation picker next to it then offers only the
nations that exist in that save — twenty-one in 1908 rather than the hundred and
twenty-six the campaign has seen. Step back to 1836 and they all come back.

**Sorting.** Click any column heading. Click again to reverse it.

---

## The tabs

### Nations

Opens on the **deployment map**: the political map of the selected save with
every army drawn where the game stacks it, sized by brigade count and coloured
by its nation.

- **Hover** a marker for the province, the nations stacked there, and what they
  are made of — *"Bern, 113 brigades, KUK 85 artillery 71 hussar 14, FRA 28
  artillery 28"*.
- **Click** a marker to pin its readout while you look elsewhere.
- **Scroll** to zoom on the cursor, **drag** to pan, **double-click** to zoom
  in, **Reset** for the whole world.
- **Control / Ownership** switches the shading between who holds ground and who
  owns it, which is what separates a front line from an annexation.
- Narrowing the nation picker strips the map back to the armies you care about.
  The land stays shaded, so the geography does not move under you.

Below it, the **great powers** of that save in the game's own rank order, laid
out as the game lays them out — first to fourth down the left, fifth to eighth
down the right — each with its flag, prestige, craftsmen, factories, brigades
and ships.

Then **Series**: any measure plotted over the whole campaign for the nations you
pick. Population, literacy, brigades, ships, factories, prestige, treasury,
infamy and about twenty more. **Linear/Log** switches the vertical scale, which
is what makes a small nation and a great power readable on one chart.

A dashed line joins a nation to the one it became, so Prussia's line runs into
the North German Federation's and that into Germany's rather than three lines
starting and stopping in mid-air.

Last, **Standing**: the closing table at the final save for the nations you have
selected.

### Pops

**Pops at ⟨save⟩** — every nation with its population, accepted-culture share,
literacy, militancy, consciousness, and a column per pop type. The
**Counts/Shares** button switches the pop-type columns between head counts and
percentages, which is the difference between "who has the most craftsmen" and
"who is the most industrialised".

Click any row to load that nation into the two sections below.

**Cultures** — every culture in one nation at one save, with its size, its share
of the population, and whether the nation accepts it.

**Population composition** — one nation's pop types stacked over the whole
campaign.

### Military

**Head to head at ⟨save⟩** compares two sides. Each side takes a *group* of
nations, so USA and Austria-Hungary against Germany is a single comparison.

- **Totals** — one pie, one slice per side. Hover a side to break its number
  down by member nation.
- **Composition** — two pies split by unit type. Hover a slice and both sides'
  counts for that type are reported together with the ratio between them.
- **Army/Navy** switches both views between land regiments and naval hulls.
- **With mobilization** adds each nation's mobilization ceiling to its brigade
  count, which is the honest measure of what a nation could put in the field
  rather than what it has standing today.

Below that, a sortable overview of the nations you select — brigades, ships,
army and navy tech counts, soldier pops and soldier pops as a share of
population — and a technology matrix listing every army and navy tech in
research order with a column per nation. Those two tables scroll sideways with
the label column pinned, because a column per nation is the point of them.

### Fleets

Three views. **Compare navies** plots one hull type, or all ships, across
nations over time. **Fleets at ⟨save⟩** is a table of every navy with a column
per hull type. **Fleet composition** stacks one nation's hull types over the
campaign. Hull types are read from the save, so mod-added ships appear under
their own names.

### Wars

Every war in the campaign. The table lists who fought whom, when it started and
ended, total casualties, how many battles, how many states changed hands, and
how many of its war goals were met. Search by war name or by any nation in it.

Click a war for the detail:

- **War goals** — every demand the war carried: the one it opened with plus any
  added while it ran. **Taken at the peace** compares who held the state before
  the war against who held it after. **Occupied mid-war** is a different thing
  and says so — the claimant held the state by siege at the moment a save was
  taken, which is a condition during the war, not an outcome.
- **States that changed hands**, with how many provinces of each moved.
- **Land battles** and **naval battles**, separately, each sortable by date, by
  name, or by either side's losses. Every battle shows both commanders and what
  each side was made of.

Battles carry dates where any save still remembered them; a save keeps dates
only on its most recent battles, so older ones are marked undated rather than
guessed at.

### Technology

The mod's own technology tree for one nation at one save, in the game's five
categories, each showing how many of its technologies that nation has. Click any
technology for its bonuses and the inventions it unlocks.

### Market

Price history for every good over the campaign — real monthly history, not one
reading per save, because each save carries three years of it. Below that, the
market snapshot: supply, demand, and how each good's price compares with its
base price.

---

## What you get

Everything lands in the output folder. The report is the point; the CSVs are
there for when you want to do your own arithmetic.

| File | Contents |
|---|---|
| `report.html` | The report. Open it in a browser. |
| `nations_timeseries.csv` | One row per nation per save. The main table. |
| `prices.csv` | Monthly world price per good. |
| `market_snapshot.csv` | Supply, demand and quantity sold per good, per save. |
| `pops_by_type.csv` | Long format: date, tag, pop type, size. |
| `pops_by_culture.csv` | Long format, with whether the culture was accepted. |
| `ships_by_type.csv` | Long format: date, tag, ship type, count. |
| `brigades_by_type.csv` | Long format: date, tag, regiment type, count. |
| `technologies.csv` | One row per nation per technology per save. |

---

## Running it from a terminal

The executable works as a command-line tool when given arguments, and
`vic2_analyzer.py` does the same with Python 3.8 or newer. No dependencies.

```bash
vic2saveanalyzer.exe "C:\path\to\saves" --mod-path "C:\path\to\mod"
```

```bash
python3 vic2_analyzer.py "~/Documents/Paradox Interactive/Victoria2/save games"
```

Useful flags:

| Flag | What it does |
|---|---|
| `-o`, `--out` | Output folder (default `vic2_report`) |
| `--mod-path` | The mod or game folder |
| `--tags ENG FRA …` | Only keep these nations |
| `--min-pop 500000` | Drop microstates |
| `--no-html` | CSVs only |
| `-j 1` | Read saves one at a time instead of on every core |
| `--no-cache` | Re-read every save from scratch |
| `--map-scale N` | Map resolution: 2 is the default, 1 is sharper and bigger, 5 is small and blocky |
| `--peek` | Print the structure of a save and stop |
| `--verify` | Cross-check unit counts against a raw scan of the file |
| `-q` | Quiet |

There are a few more for interrogating the mobilization numbers —
`--explain-mob TAG` and `--explain-mob-pool TAG` print exactly which
technologies, inventions and modifiers produced a nation's figures. `--help`
lists everything.

Saves are ordered by their in-game date, so filenames do not matter.

### Multiplayer

A save records only the nation that saved it. That matters in one place: an
uncivilized nation run by a human gets a mobilization bonus an AI one does not,
so name the human-run nations with `--player-nations TAG TAG` if you want those
numbers exact. Everything else is unaffected.

---

## Accuracy

Where the game's own numbers can be read out of a save, they are: prestige, the
great power ranking, unit counts, populations, prices, war casualties. Where
they cannot, the rule was measured against the game rather than guessed, and
checked against readings from a hundred test nations plus several campaigns.

Two things worth knowing:

- **Mobilization ceilings** are computed, not stored. They match the game
  exactly in nearly every case tested; the misses are single-brigade rounding at
  the boundary.
- **Battle dates** are recovered by reading the whole folder, which dates about
  90% of battles. The rest are shown as undated rather than filled in with a
  guess.

If you want the whole story — how the mobilization rule was measured, which
models failed, what is still not modelled — it is in
[INTERNALS.md](INTERNALS.md).

---

## Building the executable

```bash
python build_exe.py
```

Needs PyInstaller (`pip install pyinstaller`). Writes
`dist/vic2saveanalyzer.exe`, about 13 MB, no Python needed on the machine that
runs it.

## Files

| | |
|---|---|
| `gui.py` | The window: the folder pickers and the log box |
| `vic2_analyzer.py` | Command line, aggregation, CSV output |
| `v2parse.py` | The save-file parser |
| `mod_reader.py` | Reads the mod: names, colours, map, tech, pop types, modifiers |
| `report.py` | Prepares everything the report needs |
| `template.py` | The report's HTML, CSS and JavaScript |
| `tech_groups.py` | Which technologies count as army or navy |
| `build_exe.py` | Draws the icon and packs the executable |

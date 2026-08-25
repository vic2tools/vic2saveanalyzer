# Victoria 2 campaign analyzer

Point it at a folder of saves from one campaign and it builds a single HTML
report: every nation's population, literacy, army, navy, industry, technology
and trade over the whole game, a political map with every army on it, and a
record of every war that was fought.

Point it at a folder of campaigns instead and it reads them all, works out which
mod each was played on, and sets the same nation's run in one game beside its
run in another.

Works with vanilla and with mods, including total conversions.

---

## Getting started

Double-click **`vic2saveanalyzer.exe`**. A window asks for two folders:

| | |
|---|---|
| **Saves folder** | One campaign's `.v2` files — or the folder all your campaigns live in. |
| **Mod folder** | The mod's own folder, the one with `common/`, `map/` and `history/` inside — or `Victoria 2/mod` itself, in which case each campaign's mod is worked out from its own saves. |

A third box says where the report goes. It defaults to
`Documents/Victoria 2 Save Analyzer`, deliberately *not* inside your saves
folder — that folder belongs to the game.

Then press **Analyze**. A minute later the report opens in your browser.

On a first run the saves box is already filled in with
`Documents/Paradox Interactive/Victoria II/save games` if that folder exists,
and **Browse** for the mod opens straight in
`Steam/steamapps/common/Victoria 2/mod`. After that all three paths are
remembered, so the next run is one click.

The box at the bottom shows progress, and there is a tick to stop it opening the
report if you would rather find it yourself.

**Stop** cancels a run. Saves already being read finish first — they are seconds
each — and nothing new is started, so pointing it at a folder of two hundred
campaigns by mistake costs you a moment rather than a coffee break. Every save
read before you stopped stays cached, so starting again picks up where it left
off.

Along the bottom is what that cache currently weighs, and a **Wipe cache**
button. Nothing here expires: an entry is keyed to the version of the program
that wrote it, so every update leaves the previous generation behind unreadable
rather than replacing it, and a long-lived install ends up holding mostly
history. Wiping costs one slow run per campaign and touches neither your saves
nor your reports.

### Several campaigns at once

Point the saves box at the folder your campaigns live in rather than at one of
them, and every campaign underneath is read together. Nothing else has to be
filled in: campaigns are found by looking, and each one's mod is worked out
from its own saves.

Campaigns grouped into folders of their own are found too — the search goes
down through subfolders rather than looking only at the children — so a tidy
saves directory reads the same as a flat one.

A **Campaigns** panel then lists what it found, one row each, with the save
count and a mod. Every row starts on *work it out from the saves*; set one to a
named mod and that campaign is read under it with no guessing at all. Settle the
ones you care about and leave the rest — the two are not exclusive.

Doing that is worth knowing about, because two mods built on the same base can
agree on every country, every technology and every invention a save records,
leaving little to tell them apart. Getting it wrong is not cosmetic: mods that
close agree that closely still disagree about unit stats, so the ships in the
report would be rated against the wrong rulebook.

The marked row is the **main campaign** — the one the map, wars and technology
tree are about, since those can only be about one game. It starts on whichever
has the most saves. The comparison itself covers all of them whichever you
mark.

Two campaigns' saves in one folder is the one mistake worth catching, and it is:
the global event flags a save carries accumulate as a game runs, so an earlier
save's flags are a later save's past, and one holding flags its successors never
had is named in the log as possibly from another game.

### About the mod folder

Give it one. Without it the report loses the map, the technology tree, the great
power ranking and the war goals, and every nation is named by its three-letter
tag instead of its real name. The analyzer reads the mod for country names,
nation colours, the province map, the tech tree, pop types and the rules behind
the mobilization numbers, so a report built without it is a much thinner thing.

For an unmodded game, point it at the Victoria 2 install folder itself.

Reading several campaigns does not change this: name one mod and every campaign
under the folder is read under it, which is what you want when they were all
played on the same one.

You can also decline to choose. Point the box at `Victoria 2/mod` — the folder
mods live in rather than a mod — and each campaign is matched to one by
elimination. A country tag the folder has never heard of, a pop type it does not
define, a technology name it lacks, or an invention index past the end of the
array it builds each rule it out, because a save cannot hold a name the folder
that made it never defined.

The map settles what those cannot, and it settles it by identity rather than by
size: a save carries every province the map defines, so the two are the same set
or the save did not come from that folder. This is what separates mods sharing a
base, where nothing else does. Two PUIR derivatives here agree on all 309
countries, all 150 technologies and all 566 inventions in the same order, and
differ by three provinces.

It is worth getting right rather than nearly right. Those same two mods give the
cruiser different guns, different evasion and different torpedoes, so reading a
campaign under the wrong one of them rates every cruiser 18% low and invents
torpedoes it never had. A wrong answer here does not mislabel the report; it
changes the numbers in it.

Where several still fit, the one whose own country list the campaign comes
closest to exhausting is taken, and the log says the answer was not forced. If
nothing fits at all — usually the right mod at a different version — the closest
is named, loudly, as not matching. Both are judgements rather than measurements:
naming the mod yourself settles it, and doing so reads every campaign in the
folder under that one mod.

A mod is read the way the game reads one: file by file, with the mod's copy
winning and anything it does not ship taken from the Victoria 2 install
underneath. That matters for the partial ones — Divergences of Darkness names
599 of its 658 countries and leaves the rest to the base game, and CE 1v1 ships
two localisation files and no pop types at all. So keep the mod inside
`Victoria 2/mod/`, where the game keeps it, rather than copying it somewhere
else; pointed at a stray copy it can only read what that copy contains.

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

Eight tabs across the top, and they share five habits worth knowing:

**Nation pickers.** Anything comparing nations uses a searchable dropdown rather
than a wall of tags. Type to filter by tag or by name, or use the presets:

- **Players** — every nation somebody was playing. Each save marks them itself,
  so a multiplayer game names all of its players and not only whoever pressed
  save. Absent from single-player campaigns, where it would be one nation.
- **Great powers** — the eight the game itself ranks, at the save being viewed
- **Top 8 by pop**
- **All** / **None**

**Save pickers.** Where a section shows one moment rather than a trend, there is
a **Save** dropdown beside it. The nation picker next to it then offers only the
nations that exist in that save — twenty-one in 1908 rather than the hundred and
twenty-six the campaign has seen. Step back to 1836 and they all come back.

**Sorting.** Click any column heading. Click again to reverse it.

**Names.** Goods, unit types, pop types, technologies and cultures are named the
way the mod names them rather than by the key the save stores. IGoR's `cattle` is
Livestock and its aristocrats are Landowners; Divergences of Darkness has no
Post-Napoleonic Thought but does have Post-Wenceslian Thought. Without a mod
folder there is nothing to read the names out of, so the keys stand in, tidied.

**Charts** carry a mark at each end of a line and nothing in between, and rule
the background at round years rather than at each save. A campaign saved by hand
thirty times and one autosaved every month therefore draw the same chart, rather
than the second one burying its own lines under nine hundred gridlines and four
thousand point markers.

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
- **Play**, and the slider beside it, walk the map through every save in order,
  so a campaign plays out rather than being read one date at a time. The button
  beside Play sets the pace — **1×**, **2×**, **5×** — which is the difference
  between watching a thirty-save campaign and watching a nine-hundred-save one.
  Drag the slider to move by hand; leaving the tab stops it.
- Land is shaded by whoever **owns** it. Ground somebody else is holding is
  hatched diagonally in the occupier's colour on top, so a siege and an
  annexation stop looking the same. The stripes never cross a province border,
  and they cover a third of the ground rather than half, so the owner's colour
  stays the one the eye lands on. **Occupation** turns the hatching off.
- **Hover any land** and the readout names the province, the nation that owns
  it, and the nation holding it if that is somebody else. No pattern can say
  which of two nations owns the ground under a stripe; this can.
- Narrowing the nation picker strips the map back to the armies you care about.
  The land stays shaded, so the geography does not move under you.

Below it, the **great powers** of that save in the game's own rank order, laid
out as the game lays them out — first to fourth down the left, fifth to eighth
down the right — each with its flag, prestige, craftsmen, factories, brigades
and ships.

### Compare

**Data visualizer**: any measure plotted over the whole campaign for the
nations you pick. Population, literacy, brigades, ships, factories, prestige, treasury,
infamy and about twenty more. **Linear/Log** switches the vertical scale, which
is what makes a small nation and a great power readable on one chart.

Two of the measures are rates rather than quantities: **population growth** and
**accepted-culture growth**, both as a percentage a year, compounded between one
save and the one before it. A nation that grew 3% over six months plots at about
6%. Saves less than three months apart are measured across the gap to the next one
far enough away instead, because a fortnight of ordinary growth annualises into
hundreds of percent and would bury everything else on the chart.
Conquest moves population as surely as births do, so a spike is usually a border
moving.

A dashed line joins a nation to the one it became, so Prussia's line runs into
the North German Federation's and that into Germany's rather than three lines
starting and stopping in mid-air.

Below it, **Standing**: the closing table at the final save for the nations you
have selected.

#### Cross-campaign comparison

Present only when several campaigns were read together. One nation, one measure,
one line per game: how did Italy fare in this campaign against the last one?
Every measure the data visualizer offers is here, drawn from the same numbers,
so they mean what they mean above.

Only nations that turn up in at least two of the campaigns are offered — a
nation in one game has nothing to be set beside. Whether there are any depends
on the mods: two builds of the same total conversion share almost all their
countries, while two unrelated total conversions share none at all and the
section has nothing to say.

**Calendar years / Campaign years** decides what the horizontal axis means.
On calendar years each line sits where it actually happened, so two games
overlap only where they really did. On campaign years every line starts at zero,
which is the fair way to ask how two runs developed, since campaigns rarely
begin on the same date or run the same length. Under the chart, the last moment
every campaign still covers is stated with each one's value there — comparing
the closing figures instead would be comparing 1894 against 1874.

Hovering reads every campaign at once. They save on different days, so a value
marked **·** is that campaign's most recent reading at or before the line rather
than one taken on it.

A few measures are marked **†**. Those are not read off a save: they are worked
out from a mod's own technologies, inventions and modifiers, so two campaigns on
two mods answer them from different rulebooks. They are still worth asking
about — a mobilization ceiling is a real fact about a game — so they are shown
with that said plainly rather than left out.

### Pops

**Pops at ⟨save⟩** — every nation with its population, accepted-culture share,
literacy, militancy, consciousness, and a column per pop type. The
**Counts/Shares** button switches the pop-type columns between head counts and
percentages, which is the difference between "who has the most craftsmen" and
"who is the most industrialised".

Click any row to load that nation into the two sections below.

**Cultures** — every culture in one nation at one save, with its size, its share
of the population, and whether the nation accepts it. Cultures are named the way
the mod names them, not by the key the save stores: IGoR's China is South Han and
North Han, not `nanfaren` and `beifaren`. Without a mod folder there is nothing
to read the names out of, so the keys stand in.

**Population composition** — one nation's pop types stacked over the campaign,
one bar a year taken from the last save in each. A year is the unit a population
is read in, and it is what keeps the chart the same whether the campaign was
saved thirty times or every month.

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

#### Fleet power

Hulls are not interchangeable: five frigates are not a cruiser. In **Navy** mode
each side also carries a **fleet power**, which sits beside the ship count rather
than replacing it — the two disagreeing is the interesting part.

One hull is worth

    gun power × hull ÷ (1 − evasion)

which is what falls out of asking who out-damages whom. Two ships trading fire
deal damage in proportion to their own gun power and in inverse proportion to the
other's hull, and evasion throws away a share of the ticks aimed at it; move each
ship's terms to its own side of that comparison and this is what is left. It adds
up over a fleet, so a side's total is a number you can divide. The reading is
Boltun's, from his guide to navies, and it reproduces his figures exactly: a
frigate at 16 per naval point, a man-o'-war at the same, both before any
technology.

Stats come from the mod's own `units/` files and are upgraded by the inventions
each nation actually rolled, so the same hull type is worth more to a nation that
researched further — in one campaign here Britain's battleship reads 4,453 and
Germany's 4,200. Torpedoes work only against big ships, so where any are carried
a second figure is given for a fight against heavy hulls. **Composition** adds
what one hull of each type is worth to each side, and each side's total under its
pie. Without a mod folder there are no unit files and the measure is unavailable.

That figure rates the ships as *designed*, at full strength and no experience,
which is what makes it comparable between nations and across a campaign.
Underneath it, **at current strength** is the same fleet as the save finds it:
the damage a hull deals runs with its strength, and the damage it takes runs
against its experience, so a battered fleet fights below its paper figure and a
veteran one above. It matters more than it sounds — in the campaigns here it
moves individual navies by anywhere from −34% to +25%, and changes who ranks
where. Both are shown rather than one replacing the other, so a fleet somebody
has stopped paying for still shows what it would be worth repaired.

Below that, a sortable overview of the nations you select — brigades, ships,
army and navy tech counts, soldier pops, soldier pops as a share of population,
and the same share counting only soldiers in the nation's own states. A colonial
soldier pop raises no brigade, so that last column is the part of the soldier base
an army can actually be built on: Britain reads 3.98% on the plain measure and
1.82% on this one. Then a technology matrix listing every army and navy tech in
research order with a column per nation. Those tables scroll sideways with the
label column pinned, because a column per nation is the point of them.

### Fleets

Three views. **Compare navies** plots one hull type, or all ships, across
nations over time; the axis covers the years anybody actually had that hull, so
a battleship chart starts at the first one launched instead of spending two
thirds of its width on the decades before the type existed. **Fleets at ⟨save⟩**
is a table of every navy with a column per hull type. **Fleet composition**
stacks one nation's hull types over the campaign, one bar a year. Hull types are
read from the save and named the way the mod names them, so mod-added ships
appear under their own names.

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
reading per save, because each save carries three years of it.

Below that, the market snapshot: supply, demand, how each good's price compares
with its base price, and two columns about gluts. **Unsold** is the share of that
day's supply that found no buyer at all. **Pegged** marks a good whose recorded
demand runs to something on the order of a billion — a standing order to buy
without limit, which some mods hand a nation so that raw materials always sell.
Every pegged reading in the campaigns this was checked against sits at exactly
five times the good's base cost, the engine's price ceiling, so for those goods
neither price nor demand reports on scarcity and only **Unsold** still does.

Last, **Who produces it**: for one good at one save, every nation's own
contribution to the world supply, biggest first. Summed over every nation it
comes back to the market's supply pool, so these are shares of the same quantity
the price responds to. That is what names the nations behind an overproduced
good. Clicking a row in the table above brings that good's producers up here.

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
| `ships_by_type.csv` | Long format: date, tag, ship type, count, and the same ships at the strength the save finds them in. |
| `brigades_by_type.csv` | Long format: date, tag, regiment type, count. |
| `technologies.csv` | One row per nation per technology per save. |

The report is one file with everything in it -- the map, the flags, every
number -- and it is small enough to send: a thirty-eight-save campaign comes to
about 2 MB. The data inside it is compressed, so any browser from 2023 onwards
will open it and older ones will say so rather than showing you an empty page.
Nothing needs to be installed and it does not need a web server; open it off the
disk. Everything is also on `window.campaign` if you would rather read it out of
the console.

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
technologies, inventions and modifiers produced a nation's figures.

Two more read the inventions themselves. `--inventions TAG` prints every
invention the last save says that nation has discovered, which is a list you can
hold against the game's own technology screen. `--check-inventions` takes a
folder of saves instead and grades the decode against those saves rather than
against the mod folder: an invention gated behind a technology should be held
almost only by nations that have that technology, so its holders fingerprint the
gate it came through and a campaign can mark its own reading. `--help` lists
everything.

Four more read a folder of campaigns rather than one. `--cross` treats the
saves path as a folder of campaign folders; `--game-root` says where the mods
live, so each campaign can be matched to one; `--campaign-mod "NAME=PATH"`
names the mod for one campaign outright and can be repeated, with anything
unnamed still worked out; `--primary NAME` picks which campaign the rest of the
report is about, instead of whichever has the most saves.

```bash
vic2saveanalyzer.exe "C:\path\to\campaigns" --cross --game-root "C:\path\to\Victoria 2"
```

Saves are ordered by their in-game date, so filenames do not matter.

### Multiplayer

Every country somebody is playing carries a `human = yes` marker in its own
block of the save, so a multiplayer campaign is read without being told anything:
the **Players** preset in each nation picker and the **Player** column in the
standing table both come from it, and so does the mobilization bonus an
uncivilized nation run by a human gets and an AI one does not.

`--player-nations TAG TAG` overrides that list, for a save whose markers are
missing or a campaign where somebody handed a nation over.

---

## Accuracy

Where the game's own numbers can be read out of a save, they are: prestige, the
great power ranking, unit counts, populations, prices, war casualties. Where
they cannot, the rule was measured against the game rather than guessed, and
checked against readings from a hundred test nations plus several campaigns.

Four things worth knowing:

- **Mobilization ceilings** are computed, not stored. They match the game
  exactly in nearly every case tested; the misses are single-brigade rounding at
  the boundary.
- **Mobilisation size** adds up every source the mod has: technologies,
  inventions, national values, reforms, event modifiers, the flat penalty an
  uncivilized nation carries, and triggered modifiers — which are re-evaluated
  by the game every day and written into the save nowhere, so their conditions
  have to be read and judged. Where a condition is one the analyzer cannot
  answer, the modifier is left out rather than guessed at, and
  `--explain-mob TAG` names which ones those were along with every source that
  did count.
- **Inventions** are stored as bare numbers — positions in an array the
  engine builds when it loads and writes down nowhere. That array is rebuilt by
  reading the mod's `inventions/` folder the way the engine reads it, and the
  result was confirmed against the game: inventions watched as they fired in a
  live campaign decoded to their exact names, out of index order. Each campaign
  also grades its own decode without the mod folder having to be trusted, which
  is what `--check-inventions` reports.
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
| `cross.py` | Finds campaigns, works out which mod each was played on |
| `report.py` | Prepares everything the report needs |
| `template.py` | The report's HTML, CSS and JavaScript |
| `tech_groups.py` | Which technologies count as army or navy |
| `build_exe.py` | Draws the icon and packs the executable |

---

## Licence

**GNU Affero General Public License v3.0.** The full text is in
[LICENSE](LICENSE).

In plain terms, you may use this for anything, change it, and pass it on. What
you may not do is take it private. If you distribute a modified version, or run
one as a service other people use, you have to give them the source under this
same licence.

That is the deal in both directions: nobody can wall this off behind a paywall
or a login and keep the improvements to themselves, and by the same token
anything you build on it stays available to everyone who comes after. Selling
copies is not forbidden and never has been under this kind of licence — it is
simply futile, because whoever buys one gets the source with it and may give it
away.

### A note on game files

The analyzer ships no Victoria 2 content. It reads the game and mod files
already on your machine, and the reports it generates embed things drawn from
them — nation flags, the province map, country and state names. Those belong to
Paradox Interactive and to the mod's authors, not to this project and not to
you. Keep that in mind before publishing a generated report somewhere public;
sharing one with the people you played the campaign with is a different matter
entirely.

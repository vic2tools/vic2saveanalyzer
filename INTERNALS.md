# How it works

Everything the analyzer had to work out for itself, and what it cost to work it
out. The README next door is the guide to using the tool; this is the record of
why it does what it does -- which rules were measured against the game, which
guesses failed and how, and what is still not modelled.

None of it is needed to use the analyzer. It is here because the alternative is
re-deriving it, and because several of these were wrong in ways that looked
right for a long time.

## The deployment map

With `--mod-path` the **Nations** tab opens on a map: a political map of the campaign
with every army drawn where the game stacks it, sized by brigade count and
coloured by its nation, using the nation colours out of the mod's own
`common/countries/*.txt`. Hovering a marker names the province and breaks the
stack down by nation and unit type — "Bern, 113 brigades, KUK 85 artillery 71
hussar 14, FRA 28 artillery 28".

It is built to stay light enough to carry every save in a campaign:

- The province bitmap is 5616x2160 and 36 MB. It ships as a run-length encoded
  grid of province ids at half scale -- 2808x1080, about 660 KB of base36 text.
  Only sampled rows are read, so building it costs a fraction of a second rather
  than the minute a full decode would take.
- One raster serves every save. Only ownership changes, and that ships as a
  delta against the previous save: an 1836 base of 2,297 provinces is followed
  by a few hundred changes per snapshot.
- Occupation rides along as a full list each save, because it is a couple of
  dozen provinces rather than thousands. The **Control** button switches the
  shading between who holds ground and who owns it, which separates a front line
  from an annexation.

Roughly 300 KB for two saves. Narrow the nation list to strip the markers back
to the nations you care about; the land stays shaded so the geography does not
move under you.

**The hole in the Tibesti.** Victoria 2 paints about 8,000 pixels of northern
Chad into `provinces.bmp` in a magenta -- RGB 208,17,223 -- that `definition.csv`
never names, and it is the only unnamed colour on the map. Vanilla has it, and so
does every mod built on the vanilla bitmap. It is drawn as unclaimed land and
left that way. Filling it from its neighbours was tried and reverted: the map
would have shown someone owning ground nobody owns, which is worse than a blank
patch that matches what the game itself shows.

**Nations are drawn in their own colours.** Tags, chart lines and picker
swatches take the colour the mod gives the nation in `common/countries/*.txt`,
so the report reads like the game. About a third of them are unusable as ink on
a burgundy page -- Prussia ships a near-black navy, Russia a bottle green -- so
each is checked against the ground and lifted only if it fails, keeping its hue
and moving its lightness until it clears a contrast ratio of 3.4. Saturation is
floored so near-greys do not wash out and capped so a fully saturated dark comes
up as ink rather than neon. On one campaign 91 of 126 nations keep their exact
game colour and the worst contrast on the page is 3.42. The map itself is
untouched: it paints the raw colours, because there it is the map.

**Nations in a picker are the ones in the save.** Anything read at one date --
the tech tree, the culture table, the force comparison, the map -- offers only
the nations that hold land in the save selected beside it, which on a late save
is twenty-one rather than the campaign's hundred and twenty-six. The options are
hidden rather than removed, so stepping back to an earlier save brings them
straight back with the selection intact. Anything plotted across every date
keeps the full list, because a nation that ended in 1860 still has a line worth
drawing.

**Zoom and pan.** Scroll to zoom on the cursor, drag to pan, double-click to zoom
in, **Reset** for the whole world. Markers grow more slowly than the map, so a
crowded theatre thins out as you go in rather than turning into one blob: at
6.8x only 88 of 371 stacks are on screen. Click a marker to pin its readout while
you look elsewhere. The political map is painted once per save into an offscreen
canvas and blitted at whatever zoom is in force, so panning does not repeat the
per-pixel work.

One trap worth recording. The province bitmap declares a positive height, which
in a BMP means the rows are stored bottom-up, but this one is stored top-down:
file row 168 holds Sitka, whose own position is 168 rows from the top. Trusting
the header puts Alaska in the southern ocean. Check orientation against a
province you can place rather than against the spec.

`--map-scale` trades size against sharpness, and it is a one-off cost however
many saves are in the report: the default 2 gives 2808x1080 for about 660 KB, 3
gives 1872x720 for 410 KB, 5 gives 1123x432 for 230 KB and is visibly blocky
once you zoom, and 1 is the map at native resolution for 1.4 MB. Decoding half
scale takes 24 ms and the first paint 38 ms; native quadruples both. Without
`--mod-path` there is no bitmap to read and the tab is dropped rather than shown
empty.

Two traps, both recorded because each cost an afternoon. The bitmap declares a
positive height, which in a BMP means bottom-up rows, but this one is stored
top-down -- file row 168 holds Sitka, whose own position is 168 rows from the
top -- so trusting the header puts Alaska in the southern ocean. And the canvas
needs an explicit CSS size: without one it falls back to its `width`/`height`
attributes, which are the raster's, and a 2808px canvas bursts straight out of
the page.

### One column, as wide as the window

The sheet was 1180 pixels wide, chosen when the widest thing on it was a
paragraph. What is on it now is mostly a twenty-column table, a chart or a world
map, and on an ordinary 1080p screen that left a third of the window empty on
either side. It is `min(1800px, 96vw)` instead.

A `max-width` only ever gives room back, so this costs a small screen nothing:
at 1366 the sheet is 1311 and at 3840 it stops at 1800 rather than becoming a
two-thousand-pixel wall of text. `vw` rather than `%` because the sheet is the
page's only column, and the 4% left over covers the scrollbar `100vw` counts and
`clientWidth` does not.

The map briefly had a `.bleed` rule stepping it out of the column and across the
whole window, on the grounds that the world raster is 2.6 times as wide as it is
tall. It looked wrong for a simpler reason than any of that: a map wider than
the sheet it sits in reads as a mistake, whatever its aspect ratio. Widening the
column and leaving the map inside it gets the same map at the same size with
nothing sticking out.

The notes under each figure were given a reading measure of their own for a
while, on the grounds that prose runs to two hundred characters a line at 1,700
pixels. It looked worse than the long line did: a paragraph that stops half a
screen short of the chart it is explaining reads as text that has been cut off.
Everything in the column is now the width of the column.

### Occupation is drawn over the map, not into it

Shading a province in the colour of whoever is holding it made a siege and an
annexation look identical, so land keeps its owner's colour and occupied ground
is hatched diagonally in the occupier's on top.

The hatching is a mask applied on the screen rather than stripes painted into
the raster. The raster is 5,616 pixels wide and the panel is about 1,100, so a
stripe baked into it at a width that reads at zoom 1 would be half a province at
zoom 24 -- the hatching would grow with the map instead of staying a texture on
it. So `mapPaintBase` builds a second canvas holding only the occupied
provinces, in the occupier's colours, everything else transparent; each frame
that layer is drawn into a screen-sized scratch canvas, masked with
`destination-in` against a repeating 9-pixel diagonal tile, and blitted over the
map. The tile is built once from an `ImageData` where alpha follows
`(x + y) % 9`, which wraps cleanly at the tile edge so the stripes join up.

Two canvases rather than one because `destination-in` eats everything already on
the canvas it runs on, and the map underneath has to survive.

Two things keep the owner readable under all that. The occupation layer skips
every pixel the edge mask marks, so province borders are never hatched over --
without that, a stripe of occupier colour ran straight across the line between
two provinces and it became a guess which one the ground belonged to. And the
stripes cover three pixels of the nine-pixel tile rather than five: the occupier
has to be legible, but it is the owner's province and the owner's colour should
still be the one the eye lands on.

Neither is a substitute for saying it outright, so hovering any land names the
province, its owner and whoever is holding it. `mapProvinceAt` is the painting's
own lookup run backwards -- screen point to map pixel to `mapProv[y * w + x]` --
which round-trips exactly at every zoom from 1 to 24, and costs one array read
per pointer move. An army marker still wins the readout when the cursor is on
one, and it now carries the same two lines above its brigade count.

### Playing the campaign back

A run of saves is a campaign in the order it happened, and the only way to watch
it move used to be picking each date in turn. The slider beside the save
dropdown is the same choice by another route -- both set the save and go through
`mapSave.onchange`, so the picker, the great power panel and the readout stay in
step -- and **Play** walks it, at 250 ms a frame, or half or a fifth of that
under the 1x/2x/5x button beside it. A repaint costs about 120 ms and the picker
refresh doubles it to roughly 300 ms, so even first gear is asking for frames
faster than they can be drawn. What is waited is the rest of the frame's slot
rather than the whole slot on top of the drawing, so 1x is a quarter of a second
a frame and not a quarter of a second plus however long the frame took -- which
is the difference between a third of the old pace and half of it.

That is why each frame books the next one after it has finished drawing rather
than every frame being booked in advance on an interval. An interval would keep
firing while the previous frame was still painting and the queue would run away
from the machine; a chain of timeouts simply plays back as fast as the machine
manages, which is the failure worth having -- and it is what makes asking for
50 ms a frame at 5x a reasonable thing to do rather than a way to hang the tab. Pressing Play while sitting
on the last save rewinds to the first, and leaving the tab stops the timer,
since a slideshow nobody is looking at is just work.

## One nation becoming another

The **Data visualizer** joins a nation to the one it became with a dashed line, so
Prussia's population does not simply stop in 1860 while Germany's begins out of
nowhere in 1870.

A save records none of this. A nation that formed another leaves a block holding
only its diplomatic relations -- no successor field, no event log -- and the
decision that does the forming leaves no mark either: `form_italy` changes the
tag, swaps the cores and inherits the other Italian states, and the file that
forms Germany, Italy, Scandinavia and Romania sets exactly one country flag
between them, about Finland. The one formation flag that does survive, IGoR's
`dual_monarchy_done`, sits on Austria-Hungary, because a country carries its own
flags through a tag change -- which tells you the nation is the product of a
decision without telling you what it used to be.

Two sources do know, and they are used together:

- **The mod's own decisions** declare who may form what. A decision whose effect
  is `change_tag = ITA` and whose `potential` is `tag = SAR OR tag = SIC` says
  Italy is formed by Sardinia-Piedmont or the Two Sicilies. IGoR declares 15
  such tags, DoD 42.
- **The province ledger** says which of them happened here: the newcomer appears
  holding land the old nation held one save earlier, and the old nation holds
  none any more.

A predecessor has to disappear as the newcomer appears, having handed over most
of what it owned, and be either named by a decision or of a culture the newcomer
accepts. Without the first test Austria-Hungary would read as *becoming* Hungary
in 1906 when it merely released it, and the Confederacy as replacing the United
States. Without the last, a conquest that happened inside the same window --
saves are years apart -- reads exactly like a formation, which is what would
otherwise have Tibet becoming a Dzungar khanate.

Nations matched by culture rather than by a decision are starred in the note
under the chart: releases and event formations are in no decision file.

## Great powers

Below the map, the eight great powers of the selected save, arranged as the
game arranges them -- first to fourth down the left, fifth to eighth down the
right -- with their flag, prestige and craftsmen.

Both come straight out of the save. A save carries a `great_nations` list --
eight 1-based indices into the country array `common/countries.txt` defines --
and it is the game's own ranking: across this campaign Turkey drops out between
1888 and 1908 and the United States enters, and the order is not prestige order
(Italy outscores Britain on prestige in 1908 and still ranks second). `prestige`
is a top-level country field, read directly.

That array is `common/countries.txt` with its repeats dropped. A mod can name
the same tag twice -- Divergences of Darkness lists eight, ARC and AZL among
them -- and the engine keeps only the first, so counting the file as written
puts every index past the first repeat out by however many came before it. In
DoD that turned eight real great powers into five tags the campaign has never
heard of, each with an empty row beside it, because the wrong tags are not in
the save to have statistics. De-duplicated, the list matches the order a save
writes its own country blocks in, tag for tag, at 658 of 658 -- which is the
engine's array by definition. `common/countries.txt` also drives the party list
`ruling_party` indexes into, so the same repeats were shifting war policy and
mobilisation impact for every country past the first one.

Flags come out of the mod's own `gfx/flags/*.tga`, converted to PNG and inlined
as data URIs -- about 2.4 KB a flag, 26 KB for a campaign, and 10 ms to decode.
Which variant a nation flies mostly follows `flagType` in `governments.txt`, so a
communist Russia flies the communist flag, and one image is kept per tag and
variant rather than per save. Which file a nation flies is fitted to what the game displays rather than to
`flagType`, which cannot be the whole story. In one 1908 save Germany and Japan
share a government (HM's Government) *and* a ruling party ideology
(reactionary) and still fly different files, and a democratic United States
under a communist party flies the plain national flag rather than the communist
one. Seven of that save's eight great powers fly the plain `TAG.tga`; only an
autocracy -- `flagType = monarchy` with no elections -- reliably takes a
variant, and a communist or fascist government takes its own.

Germany is a standing exception: the game shows it black-red-gold, which is
`GER_republic.tga`, and nothing in the files separates it from a Japan flying
the Hinomaru under the same government and the same party. It is left wrong
rather than special-cased on a guess.

**Industrial and military score are not in a save.** Nothing resembling them
appears in any country block or anywhere else in the file; the engine derives
both at runtime. Rather than print a guess beside two exact numbers, the cards
carry the real quantities instead -- factory levels, brigades and ships -- all
of which are counted from the save. If you want the game's own two numbers they
have to be read off the in-game ledger.

### States come from the first region that claims a province

`map/region.txt` is meant to be one entry per state, but a mod can keep other
things in it: DoD ends the file with `MET_1`, a metaregion naming almost every
province on the map. Reversing the file into a province-to-state mapping without
a rule for repeats handed all 2,704 provinces to that one entry, and every state
in the war tab came out as "Earth". A province now belongs to the **first**
region that claims it, the same rule the country array follows, which leaves
mods without metaregions untouched -- IGoR reads 528 regions either way.

### Charts that survive a monthly autosave

Every chart here used to be drawn against the saves themselves: a vertical rule
and a date label per save behind the lines, and a small square on every reading.
At thirty hand-made saves that reads as a calendar. At an autosave a month it is
nine hundred rules a pixel apart behind the very lines they are there to help
read, and four thousand squares threaded onto eight of them.

So the two were separated. The background is ruled at round years -- the step is
the first of 1, 2, 5, 10, 20, 25, 50 that leaves each label about 74 pixels,
which is why no thinning pass is needed afterwards -- and the markers are drawn
only at the two ends of each line. The ends are the one thing a line cannot say
for itself: where this nation's run of data begins and where it stops, which on
a chart full of nations that come and go is worth more than a box on every
reading in between. A series with a single reading has no line at all, so its
one marker is the whole of it and is drawn once rather than twice.

Hovering is unaffected. The rules are years but `hoverXs` is still the saves, so
the readout snaps to real dates and reports what was actually recorded.

The stacked charts -- fleet composition, population composition -- cannot thin a
bar the way a line chart thins a gridline, since the bar is the data. They keep
the last save in each year and drop the rest. A year is the unit a population is
read in, and the totals printed over the bars and the years printed under them
are then handed out by the same greedy pass, so a label is drawn only where it
clears its neighbour, with the final bar always keeping its own.

### A hull the campaign has not invented yet

**Compare navies** plots one hull type across nations. Plotted against the whole
campaign, a battleship chart in a run starting in 1836 is two thirds empty floor
and one third data, because nobody launched one until 1882.

The axis is therefore built from the plotted points rather than from the
campaign: it runs from the first save anyone held that hull to the last, with
two percent of the span as padding. Taking it off the data rather than off the
tech tree covers the other end too -- a hull every navy has since scrapped stops
the axis where the last one was scrapped, instead of trailing off flat -- and it
needs nothing from the mod, which is what makes it work on a report built
without one. `hoverXs` is filtered to the same window so a hover cannot land
outside the plot.

### Names come from the mod, not from the key

A save writes a good, a unit type, a pop type, a technology and a casus belli as
a bare key: `cattle`, `clipper_transport`, `aristocrats`,
`post_napoleonic_thought`. Tidying the underscores out is not translation --
IGoR calls `cattle` Livestock and `aristocrats` Landowners, and Divergences of
Darkness renames Post-Napoleonic Thought to Post-Wenceslian Thought.

All five are ordinary localisation keys sharing one namespace, so
`display_names` gathers the keys from `common/goods.txt`, `poptypes/`, `units/`,
`technologies/` and `common/cb_types.txt` across base game and mod, and looks
all of them up in one pass. `text_localisation` reads the mod first and the base
game after it with the first definition winning, so a mod's rename wins and a
partial mod still gets the game's names for what it left alone.

Country names took longer to get there. `read_localisation` read the mod folder
and stopped, which is fine for a total conversion and wrong for everything else:
Divergences of Darkness names 599 of its 658 tags and leaves Denmark, Norway,
Sweden, Belgium and 55 more to the game underneath, and CE 1v1 ships two
localisation files and inherits the rest. Those tags came out as bare three-letter
codes. It now reads both roots on the same first-wins rule as everything else,
and the count of nations with no name at all went 59 to 1 on Divergences and 77
to 0 on CE -- the one that remains, CHR, is not named anywhere.

The lists a reader scans alphabetically -- the goods dropdown, the goods picker,
the hull dropdown -- are sorted by the name they show rather than by the key
behind it, or Livestock would sit under C. The same goes for sorting the market
table by good, which is what `renderTable`'s `sortBy` is for.

### A mod is a layer over the game, not a replacement for it

Victoria II resolves a mod file by file. `units/frigate.txt` in a mod replaces
the game's; a file the mod does not ship is inherited whole. Half of this
program's readers followed that rule and half looked only in the mod folder,
which is a bug that hides well -- most mods override most things, so it only
shows on the file a particular mod happens not to ship.

What it was actually costing, across the seven mods installed here:

| | |
|---|---|
| `localisation/` | 59 nameless tags on Divergences of Darkness, 77 on CE 1v1 |
| `poptypes/` | CE 1v1 read **none** of the twelve; three mods missed `slaves` |
| `decisions/` | CE 1v1 saw 1 file of 30, Ferrum Mare 44 of 73 -- no formations |
| `common/issues.txt` and its neighbours | nothing yet, but one file away from it |

`_resolved_files` does folders and `_resolved_file` does the single files, and
between them every reader now goes through one of the two. Two of them are
order-sensitive and were checked rather than assumed: no mod here borrows a
single `technologies/` or `inventions/` file, so the invention array the save's
indices point into is byte-for-byte what it was.

### One run must not leave its pop types for the next

`register_pop_types` folded the mod's own pop types into a module-level set so
`read_province` would keep them. It only ever added. The window runs one
campaign after another inside the same process, so analyzing IGoR and then
Divergences of Darkness read IGoR's `bankers` out of Divergences saves -- Jan
Mayen came back 16,482 bankers under a mod that has no such pop type -- and then
wrote that answer into the parse cache under a key computed from the mod's
declared types, which said it had not.

It is set from scratch now, from the twelve the game ships plus the mod's own,
and the cache key is taken from the set the parse will actually use rather than
from the set the mod declares. The regression test runs Divergences alone, then
after IGoR, then after a no-mod run, and requires all three tables to be
byte-identical.

### Who was playing

Each country a person is playing carries `human = yes` as the first line of its
own block. That is every player in a multiplayer game, not just the one who
pressed save, which is all `meta["player"]` ever gave -- and the difference is
thirty-one nations against one in the campaigns this was built on.

It matters twice: the **Players** preset and the **Player** column are read off
it, and so is `player_unciv_mobilization`, the bonus an uncivilized nation gets
for being run by a person. `--player-nations` still overrides the lot, and the
save's own player is still the fallback for a save with no markers at all.

### Nothing scrolls sideways

The war tables are read, not scrubbed, so they are laid out to fit the page
rather than to fit their content. Two changes did it.

The belligerent list under a war keeps its `A B C v D E F` reading order but
wraps inside its column instead of stretching the table -- the widest war in one
campaign lists thirty-one nations, which was pushing every other column off the
right of the screen.

And each side of a battle became a column of its own: the nation, then who led
it, then one line per unit type. Laid out across, as `Herbert Kitchener ·
artillery 172539, infantry 91352, hussar 31494, cuirassier 5652`, a single
battle was wider than the window, which put the two sides so far apart that
nobody could compare them without dragging. Stacked, both sides and both
casualty columns sit inside one screen.

## Wars

Every war in the campaign, its battles, and what it actually took.

Battles are split into land and naval by the unit types present, read from the
mod's own `units/*.txt`, and every column of both tables sorts -- including each
side's losses, so the costliest engagement of a war is one click away. Land that
changed hands is reported by state rather than province: five names under Tabriz
is one line, not five.

**Battle dates take the whole folder.** A save dates only its most recent
battles and drops the dates from older ones -- the 1908 save can date 33 of its
1,310. Reading all 38 saves lifts that to **1,217 of 1,359, about 90%**, because
each save catches a different window and the windows tile the campaign. What is
still undated is shown as unknown.

The obvious shortcut does not work. Scanning the file and stamping each battle
with the last date seen -- which is what the one other tool of this kind does --
is **3% correct here**: in a finished war the battles are written *before* the
dated events, so every battle inherits a date from the war above it in the file.
Three battles of Dresden come out as 1836.8.25 against a true 1836.9.13,
1836.9.18 and 1836.9.26; Gharyan lands eleven months out.

**War goals are read, not inferred.** A war carries more than one demand: the
one it opened with plus any added while it ran, each naming a claimant, a target
and a state. Added demands are dropped when the war ends, so like battle dates
they survive only in a save taken while the war was live -- 52 of 270 wars here.

Those demands carry an `is_fulfilled` flag, and it is worth being clear about
what it is not. It means the claimant held the state **by siege at the moment
that save was taken** -- a live condition, not the peace. Across the goals where
both a flag and a territorial answer exist, the two agree only **44%** of the
time, and 26 goals were occupied mid-war and took nothing at all. So the report
shows them as separate columns: *taken at the peace*, from who owned the state
either side of the war, and *occupied mid-war*, from the flag.

This matters more than it sounds. The French Conquest of Friesland looks like a
Franco-Prussian affair, and its original goal is exactly that. Caught mid-war in
an 1857 save it turns out to carry three demands, the third an American claim on
Mexico for Georgia -- which is why Atlanta, Savannah and four more provinces
change hands in a war named after a Dutch province. All three demands read as
occupied; only that third one took anything.

## Speed

A campaign folder is 38 saves of 44 MB each, and reading them used to be the
whole runtime. Measured on the same folder and the same machine, 32 logical
cores:

| 38 saves, 1.28 GB | | |
|---|---|---|
| first run, one core | 63 s | where this started |
| first run, one core | 40 s | once pops stopped being built and thrown away |
| first run, one core | **21 s** | once the parse stopped being a token walk |
| **first run** | 6.1 s &rarr; **4.1 s** | on as many cores as the machine has |
| **every run after** | 3.0 s &rarr; **2.7 s** | the saves come back from the cache |

Four things got it there.

**Saves are read in parallel.** They do not depend on each other, so the only
thing in the way was that a worker needs the same two pieces of state the mod
sets up -- which pop types exist and which of them can be mobilized -- and
Windows starts workers with a fresh interpreter. Both are handed over before a
worker touches a save. How many workers is the machine's business: one per core
bar one, no more than there are saves left to read, and bounded by free memory,
because a worker peaks at about two and a half times its save (114 MB for a
46 MB file). `-j N` overrides it; `-j 1` reads them one at a time. Anything
already cached is loaded in the parent, since a process started to do that would
cost more than it saves. On this machine: 63s on one core, 13s on eight, 8.5s on
sixteen, 7.3s on twenty-four -- it keeps paying past the physical core count,
just less.

**Pops skip what nothing reads.** Every pop carries an `ideology` and an
`issues` sub-block -- six ideology numbers and sixteen party-support numbers --
against the seven fields that are actually used. They were being parsed into
dictionaries and thrown away. Skipping them at the brace took a save from 2.0 s
to 1.4 s and dropped the tokens read from 5.2 M to 3.0 M. The scan that replaced
the walk does not so much skip them as never look: see below.

**The parse reads the layout rather than every token**, which is the largest
single change and has a section of its own below.

**The map is decoded once.** `provinces.bmp` is 5616x2160 and decoding it cost
half a second on every single run, so the result is cached beside the saves,
keyed by the two files it comes from and the scale. The decode itself also got
twice as fast: a pixel is looked up by slicing three bytes out of the row rather
than unpacking them into a tuple, and since provinces are contiguous a pixel
almost always repeats the one to its left, which skips nine lookups in ten.

The cache key is the save's path, size and timestamp, **a hash of the parsing
code**, and **which mod it was read under**. The first expires every entry the
moment `vic2_analyzer.py` or `v2parse.py` changes -- the one version counter
nobody forgets to bump. The second matters because a save is not read the same
way under every mod: the mod's own pop types are registered before parsing and
decide which pop blocks the province reader keeps, so the same file under two
mods is two different parses and must not share a slot. Output is byte-identical
either way. `--no-cache` re-reads everything.

Both of those still describe the token walk, which is now the fallback rather
than the usual path: skipping a block does not tokenize it, since most of a save
is blocks nothing here reads and the skip leaps brace to brace through the raw
text, and the cursor keeps its last match rather than asking it for a position,
because where the cursor is only matters when a block gets skipped.

Every number above was checked by comparing output: the report and all eight
CSVs are byte-identical across one core and many, cached and not.

### A campaign saved every month

Thirty-eight hand-made saves is one shape of problem. A century autosaved
monthly is twelve hundred, and things that were rounding errors at thirty-eight
are the whole runtime at twelve hundred. Measured by running the real pipeline
over twelve hundred saves:

| | before | after |
|---|---|---|
| the parse, on every core | about 100 s | about 51 s |
| everything after the parse | 32.3 s | 23.5 s |
| peak memory | 4.14 GB | 2.94 GB |
| report.html | 119 MB | about 30 MB |

Four things were costing more than they were worth.

**The same war history, twelve hundred times.** A save does not record the war
it is in; it records every war there has ever been. By 1908 that is 2.7 MB per
save of which 263 wars are distinct, so thirty-eight saves carry fifty megabytes
of overlapping copies and twelve hundred would carry nearly two gigabytes. The
merge that `build_wars` always did at the end now happens once up front, in
`merge_wars`, and each save drops its own list the moment it has been folded in.

**Mobilizable pops that were never eligible.** The biggest thing a parsed save
carries is one entry per pop per province -- eleven thousand for a large nation,
two megabytes a save -- and about half of them are of a culture the nation does
not accept, which `finalize` was discarding every time it ran. The test needs
the country block, which is why it could not live in `read_province`, but it can
live at the end of `analyze_save`, and now does. What survives keeps its order,
because the counting rule depends on it, and the total the dropped pops came to
is kept as a number so `--explain-mob-pool` still reports it exactly. The rest
of the list goes as soon as `finalize` has read it. `regiment_pops` goes the
same way, one line after the only loop that reads it.

**A date split three million times.** `merge_prices` was asking `date_key` for
the save's own date once per price reading rather than once per save, and both
`date_key` and `year_fraction` were re-splitting the same few hundred strings
hundreds of thousands of times. Hoisting the first and remembering the other two
takes `merge_prices` from 2.6 s to 0.6 s and `build_wars` from 2.7 s to 0.5 s.

**A dict per CSV row.** The four big tables -- technologies above all, which is
one row per nation per save per tech -- are tuples now, in the column order the
writer declares, and `csv.writer.writerows` pulls them itself instead of
`DictWriter` naming the same six columns three million times.

### The parse stopped being a walk

The token walk reads a save without knowing anything about how it is laid out,
which is what made it safe and what made it slow: eight million tokens, every
one a Python step, most of them inside blocks nothing here reads. It ran at
35 MB/s.

Five attempts to make the walk itself cheaper are worth recording, because they
all failed the same way. Each was measured on four saves from four mods and
each was checked for identical output:

| | |
|---|---|
| read each pop block by slicing it out and regexing it | 1.03x |
| count braces in C instead of walking them one at a time | 3.4x on the skip, 0.99x overall |
| a fast path for flat blocks, which are 75% of the skips | 1.01x |
| let `read_pop` drive the match iterator itself | 1.04x |
| leave a pop block early, once it has given up its seven fields | 1.00x-1.12x |

Tokenising the whole file takes 0.98 s and a bare regex scan for braces alone
takes 0.30 s, against 1.33 s for the parse. The cost was never which tokens got
built; it was walking 46 MB one match at a time. The last two rows make the
point exactly -- skipping work inside a pop saves nothing, because the skip has
to cross the same bytes the tokeniser would have.

So the walk was replaced by a scan, and the same save now parses in **0.58 s**,
80 MB/s, **2.14x** over all 76 saves of the four campaigns.

**The layout is the thing.** The engine writes a save to a fixed shape and no
mod can change it: a top-level key at column zero with its `{` alone on the next
line, a province's own fields one tab in, a pop's two. Four things follow.

*Finding the blocks.* `top_level_blocks` looks for `\n{` -- a memchr over four
thousand hits -- and reads the key backwards off the line above. Looking for the
key instead, with `(?m)^([^\s={}"]+)=`, means offering three million line starts
to a regex and cost 0.24 s, a quarter of the parse on its own. A block then runs
to the *next* block's key line, which is more than the block; that is
deliberate, since every reader stops at its own closing brace anyway and finding
that brace exactly would mean counting braces through the file again.

*Never touching what is not wanted.* The walk had to brace-count its way through
26 MB of blocks nothing reads. The scan does not look at them at all.

*Matching only the seven fields a pop has to answer for.* A pop carries about
two dozen and seven are read: six numbers and the culture line, which has no key
of its own -- it is literally `french=catholic` -- and so is picked out by having
a value that does not start with a digit. Matching all of them was half a
million matches a save; matching those is two hundred thousand. And the pop is
filled into a list of eight slots rather than a dictionary, which is
twenty-five thousand dictionaries a save that are no longer built, filled, and
read back a key at a time.

*A literal to search for.* `\n\t` rather than `(?m)^\t` lets the engine jump
from newline to newline instead of trying every line start: same matches, a
third off the scan.

Two things that are still `parse_block` got told what to skip instead. A state
lists every employed pop of every factory under `employment`, which is most of
the block and has never been read here; an `id` sub-block is the engine's handle
on a thing and says nothing about it, and a `leader` is a handle too. `pop` is
in neither list and must not be, because a regiment's pop is how a standing
brigade is told from a mobilized one.

**The walk is still there.** `top_level_blocks` returns None the moment a `{` at
column zero does not have a bare `key=` above it, and everything falls back to
the token walk, which needs no layout at all -- a save reflowed by a text editor
still reads, just slowly. The readers are written once and take their entries
from either source, so there is one copy of what a province or a country
*means* and two of how its parts are found.

**How it was checked.** The scan and the walk were run against each other over
all 76 saves of the four campaigns -- 2.7 GB, four different mods -- and
compared by pickling the whole result, so a stray key or a float differing in
the last place would show. They agree on every save. Before any of it was
written, the two were compared structurally on 69,106 top-level blocks: same
keys, same order, same block-or-scalar, every time. `--verify`, which counts
regiments and ships by an independent brace-tracking scan of the raw text,
agrees on all four mods. And the whole pipeline's output -- eight CSVs and the
report payload -- is byte-identical to what the walk produced.

### The report travels compressed

A payload of thirty-eight saves is 7.3 MB of JSON. The same campaign autosaved
monthly is 119 MB, which is not a file anybody sends anyone.

It is mostly repeated key names and columns of similar numbers, so it goes into
the page gzipped and base64'd and the browser inflates it on the way in. A real
report goes from 7.5 MB to 2.3 MB, and opens quicker than it did: inflating a
megabyte costs less than reading nine off a disk and parsing them. On the
twelve-hundred-save payload, 253 ms to inflate and 479 ms to parse against
4.3 s to load it uncompressed.

Base64 costs a third back on top of the gzip. That is the price of keeping one
file that opens off a disk with no server behind it, and it is worth paying.

Two things follow from it. `DecompressionStream` is asynchronous and a browser
has no synchronous gzip, so the whole page script runs inside one async function
-- which is also why it is not a module: a module script will not load from a
`file://` URL, and opening the report off a disk is the normal way to read one.
And a failure has to say so on the page, since a report is a file somebody was
sent and the console is not somewhere they will look.

Rearranging the payload was tried and dropped. Turning every date key into an
index into `DATA.dates`, and printing whole floats as integers, takes 7% off the
raw JSON and **2%** off the compressed size, because gzip was already doing that
work. The compression is the whole of the win.

## What was removed

Six models of the mobilization count were built and discarded before the rule
was measured: per-pop truncation, a cascade up province/state/nation, a province
levy, a fixed share of short pops, a manpower threshold, and a pooled scale
factor. Each was fitted to in-game readings, each failed somewhere, and all six
plus their ten command-line knobs and the calibration harness are gone -- about
370 lines. What they were and how they broke is recorded under *Dead ends
worth recording* further down, which is the part worth keeping.

## Prices come out of the save with real history

Unlike almost everything else, prices are not snapshot-only. Each save carries a
rolling buffer of **36 monthly price readings** for every good, in repeated
`price_history` blocks under `worldmarket`, stamped by
`price_history_last_update`. So one save yields three years of monthly prices,
and a run of saves stitches into a continuous series — buffers from consecutive
saves overlap heavily, and duplicates collapse on (date, good).

The interval is one month rather than one day: the `price_change` block caps
daily movement at about 0.01, while consecutive history entries differ by up to
0.30.

`prices.csv` is `date, year, good, category, price`. Categories come from a
vanilla goods list; anything a mod adds lands in `other` and still charts fine.

**Demand needs care.** Some goods carry a stored `demand` of roughly a billion
or two, which is nobody's economy: it is a standing order to buy without limit,
which mods hand a nation so raw materials always find a buyer. Every reading
carrying one, across the campaigns this was checked against, sits at exactly
five times the good's base cost -- the engine's price ceiling -- so for those
goods neither price nor demand reports on scarcity. The report flags them in a
**Pegged** column and falls back to `unsold` (supply that found no buyer at all)
as the glut signal. `market_snapshot.csv` keeps both the raw `demand` and the
honest `real_demand`; if you analyse the CSV yourself, use `real_demand` or you
will get nonsense.

Market tab controls worth knowing: **Top movers** picks the six goods that moved
most across the span, **Indexed (=100)** rebases every good to 100 at its first
reading so a 70-unit good and a 1-unit good can share an axis, and clicking a
row in the market table plots that good.

## Who supplied what

Each country block carries `saved_country_supply`: a good-by-good record of what
that nation put on the world market. It is production as the market sees it
rather than a stockpile or an income, and the check is that it adds up. Summed
over the nations that hold land in the 1908 IGoR save it comes to 41,072.85 of
grain against a world `supply_pool` of 41,072.85. Summed over *every* country
block it comes to 43,191, because a nation that no longer exists keeps the last
figure it ever had; the report only ever counts nations with population, which
is what makes the two agree.

The payload names the fourteen largest suppliers of each good at each save and
keeps the world total beside them, so the share the named ones do not account for
is still recoverable as one bar. Naming all of them for every good at every save
was most of a megabyte; fourteen is 370 KB, and the ninetieth supplier of grain
is not what makes a glut.

**A good that records no sale in any save is not traded at all.** Precious metal
is the standing case: the engine turns it into money at the mint rather than
putting it up for sale, so its supply is real and its `actual_sold` is always
nil. Read naively that is "100% unsold, for ever", which puts it at the top of
every glut list and says nothing, so those goods are left blank instead.

## Fleet power

A hull is worth

    gun power x hull / (1 - evasion)

Two ships trading fire deal damage in proportion to their own gun power and in
inverse proportion to the other's hull, and evasion throws away a share of the
ticks aimed at it. Ask which of them out-damages the other and move each ship's
terms to its own side of the comparison, and this is what is left -- a number
that can be added over a fleet and divided between two of them. The derivation is
Boltun's, in his guide to navies, after Poppis on the combat code.

It reproduces his worked figures exactly, which is what makes it trustworthy.
Vanilla frigate: gun power 4, hull 3, evasion 0.25, one naval point, so
`4 x 3 / 0.75 = 16` per point. Man-o'-war: 8, 4, no evasion, two points, so also
16 -- "just as efficient", as the guide has it. Add the +2 gun power an early
invention gives every ship and the frigate goes to 24 and the man-o'-war to 20,
his numbers. Add the later +2 gun power and +1 hull and the frigate reads
`8 x 4 / 0.75 = 42.67`, and the guide says 42.7. Commerce raiders come out the
most powerful of the three early hulls and the least efficient per point, which
is what he says of them too, and the monitor overtakes the ironclad exactly
where he says it does -- 98 against 101.3 before Main Armament, 119.0 against
117.3 after.

### The design figure, and the fleet as it stands

The power level above compares ship *designs*, and to do that it takes two
terms of the damage formula as equal. Boltun says so plainly: "all ships have
the same experience... strength is maxed at 100%". Two real fleets on a real
date do not oblige, and the save records both.

Strength multiplies the damage a hull deals. Experience is subtracted from the
damage it takes, so the same rearranging that put hull and evasion on their
owner's side puts experience there too:

    what a hull is worth today = gun power x hull x strength
                                 / ((1 - evasion) x (1 - experience))

Leaving the two out is not a small thing. Across a save it runs at 98.9%
strength and 16.2% experience in the IGoR campaign, 77.4% and 5.0% in
Divergences of Darkness, 92.8% and none at all in Ferrum Mare -- and per nation
it swings from -34% to +25%. **The order changes in all three campaigns.** In
Divergences in 1871 the Danubian fleet reads second and is fourth: it is at 85%
of its paper figure while Italy's is at 106%.

Both are shown, the design figure first and "at current strength" under it,
rather than one replacing the other. A fleet somebody has stopped paying for
should still show what it would be worth repaired -- China in the 1860s keeps a
paper fleet worth 516 that is fighting at 7, and a report that showed only the
7 would suggest there was nothing there to fix.

The weight is summed per hull rather than averaged per type, because the sum is
exact and the average is not: `crews` carries the sum of
`strength / (1 - experience)` over the hulls of each type, and is left out
entirely wherever it comes to the hull count, which for most navies most of the
time it does.

Torpedoes are a second power level rather than part of the first: they only work
against a `big_ship`, so `unit_type` is carried through and the report gives a
separate "against heavy ships" figure wherever any hull on either side carries
one.

**The upgrades are almost all inventions rather than technologies.** A
technology opens an area and the inventions under it add the gun power and the
hull: in vanilla, IGoR, Ferrum Mare and Divergences of Darkness, `technologies/`
does not touch a ship at all. Almost -- GFM's `naval_directionism` hands the two
transports speed and evasion directly, so technologies are read as well. They are
the easier half, since a save names a nation's technologies outright; `ai_chance`
is cut out of a tech block first, because it is full of `modifier = { ... }`
blocks that look like effects and are weightings.

Inventions follow `breakdown`: the save names them by index where the load order
decodes, and otherwise falls back to every invention whose requirements the
nation meets, which flatters unlucky nations. Only `effect = { ... }` is read
there -- a `limit` or a `chance` block names ships as requirements, not as
changes. `navy_base` is the engine's name for "every naval unit" and is applied
to all of them.

**Which inventions a technology opens is the mod's business, so none of this is
written down here.** Of the 42 naval inventions IGoR, Ferrum Mare, CE 1v1 and
DoD Heartbreaker each carry, six are vanilla's, sixteen have different numbers
and twenty do not exist in the base game; Divergences of Darkness keeps
vanilla's twenty-five and rewrites ten of them; GFM adds a submarine and gives
it the cruiser's torpedoes. A table of vanilla effects would be wrong for every
campaign in this folder, which is why the mapping is read from each mod's own
`inventions/` and the nation's holdings are decoded against that mod's own
ordering.

### The ordering was checked against the game

The array is a reconstruction, so for a long time the argument for it was
circumstantial. It is not any more. Four inventions were watched as they fired
in IGoR, each with a save taken the day after, and the saves diffed:

| the game announced | new index | decoded as |
|---|---|---|
| Prophylaxis against malaria | 468 | `prophylaxis_against_malaria` |
| Genetics: Heredity | 466 | `genetics:_heredity` |
| Vaccination | 464 | `vaccination` |
| Chemotherapy | 465 | `chemotherapy` |

Four for four, and note the indices are not in the order the inventions fired.
A wrong array would have to be wrong in a way that produced four exactly right
names in a scrambled order.

The base is confirmed the same way. `caste_privileges` cannot be researched
naturally in IGoR, and spawned into a British save from the console it appears
at **index 1** -- the first entry of `POD_sepoys.txt`. The USA's lowest index in
1836 is 4, and the technology screen shows it holding everything under The
Rights of Man except Caste Privilege, Abolishment of Sati and Pig Fat
Cartridges, which are array positions 1, 2 and 3.

And the leftover disagreements are not errors. The technology screen shows the
1836 USA holding four Ideological Thought inventions -- Authoritarianism,
Hierarchical Order, Traditionalism, Political Religion -- without having
researched Ideological Thought, which is what the decode said and what
`validate_indices` counts as impossible. `commerce_raiders` is the same story:
gated on `steamers`, and handed to anyone who starts with the ships. The
residue is the engine granting inventions outside the tech tree.

Ship stats were read off the naval panel at the same time and matched the unit
files exactly, and an invention spawned into an Ottoman save moved every combat
hull by +2 gun power while leaving both transports alone -- the mod writes
`navy_base` +1 and a matching -1 for each transport, and the two cancel.

That the ordering is right is also checkable from the files alone, and it was
worth checking first, because a mis-decode hands a nation some other
invention's gun power. Narrow `validate_indices` to the inventions that touch a
ship and shift the base a step either way:

| | -2 | -1 | **as decoded** | +1 | +2 |
|---|---|---|---|---|---|
| IGoR | | 13.6% | **0.1%** | 37.9% | 53.2% |
| Divergences of Darkness | 41.2% | 33.9% | **6.8%** | 51.7% | 68.3% |
| Ferrum Mare | 47.9% | 23.6% | **0.0%** | 70.9% | 87.3% |

An ordering that were only accidentally plausible would not do that.

### When a save is not from the build

Divergences of Darkness is the exception in that table, and it is not the
ordering -- it is one file. The folder rebuilds 408 inventions and 28 of the
campaign's 29 saves stay inside that; `mp_Xifang1850_01_01.v2` names indices up
to 549. It is a Divergences save, unmistakably -- every other mod here fails to
recognise between 195 and 595 of its country tags, and this folder fails to
recognise two -- but it is a *different build* of it: two extra tags, `JAN` and
`YUA`, and about a hundred and forty more inventions. It is also the earliest
save in the folder, which is what you would expect of a campaign that carried on
across a version bump.

That one file is the whole of the 3.5%. Its 495 unreadable holdings drag three
inventions at the tail -- `wireless`, `advanced_fire_control` and
`15_inch_main_armament`, all gated on a technology nobody in the campaign ever
researched -- into decoding as something the nation could not have had, and
nothing in the mod grants those by event or decision.

Every other campaign fits its folder exactly: IGoR rebuilds 566 and its saves
use 1..566, Ferrum Mare rebuilds 557 and uses 1..555, DoD Heartbreaker rebuilds
563 and the fourth campaign uses 1..560.

So `index_coverage` reports it **per save**, and names the file. An index past
the end of the array is proof that *that save* was written by a different build,
and everything read off an invention in it is short by whatever those grant. The
run used to print a confident "indices decoded" and leave it there; the first
attempt at a warning blamed `--mod-path`, which sends you looking in the wrong
place when 28 of 29 files are fine.

### Checking the decode against the saves instead of the folder

`--check-inventions` does the whole thing without trusting the folder at all.
An invention gated on a technology is held almost only by nations that have
that technology, so who holds an index and what they know is a fingerprint of
what the invention there requires -- built from the saves and from nothing else.

Almost only, not only, and the difference is the whole design of the check. A
first cut scored each index by a 95% quantile and returned pass or fail, which
cannot tell *thirty-four nations hold this with the technology and two without*
from *nobody who holds it has the technology*. The first is the engine granting
an invention outside the tech tree, which the game's own screens confirm; the
second is what a misaligned array looks like. So each index is graded by the
share of its holders that could actually have researched it:

| | |
|---|---|
| **confirmed** | 95% or more of holders have the technology |
| **granted** | most do, a few do not -- the engine handing it out |
| **suspect** | fewer than half do, which is misalignment |

| campaign | confirmed | granted | suspect |
|---|---|---|---|
| IGoR | 420 | 1 | **0** |
| DoD Heartbreaker | 206 | 1 | **0** |
| Ferrum Mare | 193 | 23 | **0** |
| Divergences, without the foreign save | 271 | 2 | **0** |
| Divergences, all 29 saves | 235 | 28 | 35 |

Every other offset is far worse everywhere: at -1 IGoR confirms 262 against 420
and turns up 88 suspects where the decode in use has none.

Divergences is the one row that is not zero, and it is one file rather than the
folder. `mp_Xifang1850_01_01.v2` decodes against a different array, so every
invention it contributes lands on the wrong name and drags the other 28 saves'
fingerprints with it. On its own it does not decode at all.

### A gate that never closes

Ferrum Mare read one suspect until the check learned about this. Its
`transport_convoys` requires `clipper_designs`; the technology the mod actually
defines is `clipper_design`. The name matches nothing, so the gate never
closes, the engine hands the invention to every nation from the first day, and
151 nation-saves hold it without a single one having "the technology" -- which
is exactly what a misaligned array looks like from the outside.

It is not misaligned. The invention is where the array says, and the only thing
it does is `activate_building = transport_shipyard`: it touches no ship stat
and no mobilisation size, so nothing computed here moved either way.

So `load_mod` now carries the set of technologies a mod defines, and an
invention asking for something outside it is judged neither way and reported
separately. `ungated_inventions` finds one in Ferrum Mare and four in CE 1v1 --
which borrows PUIR's invention files without PUIR's `psychological_intelligence`
technology to gate them. The base game and the other five mods have none.

Nations that researched the same things have the same ships, so the profiles are
stored once each and referred to by number: 83 distinct profiles across 126
nations and 38 saves in the IGoR campaign.

Two things a mod can do that the measure has to survive. IGoR sets
`supply_consumption_score = 0` on every hull, so there are no naval points to
divide by and only the per-hull figure is shown. And a mod is free to rewrite the
stats entirely -- IGoR's cruiser is 20/30/0.25 against vanilla's 30/50/0.30 --
which is exactly why the numbers are read from the files rather than written down
here.

That second one is worth being firm about, because the guide is wrong about it:
"none of the most popular mods actually change any values for the ships or navy
technology". Every one of the seven installed here does. GFM swaps the monitor
and the ironclad round -- monitor gun power 10 to 20 and hull 20 to 10 -- DoD
doubles the dreadnought, and four mods zero every naval point. A spreadsheet of
vanilla numbers does not describe any campaign in this folder.

## Stopping a run

The window has a **Stop** button, so the analyzer takes a callable and asks it,
between saves, whether to carry on; a terminal run never sets one and never asks.
Between saves rather than inside one, because a save is a few seconds at worst
and unwinding a half-read one buys nothing.

The parallel path had to change shape for it. `pool.map` gives no handle on the
queue, so a cancellation would leave the executor's context manager waiting
politely for every save still to come -- on a folder of hundreds, a Stop button
that takes ten minutes to stop. Work is now submitted one future per save and
collected with a short `wait` timeout, so the button is answered while the
workers are busy, and cancelling calls `shutdown(cancel_futures=True)`: everything
not yet started is dropped and only the saves actually in flight finish. Measured
on the 38-save folder, Stop pressed at 1.5 s returned at 1.7 s and the process was
gone at 4.5 s. `parse_saves` re-raises `Cancelled` rather than treating it as a
machine that cannot start workers, which would otherwise quietly restart the
whole folder one save at a time.

Everything read before the stop is already in the cache, so starting again picks
up where it left off.

## Mobilized brigades

Saves do not label a regiment as mobilized, and they do not store a nation's
mobilization *pool* at all — the game computes that at runtime from pops and
military spending. What every regiment does carry is the pop it was raised from,
so the split falls out of the data: a regiment sourced from a **soldiers** pop is
standing army, and one sourced from farmers, labourers or any other pop only
exists because the nation mobilized.

That test agrees exactly with the `mobilize=yes` flag. In the 1908 save, the
only three nations with regiments from non-soldier pops — Mexico 72, Andine
Federation 50, Commonwealth 24 — are precisely the three flagged as mobilized,
and every other nation is 100% soldier-pop.

Brigades still on the way are counted separately as `mobilizing`, from
`scheduled_mobilization` blocks that have not spawned. The Andine Federation has
50 mobilized and 68 queued, so its army is set to roughly double.

Classification happens after the whole file is read, so it does not depend on
provinces being written before country blocks.

### The mobilization pool

The in-game "Brigades to Mobilize" figure is **not stored in the save** — the
game derives it at runtime, so it has to be recomputed from the pops. Two things
go into that: how big each nation's mobilisation size is, and how the engine
turns population into brigades. The first is exact. The second is a calibration.

#### Mobilisation size is read out of the save

`--mod-path` computes each nation's mobilisation size from the mod's own files
plus what the save says the nation has:

```bash
python3 vic2_analyzer.py saves/ --mod-path "path/to/IGoR"
```

- **Technologies and national values** are stored in the save by name.
- **Reforms** are stored in the save by name too -- a country block carries a
  plain `conscription = mandatory_service` line. GFM hangs a four-rung
  conscription ladder off that reform, +1% to +6%, and takes 1% back at two
  levels of its `centralization` reform. Six percent is more than GFM's entire
  technology tree grants.
- **Inventions** are stored as bare numeric indices into the engine's global
  invention array. That array is built by walking `inventions/` in plain ASCII
  file order — uppercase file names sort before lowercase — taking inventions in
  the order they appear inside each file, and numbering from 1. The run decodes
  those indices and checks the result: an invention a nation holds should be one
  whose `limit` that nation meets. On the IGoR saves that check fails for 7 of
  5694 nation-invention pairs (0.1%), which is the residue of inventions granted
  by events. A wrong ordering fails 11% or more, and the analyzer falls back to
  requirement matching and says so when the check does not pass.
- **Event modifiers** are listed in the save by name.
- **The uncivilized penalty** is a static modifier: `unciv_nation` in
  `common/static_modifiers.txt`, -10% in the base game and -20% in Divergences
  of Darkness, applied to everyone uncivilized and written down nowhere.
- **Triggered modifiers** are the hard ones, and have a section to themselves
  below.

This matters because inventions fire on a chance roll: two nations with
identical technology routinely have different mobilisation sizes. Assuming every
nation holds every invention it *could* have overstates the unlucky ones — in
the 1908 save that assumption inflates Spain and Mexico by a full point, China
by 1.5, and the Andine Federation by 2.

Contributions can also be strongly negative — IGoR's `china_mobilization_nerf`
is −100 — and the result is floored at zero rather than falling through to the
`--mobilisation-size` default.

Without `--mod-path`, or for a nation the mod says nothing about, the rate falls
back to `--mobilisation-size`:

```bash
python3 vic2_analyzer.py saves/ --mobilisation-size 0.12
```

#### Triggered modifiers have to be judged, not looked up

An **event** modifier is granted to a country and stays granted, so the save
lists it by name and reading it is a dictionary lookup. A **triggered** modifier
is re-evaluated by the engine every day from its own `trigger` block and never
written down at all. The only way to know a country has one is to read the
trigger and decide.

This used to be done for exactly two shapes: a trigger that names a revanchism
threshold, and the human-run-uncivilized bonus. Everything else was skipped in
silence. On GFM that is most of them:

| | |
|---|---|
| `ils_ne_passeront_pas` | +13% to an AI France that does not hold province 409 |
| `pashtunwali` | +20% to Afghanistan at war with a great power |
| `glory_prussia` | +10% to an AI Prussia before 1880 |
| five more, for the Americas | +3% to +10%, by population and by whether a person is playing |
| `collectivisation_modifier` | +2% to a communist government holding the invention |

`_trigger_ok` reads a trigger one condition at a time and answers **true, false
or "I cannot tell"**. It knows twenty-five conditions -- tag, ai, civilized,
war, exists, government, national value, primary culture, culture group,
capital, capital continent, year, great-power status, total population, province
ownership, invention, technology, country flags, country modifiers, and the
numeric ones (revanchism, infamy, prestige, treasury, war exhaustion,
plurality) -- plus whichever reforms a trigger names, and `AND`, `OR` and
`NOT`. A modifier whose trigger
uses anything else is left out, and `--explain-mob` prints which ones those
were, so a number that is short is short *visibly*. Across all seven installed
mods that is one modifier: GFM's `pashtunwali`, which asks
`any_greater_power = { war_with = THIS }`.

One subtlety worth writing down. A Clausewitz block is a bag of key/value pairs
and the same key may repeat, so `OR = { tag = FRA tag = BOR }` parses to a
single block whose `tag` holds two values. It is two conditions, not one
condition with two values, and only the enclosing operator says whether they are
ANDed or ORed. Reading the first value alone cost Bourbon France a modifier
worth 13%.

**Retiring the two special cases changed nothing where nothing should change.**
The revanchism ladder picked the highest matching band; the general evaluator
sums every matching modifier, and the bands are written mutually exclusive
(`revanchism = 0.20`, `NOT = { revanchism = 0.25 }`), so the two agree by
construction. Checked rather than argued: 1,543 nation-saves of IGoR and 156 of
Ferrum Mare come out identical to the last decimal, and the 80 that move on
Divergences of Darkness all move for the separate reason that its uncivilized
nations now carry `unciv_nation` at -20% and floor at zero.

GFM has no save here, so its rules are checked against nations built for the
purpose -- an AI France, a Bourbon France, a player France, a France holding 409,
a Prussia either side of 1880, a regionalist USA, five sizes of South American
nation, a communist with and without the invention -- 27 assertions worked out
by hand from the mod files.

#### Uncivilized nations, and who was human

Being uncivilized is **not** a filter. A test nation with `civilized = no` in its
history and a national value granting 3% mobilized exactly like its civilized
control. Uncivilized nations read zero in practice because their *rate* is zero:
no technology or invention they can hold grants mobilisation size, and in IGoR
no national value grants it either. (Project Alice documents an explicit
`is_civilized() == false -> 0`; since a mod runs the same executable, that
appears to be a divergence rather than a description.)

The **base game and Divergences of Darkness** do apply a flat penalty --
`unciv_nation`, -10% and -20% -- which had been missed entirely. It is what
takes Ethiopia, Punjab, Berar and forty other Divergences nations from the 4-5%
their national value grants to a floored zero, which is the same place the
vanilla engine puts them. IGoR, Ferrum Mare, CE 1v1 and DoD Heartbreaker attach
no mobilisation size to `unciv_nation` at all, so nothing there moves.

That leaves one modifier the save cannot resolve on its own. IGoR's
`player_unciv_mobilization` grants **+2%** on `ai = no` and `civilized = no`,
excluding whoever holds the `china` country flag:

```
python3 vic2_analyzer.py saves/ --mod-path <mod> --player-nations JAP KOR
```

Every country a person is playing carries `human = yes`, so this is read off
the save and `--player-nations` is only needed for a save that carries no such
marker -- it overrides what the save says when given, and passing the flag with
no tags treats everyone as AI. It is no longer only uncivilized nations that
care: GFM pays a South American player differently from a South American AI, and
three of its modifiers turn on `ai = yes`. In a 1836 save this reproduces
Japan's in-game tooltip
exactly -- 2.00% mobilisation size, a pro-military cap of 40 x (1 + 3) = 160 --
while China, holding the `china` flag, stays at zero however it is marked.

Two things that bite when checking this against the game: the modifier is a
*triggered* modifier, so it does not appear until a tick passes -- tag-switching
to a nation and reading it immediately shows the pre-switch state -- and the
rate is zero the moment the nation westernizes into the ordinary tech path.

#### Day one is not trustworthy

The figure the game shows on the very first day of a start date can disagree
with the figure it shows on day two, without anything in the save changing that
would explain it. A fresh 1836 game played as Japan showed 30 on 1836.1.1 and 27
on 1836.2.1; the model reads 27 from the day-two save. The engine appears not to
have run the calculation yet on day one.

Take readings from day two onwards. This matters mainly for controlled
experiments, which naturally get read at the start date -- worth stepping a day
before reading, and worth re-reading anything surprising a day later.

#### Who is eligible

[Project Alice](https://github.com/schombert/Project-Alice), the open-source
reimplementation, documents the rule and implements it in `military.cpp`
(`mobilized_regiments_possible_from_province`, `pop_eligible_for_mobilization`):

> Mobilized regiments come only from unoccupied, non-colonial provinces. In
> those provinces, mobilized regiments come from non-soldier, non-slave,
> poor-strata pops with a culture that is either the primary culture of the
> nation or an accepted culture. The number of regiments these pops can provide
> is determined by pop-size × mobilization-size / `define:POP_SIZE_PER_REGIMENT`.

All of that eligibility is enforced here, and none of it is fitted:

- **Eligible pop types are a mod property.** They are the poor strata minus
  soldiers and slaves, read from the mod's `poptypes/*.txt`. For IGoR that works
  out to farmers, labourers and craftsmen.
- **Occupied provinces contribute nothing.** Any province whose `controller`
  differs from its `owner` is skipped, along with colonial and protectorate
  states (`is_colonial` in the save). This moves a nation under siege a lot —
  Russia in 1908 reads 598 without its nine occupied provinces and 652 with, and
  the in-game figure is exactly 598 — so `--mob-include-occupied` exists only to
  re-check it.
- **Culture is filtered per pop**, against the save's `primary_culture` plus its
  `culture={...}` accepted list.

#### The arithmetic, measured

Alice's per-pop truncation does not reproduce the game. At 3% almost no pop on
its own reaches the 3000 manpower a regiment costs, so it predicts **zero**
brigades for the 1836 USA while the game offers 23. Manpower below a whole
regiment is clearly pooled — but pooled how, and where it is lost, took a
controlled experiment to settle.

That experiment lives in the mod: 147 test nations across six rounds, each
holding everything fixed and varying one thing, read straight off the in-game
counter. The rule it produced:

    pool = 0
    for each eligible pop, in the order the save lists them:
        manpower = pop_size x mobilisation_size

        if manpower >= POP_SIZE_PER_REGIMENT:     # raises regiments by itself
            brigades += int(manpower / POP_SIZE_PER_REGIMENT)
            pool = 0                              # <-- and empties the pool
        else:
            pool += manpower
            if pool >= POP_SIZE_PER_REGIMENT:
                brigades += 1
                pool = 0

There is nothing fitted here. `POP_SIZE_PER_REGIMENT` is 3000 straight out of
`defines.lua`, and it is the only number in the rule.

**The flush is the whole story.** A pop large enough to raise a regiment on its
own does so and throws away whatever had been gathered behind it. That single
line explains everything that looked anomalous for months:

- A nation of uniformly small pops never flushes, so its pool runs perfectly and
  `k` identical short pops yield `floor(k / ceil(3000 / manpower))`.
- A nation whose large and small pops interleave keeps losing what it gathered.
  This is why culturally mixed nations — which have many small pops scattered
  between large ones — came out systematically high under every pooling model
  that lacked the flush, by about 6%.
- Order therefore matters, and the order is the save's own. Shuffling the pop
  order changes the answer for 40 of the 100 test nations, and only the save
  order reproduces all of them.

Measured against every in-game reading ever taken:

| readings | source | exact |
|---|---|---:|
| 100 | test bed generation 3 (`M00`-`M99`, 1836) | 100 / 100 |
| 39 | test bed generations 1-2 (`T01`-`T25`) | 39 / 39 |
| 46 | campaign saves, 1836 / 1862 / 1888 / 1908 | 45 / 46 |

Median error 0.00%, worst 0.21%, bias −0.00%. The single miss is Japan in 1908,
467 against 468.

The flags that used to select between the fitted models -- `--mob-model`,
`--mob-pool-factor`, `--mob-grouping` -- are gone along with the models
themselves. What survives on the command line is the machinery for checking the
rule rather than changing it: `--explain-mob TAG` prints every technology,
invention and modifier contributing to a nation's mobilisation size, and
`--explain-mob-pool TAG` prints the pool itself -- eligible pops, and what
colonial, occupied and non-accepted provinces cost it.

#### Dead ends worth recording

All of these were tested in the bed and are **not** part of the rule. Each was
measured with 8 pops in 4 states that read 4 brigades in the control, changing
one thing:

| changed | reads | verdict |
|---|---:|---|
| no cores on any province | 4 | cores are irrelevant |
| half the states cored | 4 | irrelevant |
| craftsmen, or labourers, instead of farmers | 4 | pop type is irrelevant |
| pops with no matching RGO (unemployed) | 4 | employment is irrelevant |
| literacy 5% / 95% | 4 | irrelevant |
| democracy instead of absolute monarchy | 4 | irrelevant |
| pacifism, and pacifism with no standing army | 4 | the cap did not bind |
| no soldier pop, or a 300,000 soldier pop | 4 | soldiers are excluded, cleanly |
| pops at militancy 9 | 4 | irrelevant |
| provinces carrying a foreign core | 4 | irrelevant |
| `civilized = no` | 4 | uncivilized nations still report a pool |
| half the pops given a non-accepted culture | 2 | **culture is the only filter** |

Earlier model families are also dead, and are recorded because each looked
convincing on a narrow sample: a **cascade** of leftovers up province → state →
nation (6.2% mean, needed an invented 3220-manpower cost), **short-share** (fits
the eight 1908 great powers to 1.2%, an artifact of all eight sharing a 12%
rate, 49% out at 3%), and **province-levy** (fits all thirteen 1908 readings to
2.3%, 60% low in 1836). Gathering leftovers **per state** rather than nationally
also survived all 47 readings taken before generation 3, and was only killed by
`M01`-`M08`, which put one pop in each of several states and still raised
brigades.

Recalibrate against your own readings at any time, across as many saves as you
like:

```bash
python3 vic2_analyzer.py saves/ --mod-path <mod> --mob-calibrate 1836.3.1:USA=23 1888.2.15:USA=275 USA=560
```

Readings are `TAG=N` for the last save or `DATE:TAG=N` to name one. The command
fits every model, ranks them by mean, worst and held-out error, prints the best
beside plain truncation, and exits without writing anything. To inspect one
nation's pool instead:

```bash
python3 vic2_analyzer.py saves/ --mod-path <mod> --explain-mob-pool KUK
```

Constants are exposed too, since mods change them:

```bash
python3 vic2_analyzer.py saves/ --pop-per-regiment 3000 --mob-types farmers labourers
```

`--mod-path` reads `POP_SIZE_PER_REGIMENT` from `common/defines.lua` and the
strata table from `poptypes/`, along with any pop type the mod adds — IGoR's
`bankers`, which the parser would otherwise skip, dropping those pops from every
population total. Note that IGoR's `POP_MIN_SIZE_FOR_REGIMENT` of 1000 is *not*
the mobilization threshold: it governs how small a **soldier** pop may be and
still support a **standing** brigade, a different rule on a different pop type.

#### Which layer a pop type sits in is the mod's business too

Reading a mod's own pop types was only half of it. The poor/middle/rich totals
and the per-type columns of `nations_timeseries.csv` were both counted against
a hardcoded vanilla twelve, so a mod's own type was parsed out of the save,
added to the national total, and then dropped on the way to the table. Every one
of the four campaigns this is used on hit it: IGoR and Ferrum Mare add rich
`bankers`, GFM and Divergences of Darkness add poor `serfs`.

It shows worst where a nation is mostly that type. Ferrum Mare's LCT is 98%
bankers and its wealth breakdown accounted for 2,305 of its 116,733 people;
Hungary in Divergences is 29% serfs and lost every one of them. The layers now
come from the mod's `strata` table and the columns from the pop types actually
registered, and poor + middle + rich adds up to the population again.

#### What is not modelled

**The engine's cap is modelled** (`mobilization_cap`, `mobilization_available`).
`start_mobilization` limits a mobilization to

    floor(max(standing regiments, MIN_MOBILIZE_LIMIT) x (1 + impact))

where `impact` is the ruling party's war policy (`common/issues.txt`: jingoism
4, pro_military 3, anti_military 2, pacifism 1) plus every national modifier
that moves `mobilization_impact`. Saves store the ruling party as a **1-based**
index into the engine's global party list, which is rebuilt by walking
`common/countries.txt` in order and taking each country file's `party = {...}`
blocks in order — the same decoding the invention indices need. Active event
modifiers are stored by name and resolve directly; the revanchism bands are
triggered modifiers, evaluated live rather than written to the save, so they are
re-derived from the nation's `revanchism`.

Both halves were measured against China, whose army is small enough for the cap
to bind:

| nation | standing | policy | modifiers | cap | ceiling | game offers |
|---|---:|---|---|---:|---:|---:|
| CHI 1890 | 8 | pro_military (3) | none | **32** | 95 | 32 |
| CHI 1908 | 6 | pro_military (3) | totalitarianism −0.2 | **22** | 1056 | 22 |
| PBC 1908 | 33 | pro_military (3) | revanchism +0.25 | **140** | 161 | 140 |
| PBC 1908 | 34 | pro_military (3) | revanchism +0.25 | **144** | 161 | 144 |
| PBC 1908 | 34 | jingoism (4) | revanchism +0.25 | **178** | 161 | 161 |

The last row is why the ceiling and the cap are separate columns: raise the war
policy far enough and the cap stops being the binding constraint, and the number
the game offers goes back to being the pop ceiling. The two PBC rows one day
apart are the same nation with a brigade that finishes building the moment the
game unpauses.

The revanchism half is measured too. The Andine Federation in 1908 sits at
revanchism 0.2250, which lands in `save_the_nation2` (>= 0.20) for +0.25, and
the game reports its impact as **325%** against a pro-military party worth 300%.
Swapping it to a jingoist party moves the reported figure to 425%, which is the
same +0.25 on a different base.

The 1908 China case is worth keeping in mind as a warning: the in-game tooltip reads
"Mobilization impact 280.0% from Pro Military war policy", against a party file
that says 300%, because a communist China carries
`totalitarianism_modifier`. Reading the policy alone would have been 24.

`mobilization_brigades` stays the uncapped pop ceiling, since that is what all
57 validated readings measure; `mobilization_available` is the two combined and
is what the game offers.

Occupied provinces were confirmed the same way. The Andine Federation reads a
147-brigade ceiling with its Mexican-occupied states excluded and **161** with
them counted; white-peacing Mexico in game and re-reading gives 161.

**The save's own mobilization data is a snapshot, not a total.** A nation that
is mid-mobilization carries `scheduled_mobilization` blocks naming the pop and
province each brigade is being raised from, which is tempting to use as ground
truth — but the schedule is built and consumed progressively, so its size is a
lower bound. In the 1908 save the Andine Federation shows 121 orders (53
spawned) against a computed ceiling of 157.

## Military technology grouping

Saves list technologies as bare names with a researched flag and no folder
information, so `tech_groups.py` holds the mapping from tech to army or navy
line. Those are the vanilla names, which most mods reuse. Anything unrecognised
is reported under `other` in `technologies.csv` rather than dropped, so a mod's
own techs are still visible — add them to `ARMY_LINES` or `NAVY_LINES` to have
them appear in the report's technology matrix.

# Nations over a campaign

Nations over a campaign: tags that change, great powers, states, charts that survive gaps, names, a mod over its game, pop types and players.

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

## States come from the first region that claims a province

`map/region.txt` is meant to be one entry per state, but a mod can keep other
things in it: DoD ends the file with `MET_1`, a metaregion naming almost every
province on the map. Reversing the file into a province-to-state mapping without
a rule for repeats handed all 2,704 provinces to that one entry, and every state
in the war tab came out as "Earth". A province now belongs to the **first**
region that claims it, the same rule the country array follows, which leaves
mods without metaregions untouched -- IGoR reads 528 regions either way.

## Charts that survive a monthly autosave

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

## A hull the campaign has not invented yet

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

## Names come from the mod, not from the key

A save writes a good, a unit type, a pop type, a technology and a casus belli as
a bare key: `cattle`, `clipper_transport`, `aristocrats`,
`post_napoleonic_thought`. Tidying the underscores out is not translation --
IGoR calls `cattle` Livestock and `aristocrats` Landowners, and Divergences of
Darkness renames Post-Napoleonic Thought to Post-Wenceslian Thought.

All five are ordinary localisation keys sharing one namespace, so
`display_names` gathers the keys from `common/goods.txt`, `poptypes/`, `units/`,
`technologies/` and `common/cb_types.txt` across base game and mod, and looks
all of them up in one pass. `_text_localisation` reads the mod first and the base
game after it with the first definition winning, so a mod's rename wins and a
partial mod still gets the game's names for what it left alone.

Country names took longer to get there. `_read_localisation` read the mod folder
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

## A mod is a layer over the game, not a replacement for it

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

`resolved_files` does folders and `resolved_file` does the single files, and
between them every reader now goes through one of the two. Two of them are
order-sensitive and were checked rather than assumed: no mod here borrows a
single `technologies/` or `inventions/` file, so the invention array the save's
indices point into is byte-for-byte what it was.

## Each run reads under its own pop types

A save is read under a *reading*: the pop types the game ships plus the
mod's own, which of them can be mobilized, and which country fields are a
reform choice rather than an ordinary number. The reading is part of every
run (`Run.reading` in `scanner/src/engine/mod.rs`) and of the key a read save
is cached under, so a campaign read under one mod is never answered from a
read made under another. That matters because the window runs one campaign
after another: read IGoR and then Divergences of Darkness, and IGoR's
`bankers` once turned up in Divergences saves -- Jan Mayen with 16,482 of
them, under a mod that has no such pop type.

`testkit/caching.py` changes the mobilizable pop types between two cached
runs and holds the second to a run made with no cache.

## Who was playing

Each country a person is playing carries `human = yes` as the first line of its
own block. That is every player in a multiplayer game, not just the one who
pressed save, which is all `meta["player"]` ever gave -- and the difference is
thirty-one nations against one in the campaigns this was built on.

It matters twice: the **Players** preset and the **Player** column are read off
it, and so is `player_unciv_mobilization`, the bonus an uncivilized nation gets
for being run by a person. `--player-nations` still overrides the lot, and the
save's own player is still the fallback for a save with no markers at all.

## Nothing scrolls sideways

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

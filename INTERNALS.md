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

## One nation becoming another

The **Series** chart joins a nation to the one it became with a dashed line, so
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

| 38 saves | | |
|---|---|---|
| first run, one core | 63 s | where this started |
| first run, one core | 41 s | after the parser changes described here |
| **first run** | **6 s** | on as many cores as the machine has |
| **every run after** | **2.3 s** | the saves come back from the cache |

Three things got it there.

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
against the fourteen fields that are actually used. They were being parsed into
dictionaries and thrown away. Skipping them at the brace takes a save from 2.0 s
to 1.4 s and drops the tokens read from 5.2 M to 3.0 M.

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

Skipping a block also does not tokenize it: most of a save is blocks nothing
here reads, and the skip leaps brace to brace through the raw text. The token
cursor keeps the last match rather than asking it for its position, because
where the cursor is only matters when a block gets skipped -- once in thirty
tokens, not three million times on the way there.

Every number above was checked by comparing output: the report and all eight
CSVs are byte-identical across one core and many, cached and not.

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

**Demand needs care.** Victoria II holds a good at its price floor by adding a
sentinel of roughly two billion to the stored `demand`. `market_snapshot.csv`
keeps both the raw `demand` and the honest `real_demand`; the report shows
`real_demand` and flags pinned goods in an "At floor" column. If you analyse the
CSV yourself, use `real_demand` or you will get nonsense.

Market tab controls worth knowing: **Top movers** picks the six goods that moved
most across the span, **Indexed (=100)** rebases every good to 100 at its first
reading so a 70-unit good and a 1-unit good can share an axis, and clicking a
row in the market table plots that good.

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
- **Inventions** are stored as bare numeric indices into the engine's global
  invention array. That array is built by walking `inventions/` in plain ASCII
  file order — uppercase file names sort before lowercase — taking inventions in
  the order they appear inside each file, and numbering from 1. The run decodes
  those indices and checks the result: an invention a nation holds should be one
  whose `limit` that nation meets. On the IGoR saves that check fails for 7 of
  5694 nation-invention pairs (0.1%), which is the residue of inventions granted
  by events. A wrong ordering fails 11% or more, and the analyzer falls back to
  requirement matching and says so when the check does not pass.
- **Event modifiers and revanchism bands** come from `common/`.

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

#### Uncivilized nations, and who was human

Being uncivilized is **not** a filter. A test nation with `civilized = no` in its
history and a national value granting 3% mobilized exactly like its civilized
control. Uncivilized nations read zero in practice because their *rate* is zero:
no technology or invention they can hold grants mobilisation size, and in IGoR
no national value grants it either. (Project Alice documents an explicit
`is_civilized() == false -> 0`; since a mod runs the same executable, that
appears to be a divergence rather than a description.)

That leaves one modifier the save cannot resolve on its own. IGoR's
`player_unciv_mobilization` grants **+2%** on `ai = no` and `civilized = no`,
excluding whoever holds the `china` country flag:

```
python3 vic2_analyzer.py saves/ --mod-path <mod> --player-nations JAP KOR
```

A save records only the nation that took it, so in multiplayer every other human
reads as AI. Name them with `--player-nations`; the default is the save's own
player, and passing the flag with no tags disables it. It only ever changes an
uncivilized nation. In a 1836 save this reproduces Japan's in-game tooltip
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

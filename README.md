# Victoria 2 campaign analyzer

Reads a folder of `.v2` saves from the same game and turns them into per-nation
time series — population, accepted-culture share, literacy, brigades, ships by
type, industry, naval bases — as CSVs plus a single self-contained HTML report.

No dependencies. Python 3.8 or newer.

## Use

```bash
python3 vic2_analyzer.py "~/Documents/Paradox Interactive/Victoria2/save games"
```

```bash
# only some nations, custom output folder
python3 vic2_analyzer.py saves/ --out mp_campaign --tags ENG FRA GER AUS RUS

# drop microstates
python3 vic2_analyzer.py saves/ --min-pop 500000

# CSVs only
python3 vic2_analyzer.py saves/ --no-html

# print the structure of a save without analyzing it
python3 vic2_analyzer.py saves/ --peek

# cross-check unit counts against an independent scan of the raw file
python3 vic2_analyzer.py saves/ --verify
```

`--verify` counts `regiment` and `ship` blocks by raw brace nesting and compares
against what the analyzer found. If they disagree, the structured reader is
missing a nesting your saves use — that is a bug, so please report it. This
caught embarked armies: troops loaded onto transports are stored as an `army`
block *inside* the `navy` carrying them, and an early-game colonial power keeps
most of its army at sea, so reading army→regiment at one fixed depth undercounted
badly. Unit counting now recurses.

Saves are ordered by their in-game date, so filenames don't matter.

## Saves must be plaintext

Victoria 2 can write compressed saves. If you get *"does not look like a
plaintext Vic2 save"*, launch the game in debug mode and re-save. The file gets
roughly 10× bigger but becomes readable. Switching debug mode back off and
saving again returns it to normal size.

Speed is about 6 seconds and 130 MB of memory per 60 MB save. The parser streams
rather than building the whole tree, so a 150 MB save won't exhaust RAM.

## Output

| File | Contents |
|---|---|
| `report.html` | Interactive report with four tabs — Nations, Fleets, Pops, Market. Open it in a browser; it needs no server. |
| `nations_timeseries.csv` | One row per nation per save. The main table. |
| `prices.csv` | Monthly world price per good. See below. |
| `market_snapshot.csv` | Supply, demand and quantity sold per good, per save. |
| `ships_by_type.csv` | Long format: date, tag, ship type, count. |
| `brigades_by_type.csv` | Long format: date, tag, regiment type, count. |
| `technologies.csv` | Every researched tech per nation per save, with its branch and line. |
| `pops_by_type.csv` | Long format: date, tag, pop type, size. |
| `pops_by_culture.csv` | Long format, with an `accepted` flag per culture. |

`nations_timeseries.csv` columns worth knowing:

- **total_pop** — sum of pop sizes in provinces the nation owns
- **accepted_pop / accepted_pct** — pops whose culture is the primary culture or
  in the accepted list
- **avg_literacy / avg_consciousness / avg_militancy** — weighted by pop size,
  not a plain mean of pops
- **brigades** — count of regiment blocks across all armies, standing plus mobilized
- **regular_brigades / mobilized_brigades** — see below
- **mobilizing** — mobilization orders that have not spawned a brigade yet
- **is_mobilized** — 1 when the country block carries `mobilize=yes`
- **mobilization_pool** — eligible population behind the ceiling: poor-strata
  non-soldier pops of an accepted culture, in unoccupied non-colonial provinces
- **mobilization_pops** — how many pop entries that pool is split across. This
  is what makes two nations of equal population mobilize differently: the more
  the pool is fragmented, the more often a large pop flushes what the small ones
  had gathered — see below
- **mobilization_brigades** — the ceiling itself
- **prestige** — the country's prestige score, read straight from the save
- **ships** — count of ship blocks across all navies
- **factory_levels** — summed levels of all state buildings
- **ports / naval_base_levels / max_naval_base** — naval base coverage, depth,
  and the single largest base
- **pop_poor / pop_middle / pop_rich** — strata rollups
- **pop_farmers**, **pop_craftsmen**, … — all twelve pop types

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

## Great powers

Below the map, the eight great powers of the selected save, in rank order, with
their flag and prestige.

Both come straight out of the save. A save carries a `great_nations` list --
eight 1-based indices into the country array `common/countries.txt` defines --
and it is the game's own ranking: across this campaign Turkey drops out between
1888 and 1908 and the United States enters, and the order is not prestige order
(Italy outscores Britain on prestige in 1908 and still ranks second). `prestige`
is a top-level country field, read directly.

Flags come out of the mod's own `gfx/flags/*.tga`, converted to PNG and inlined
as data URIs -- about 2.4 KB a flag, 26 KB for a campaign, and 10 ms to decode.
Which variant a nation flies follows `flagType` in `governments.txt`, so a
communist Russia flies the communist flag, and one image is kept per tag and
variant rather than per save. The mod's folder wins over the base game's, which
is how a mod replaces a flag without shipping all 1,300. Vic2 flags are TGA in
four shapes -- run-length encoded or not, 24 or 32 bit -- and all four are read;
the five 8-bit greyscale files fall back to a plain colour chip.

**Industrial and military score are not in a save.** Nothing resembling them
appears in any country block or anywhere else in the file; the engine derives
both at runtime. Rather than print a guess beside two exact numbers, the cards
carry the real quantities instead -- factory levels, brigades and ships -- all
of which are counted from the save. If you want the game's own two numbers they
have to be read off the in-game ledger.

## Picking nations

Every chart that compares nations uses a searchable dropdown rather than a wall
of tags: type into it to filter by tag or by name, and use the **Players**,
**Top 8 by pop**, **All** and **None** presets.

With `--mod-path`, country names come from the mod's own `localisation/*.csv`,
which is where the game gets them, so every tag gets its proper name — including
total conversions that rename everything. Two details are handled because the
game handles them:

- **Names depend on government.** A bare `TAG` is overridden by
  `TAG_<government>` where one exists. IGoR's PBC is "Peru-Bolivia" plainly but
  **"Andine Federation"** while it is a democracy, and the report shows the
  latter. Where a series of saves spans a revolution, the name follows the
  government the nation ended on.
- **The first definition of a key wins**, not the last. IGoR defines
  `PBC_democracy` twice, as "Andine Federation" in its country pack and "The
  Andean Republic" in a later file, and the game shows the first.

Without `--mod-path` there is nothing to read and tags stand in for names.

`DEFAULT_PLAYER_TAGS` in `vic2_analyzer.py` is the list behind the **Players**
preset, which is also the default selection — a convenience for one campaign
rather than data, so it is the one name list still written by hand. Override it
for a single run without editing anything:

```bash
python3 vic2_analyzer.py saves/ --players ENG FRA GER RUS USA JAP
```

## What each tab holds

**Nations** — any measure plotted over time for the nations you pick, plus a
standings table at the last save.

**Military** — head-to-head comparison at one save. Each side takes a *group* of
nations, so USA + Austria-Hungary against Germany is a single comparison. Two
views:

- **Totals** — one pie, one slice per side, for the plain "who has more"
  answer. Hovering a side breaks its number down by member nation.
- **Composition** — two pies split by unit type. Hovering a slice reports that
  type for *both* sides with the ratio between them.

The Army/Navy button switches both views between land regiments and naval hulls.
Below that, a sortable overview across the nations you select — brigades, ships,
army and navy tech counts, soldier pops and soldier pops as a share of
population — and a technology matrix listing every army and navy tech in
research order with a column per nation. Both tables scroll sideways with the
label column pinned, and technology columns are ordered by military tech so the
nations worth reading sit nearest the labels.

**Fleets** — three views. *Compare navies* plots one hull type (or all ships)
across nations over time. *Fleets at ⟨save⟩* is a table of every nation's navy
with a column per hull type, sortable. *Fleet composition* stacks one nation's
hull types over the campaign.

**Pops** — *Pops at ⟨save⟩* is a table of every nation with total population,
accepted share, literacy, militancy, consciousness and a column per pop type;
the Counts/Shares button switches the pop-type columns between absolute numbers
and percentages. Clicking a row loads that nation into the culture breakdown
below it and into the composition chart.

**Market** — price history and the market snapshot, described next.

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

The knobs survive for experimentation but no longer need touching:

- `--mob-model` — `measured` (default) is the rule above. `cascade`,
  `province-levy`, `short-share`, `threshold` and `plain` are the earlier fitted
  models, kept so the comparison can be re-run.
- `--mob-pool-factor` (default 1.0) — scales manpower before the arithmetic.
  This was 0.94 while the flush was unknown, absorbing the 6%; it is now inert.
- `--mob-grouping` — whether the first stage truncates per pop entry (`pop`,
  default) or per pop type per province (`province-type`). Only `pop` matches
  the game, since pooling is per pop.

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

## Caveats

**Pop IDs are not stable across saves.** Pops merge, split, promote and demote,
so a pop ID vanishing between saves usually means it was absorbed into another
pop of the same type, culture and religion in the same province — not that
anyone died. Everything here aggregates before comparing, which is why it's
safe. If you extend the tool, don't join on pop ID.

**Ship and pop types are read from the save, not from a fixed list.** Mod-added
hull types appear under their own names automatically. Mod-added *pop types*
won't, since the twelve vanilla types are hardcoded in `v2parse.py`; add yours
to `POP_TYPES` there.

**Factory counts assume `state_buildings` blocks sit inside `state` blocks
inside the country block.** If a mod restructures that, factory columns come out
zero while everything else stays correct. Run `--peek` to see what's actually in
your saves.

**Country tags are detected by shape** — three characters, first one an
uppercase letter. That catches vanilla tags and dynamic ones like `D01`. Tags
with no provinces and no population are dropped, which removes rebel and
uncreated-nation stubs.

## Files

- `vic2_analyzer.py` — CLI, aggregation, CSV output
- `v2parse.py` — Clausewitz tokenizer and streaming parser
- `report.py` — HTML report data prep
- `template.py` — the report's HTML, CSS and JavaScript
- `mod_reader.py` — reads the mod: defines, poptypes, inventions, parties,
  modifiers and localisation
- `tech_groups.py` — which techs count as army or navy, and their research lines
- `tests/make_campaign.py` — generates fake saves to test against

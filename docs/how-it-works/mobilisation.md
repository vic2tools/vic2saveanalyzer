# Mobilized brigades

Mobilized brigades: the mobilization pool, the rate and its modifiers, and what is not modelled.

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

## The mobilization pool

The in-game "Brigades to Mobilize" figure is **not stored in the save** — the
game derives it at runtime, so it has to be recomputed from the pops. Two things
go into that: how big each nation's mobilisation size is, and how the engine
turns population into brigades. The first is exact. The second is a calibration.

### Mobilisation size is read out of the save

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

### Triggered modifiers have to be judged, not looked up

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

### Uncivilized nations, and who was human

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

### Day one is not trustworthy

The figure the game shows on the very first day of a start date can disagree
with the figure it shows on day two, without anything in the save changing that
would explain it. A fresh 1836 game played as Japan showed 30 on 1836.1.1 and 27
on 1836.2.1; the model reads 27 from the day-two save. The engine appears not to
have run the calculation yet on day one.

Take readings from day two onwards. This matters mainly for controlled
experiments, which naturally get read at the start date -- worth stepping a day
before reading, and worth re-reading anything surprising a day later.

### Who is eligible

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

### The arithmetic, measured

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

There is one rule, not a choice of fitted models. The command line has the
machinery for checking it rather than changing it: `--explain-mob TAG` prints every technology,
invention and modifier contributing to a nation's mobilisation size, and
`--explain-mob-pool TAG` prints the pool itself -- eligible pops, and what
colonial, occupied and non-accepted provinces cost it.

### Dead ends worth recording

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

### Which layer a pop type sits in is the mod's business too

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

### What is not modelled

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

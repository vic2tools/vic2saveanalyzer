# Fleet power

Fleet power: the figure the Military tab ranks navies by, and how it was checked against the game.

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

## The design figure, and the fleet as it stands

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

## The ordering was checked against the game

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
`--check-inventions` counts as impossible. `commerce_raiders` is the same story:
gated on `steamers`, and handed to anyone who starts with the ships. The
residue is the engine granting inventions outside the tech tree.

Ship stats were read off the naval panel at the same time and matched the unit
files exactly, and an invention spawned into an Ottoman save moved every combat
hull by +2 gun power while leaving both transports alone -- the mod writes
`navy_base` +1 and a matching -1 for each transport, and the two cancel.

That the ordering is right is also checkable from the files alone, and it was
worth checking first, because a mis-decode hands a nation some other
invention's gun power. Narrow the `--check-inventions` count to the inventions that touch a
ship and shift the base a step either way:

| | -2 | -1 | **as decoded** | +1 | +2 |
|---|---|---|---|---|---|
| IGoR | | 13.6% | **0.1%** | 37.9% | 53.2% |
| Divergences of Darkness | 41.2% | 33.9% | **6.8%** | 51.7% | 68.3% |
| Ferrum Mare | 47.9% | 23.6% | **0.0%** | 70.9% | 87.3% |

An ordering that were only accidentally plausible would not do that.

## When a save is not from the build

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

So the run reports it **per save**, and names the file. An index past
the end of the array is proof that *that save* was written by a different build,
and everything read off an invention in it is short by whatever those grant. A
warning that blamed `--mod-path` would send you looking in the wrong
place when 28 of 29 files are fine.

## Checking the decode against the saves instead of the folder

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

## A mod that will not guess

`load_mod` returned a bare dict. Its docstring named five keys; callers read
thirty-one, which is only a documentation problem. The real problem was the
thirty-eighth.

`index_base` is the offset that turns a save's bare `active_inventions`
numbers into invention names, and it cannot be known when the mod is read: the
engine's invention array is rebuilt from the folder and then *checked against
a save*, so the base is only decidable once a campaign is in hand. The mod as
read (`Mod`, in `scanner/src/engine/rules.rs`) carries it as `index_base`, and
`settle_campaign` sets it from the campaign (`index_base_for`) before anything
asks for a rate. Until then the rate tables are not built, and asking for one
stops the run rather than answering from nothing.

After settling, `None` means the indices cannot be decoded for this campaign.
A nation is then assumed to hold every invention whose requirements it meets
-- an upper bound that overstates nations with poor luck -- and
`--check-inventions` says how well the decode fits.

## A gate that never closes

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

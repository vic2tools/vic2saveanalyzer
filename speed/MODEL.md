# The engine's data model: what it holds, what it costs, and the design that replaces it

Written in task 05 (3 Oct 2026) on `398de81`. No code in the engine changed
for it. Tasks 06-12 follow this file, in the order of their numbers (section 6
says why that order); if the code proves it wrong, fix it here and say so in
`STATUS.md`.

Raw numbers: `speed/model-census-2026-10-03.txt` (every figure below that has a
number is in it). The probe that made them: `speed/model-probe.diff`
(applies to `398de81`; a counting global allocator, a census, and
reverse-this-field switches), run as described in section 1.3. The campaign
is the 1880s one (265 saves, 9.1 GB) with its mod, on the Windows PC
(Ryzen 9 7950X). Allocation counts do not depend on the machine; times do.

## 0. What the survey found

1. **The nation fields are a quarter of what the model holds, not all of
   it.** After pass one the campaign holds 9.49 M live allocations
   (36,000 a save). `Nation` is 2.34 M of them (25%). `Meta` is 6.61 M
   (70%): `wars` 4.14 M, `province_owner` 1.35 M, `market` 1.12 M. `Held`,
   which copies a nation's techs and invention ids so the invention pass can
   read them, is 0.52 M. The first draft of the staging covered the 25%; the
   order in section 6 starts with `Meta` (tasks 06 and 07).
2. **The churn is bigger than what stays.** One save costs 221,000
   allocations in pass one on an empty cache: 85,000 reading the wars and the
   market into `clause::Tree` and back (`read_rest`), 46,000 in the
   provinces, 38,000 in the countries, 35,000 in `model::build`, 15,000 in
   `prepare`, 2,000 writing the cache entry. A warm run's cache load is
   38,000 a save. Most of `build` and `prepare` is Strings made to be
   dropped: 2.2 M for `Group.types`/`cultures`, 2.3 M for
   `mobilizable_pops`.
3. **Every name in the nation fields is one of about 600** (221 cultures,
   112 techs, 61 flags, 48 goods, 47 tags, 27 modifiers, 12 pop types, and a
   few small sets). Add the wars and the market and a whole run still has
   at most about 7,400 distinct strings. One run-wide table is small, and almost all
   of it is read-only after the first saves.
4. **Order matters in thirteen places and not in the rest** (section 3),
   found by reversing each field in turn and running the campaign. Where it
   does not matter on this campaign, the code says why, and the design keeps
   the order anyway where that costs nothing.
5. **Row carries a whole `Nation` through the walk and the page build**
   (2.34 M allocations) of which `Row::get` reads a few scalars and
   `pop_by_type`. That is dead weight, and dropping it needs no new
   representation.
6. **The design:** one run-wide name table (`Sym(u32)`), per-thread caches in
   front of it, strings kept only in the table; first-seen order kept by
   keeping the insertion-ordered containers and changing only their keys;
   alphabetical order made by sorting on the text; per-entry name tables in
   the engine cache. Section 5.
7. **The clocks agree with the counts, and add a free win** (4.2). In a warm
   rebuild, the walk waits 0.131 s for one thread to free the saves' war
   records, which is two thirds of the walk and 11% of the run; handing
   that free to a thread of its own is three lines (1.172 s to 1.042 s,
   measured). In an empty-cache run on this PC, provinces are 30% of a
   save's thread time, the countries 17%, reading the file 17% (a buffer
   copy; Windows has no mapping yet), the wars and market 7%.

## 1. How the data moves

### 1.1 Who builds what, and who carries it

```
save bytes
  country.rs  read_country        -> Country   (Strings, Vec<(String, _)>)         per country block
  province.rs read_province       -> Scan      (Counters keyed by Vec<u8>, FxMaps) per province
  model.rs    read_rest           -> Rest      (wars, market; via clause::Tree)
  model.rs    build               -> Save { meta: Meta, nations: Vec<Nation> }
                                     fold_provinces + fold_country copy the above into Nation
  finish.rs   prepare             -> Pre { meta, nations: Vec<PreNation>, chunk, held }
                                     drops the per-province tables; builds the state chunk and Held
  cache.rs    store / load           the whole Pre, by field
  rules.rs    settle_campaign        reads every Pre's Held
  finish.rs   finish              -> Spent { meta, nations: Vec<Kept>, chunk, rows: Vec<Row>,
                                     tables: PerNation, naval, supply, text: [String; 6] }
  report.rs   walk                -> Campaign { rows, ByTag tables, supply, parsed: Vec<Kept1>, book }
  report.rs   page / write_outputs   the page and the nine tables
```

The same `Country` is made by two readers: `country.rs` (the game's layout)
and `walk.rs` (a save that was reflowed). Every change to a country field is
made in both (`walk.rs:431-577` and `country.rs:560-737`).

What each hop keeps of a nation:

| hop | what is held per nation |
|---|---|
| `Nation` after `build` | everything, including the per-province tables |
| `PreNation` after `prepare` | `Nation` with `mobilizable_pops`, `population_by_state`, `soldier_pops_at`, `province_state`, `colonial_*`, `core_provinces`, `occupied_provinces` emptied; plus `buckets` |
| `Held` (beside it) | a second copy of `tag`, `tech_list`, `invention_ids`, `government` (and `record_tag` = `nat.tag`) |
| `Row.nat` after `finish` | the same `Nation` moved in, whole; `Kept` is a clone of `units_at`, `men_at`, `primary_culture`, `accepted_cultures`, `government`, `capital` |
| `PerNation`, `text`, `supply`, `naval` | copies of strings and numbers for the tables (a tech name once more per nation per save) |
| the page build | `Row::get(col)` for the columns, `r.nat.tag/total_pop/brigades/ships`, `Kept.units_at/men_at/capital/primary_culture/accepted_cultures`, `Kept1.meta` |

What `Row::get` reads of `nat` is: `tag`, `primary_culture`, `civilized`,
`provinces`, `states`, `total_pop`, `pop_noncolonial`, `brigades`,
`regular_brigades`, `mobilized_brigades`, `mobilizing`, `is_mobilized`,
`armies`, `ships`, `navies`, `factory_count`, `factory_levels`, `ports`,
the four `Num` levels, `techs`, `army_techs`, `navy_techs`, the eight
float scalars, `soldiers_noncolonial`, `life_unmet`, `starving`, and
`pop_by_type` (the `pop_<type>` columns, `finish.rs:462`). Nothing after
`finish` reads `ships_by_type`, `ship_crew`, `regiments_by_type`,
`tech_list`, `invention_ids`, `modifiers`, `country_flags`, `reforms`,
`pop_by_culture`, `goods_supply`, `accepted_cultures`, `units_at` or
`men_at` off a `Row`.

### 1.2 What the invariants are

Two pairs of fields are always written together with the same keys in the
same order, so they can be one field:

- `units_at[p]` and `men_at[p]`: `Units::at_mut` pushes both tallies for a
  location (`country.rs:413-421`, `walk.rs` the same), and every regiment adds
  its type to both (`country.rs:452-454`, `walk.rs:396-398`). The census
  agrees: 93,711 provinces and 184,945 kind entries in each.
- `ships_by_type` and `ship_crew`: `add(kind, 1.0)` and `add(kind, crew)` on
  one line pair (`country.rs:461,468`). 12,479 entries in each.

### 1.3 How the numbers were taken

Everything on `398de81` with `speed/model-probe.diff` applied in a worktree
(`~/vic2speed/rw/model05`), release build, `-j 1`, scratch `TMPDIR`:

- `VIC2_ALLOC=1`: the live allocation count and bytes at every `phase()` line.
- `VIC2_STAGES=file`: allocations by stage, counted on the reading thread
  only (so the mod's thread does not count): `read_countries`,
  `read_provinces`, `read_rest`, `build`, `prepare`, the cache store and load.
  `reallocs` are counted apart.
- `VIC2_STATS=file` (adds its own allocations, so it is not used for the stage
  counts): the census of entries per nation, the names by class, and
  **what is held**: a clone of each part, counting the allocations the clone
  makes, which is what the part holds. Each call's own `Box` is one
  allocation, so the tables below subtract one per call.
- `VIC2_PERMUTE=field,...`: reverse those fields' order in every nation or
  save just before `prepare`. `speed/permute.sh TREE FIELD...` runs the
  campaign for each and compares it with `speed/runs/11e1f21`;
  `speed/permexample.py TREE FIELD` shows where it differs.

The probe tree, with its numbers, is also the reproduction: the first thing
a stage after this one should do is run the same probes on its own
tree and put the new numbers beside these.

Baseline of the build all of this was taken on, no probe (medians; empty
scratch cache x3, warm x5, this PC; `bench.sh` does not run in this shell, so
`speed/minibench.py` did it):

| | wall | pass one ends | pass two | walked | tables written |
|---|---|---|---|---|---|
| empty cache | 2.465 s | 1.469 s | 1.593 s | 1.824 s | 2.267 s |
| warm rebuild | 1.206 s | 0.213 s | 0.352 s | 0.553 s | 1.003 s |

A second run of the stand-in, later the same day: empty cache 2.459 s, warm 1.138 s (pass one
1.475 s and 0.209 s). Differences under about 5% are noise on this PC.
This PC has 16 cores and 32 logical processors, so the engine's default is 31
workers (cores bar one); the laptop's was 15.

## 2. Every string-keyed or string-holding field

"Per nation" is over the 10,569 nation-saves (265 saves, 39.9 a save, at most
43). "Live allocs" is what the campaign holds after pass one (the
clone-count), all saves together. Types are today's.

### 2.1 `Nation`, after `prepare` (these are cached, carried and finished)

| field | type | entries a nation: mean (median, p90, max) | all | live allocs | written | read |
|---|---|---|---|---|---|---|
| `key`, `tag`, `primary_culture`, `civilized`, `government`, `capital`, `nationalvalue` | 7 x `String` | 7 | 74,000 | 73,983 | `model.rs:413,279-288` from `country.rs:573` / `walk.rs:432-436` | all over; `tag` is every table's key. `primary_culture`: `finish.rs:404,595,728,752`, `model.rs:212`, `rules.rs:469,511`, `report.rs:409`, `explain.rs:239`. `civilized`: `finish.rs:405`, `rules.rs:463,654`. `government`: `finish.rs:276,754`, `report.rs:522,1029`, `rules.rs:468`, `mod.rs:1070,1121`. `capital`: `finish.rs:755`, `report.rs:305`, `rules.rs:396`. `nationalvalue`: `rules.rs:470,638` |
| `accepted_cultures` | `Vec<String>` | 0.90 (1, 2, 6) | 9,505 | 15,052 | `model.rs:311`; `country.rs:599`; `walk.rs:471` | `model.rs:213` (`accepts`: `finish.rs:172,285,593`), `finish.rs:624,727,753`, `report.rs:408`, `explain.rs:240`, and `mod.rs:628,855`/`walk.rs:772` (pass one, from `Country`) |
| `ships_by_type` | `OMap<String, i64>` | 1.18 (1, 3, 7) | 12,479 | 23,801 | `model.rs:350`; `country.rs:461,734`; `walk.rs:408,590` | `finish.rs:662` |
| `ship_crew` | `OMap<String, f64>` | same keys | 12,479 | 23,801 | `model.rs:353`; `country.rs:468,735`; `walk.rs:411,591` | `finish.rs:666` |
| `regiments_by_type` | `OMap<String, i64>` | 2.53 (3, 4, 6) | 26,739 | 45,755 | `model.rs:347`; `country.rs:733`; `walk.rs:589` | `finish.rs:691` |
| `units_at` | `OMap<i64, OMap<String, i64>>` | 8.87 provinces (4, 24, 93), 17.50 kinds (9, 48, 142) | 184,945 | 394,041 | `model.rs:356`; `country.rs:736`; `walk.rs:592` | `finish.rs:750` (`Kept`), `report.rs:157,345` |
| `men_at` | same | same | 184,945 | 394,041 | `model.rs:356`; `country.rs:737`; `walk.rs:593` | `finish.rs:751`, `report.rs:354` |
| `tech_list` | `Vec<String>` | 44.07 (50, 81, 104) | 465,761 | 475,800 | `model.rs:340`; `country.rs:714`; `walk.rs:562` | `finish.rs:275,701`, `rules.rs:518,602,621,727,741,828,886`, `explain.rs:137,291,294,458` |
| `invention_ids` | `Vec<i64>` | 82.7 (85, 170, 230) | 874,172 ints | 10,039 | `model.rs:325`; `country.rs:641`; `walk.rs:504` | `finish.rs:275`, `rules.rs:585,612,735,772,829`, `report.rs:757`, `explain.rs:137,147,295,446` |
| `modifiers` | `Vec<String>` | 0.88 (1, 3, 5) | 9,278 | 14,726 | `model.rs:317`; `country.rs:620`; `walk.rs:487` | `rules.rs:524,642,685` |
| `country_flags` | `FxSet<String>` | 2.01 (1, 6, 14) | 21,228 | 27,045 | `model.rs:314`; `country.rs:611`; `walk.rs:478` | `rules.rs:521` (`contains` only) |
| `reforms` | `OMap<String, String>` | 0 in this campaign | 0 | 0 | `model.rs:308`; `country.rs:568`; `walk.rs:575` | `rules.rs:527,648` |
| `pop_by_type` | `OMap<String, i64>` | 9.10 (9, 11, 12) | 96,147 | 116,755 | `model.rs:244` | `finish.rs:462,617,621,714` |
| `pop_by_culture` | `OMap<String, i64>` | 16.2 (9, 41, 78) | 171,175 | 333,143 | `model.rs:247` | `finish.rs:593,595,725` |
| `goods_supply` | `OMap<String, f64>` | 18.3 (16, 35, 43) | 193,096 | 391,056 | `model.rs:318`; `country.rs:633`; `walk.rs:493` | `finish.rs:688` |
| `PreNation.tag`, `.buckets` | `String`, `Vec<i64>` (the sizes of the mobilizable pops that pass `mob_types` and `accepts`, in save order) | `buckets` is empty in 605 nations | | 10,569 + 9,964 | `finish.rs:278,293` | `finish.rs:563,573` |

An `OMap` past 12 keys keeps a second copy of every key in its hash index
(`omap.rs:72-78`), so `goods_supply`'s 193,096 entries cost 391,056
allocations: two Strings each. That is also why a plain `String` to `Sym`
change shrinks these fields by more than the entries.

Not held after pass one but made and dropped on the way, per nation and per
save (these are the pass-one churn, section 4):

| field | type | per nation: mean (median, p90, max) | all | allocs made |
|---|---|---|---|---|
| `population_by_state` | `Vec<Group>`, each `types: Vec<(String, i64)>`, `cultures: ...` | 14.5 groups (4, 47, 75); 127.8 type entries (33, 372, 631); 76.4 culture entries (17, 234, 685) | 152,959 groups; 1,350,665 + 807,818 entries | 2.16 M Strings (`model.rs:251-260`) |
| `mobilizable_pops` | `Vec<(String, String, i64, i64)>` | 106.8 (27, 292, 617) | 1,128,927 | 2.26 M Strings (`model.rs:273-275`) |
| `soldier_pops_at` | `Vec<(i64, Vec<i64>)>` | 62 provinces (19, 174, 344), 85 sizes | 654,741 inner `Vec`s | not strings |
| `core_provinces`, `colonial_provinces`, `occupied_provinces`, `colonial_level`, `province_colonial`, `province_state` | `FxSet<i64>`, `FxMap<i64, i64>` | 41.6, 18.5, 2.1, 18.5, 18.5, 64.1 | 439,218; 195,195; 22,108; 195,195; 195,195; 677,310 | hash inserts, not strings |

In `province.rs` the scanner's own `Counter` is a `Vec<Vec<u8>>` plus an
`FxMap<Vec<u8>, usize>`: `add` copies a new name twice (`province.rs:73-81`),
once per name per nation (and per group), 577 groups a save. The scanner
already interns what `mobilizable` holds (`Interner`, `province.rs:47-62`):
a per-save table of ids that `build` then turns back into two Strings an
entry.

### 2.2 `Meta`, `Market`, `War` (cached, carried to the page)

Per save: nations 39.9, `province_owner` 2,556 (2,613, 2,678, 2,703), wars
161.7, battles 782 (767, 915, 1,014), joins + leaves 1,275 (1,289, 1,335,
1,352), war side tags 646, battle unit entries 3,607, `market.current` 48,
`market.history` 1,730 (1,728, 1,728, 1,776), `market.snapshot[0..6]` 42-48.

| field | type | all | live allocs | written | read |
|---|---|---|---|---|---|
| `Meta.province_owner` | `Vec<(i64, String, String)>` | 677,310 | 1,354,885 | `model.rs:435` | `report.rs:177,231,241,405,412,1008` |
| `Meta.file`, `.date`, `.player` | `String` | 795 | 795 | `model.rs:430` | many; `date` is every table's key |
| `Meta.great_nations` | `Vec<i64>` | 2,120 | 265 | `model.rs:437`; `clause.rs:301` | `rules.rs:316` |
| `Meta.wars` | `Vec<War>` | 42,854 wars | 4,138,516 | `model.rs:496-618` | `rules.rs:324-332` (`save_world`), `report.rs:78` (moved into `Book`), `wars.rs` |
| `War.name`, `start`, `end`, `original_attacker`, `original_defender` | 5 x `String` | | | `model.rs:597-603` | `wars.rs:19-38,112-143,442-445` |
| `War.attackers`, `defenders`, `fighting` | `Vec<String>`, sorted, deduped | 171,164 tags | | `model.rs:604-606` | `rules.rs:328-332`, `wars.rs:113,154,442` |
| `War.joins`, `leaves` | `Vec<(String, String, bool)>` | 338,000 | | `model.rs:607-608` | `wars.rs:156,169` |
| `War.goals`, `War.goal` | `Vec<Goal>` (5 Strings), `FirstGoal` (3) | 561 | | `model.rs:542-615` | `wars.rs:182` |
| `War.battles` | `Vec<Battle>`: `name`, `date: Option<String>`, two `Option<Side>` (`country`, `leader`, `units: OMap<String, i64>`) | 207,296 battles; 955,959 unit entries | | `model.rs:473-487` | `wars.rs:189-197,413,650` |
| `Meta.market.current` | `OMap<String, f64>` | 12,720 | 26,235 | `model.rs:620-633` | `market.rs:38,79,117,130` |
| `Meta.market.history` | `Vec<(String, String, f64)>`: stamp, good, price | 458,352 | 916,969 | `model.rs:646-666` | `market.rs:44,82`, `mod.rs:969` |
| `Meta.market.snapshot[7]` | `[OMap<String, f64>; 7]` | 84,729 | 175,023 | `model.rs:667-672` | `market.rs:116-130` |

`Book` (`wars.rs`) folds every save's wars into one record per war, in the
walk, and keeps a clone of the last record of each name to skip an unchanged
one (`fold_save`, `wars.rs:75`): 171 wars held, 22,790 live allocations
after the walk. The saves' war records (4.14 M allocations in `Meta.wars`)
are dropped once folded, which is the 4.2 M fall between "pass two" and
"walked" in section 4.

### 2.3 What the rest of the run holds

`Row` (`finish.rs:363`: its own scalars and a whole `nat`): 2.39 M live
allocations after the walk, of which 2.34 M are the `nat`.
`Kept` (`finish.rs:481`): 0.85 M, nearly all `units_at` + `men_at` clones.
`PerNation` and the walk's tables (`report.rs:42-56`, `ByTag<_>` =
`OMap<String, OMap<String, V>>`): ships 29,580, techs 496,095, pops
127,281, cultures 202,309, ... 0.94 M in all; `supply`
(`OMap<good, OMap<date, OMap<tag, f64>>>`) 0.41 M. `Kept1.meta` carries
the saves' `Meta` for the page: 2.47 M (owners 1.35 M, market 1.12 M).
`Book` 44,098.

### 2.4 Run-level tables (small, but looked up per nation)

`Spec`: `mob_types: FxSet<String>` (probed once per mobilizable pop,
1.13 M times), `wanted`, `player_nations`, `regions: FxMap<i64, String>`,
`defines: FxMap<String, f64>`, `tech_group: FxMap<String, (String,
String)>` (once per tech per nation in `finish.rs:704`, 466 k times),
`columns`, `strata`. `Reading`: `pop_types`, `mob_types` (`Vec<Vec<u8>>`),
`reform_keys`, `army_techs`, `navy_techs`. `Mod` (`rules.rs:74-134`):
`tech_mob`, `event_mob`, `nv_mob`, `modifier_impacts`, `reform_mob`,
`mob_impacts`, `strata`, `culture_groups`, `static_mob`
(`FxMap<String, f64>`, bar `strata` and `culture_groups`, which map to a
String; looked up by a nation's names in `rules.rs:602-648,685,727`), `localisation`, `unit_kinds`,
`naval_tech_effects`, `naval_effects`, `invention_rules`. These are built
once and stay as they are in task 06; their lookups become indexed, each
stage for the names it converts (section 5.6).

## 3. Where order is observable

### 3.1 Method

For each field the probe reverses it in every nation (or save) just before
`prepare`, runs the real campaign from an empty cache, and compares every
CSV and the decoded page (`testkit/expected.page`, state chunks as text)
with `speed/runs/11e1f21`. Reversing is the cheapest permutation that
moves every order and breaks every tie. `none` (no field) is identical,
which checks the probe.

IDENTICAL means the field's order did not reach this campaign's output. The
code is then read for why, and where the order could in principle reach it,
it is kept.

### 3.2 Results

Order **reaches** the output:

| field | what decides it | real example (reference vs reversed) |
|---|---|---|
| nations in a save | first-seen: the order the provinces first name an owner (`scan.seen`) | `nations_timeseries.csv`, 1872.9.1: reference rows start USA, ENG...; reversed start ARG, BRZ... (and `brigades_by_type`, `pops_by_*`, `ships_by_type`, `technologies` all move: 51,000 changed lines in the first) |
| `units_at` outer (provinces) | first-seen, nation by nation (`report.rs:345`, `here: OMap<pid, ..>`) | `/map/armies/1873.2.1` keys: `21, 109, 43, ...` vs `2556, 216, 185, ...` |
| `units_at` inner (kinds) | `ranked.sort_by(count desc)` is stable, so ties keep first-seen (`report.rs:356`) | province 70, 1872.9.1: `hussar:1;artillery:1` vs `artillery:1;hussar:1` |
| `pop_by_culture` | `cultures.sort_by(size desc)`, stable: ties keep first-seen (`finish.rs:725`) | `pops_by_culture.csv`, USA 1872.9.1: `rajput` and `swiss` (both 60), `armenian` and `french` (both 37) swap places |
| `goods_supply` | the goods' first-seen order across the campaign (`finish.rs:688` into `supply`'s `OMap`) | `/supply` keys: `ammunition, small_arms, artillery, ...` vs `luxury_furniture, furniture, ...` |
| `population_by_state` (groups) | first-seen; sets the rows and the chunk's word numbers | the state chunks differ from `chunks[0]` on |
| `Group.types`, `Group.cultures` | first-seen; sets the chunk's `words` and the layouts | `["aristocrats","artisans","bureaucrats",...]` vs `["farmers","soldiers","officers",...]` as the chunk's first word list |
| `Meta.great_nations` | rank: the first is the strongest | `/greatPowers/1872.9.1`: `ENG, GER, FRA...` vs `SIC, RUS, KUK...` |
| `Meta.wars` | file order, which is the page's war order | `/wars[1]`: `Texan War of Independence` vs `Ottoman Restoration of Tripoli` |
| `War.battles` | file order | `/wars[4]/battles[1]` differs entirely |
| `War.goals` | file order | `/wars[146]/goals[0]/actor` `ENG` vs `AST` |
| `Side.units` (battle) | file order | `/wars[5]/battles[0]/d[3]`: `cavalry:18000;irregular:18000` vs `irregular:18000;cavalry:18000` |

Order did **not** reach the output on this campaign:

| field | why, from the code | kept in the design? |
|---|---|---|
| `accepted_cultures` | sorted for the CSV column (`finish.rs:624`); the rest is `any`/membership | order free; a sorted `Vec<Sym>` is fine |
| `ships_by_type`, `regiments_by_type`, `pop_by_type` | sorted by name before output (`finish.rs:662,691,714`); `stratum` sums ints | the sort stays, on the text |
| `ship_crew`, `men_at` (both levels) | looked up by key only (`finish.rs:666`, `report.rs:354`) | folded into their partners (5.3) |
| `tech_list`, `invention_ids`, `modifiers`, `reforms` | sorted for the CSV (`tech_list`); for the rates they feed `py_sum`, a Neumaier sum, in list order (`rules.rs:602-648`): the last bit can move with order, and did not move any rounded figure here. `reforms` is empty in this campaign, so its row says nothing | **kept in order**: it is free |
| `mobilizable_pops` | `brigades_from_clusters` carries `pooled` from bucket to bucket (`finish.rs:571-588`), so order is observable in principle; reversing moved nothing here | **kept in save order** |
| `soldier_pops_at` (outer and inner) | `brigade_cap` adds ints (`finish.rs:121-143`) | order free |
| `country_flags` | `contains` only | a sorted `Vec<Sym>` or a bitset |
| `Meta.province_owner` | every reader keys by province id or builds a set (`report.rs:231-253,405,1008`) | order free |
| `War.joins`, `leaves` | read into `join_dates: OMap<(String, bool), String>` by key (`wars.rs:156,169`) | kept in order |
| `Market.current`, `.history`, `.snapshot` | dates and goods are sorted for every output (`market.rs:52,62,89,122`); history's first-wins per (stamp, good) only matters for a repeated stamp in one save | kept in order |

### 3.3 The rules for the design

- A map the output iterates in first-seen order keeps its insertion order:
  `units_at`, `goods_supply`, `pop_by_culture`, `Group.types`/`cultures`,
  `population_by_state`, `Side.units`.
- A list sorted by text for output is sorted on the text, never on an id.
  `Sym` has no `Ord`; `names::cmp(a, b)` compares the strings.
- A `Vec<Nation>` is in first-seen order and stays.
- A hash container keyed by `Sym` is never iterated to produce output. Its
  order moves with the ids, and the ids move from run to run (5.2).
- A tie in a stable sort is broken by the order of the vector sorted: no
  change of representation may reorder that vector.

## 4. Allocation counts

All from the probe, `-j 1`, this thread's allocations (the mod's thread and
the page are not in the stage counts).

**Pass one, empty cache, per save** (265 saves):

| stage | allocs | reallocs | frees | MB allocated |
|---|---|---|---|---|
| `read_countries` (`country.rs`) | 38,073 | 5,374 | 23,157 | 9.1 |
| `read_provinces` (`province.rs`) | 45,562 | 7,747 | 15,546 | 12.9 |
| `read_rest` (wars, market) | 85,208 | 3,110 | 65,073 | 5.9 |
| `model::build` | 35,151 | 721 | 663 | 2.8 |
| **read + build** | **204,000** | 16,962 | 149,000 | 31.5 |
| `prepare` | 14,541 | 507 | 33,095 | 2.1 |
| cache store | 2,361 | 1 | 2,361 | 1.4 |
| **total** | **221,000** | 17,470 | 184,800 | |

Net: each save leaves 36,000 live allocations behind. A save's file is 34 MB;
the reader allocates 31.5 MB for it.

**Cache load, warm run, per save:** 38,200 allocations (225,092 reallocs in
all), 2.5 MB. The load runs on every thread: 0.213 s for the campaign on this
PC.

**Live allocations, whole process** (the mod and the page included; empty
cache, then warm):

| phase | empty cache: allocs, MB | warm: allocs, MB |
|---|---|---|
| pass one done | 9,614,015; 687.6 | 9,535,387; 484.3 |
| pass two done | 11,340,981; 837.3 | 11,262,353; 636.9 |
| walked | 7,182,822; 557.5 | 7,182,819; 451.5 |
| tables written | 7,876,401; 593.6 | |

An empty-cache run holds 200 MB more at the end of pass one than a warm one
for the same 9.5 M allocations. Mostly that is the slack in `Vec`s grown a
push at a time, which the cache load sizes exactly (not measured apart; the
mod read from its files rather than from its cache is some of it). Pass two itself makes 4.97 M
allocations (18,800 a save) and leaves 1.7 M more behind; the walk drops
4.2 M (the saves' war records) and keeps the rest. 7.9 M live allocations
and 594 MB are what the process hands the kernel at exit (task 02 measured
60-80 ms between the last line and the process going, on the laptop).

**What the 9.49 M held after pass one are:**

| part | live allocs | share |
|---|---|---|
| `Meta` | 6,612,688 | 69.7% |
| of which `wars` | 4,138,516 | 43.6% |
| `province_owner` | 1,354,885 | 14.3% |
| `market` | 1,118,227 | 11.8% |
| `Nation`s | 2,339,038 | 24.6% |
| `Held` | 517,546 | 5.5% |
| `PreNation.tag`, `.buckets` | 20,533 | 0.2% |
| chunk | 265 | |

**After the walk** (7.18 M): `Row`s 2,386,862 (their `nat` 2,339,039),
`Kept1`s 3,320,113 (`meta` 2,474,173: owners 1,354,886, market 1,118,228;
`Kept` 845,676), the per-nation tables 939,637, `supply` 412,547, `Book`
44,098, naval 12,035.

### 4.2 Where the time goes

Taken after the counts, to rank the stages by what they can buy and not only by
what they hold. The probe's clocks (`VIC2_TIMES`, no counting) time each stage
on the thread that runs it; raw tables in `speed/model-census-2026-10-03.txt`
sections 8-11.

**Empty cache, a save's thread time, one thread alone and the default 31
workers** (the median of three runs):

| stage | alone ms | share | 31 workers ms | share |
|---|---|---|---|---|
| load the file (read into a buffer) | 5.0 | 9.3% | 27.9 | 17.1% |
| `top_level_blocks` | 4.9 | 9.0% | 10.3 | 6.3% |
| countries (`country.rs`) | 10.7 | 19.8% | 28.2 | 17.3% |
| provinces (`province.rs`) | 19.8 | 36.6% | 48.0 | 29.5% |
| wars and market (`read_rest`) | 3.9 | 7.1% | 12.0 | 7.3% |
| `model::build` | 2.4 | 4.4% | 8.5 | 5.2% |
| `prepare` | 4.6 | 8.5% | 13.2 | 8.1% |
| cache store | 1.7 | 3.2% | 7.6 | 4.7% |
| the rest of a read | 1.1 | 2.1% | 7.2 | 4.4% |
| one save | 54.1 | | 162.9 | |

At 31 workers a save costs three times the thread time it costs alone, and the
parts that allocate or move most grow most (the file load 5.6x, the cache store
4.4x, `build` 3.5x, `read_rest` 3.1x, against provinces 2.4x): the allocator
and the file cache are shared. That is the case for fewer allocations, and
the case against reading the wars through a `Tree` first; it is also why the
file load, which the model does not touch, is as big as the countries.

**A warm rebuild, the engine's phases** (wall seconds, median of three; the
whole run is 1.17 s, so about 0.2 s is outside the engine):

| phase | s | what the model touches |
|---|---|---|
| pass one (the cache load) | 0.22 | everything the entry holds: 38,200 allocations a save, `Meta` 70% of them |
| settle | 0.050 | one thread: the tech sets 12 ms, `index_base_for` 37 ms: `Held`'s Strings |
| pass two | 0.081 | 1.56 s of thread time, of which `rate_for`, `impact_for`, `naval_profile` 0.50 s |
| the walk | 0.197 | the Book's fold 0.066 s, then **freeing the saves' war records 0.131 s**; `walk_tables` 0.070 s runs beside |
| the map | 0.131 + 0.044 + 0.015 | the raster and spots (the mod's), the owners (`province_owner`'s Strings), the capitals |
| the payload's sections | 0.139 | strings of every table |
| gzip, the page, the tables | 0.09 | |

**The free in the walk, three ways** (a warm rebuild, six interleaved rounds,
medians; `VIC2_WARDROP` in the probe):

| | wall | the walk | heap peak |
|---|---|---|---|
| as it is | 1.172 s | 0.197 s | 666.8 MB |
| the free on a thread of its own, not waited for | 1.042 s | 0.069 s | 666.8 MB |
| `mem::forget` | 0.999 s | 0.068 s | 856.0 MB |

The walk takes the saves' war records out of `Spent` and hands them to the
thread that folds them into the `Book`; when it has folded them it drops them,
4.1 M allocations, and the walk's scope waits for it. Nothing needs them
after the fold. A thread of its own that nothing waits for costs no memory;
forgetting them is quicker still and holds 189 MB more at the peak. Task 07
makes the free cheaper at its source (4.1 M allocations to about 1 M); until
then it is a three-line change that is worth more to a warm rebuild than any
stage of the model.

## 5. The design

### 5.1 What it does, in one paragraph

Every string that a nation or a save holds, and that comes from a
vocabulary (names, tags, cultures, techs, goods, dates, leaders, battle
names), becomes a `Sym(u32)`: an index into one run-wide, append-only table
that holds each string once. The containers around them keep their shape and
their order; only the key and the string types change. Output order that
came from the text is made by sorting on the text. Strings come back only
where something is written: a CSV field, a JSON string, a printed line.
The cache stores each entry's names once and the rest as indices. Then, once
the numbers show what is left, the containers themselves are flattened.

### 5.2 The name table

**One per run, shared, with a per-thread cache in front of it.** Not one per
save. The reasons, in order:

1. The vocabulary is tiny: about 600 names in the nation fields, at most about 7,400
   with the wars, the market's stamps and the mod's names. A table that size
   is read-only after the first saves.
2. A per-save table would make `Sym` mean nothing without the save it came
   from. The walk, `Book`, the `ByTag` tables, `Kept1`, `Row` and the page
   all join saves; every join would translate, and every accessor would need
   the right table.
3. The reader already interns per save (`Interner` in `province.rs`) and
   then builds a String per use; the run-wide table is the same idea one
   level up.

```rust
// names.rs (new)
#[derive(Copy, Clone, PartialEq, Eq, Hash)] pub struct Sym(u32); // 0 is ""; no Ord, on purpose
pub fn intern(latin1_bytes: &[u8]) -> Sym;   // a save's bytes, decoded as `latin1` does
pub fn intern_str(s: &str) -> Sym;           // the mod, the spec, the cache
pub fn text(s: Sym) -> &'static str;
pub fn cmp(a: Sym, b: Sym) -> std::cmp::Ordering;   // by text
```

- The table is a `Mutex` over `Vec<&'static str>` and `FxMap<&'static str,
  u32>`. Strings are leaked: the process ends by forgetting the campaign
  (task 02) and a `--cross` run is a few campaigns, so nothing is lost by it.
- Each thread has a cache `FxMap<Vec<u8>, Sym>` (bytes to id) and a mirror
  `Vec<&'static str>` of the table. `intern` is a hash and a compare on a hit,
  with no lock, no allocation and no copy of the save's bytes; a miss takes
  the lock once, and the name is then in that thread's cache for good.
  `text` is an index into the mirror, topped up from the table the first time
  a thread meets an id from another thread.
- The readers pass `&[u8]` slices of the save to `intern`; `Tally`'s
  `FxMap<&[u8], usize>` becomes a `FxMap<Sym, usize>` or, for the 1-12 kinds a
  nation usually has, a linear scan of a `Vec<Sym>`.
- Ids are assigned in the order threads first meet names. **They differ from
  run to run, and no output, cache key, hash order or sort may depend on
  them.** `Sym` has no `Ord`; `.0` is used only in `names.rs`; the cache
  never stores a run's ids (5.5). To prove it, a debug knob
  `VIC2_ENGINE_NAMES_SHIFT=k` interns `k` placeholder names first, which moves
  every id and every `FxMap<Sym, _>`'s order; task 06 adds it, and the suite
  and the reference comparison run once with it on.
- `Names` for the mod's own tables: the mod is read while the saves are
  (`mod_job`), so its names get ids during pass one; after pass one the
  table is complete, and 5.6 builds the dense lookups from it.

### 5.3 What replaces each field

`OMap<K, V>` stays (`omap.rs`) with `K = Sym`: it is already first-seen
ordered, `Clone`, and indexed past 12 keys; with 4-byte keys the index copy
costs nothing. It is the mechanical first step of every stage. The second
step, where a count below shows it is worth it, is a flat `Vec`.

| field | now | after the first step (`Sym`) | flattened (where it pays) |
|---|---|---|---|
| `key`, `tag`, `primary_culture`, `civilized`, `government`, `capital`, `nationalvalue` | `String` | `Sym` | |
| `accepted_cultures` | `Vec<String>` | `Vec<Sym>` | |
| `ships_by_type` + `ship_crew` | two `OMap<String, _>` | one `Vec<Ship { kind: Sym, count: i64, crew: f64 }>` (same keys, same order: 1.2) | |
| `regiments_by_type` | `OMap<String, i64>` | `OMap<Sym, i64>` (a `Vec<(Sym, i64)>`, at most 6) | `Vec<(Sym, i64)>` |
| `units_at` + `men_at` | two `OMap<i64, OMap<String, i64>>` | one `Vec<(pid, OMap<Sym, (n, men)>)>` | one `Vec<Stack { pid, kind: Sym, n, men }>`, grouped by province, in first-seen order: 1 allocation a nation, not 2 + 4 a province |
| `tech_list` | `Vec<String>` | `Vec<Sym>`, in order | |
| `invention_ids` | `Vec<i64>` | unchanged | |
| `modifiers` | `Vec<String>` | `Vec<Sym>`, in order | |
| `country_flags` | `FxSet<String>` | sorted `Vec<Sym>` | |
| `reforms` | `OMap<String, String>` | `Vec<(Sym, Sym)>` | |
| `pop_by_type`, `pop_by_culture`, `goods_supply` | `OMap<String, _>` | `OMap<Sym, _>` | `Vec<(Sym, _)>` while it is built (`Counter` is already that); the index only past 12 |
| `mobilizable_pops` | `Vec<(String, String, i64, i64)>` | `Vec<(Sym, Sym, i64, i64)>` (`build` stops making Strings) | |
| `Group` | `types`, `cultures`: `Vec<(String, i64)>` | `Vec<(Sym, i64)>` | all of a nation's groups in one `Vec<(Sym, i64)>` with a range each |
| `Held` | a copy of `tag`, `tech_list`, `invention_ids`, `government` | **gone**: the invention pass reads `PreNation.nat` through a slice of references | |
| `Row.nat` | the whole `Nation` | **gone**: a `RowFacts` of what `Row::get` reads (1.1), `pop_by_type` included | |
| `Kept` | clones of `units_at`, `men_at` and four strings | moved out of the nation, not cloned | |
| `PerNation`, `supply`, `naval` | `String`s | `Sym`s | |
| `Meta.province_owner` | `Vec<(i64, String, String)>` | `Vec<(i64, Sym, Sym)>` | |
| `Meta.market` | `OMap<String, f64>` x 8, `history: Vec<(String, String, f64)>` | `OMap<Sym, f64>`, `Vec<(Sym, Sym, f64)>` (stamps are 4,403 distinct strings) | |
| `War`, `Goal`, `Battle`, `Side` | Strings throughout | `Sym` for every one of them (names, tags, dates, leaders, casus belli) | one arena of battles and one of unit entries a save |

`capital` is a province id in text (`rules.rs:396` parses it): it stays a
`Sym` so the parse and its refusal are unchanged. `civilized` stays text too
(`to_lowercase() == "yes"`).

What the first step alone is worth (a count, not a measurement; an
`OMap<Sym, V>` is 2 allocations, 3 past 12 keys, a `Vec` 1, and the Strings
go): units and ships 881 k live allocations now, about 460 k after the first
step (the inner maps are 187 k a side), about 25 k flattened; pops and
cultures 475 k now, about 60 k, 36 k; techs, goods, flags, modifiers, the
seven names and `Held` 1.52 M now, about 60 k; `Meta` 6.61 M now, about 1.14 M
after the first step (battles each keep two `units` maps), a few hundred
thousand with arenas. **In all about 9.5 M now, about 1.7 M after the first
step of every stage, 0.3-0.4 M flattened.** Stages measure their own
against these.

### 5.4 First-seen order, where it matters

Nothing about the order changes, because the containers do not: an `OMap`
or a `Vec` filled in the order the reader met things holds that order,
whatever its keys are. What changes is the places that sort. They are the
four in 3.2 (`ships_by_type`, `regiments_by_type`, `pop_by_type`,
`accepted_cultures`) and the `ByTag` types lists (`report.rs:1371-1377`);
each sorts by `names::cmp`. The two stable sorts that depend on ties
(`pop_by_culture`, `units_at` inner) sort the same vector as now.

### 5.5 The engine-cache format (`V2ENGC03`)

Finished in task 12; tasks 06-11 change the cache only as far as their
fields need, writing what they hold the way the old format would, with a
`Sym` written by its text through the entry's own string table (the
`W::s` table already in `cache.rs:75-86`).

The new format:

1. The key (as now), then the **entry's name table**: a count, then each name
   as a length and its UTF-8 bytes. Only names the entry uses, in the order
   it first met them: 100-300 of them.
2. The body, with every `Sym` as an index into that table (one varint, one
   byte nearly always). No run's id is ever written, so an entry stays valid
   whatever else a run interned, and a cache made by a run with
   `VIC2_ENGINE_NAMES_SHIFT` is the same cache.
3. Sections with their lengths in front (`Meta`, nations, chunk), so a
   reader can skip one and a cut-short entry is refused as it is now. `Held`
   is not in the entry: it is gone (5.3).
4. On load: read the table, one `intern_str` per name into a `Vec<Sym>`
   (a hash on a hit: a few hundred a save, against 38,000 allocations now), then
   decode the body through it. Container sizes are known: each `Vec` is made
   with its exact length.

The key still names the path, size, mtime, the reading and the settings,
and the program (`version`), so an old-format entry is a miss; old entries
are never read. `testkit/caching.py` holds the safety properties.

### 5.6 The mod's names, and what the lookups become

The mod's tables are `FxMap<String, f64>` looked up with a nation's names:
`tech_mob` once per tech per nation (466 k), `event_mob` per modifier,
`reform_mob`, `nv_mob`, `culture_groups`, `strata`; `Spec.tech_group` and
`Spec.mob_types` the same (466 k and 1.13 M lookups). After pass one the
name table is complete, so each stage builds dense `Vec<f64>` / bitsets indexed
by `Sym` (a few KB each, from `names::len()`) once, before pass two, for the
names it converts (task 08: pop types and cultures; task 09: techs,
modifiers, national values, reforms), and the lookups become an index. The mod's own strings are interned with
`intern_str`; a mod name with a character past U+00FF never equals a save's
latin-1 name, exactly as now.

Triggers (`Asker::condition_ok`, `rules.rs:407-535`) compare a trigger's
text with `names::text(nat.government)` and so on: an index and a compare,
no allocation, no hash. They stay on text.

### 5.7 What is dropped, not converted

- `Held` (0.52 M live allocations, and 28.5 MB, and a field of every cache
  entry): `rules::settle_campaign` and `explain.rs` read slices of
  `PreNation` instead. `held_names` (`mod.rs:1069`) too.
- `Row.nat`'s unused fields (2.34 M).
- `Kept`'s clones.
- `Group`s for nations that are not kept: `Snapshot.add` is called only for
  kept nations (`finish.rs:297`), yet `build` makes the `Group`s for all.
  Every nation is kept in this campaign, so this one is for a campaign with
  `--min-pop`; measure before doing it.

### 5.8 What this does not do

- It does not touch what is *read* from the bytes beyond the strings:
  `read_rest` parses the wars and the market through `clause::Tree` (85,000
  allocations a save, 22.6 M in all, the largest single piece of pass-one
  churn, though only 7.3% of the empty-cache thread time). Making `Meta`
  `Sym`-based (task 07) removes the Strings it ends in, not the Tree it goes
  through. Reading them straight from the bytes, as task 03 did for the
  countries, is task 11, optional.
- It does not touch the integer tables (`core_provinces`, `province_state`,
  `colonial_*`, `soldier_pops_at`): hash inserts and small `Vec`s, no strings.
  They are task 13's if the profile still shows them.
- It does not change the text of any output. Nothing here may.

### 5.9 What it should buy

Said as a bet, to be measured in tasks 12 and 13, not as a result. The pass-one
profile (CONTEXT.md, and 3 Oct on this PC) puts malloc and free at 15-21% of
a worker's time and the provinces and countries at 59%. This model touches
every allocation in `build`, `prepare` and the cache load, which is
0.213 s of a warm run on this PC, and the walk (0.20 s). The retained 590 MB
at exit should fall by about half (the strings and the `Vec` slack go), so
the kernel's teardown should shorten with it. None of this is promised; the
checks hold the output to the bytes whatever it buys.

## 6. The staging

Each stage passes the whole suite on its own, and the real campaign against
`speed/runs/11e1f21` (every CSV, the decoded page, stdout, stderr).

**The order is the order of the task files**, 06 to 12, and was decided after
this survey from the counts in section 4 and the clocks in 4.2. The first
draft of this section went units, pops, the rest, `Meta`, cache, because the
data-model plan was drawn around the nation fields; the counts say `Meta` is
70% of what is held, and the clocks say the biggest cost of a warm rebuild is
`Meta`'s too. `STATUS.md` has the reasoning in short.

| task | what | live allocs now (all saves) | what it should buy: a warm rebuild / an empty-cache run (estimates, section 4.2 is the basis) |
|---|---|---|---|
| (06's first commit) | the walk stops waiting for the saves' war records to be freed | | measured: warm 1.172 s to 1.042 s |
| **06** names, owners, market | `names.rs`, the cache's `Sym`, the shift knob; `Scan.owners` and `Meta.province_owner`; `Market`; `report.rs`, `market.rs` | 2.47 M | warm 0.05-0.07 s quicker; empty 0.03-0.05 s |
| **07** wars | `War`, `Goal`, `Battle`, `Side`, `wars::Held`, `Book`, `save_world`, `wars::build`, `explain.rs` | 4.14 M | warm 0.07-0.10 s beyond the first commit above (the cache load, the Book's fold); empty 0.01-0.03 s |
| *gate* | measure the warm rebuild's pass one (0.214 s; about 0.13 s expected). If it is above 0.17 s, the allocations are not what the load costs: re-profile before 08-10 | | |
| **08** pops and cultures | `Interner` and `Counter` in `province.rs`; `pop_by_type`, `pop_by_culture`, `accepted_cultures`, `primary_culture`; `Group`; `mobilizable_pops`; `Snapshot`; `Spec.mob_types`; `PopulationRules`; dense `strata` and `culture_groups` | 0.475 M, and about 50,000 a save of pass-one churn | warm 0.01 s; empty 0.08-0.18 s |
| **09** techs, `Held`, the rates | **`Held` gone, `Row.nat` slimmed, `Kept` moved**; `tech_list`, `modifiers`, `reforms`, `nationalvalue`; dense `tech_mob`, `event_mob`, `nv_mob`, `reform_mob`, `tech_group`; (optional: `goods_supply`, `country_flags`, the scalars) | 1.52 M, and 2.34 M carried | settle 0.050 s to about 0.02 s in both; warm 0.04 s, empty 0.04 s |
| **10** units and ships | `Ship`, `Stack`; `country.rs` and `walk.rs`; `finish.rs`, `report.rs:345` | 0.88 M | warm 0.02 s; empty 0.02-0.03 s |
| **11** wars and market from the bytes (optional) | `read_rest` without `clause::Tree` | churn 85,200 a save | empty 0.04-0.08 s |
| **12** the cache and the result | `V2ENGC03` finished; arenas only if the load is still over about 50 ms; teardown; dense lookups finished; re-measure | the cache load's 38,000 a save | warm 0.01-0.03 s |

Why this order:

1. **The plumbing goes first, on the part with the least in its way.** The
   owners and the market are order-free (reversing them moved nothing), are
   built in one place each, and have one reader of the save between them.
   Units and ships, the first draft's choice, have two readers (`country.rs`
   and `walk.rs`' own), a stable sort that depends on order, and the smallest
   payoff of the nation stages.
2. **Then the biggest warm-rebuild cost.** The saves' war records are 44% of
   what is held, a third of the walk (0.066 s of folding) and, until the first
   commit above, 0.131 s of freeing; the warm rebuild is the everyday run.
3. **Then a gate**, so that the rest is not done on an estimate: the first two
   stages carry 70% of the allocations, and if the warm load has not fallen the
   way the counts say it should, the remaining estimates are wrong too.
4. **Then the first-run lever.** Pops and cultures are what the scanner and
   `build` and `prepare` make and throw away: about 22% of a save's pass-one
   allocations, on the stage that is 30% of the thread time.
5. **Then what is left, by payoff for the work**, and the optional last: task
   11 is the lowest payoff for the work (7.3% of the empty-cache thread
   time, a reader to rewrite) and needs task 07 first, so it is last before
   the close. The scalar names (`tag`, `government`, ...) stay Strings: 74,000
   allocations and they touch everything.
6. **After 06, every stage depends on `names.rs` and on nothing else here**
   (11 also needs 07), so any of 07-11 can be dropped, or done in another
   order, without breaking the others. 12 closes.

Alternatives looked at and not taken: the nation fields first (the first
draft: small payoff, the most to do); "carry less" (`Held`, `Row.nat`) as a
stage of its own first (it saves memory and a little of the cache, not time,
and `Held` is cheaper to delete with the tech lists it copies); all of `Meta`
in one session (the plumbing and the most order-sensitive structure at once);
the typed reader before the types (it would be written twice).

Task 09 is two halves, carry-less first, and may stop between them; task 11 is
the severable one. Do not start a stage by flattening: the first commit of
each is the `Sym` change with `OMap<Sym, _>` and nothing else, so a difference
is the change of key and not the change of shape. Flatten in later commits,
each passing.

## 7. How each stage is verified

- `python3 testkit/all.py "$VIC2_SAVES" --mod "$VIC2_MOD"`: 28 of 28 hold on
  Windows (task 03b).
- The real campaign: `refrun.sh` and `cmpruns.py 11e1f21 NEW --payload`:
  IDENTICAL. The page's bytes are not the reference's (the chunks are level
  5), the decoded payload is.
- Once, with `VIC2_ENGINE_NAMES_SHIFT=7`, the same two (task 06 adds the
  knob).
- **Mutations** (`testkit/mutate.py`, a clean worktree, `--saves` and
  `--mod`). These patch files the stages edit; one that no longer applies
  after a stage is re-aimed at the new code, never dropped: in `finish.rs` `cross-min-pop`,
  `cross-player-nations-unread`, `cross-player-ignores-save`,
  `name-runs-as-script`, `chunk-stream-cut`; in `walk.rs`
  `walk-navy-not-entered`, `walk-colonies-ignored` (task 10: `count_units`
  and `Tally`); in `model.rs` `naval-base-int-becomes-float`; in `cache.rs`
  `save-key-drops-reading`, `save-key-drops-time`, `modread-kept-copy-unsigned`
  (task 12); in `rules.rs` `at-war-from-joins`; `explain.rs`
  `explain-without-wars`; `report.rs` `locked-table-not-refused`,
  `empty-table-left-stale`; `wars.rs` `goal-judged-before-first-save`; `mod.rs`
  `cut-save-read-as-whole`. `mutdry.py` (laptop) or running the mutation
  list on the new tree says which no longer apply.
- **New mutations** each stage should add, so a wrong order is caught and
  not only a wrong value: sort the market's goods by id rather than by name
  (task 06); reverse `Side.units` (07); break a stable tie in `pop_by_culture`
  and reverse `Group.types` (08); reverse `goods_supply` (09, if it is done);
  sort `ships_by_type` by id and reverse `units_at`'s inner order (10). Each of these is a change the
  reversal runs of section 3 showed the campaign notices. Where
  `speed/permute.sh` showed IDENTICAL, there is nothing to catch on this
  campaign and no mutation to add.
- **Allocations:** apply `speed/model-probe.diff` to the stage's tree (it
  needs only rebasing on `Nation`'s new fields) and put its three numbers
  (stage counts, live after each phase, and what is held) beside section 4.
  Each stage's `STATUS.md` entry has them.
- The bench (warm x5, empty cache x3) beside section 1.3's baseline. Run the
  bench on a quiet machine; `bench.sh` needs `bc`, `uptime` and `pgrep`,
  which this PC's shell lacks, so use the laptop or `speed/minibench.py TREE`
  (empty cache x3, warm x5, medians of the phases).

## 8. What this survey did not settle

- **One campaign.** 40 nations a save, 1880s, one mod. A campaign with
  more nations a save shifts the weights toward the nation
  fields and away from `Meta`; its per-nation counts are not here. The
  design does not depend on it; the order of payoff might.
- **`reforms` is empty here**, so its reversal is vacuous. Its code path is
  the same as `modifiers`'; the design keeps it in order.
- **IDENTICAL is not "free".** Section 3.2 says why for each. A different mod
  (different rates) could make a float sum's order show; the design keeps those
  orders because it costs nothing.
- **Linux and the mmap path** were not run. The allocation counts do not
  depend on how the file is read; the stage times on the laptop will differ.
- **`Group` for unkept nations** (5.7): not measured, as every nation is kept.
- **Whether arenas are needed** is for task 12 to decide from the earlier
  stages' numbers: the criterion is the warm cache load. If it is below about
  50 ms by then, leave the containers alone and spend the session on task 13.
- **The estimates in section 6 are estimates.** They scale a stage's share
  of the allocations by the stage's share of the clocks; only the first
  commit's (1.172 s to 1.042 s) was measured. Task 07's gate is there to find
  out early whether the scaling holds.

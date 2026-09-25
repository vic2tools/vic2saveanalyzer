# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""
What a nation comes to, once its save has been read.

`readsave` fills a nation record with what the save says. This turns that
record into the row the report shows: who was playing, which nations this run
measures, the mobilisation ceiling under the mod's own rules, the brigade cap,
the strata and the shares. One save at a time, wherever the save was read.

One recipe, because there used to be four. The workers, the parent, the row
loop and `--cross` each wrote the finishing out for themselves and promised
in a comment to match the others, and they did not: `--cross` divided
brigades by the vanilla 3000 while the chart above it used the mod's own
number. There is one `finish_spec` deciding what finishing is given, one
`finish_nations` doing it, and one `kept_by` saying which nations it was done
to.

`readfolder` never imports this. The finishing reaches the workers as a
`transform` handed to it, so the reader does not learn what finishing is, and
editing this file leaves the parse cache alone.

Callers outside reach `finish_nations` through the module --
`finishing.finish_nations(...)` rather than a name imported from here --
because `testkit/crossrows.py` replaces it here to watch both of its callers
finish the same save, and a caller holding its own copy of the name would
finish unwatched.
"""

from collections import namedtuple

from modrules import rate_for, save_world
from nation import (
    AS_PLAIN_DICTS,
    AS_PLAIN_DICTS_INSIDE,
    MOBILIZABLE_TYPES,
    POP_SIZE_PER_REGIMENT,
    SPENT_ON_FINALIZE,
    accepted_cultures_of,
    brigades_from_clusters,
    mobilization_clusters,
)
from readsave import STRATA
from v2parse import to_float


# What a worker needs to finish a save where it read it. A named shape
# rather than a dict of strings because it crosses a process boundary and
# is read in a loop: `spec.rate` says what it is, `spec["rate"]` says only
# that somebody hoped it would be there.
Finish = namedtuple(
    "Finish", "rate pop_per_regiment mob_types include_occupied "
              "player_nations wanted min_pop mod live keep_pools",
    defaults=(False,))


def mod_defaults(args, mod):
    """
    The two numbers a mod has an opinion about, as this run should use them.

    `defines.lua` says how many people a regiment costs and `poptypes/` says
    which pops can be mobilized, and both are defaults rather than overrides:
    they fill in what the caller left alone and give way to
    `--pop-per-regiment` and `--mob-types`.

    Worked out here and handed back rather than written into `args`, because
    `--cross` reads several campaigns under several mods and there is one
    `args` for all of them. `main` still writes the answer back -- it has the
    one mod, and the rest of a single-campaign run reads these off `args` --
    but `run_cross` cannot, and so it used not to apply them at all.

    "Left alone" is `None`, not "happens to equal the default". It used to be
    the second, and so `--pop-per-regiment 3000` was indistinguishable from
    not passing the flag: under a mod whose defines.lua said 1000, asking for
    2000 got 2000 and asking for 3000 got 1000. Somebody typing that flag is
    usually holding a modded campaign against vanilla numbers, which is the
    one thing it silently refused to do. Same for `--mob-types` named as
    exactly the vanilla three.
    """
    pop_per_regiment = args.pop_per_regiment
    mob_types = list(args.mob_types) if args.mob_types is not None else None
    defines = (mod.defines or {}) if mod is not None else {}
    if pop_per_regiment is None:
        pop_per_regiment = int(defines.get("POP_SIZE_PER_REGIMENT",
                                           POP_SIZE_PER_REGIMENT))
    if mob_types is None:
        mob_types = sorted((mod.mob_types if mod else None)
                           or MOBILIZABLE_TYPES)
    return pop_per_regiment, mob_types


def finish_spec(args, mod, live, wanted=None, keep_pools=False):
    """
    Everything finishing a save needs, decided in one place.

    There used to be two of these. `main` built one for the workers and
    `run_cross` built its own by hand for each campaign, and they disagreed
    about five things -- the mod's regiment size, whether `--mob-types` was
    read at all, which list the parse and the finishing each used, who
    counted as a player, and the smallest population worth measuring.

    The worst of them was the first. `--cross` puts a cross-campaign block in
    a report whose other charts are about one of those same campaigns, so the
    same nation appeared twice on one page with its brigades divided by 3000
    in one place and by the mod's own number in the other, and nothing said
    which was which.
    """
    pop_per_regiment, mob_types = mod_defaults(args, mod)
    return Finish(
        rate=args.mob_rate,
        pop_per_regiment=pop_per_regiment,
        mob_types=frozenset(mob_types),
        include_occupied=args.mob_include_occupied,
        player_nations=(set(args.player_nations)
                        if args.player_nations is not None else None),
        wanted=wanted,
        min_pop=args.min_pop,
        mod=mod,
        live=live,
        keep_pools=keep_pools)


def players_in(meta, nations, told):
    """
    Which tags a person was playing, in the order the answers are believed.

    What was said outright first. Then the save's own markers: every country
    a person is playing carries `human=yes` in its own block, so a
    multiplayer save names all of its players and not just whoever pressed
    save. Older saves and some mods write no such marker at all, hence the
    fall back to the save's own player.

    This decides more than a column. IGoR and GFM both pay a human-run
    nation a mobilisation size an AI does not get, so a run that answers it
    differently reports different brigade counts for the same save.
    """
    if told is not None:
        return set(told)
    played = {tag for tag, nat in nations.items() if nat.get("human")}
    if played:
        return played
    return {meta["player"]} if meta.get("player") else set()


def kept_by(spec, tag, nat):
    """
    Whether this run measures this nation.

    One definition, because three loops used to carry their own copy of it
    and a nation the report leaves out has to be left out everywhere:
    `is_player` is set on the nations that are kept and on no others, and
    the trim keeps that key only where it exists.
    """
    return ((not spec.wanted or tag in spec.wanted)
            and nat["total_pop"] >= spec.min_pop)


def finish_nations(meta, nations, spec):
    """
    One save's nations, finished: the players picked, the rest filtered out,
    and `finalize` run over what is left.

    This is the last step that reads a save whole, and it turns two megabytes
    of per-province tables into a few dozen numbers a nation. Done where the
    save was parsed it happens on every core at once and only the numbers are
    sent back; done in the parent it happens one save at a time, after the
    tables have already been pickled, piped and unpickled to get there.

    Every nation comes back -- finished where it was kept, untouched where it
    was not -- so a caller that needs to know which is which asks `kept_by`
    rather than repeating the filter and drifting away from it.
    """
    players = players_in(meta, nations, spec.player_nations)
    # What this save says about everyone, which is what the mod's triggered
    # modifiers ask about: the year, the great powers, who is at war and who
    # owns what. One per save rather than one per nation, and worked out
    # here rather than sent, because the worker has the save and the mod.
    stage = save_world(meta, spec.mod) if spec.mod else None
    out = {}
    for tag, nat in nations.items():
        if not kept_by(spec, tag, nat):
            out[tag] = nat
            continue
        nat["is_player"] = (tag in players)
        rate = rate_for(nat, spec.mod, spec.live, stage, spec.rate)
        done = finalize(nat, rate, spec.pop_per_regiment,
                        mob_types=spec.mob_types,
                        include_occupied=spec.include_occupied,
                        mod=spec.mod, world=stage)
        done["mobilisation_size"] = round(rate, 5)
        if not spec.keep_pools:
            # A nation's mobilizable pops are one entry per pop per province
            # -- eleven thousand of them for a large nation, two megabytes a
            # save -- and `finalize` copies a nation shallowly, so the
            # finished one still points at the raw pool that made it. Only
            # `--explain-mob-pool` prints that back, so every other run lets
            # it go here instead of carrying it for the whole campaign.
            done["mobilizable_pops"] = ()
        out[tag] = done
    return out


def finish_and_pack(meta, nations, spec):
    """
    `finish_nations`, and then what a save needs to cross a pipe.

    Finishing in the worker is what lets a save come back as numbers rather
    than tables, so what the finishing has spent is dropped here, and the
    counters go over as the plain dicts they already are.

    `spending.spend` calls it in the worker, before turning the save into
    its rows. That is what `readfolder` is handed as the `transform`, and
    it has to stay a plain function at the top of its module: Windows sends
    it to each worker by name, and something without one -- a lambda, a
    function inside a function -- cannot be sent, so no worker starts and
    every save is read on one core.
    """
    out = finish_nations(meta, nations, spec)
    for done in out.values():
        for name in SPENT_ON_FINALIZE:
            done.pop(name, None)
        for name in AS_PLAIN_DICTS:
            counted = done.get(name)
            if counted is not None:
                done[name] = dict(counted)
        for name in AS_PLAIN_DICTS_INSIDE:
            counted = done.get(name)
            if counted is not None:
                done[name] = {where: dict(kinds)
                              for where, kinds in counted.items()}
    return meta, out


# The engine applies no minimum pop size to *mobilization*. POP_MIN_SIZE_FOR_REGIMENT
# governs how small a *soldier* pop may be and still support a standing brigade,
# which is a different rule on a different pop type -- IGoR sets it to 1000.
#
# How the count works is in brigades_from_clusters and in the README. It was
# measured on a purpose-built test bed inside the mod rather than fitted, and
# POP_SIZE_PER_REGIMENT is the only number in it. Six earlier models -- per-pop
# truncation, a cascade up province/state/nation, a province levy, a fixed
# share of short pops, a manpower threshold, and a pooled scale factor -- were
# each fitted to in-game readings and each failed somewhere; they are gone, and
# the README records what they were and how they broke.


def brigade_cap(nat, defines, pop_per_regiment=POP_SIZE_PER_REGIMENT):
    """
    How many standing brigades a nation's soldier pops could support.

    Measured on purpose-built test beds rather than fitted, the same way the
    mobilization ceiling was. Two of them, 72 provinces each, every province
    given one soldier pop of a known size across sizes either side of every
    step, and every brigade the game would allow raised from each. The second
    bed was needed because IGoR sets its non-core multiplier to 1, which cannot
    show whether a multiplier gates anything; Modus Omnino Demens carries
    vanilla's 3, 5 and 8. All 144 cells agreed with:

        nothing                              below POP_MIN_SIZE_FOR_REGIMENT
        1 + size // (POP_SIZE_PER_REGIMENT * multiplier)   at or above it

    Two things about that are worth stating because they are not what the
    define names suggest. The minimum is a *gate* and never a deduction: a pop
    of exactly 1000 raises one brigade and a pop of 3000 raises two, where
    subtracting the minimum first would have given one. And the multipliers
    scale the step, not the gate -- a colonial pop of 1000 still raises a
    brigade, though three times the minimum would have denied it one.

    Culture does not enter into it. Pops of a culture the nation does not
    accept were measured raising exactly as many brigades as accepted ones, at
    all eighteen sizes.

    A colony is charged its own multiplier and not the colonial and non-core
    ones compounded: on the mod where those are 5 and 3, a colonial pop steps
    every 15000 rather than every 45000. `is_colonial=1` is the protectorate
    the defines name, stepping every 24000 where its multiplier is 8. The
    province's own `colonial=` is what the engine charges against, which is why
    it is read in preference to the state's.

    Real campaigns cannot be used to check this: a regiment is not disbanded
    when its pop shrinks, so counts read out of a played save describe the
    pop's history rather than its capacity.
    """
    floor = int(defines.get("POP_MIN_SIZE_FOR_REGIMENT") or 1000)
    colony = float(defines.get("POP_MIN_SIZE_FOR_REGIMENT_COLONY_MULTIPLIER") or 1)
    noncore = float(defines.get("POP_MIN_SIZE_FOR_REGIMENT_NONCORE_MULTIPLIER") or 1)
    protect = float(
        defines.get("POP_MIN_SIZE_FOR_REGIMENT_PROTECTORATE_MULTIPLIER") or 1)
    colonial = nat["colonial_provinces"]
    levels = nat["colonial_level"]
    own = nat["province_colonial"]
    cored = nat["core_provinces"]

    total = 0
    for pid, sizes in nat["soldier_pops_at"].items():
        # The province's own flag first, then the state's, since it is the
        # province the multiplier is charged against.
        level = own.get(pid) or (levels.get(pid, 2) if pid in colonial else 0)
        if level:
            mult = protect if level == 1 else colony
        elif pid not in cored:
            mult = noncore
        else:
            mult = 1.0
        step = pop_per_regiment * mult
        for size in sizes:
            if size >= floor:
                total += 1 + int(size // step)
    return total


def finalize(nat, rate=1.0, pop_per_regiment=POP_SIZE_PER_REGIMENT,
             mob_types=MOBILIZABLE_TYPES, include_occupied=False, mod=None,
             world=None):
    """Derive the ratios that need the totals first."""
    total = nat["total_pop"]
    accepted_set = accepted_cultures_of(nat)
    primary = nat["primary_culture"]

    accepted_pop = sum(
        size for cul, size in nat["pop_by_culture"].items() if cul in accepted_set
    )
    primary_pop = nat["pop_by_culture"].get(primary, 0)

    buckets, pool_stated, entries = mobilization_clusters(
        nat, mob_types, include_occupied)
    brigades = brigades_from_clusters(buckets, rate, pop_per_regiment)

    out = dict(nat)
    out["life_unmet_pct"] = round(100.0 * nat["life_unmet"] / total, 3) \
        if total else 0.0
    out["starving_pct"] = round(100.0 * nat["starving"] / total, 3) \
        if total else 0.0
    # A nation can stand above what its pops now support, because a brigade is
    # not disbanded when the pop that raised it shrinks. Reported as the larger
    # of the two: a cap under the standing army is not a cap the nation is held
    # to, it is only a statement that it cannot recruit any more, and every
    # reading of it -- headroom, total potential, the head-to-head -- wants the
    # number the nation can actually field.
    out["brigade_cap"] = max(
        brigade_cap(nat, (mod.defines if mod else None) or {}, pop_per_regiment),
        nat["regular_brigades"])
    out["mobilization_pool"] = pool_stated
    out["mobilization_pops"] = entries
    # A nation already mobilized has (some of) its ceiling standing in the army
    # or in the queue; only the remainder is still potential. This is what stops
    # mobilized brigades from being counted twice in "total potential".
    # `start_mobilization` limits a mobilization to
    #     floor(max(standing regiments, MIN_MOBILIZE_LIMIT) x (1 + impact))
    # where impact is the ruling party's war policy plus every national modifier
    # that moves mobilization_impact. The save stores the party as a 1-based
    # index into the engine's global party list, which `party_sequence` rebuilds,
    # and stores active event modifiers by name.
    #
    # Both halves are measured against China, whose army is small enough for the
    # cap to bind. 1890: 8 standing, a pro-military party, no modifiers, and the
    # game offers 8 x (1 + 3) = 32 of a 95-brigade ceiling. 1908: 6 standing, the
    # same policy but a communist government carrying totalitarianism_modifier at
    # -0.2, and the game's own tooltip reads "280.0%" and offers
    # floor(6 x 3.8) = 22 of a 1056-brigade ceiling.
    policy = ""
    cap = 0
    if mod:
        table = mod.party_sequence or ()
        index = int(nat.get("ruling_party") or 0) - 1
        if 0 <= index < len(table):
            policy = table[index][3]
        impact = (mod.mob_impacts or {}).get(policy)
        if impact is not None:
            # Event modifiers, which the save lists by name, plus triggered
            # ones, which it does not and which have to be judged from their
            # own triggers.
            from modrules import impact_for
            impact += impact_for(nat, mod, world)
            floor_ = int(to_float((mod.defines or {}).get(
                "MIN_MOBILIZE_LIMIT", 3), 3))
            cap = int(max(nat["regular_brigades"], floor_) * (1.0 + impact))
    out["war_policy"] = policy
    out["mobilization_cap"] = cap
    # What the game will actually offer: the pop ceiling, held down by the cap.
    out["mobilization_available"] = min(brigades, cap) if cap else brigades
    # Ceiling minus what is already standing. For a nation that mobilized a
    # while ago this is pop GROWTH since it mobilized, not something the game
    # will let it raise -- Victoria 2 does not top up a mobilization.
    out["mobilization_remaining"] = max(
        0, brigades - nat["mobilized_brigades"] - nat["mobilizing"])
    # `rate` is the country's mobilisation size modifier, which the save does
    # not store, so it is a parameter.
    out["mobilization_brigades"] = brigades
    out["accepted_pop"] = accepted_pop
    out["primary_culture_pop"] = primary_pop
    out["accepted_pct"] = round(100.0 * accepted_pop / total, 2) if total else 0.0
    out["avg_literacy"] = round(nat["literacy_weighted"] / total, 5) if total else 0.0
    out["avg_consciousness"] = round(nat["con_weighted"] / total, 4) if total else 0.0
    out["avg_militancy"] = round(nat["mil_weighted"] / total, 4) if total else 0.0
    # Which pop types sit in which layer is the mod's business, not a
    # constant: GFM and Divergences of Darkness add poor-strata `serfs`, IGoR
    # and Ferrum Mare rich `bankers`. Counted against the vanilla list those
    # people simply vanished -- Ferrum Mare's LCT is 98% bankers and read as a
    # nation of two thousand.
    layers = (mod.strata if mod else None) or {}
    if layers:
        for stratum in STRATA:
            out[f"pop_{stratum}"] = sum(
                size for t, size in nat["pop_by_type"].items()
                if layers.get(t) == stratum)
    else:
        for stratum, types in STRATA.items():
            out[f"pop_{stratum}"] = sum(nat["pop_by_type"].get(t, 0) for t in types)
    # Soldiers in a colonial state support no brigade, so the soldier pops that
    # matter to an army are the ones in stated land. The share is taken against
    # the whole nation, colonies included: a soldier base of five million reads
    # differently under fifty million people than under two hundred.
    colonial = nat["colonial_provinces"]
    stated = sum(size for pid, size in nat["soldiers_at"].items()
                 if pid not in colonial)
    out["soldiers_noncolonial"] = stated
    out["soldiers_noncolonial_pct"] = (
        round(100.0 * stated / total, 3) if total else 0.0)
    # Literacy the same way. A colony's pops are counted in the national average
    # and drag it down without saying anything about the metropole -- Britain
    # reads one way with India in the figure and another without. This is the
    # same restriction the soldier measure above uses, so the two agree about
    # what "our own states" means.
    home_pop = sum(size for pid, size in nat["pop_at"].items()
                   if pid not in colonial)
    home_literate = sum(v for pid, v in nat["literacy_at"].items()
                        if pid not in colonial)
    out["avg_literacy_stated"] = (
        round(home_literate / home_pop, 5) if home_pop else 0.0)
    out["pop_noncolonial"] = home_pop
    return out

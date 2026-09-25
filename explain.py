#!/usr/bin/env python3
"""
The four flags that print something about one nation and stop.

`--explain-mob-pool`, `--check-inventions`, `--inventions` and
`--explain-mob` each answer a question about a campaign that has already
been read, print it, and end the run. None of them writes a report, none
of them touches the tables, and none of them is reached by a run that is
building anything -- which is why a hundred and sixty lines of them sat at
the bottom of `main` being skipped, and why they are here now.

"""

import os
import sys
from collections import defaultdict

from nation import (accepted_cultures_of, brigades_from_clusters,
                    mobilization_clusters)
from modrules import save_world


def explain_mob_pool(tag, nat, meta, rate, args):
    """
    Show where a nation's mobilization pool comes from and what it is worth.

    The interesting number is not the ceiling but the gap between the two
    grouping models: they agree exactly when every province holds one pop per
    poor type, and diverge in proportion to how many cultures those pops are
    split across. That gap is the cost of truncating each pop separately.
    """
    mob_types = frozenset(args.mob_types)
    accepted = accepted_cultures_of(nat)
    occ = args.mob_include_occupied
    per_pop, pool, entries = mobilization_clusters(nat, mob_types, occ)
    # The other grouping the engine might have used: one bucket per province
    # and pop type rather than one per pop. It is not an option any anymore --
    # the engine groups per pop -- but the gap between the two is the whole
    # point of this readout, so it is rebuilt here from the same buckets.
    merged, first = defaultdict(int), {}
    for province, state, poptype, size in per_pop:
        key = (province, poptype)
        first.setdefault(key, (province, state, poptype))
        merged[key] += size
    per_pt = [first[k] + (v,) for k, v in merged.items()]

    dropped = defaultdict(int)
    # Pops of a culture the nation does not accept are dropped as the save is
    # read, so what they came to is carried as a total rather than recounted.
    if nat.get("mob_excluded_culture"):
        dropped["non-accepted culture"] += nat["mob_excluded_culture"]
    for poptype, culture, size, province_id in nat["mobilizable_pops"]:
        if poptype not in mob_types:
            continue
        if culture not in accepted:
            dropped["non-accepted culture"] += size
        elif not occ and province_id in nat["occupied_provinces"]:
            dropped["occupied province"] += size
        elif province_id in nat["colonial_provinces"]:
            dropped["colonial province"] += size

    print(f"\nMobilization pool for {tag} at {meta['date']} "
          f"({os.path.basename(meta['file'])})")
    print(f"  primary culture   {nat['primary_culture']}")
    print(f"  accepted cultures {' '.join(sorted(nat['accepted_cultures'])) or '(none)'}")
    print(f"  pop types counted {' '.join(sorted(mob_types))}")
    print(f"  mobilisation size {rate * 100:.2f}%   "
          f"POP_SIZE_PER_REGIMENT {args.pop_per_regiment}")
    print(f"\n  eligible population   {pool:>12,} in {entries} pop entries, "
          f"{len(per_pt)} province/type slots")
    if entries:
        print(f"  cultural split        {entries / max(1, len(per_pt)):.2f} pop "
              f"entries per province/type slot")
    for reason, size in sorted(dropped.items(), key=lambda kv: -kv[1]):
        print(f"  excluded: {reason:<20} {size:>12,}")

    per_pop_n = brigades_from_clusters(per_pop, rate, args.pop_per_regiment)
    per_pt_n = brigades_from_clusters(per_pt, rate, args.pop_per_regiment)
    untruncated = pool * rate / args.pop_per_regiment
    print(f"\n  ceiling, grouped per pop               {per_pop_n:>6}")
    print(f"  ceiling, grouped per province and type {per_pt_n:>6}"
          f"   ({'+' if per_pt_n >= per_pop_n else ''}{per_pt_n - per_pop_n})")
    print(f"  no truncation at all                   {untruncated:>6.0f}")
    print(f"  standing brigades                      {nat['brigades']:>6}"
          f"  ({nat['mobilized_brigades']} of them mobilized, "
          f"{nat['mobilizing']} queued)")
    print("\n  Compare the two ceilings against the in-game military panel.")

    biggest = sorted(per_pt, key=lambda b: -b[3])[:10]
    if biggest:
        print("\n  largest province/type slots")
        print(f"    {'prov':>6} {'manpower':>10} {'brigades':>8}")
        for province_id, _state, _type, size in biggest:
            print(f"    {province_id:>6} {size * rate:>10,.0f} "
                  f"{int(size * rate // args.pop_per_regiment):>8}")


def asked(args):
    """
    Whether one of the four was asked for.

    Kept beside the code that answers them, because `main` needs to know
    the same thing before the campaign is read: a run that is only going
    to print a nation cannot be answered with the report that is already
    on disk. Asking that question by listing the four flags a second time
    is how `--explain-mob ENG` on an unchanged campaign came to answer
    "nothing has changed" and explain nothing at all.
    """
    return bool(args.explain_mob or args.explain_mob_pool or args.inventions
                or args.check_inventions)


def explain(args, mod, live, parsed):
    """
    Answer whichever of the four was asked for, and say whether one was.

    True means the run is over: the question has been printed and there is
    nothing left to do. False means nothing was asked and the caller should
    get on with building the report.

    """
    if args.explain_mob_pool:
        tag = args.explain_mob_pool.upper()
        meta, nations = parsed[-1]
        nat = nations.get(tag)
        if nat is None:
            sys.exit(f"{tag} is not in {meta['file']}.")
        from modrules import rate_for
        rate = rate_for(nat, mod, live=live,
                        world=save_world(meta, mod) if mod else None,
                        fallback=args.mob_rate)
        explain_mob_pool(tag, nat, meta, rate, args)
        return True

    if args.check_inventions:
        if mod is None:
            sys.exit("--check-inventions needs --mod-path.")
        from mod_reader import (alignment_score, index_holdings,
                                ungated_inventions)
        holdings = index_holdings(parsed)
        base = mod.index_base
        seq = mod.invention_sequence
        print(f"\nChecking {len(seq)} inventions against {len(parsed)} saves.")
        if base is None:
            sys.exit("  the indices did not decode at all, so there is "
                     "nothing to check.")
        if len(holdings) < 40:
            print(f"  only {len(holdings)} indices are held often enough to "
                  f"say anything about. Run this on a whole campaign.")
        print(f"  {len(holdings)} indices held often enough to judge\n")
        print(f"  {'offset':<10}{'confirmed':>11}{'granted':>10}"
              f"{'suspect':>10}{'unjudged':>10}")
        table = {}
        for shift in (-2, -1, 0, 1, 2):
            good, granted, bad, unjudged, ungated, detail = alignment_score(
                mod, holdings, base + shift)
            table[shift] = (good, granted, bad, detail)
            print(f"  {('as used' if not shift else '%+d' % shift):<10}"
                  f"{good:>11}{granted:>10}{bad:>10}{unjudged + ungated:>10}"
                  f"{'   <-- the decode in use' if not shift else ''}")
        loose = ungated_inventions(mod)
        if loose:
            print(f"\n  {len(loose)} invention(s) in this mod are gated on a "
                  f"technology it never defines, so the gate never closes and "
                  f"every nation has them from the start. They are left out of "
                  f"the count above:")
            for name in sorted(loose):
                print(f"    {name:<40} asks for {' '.join(loose[name])}")
        good, granted, bad, detail = table[0]
        judged = good + granted + bad
        best = max(table, key=lambda k: table[k][0])
        print()
        if best != 0:
            print(f"  Offset {best:+d} confirms more indices than the one in use. "
                  f"The base is probably wrong.")
        elif bad == 0:
            one = granted == 1
            tail = ("" if not granted else
                    f" {granted} of them {'is' if one else 'are'} held by a few "
                    f"nations that could not have researched "
                    f"{'it' if one else 'them'}, which is the engine granting "
                    f"inventions outside the tech tree.")
            print(f"  Every index the saves can judge sits where the array says "
                  f"it does.{tail}\n"
                  f"  The decode is right: who holds which invention is exact.")
        else:
            print(f"  {bad} of {judged} indices are held mostly by nations that "
                  f"could not have researched them. That is what a misaligned "
                  f"stretch of the array looks like, and it is worth reading the "
                  f"list below before trusting anything taken off an invention.")
        if detail:
            print(f"\n  {'index':>6}  {'invention':<38} {'holders':>16}  needs")
            for idx, have, lack in detail[:26]:
                entry = seq[idx - base]
                flag = "" if have >= lack else "  <-- suspect"
                print(f"  {idx:>6}  {entry['name']:<38} "
                      f"{have:>6} with {lack:>4} without  "
                      f"{' '.join(sorted(entry['techs']))}{flag}")
            if len(detail) > 26:
                print(f"  ... and {len(detail) - 26} more")
        return True

    if args.inventions:
        if mod is None:
            sys.exit("--inventions needs --mod-path.")
        from mod_reader import invention_files
        tag = args.inventions.upper()
        meta, nations = parsed[-1]
        nat = nations.get(tag)
        if nat is None:
            sys.exit(f"{tag} is not in {meta['file']}.")
        seq = mod.invention_sequence
        base = mod.index_base
        where = invention_files(args.mod_path)
        held = sorted(nat.get("invention_ids", ()))
        print(f"\n{tag} at {meta['date']} in {meta['file']}")
        print(f"the mod rebuilds {len(seq)} inventions; this save names "
              f"{len(held)} of them, indices {min(held, default=0)}"
              f"..{max(held, default=0)}")
        if base is None:
            sys.exit("  indices could not be decoded for this install, so "
                     "there is nothing to print.")
        print(f"decoded with base {base}\n")
        shown = 0
        last_file = None
        for idx in held:
            j = idx - base
            if not (0 <= j < len(seq)):
                print(f"  {idx:>4}  *** past the end of the array -- this save "
                      f"is from a different build ***")
                continue
            entry = seq[j]
            fname = where.get(entry["name"], "?")
            if fname != last_file:
                print(f"  -- {fname}")
                last_file = fname
            gates = " ".join(sorted(entry["techs"])) or "(no technology)"
            has = "" if entry["techs"] <= set(nat["tech_list"]) else "   <-- the nation does not have that technology"
            print(f"  {idx:>4}  {entry['name']:<42} {gates}{has}")
            shown += 1
        print(f"\n{shown} decoded. Compare against the technology screen: every "
              f"invention shown as discovered there should appear here, and "
              f"nothing else should.")
        return True

    if args.explain_mob:
        if mod is None:
            sys.exit("--explain-mob needs --mod-path.")
        from modrules import breakdown
        tag = args.explain_mob.upper()
        meta, nations = parsed[-1]
        nat = nations.get(tag)
        if nat is None:
            sys.exit(f"{tag} is not in {meta['file']}.")
        parts = breakdown(nat, mod, live=live, world=save_world(meta, mod))
        print(f"\nMobilisation size for {tag} at {meta['date']}:")
        total = 0.0
        for kind, name, value in sorted(parts, key=lambda p: (p[0], -p[2])):
            total += value
            print(f"  {kind:<19}{name:<46} {value * 100:+.2f}%")
        print(f"  {'':<19}{'TOTAL':<46} {total * 100:>6.2f}%")
        print(f"\n{tag} has {len(nat['tech_list'])} techs and "
              f"{len(nat['invention_ids'])} active inventions; "
              f"{len(parts)} sources grant it mobilisation size.")
        from modrules import unjudged_triggers
        skipped = unjudged_triggers(mod)
        if skipped:
            print(f"Left out, because their trigger asks something this "
                  f"cannot answer: {', '.join(skipped)}.")
        print(f"Invention indices in save run "
              f"{min(nat['invention_ids'], default=0)}..{max(nat['invention_ids'], default=0)}; "
              f"the mod defines {len(mod.invention_sequence)} inventions, "
              f"{mod.invention_count} of which grant mobilisation size.")
        return True
    return False


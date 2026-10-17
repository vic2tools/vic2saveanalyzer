#!/usr/bin/env python3
"""
A campaign's verified answers, recorded once and compared against after
every change to the engine.

    python3 testkit/baseline.py record  CAMPAIGN --mod MOD [--into DIR] [--match GLOB]
                                        [--count N] [--nations explain=NET,pool=ENG,inventions=FRA]
    python3 testkit/baseline.py compare CAMPAIGN --mod MOD [--from DIR] [--ignore KEY ...]

`record` picks `--count` saves spaced evenly through the campaign's saves
(those matching `--match`) and the last one, and writes down exactly which:
their names, sizes and SHA-256 in `manifest.json`, with the mod's name and
the commit it was recorded at. It then runs the program over them a couple
of dozen ways (`RUNS`: every table, the page's payload, what it printed)
and keeps each answer, along with the mod as the program reads it.

`compare` finds those saves by name in the campaign folder -- saves added
since do not matter -- and holds a run of the program now to every recorded
answer. A save that is missing, or whose content changed under its name, is
named and nothing is compared (exit 77): a baseline only means something on
the saves it was made from. `--ignore payload.wars[].side_losses` leaves a
payload key out, for a change that removes it on purpose.

DIR defaults to `$VIC2_BASELINE`. Keep it outside the repository: it is one
person's campaign. The world each run reads is a private copy of the game
and the mod, with rules added that campaigns rarely meet (`TRIGGERED`,
`ISSUES`, `STATIC`); the real install is never written, and is checked
afterwards not to have been.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import kit
import expected
from outcome import SKIPPED

TRIGGERED = """
enginecheck_war = {
	mobilisation_size = 0.031
	mobilization_impact = 0.5
	trigger = { war = yes }
}
enginecheck_great = {
	mobilisation_size = 0.017
	trigger = { is_greater_power = yes year = 1875 }
}
enginecheck_human = {
	mobilisation_size = 0.011
	trigger = { ai = no civilized = yes }
}
enginecheck_europe = {
	mobilisation_size = 0.007
	trigger = { capital_scope = { continent = europe } NOT = { tag = ENG } }
}
enginecheck_or = {
	mobilisation_size = 0.013
	mobilization_impact = -0.25
	trigger = { OR = { tag = FRA tag = RUS primary_culture = british } prestige = 50 }
}
enginecheck_numbers = {
	mobilisation_size = 0.003
	trigger = { total_pops = 5000000 money = 1000 badboy = 1 revanchism = 0 }
}
enginecheck_tech = {
	mobilisation_size = 0.009
	trigger = { technology = military_logistics invention = mobilization_time_tables }
}
enginecheck_capital = {
	mobilisation_size = 0.004
	trigger = { capital_scope = { OR = { province_id = 300 province_id = 1 } } }
}
enginecheck_owns = {
	mobilisation_size = 0.5
	trigger = { owns = 300 }
}
enginecheck_flags = {
	mobilisation_size = 0.002
	trigger = { NOT = { has_country_flag = nonexistent_flag } exists = yes }
}
enginecheck_culture_group = {
	mobilisation_size = 0.006
	trigger = { is_culture_group = germanic }
}
enginecheck_unknown = {
	mobilisation_size = 0.04
	trigger = { some_trigger_nobody_reads = yes }
}
enginecheck_reform = {
	mobilisation_size = 0.005
	mobilization_impact = 0.125
	trigger = { slavery = no_slavery }
}
enginecheck_nested = {
	mobilisation_size = 0.0015
	trigger = { AND = { war_exhaustion = 0 NOT = { OR = { government = absolute_monarchy nationalvalue = nv_order } } } }
}
"""

ISSUES = """
enginecheck_reforms = {
	vote_franschise = {
		universal_voting = { mobilisation_size = 0.012 }
		landed_voting = { mobilisation_size = -0.004 }
	}
}
"""

STATIC = """
unciv_nation = {
	mobilisation_size = -0.1
}
"""

RUNS = [
    ("as it comes", []),
    ("verbose", ["VERBOSE"]),
    ("verbose, one at a time", ["VERBOSE", "-j", "1"]),
    ("a few nations", ["--tags", "ENG", "FRA", "RUS", "CHI"]),
    ("small nations dropped", ["--min-pop", "4000000"]),
    ("players named", ["--player-nations", "ENG", "RUS"]),
    ("nobody playing", ["--player-nations"]),
    ("farmers only", ["--mob-types", "farmers"]),
    ("regiments of a thousand", ["--pop-per-regiment", "1000"]),
    ("occupied land counted", ["--mob-include-occupied"]),
    ("a smaller map", ["--map-scale", "3"]),
    ("split payload", ["--split"]),
    ("no page", ["--no-html"]),
    # The engine's own cache: filled by one run and read by the next, which
    # has to make what a run with no cache makes.
    ("out of the engine's cache", ["CACHED"]),
    ("out of the engine's cache, verbose", ["CACHED", "VERBOSE"]),
    # What the diagnostics make of a real campaign, and --cross over it cut
    # in two.
    ("where a mobilisation size comes from", ["VERBOSE", "--explain-mob", "NET"]),
    ("a mobilization pool", ["VERBOSE", "--explain-mob-pool", "ENG"]),
    ("the inventions a nation holds", ["VERBOSE", "--inventions", "FRA"]),
    ("the invention decode checked", ["VERBOSE", "--check-inventions"]),
    ("a peek", ["VERBOSE", "--peek"]),
    ("verified", ["VERBOSE", "--verify"]),
    ("campaigns compared", ["CROSS"]),
    ("campaigns compared, verbose", ["CROSS", "VERBOSE"]),
]


def file_stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def real_files(mod):
    """{path: (size, mtime)} for every file of the real game and mod this
    check builds its world out of, to prove afterwards that it left them
    alone, even if a future fixture helper changes."""
    game = os.path.dirname(os.path.dirname(os.path.abspath(mod)))
    out = {}
    for root in [os.path.join(game, name) for name in os.listdir(game) if name != "mod"] + [mod]:
        if os.path.isfile(root):
            out[root] = file_stamp(root)
            continue
        for folder, subs, files in os.walk(root):
            for f in files:
                path = os.path.join(folder, f)
                out[path] = file_stamp(path)
    return out


def a_world(holding, mod, saves, extra_modifier):
    """
    (a game, the mod in it, a folder of saves): the install copied, the
    mod copied with the extra rules, and every save in `saves`.
    """
    game = os.path.dirname(os.path.dirname(os.path.abspath(mod)))
    world = os.path.join(holding, "game")
    # What the analyzer reads of an install -- the folders `mod_signature`
    # covers -- and not the movies, music and sound beside them, which are
    # most of its gigabyte.
    for name in ("common", "decisions", "inventions", "localisation", "poptypes",
                 "technologies", "units"):
        if os.path.isdir(os.path.join(game, name)):
            shutil.copytree(os.path.join(game, name), os.path.join(world, name),
                            symlinks=False)
    if os.path.isdir(os.path.join(game, "gfx", "flags")):
        shutil.copytree(os.path.join(game, "gfx", "flags"),
                        os.path.join(world, "gfx", "flags"), symlinks=False)
    os.makedirs(os.path.join(world, "map"), exist_ok=True)
    for name in os.listdir(os.path.join(game, "map")):
        source = os.path.join(game, "map", name)
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(world, "map", name))
    ours = os.path.join(world, "mod", os.path.basename(os.path.abspath(mod)))
    shutil.copytree(mod, ours, symlinks=False)
    common = os.path.join(ours, "common")

    def append(name, text):
        # At the front: this mod's event_modifiers.txt ends without closing
        # its last block, so anything added at the end is read as part of
        # that block rather than beside it.
        target = os.path.join(common, name)
        if not os.path.exists(target):
            src = os.path.join(game, "common", name)
            if os.path.exists(src):
                shutil.copy(src, target)
            else:
                open(target, "wb").close()
        with open(target, "rb") as fh:
            before = fh.read()
        with open(target, "wb") as fh:
            fh.write(text.encode("latin-1") + b"\n" + before)

    append("triggered_modifiers.txt", TRIGGERED)
    append("issues.txt", ISSUES)
    append("static_modifiers.txt", STATIC)
    if extra_modifier:
        append("event_modifiers.txt",
               "\n%s = {\n\tmobilisation_size = 0.021\n\tmobilization_impact = 0.75\n}\n"
               % extra_modifier)
    folder = os.path.join(holding, "saves")
    os.makedirs(folder)
    for name in sorted(f for f in os.listdir(saves) if f.endswith(".v2")):
        target = os.path.join(folder, name)
        if not os.path.exists(target):
            shutil.copy2(os.path.join(os.path.abspath(saves), name), target)
    # The same saves as two campaigns, for --cross: linked to the copies
    # just made, never to the real ones.
    kept = sorted(os.listdir(folder))
    for part, names_in in (("early", kept[:len(kept) // 2]), ("late", kept[len(kept) // 2:])):
        os.makedirs(os.path.join(holding, "cross", part))
        for name in names_in:
            os.link(os.path.join(folder, name), os.path.join(holding, "cross", part, name))
    return world, ours, folder


def a_modifier_someone_holds(saves, name):
    """
    The national modifier most nations of save `name` hold, or None: a
    country block's `modifier = { modifier="..." }`, counted by occurrence.
    """
    with open(os.path.join(saves, name), "rb") as fh:
        text = fh.read().decode("latin-1")
    counts = {}
    for country in re.finditer(r"(?ms)^([A-Z][A-Z0-9]{2})=[ \t]*\r?\n\{(.*?)^\}", text):
        for held in re.finditer(r'(?m)^\tmodifier=\s*\{\s*modifier="([^"]*)"', country[2]):
            counts[held[1]] = counts.get(held[1], 0) + 1
    return max(sorted(counts), key=counts.get) if counts else None


# ------------------------------------------------------------- running

def run(folder, mod, args, out, holding):
    """One run's answer. `CACHED` fills a cache of its own first, so the run
    answered is read entirely out of it."""
    env = dict(os.environ)
    quiet = [] if "VERBOSE" in args else ["-q"]
    if "VERBOSE" in args and "-j" not in args:
        # How many saves are read at once follows the memory free at the
        # moment, and a verbose run says each save in the way that number
        # decides, so a verbose run names it.
        quiet = ["-j", "3"]
    argv = [a for a in args if a not in ("VERBOSE", "CACHED", "CROSS")]
    cached = "CACHED" in args
    if "CROSS" in args:
        folder = os.path.join(os.path.dirname(folder), "cross")
        argv.append("--cross")
    env["TMPDIR"] = out + "-tmp"
    os.makedirs(env["TMPDIR"], exist_ok=True)
    command = ([folder, "--out", out, "--mod-path", mod, "--rebuild"]
               + ([] if cached else ["--no-cache"]) + quiet + argv)
    places = [(env["TMPDIR"], "TMP"), (holding, "HOLDING")]
    if cached:
        expected.run(command, kit.ROOT, env, out, places)
    got = expected.run(command, kit.ROOT, env, out, places)
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(env["TMPDIR"], ignore_errors=True)
    return got


# ------------------------------------------------------------- the record

NATIONS = {"explain": "NET", "pool": "ENG", "inventions": "FRA"}
ASKS = {"explain": "--explain-mob", "pool": "--explain-mob-pool", "inventions": "--inventions"}


def slug(name):
    return expected.slug(name)


def chosen(names, count):
    """`count` names spaced evenly through `names` (sorted), and the last."""
    names = sorted(names)
    if not names:
        return []
    step = max(1, len(names) // max(1, count))
    return list(dict.fromkeys(names[::step][:count] + names[-1:]))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def holds_nation(save, tag):
    with open(save, "rb") as fh:
        return re.search(rb"(?m)^" + re.escape(tag.encode()) + rb"=\s*\r?\n\{", fh.read()) is not None


def runs_for(nations, only=None):
    """RUNS with the diagnostics asking about `nations`, limited to `only`."""
    out = []
    for name, flags in RUNS:
        if only and name not in only:
            continue
        flags = list(flags)
        for key, ask in ASKS.items():
            if ask in flags:
                flags[flags.index(ask) + 1] = nations[key]
        out.append((name, flags))
    return out


def commit():
    done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=kit.ROOT,
                          capture_output=True, text=True)
    return done.stdout.strip()


def mod_as_read(mod):
    """The mod as the program reads it, with its folders written portably."""
    import modread
    return {"mod.json": json.dumps(modread.portable(modread.answer_of(mod)),
                                   indent=1, sort_keys=True) + "\n"}


def held_runs(source, campaign, mod, manifest, update, ignore=(), only=None):
    """Run every case on the manifest's saves and hold (or record) each.
    0 if all held, 1 if not."""
    real = real_files(mod)
    try:
        with kit.holding("vic2base") as (holding, _env):
            folder = os.path.join(holding, "picked")
            os.makedirs(folder)
            for name, _size, _sha in manifest["saves"]:
                shutil.copy2(os.path.join(campaign, name), os.path.join(folder, name))
            _world, world_mod, saves = a_world(holding, mod, folder, manifest["modifier"])
            cases = [(name, lambda f=flags: run(saves, world_mod, f,
                                                os.path.join(holding, "out"), holding))
                     for name, flags in runs_for(manifest["nations"], only or manifest["runs"])]
            cases.append(("the mod as read", lambda: mod_as_read(mod)))
            return expected.hold_cases(source, "baseline", cases, update, ignore=ignore)
    finally:
        touched = [path for path, was in real.items() if file_stamp(path) != was]
        if touched:
            raise RuntimeError("the baseline changed the real game or mod: %s"
                               % ", ".join(touched[:5]))


def record(campaign, mod, into, *, match="*.v2", count=8, nations=None, runs=None):
    """Pick the saves, write the manifest, and record every answer. 0 or 1."""
    names = [n for n in os.listdir(campaign) if fnmatch.fnmatch(n, match)]
    picked = chosen(names, count)
    if not picked:
        print("no saves matching %s in %s" % (match, campaign))
        return 1
    nations = dict(NATIONS, **(nations or {}))
    last = os.path.join(campaign, picked[-1])
    missing = [k for k, tag in nations.items() if not holds_nation(last, tag)]
    if missing:
        print("%s holds no %s; name nations it holds with --nations %s"
              % (picked[-1], ", ".join(nations[k] for k in missing),
                 ",".join("%s=TAG" % k for k in missing)))
        return 1
    manifest = {"saves": [[n, os.path.getsize(os.path.join(campaign, n)),
                           sha256(os.path.join(campaign, n))] for n in picked],
                "mod": os.path.basename(os.path.abspath(mod)),
                "modifier": a_modifier_someone_holds(campaign, picked[-1]),
                "nations": nations,
                "runs": [name for name, _f in RUNS if not runs or name in runs],
                "commit": commit()}
    os.makedirs(into, exist_ok=True)
    with open(os.path.join(into, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print("recording %d saves of %s under %s" % (len(picked), campaign, manifest["mod"]))
    return held_runs(into, campaign, mod, manifest, update=True)


def compare(campaign, mod, source, *, ignore=(), runs=None):
    """Hold a run now to the baseline in `source`. 0, 1, or 77 when the
    baseline cannot be compared here."""
    source = source or os.environ.get("VIC2_BASELINE", "")
    if not source or not os.path.isfile(os.path.join(source, "manifest.json")):
        print("no baseline%s: record one with `python testkit/baseline.py record "
              "CAMPAIGN --mod MOD --into DIR`, then set VIC2_BASELINE=DIR"
              % (" in %s" % source if source else ""))
        return SKIPPED
    with open(os.path.join(source, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    changed = []
    for name, size, sha in manifest["saves"]:
        path = os.path.join(campaign, name)
        if not os.path.isfile(path):
            changed.append("%s is missing" % name)
        elif os.path.getsize(path) != size or sha256(path) != sha:
            changed.append("%s: content changed since the baseline was recorded" % name)
    if os.path.basename(os.path.abspath(mod)) != manifest["mod"]:
        changed.append("the baseline was recorded under %s, not %s"
                       % (manifest["mod"], os.path.basename(os.path.abspath(mod))))
    if changed:
        print("the baseline in %s cannot be compared here:\n  %s"
              % (source, "\n  ".join(changed)))
        return SKIPPED
    print("comparing with the baseline recorded at %s (%d saves)"
          % (manifest.get("commit") or "?", len(manifest["saves"])))
    return held_runs(source, campaign, mod, manifest, update=False, ignore=ignore, only=runs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    sub = ap.add_subparsers(dest="what", required=True)
    rec = sub.add_parser("record", help="record a baseline")
    rec.add_argument("campaign")
    rec.add_argument("--mod", required=True)
    rec.add_argument("--into", default=os.environ.get("VIC2_BASELINE", ""))
    rec.add_argument("--match", default="*.v2")
    rec.add_argument("--count", type=int, default=8)
    rec.add_argument("--nations", default="",
                     help="explain=TAG,pool=TAG,inventions=TAG (default NET, ENG, FRA)")
    cmp_ = sub.add_parser("compare", help="compare a run now with a baseline")
    cmp_.add_argument("campaign")
    cmp_.add_argument("--mod", required=True)
    cmp_.add_argument("--from", dest="source", default=os.environ.get("VIC2_BASELINE", ""))
    cmp_.add_argument("--ignore", nargs="*", default=[])
    args = ap.parse_args()
    if args.what == "record":
        if not args.into:
            ap.error("say where with --into, or set VIC2_BASELINE")
        nations = dict(pair.split("=", 1) for pair in args.nations.split(",") if pair)
        return record(args.campaign, args.mod, args.into, match=args.match,
                      count=args.count, nations=nations)
    return compare(args.campaign, args.mod, args.source, ignore=tuple(args.ignore))


if __name__ == "__main__":
    sys.exit(main())

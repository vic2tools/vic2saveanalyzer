#!/usr/bin/env python3
"""
The report engine against the answers recorded for it, run for run.

This runs the real program over a world of edge cases and over a handful of
real saves, a dozen ways of asking, and requires the nine outputs and the
printed words recorded for each (`expected.py`). The answers were the pure
Python's, taken on 1 Oct 2026 while it was still here; before then this ran
every case both ways. The real saves' answers are somebody's campaign and
are kept outside the repository (`$VIC2_EXPECTED_REAL`), with the saves they
came from named in `inputs.json`.

    python3 testkit/enginecheck.py SAVES --mod MOD [--every N] [--update]

The mod they are read under is the real one, with rules added that the
campaigns here never meet: triggered modifiers asking every question the
trigger reader answers (at war, a great power, a person playing, a capital
in Europe, OR and NOT, a technology and an invention, a reform, a culture
group, one it cannot answer), a reform option and a national modifier that
grant mobilisation size, a penalty for being uncivilized. It is built in a private copy of the game and mod. No writable fixture
contains links back to the real install.

The page is compared by what it carries: its payload as JSON text, with each
flag's PNG and each state snapshot decoded first, because those are made by
two different compressors and only what they hold has to agree.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import expected                                            # noqa: E402
from outcome import SKIPPED                                 # noqa: E402

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


def copies_of(src, dst, skip=()):
    """Copy fixture inputs, dereferencing links so writes stay in the fixture."""
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in skip:
            continue
        source, target = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(source):
            shutil.copytree(source, target, symlinks=False)
        elif os.path.isfile(source):
            shutil.copy2(source, target)


def a_world(holding, mod, saves, every, extra_modifier):
    """
    (a game, the mod in it, a folder of saves): the install copied, the
    mod copied with the extra rules, and every `every`th save.
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
    names = sorted(f for f in os.listdir(saves) if f.endswith(".v2"))
    for name in names[::every] + names[-1:]:
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


SYNTHETIC_RUNS = [
    ("on the edges", []),
    ("on the edges, occupied counted", ["--mob-include-occupied"]),
    ("on the edges, farmers only", ["--mob-types", "farmers"]),
    ("on the edges, verbose", ["VERBOSE"]),
]


def an_edge_world(holding):
    """
    (a mod, a folder of saves) built to sit on every boundary a count has:
    a pop worth exactly one regiment, a pool that fills to exactly one,
    soldiers either side of the smallest pop a brigade may be raised from,
    and land that is colonial, occupied and not cored. The mod grants half
    its people to mobilisation and charges a thousand a regiment, and has
    no map, no defines past that and no flags, which are paths of their own.
    """
    import matching
    import savefmt
    pops = matching.POPS + ["serfs"]
    mod = matching.a_mod_in_a_game(holding, "edges", pops=pops, pop_per_regiment=1000,
                                   mob_size=0.5)
    folder = os.path.join(holding, "edge-saves")
    os.makedirs(folder)
    for n, (date, grow) in enumerate((("1870.1.1", 0), ("1871.1.1", 2), ("1872.1.1", 1))):
        def people(pid, kinds):
            return [savefmt.pop(kind, pid * 100 + i, size + grow * (i % 2), culture=culture)
                    for i, (kind, size, culture) in enumerate(kinds)]
        savefmt.write(
            os.path.join(folder, "edge%d.v2" % n),
            savefmt.head(date, player="ENG"),
            savefmt.province(1, "ENG", people(1, [
                ("farmers", 2000, "british"), ("farmers", 1999, "british"),
                ("labourers", 1, "british"), ("craftsmen", 4000, "british"),
                ("soldiers", 999, "british"), ("soldiers", 1000, "british"),
                ("soldiers", 3000, "british"), ("soldiers", 2999, "british"),
                ("serfs", 2002, "british"), ("farmers", 700, "irish")])),
            savefmt.province(2, "ENG", people(2, [
                ("farmers", 6000, "british"), ("soldiers", 4000, "british")]),
                extra=["colonial=2"]),
            savefmt.province(3, "ENG", people(3, [
                ("labourers", 8000, "british"), ("soldiers", 1500, "british")]),
                extra=['controller="FRA"']),
            savefmt.province(4, "FRA", people(4, [
                ("farmers", 3000, "french"), ("soldiers", 1000, "french")])),
            savefmt.country("ENG", techs=matching.TECHS, inventions=[1],
                            extra=["ruling_party=1", "human=yes"]),
            savefmt.country("FRA", culture="french", capital=4,
                            techs=matching.TECHS[:1], inventions=[1]),
            savefmt.war("The Edge War", "ENG", "FRA", active=n < 2,
                        action="1870.5.%d" % (n + 1)))
    return mod, folder


def a_modifier_someone_holds(saves):
    """
    The national modifier most nations of the last save hold, or None: a
    country block's `modifier = { modifier="..." }`, counted by occurrence.
    """
    names = sorted(f for f in os.listdir(saves) if f.endswith(".v2"))
    if not names:
        return None
    with open(os.path.join(saves, names[-1]), "rb") as fh:
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
        expected.run(command, HERE, env, out, places)
    got = expected.run(command, HERE, env, out, places)
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(env["TMPDIR"], ignore_errors=True)
    return got


def inputs_of(saves, every, mod):
    """What the real record was made from: which saves, and how big."""
    names = sorted(f for f in os.listdir(saves) if f.endswith(".v2"))
    chosen = names[::every] + names[-1:]
    return {"every": every, "mod": os.path.basename(os.path.abspath(mod)),
            "saves": [[n, os.path.getsize(os.path.join(saves, n))]
                      for n in dict.fromkeys(chosen)]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("saves", nargs="?", default="")
    ap.add_argument("--mod", default="")
    ap.add_argument("--every", type=int, default=17)
    ap.add_argument("--update", action="store_true",
                    help="write what the program answers now as the expected answers")
    args = ap.parse_args()
    binary = os.path.join(HERE, "scanner", "target", "release",
                          "vic2scan" + (".exe" if os.name == "nt" else ""))
    if not os.path.isfile(binary):
        print("needs the scanner built")
        return SKIPPED
    holding = tempfile.mkdtemp(prefix="vic2engine")
    wrong = []
    real = {}
    skipped = []
    try:
        width = max(len(n) for n, _ in RUNS + SYNTHETIC_RUNS)
        # The edge world first: it needs nothing but this tree. A folder of
        # its own: the helpers that build a small game write into
        # `<holding>/game`, and built beside a copy of the real install
        # they once emptied the real game's map/default.map through a link.
        edge_mod, edge_folder = an_edge_world(os.path.join(holding, "edges"))
        book = expected.Book(expected.REPO, "enginecheck", args.update)
        for name, flags in SYNTHETIC_RUNS:
            got = run(edge_folder, edge_mod, flags, os.path.join(holding, "out"), holding)
            found = book.hold(name, got)
            expected.report(name, found, width)
            wrong += ["%s: %s" % (name, f) for f in found]
        book.finish()

        # Then the real campaign, whose answers live outside the tree.
        record = os.path.join(expected.REAL, "enginecheck")
        manifest = os.path.join(record, "inputs.json")
        if not (args.saves and os.path.isdir(args.saves) and args.mod
                and os.path.isdir(args.mod)):
            skipped.append("no saves and mod given, so the real campaign was not run")
        elif not args.update and not os.path.isfile(manifest):
            skipped.append("no answers are recorded for a real campaign in %s" % record)
        else:
            inputs = inputs_of(args.saves, args.every, args.mod)
            if args.update:
                inputs["modifier"] = a_modifier_someone_holds(args.saves)
            else:
                with open(manifest, encoding="utf-8") as fh:
                    kept = json.load(fh)
                inputs["modifier"] = kept.get("modifier")
                if kept != inputs:
                    skipped.append("the answers in %s were recorded from other saves or "
                                   "another mod (%s), so the real campaign was not run"
                                   % (record, ", ".join(k for k in inputs
                                                        if kept.get(k) != inputs[k])))
                    inputs = None
            if inputs is not None:
                real = real_files(args.mod)
                world, mod, folder = a_world(holding, args.mod, args.saves, args.every,
                                             inputs["modifier"])
                book = expected.Book(expected.REAL, "enginecheck", args.update)
                for name, flags in RUNS:
                    got = run(folder, mod, flags, os.path.join(holding, "out"), holding)
                    found = book.hold(name, got)
                    expected.report(name, found, width)
                    wrong += ["%s: %s" % (name, f) for f in found]
                book.finish()
                if args.update:
                    with open(manifest, "w", encoding="utf-8") as fh:
                        json.dump(inputs, fh, indent=1)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
        touched = [path for path, was in real.items() if file_stamp(path) != was]
        if touched:
            print("THIS CHECK CHANGED THE REAL GAME OR MOD: %s" % ", ".join(touched[:5]))
            raise RuntimeError("fixture changed real inputs")
    print()
    for why in skipped:
        print(why)
    if wrong:
        print("%d thing(s) differ from the recorded answers" % len(wrong))
        return 1
    if args.update:
        print("recorded")
        return 0
    print("the report engine gives the recorded answers, %d ways"
          % (len(SYNTHETIC_RUNS) + (0 if skipped else len(RUNS))))
    return SKIPPED if skipped and not args.update else 0


if __name__ == "__main__":
    sys.exit(main())

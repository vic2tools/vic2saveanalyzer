#!/usr/bin/env python3
"""
The report engine against the analyzer's own Python, run for run.

A run the engine takes is read, finished and written in Rust, and a run it
hands back is done in Python, so the program has two implementations of
everything from the saves to the report. This runs the real program both
ways -- the engine, and `VIC2_NO_ENGINE=1` -- over a handful of real saves
and a dozen ways of asking, and requires the same nine outputs and the same
printed words from both.

    python3 testkit/enginecheck.py SAVES --mod MOD [--every N]

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
import base64
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

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


def a_world(holding, mod, saves, every):
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
    extra_modifier = a_modifier_someone_holds(saves)

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
    """The national modifier most nations of the last save hold, or None."""
    import readsave
    names = sorted(f for f in os.listdir(saves) if f.endswith(".v2"))
    if not names:
        return None
    _meta, nations = readsave.analyze_save(os.path.join(saves, names[-1]),
                                           readsave.PLAIN, verbose=False)
    counts = {}
    for nat in nations.values():
        for m in nat.get("modifiers") or ():
            counts[m] = counts.get(m, 0) + 1
    return max(sorted(counts), key=counts.get) if counts else None


# ------------------------------------------------------------- comparing

def png_pixels(uri):
    raw = base64.b64decode(uri.split(",", 1)[1])
    at, ihdr, idat = 8, b"", b""
    while at < len(raw):
        n = int.from_bytes(raw[at:at + 4], "big")
        tag = raw[at + 4:at + 8]
        if tag == b"IHDR":
            ihdr = raw[at + 8:at + 8 + n]
        elif tag == b"IDAT":
            idat += raw[at + 8:at + 8 + n]
        at += 12 + n
    return "png:%s:%s" % (ihdr.hex(), hashlib.sha256(zlib.decompress(idat)).hexdigest())


def chunk_text(b64):
    return gzip.decompress(base64.b64decode(b64)).decode("utf-8")


def page(folder):
    """(the payload as normal JSON text, the state chunks, the page around them)."""
    html = open(os.path.join(folder, "report.html"), encoding="utf-8").read()
    packed = re.search(r'const PACKED = "([^"]*)"', html)[1]
    if packed:
        text = gzip.decompress(base64.b64decode(packed)).decode("utf-8")
    else:
        with open(os.path.join(folder, "report.data.gz"), "rb") as fh:
            text = gzip.decompress(fh.read()).decode("utf-8")
    data = json.loads(text)
    if data.get("flags"):
        data["flags"] = {k: png_pixels(v) for k, v in data["flags"].items()}
    board = data.get("map")
    if board and board.get("populationStateChunks"):
        board["populationStateChunks"] = [[d, chunk_text(c)]
                                          for d, c in board["populationStateChunks"]]
    beside = re.search(r'const STATE_CHUNKS = (\[.*?\]);\n', html, re.S)
    states = [[d, chunk_text(c)] for d, c in json.loads(beside[1])] if beside else []
    shell = html.replace(packed, "<DATA>") if packed else html
    if beside:
        shell = shell.replace(beside[0], "<STATES>")
    return json.dumps(data, separators=(",", ":")), json.dumps(states), shell


def differences(a, b):
    """[what differs] between two runs' output folders and printed text."""
    wrong = []
    names = sorted(set(os.listdir(a["out"])) | set(os.listdir(b["out"])))
    for name in names:
        if name in ("report.stamp",):
            continue
        pa, pb = os.path.join(a["out"], name), os.path.join(b["out"], name)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            wrong.append("%s is written by only one of them" % name)
            continue
        if name == "report.html":
            for what, x, y in zip(("the payload", "the state chunks", "the page"),
                                  page(a["out"]), page(b["out"])):
                if x != y:
                    j = next((j for j, (p, q) in enumerate(zip(x, y)) if p != q),
                             min(len(x), len(y)))
                    wrong.append("%s differs at %d: python %r, engine %r"
                                 % (what, j, x[max(0, j - 60):j + 60],
                                    y[max(0, j - 60):j + 60]))
        elif name == "report.data.gz":
            continue                      # compared through report.html
        else:
            with open(pa, "rb") as fa, open(pb, "rb") as fb:
                if fa.read() != fb.read():
                    wrong.append("%s differs" % name)
    # How many cores a read takes follows the memory free that moment, by
    # the same rule both ways, so that one number is not compared.
    cores = re.compile(r"(save\(s\) on )\d+( cores)")
    for stream in ("stdout", "stderr"):
        x = cores.sub(r"\1N\2", a[stream].replace(a["out"], "OUT"))
        y = cores.sub(r"\1N\2", b[stream].replace(b["out"], "OUT"))
        if x != y:
            j = next((j for j, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
            wrong.append("printed %s differs at %d:\n      python %r\n      engine %r\n"
                         "      engine's stderr ends %r"
                         % (stream, j, x[max(0, j - 200):j + 200], y[max(0, j - 200):j + 200],
                            b["stderr"][-600:]))
    return wrong


def run(folder, world, mod, args, out, engine):
    env = dict(os.environ)
    env.pop("VIC2_NO_ENGINE", None)
    if not engine:
        env["VIC2_NO_ENGINE"] = "1"
    else:
        env["VIC2_ENGINE_REQUIRED"] = "1"
    quiet = [] if "VERBOSE" in args else ["-q"]
    argv = [a for a in args if a not in ("VERBOSE", "CACHED")]
    cached = "CACHED" in args
    if cached:
        # Each way a cache of its own, filled first, so the run compared is
        # read entirely out of it: the engine's entries on one side, the
        # Python's on the other, and what each prints for a campaign it has
        # read before.
        env["TMPDIR"] = out + "-tmp"
        os.makedirs(env["TMPDIR"], exist_ok=True)
    command = ([sys.executable, os.path.join(HERE, "vic2_analyzer.py"), folder, "--out", out,
                "--mod-path", mod, "--rebuild"] + ([] if cached else ["--no-cache"])
               + quiet + argv)
    if cached:
        subprocess.run(command, capture_output=True, text=True, cwd=HERE, env=env)
    done = subprocess.run(command, capture_output=True, text=True, cwd=HERE, env=env)
    return {"out": out, "code": done.returncode, "stdout": done.stdout,
            "stderr": done.stderr}


def engine_ran(result):
    """Whether the run went through the engine (the scanner answers `report`)."""
    return result["code"] == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("saves", nargs="?", default="")
    ap.add_argument("--mod", default="")
    ap.add_argument("--every", type=int, default=17)
    args = ap.parse_args()
    import fastscan
    if not (args.saves and os.path.isdir(args.saves) and args.mod
            and os.path.isdir(args.mod)):
        print("needs a folder of saves and the mod they were played on")
        return SKIPPED
    if fastscan.available() is None:
        print("needs the scanner built: the engine is the scanner's `report` mode")
        return SKIPPED
    holding = tempfile.mkdtemp(prefix="vic2engine")
    wrong = []
    real = {}
    try:
        real = real_files(args.mod)
        world, mod, folder = a_world(holding, args.mod, args.saves, args.every)
        # A folder of its own: the helpers that build a small game write
        # into `<holding>/game`, which in `holding` is the real install
        # seen through links. Built there once, it emptied the real
        # game's map/default.map.
        edge_mod, edge_folder = an_edge_world(os.path.join(holding, "edges"))
        width = max(len(n) for n, _ in RUNS + SYNTHETIC_RUNS)
        plan = ([(name, flags, folder, mod) for name, flags in RUNS]
                + [(name, flags, edge_folder, edge_mod) for name, flags in SYNTHETIC_RUNS])
        for name, flags, folder, mod in plan:
            py = run(folder, world, mod, flags, os.path.join(holding, "py"), False)
            rs = run(folder, world, mod, flags, os.path.join(holding, "rs"), True)
            found = []
            if py["code"] or rs["code"]:
                found.append("exit %s (python) and %s (engine): %s"
                             % (py["code"], rs["code"], (py["stderr"] + rs["stderr"])[-500:]))
            else:
                found = differences(py, rs)
            print("  %-*s %s" % (width, name, "ok" if not found else "DIFFERS"))
            for f in found:
                print("      " + f[:600])
            wrong += ["%s: %s" % (name, f) for f in found]
            shutil.rmtree(py["out"], ignore_errors=True)
            shutil.rmtree(rs["out"], ignore_errors=True)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
        touched = [path for path, was in real.items() if file_stamp(path) != was]
        if touched:
            print("THIS CHECK CHANGED THE REAL GAME OR MOD: %s" % ", ".join(touched[:5]))
            raise RuntimeError("fixture changed real inputs")
    print()
    if wrong:
        print("the engine and the Python disagree on %d thing(s)" % len(wrong))
        return 1
    print("the engine and the Python make the same report, the same tables and "
          "say the same things, %d ways" % len(RUNS + SYNTHETIC_RUNS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

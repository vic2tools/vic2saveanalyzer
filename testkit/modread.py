"""
Hold the engine's mod reader (`scanner/src/engine/modread.rs`) to Python's.

The engine reads a mod folder itself, and what it makes of one has to be
what `mod_reader.load_mod` makes of it, field for field: the JSON
`modexport.export_mod` writes of Python's `Mod` and the JSON
`vic2scan mod-export` writes must be the same text. Where Python raises
over a folder, the Rust must decline it (status 3), so the analyzer reads
it in Python and raises as it always did.

Four parts:

- the regular expressions the reader runs, against Python's `re`, on
  random text built from the pieces mod files are made of;
- a world written to be awkward -- a mod over a game, file names that
  differ only in case, localisation in Windows-1252 with its gaps, a block
  where a name belongs, numbers Python spells its own way -- read as the
  mod and as the game;
- that world, damaged at random a few hundred times, each read both ways;
- the real mod, when `--mod` names one;
- and the copy the engine keeps of a mod it has read: a report run twice
  with the mod edited in between must show the edit.

    python3 testkit/modread.py [--mod MOD] [--rounds N]
"""

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import mod_reader as mr                                        # noqa: E402
from modexport import export_mod                               # noqa: E402
from outcome import SKIPPED                                    # noqa: E402

BIN = os.path.join(HERE, "scanner", "target", "release",
                   "vic2scan" + (".exe" if os.name == "nt" else ""))

# ---------------------------------------------------------------- patterns

PATTERNS = [
    ("", r"#[^\r\n]*"), ("", r"[\w.]"), ("", r"\s*=\s*\{"),
    ("S", r"NOT\s*=\s*\{(?:[^{}]|\{[^{}]*\})*\}"), ("", r"limit\s*=\s*\{"),
    ("", r"([a-z_][a-z_0-9]*)\s*=\s*1\b"), ("", r"tag\s*=\s*(\w+)"),
    ("", r"invention\s*=\s*(\w+)"), ("", r"chance\s*=\s*\{"), ("", r"base\s*=\s*([-\d.]+)"),
    ("S", r"modifier\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}"), ("", r"factor\s*=\s*([-\d.]+)"),
    ("S", r"NOT\s*=\s*\{\s*invention\s*=\s*(\w+)\s*\}"), ("", r"--.*"),
    ("", r"(?<![\w.])POP_SIZE_PER_REGIMENT\s*=\s*([-\d.]+)"),
    ("", r"(?<![\w.])strata\s*=\s*(\w+)"), ("", r"\bparty\s*=\s*\{"),
    ("M", r'^\s*([A-Z0-9]{3})\s*=\s*"?([^"\r\n]+?)"?\s*$'),
    ("", r"war_policy\s*=\s*(\w+)"), ("", r"(\w+)\s*=\s*\{"),
    ("", r"mobilization_impact\s*=\s*([-\d.]+)"),
    ("", r"([A-Za-z0-9_]+)\s*=\s*\{([^{}]*)\}"), ("M", r"^(\w+)\s*=\s*\{"),
    ("", r"(?<![\w_])type\s*=\s*(\w+)"), ("", r"(\w+)\s*=\s*([-\d.]+)"),
    ("", r"color\s*=\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}"), ("", r"sea_starts\s*=\s*\{([^}]*)\}"),
    ("", r"change_tag(?:_no_core_switch)?\s*=\s*([A-Z0-9]{3})\b"),
    ("", r"(?<![\w_])tag\s*=\s*([A-Z0-9]{3})\b"),
    # And a few that make a repeat's steps end in more than one place.
    ("", r"(?:a|ab)*b"), ("", r"(?:a|ab)*?b"), ("", r"((?:a|ab)*)(b+)"),
]
BITS = ["NOT", "limit", "tag", "invention", "chance", "base", "modifier", "factor", "strata",
        "party", "war_policy", "color", "sea_starts", "change_tag", "_no_core_switch", "type",
        "ENG", "A1B", "abc", "a", "ab", "b", "x_y", "1", "0", "12", "-3.5", ".", "-", "=", "{",
        "}", " ", "\t", "\n", "\r\n", "\r", '"', "#", "--", "\x1c", "\x85", "\xa0", "\xe9",
        "\xb2", "\xd7", "\xaa", "\xff", "_", "a.b"]
SNIPPETS = ["NOT = { invention = foo }", "limit = {", "chance = { base = 5",
            "modifier = { factor = -0.5 NOT = { invention = bar } }", "type = naval",
            'ENG = "countries/England.txt"', "color = { 12 34 56 }", "sea_starts = { 1 2 3 }",
            "change_tag = GER", "tag = SAR", "abc = 1", "x = {a b}", "\n", " = ", "{ ", " }"]


def patterns(rnd, rounds):
    cases = []
    for _ in range(rounds):
        for flags, pat in PATTERNS:
            text = "".join(rnd.choice(BITS) if rnd.random() < 0.6 else rnd.choice(SNIPPETS)
                           for _ in range(rnd.randint(0, 30)))
            cases.append((flags, pat, text))
    feed = "".join("%s\t%s\t%s\n" % (f, p, t.encode("latin-1").hex()) for f, p, t in cases)
    run = subprocess.run([BIN, "selftest-re"], input=feed.encode(), capture_output=True)
    got = run.stdout.decode().split("\n")
    if run.returncode or len(got) != len(cases) + 1:
        print("the pattern selftest did not answer every case: status %d, %d of %d lines"
              % (run.returncode, len(got) - 1, len(cases)))
        return False
    bad = 0
    for (flags, pat, text), answer in zip(cases, got):
        f = (re.M if "M" in flags else 0) | (re.S if "S" in flags else 0)
        want = ";".join(" ".join("-" if m.span(g)[0] < 0 else "%d,%d" % m.span(g)
                                 for g in range(m.re.groups + 1))
                        for m in re.compile(pat, f).finditer(text))
        if want != answer:
            bad += 1
            if bad <= 3:
                print("pattern %r on %r:\n  Python %s\n  Rust   %s" % (pat, text, want, answer))
    matched = sum(1 for a in got if a)
    print("patterns: %d cases, %d with matches, %d differ" % (len(cases), matched, bad))
    return bad == 0 and matched > len(cases) // 10


# ------------------------------------------------------------ the two sides

def python_side(path):
    """Python's export as text, or None and what it raised."""
    try:
        return json.dumps(export_mod(mr._load_mod(mr._mod_root(path))),
                          separators=(",", ":")), None
    except Exception as exc:                                  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, exc)


def rust_side(path):
    run = subprocess.run([BIN, "mod-export", mr._mod_root(path)], capture_output=True)
    return run.returncode, run.stdout.decode("utf-8").rstrip("\n"), run.stderr.decode("utf-8", "replace")


def where(a, b):
    """The first field the two exports differ in, and around where."""
    ja, jb = json.loads(a), json.loads(b)
    for key in ja:
        if ja[key] != jb.get(key):
            va, vb = json.dumps(ja[key]), json.dumps(jb.get(key))
            i = next((i for i in range(min(len(va), len(vb))) if va[i] != vb[i]),
                     min(len(va), len(vb)))
            return "%s: Python ...%s... Rust ...%s..." % (key, va[max(0, i - 120):i + 120],
                                                          vb[max(0, i - 120):i + 120])
    return "the same values, written differently"


def same(path, say=True):
    """Whether the two sides agree on one folder: "raised" when both refuse it."""
    text, raised = python_side(path)
    code, out, err = rust_side(path)
    if raised is not None:
        if code == 3:
            return "raised"
        print("%s: Python raised (%s) and the Rust %s" % (path, raised[:200],
              "exited %d: %s" % (code, err.strip()[-200:]) if code else "read it"))
        return False
    if code != 0:
        print("%s: the Rust exited %d: %s" % (path, code, err.strip()[-300:]))
        return False
    if out != text:
        print("%s: %s" % (path, where(text, out)))
        return False
    if say:
        print("same: %s (%d bytes)" % (path, len(text)))
    return True


# ------------------------------------------------------- an awkward world

def write(root, rel, data):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("latin-1"))


GAME = {
    "map/default.map": "sea_starts = { 5 6\n 7 x -1 }\n",
    "map/provinces.bmp": b"BM",
    "map/definition.csv": "province;red;green;blue;x;x\n1;10;20;30;Alpha;x\n2;1;2;3;x;x\n"
                          "3;4;5;6; Gamma \xe9 ;x\r\n bad;1;1;1;Bad;x\n4;1;1;1;X;x\n5;0;0;0\n"
                          "1_0;9;9;9;Ten;x\n2;7;7;7;Beta;x\n",
    "map/positions.txt": "1 = { unit = { x = 10.5 y = 20 } }\n2 = { city = { x=1 y=2 } "
                         "text_position = { y = 3 } }\n3 = { }\nx = { unit = { x = 1 } }\n"
                         "+4 = { town = { x = 1_5 y = nan } }\n1 = { factory = { x = 7 } }\n",
    "map/region.txt": "ENG_1 = { 1 2 }\nMET_1 = { 1 2 3 # a comment\n 4 }\nEMPTY_1 = { }\n"
                      "BAD = { x }\nFRA_9 = { 9 }\n",
    "map/continent.txt": "europe = { provinces = { 1 2 x 3.7 } }\nasia = { provinces = 4 }\n"
                         "africa = { provinces = { 5 } provinces = { 6 } }\n",
    "common/countries.txt": 'ENG = "countries/England.txt"\nFRA = countries/France.txt\n'
                            'ENG = "countries/Other.txt"\n GER=  "countries/Germany.txt"  \n'
                            'AUS = "countries/\xd6sterreich.txt"\nxyz = "countries/lower.txt"\n',
    "common/countries/England.txt": 'color = { 200 10 5 }\nparty = { name = "ENG_lib" '
                                    'ideology = liberal war_policy = pacifism }\n'
                                    'party = { name = ENG_con war_policy = jingoism }\n',
    "common/countries/France.txt": 'color = { 1 2 300 }\nparty = { name = "x" }\n',
    "common/countries/Germany.txt": "color = {1 2}\nparty={war_policy=pro_military}\n",
    "common/countries/\xd6sterreich.txt": "color = { 9 9 9 }\n",
    "common/cultures.txt": "british_g = { british = { color = { 1 2 3 } } scottish = { } "
                           "union = ENG color = { 1 2 3 } _x = { } bare = x }\n"
                           "french_g = { french = { } french = { } norman = { { a = b } } }\n",
    "common/goods.txt": "military_goods = { small_arms = { cost = 37.5 } ammunition = { cost = x } "
                        "artillery = { } _hidden = { cost = 1 } loose = 3 }\nraw = { coal = { cost = 2.3 } "
                        "iron = { cost = 1_5 } }\n",
    "common/issues.txt": "party_issues = { war_policy = { jingoism = { mobilization_impact = 0.1 "
                         "rules = { } } pacifism = { mobilization_impact = -0.1 } } }\n"
                         "political_reforms = { conscription = { none = { } mandatory = "
                         "{ mobilisation_size = 0.02 } } press = { free = { } } _x = { } }\n",
    "common/triggered_modifiers.txt": "war_mob = { mobilisation_size = 0.05 trigger = { war = yes "
                                      "AND = { is_greater_power = yes } press = free NOT = { x } } }\n"
                                      "impact_only = { mobilization_impact = 0.2 trigger = none }\n"
                                      "nothing = { x = 1 }\n",
    "common/event_modifiers.txt": "war_mob = { mobilisation_size = 1 mobilization_impact = 5 }\n"
                                  "ev = { mobilisation_size = 0.01 mobilisation_size = 0.02 "
                                  "mobilization_impact = -0.3 }\nlisted = { mobilisation_size = { 1 2 } }\n",
    "common/static_modifiers.txt": "unciv_nation = { mobilisation_size = -0.1 }\nzero = { mobilisation_size = 0 }\n",
    "common/nationalvalues.txt": "nv_order = { effect = { mobilisation_size = 0.01 } }\n",
    "common/defines.lua": "defines = {\ncountry = {\n POP_SIZE_PER_REGIMENT = 3000, -- note\n"
                          "\tMIN_MOBILIZE_LIMIT=0.5,\n--POP_MIN_SIZE_FOR_REGIMENT = 9\n"
                          " X.POP_MIN_SIZE_FOR_REGIMENT = 7\n}\n}\n",
    "common/governments.txt": "absolute_monarchy = { flagType = monarchy election = no }\n"
                              "democracy = { flagType = republic election = YES }\n"
                              "odd = { flagType = { a = \"b'c\" } election = { x } }\nplain = { }\n",
    "common/cb_types.txt": "conquest = { }\nloose = 1\n",
    "poptypes/farmers.txt": "strata = poor\n",
    "poptypes/Soldiers.TXT": "strata = POOR\n",
    "poptypes/aristocrats.txt": "sprite = 1 strata = rich\n",
    "poptypes/\xe9lite.txt": "x.strata = middle\nstrata = \xc9LITE\n",
    "technologies/army_tech.txt": "post_napoleonic = { area = army_doctrine year = 1836 cost = 3600 "
                                  "mobilisation_size = 0.01 ai_chance = { factor = 1 modifier = "
                                  "{ frigate = { hull = 9 } } } frigate = { hull = 2 evasion = 0.05 } }\n"
                                  "navy_tech = { area = { x = y } year = 1e3 cost = 12.7 "
                                  "rgo_goods_output = { coal = 0.1 } list = { 1 2 } }\n",
    "technologies/commerce_tech.txt": "trade = { area = market_structure year = 1850 "
                                      "navy_base = { hull = 1 } _skip = 1 }\n",
    "inventions/army_inventions.txt": "invA = { limit = { post_napoleonic = 1 NOT = { invention = invB } "
                                      "tag = ENG } chance = { base = 5 modifier = { factor = -5 NOT = "
                                      "{ invention = invB } } } effect = { mobilisation_size = 0.02 "
                                      "navy_base = { hull = 1 gun_power = 0.5 } } }\n"
                                      "invB = { limit = { invention = invA navy_tech = 1 } "
                                      "mobilisation_size = 0.01 icon = x }\n"
                                      "invC = { limit = { trade = 1 } effect = { frigate = { hull = -1 } } }\n",
    "units/frigate.txt": "frigate = {\n type = naval\n unit_type = light_ship\n hull = 10\n"
                         " gun_power = 5\n evasion = 0.1\n supply_consumption_score = 2\n}\n",
    "units/infantry.txt": "infantry = { type = land }\n",
    "decisions/form.txt": "political_decisions = { form_germany = { potential = { tag = PRU OR = "
                          "{ tag = NGF } } effect = { change_tag = GER } }\n form_x = { effect = "
                          "{ change_tag_no_core_switch = XXX } potential = { tag = abc } } }\n",
    "localisation/00_base.csv": b"ENG;England;x\nENG_democracy;British Republic\x92s;\n#FRA;Hash France\n"
                                b"FRA;France\x80\x81;\npost_napoleonic;Post-Napoleonic Thought\n"
                                b"army_doctrine;Army Doctrine\r\nbritish;British\x1cmore;\n"
                                b" farmers ;  Farmers\xa0 ;\nENG_1;London\nsmall_arms;Small Arms\n"
                                b"coal;Coal\x0bmore\ncommerce;Commerce\ninvA;Invention A\n"
                                b"ENG_monarchy;\x85Kingdom\x85;\n",
    "localisation/zz_later.csv": b"ENG;Later England\nfrench;French\x9d\ninvC;;\n"
                                 b"army_doctrine;Later Doctrine\n",
}
MOD = {
    "technologies/Army_Tech.txt": "post_napoleonic = { area = army_doctrine year = 1840 }\n"
                                  "new_tech = { area = \"quoted\" }\n",
    "inventions/extra.txt": "invD = { limit = { new_tech = 1 } effect = { mobilisation_size = 0.03 } "
                            "chance = { base = 1 } }\n",
    "localisation/mod.csv": b"ENG;Mod England\nGER_fascism;Reich\nnew_tech;New \xe9 Tech\n",
    "common/countries/England.txt": "color = { 0 0 1 }\n",
    "poptypes/bankers.txt": "strata = middle\n",
    "units/ironclad.txt": "ironclad = {\n type = naval\n unit_type = big_ship\n hull = 30\n"
                          " gun_power = 1_0\n torpedo_attack = 2\n}\n",
    "decisions/mod.txt": "d = { f = { potential = { tag = SAR tag = SIC } effect = { change_tag = ITA } } }\n",
    "map/region.txt": "ITA_1 = { 11 12 }\n",
}


def world(root):
    """The awkward world at `root`: (the mod, the game)."""
    game = os.path.join(root, "game")
    mod = os.path.join(game, "mod", "E")
    for rel, data in GAME.items():
        write(game, rel, data)
    for rel, data in MOD.items():
        write(mod, rel, data)
    os.makedirs(os.path.join(game, "gfx", "flags"), exist_ok=True)
    os.makedirs(os.path.join(mod, "gfx", "flags"), exist_ok=True)
    return mod, game


DAMAGE = [b"{", b"}", b'"', b"=", b" = ", b"#", b"\n", b"\r\n", b"\r", b" ", b"\x1c", b"\x85",
          b"\xa0", b"\xe9", b"\xb2", b"\x81", b";", b"1_000", b"inf", b"nan", b"1e400", b"-", b".",
          b"mobilisation_size = 0.5", b"NOT = { invention = invB }", b"limit = {", b"hull = 1_0",
          b"gun_power = -", b"area = { a = b }", b"flagType = { x }", b"year = 1e400",
          b"color = { 300 2 3 }", b"sea_starts = { 1 2 \xb2 }", b"trigger = { AND = { war = yes } }",
          b"ENG_x;Name;", b"_items = 1", b"x = \"unclosed"]


def damage(root, rnd):
    """Change a few of the world's files at random."""
    files = []
    for folder, _dirs, names in os.walk(root):
        files += [os.path.join(folder, n) for n in names]
    files.sort()
    for path in rnd.sample(files, rnd.randint(1, 4)):
        with open(path, "rb") as fh:
            data = fh.read()
        for _ in range(rnd.randint(1, 5)):
            at = rnd.randint(0, len(data))
            kind = rnd.random()
            if kind < 0.6:
                data = data[:at] + rnd.choice(DAMAGE) + data[at:]
            elif kind < 0.85:
                data = data[:at] + data[at + rnd.randint(1, 20):]
            else:
                b = rnd.randint(0, len(data))
                data = data[:at] + data[b:b + rnd.randint(1, 60)] + data[at:]
        with open(path, "wb") as fh:
            fh.write(data)


def kept_copy(holding):
    """
    Whether a report shows a mod edited since the engine last read it.

    The engine keeps what it read of a mod under the mod's signature, the
    size and time of every file in it. Run on a small campaign, a
    technology's year changed, run again: the report's technology tree must
    carry the new year, and a third run with nothing changed must find the
    copy it kept.
    """
    import matching
    from invariants import payload_of
    mod = matching.a_mod_in_a_game(holding, "Kept", mob_size=0.05)
    saves = os.path.join(holding, "saves")
    os.makedirs(saves)
    matching.a_save(os.path.join(saves, "a.v2"))
    out = os.path.join(holding, "out")
    env = dict(os.environ)
    env.pop("VIC2_NO_ENGINE", None)
    env["VIC2_ENGINE_REQUIRED"] = "1"

    def years():
        run = subprocess.run([sys.executable, os.path.join(HERE, "vic2_analyzer.py"), saves,
                              "--out", out, "--mod-path", mod, "--rebuild", "-q"],
                             capture_output=True, text=True, env=env)
        if run.returncode:
            print("the analyzer failed:\n" + (run.stdout + run.stderr)[-2000:])
            return None
        tree = payload_of(os.path.join(out, "report.html"))["technology"]["tree"]
        return sorted({t["year"] for areas in tree.values() for a in areas for t in a["techs"]})

    first = years()
    techs = os.path.join(mod, "technologies", "army_tech.txt")
    with open(techs) as fh:
        text = fh.read()
    with open(techs, "w") as fh:
        fh.write(text.replace("year = 1836", "year = 1901"))
    second = years()
    kept = [n for n in os.listdir(os.path.join(os.environ["TMPDIR"], "vic2_analyzer_cache"))
            if n.startswith("enginemod_")]
    third = years()
    print("a mod edited between runs: years %s, then %s, then %s; %d copies kept"
          % (first, second, third, len(kept)))
    return first == [1836] and second == [1901] and third == [1901] and len(kept) == 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", default="")
    ap.add_argument("--rounds", type=int, default=200)
    args = ap.parse_args()
    if not os.path.isfile(BIN):
        print("needs a built Rust scanner")
        return SKIPPED
    rnd = random.Random(20260929)
    ok = patterns(rnd, 1500)
    holding = tempfile.mkdtemp(prefix="vic2modread")
    # Python keeps parsed positions in its temp folder: this run's own.
    os.environ["TMPDIR"] = os.path.join(holding, "tmp")
    os.makedirs(os.environ["TMPDIR"])
    tempfile.tempdir = None
    try:
        mod, game = world(os.path.join(holding, "pristine"))
        ok &= bool(same(mod)) & bool(same(game))
        empty = os.path.join(holding, "pristine", "game", "mod", "Empty")
        os.makedirs(os.path.join(empty, "common"))
        # A mod with nothing of its own reads the game's rules.
        ok &= bool(same(empty))
        bad = raised = 0
        for i in range(args.rounds):
            work = os.path.join(holding, "w")
            shutil.rmtree(work, ignore_errors=True)
            shutil.copytree(os.path.join(holding, "pristine"), work)
            damage(work, random.Random(i))
            target = os.path.join(work, "game", "mod", "E") if i % 4 else os.path.join(work, "game")
            got = same(target, say=False)
            raised += got == "raised"
            if not got:
                bad += 1
                print("  (damaged world %d)" % i)
                if bad >= 3:
                    break
        print("damaged worlds: %d read, %d refused by both, %d differ" % (i + 1, raised, bad))
        ok &= bad == 0
        ok &= kept_copy(os.path.join(holding, "kept"))
        if args.mod:
            if os.path.isdir(args.mod):
                ok &= bool(same(args.mod))
            else:
                print("no mod at %s" % args.mod)
                ok = False
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print("the mod reader holds" if ok else "the mod reader DIFFERS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

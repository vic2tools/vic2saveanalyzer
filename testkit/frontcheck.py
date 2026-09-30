#!/usr/bin/env python3
"""
Hold the Rust front end of a run (`vic2scan analyze`) to the Python's.

A run from the command line is now done by the scanner from the start --
finding the saves, settling the game and the mod, the stamp, the dates --
and what it does not do it hands back before saying anything. So every
case here is run twice, the Rust way and all in Python (`VIC2_NO_ENGINE=1`),
and the two must agree on everything a person sees: what was printed to
stdout and to stderr, the exit status, and every file written but the
stamp, which each way takes of itself. The page is compared by what it
carries (`enginecheck.page`): its compressed parts are two compressors'
output.

The cases are the edges of the front end: every refusal it words, a single
save, a folder with none, two saves of one date, `~` and `$VAR` in paths, a
relative path, the settings that change the spec, a table open elsewhere,
"nothing has changed" on the second run, and the runs it hands back.

    python3 testkit/frontcheck.py
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import matching                                            # noqa: E402
import savefmt                                             # noqa: E402
from edges import a_save                                   # noqa: E402
from enginecheck import page                               # noqa: E402
from outcome import SKIPPED                                # noqa: E402

BIN = os.path.join(HERE, "scanner", "target", "release",
                   "vic2scan" + (".exe" if os.name == "nt" else ""))
TAGS = ("ENG", "FRA", "PRU")


def world(holding):
    """A game with a mod in it, and a campaign of four saves played on it."""
    mod = matching.a_mod_in_a_game(holding, "Mod", tags=list(TAGS), mob_size=0.05,
                                   pop_per_regiment=2000,
                                   pops=["farmers", "labourers", "craftsmen", "soldiers",
                                         "aristocrats", "bankers"])
    # A trigger holding lists where one value belongs, which Python judges
    # by their repr: nobody is tagged "['a']", so NOT holds for everyone.
    with open(os.path.join(mod, "common", "triggered_modifiers.txt"), "w") as fh:
        fh.write("listy = {\n\tmobilisation_size = 0.01\n\ttrigger = {\n"
                 "\t\tNOT = { tag = { a } tag = { b c } }\n\t}\n}\n")
    saves = os.path.join(holding, "saves")
    os.makedirs(saves)
    for i, date in enumerate(("1880.1.1", "1881.1.1", "1881.7.1", "1882.1.1")):
        a_save(os.path.join(saves, "%d.v2" % i), date, tags=TAGS, provinces=3,
               techs=["flintlock_rifles"], inventions=[1],
               wars=savefmt.war("The Test War", "ENG", "FRA") if i else "")
    return mod, saves


def reflow(data, rnd, how):
    """
    The same tokens, laid out another way: every run of whitespace outside
    quotes made one space (`line`), something random (`random`), or its tabs
    taken out (`untabbed`). A save the game did not lay out, which the
    scanner walks a token at a time as Python does.
    """
    import re
    parts = re.split(rb'("[^"]*")', data)
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(part)
            continue
        if how == "line":
            part = re.sub(rb"\s+", b" ", part)
        elif how == "untabbed":
            part = part.replace(b"\t", b"")
        else:
            part = re.sub(rb"\s+", lambda m: rnd.choice(
                [b" ", b"\n", b"\r\n\t", b"  \t", b"\n\n", b"\x0b "]), part)
        out.append(part)
    return b"".join(out)


def run(argv, cwd, env, out):
    """(status, stdout, stderr) of one run, the out folder's path made OUT."""
    done = subprocess.run([sys.executable, os.path.join(HERE, "vic2_analyzer.py")] + argv,
                          capture_output=True, text=True, cwd=cwd, env=env, timeout=300)
    clean = lambda t: t.replace(out, "OUT")
    return done.returncode, clean(done.stdout), clean(done.stderr)


def files_of(folder):
    """{name: what it holds} of what a run left, the stamp aside, the page
    as what it carries."""
    got = {}
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if name == "report.html":
                got[name] = page(folder)
            elif name == "report.data.gz":
                got[name] = "read with the page"
            elif name != "report.stamp" and os.path.isfile(path):
                with open(path, "rb") as fh:
                    got[name] = fh.read()
    return got


def main():
    if not os.path.isfile(BIN):
        print("needs a built Rust scanner")
        return SKIPPED
    holding = tempfile.mkdtemp(prefix="vic2front")
    try:
        mod, saves = world(holding)
        game = os.path.join(holding, "game")
        # An empty mod in an install with no rules of its own to lend it.
        bare_game = matching.a_game(os.path.join(holding, "bare"))
        empty_mod = os.path.join(bare_game, "mod", "Empty")
        os.makedirs(os.path.join(empty_mod, "common"))
        # Two saves of one date, and a folder with none.
        twice = os.path.join(holding, "twice")
        os.makedirs(twice)
        for name in ("a.v2", "b.v2", "c.v2"):
            a_save(os.path.join(twice, name), "1880.1.1" if name != "c.v2" else "1881.1.1",
                   tags=TAGS)
        nothing = os.path.join(holding, "nothing")
        os.makedirs(nothing)
        with open(os.path.join(nothing, "readme.txt"), "w") as fh:
            fh.write("not a save")
        # Good saves among files the reader refuses, each in Python's words.
        mixed = os.path.join(holding, "mixed")
        shutil.copytree(saves, mixed)
        with open(os.path.join(mixed, "0a_zip.v2"), "wb") as fh:
            fh.write(b"PK\x03\x04" + b"\0" * 100)
        open(os.path.join(mixed, "0b_empty.v2"), "w").close()
        with open(os.path.join(saves, "3.v2"), "rb") as fh:
            whole = fh.read()
        with open(os.path.join(mixed, "1b_cut.v2"), "wb") as fh:
            fh.write(whole[:len(whole) // 2])
        os.makedirs(os.path.join(mixed, "2b_folder.v2"))
        locked_save = os.path.join(mixed, "2c_locked.v2")
        shutil.copyfile(os.path.join(saves, "0.v2"), locked_save)
        os.chmod(locked_save, 0)
        refused_only = os.path.join(holding, "refused")
        os.makedirs(refused_only)
        for name in ("0a_zip.v2", "0b_empty.v2", "1b_cut.v2"):
            shutil.copyfile(os.path.join(mixed, name), os.path.join(refused_only, name))
        # A war the scanner used to hand back: a block where a name belongs,
        # a battle whose numbers Python spells its own way, a goal fulfilled
        # by a block.
        odd = os.path.join(holding, "odd")
        os.makedirs(odd)
        odd_war = ["active_war=", "{",
                   '\tname={ first="The" second="Odd War" }',
                   '\toriginal_attacker="ENG"', '\toriginal_defender={ "FRA" }',
                   '\tattacker="ENG"', '\tdefender="FRA"', '\tattacker={ x=1 }',
                   "\thistory=", "\t{", "\t\t1880.6.1=", "\t\t{",
                   '\t\t\tadd_attacker="ENG"', "\t\t\tadd_defender={ a=b }",
                   "\t\t\tbattle=", "\t\t\t{", '\t\t\t\tname={ 1 2 }', "\t\t\t\tlocation=1_2",
                   "\t\t\t\tresult={ yes }",
                   "\t\t\t\tattacker=", "\t\t\t\t{", '\t\t\t\t\tcountry="ENG"',
                   "\t\t\t\t\tleader={ n=1 }", "\t\t\t\t\tlosses=1_000", "\t\t\t\t\tinfantry= 2_000 ",
                   "\t\t\t\t}", "\t\t\t}", "\t\t}", "\t}",
                   "\twar_goal=", "\t{", '\t\tcasus_belli={ a="b\'c" }', '\t\tactor="ENG"',
                   '\t\treceiver="FRA"', "\t\tis_fulfilled={ yes }", "\t\tdate=1880.6.1", "\t}",
                   "\taction=\"1880.5.1\"", "}"]
        for i, date in enumerate(("1880.1.1", "1881.1.1")):
            a_save(os.path.join(odd, "%d.v2" % i), date, tags=TAGS, wars=odd_war)
        # Mods Python refuses, each a copy of the good one with one fault.
        def faulty(name, rel, text, append=True):
            where = os.path.join(game, "mod", name)
            shutil.copytree(mod, where)
            target = os.path.join(where, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "ab" if append else "wb") as fh:
                fh.write(text.encode("latin-1"))
            return where
        bad_define = faulty("BadDefine", "common/defines.lua",
                            "NDefines = { POP_SIZE_PER_REGIMENT = 1.2.3, }\n", append=False)
        bad_ship = faulty("BadShip", "units/frigate.txt",
                          "frigate = {\n\ttype = naval\n\thull = -\n}\n", append=False)
        bad_region = faulty("BadRegion", "map/region.txt", "XX_1 = { 1 \xb2 }\n", append=False)
        # With a bitmap and a definition of its own, the map read is its own.
        with open(os.path.join(bad_region, "map", "provinces.bmp"), "wb") as fh:
            fh.write(b"BM")
        # Saves laid out another way, from the fullest save the builders
        # write: armies at sea, states, colonies, occupied land, a war.
        import random
        walked = os.path.join(holding, "walked")
        os.makedirs(walked)
        full = savefmt.furnished(os.path.join(holding, "furnished.v2"))
        with open(full, "rb") as fh:
            rich = fh.read()
        rnd = random.Random(7)
        for i, (date, how) in enumerate((("1881.3.24", "line"), ("1882.1.1", "random"),
                                          ("1883.1.1", "untabbed"), ("1884.1.1", "random"))):
            data = rich.replace(b'date="1881.3.24"', ('date="%s"' % date).encode())
            with open(os.path.join(walked, "%d.v2" % i), "wb") as fh:
                fh.write(reflow(data, rnd, how))
        afile = os.path.join(holding, "afile")
        with open(afile, "w") as fh:
            fh.write("x")
        away = os.path.join(holding, "elsewhere", "mod", "Away")
        shutil.copytree(mod, away)

        M = ["--mod-path", mod]
        cases = [
            ("a report", [saves] + M, None),
            ("a report, quiet", [saves, "-q"] + M, None),
            ("the game alone", [saves, "--game-root", game], None),
            ("the game named twice", [saves, "--game-root", game] + M, None),
            ("one save", [os.path.join(saves, "2.v2")] + M, None),
            ("two saves of one date", [twice] + M, None),
            ("a folder with no saves", [nothing] + M, None),
            ("a path that is not there", [os.path.join(holding, "nowhere")] + M, None),
            ("$VAR in the saves path", ["$VIC2FRONT/saves"] + M, None),
            ("~ in the saves path", ["~/saves"] + M, None),
            ("a relative saves path", ["saves", "--mod-path", "game/mod/Mod"], None),
            ("a mod outside a game", [saves, "--mod-path", away], None),
            ("a game root that is not one", [saves, "--game-root", saves], None),
            ("a mod in another game", [saves, "--game-root", bare_game] + M, None),
            ("no game at all", [saves], None),
            ("a mod with no rules", [saves, "--mod-path", empty_mod], None),
            ("an out folder under a file", [saves, "--out", os.path.join(afile, "out")] + M,
             "own-out"),
            ("only some nations", [saves, "--tags", "ENG", "PRU"] + M, None),
            ("no tags named", [saves, "--tags"] + M, None),
            ("no page", [saves, "--no-html"] + M, None),
            ("the settings a mod gives way to",
             [saves, "--pop-per-regiment", "1500", "--mob-types", "farmers", "farmers",
              "--mobilisation-size", "0.5", "--min-pop", "5000", "--player-nations",
              "FRA", "--mob-include-occupied", "--map-scale", "3", "-j", "1"] + M, None),
            ("no players", [saves, "--player-nations"] + M, None),
            ("the page split", [saves, "--split"] + M, None),
            ("no cache", [saves, "--no-cache"] + M, None),
            ("a table open elsewhere", [saves] + M, "locked"),
            ("nothing has changed", [saves] + M, "again"),
            ("nothing has changed, quiet", [saves, "-q"] + M, "again"),
            ("rebuilt on purpose", [saves, "--rebuild"] + M, "again"),
            ("a setting changed since", [saves, "--min-pop", "3000"] + M, "changed"),
            ("a save touched since", [saves] + M, "touched"),
            ("saves it refuses", [mixed] + M, None),
            ("saves it refuses, quiet", [mixed, "-q"] + M, None),
            ("saves it refuses, one at a time", [mixed, "-j", "1"] + M, None),
            ("nothing but saves it refuses", [refused_only] + M, None),
            ("saves it refuses, rebuilt", [mixed, "--rebuild"] + M, "again"),
            ("a war with blocks where names belong", [odd] + M, None),
            ("a define that is not a number", [saves, "--mod-path", bad_define], None),
            ("a ship stat that is not a number", [saves, "--mod-path", bad_ship], None),
            ("a region naming a superscript", [saves, "--mod-path", bad_region], None),
            ("saves laid out another way", [walked] + M, None),
            ("saves laid out another way, one at a time", [walked, "-j", "1"] + M, None),
            ("a diagnostic", [saves, "--explain-mob", "ENG"] + M, "handed back"),
            ("a peek", [saves, "--peek"] + M, "handed back"),
        ]
        bad = 0
        # The mod's signature, which keys the engine's copy of the mod and
        # goes into the stamp: Python's MD5 over the same walk.
        import mod_reader
        for folder in (mod, game, away, empty_mod, os.path.join(holding, "nowhere")):
            mine = subprocess.run([BIN, "mod-signature", folder], capture_output=True,
                                  text=True).stdout.strip()
            theirs = mod_reader.mod_signature(folder)
            if mine != theirs:
                bad += 1
                print("DIFFERS: the signature of %s: %s against %s" % (folder, mine, theirs))
        for name, argv, how in cases:
            got = {}
            for way in ("rust", "python"):
                place = os.path.join(holding, "case", name.replace(" ", "_"), way)
                os.makedirs(place)
                out = os.path.join(place, "out")
                env = dict(os.environ)
                env.pop("VIC2_NO_ENGINE", None)
                env.pop("VIC2_ENGINE_REQUIRED", None)
                env["VIC2FRONT"] = holding
                env["HOME"] = holding
                env["TMPDIR"] = os.path.join(place, "tmp")
                os.makedirs(env["TMPDIR"])
                log = os.path.join(place, "front.log")
                env.pop("VIC2_NO_FRONT", None)
                if way == "python":
                    env["VIC2_NO_ENGINE"] = "1"
                else:
                    env["VIC2_FRONT_LOG"] = log
                full = list(argv) if how == "own-out" else list(argv) + ["--out", out]
                if how == "locked":
                    os.makedirs(out)
                    locked = os.path.join(out, "ships_by_type.csv")
                    open(locked, "w").close()
                    os.chmod(locked, stat.S_IREAD)
                if how == "again":
                    run([a for a in full if a not in ("-q", "--rebuild")], holding, env, out)
                if how == "changed":
                    run([a for a in full if a not in ("--min-pop", "3000")], holding, env, out)
                if how == "touched":
                    run(full, holding, env, out)
                    touched = os.path.join(saves, "1.v2")
                    st = os.stat(touched)
                    os.utime(touched, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
                said = run(full, holding, env, out)
                got[way] = (said, files_of(out))
                if how == "locked":
                    os.chmod(locked, stat.S_IREAD | stat.S_IWRITE)
                if way == "rust":
                    with open(log) as fh:
                        got["log"] = fh.read().strip().splitlines()[-1:]
            (rs, rfiles), (py, pfiles) = got["rust"], got["python"]
            same = rs == py and rfiles == pfiles
            # A case the Rust handed back compares the Python with itself.
            # A refusal is written for Python to raise (status 4), which
            # the person sees as status 1.
            logged = {"done: status 4": "done: status 1"}.get(got["log"][0] if got["log"] else "",
                                                             got["log"][0] if got["log"] else "")
            handed = logged != "done: status %d" % rs[0]
            if handed != (how == "handed back"):
                same = False
                print("  the Rust %s %s: %s" % ("handed back" if handed else "made",
                                               name, got["log"]))
            if not same:
                bad += 1
                print("DIFFERS: %s" % name)
                for label, a, b in (("status", rs[0], py[0]), ("stdout", rs[1], py[1]),
                                    ("stderr", rs[2], py[2])):
                    if a != b:
                        print("  %s:\n    rust:   %r\n    python: %r" % (label, a, b))
                if rfiles != pfiles:
                    names = sorted(set(rfiles) | set(pfiles))
                    print("  files that differ: %s" % [n for n in names
                                                       if rfiles.get(n) != pfiles.get(n)])
            else:
                print("same: %s (status %s, %d files)" % (name, rs[0], len(rfiles)))
        print("\n%d of %d cases differ" % (bad, len(cases)))
        return 1 if bad else 0
    finally:
        try:
            os.chmod(locked_save, stat.S_IREAD | stat.S_IWRITE)
        except (OSError, NameError):
            pass
        shutil.rmtree(holding, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

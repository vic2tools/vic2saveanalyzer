#!/usr/bin/env python3
"""
Hold the run's front end (`vic2scan analyze`) to the answers recorded for it.

A run from the command line is done by the scanner from the start --
finding the saves, settling the game and the mod, the stamp, the dates, the
diagnostics, `--cross` -- and every case here must print, exit and write
what is recorded for it in `testkit/expected/frontcheck/` (`expected.py`):
stdout and stderr, the exit status, and every file but the stamp, the page
by what it carries. The answers were the pure Python's, taken while it was
still here to ask, and are updated with `--update` after a deliberate
change.

The cases are the edges of the front end: every refusal it words, a single
save, a folder with none, two saves of one date, `~` and `$VAR` in paths, a
relative path, the settings that change the spec, a table open elsewhere,
"nothing has changed" on the second run, saves laid out another way, the
diagnostics, `--peek`, `--verify` and `--cross`, and files that cannot be
read at all.

    python3 testkit/frontcheck.py [--update]
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

import expected                                            # noqa: E402
import matching                                            # noqa: E402
import savefmt                                             # noqa: E402
from edges import a_save                                   # noqa: E402
from outcome import SKIPPED                                # noqa: E402

BIN = os.path.join(HERE, "scanner", "target", "release",
                   "vic2scan" + (".exe" if os.name == "nt" else ""))
TAGS = ("ENG", "FRA", "PRU")


def shut(path):
    """
    Make `path` a file that cannot be opened for reading; the way back, as a
    function. A mode of 0 does it where permissions are modes. Windows has no
    such mode, so the file is held open by a handle that shares it with no
    one, which refuses every other open the same way until it is let go.
    """
    if os.name != "nt":
        os.chmod(path, 0)
        return lambda: os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    held = kernel.CreateFileW(path, 0x80000000, 0, None, 3, 0x80, None)   # read, no sharing
    if held in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    return lambda: kernel.CloseHandle(held)


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


def cross_world(holding):
    """
    A game with two mods a letter apart and campaigns that test the survey:
    one only the second fits, one both fit, one nothing fits, two folders
    of one name, one too deep to count, and a save whose event flags say
    it came from another game. (the game, the folder of campaigns)
    """
    tags8 = ["ENG", "FRA", "PRU", "RUS", "AUS", "TUR", "SPA", "USA"]
    game = matching.a_game(os.path.join(holding, "xgame"))
    matching.a_mod(os.path.join(game, "mod", "Alpha"), tags=tags8, provinces=range(1, 41))
    matching.a_mod(os.path.join(game, "mod", "Beta"), tags=tags8 + ["NEW"], provinces=range(1, 41))
    top = os.path.join(holding, "xcampaigns")

    def campaign(rel, tags, dates, flags=None):
        folder = os.path.join(top, *rel.split("/"))
        os.makedirs(folder, exist_ok=True)
        for i, date in enumerate(dates):
            parts = [savefmt.head(date, player=tags[0], flags=flags[i] if flags else ())]
            for pid in range(1, 41):
                parts.append(savefmt.province(pid, tags[(pid - 1) % len(tags)],
                                              [savefmt.pop("farmers", pid, 1000 + pid * 7 + i)]))
            for k, tag in enumerate(tags):
                parts.append(savefmt.country(tag, techs=["flintlock_rifles"], inventions=[1],
                                             capital=k + 1))
            savefmt.write(os.path.join(folder, "s%d.v2" % i), *parts)

    campaign("onlybeta", ["ENG", "FRA", "NEW"], ["1880.1.1", "1881.1.1", "1882.1.1"])
    campaign("both", ["ENG", "FRA"], ["1880.1.1", "1880.7.1", "1881.1.1", "1881.7.1"],
             flags=[["f%d" % k for k in range(8)]] + [["g%d" % k for k in range(8)]] * 3)
    campaign("none", ["ZZZ", "ENG"], ["1880.1.1", "1881.1.1"])
    campaign("a/run", ["ENG", "PRU"], ["1885.1.1", "1886.1.1"])
    campaign("b/run", ["PRU", "RUS"], ["1885.1.1"])
    campaign("d1/d2/d3/d4/d5/d6/deep", ["ENG"], ["1890.1.1"])
    return game, top


def mod_signature(mod_path):
    """
    What `vic2scan mod-signature` has to answer, as the Python it replaced
    worked it out: an MD5 of the mod folder's path and every file below it
    (its path under the folder, size and time, `os.walk` order with names
    sorted, linked folders not followed), and of the game folders beneath
    a mod that sits in an install's mod folder.
    """
    import hashlib
    from mod_reader import _base_game_path
    if not mod_path:
        return "no-mod"
    mod_path = os.path.abspath(os.path.expanduser(os.path.expandvars(mod_path)))
    roots = [mod_path]
    base = _base_game_path(mod_path)
    if base:
        roots.extend(os.path.join(base, folder) for folder in (
            "common", "decisions", "gfx/flags", "inventions", "localisation",
            "map", "poptypes", "technologies", "units"))
    digest = hashlib.md5()
    for source in roots:
        digest.update(source.encode("utf-8", "replace"))
        _sign_folder(digest, source, "")
    return digest.hexdigest()


def _sign_folder(digest, folder, under):
    files, folders = [], []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    is_dir = False
                (folders if is_dir else files).append(entry)
    except OSError:
        return
    files.sort(key=lambda entry: entry.name)
    for entry in files:
        try:
            st = entry.stat()
        except OSError:
            continue
        digest.update(("%s|%d|%d\n" % (os.path.join(under, entry.name), st.st_size,
                                        st.st_mtime_ns)).encode("utf-8", "replace"))
    folders.sort(key=lambda entry: entry.name)
    for entry in folders:
        path = os.path.join(folder, entry.name)
        if not os.path.islink(path):
            _sign_folder(digest, path, os.path.join(under, entry.name))


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--update", action="store_true",
                    help="write what the program answers now as the expected answers")
    args = ap.parse_args()
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
        release_save = shut(locked_save)
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

        xgame, xtop = cross_world(holding)
        X = [xtop, "--cross", "--game-root", xgame]
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
            ("where a mobilisation size comes from", [saves, "--explain-mob", "ENG"] + M, None),
            ("where it comes from, quiet", [saves, "--explain-mob", "eng", "-q"] + M, None),
            ("a mobilization pool", [walked, "--explain-mob-pool", "SWE"] + M, None),
            ("a pool, occupied land counted",
             [walked, "--explain-mob-pool", "SWE", "--mob-include-occupied", "--mob-types",
              "farmers", "labourers"] + M, None),
            ("a pool, another regiment size", [walked, "--explain-mob-pool", "DEN",
                                               "--pop-per-regiment", "1000"] + M, None),
            ("the inventions a nation holds", [saves, "--inventions", "FRA"] + M, None),
            ("the invention decode checked", [saves, "--check-inventions"] + M, None),
            ("a diagnostic among saves it refuses", [mixed, "--explain-mob", "PRU"] + M, None),
            ("campaigns compared", X, None),
            ("campaigns compared, quiet", X + ["-q"], None),
            ("campaigns compared, one named primary", X + ["--primary", "BOTH"], None),
            ("campaigns compared, a primary not there", X + ["--primary", "nope"], None),
            ("campaigns compared under one mod",
             [xtop, "--cross", "--mod-path", os.path.join(xgame, "mod", "Beta")], None),
            ("campaigns compared, one named",
             X + ["--campaign-mod", "none=" + os.path.join(xgame, "mod", "Beta")], None),
            ("campaigns compared, one named wrongly",
             X + ["--campaign-mod", "none=" + holding], None),
            ("campaigns compared, no game named", [xtop, "--cross"], None),
            ("campaigns compared, again", X, "again"),
            ("campaigns compared, a diagnostic", X + ["--explain-mob", "ENG"], None),
            ("a diagnostic of a nation not there", [saves, "--explain-mob", "XXX"] + M, None),
            ("two diagnostics at once",
             [saves, "--explain-mob", "ENG", "--inventions", "FRA"] + M, None),
            ("a peek", [saves, "--peek"] + M, None),
            ("a peek at a save laid out another way", [walked, "--peek"] + M, None),
            ("a peek at the fullest save", [os.path.join(holding, "furnished.v2"), "--peek"], None),
            ("a peek at a file it cannot read", [refused_only, "--peek"] + M, None),
            ("a peek beside a diagnostic", [saves, "--peek", "--explain-mob", "ENG"] + M, None),
            ("verified", [saves, "--verify"] + M, None),
            ("verified, laid out another way", [walked, "--verify", "-j", "1"], None),
            ("verified among files it cannot read", [mixed, "--verify"] + M, None),
        ]
        bad = 0
        temps = []
        book = expected.Book(expected.REPO, "frontcheck", args.update)
        # What --cross reads a save for, found by hand-written scanners, held
        # to the patterns they stand for on the saves here and on random text.
        sniffed = subprocess.run([BIN, "selftest-sniff"] + sorted(
            os.path.join(r, f) for r, _d, fs in os.walk(xtop) for f in fs) + [full],
            capture_output=True, text=True)
        print(sniffed.stdout.strip())
        if sniffed.returncode:
            bad += 1
        # The mod's signature, which keys the engine's copy of the mod and
        # goes into the stamp: Python's MD5 over the same walk.
        for folder in (mod, game, away, empty_mod, os.path.join(holding, "nowhere")):
            mine = subprocess.run([BIN, "mod-signature", folder], capture_output=True,
                                  text=True).stdout.strip()
            theirs = mod_signature(folder)
            if mine != theirs:
                bad += 1
                print("DIFFERS: the signature of %s: %s against %s" % (folder, mine, theirs))
        width = max(len(n) for n, _a, _h in cases)
        for name, argv, how in cases:
            place = os.path.join(holding, "case", expected.slug(name))
            os.makedirs(place)
            out = os.path.join(place, "out")
            env = dict(os.environ)
            env["VIC2FRONT"] = holding
            env["HOME"] = holding
            if os.name == "nt":
                env["USERPROFILE"] = holding        # where Windows looks for `~`
            # Short: a worker pool's socket may live in it, and a path past
            # 108 bytes is refused.
            env["TMPDIR"] = tempfile.mkdtemp(prefix="vf", dir="/tmp" if os.name != "nt" else None)
            temps.append(env["TMPDIR"])
            full = list(argv) if how == "own-out" else list(argv) + ["--out", out]
            places = [(env["TMPDIR"], "TMP"), (holding, "HOLDING")]
            if how == "locked":
                os.makedirs(out)
                locked = os.path.join(out, "ships_by_type.csv")
                open(locked, "w").close()
                os.chmod(locked, stat.S_IREAD)
            before = lambda a: expected.run(a, holding, env, out, places)
            if how == "again":
                before([a for a in full if a not in ("-q", "--rebuild")])
            if how == "changed":
                before([a for a in full if a not in ("--min-pop", "3000")])
            if how == "touched":
                before(full)
                touched = os.path.join(saves, "1.v2")
                st = os.stat(touched)
                os.utime(touched, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
            got = expected.run(full, holding, env, out, places)
            if how == "locked":
                os.chmod(locked, stat.S_IREAD | stat.S_IWRITE)
            found = book.hold(name, got)
            if found:
                bad += 1
            expected.report(name, found, width)
        gone = book.finish()
        if gone:
            print("dropped the record of %d cases no longer asked: %s" % (len(gone), gone))
        print("\n%d of %d cases differ" % (bad, len(cases)))
        return 1 if bad else 0
    finally:
        for t in locals().get("temps", ()):
            shutil.rmtree(t, ignore_errors=True)
        try:
            release_save()
        except (OSError, NameError):
            pass
        shutil.rmtree(holding, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

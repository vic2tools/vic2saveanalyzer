#!/usr/bin/env python3
"""
A mod is wherever its `.mod` file points, not only `<install>/mod/<name>`.

In Victoria II a mod is what a `.mod` file in `<install>/mod/` says it is:
`path` names its folder, relative to the install. A mod kept as a clone of
its repository sits a level deeper -- `mod/GGG.mod` saying
`path = "mod/GGG/GGG"` -- and the analyzer used to find mods by looking two
folders up from them and at the children of `mod/` only, so such a mod was
never offered, never settled and never read on its install.

    python3 testkit/modplaces.py

Builds an install with two mods side by side: `Plain` at `mod/Plain`, the
way most mods sit, and `GGG` at `mod/GGG/GGG` behind its `.mod` file, which
also replaces `common` and `decisions` the way the reported mod does. Then
asks, of each:

- the window: is the mod folder a folder of mods, which mods does a
  campaign row offer, where does the search for one start;
- the scanner: does naming the mod settle on the install, does `--cross`
  offer it and match a campaign to it;
- the mod reader: are the mod's own files read, the game's map, flags and
  rules inherited, and a folder the `.mod` file replaces taken from the mod
  alone;
- the engine's kept copy of a mod: does an edit to the `.mod` file's
  `replace_path` reach it.
"""
import json
import os
import subprocess
import sys

import kit
import fixtures
from fixtures import TAGS, TECHS


# `gfx` replaces that folder's own files and not the folders inside it, so
# the game's gfx/flags are still read: the game names each folder it
# replaces, `history/pops/1836.1.1` and not `history/pops`.
GGG_MOD = """name = "GGG: Gozomedes' Great Game 1.0"
path = "mod/GGG/GGG"
user_dir = "GGG"
replace_path = "common"
replace_path = "decisions"
replace_path = "gfx"
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="latin-1") as fh:
        fh.write(text)


def an_install(root):
    """An install with a map, flags, a culture, a formation and a rule of its own."""
    game = fixtures.a_vanilla(root, techs=TECHS)
    write(os.path.join(game, "map", "provinces.bmp"), "BM")
    write(os.path.join(game, "gfx", "flags", "ENG.tga"), "")
    write(os.path.join(game, "technologies", "zz_game_only.txt"),
          "game_only_tech = {\n\tarea = army_tech\n\tyear = 1836\n\tcost = 100\n}\n")
    write(os.path.join(game, "common", "cultures.txt"),
          "germanic = {\n\tgame_culture = {\n\t\tcolor = { 1 2 3 }\n\t}\n}\n")
    write(os.path.join(game, "decisions", "forms.txt"),
          "political_decisions = {\n\tform_germany = {\n\t\tpotential = { tag = PRU }\n"
          "\t\teffect = { change_tag = GER }\n\t}\n}\n")
    return game


def the_world(holding):
    """(install, Plain, GGG): the reporter's layout beside the usual one."""
    game = an_install(os.path.join(holding, "game"))
    plain = fixtures.a_mod(os.path.join(game, "mod", "Plain"))
    write(os.path.join(game, "mod", "Plain.mod"),
          'name = "Plain"\npath = "mod/Plain"\n')
    ggg = fixtures.a_mod(os.path.join(game, "mod", "GGG", "GGG"), tags=TAGS + ["BAV"])
    # Its map comes from the game, as a mod that leaves the map alone does.
    for name in os.listdir(os.path.join(ggg, "map")):
        os.remove(os.path.join(ggg, "map", name))
    os.rmdir(os.path.join(ggg, "map"))
    write(os.path.join(game, "mod", "GGG.mod"), GGG_MOD)
    # What a clone of a repository carries beside the mod.
    write(os.path.join(game, "mod", "GGG", "README.md"), "GGG\n")
    # A second mod whose folder is also called Plain, behind a .mod file
    # saved the way an editor might leave it: a byte-order mark, CRLF
    # line ends and a comment.
    fixtures.a_mod(os.path.join(game, "mod", "Dup", "Plain"), tags=TAGS + ["DUP"])
    with open(os.path.join(game, "mod", "Dup.mod"), "w", encoding="utf-8-sig",
              newline="\r\n") as fh:
        fh.write('# kept beside the other Plain\nname = "Dup"\npath = "mod/Dup/Plain"\n')
    return game, plain, ggg


DUP_LABEL = "mod/Dup/Plain"


def same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


# ------------------------------------------------------------------ window

def window_problems(report_tab, game, plain, ggg):
    wrong = []
    home = os.path.join(game, "mod")
    if not hasattr(report_tab, "installed_mods"):
        return ["the window has no installed_mods(install) to list the mods a campaign row offers"]
    offered = report_tab.installed_mods(game)
    paths = {label: path for label, path in offered}
    if not any(same(p, ggg) for p in paths.values()):
        wrong.append("the window does not offer GGG at mod/GGG/GGG: it offers %s" % offered)
    if not any(same(p, plain) for p in paths.values()):
        wrong.append("the window no longer offers Plain at mod/Plain: it offers %s" % offered)
    if "GGG" not in paths or "Plain" not in paths:
        wrong.append("the window's labels are not the mods' folder names: %s" % sorted(paths))
    if DUP_LABEL not in paths or not same(paths[DUP_LABEL], os.path.join(game, "mod", "Dup", "Plain")):
        wrong.append("the second folder called Plain is not offered as %s: %s"
                     % (DUP_LABEL, sorted(paths)))
    kind = report_tab.mod_kind(ggg)
    if kind != ("mod", ggg):
        wrong.append("mod_kind(mod/GGG/GGG) is %r, not one mod" % (kind,))
    kind = report_tab.mod_kind(home)
    if kind[0] != "home" or not same(kind[1], game):
        wrong.append("mod_kind(mod) is %r, not the folder of mods of the install" % (kind,))
    root = report_tab.search_root(ggg)
    if not root or not same(root, game):
        wrong.append("search_root(mod/GGG/GGG) is %r, not the install" % root)
    try:
        _mod, settled = report_tab.settle_game(ggg, game)
        if not same(settled, game):
            wrong.append("the window settles mod/GGG/GGG on %s, not the install" % settled)
    except ValueError as refused:
        wrong.append("the window refuses mod/GGG/GGG: %s" % refused)
    return wrong


def window_alone_problems(report_tab, holding):
    """A mod folder holding only a mod one level down is still a folder of mods."""
    game = an_install(os.path.join(holding, "alone"))
    fixtures.a_mod(os.path.join(game, "mod", "GGG", "GGG"))
    write(os.path.join(game, "mod", "GGG.mod"), GGG_MOD)
    kind = report_tab.mod_kind(os.path.join(game, "mod"))
    if kind[0] != "home":
        return ["a mod folder whose only mod is mod/GGG/GGG is %r, not a folder of mods"
                % (kind,)]
    return []


# ----------------------------------------------------------------- scanner

def settled_line(game, mod, holding, env):
    saves = os.path.join(holding, "one-campaign")
    if not os.path.isdir(saves):
        os.makedirs(saves)
        fixtures.a_save(os.path.join(saves, "1.v2"))
    done = kit.analyze(saves, "--out", os.path.join(holding, "out-one"), "--rebuild",
                       "--mod-path", mod, env=env)
    line = next((l for l in done.stdout.splitlines() if l.startswith("Victoria II at ")), None)
    return done, line


def scanner_problems(game, plain, ggg, holding, env):
    wrong = []
    for name, mod in (("Plain", plain), ("GGG", ggg)):
        done, line = settled_line(game, mod, holding, env)
        want = "Victoria II at %s, with %s." % (game, name)
        if line != want:
            wrong.append("--mod-path %s settles as %r, not %r -- %s"
                         % (name, line, want, (done.stdout + done.stderr)[-600:]))

    # A campaign only GGG explains: it holds a country only GGG lists.
    top = os.path.join(holding, "campaigns")
    for name in ("gozo", "plain", "dup"):
        os.makedirs(os.path.join(top, name))
    fixtures.a_save(os.path.join(top, "gozo", "1.v2"), tags=TAGS + ["BAV"])
    fixtures.a_save(os.path.join(top, "plain", "1.v2"), provinces=range(1, 41))
    # And one only the second Plain explains, named as the window names it.
    fixtures.a_save(os.path.join(top, "dup", "1.v2"), tags=TAGS + ["DUP"])
    done = kit.analyze(top, "--cross", "--game-root", game, "--out",
                       os.path.join(holding, "out-cross"), "--no-html", "--no-cache", env=env)
    said = done.stdout + done.stderr
    lines = {l.split()[0]: l for l in said.splitlines() if l.startswith("  ") and "->" in l}
    for campaign, label in (("gozo", "GGG"), ("dup", DUP_LABEL)):
        line = lines.get(campaign, "")
        if done.returncode or line.split("->")[-1].split()[:1] != [label]:
            wrong.append("--cross did not read %s under %s: %r -- %s"
                         % (campaign, label, line.strip(), said[-800:]))
    return wrong


# -------------------------------------------------------------- the reader

def exported(path):
    run = subprocess.run([kit.SCANNER, "mod-export", path], capture_output=True)
    if run.returncode:
        return None, run.stderr.decode("utf-8", "replace")
    return json.loads(run.stdout.decode("utf-8")), None


def reader_problems(game, plain, ggg):
    wrong = []
    for name, mod, replaced in (("Plain", plain, False), ("GGG", ggg, True)):
        j, said = exported(mod)
        if j is None:
            wrong.append("mod-export %s declined: %s" % (name, said))
            continue
        # Neither ships a whole map (Plain has no provinces.bmp), so both
        # draw on the game's.
        if not j["map_csv"] or not same(j["map_csv"], os.path.join(game, "map", "definition.csv")):
            wrong.append("%s does not read the game's map: map_csv is %r" % (name, j["map_csv"]))
        if not any(same(r, os.path.join(game, "gfx", "flags")) for r in j["flag_roots"]):
            wrong.append("%s does not read the game's flags: flag_roots is %s"
                         % (name, j["flag_roots"]))
        if "game_only_tech" not in j["technologies"]:
            wrong.append("%s does not inherit the game's technologies: %s"
                         % (name, j["technologies"]))
        if name == "GGG" and "BAV" not in j["country_order"]:
            wrong.append("GGG's own countries are not read: %s" % j["country_order"])
        inherited_culture = "game_culture" in j["culture_groups"]
        inherited_formation = "GER" in j["formations"]
        if replaced and (inherited_culture or inherited_formation):
            wrong.append("GGG replaces common and decisions, yet the game's %s read"
                         % " and ".join(w for w, on in (("cultures.txt was", inherited_culture),
                                                         ("formation was", inherited_formation))
                                        if on))
        if not replaced and not (inherited_culture and inherited_formation):
            wrong.append("Plain replaces nothing, yet the game's culture (%s) or formation (%s) "
                         "was not read" % (inherited_culture, inherited_formation))
    return wrong


def signature(path):
    run = subprocess.run([kit.SCANNER, "selftest-signature", path], capture_output=True, text=True)
    return run.stdout.strip()


def kept_copy_problems(game, ggg):
    """An edit to the .mod file's replace_path changes what is read, so the key."""
    descriptor = os.path.join(game, "mod", "GGG.mod")
    before = signature(ggg)
    write(descriptor, GGG_MOD.replace('replace_path = "decisions"\n', ""))
    after = signature(ggg)
    write(descriptor, GGG_MOD)
    if before == after:
        return ["dropping a replace_path from GGG.mod leaves the kept copy's key as it was, "
                "so a run would read GGG as it was read before"]
    return []


def main():
    kit.need_scanner()
    try:
        from vic2tools import report_tab
    except ImportError:
        kit.skip("needs tkinter, which the window's report tab is built with")
    with kit.holding("vic2modplaces") as (holding, env):
        game, plain, ggg = the_world(holding)
        parts = [
            ("the window", lambda: window_problems(report_tab, game, plain, ggg)
             + window_alone_problems(report_tab, holding)),
            ("the scanner", lambda: scanner_problems(game, plain, ggg, holding, env)),
            ("the mod reader", lambda: reader_problems(game, plain, ggg)),
            ("the kept copy", lambda: kept_copy_problems(game, ggg)),
        ]
        wrong = []
        for what, ask in parts:
            bad = ask()
            print("  %-20s %s" % (what, "ok" if not bad else "FAIL"))
            wrong += bad
    if wrong:
        print("\nPROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("\na mod one level down, behind its .mod file, is offered, settled and read "
          "like any other")
    return 0


if __name__ == "__main__":
    sys.exit(main())

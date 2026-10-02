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
What makes a folder a Victoria II install, and the one way a run is read on
one: `settle_game`, which the window asks before it starts a run so that a
wrong folder is a sentence there and then. The scanner reads the mod itself
(`scanner/src/engine/modread.rs`) and settles the game again the same way
(`scanner/src/front/`).
"""

import os


def is_install(path):
    """Whether a folder is a Victoria II install: it holds the game's map."""
    return bool(path) and os.path.isfile(os.path.join(path, "map", "default.map"))


def _same_folder(a, b):
    return (os.path.normcase(os.path.realpath(a))
            == os.path.normcase(os.path.realpath(b)))


def settle_game(mod_path, game_root):
    """
    (the folder to read as the mod, the install it runs on) for a run, or
    ValueError saying in a sentence what to do instead.

    A report is read on an installed Victoria II, and a mod is read where the
    game loads it from: `<install>/mod/<name>`. Every file a mod does not
    ship comes from the install beneath it -- the map, most of the flags,
    whatever rules and names it leaves alone -- so a mod anywhere else is
    missing all of that, and a report built from a stray copy says things the
    game would not. So there is exactly one way to run: name the install
    with `game_root`, and a mod inside its mod folder with `mod_path`, or no
    mod for the unmodded game. A mod inside an install names that install
    itself, and the install asked for as its own mod is vanilla.
    """
    game = None
    if game_root:
        game = os.path.abspath(os.path.expanduser(os.path.expandvars(game_root)))
        if not is_install(game):
            raise ValueError(
                f"{game_root} is not a Victoria II install: there is no "
                f"map/default.map in it. Point --game-root at the folder the "
                f"game is installed in, the one holding map/, gfx/ and mod/.")
    if not mod_path:
        if not game:
            raise ValueError(
                "Say where Victoria II is installed, with --game-root. The "
                "report is read on the game's own rules, or on a mod's when "
                "--mod-path names one inside the game's mod folder.")
        return game_root, game
    mod = os.path.abspath(os.path.expanduser(os.path.expandvars(mod_path)))
    home = mod if is_install(mod) else _base_game_path(mod)
    if not home:
        raise ValueError(
            f"{mod_path} is not in a Victoria II install's mod folder. Put the "
            f"mod -- its folder and its .mod file -- in the mod folder of the "
            f"game it runs on, where the game loads it from, and point "
            f"--mod-path at it there.")
    if game and not _same_folder(home, game):
        raise ValueError(
            f"{mod_path} is in the mod folder of {home}, not of {game_root}. "
            f"Point --game-root at the install the mod is in, or leave it out.")
    return mod_path, home


def _base_game_path(path):
    """
    The Victoria II install a mod sits inside, or None when there isn't one.

    Mods live at `<install>/mod/<name>`, so the install is two levels up.
    Confirmed by looking for files no mod folder holds on its own, rather
    than trusting the shape of the path.
    """
    if not path:
        return None
    root = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    if os.path.basename(os.path.dirname(os.path.abspath(path))).lower() != "mod":
        return None
    if not is_install(root):
        return None
    return root

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
What the windows remember between runs, and where a first run starts looking.

One file holds what the analyzer's window and its share menu remember: the
folders last used, the GitHub token, the report host. Each of them used to
read the whole file, change its own keys and write the whole file back, and
one of the five places that did so wrote only its own four keys -- so every
press of Analyze erased the token. `remember` merges, and is the only way in.
The keeper's half is a file of its own beside it.
"""

import json
import os


def _settings_path(app):
    """
    Where this machine keeps a program's settings.

    Windows has APPDATA and that is the end of it. Everywhere else, falling
    back to the home directory put the file at `~/<app>/settings.json`, which
    on this machine is the checkout itself -- a test run wrote its settings
    into the working tree and they were very nearly committed. The XDG
    directory is where settings belong on those systems anyway.
    """
    roaming = os.environ.get("APPDATA")
    if roaming:
        return os.path.join(roaming, app, "settings.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, app, "settings.json")


# The analyzer's window and its share menu.
ANALYZER = _settings_path("vic2saveanalyzer")
# The keeper's half: beside the analyzer's, since the two are one window.
KEEPER = os.path.join(os.path.dirname(ANALYZER), "keeper.json")
# Where the keeper kept its settings when it was a program of its own. Read
# only while there is nothing in the new place yet, so folders somebody
# picked before the two became one window are still there afterwards.
KEEPER_FORMERLY = os.path.join(
    os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"),
                                              ".config"),
    "vic2autosavekeeper", "settings.json")


def load(path=None, formerly=None):
    """
    What `path` holds -- the analyzer's file unless told otherwise -- or,
    when it holds nothing readable, what `formerly` holds. {} if neither.
    """
    for where in (path or ANALYZER, formerly):
        if not where:
            continue
        try:
            with open(where, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            continue
    return {}


def remember(path=None, **changes):
    """
    Write these keys into `path`, leaving every other key there as it was.
    A key given as None is forgotten.
    """
    path = path or ANALYZER
    held = load(path)
    for key, value in changes.items():
        if value is None:
            held.pop(key, None)
        else:
            held[key] = value
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(held, fh, indent=1)
    except Exception:
        pass                      # remembering is a convenience, not a duty


def documents():
    """
    The user's Documents folders, OneDrive's copy first.

    Windows moves Documents under OneDrive when that is switched on, and
    Victoria II follows it there, so both are worth looking at. Neither is
    guaranteed to exist; the caller checks.
    """
    home = os.path.expanduser("~")
    return [os.path.join(base, "Documents")
            for base in (os.environ.get("OneDrive"),
                         os.environ.get("OneDriveConsumer"), home)
            if base]


def game_folders():
    """Where Victoria II keeps its saves and the rest, in each Documents."""
    return [os.path.join(docs, "Paradox Interactive", "Victoria II")
            for docs in documents()]

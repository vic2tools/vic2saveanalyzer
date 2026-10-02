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
The two things a running analysis shares with whoever started it -- a Stop
button to ask between saves, a progress bar to tell -- and the folder the
scanner keeps what it has read in, which the window can measure and empty.
"""

import os
import tempfile


class Cancelled(Exception):
    """The caller asked for the run to stop before it finished."""


# A window has a Stop button; a terminal has Ctrl-C. Whoever is driving hands a
# callable in and it is asked, between saves, whether to carry on. Between
# saves rather than inside one because a save is a few seconds at worst and
# unwinding a half-read one buys nothing.
_STOP = None


def set_cancel_check(fn):
    """Give the analyzer something to ask before it starts the next save."""
    global _STOP
    _STOP = fn


def stop_if_asked():
    if _STOP is not None and _STOP():
        raise Cancelled()


_PROGRESS = None


def set_progress(fn):
    """
    Give the analyzer somewhere to say how far through the saves it is.

    Counted in saves rather than in bytes or in stages, because a save is the
    unit the work actually comes in and the one a reader can see going by. A
    campaign of a few dozen does not need this; one of seven hundred is four
    minutes of a window that otherwise looks stuck.
    """
    global _PROGRESS
    _PROGRESS = fn


def tell_progress(done, total):
    if _PROGRESS is not None:
        try:
            _PROGRESS(done, total)
        except Exception:             # a window that has gone away
            pass


def cache_dir():
    """Where parsed saves are remembered between runs."""
    return os.path.join(tempfile.gettempdir(), "vic2_analyzer_cache")


def cache_stats():
    """How many entries the cache holds and what they weigh, as (count, bytes).

    Nothing here evicts anything. A slot is keyed by the save, the mod, and a
    hash of the parser itself, so editing the parser does not replace the old
    entries -- it stands a fresh generation up beside them, and the previous one
    can never be read again. An install that has seen a few updates is therefore
    mostly holding generations it has no use for, which is the case for offering
    to empty it.
    """
    count = size = 0
    try:
        with os.scandir(cache_dir()) as entries:
            for entry in entries:
                if not entry.name.endswith(".pkl"):
                    continue
                try:
                    size += entry.stat().st_size
                except OSError:
                    continue          # vanished under us; it is not in the total
                count += 1
    except OSError:
        return 0, 0                   # no cache folder yet, which is not a fault
    return count, size


def clear_cache():
    """Empty the cache. Returns (entries removed, bytes freed).

    Only this program's own `.pkl` files go, and the folder itself stays: it
    sits in the system temp directory, which belongs to everybody, so taking
    the tree out wholesale is not this program's business. An entry another run
    still has open is skipped rather than fought over -- it will be caught by
    the next wipe.
    """
    removed = freed = 0
    folder = cache_dir()
    try:
        names = os.listdir(folder)
    except OSError:
        return 0, 0
    for name in names:
        if not name.endswith(".pkl"):
            continue
        path = os.path.join(folder, name)
        try:
            size = os.path.getsize(path)
            os.remove(path)
        except OSError:
            continue
        removed += 1
        freed += size
    return removed, freed

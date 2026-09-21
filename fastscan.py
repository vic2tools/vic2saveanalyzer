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
The province scan, handed to `scanner/` when that has been built.

Reading a save is almost entirely scanning text and converting numbers, and
the province blocks are most of the file: they are about fifty-five percent of
the parse and they hold every pop in the game. `scanner/src/main.rs` does that
one loop, and this hands saves to it and turns what comes back into the same
structures Python would have built.

Everything here is optional. If the binary has not been built -- no Rust
compiler on the machine that made the release, a platform nobody cross-compiled
for -- `available()` says so once and every save is read the way it always was.
A missing scanner costs speed and nothing else, which is the only reason it is
safe to have a second implementation of anything.
"""

import json
import os
import subprocess
import sys

BINARY = "vic2scan.exe" if sys.platform == "win32" else "vic2scan"
_FOUND = None


def _candidates():
    """Where the scanner might be, nearest first."""
    here = os.path.dirname(os.path.abspath(__file__))
    # Beside the executable when frozen, beside this file when not, and in
    # the crate's own target directory when working on it.
    yield os.path.join(getattr(sys, "_MEIPASS", here), BINARY)
    yield os.path.join(here, BINARY)
    yield os.path.join(here, "scanner", "target", "release", BINARY)


def available():
    """The scanner's path, or None. Looked for once."""
    global _FOUND
    if _FOUND is None:
        _FOUND = ""
        for path in _candidates():
            if os.path.isfile(path) and os.access(path, os.X_OK):
                _FOUND = path
                break
    return _FOUND or None


def start(path, pop_types, mob_types):
    """
    Set the scanner going and come straight back.

    Started before the file is read rather than after, so it works through
    the provinces while this process reads the same file and finds its
    blocks. On a machine with a core to spare that is the scanner for free;
    on one already using every core it changes nothing, which is why it is
    worth doing and not worth much.
    """
    binary = available()
    if binary is None:
        return None
    try:
        return subprocess.Popen(
            [binary, path,
             "--pop-types", ",".join(sorted(pop_types)),
             "--mob-types", ",".join(sorted(mob_types))],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return None


def collect(running, timeout=600):
    """
    What the scanner found, or None.

    None always means "read it in Python instead", never "give up": the
    binary is missing, or it refused the file -- a zip, a save some editor
    has reflowed -- or it failed in a way nobody has thought of yet.
    """
    if running is None:
        return None
    try:
        out, _err = running.communicate(timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        running.kill()
        return None
    if running.returncode != 0 or not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def scan(path, pop_types, mob_types, timeout=600):
    """Start the scanner and wait for it. Kept for callers that want both."""
    return collect(start(path, pop_types, mob_types), timeout=timeout)


def apply(got, nations, province_owner, pop_registry, world_sink,
          province_counts):
    """
    Fold a scan into the structures `analyze_save` is filling.

    The shapes here are the scanner's, chosen to be cheap to write and cheap
    to read back: pairs rather than objects, one shared table of pop type
    names rather than the name against every pop. Turning them into the
    dicts, sets and lists Python expects is the price of not parsing the
    file twice, and it is about a twentieth of what parsing it costs.
    """
    world_sink[0] += got["world_pop"]
    for pid, owner, held in got["owners"]:
        province_owner[pid] = (sys.intern(owner), sys.intern(held))
        province_counts[owner] += 1

    kinds = [sys.intern(k) for k in got["kind_names"]]
    ids, kind_of = got["pop_ids"], got["pop_kinds"]
    for i, pop_id in enumerate(ids):
        pop_registry[pop_id] = kinds[kind_of[i]]

    for tag, block in got["nations"].items():
        nat = nations[sys.intern(tag)]
        nat["provinces"] += block["provinces"]
        nat["ports"] += block["ports"]
        nat["total_pop"] += block["total_pop"]
        nat["life_unmet"] += block["life_unmet"]
        nat["starving"] += block["starving"]
        # Only when there is one, because that is what Python does: these two
        # start as int 0 and are left alone by a province with no naval base,
        # so a nation without one carries `0` and not `0.0`. The report never
        # notices; the CSV writes the number out and does.
        if block["naval_base_levels"]:
            nat["naval_base_levels"] += block["naval_base_levels"]
        if block["max_naval_base"] > nat["max_naval_base"]:
            nat["max_naval_base"] = block["max_naval_base"]
        nat["fort_levels"] += block["fort_levels"]
        nat["railroad_levels"] += block["railroad_levels"]
        nat["literacy_weighted"] += block["literacy_weighted"]
        nat["con_weighted"] += block["con_weighted"]
        nat["mil_weighted"] += block["mil_weighted"]
        nat["money_total"] += block["money_total"]

        nat["core_provinces"].update(block["cores"])
        nat["occupied_provinces"].update(block["occupied"])
        for pid, flag in block["colonial"]:
            nat["province_colonial"][pid] = flag

        # Pairs, in the order the file first mentioned each name, because a
        # stable sort downstream breaks ties on it.
        by_type = nat["pop_by_type"]
        for kind, size in block["pop_by_type"]:
            by_type[sys.intern(kind)] += size
        by_culture = nat["pop_by_culture"]
        for culture, size in block["pop_by_culture"]:
            by_culture[sys.intern(culture)] += size

        pop_at = nat["pop_at"]
        for pid, size in block["pop_at"]:
            pop_at[pid] += size
        soldiers_at = nat["soldiers_at"]
        for pid, size in block["soldiers_at"]:
            soldiers_at[pid] += size
        literacy_at = nat["literacy_at"]
        for pid, value in block["literacy_at"]:
            literacy_at[pid] += value
        soldier_pops_at = nat["soldier_pops_at"]
        for pid, sizes in block["soldier_pops_at"]:
            soldier_pops_at[pid].extend(sizes)

        pool = nat["mobilizable_pops"]
        for kind, culture, size, pid in block["mobilizable"]:
            pool.append((sys.intern(kind), sys.intern(culture), size, pid))

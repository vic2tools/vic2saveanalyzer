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
The campaigns in a folder: every folder at or under it that holds saves.

The window asks this to tell one campaign's saves from a folder of several,
before it decides whether a run is `--cross`. `--cross` itself -- matching
each campaign to its mod, reading them all and comparing them -- is the
scanner's (`scanner/src/front/cross.rs`), which finds the folders the same
way.
"""

import os
from collections import Counter


def campaigns_in(parent, depth=6):
    """
    Every folder at or under `parent` that holds saves, as (name, path, files).

    The whole tree, not just the children: campaigns get grouped into folders of
    their own -- the two Divergences games sitting together under `dodgames` --
    and scanning one level deep would walk straight past them and report the
    parent as holding two campaigns when it holds four.

    The parent itself counts, so pointing this at a single campaign behaves the
    way the single-campaign path always did. A campaign is named by its own
    folder, or by the path down to it when two folders share a name.
    """
    found = []
    parent = os.path.normpath(parent)
    for root, dirs, files in os.walk(parent):
        rel = os.path.relpath(root, parent)
        if rel != "." and rel.count(os.sep) >= depth - 1:
            dirs[:] = []                  # deep enough; a save tree is not this deep
        dirs.sort()
        saves = sorted(f for f in files if f.lower().endswith(".v2"))
        if saves:
            found.append([os.path.basename(root) or root, rel, root,
                          [os.path.join(root, f) for f in saves]])
    seen = Counter(entry[0] for entry in found)
    out = []
    for leaf, rel, root, files in found:
        name = leaf if seen[leaf] == 1 or rel == "." else rel.replace(os.sep, "/")
        out.append((name, root, files))
    return out

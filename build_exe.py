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
Packs the analyzer into dist/vic2saveanalyzer.exe.

    python build_exe.py

Everything the report needs is already Python -- there is no image library, no
plotting library and no data files to carry -- so the bundle is the standard
library, tkinter and these seven modules. The icon is drawn here rather than
shipped, which keeps the repository free of binaries.
"""

import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "vic2.ico")
NAME = "vic2saveanalyzer"

# The report's own palette, so the icon and the window agree.
GROUND = (0x4A, 0x1C, 0x28)
GOLD = (0xB0, 0x8D, 0x3F)
BRASS = (0xE7, 0xC4, 0x64)


def _draw(size):
    """One square of the icon: a gold-edged burgundy field over three bars."""
    edge = max(1, size // 16)
    pixels = [[GROUND] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            if x < edge or y < edge or x >= size - edge or y >= size - edge:
                pixels[y][x] = GOLD

    inner = size - 2 * edge
    if inner >= 6:
        # Three rising bars. Reading a campaign is watching numbers climb, and
        # at 16 pixels a bar chart is one of the few marks still legible.
        gap = max(1, inner // 12)
        bar = max(1, (inner - 4 * gap) // 3)
        base = size - edge - max(1, inner // 8)
        left = edge + (inner - (3 * bar + 2 * gap)) // 2
        for i, share in enumerate((0.34, 0.58, 0.82)):
            x0 = left + i * (bar + gap)
            top = base - int(inner * share)
            for y in range(max(edge, top), base):
                for x in range(x0, min(x0 + bar, size - edge)):
                    pixels[y][x] = BRASS if i == 2 else GOLD
    return pixels


def _image(size):
    """A single ICO entry, in the BMP form every Windows shell understands."""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         size * size * 4, 0, 0, 0, 0)
    pixels = _draw(size)
    # ICO stores its rows bottom-up, and its colours as blue, green, red, alpha.
    colour = b"".join(
        bytes([b, g, r, 255])
        for row in reversed(pixels) for (r, g, b) in row)
    # The AND mask is obsolete but still required: zeroed, meaning fully opaque.
    stride = ((size + 31) // 32) * 4
    return header + colour + b"\x00" * (stride * size)


def write_icon(path=ICON):
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [_image(s) for s in sizes]
    offset = 6 + 16 * len(sizes)
    out = [struct.pack("<HHH", 0, 1, len(sizes))]
    for size, blob in zip(sizes, images):
        out.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                               1, 32, len(blob), offset))
        offset += len(blob)
    out.extend(images)
    with open(path, "wb") as fh:
        fh.write(b"".join(out))
    return path


def build():
    write_icon()
    # These are imported inside functions rather than at the top of the file, so
    # they are named here in case the bundler's scan ever stops following them.
    carried = ["vic2_analyzer", "v2parse", "mod_reader", "report", "template",
               "tech_groups",
               # saves are read on several cores, and the machinery for that is
               # reached through function-level imports
               "multiprocessing", "multiprocessing.spawn",
               "concurrent.futures.process"]
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--windowed", "--name", NAME, "--icon", ICON,
           "--distpath", os.path.join(HERE, "dist"),
           "--workpath", os.path.join(HERE, "build"),
           "--specpath", os.path.join(HERE, "build")]
    for module in carried:
        cmd += ["--hidden-import", module]
    for junk in ("numpy", "pandas", "matplotlib", "PIL", "scipy", "setuptools",
                 "pip", "pytest", "test"):
        cmd += ["--exclude-module", junk]
    cmd.append(os.path.join(HERE, "gui.py"))
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)


if __name__ == "__main__":
    sys.exit(build())

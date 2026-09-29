#!/usr/bin/env python3
"""
The province bitmap as the map tab ships it, against a pixel-by-pixel
reading of the same file.

`province_raster` reads a row's pixels in bulk and looks up only runs, so
what it can get wrong is at the edges of a run: a colour the map does not
name, two colours naming one province, a run that carries on into the next
row, the padding at the end of a row, and which pixels a scale samples. The
bitmap here is small and made of exactly those.

And `raster_ahead`, which decodes it in another process while the saves are
read: it has to leave the entry `province_raster` then finds, and start
nothing when there is no map or the entry is already there.

And the two other things the map takes from the map's files alone: the
anchor for a province `positions.txt` does not place, worked out a stretch
of a row at a time, and `positions.txt` itself, which is cached and has to
be read again when it changes.
"""

import atexit
from itertools import groupby
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cacheio
import mod_reader

# (red, green, blue) -> province; 9 and 10 share province 5.
NAMED = {(10, 20, 30): 1, (200, 0, 0): 2, (0, 200, 0): 3, (0, 0, 200): 4,
         (9, 9, 9): 5, (10, 10, 10): 5}
UNNAMED = (1, 2, 3)


def picture(width, height):
    """Rows of (r, g, b), top first, with runs of every awkward kind."""
    colours = list(NAMED) + [UNNAMED]
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            if y % 3 == 0:
                # long runs that end on a row's last pixel, so the next row
                # starting with the same colour continues the run
                c = colours[(x // 5 + y) % 3]
            elif y % 3 == 1:
                # the two colours of province 5 side by side, and the unnamed
                c = [(9, 9, 9), (10, 10, 10), UNNAMED, (0, 0, 200)][x % 4]
            else:
                c = colours[(x * 7 + y) % len(colours)]
            row.append(c)
        rows.append(row)
    return rows


def write_map(folder, rows):
    """map/provinces.bmp (24-bit, rows stored top first) and definition.csv."""
    width, height = len(rows[0]), len(rows)
    stride = ((width * 24 + 31) // 32) * 4
    body = b"".join(
        b"".join(bytes((b, g, r)) for r, g, b in row).ljust(stride, b"\xee")
        for row in rows)
    head = struct.pack("<2sIHHI", b"BM", 54 + len(body), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                       len(body), 0, 0, 0, 0)
    (folder / "map").mkdir(parents=True, exist_ok=True)
    (folder / "map/provinces.bmp").write_bytes(head + info + body)
    lines = ["province;red;green;blue;x;x"]
    lines += [f"{pid};{r};{g};{b};P{pid};x"
              for (r, g, b), pid in NAMED.items()]
    (folder / "map/definition.csv").write_text("\n".join(lines) + "\n")


def by_hand(rows, scale):
    """The raster read one sampled pixel at a time."""
    out_w, out_h = len(rows[0]) // scale, len(rows) // scale
    cells = [NAMED.get(rows[y * scale][x * scale], 0)
             for y in range(out_h) for x in range(out_w)]
    runs = []
    for pid in cells:
        if runs and runs[-1][0] == pid:
            runs[-1][1] += 1
        else:
            runs.append([pid, 1])
    return out_w, out_h, [tuple(r) for r in runs]


def spelled(runs):
    """Runs as the page's decoder reads them: base 36, `id` for a run of
    one, `id.count` otherwise, a space between."""
    def b36(n):
        digits = ""
        while n:
            n, d = divmod(n, 36)
            digits = "0123456789abcdefghijklmnopqrstuvwxyz"[d] + digits
        return digits or "0"
    return " ".join(b36(p) if c == 1 else b36(p) + "." + b36(c) for p, c in runs)


def anchors_by_hand(width, runs, wanted):
    """`province_anchors` a cell at a time: the mean of a province's cells,
    then its first cell nearest that mean."""
    cells, at = {}, 0
    for pid, count in runs:
        for i in range(at, at + count):
            cells.setdefault(pid, []).append((i % width, i // width))
        at += count
    out = {}
    for pid in wanted & set(cells):
        own = cells[pid]
        cx = sum(x for x, _ in own) / len(own)
        cy = sum(y for _, y in own) / len(own)
        x, y = min(own, key=lambda c: ((c[0] - cx) ** 2 + (c[1] - cy) ** 2,
                                       c[1], c[0]))
        out[pid] = [round(x + 0.5, 1), round(y + 0.5, 1)]
    return out


class RasterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vic2raster")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"

    def test_every_scale_matches_a_pixel_by_pixel_reading(self):
        # 23 wide leaves padding on every row; 19 high is not a multiple of
        # any scale above 1, so the last rows are never sampled.
        rows = picture(23, 19)
        write_map(self.game, rows)
        for scale in (1, 2, 3, 5):
            with self.subTest(scale=scale):
                want = by_hand(rows, scale)
                self.assertEqual(mod_reader.province_raster(str(self.game), scale),
                                 want)
                # and again, out of the cache entry the first call left
                self.assertEqual(mod_reader.province_raster(str(self.game), scale),
                                 want)

    def test_the_process_ahead_leaves_the_entry_behind(self):
        rows = picture(23, 19)
        write_map(self.game, rows)
        proc = mod_reader.raster_ahead(str(self.game), 1)
        self.assertIsNotNone(proc)
        proc.join(60)
        self.assertEqual(proc.exitcode, 0)
        slot = mod_reader._raster_slot(str(self.game / "map/provinces.bmp"),
                                       str(self.game / "map/definition.csv"), 1)
        self.assertEqual(cacheio.load(slot), by_hand(rows, 1))
        self.assertEqual(cacheio.load(mod_reader._text_slot(slot)),
                         spelled(by_hand(rows, 1)[2]))
        # cached now, so there is nothing to start
        self.assertIsNone(mod_reader.raster_ahead(str(self.game), 1))

    def test_the_runs_are_spelled_as_the_page_reads_them(self):
        rows = picture(23, 19)
        write_map(self.game, rows)
        for scale in (1, 3):
            with self.subTest(scale=scale):
                want = spelled(by_hand(rows, scale)[2])
                self.assertEqual(mod_reader.raster_text(str(self.game), scale), want)
                # and again, out of its cache entry
                self.assertEqual(mod_reader.raster_text(str(self.game), scale), want)
        self.assertEqual(mod_reader.raster_text(str(self.root / "nomap"), 1), "")

    def test_anchors_match_a_cell_by_cell_reading(self):
        # A crescent round a bay, a ring whose middle is not its own, a
        # province split across the wrap of a row, and a tie between two
        # columns equally near the middle.
        width = 7
        grid = ("1111111"
                "1000001"
                "1022201"
                "1020201"
                "1022200"
                "3300000"
                "0004400"
                "0000003"
                "3000000")
        runs = [(int(c), sum(1 for _ in g)) for c, g in groupby(grid)]
        for wanted in ({1}, {2}, {3}, {4}, {0, 1, 2, 3, 4}, {9}):
            with self.subTest(wanted=wanted):
                self.assertEqual(mod_reader.province_anchors(width, runs, wanted),
                                 anchors_by_hand(width, runs, wanted))

    def test_positions_are_read_again_when_the_file_changes(self):
        write_map(self.game, picture(4, 4))
        positions = self.game / "map/positions.txt"
        positions.write_text("1 = { unit = { x = 10.000 y = 20.000 } }\n")
        self.assertEqual(mod_reader.unit_positions(str(self.game)),
                         {1: (10.0, 20.0)})
        positions.write_text("1 = { unit = { x = 30.000 y = 40.000 } }\n"
                             "2 = { town = { x = 5.000 y = 6.000 } }\n")
        self.assertEqual(mod_reader.unit_positions(str(self.game)),
                         {1: (30.0, 40.0), 2: (5.0, 6.0)})

    def test_nothing_is_started_without_a_map(self):
        self.game.mkdir()
        self.assertIsNone(mod_reader.raster_ahead(str(self.game), 1))


if __name__ == "__main__":
    # The cache goes where the temp folder is, and the process `raster_ahead`
    # starts is made by a forkserver that knows only the environment -- so
    # the folder is set there, before anything starts one. Here and not at
    # the top, because the forkserver imports this file again. Removed at
    # exit, and registered before multiprocessing registers its own clean-up
    # inside it, so that it goes last.
    cache = tempfile.mkdtemp(prefix="vic2rastercache")
    atexit.register(shutil.rmtree, cache, ignore_errors=True)
    os.environ["TMPDIR"] = cache
    tempfile.tempdir = None
    unittest.main()

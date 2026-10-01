"""
The province bitmap as the map tab ships it, against a pixel-by-pixel
reading of the same file.

The map is read a row's pixels at a time and kept as runs, so what it can get
wrong is at the edges of a run: a colour the map does not name, two colours
naming one province, a run that carries on into the next row, the padding at
the end of a row, and which pixels a scale samples. The bitmap here is small
and made of exactly those. And the anchor an army is drawn at: where
`positions.txt` places a province (its y measured from the bottom, as the
bitmap is), and otherwise the province's first cell nearest the middle of
its own cells, worked out here a cell at a time.

    python3 testkit/raster.py

A real run of the analyzer at four scales; what is compared is the `map`
the page carries.
"""

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "testkit"))
import expected                                             # noqa: E402
import matching                                             # noqa: E402
import savefmt                                              # noqa: E402

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


POSITIONS = {1: (10.0, 12.0), 2: (5.5, 6.0)}


def a_world(holding, width, height):
    """(the mod, a folder with one save whose armies stand in every province)."""
    mod = matching.a_mod_in_a_game(str(holding), "Mapped")
    rows = picture(width, height)
    write_map(Path(mod), rows)
    with open(os.path.join(mod, "map", "positions.txt"), "w") as fh:
        # one by `unit`, one by `town` alone, and one that gives no anchor
        fh.write("1 = { unit = { x = 10.000 y = 12.000 } }\n"
                 "2 = { town = { x = 5.500 y = 6.000 } }\n"
                 "3 = { rotation = 1 }\n")
    saves = holding / "saves"
    saves.mkdir()
    army = lambda where: ("army", ['\t\tname="Army %d"' % where]
                          + savefmt.nest("regiment", ['\t\t\tname="B"', "\t\t\ttype=infantry",
                                                     "\t\t\tcount=1000", "\t\t\tstrength=3.000"], 2)
                          + ["\t\tlocation=%d" % where])
    savefmt.write(str(saves / "a.v2"), savefmt.head("1880.1.1"),
                  *[savefmt.province(pid, "ENG", [savefmt.pop("farmers", pid, 1000)])
                    for pid in range(1, 6)],
                  savefmt.country("ENG", blocks=[army(pid) for pid in range(1, 6)]))
    return mod, str(saves), rows


def shipped(saves, mod, scale, holding):
    """The map a run's page carries at `scale`."""
    out = holding / ("out%d" % scale)
    env = dict(os.environ, TMPDIR=str(holding / "tmp"))
    for key in ("VIC2_NO_ENGINE", "VIC2_NO_FRONT"):
        env.pop(key, None)
    (holding / "tmp").mkdir(exist_ok=True)
    done = subprocess.run([sys.executable, str(HERE / "vic2_analyzer.py"), saves, "--mod-path",
                           mod, "--out", str(out), "--map-scale", str(scale), "-q", "--no-cache"],
                          capture_output=True, text=True, env=env)
    if done.returncode:
        raise AssertionError("the run failed: %s" % (done.stdout + done.stderr)[-1500:])
    return json.loads(expected.page(str(out))[0])["map"]


def main():
    holding = Path(tempfile.mkdtemp(prefix="vic2raster"))
    wrong = []
    try:
        # 23 wide leaves padding on every row; 19 high is not a multiple of
        # any scale above 1, so the last rows are never sampled.
        mod, saves, rows = a_world(holding, 23, 19)
        for scale in (1, 2, 3, 5):
            got = shipped(saves, mod, scale, holding)
            width, height, runs = by_hand(rows, scale)
            said = []
            if (got["w"], got["h"], got["scale"]) != (width, height, scale):
                said.append("the map is %sx%s at %s, not %dx%d" % (got["w"], got["h"],
                                                                    got["scale"], width, height))
            text = got["runs"]
            if text.startswith('"'):
                text = json.loads(text)
            if text != spelled(runs):
                said.append("the runs differ:\n    shipped   %s\n    by hand   %s"
                            % (text[:300], spelled(runs)[:300]))
            full = height * scale
            want = {str(pid): [round(x / scale, 1), round((full - y) / scale, 1)]
                    for pid, (x, y) in POSITIONS.items()}
            derived = anchors_by_hand(width, runs, {3, 4, 5})
            want.update({str(p): v for p, v in derived.items()})
            if got["spots"] != want:
                said.append("the anchors are %s, not %s" % (got["spots"], want))
            # A province no sampled cell falls in has no anchor at all.
            if got["derived"] != len(derived):
                said.append("%s provinces were said to be anchored by their shape, not %d"
                            % (got["derived"], len(derived)))
            print("  scale %d  %s" % (scale, "ok" if not said else "DIFFERS"))
            for line in said:
                print("      " + line)
            wrong += said
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print()
    print("the map holds" if not wrong else "the map DIFFERS")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())

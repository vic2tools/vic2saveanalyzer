"""Lossless state snapshots, compacted and compressed where saves are finished.

Each snapshot owns its name and composition-layout tables. It can be decoded
on its own: worker ordering, retries, duplicate dates and a serial fallback
cannot leave it referring to a missing earlier result. The browser restores
the existing populationStates shape before any report view uses it.
"""

import base64
import gzip
import json


class Snapshot:
    def __init__(self):
        self.words = {}
        self.layouts = {}
        self.nations = {}

    def word(self, value):
        return self.words.setdefault(value, len(self.words))

    def add(self, tag, aggregates, regions, accepted):
        rows = []
        self.nations[tag] = rows
        for pid, (size, literate, types, cultures, provinces) in aggregates.items():
            region = str(regions.get(pid) or ("province:" + str(pid)))
            layout = (tuple(self.word(t) for t in types),
                      tuple(2 * self.word(c) + (c in accepted) for c in cultures))
            index = self.layouts.setdefault(layout, len(self.layouts))
            rows.append([self.word(region), size,
                         round(literate / size, 6) if size else None,
                         provinces, index, list(types.values()) + list(cultures.values())])

    def pack(self):
        raw = json.dumps([list(self.words), list(self.layouts), self.nations],
                         separators=(",", ":"))
        # Same name escaping as report.pack_bytes: the inner JSON bypasses it.
        raw = raw.replace("<", "\\u2039").replace(">", "\\u203a")
        return base64.b64encode(gzip.compress(raw.encode(), 6, mtime=0)).decode("ascii")


def unpack(chunk):
    """Restore a snapshot, also used to check Python/browser wire parity."""
    words, layouts, nations = json.loads(gzip.decompress(base64.b64decode(chunk)))
    restored = {}
    for tag, rows in nations.items():
        states = restored[tag] = {}
        for region, size, literacy, provinces, layout, counts in rows:
            types, cultures = layouts[layout]
            n = len(types)
            states[words[region]] = [size, literacy,
                {words[t]: count for t, count in zip(types, counts)},
                [[words[c // 2], count, bool(c % 2)]
                 for c, count in zip(cultures, counts[n:])], provinces]
    return restored


def expand_map(data):
    """Expand the wire representation for offline report comparisons."""
    if data and "populationStateChunks" in data:
        states = data.setdefault("populationStates", {})
        for date, chunk in data.pop("populationStateChunks"):
            states[date] = unpack(chunk)
    return data

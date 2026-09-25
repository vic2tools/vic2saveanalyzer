#!/usr/bin/env python3
"""
Fold a campaign's wars the way the report does and the plain way, and
require the same war book from both.

A worker sends each war packed on its own, and the parent skips a record
whose bytes are exactly those of the last record folded under the same war
(`wars.fold_packed_wars`). That is right only while folding a record a
second time changes nothing -- while every merge in `fold_wars` is an
earliest, a latest, a union or a replacement by an equal value. A change to
`fold_wars` that is not -- a count, a list that grows, a date that moves the
other way -- makes the skip wrong without making anything crash, and the
report would hold a different war book from the one the saves give.

    python3 testkit/warfold.py "/path/to/saves" [how many]

Reads that many saves (ten by default), oldest first, and folds their wars
both ways. Fails too if either way went unused -- nothing skipped, or
nothing folded -- because then the comparison compared nothing.
"""

import glob
import os
import pickle
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import readsave                                              # noqa: E402
from dates import date_key                                   # noqa: E402
from wars import fold_packed_wars, fold_wars, pack_wars     # noqa: E402


def wars_in_order(paths):
    """Each save's war list, oldest save first."""
    read = []
    for path in paths:
        meta, _nations = readsave.analyze_save(path, readsave.PLAIN, verbose=False)
        read.append((date_key(meta["date"]), meta["wars"]))
    read.sort(key=lambda got: got[0])
    return [wars for _key, wars in read]


def fold_both_ways(campaign):
    """(the plain book, the packed book, records skipped, records in all)."""
    plain = {"wars": {}, "order": []}
    packed = {"wars": {}, "order": []}
    skipped = total = 0
    for wars in campaign:
        # Each book its own copy: a fold keeps the records it is handed.
        fold_wars(plain, pickle.loads(pickle.dumps(wars)))
        packs = pack_wars(wars)
        last = packed.get("last_folded", {})
        skipped += sum(1 for name, blob in packs if last.get(name) == blob)
        total += len(packs)
        fold_packed_wars(packed, packs)
    return plain, packed, skipped, total


def differences(plain, packed):
    """[what differs] between the two books."""
    wrong = []
    if plain["order"] != packed["order"]:
        wrong.append("the wars come out in a different order, or a "
                     "different number of them: %d against %d"
                     % (len(plain["order"]), len(packed["order"])))
    for key in plain["order"]:
        a, b = plain["wars"].get(key), packed["wars"].get(key)
        if a != b:
            fields = sorted(k for k in set(a or {}) | set(b or {})
                            if (a or {}).get(k) != (b or {}).get(k))
            wrong.append("%s differs in %s" % (" / ".join(map(str, key)),
                                                ", ".join(fields)))
    return wrong


def main():
    where = sys.argv[1] if len(sys.argv) > 1 else "."
    many = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    paths = sorted(glob.glob(os.path.join(where, "*.v2")))[:many]
    if len(paths) < 2:
        print("no campaign of two saves or more in %s, so nothing to fold"
              % where)
        return 0
    plain, packed, skipped, total = fold_both_ways(wars_in_order(paths))
    wrong = differences(plain, packed)
    if not skipped:
        wrong.append("no record was skipped, so the skip went untested")
    if skipped == total:
        wrong.append("every record was skipped, so folding went untested")
    print("%d saves, %d war records: %d skipped as repeats, %d folded"
          % (len(paths), total, skipped, total - skipped))
    if wrong:
        print("\nPROBLEMS:")
        for line in wrong[:12]:
            print("  " + line)
        return 1
    print("the war book is the same folded either way")
    return 0


if __name__ == "__main__":
    sys.exit(main())

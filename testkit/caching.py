#!/usr/bin/env python3
"""
What the engine keeps between runs must never change what a run says.

The report engine keeps every save it has read, the campaign's invention
records and the mod it read, in the temp folder (`vic2_analyzer_cache`), so
that a second run reads nothing it has read before. Each case here makes a
run read out of that cache after something has changed under it, and holds
it to a run made with `--no-cache` on the same saves: every table and what
the page carries must be the same.

- a save rewritten to the same size within the same second;
- every entry in the cache damaged, and then cut in half;
- the mobilizable pop types changed between two cached runs, which changes
  what a save is read for;
- a save's file replaced by another of the same name;
- one save read at a time against several at once.

    python3 testkit/caching.py
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "testkit"))

import expected                                            # noqa: E402
import matching                                            # noqa: E402
import savefmt                                             # noqa: E402


def write_save(path, date, invention, craftsmen=2000):
    return savefmt.write(
        path, savefmt.head(date),
        savefmt.province(1, "ENG", [savefmt.pop("farmers", 1, 1000),
                                    savefmt.pop("craftsmen", 2, craftsmen)]),
        savefmt.province(2, "FRA", [savefmt.pop("farmers", 3, 1500, culture="french")]),
        savefmt.country("ENG", techs=["flintlock_rifles"], inventions=[invention]),
        savefmt.country("FRA", culture="french", capital=2, techs=["flintlock_rifles"],
                        inventions=[1]))


class World:
    def __init__(self, holding):
        self.holding = holding
        self.game = matching.a_vanilla(os.path.join(holding, "Victoria 2"))
        self.saves = os.path.join(holding, "saves")
        os.makedirs(self.saves)
        for i in range(3):
            write_save(os.path.join(self.saves, "%d.v2" % i), "1880.%d.1" % (i + 1), 1)
        self.tmp = os.path.join(holding, "tmp")
        os.makedirs(self.tmp)

    def run(self, *extra, cached=True):
        """The tables and the page of one run (what it printed aside)."""
        out = os.path.join(self.holding, "out")
        env = dict(os.environ, TMPDIR=self.tmp, TEMP=self.tmp, TMP=self.tmp)
        for key in ("VIC2_NO_ENGINE", "VIC2_NO_FRONT"):
            env.pop(key, None)
        got = expected.run([self.saves, "--out", out, "--game-root", self.game, "--rebuild",
                            "-q"] + list(extra) + ([] if cached else ["--no-cache"]),
                           self.holding, env, out, [(self.tmp, "TMP"), (self.holding, "HOLDING")])
        shutil.rmtree(out, ignore_errors=True)
        if got["status.txt"] != "0\n":
            raise AssertionError("the run failed: %s" % (got["stdout.txt"] + got["stderr.txt"])[-1500:])
        return {k: v for k, v in got.items() if k not in ("stdout.txt", "stderr.txt")}

    def entries(self):
        top = os.path.join(self.tmp, "vic2_analyzer_cache")
        return [os.path.join(top, n) for n in sorted(os.listdir(top))] if os.path.isdir(top) else []


def same(name, cached, fresh):
    found = expected.differences(fresh, cached)
    expected.report(name, found, 52)
    return ["%s: %s" % (name, f) for f in found]


def main():
    holding = tempfile.mkdtemp(prefix="vic2caching")
    wrong = []
    try:
        w = World(holding)
        w.run()
        wrong += same("a warm run against a fresh one", w.run(), w.run(cached=False))
        if not w.entries():
            wrong.append("the first run kept nothing, so nothing here was read from a cache")

        path = os.path.join(w.saves, "0.v2")
        os.utime(path, ns=(1700000000100000000, 1700000000100000000))
        w.run()
        size = os.path.getsize(path)
        write_save(path, "1880.1.1", 2)
        os.utime(path, ns=(1700000000200000000, 1700000000200000000))
        if os.path.getsize(path) != size:
            wrong.append("the edit was meant to keep the save's size")
        wrong += same("a save rewritten, same size, same second", w.run(), w.run(cached=False))

        for entry in w.entries():
            with open(entry, "wb") as fh:
                fh.write(b"broken cache")
        wrong += same("every cache entry damaged", w.run(), w.run(cached=False))
        w.run()
        for entry in w.entries():
            with open(entry, "rb") as fh:
                data = fh.read()
            with open(entry, "wb") as fh:
                fh.write(data[:len(data) // 2])
        wrong += same("every cache entry cut in half", w.run(), w.run(cached=False))

        w.run("--mob-types", "farmers")
        crafts = w.run("--mob-types", "craftsmen")
        wrong += same("the mobilizable types changed between runs", crafts,
                      w.run("--mob-types", "craftsmen", cached=False))
        if crafts == w.run("--mob-types", "farmers"):
            wrong.append("farmers and craftsmen gave the same tables: the case tests nothing")

        moved = os.path.join(holding, "elsewhere.v2")
        write_save(moved, "1880.2.1", 2, craftsmen=4321)
        w.run()
        os.replace(moved, os.path.join(w.saves, "1.v2"))
        wrong += same("a save replaced by another of the same name", w.run(), w.run(cached=False))

        wrong += same("one at a time against several at once", w.run("-j", "1", cached=False),
                      w.run("-j", "3", cached=False))
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    print()
    if wrong:
        print("%d case(s) read something stale" % len(wrong))
        return 1
    print("what the engine keeps never changed what a run says")
    return 0


if __name__ == "__main__":
    sys.exit(main())

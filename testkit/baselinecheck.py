#!/usr/bin/env python3
"""
The baseline mechanism on a campaign made up here: record one, hold a run
to it, and say plainly when the campaign it was recorded from has changed.

    python3 testkit/baselinecheck.py

`baseline.py` is how an engine change is checked against a real campaign;
this checks `baseline.py` itself, on two of its runs, with no real saves.
"""
import contextlib
import io
import json
import os
import shutil
import sys

import kit
import baseline
import fixtures
import savefmt

RUNS = ("as it comes", "verbose")
NATIONS = {"explain": "ENG", "pool": "ENG", "inventions": "FRA"}


def a_campaign(holding):
    """(a folder of six saves, a mod in a game)."""
    mod = fixtures.a_mod_in_a_game(holding, "Mod", pops=fixtures.POPS, pop_per_regiment=1000,
                                   mob_size=0.5)
    folder = os.path.join(holding, "campaign")
    os.makedirs(folder)
    for i in range(6):
        fixtures.edge_save(os.path.join(folder, "ENG18%02d_01_01.v2" % (40 + i)),
                           "18%02d.1.1" % (40 + i), tags=("ENG", "FRA"),
                           techs=fixtures.TECHS[:2], inventions=[1],
                           wars=savefmt.war("The Test War", "ENG", "FRA", active=i < 4))
    return folder, mod


def quietly(fn, *args, **kw):
    with contextlib.redirect_stdout(io.StringIO()) as said:
        code = fn(*args, **kw)
    return code, said.getvalue()


def main():
    kit.need_scanner()
    wrong = []
    with kit.holding("vic2base") as (holding, _env):
        campaign, mod = a_campaign(holding)
        into = os.path.join(holding, "baseline")

        def expect(what, want_code, got, words=()):
            code, said = got
            if code != want_code or any(w not in said for w in words):
                wrong.append("%s: exit %s (wanted %s)%s\n%s"
                             % (what, code, want_code,
                                "" if not words else ", wanted the words %s" % (words,),
                                "\n".join("      " + l for l in said.strip().splitlines()[-8:])))
            print("  %-48s %s" % (what, "ok" if not wrong or not wrong[-1].startswith(what)
                                  else "WRONG"))

        expect("recorded", 0, quietly(baseline.record, campaign, mod, into, count=4,
                                      nations=NATIONS, runs=RUNS))
        with open(os.path.join(into, "manifest.json"), encoding="utf-8") as fh:
            kept = json.load(fh)
        if len(kept["saves"]) != 5:
            wrong.append("the manifest names %d saves, not four spaced plus the last"
                         % len(kept["saves"]))
        expect("held to its record", 0, quietly(baseline.compare, campaign, mod, into))

        fixtures.edge_save(os.path.join(campaign, "ENG1846_01_01.v2"), "1846.1.1",
                           tags=("ENG", "FRA"))
        expect("a save added since does not matter", 0,
               quietly(baseline.compare, campaign, mod, into))

        first = kept["saves"][0][0]
        shutil.copy(os.path.join(campaign, kept["saves"][1][0]), os.path.join(campaign, first))
        expect("a save changed under its name is not compared", kit.SKIPPED,
               quietly(baseline.compare, campaign, mod, into), (first, "content changed"))

        os.remove(os.path.join(campaign, first))
        expect("a save missing is not compared", kit.SKIPPED,
               quietly(baseline.compare, campaign, mod, into), (first, "missing"))

        campaign2, _mod = a_campaign(os.path.join(holding, "again"))
        status = os.path.join(into, "baseline", baseline.slug("as it comes"), "status.txt")
        with open(status, "w") as fh:
            fh.write("3\n")
        expect("a run that differs from its record fails", 1,
               quietly(baseline.compare, campaign2, mod, into), ("status.txt",))

        saved = os.environ.pop("VIC2_BASELINE", None)
        try:
            expect("no baseline at all says how to record one", kit.SKIPPED,
                   quietly(baseline.compare, campaign, mod, ""), ("baseline.py record",))
        finally:
            if saved is not None:
                os.environ["VIC2_BASELINE"] = saved
    print()
    if wrong:
        print("\n".join(wrong))
        return 1
    print("a baseline records, holds, and refuses a campaign that changed under it")
    return 0


if __name__ == "__main__":
    sys.exit(main())

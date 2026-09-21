#!/usr/bin/env python3
"""
Hold the two halves of the `facts` split to being inverses.

`facts` and `series` carry the same numbers in two orientations, and the
report used to ship both whole -- two megabytes of an eleven megabyte
payload. Only what `series` cannot supply travels now, and the page puts the
rest back at boot.

That means the report shows numbers that are not in the file it came in, and
the loop that reconstructs them lives in the template while the pair it has
to agree with lives in report.py. This checks the pair:

    rebuild_facts(*thin_facts(facts, series), series) == facts

against a built report if one is given, and against made-up shapes either
way -- a nation that appears late, a measure only one nation has, a date
with a single nation in it.

    python3 testkit/facts.py [path/to/report.html]

The template's own loop is checked by `boots.py`, which opens the page in a
browser: if the two drift, every table on it is empty or wrong.
"""

import base64
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from report import rebuild_facts, thin_facts                # noqa: E402


def made_up():
    """(name, facts, series) for the shapes a real campaign gets to rarely."""
    out = []

    # The ordinary shape: two nations, three dates, measures in both.
    facts = {"1836.1.1": {"ENG": {"total_pop": 1, "is_player": 1},
                          "FRA": {"total_pop": 2, "is_player": 0}},
             "1836.2.1": {"ENG": {"total_pop": 3, "is_player": 1},
                          "FRA": {"total_pop": 4, "is_player": 0}}}
    series = {"ENG": {"total_pop": {"1836.1.1": 1.0, "1836.2.1": 3.0}},
              "FRA": {"total_pop": {"1836.1.1": 2.0, "1836.2.1": 4.0}}}
    out.append(("the ordinary shape", facts, series))

    # A nation that only exists from the second save -- formed, released,
    # or first crossing --min-pop.
    facts = {"1836.1.1": {"ENG": {"total_pop": 1}},
             "1836.2.1": {"ENG": {"total_pop": 2}, "GER": {"total_pop": 9}}}
    series = {"ENG": {"total_pop": {"1836.1.1": 1.0, "1836.2.1": 2.0}},
              "GER": {"total_pop": {"1836.2.1": 9.0}}}
    out.append(("a nation that appears late", facts, series))

    # A measure only one nation ever has, and one nobody has.
    facts = {"1836.1.1": {"ENG": {"infamy": 5}, "FRA": {}}}
    series = {"ENG": {"infamy": {"1836.1.1": 5.0}, "ports": {}},
              "FRA": {"infamy": {}, "ports": {}}}
    out.append(("a measure only one nation has", facts, series))

    # Nothing at all, which a run filtered down to nobody produces.
    out.append(("an empty campaign", {}, {}))

    # A nation in `facts` with nothing but the fields no series carries.
    facts = {"1836.1.1": {"ENG": {"primary_culture": "british"}}}
    series = {"ENG": {"total_pop": {}}}
    out.append(("only the fields no series holds", facts, series))
    return out


def from_report(path):
    """(facts, series) out of a built report, or None."""
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    found = re.search(r'const PACKED = "([^"]*)"', html)
    if not found or not found.group(1):
        return None                      # --split, or no payload inside
    payload = json.loads(gzip.decompress(base64.b64decode(found.group(1))))
    return (payload.get("facts"), payload.get("series"),
            payload.get("factKeys") or [])


def the_template_loop():
    """
    The reconstruction the report actually ships, lifted out by its text.

    Taken from `template.py` rather than copied, so this cannot be testing
    a loop the report does not contain.
    """
    from template import TEMPLATE
    found = re.search(r"for \(const tag in DATA\.series\) \{.*?\n\}\n",
                      TEMPLATE, re.S)
    return found.group(0) if found else None


def same_in_javascript(facts, series, taken):
    """
    Run the template's own loop and see whether it agrees with Python's.

    The two are the same operation written twice, in two languages, and
    only one of them is what a reader ever runs. Needs `quickjs`; skipped
    with a word when it is not installed, since it is not something this
    project otherwise depends on.
    """
    try:
        import quickjs
    except ImportError:
        return None
    loop = the_template_loop()
    if loop is None:
        return None
    data = {"facts": facts, "series": series, "factKeys": taken}
    ctx = quickjs.Context()
    ctx.eval("var DATA = " + json.dumps(data, separators=(",", ":")) + ";")
    ctx.eval(loop)
    return json.loads(ctx.eval("JSON.stringify(DATA.facts)"))


def check(name, facts, series):
    """True if thinning and rebuilding gives back exactly what went in."""
    thin, taken = thin_facts(facts, series)
    back = rebuild_facts(thin, series, taken)
    if back == facts:
        return True
    print("  %s: does NOT come back the same" % name)
    for date in sorted(set(facts) | set(back)):
        a, b = facts.get(date, {}), back.get(date, {})
        for tag in sorted(set(a) | set(b)):
            if a.get(tag) != b.get(tag):
                print("      %s %s: was %r, came back %r"
                      % (date, tag, a.get(tag), b.get(tag)))
                return False
    return False


def main():
    bad = 0
    for name, facts, series in made_up():
        if check(name, facts, series):
            print("  %-34s comes back the same" % name)
        else:
            bad += 1

    if len(sys.argv) > 1:
        path = sys.argv[1]
        got = from_report(path)
        if got is None:
            print("  %s carries no payload to check" % os.path.basename(path))
        else:
            facts, series, keys = got
            # The report on disk already has the thin `facts`, so rebuilding
            # is the whole of the page's job: what it must produce is every
            # measure, for every nation, in every save it was in.
            back = rebuild_facts(facts, series, keys)
            pairs = {(d, t) for d, by in back.items() for t in by}
            want = {(d, t) for t, ms in series.items()
                    for m in keys for d in (ms.get(m) or {})}
            thin_pairs = {(d, t) for d, by in facts.items() for t in by}
            print("  %s: %d nation-saves rebuilt, %d in the file, %d in series"
                  % (os.path.basename(path), len(pairs), len(thin_pairs),
                     len(want)))
            if not want <= pairs:
                print("      %d nation-saves in series never reached facts"
                      % len(want - pairs))
                bad += 1
            measures = {m for by in back.values() for v in by.values()
                        for m in v}
            if len(measures) < 10:
                print("      only %d measures came back; something is wrong"
                      % len(measures))
                bad += 1
            else:
                print("  %-34s %d measures across %d saves"
                      % ("rebuilt from the report", len(measures), len(back)))
            in_js = same_in_javascript(facts, series, keys)
            if in_js is None:
                print("  %-34s no quickjs here, so the template's own loop "
                      "was not run" % "")
            elif in_js == back:
                print("  %-34s agrees with report.py, on this campaign"
                      % "the template's own loop")
            else:
                print("      the loop in template.py and `rebuild_facts` "
                      "do NOT agree")
                bad += 1

    print()
    if bad:
        print("%d check(s) failed" % bad)
        return 1
    print("thinning and rebuilding `facts` is lossless")
    return 0


if __name__ == "__main__":
    sys.exit(main())

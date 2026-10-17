#!/usr/bin/env python3
"""
Hold the page's rebuilt `facts` to the table the same run wrote.

`facts` and `series` carry the same numbers in two orientations, and the
report used to ship both whole -- two megabytes of an eleven megabyte
payload. Only what `series` cannot supply travels now, and the page puts the
rest back at boot. So the report shows numbers that are not in the file it
came in.

This opens the report in headless Firefox and takes `DATA.facts` as the
page has rebuilt it, then holds it to `nations_timeseries.csv` beside the
report, which is written straight from the finished nations: every
nation-save the series hold must come back, and every value both carry must
agree.

    python3 testkit/facts.py path/to/report.html
"""

import base64
import gzip
import json
import os
import re
import sys
import tempfile

import boots
import kit                                                  # noqa: E402
from outcome import SKIPPED                                 # noqa: E402

# The line after the page's rebuilding loop that hands its result out.
HANDED_OUT = "\nwindow.__rebuiltFacts = DATA.facts;\n"


def from_report(path):
    """(facts, series, factKeys, dates) out of a built report, or None."""
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    found = re.search(r'const PACKED = "([^"]*)"', html)
    if not found or not found.group(1):
        return None                      # --split, or no payload inside
    payload = json.loads(gzip.decompress(base64.b64decode(found.group(1))))
    return (payload.get("facts"), payload.get("series"),
            payload.get("factKeys") or [], payload.get("dates") or [])


def rebuilt_by_the_page(path):
    """`DATA.facts` once the page has put it back together, or None."""
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    loop = re.search(r"for \(const tag in DATA\.series\) \{.*?\n\}\n", html, re.S)
    if not loop:
        raise SystemExit("the report has no loop rebuilding DATA.facts to check")
    html = html[:loop.end()] + HANDED_OUT + html[loop.end():]
    with tempfile.TemporaryDirectory(prefix="vic2facts") as folder:
        copy = os.path.join(folder, "report.html")
        with open(copy, "w", encoding="utf-8") as fh:
            fh.write(html)
        said = boots.looked(copy, tour=False,
                            probes=[("facts", "return window.__rebuiltFacts;")])
    if said is None or said["error"]:
        print("the page did not open cleanly: %s" % (said and said["error"]))
        return None
    return said["probes"].get("facts")


def against_the_table(back, table):
    """
    1 if the rebuilt facts disagree with the table the same run wrote: every
    nation-save in one is in the other, and every measure both carry has
    the same value. The table is written straight from the finished
    nations, so it is the answer the page has to arrive back at.
    """
    import csv
    if not os.path.isfile(table):
        print("  %-34s no table beside the report" % "")
        return 0
    with open(table, newline="") as fh:
        rows = {(r["date"], r["tag"]): r for r in csv.DictReader(fh)}
    pairs = {(d, t) for d, by in back.items() for t in by}
    wrong = []
    if pairs != set(rows):
        wrong.append("%d nation-saves only in the page, %d only in the table"
                     % (len(pairs - set(rows)), len(set(rows) - pairs)))
    compared = 0
    for (date, tag), row in sorted(rows.items()):
        for key, value in back.get(date, {}).get(tag, {}).items():
            if key not in row or isinstance(value, (dict, list)):
                continue
            compared += 1
            # The page carries a flag as 1 or 0, the table as True or False.
            text = {"True": "1", "False": "0"}.get(row[key], row[key])
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                same = str(value) == text or (value is None and text == "")
            else:
                try:
                    same = float(text) == float(value)
                except ValueError:
                    same = False
            if not same and len(wrong) < 5:
                wrong.append("%s %s %s: the page has %r, the table %r"
                             % (date, tag, key, value, text))
    print("  %-34s %d values compared with %s" % ("rebuilt against the table", compared,
                                                 os.path.basename(table)))
    for w in wrong:
        print("      " + w)
    return 1 if wrong or not compared else 0


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    path = sys.argv[1]
    got = from_report(path)
    if got is None:
        print("%s carries no payload to check" % os.path.basename(path))
        return SKIPPED
    kit.need_firefox()
    _facts, series, keys, dates = got
    back = rebuilt_by_the_page(path)
    if back is None:
        return 1
    bad = 0
    pairs = {(d, t) for d, by in back.items() for t in by}
    want = {(dates[i], t) for t, ms in series.items() for m in keys
            for i, v in enumerate(ms.get(m) or []) if v is not None}
    print("  %s: %d nation-saves rebuilt by the page, %d in series"
          % (os.path.basename(path), len(pairs), len(want)))
    if not want <= pairs:
        print("      %d nation-saves in series never reached facts" % len(want - pairs))
        bad += 1
    measures = {m for by in back.values() for v in by.values() for m in v}
    if len(measures) < 10:
        print("      only %d measures came back; something is wrong" % len(measures))
        bad += 1
    else:
        print("  %-34s %d measures across %d saves"
              % ("rebuilt by the page", len(measures), len(back)))
    bad += against_the_table(back, os.path.join(os.path.dirname(path),
                                                 "nations_timeseries.csv"))
    print()
    if bad:
        print("%d check(s) failed" % bad)
        return 1
    print("the page rebuilds every fact the table holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())

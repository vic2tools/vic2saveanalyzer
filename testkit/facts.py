#!/usr/bin/env python3
"""
Hold the two halves of the `facts` split to being inverses.

`facts` and `series` carry the same numbers in two orientations, and the
report used to ship both whole -- two megabytes of an eleven megabyte
payload. Only what `series` cannot supply travels now, and the page puts the
rest back at boot.

That means the report shows numbers that are not in the file it came in, and
the loop that puts them back lives in the template. This holds it to
`rebuild_facts` here, its description in Python: on made-up shapes -- a
nation that appears late, a measure only one nation has, an empty campaign
-- thinned and rebuilt, and on a built report if one is given, where what
comes back has to be every nation-save the series hold and every value the
table beside it (`nations_timeseries.csv`, written straight from the
finished nations) holds.

    python3 testkit/facts.py [path/to/report.html]

The template's own loop is run by quickjs where it is installed, and the
page as a whole by `boots.py`, which opens it in a browser.
"""

import base64
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from outcome import SKIPPED                                 # noqa: E402


def rebuild_facts(facts, series, taken, dates):
    """
    Put the two back together, the way the page does at boot: what this
    check holds the template's loop to. `series` is the shipped shape,
    columns against `dates`.
    """
    out = {date: {tag: dict(vals) for tag, vals in by_tag.items()}
           for date, by_tag in facts.items()}
    for tag, metrics in series.items():
        for key in taken:
            column = metrics.get(key)
            if not column:
                continue
            for i, value in enumerate(column):
                if value is None:
                    continue
                out.setdefault(dates[i], {}).setdefault(tag, {})[key] = value
    return out


def as_columns(series, dates):
    """{tag: {measure: {date: value}}} as the page carries it: columns
    against `dates`, None where a nation has no value."""
    return {tag: {m: [by.get(d) for d in dates] for m, by in measures.items()}
            for tag, measures in series.items()}


def thin_facts(facts, series):
    """
    The measures `series` can supply taken out of `facts`, as the report
    ships them: (thin facts, the measures taken). Only a measure every
    nation-save of `facts` has in `series` is taken.
    """
    taken = sorted({m for measures in series.values() for m in measures
                    if all(m not in vals or series.get(tag, {}).get(m, {}).get(date) == vals[m]
                           for date, by in facts.items() for tag, vals in by.items())})
    thin = {date: {tag: {k: v for k, v in vals.items() if k not in taken}
                   for tag, vals in by.items()} for date, by in facts.items()}
    return thin, taken


def made_up():
    """
    (name, dates, facts, series) for shapes a real campaign gets to rarely.

    `series` is written here the way it is built -- {measure: {date: value}}
    -- and turned into the shipped column form by `check`, so these read as
    the data rather than as its encoding.
    """
    out = []

    # The ordinary shape: two nations, three dates, measures in both.
    facts = {"1836.1.1": {"ENG": {"total_pop": 1, "is_player": 1},
                          "FRA": {"total_pop": 2, "is_player": 0}},
             "1836.2.1": {"ENG": {"total_pop": 3, "is_player": 1},
                          "FRA": {"total_pop": 4, "is_player": 0}}}
    series = {"ENG": {"total_pop": {"1836.1.1": 1.0, "1836.2.1": 3.0}},
              "FRA": {"total_pop": {"1836.1.1": 2.0, "1836.2.1": 4.0}}}
    out.append(("the ordinary shape", ["1836.1.1", "1836.2.1"],
                facts, series))

    # A nation that only exists from the second save -- formed, released,
    # or first crossing --min-pop.
    facts = {"1836.1.1": {"ENG": {"total_pop": 1}},
             "1836.2.1": {"ENG": {"total_pop": 2}, "GER": {"total_pop": 9}}}
    series = {"ENG": {"total_pop": {"1836.1.1": 1.0, "1836.2.1": 2.0}},
              "GER": {"total_pop": {"1836.2.1": 9.0}}}
    out.append(("a nation that appears late", ["1836.1.1", "1836.2.1"],
                facts, series))

    # A measure only one nation ever has, and one nobody has.
    facts = {"1836.1.1": {"ENG": {"infamy": 5}, "FRA": {}}}
    series = {"ENG": {"infamy": {"1836.1.1": 5.0}, "ports": {}},
              "FRA": {"infamy": {}, "ports": {}}}
    out.append(("a measure only one nation has", ["1836.1.1"],
                facts, series))

    # Nothing at all, which a run filtered down to nobody produces.
    out.append(("an empty campaign", [], {}, {}))

    # A nation in `facts` with nothing but the fields no series carries.
    facts = {"1836.1.1": {"ENG": {"primary_culture": "british"}}}
    series = {"ENG": {"total_pop": {}}}
    out.append(("only the fields no series holds", ["1836.1.1"],
                facts, series))
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
            payload.get("factKeys") or [], payload.get("dates") or [])


def the_template_loop():
    """
    The reconstruction the report actually ships, lifted out by its text.

    Taken from `template.py` rather than copied, so this cannot be testing
    a loop the report does not contain.
    """
    sys.path.insert(0, os.path.join(HERE, "testkit"))
    from expected import template
    TEMPLATE = template()
    found = re.search(r"for \(const tag in DATA\.series\) \{.*?\n\}\n",
                      TEMPLATE, re.S)
    return found.group(0) if found else None


def same_in_javascript(facts, series, taken, dates):
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
    data = {"facts": facts, "series": series, "factKeys": taken,
            "dates": dates}
    ctx = quickjs.Context()
    ctx.eval("var DATA = " + json.dumps(data, separators=(",", ":")) + ";")
    ctx.eval(loop)
    return json.loads(ctx.eval("JSON.stringify(DATA.facts)"))


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


def check(name, dates, facts, series):
    """True if thinning and rebuilding gives back exactly what went in, by
    the page's own loop where quickjs can run it."""
    thin, taken = thin_facts(facts, series)
    back = rebuild_facts(thin, as_columns(series, dates), taken, dates)
    in_js = same_in_javascript(thin, as_columns(series, dates), taken, dates)
    if in_js is not None and in_js != back:
        print("  %s: the template's loop gives %r, not %r" % (name, in_js, back))
        return False
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
    payload = True
    for name, dates, facts, series in made_up():
        if check(name, dates, facts, series):
            print("  %-34s comes back the same" % name)
        else:
            bad += 1

    if len(sys.argv) > 1:
        path = sys.argv[1]
        got = from_report(path)
        if got is None:
            print("  %s carries no payload to check" % os.path.basename(path))
            payload = False
        else:
            facts, series, keys, dates = got
            # The report on disk already has the thin `facts`, so rebuilding
            # is the whole of the page's job: what it must produce is every
            # measure, for every nation, in every save it was in.
            back = rebuild_facts(facts, series, keys, dates)
            pairs = {(d, t) for d, by in back.items() for t in by}
            want = {(dates[i], t) for t, ms in series.items()
                    for m in keys
                    for i, v in enumerate(ms.get(m) or []) if v is not None}
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
            bad += against_the_table(back, os.path.join(os.path.dirname(path),
                                                         "nations_timeseries.csv"))
            in_js = same_in_javascript(facts, series, keys, dates)
            if in_js is None:
                print("  %-34s no quickjs here, so the template's own loop "
                      "was not run" % "")
            elif in_js == back:
                print("  %-34s agrees, on this campaign" % "the template's own loop")
            else:
                print("      the loop in template.py and `rebuild_facts` do NOT agree")
                bad += 1

    print()
    if bad:
        print("%d check(s) failed" % bad)
        return 1
    print("thinning and rebuilding `facts` is lossless")
    return 0 if payload else SKIPPED


if __name__ == "__main__":
    sys.exit(main())

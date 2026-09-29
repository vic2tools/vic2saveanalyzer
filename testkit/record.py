#!/usr/bin/env python3
"""
The nation record, and the two readers that have to agree about it.

A save is read two ways: in Python by `readsave`, and -- when it has been
built -- by the Rust scanner in `scanner/`, whose answer `nation.fold_*`
folds into the same record. Two implementations of one thing is a liability
that only continuous proof makes safe, and the proof used to be
`testkit/parity.py` alone, which needs a folder of real saves and a compiled
binary and says nothing without both.

That is the wrong shape for the failure it guards. The dangerous drift is
not a wrong number on a machine with a scanner; it is a field one side
learns about and the other does not, which on a machine with no scanner
looks exactly like everything working. It has happened here: the Rust half
of a protocol change was reverted by accident and the Python half shipped
without it, every save was read twice over, and every check passed.

    python3 testkit/record.py

So this holds the two to each other *structurally*, and needs neither a
save, a mod, a Rust compiler nor the built binary -- it reads the scanner's
source. Six things:

  * every fold rule names a field the record actually declares,
  * no field is claimed by two rules,
  * the save-key names Python and Rust each keep a copy of still match,
  * every key the scanner emits is handled, and every key handled is
    emitted -- neither side knows something the other does not,
  * the fold fills the containers `blank_nation` made rather than
    replacing them, so a Counter stays a Counter, and
  * a key nobody accounted for is an error rather than a silence.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fastscan                                            # noqa: E402
import nation                                              # noqa: E402

TABLES = (("the province totals", nation.SCANNED_PROVINCES,
           nation.PROVINCE_EXTRAS),
          ("the country block", nation.SCANNED_COUNTRY,
           nation.COUNTRY_EXTRAS))


def rust_source():
    """Every scanner source file as one string, whichever file a key is in."""
    where = os.path.join(HERE, "scanner", "src")
    return "".join(
        io.open(os.path.join(where, name), encoding="utf-8").read()
        for name in sorted(os.listdir(where)) if name.endswith(".rs"))


def rust_const(text, name):
    """The `(save key, record field)` pairs of one `const` array."""
    m = re.search(r"const %s: &\[\(&str, &str\)\] = &\[(.*?)\];" % name,
                  text, re.S)
    if m is None:
        return None
    return dict(re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', m.group(1)))


def rust_keys(text):
    """
    Every JSON key the scanner writes.

    Two shapes, because the emitter has two: a key written into the string
    outright, and a key handed to one of the little `|out, name, value|`
    closures that write a list of pairs. Nothing here understands Rust; it
    only has to find names, and it is held to finding a plausible number of
    them below.
    """
    return (set(re.findall(r'\\"([a-z_]+)\\":', text))
            | set(re.findall(r'\(&mut out, "([a-z_]+)"', text)))


# One value of the right shape per combining rule, so a rule can be exercised
# without a scanner to send anything. What matters is the shape: a rule that
# adds wants a number, a rule that walks pairs wants pairs.
SAMPLES = {
    nation._add: 3,
    nation._add_if: 3,
    nation._highest: 3,
    nation._put: 1,
    nation._extend: ["a"],
    nation._extend_interned: ["a"],
    nation._update_set: [1, 2],
    nation._replace: [7],
    nation._replace_list_interned: ["a"],
    nation._replace_set_interned: ["a"],
    nation._replace_dict_interned: [("a", 1.5)],
    nation._pairs_put: [(1, 2)],
    nation._pairs_put_interned: [("a", "b")],
    nation._pairs_add: [(1, 2)],
    nation._pairs_add_interned: [("a", 2)],
    nation._pairs_extend: [(1, [5, 6])],
    nation._pairs_add_nested: [(1, [("a", 2)])],
    nation._population_rows: [(1, 2, 1.0, [("farmers", 2)], [("dutch", 2)], 1)],
}


def a_scan():
    """A scanned reading with every declared key in it, and nothing else."""
    provinces = {key: SAMPLES[rule] for key, _f, rule in nation.SCANNED_PROVINCES}
    provinces["mobilizable"] = [(0, 1, 500, 7)]
    country = {key: SAMPLES[rule] for key, _f, rule in nation.SCANNED_COUNTRY}
    country["tag"] = "ENG"
    country["scalars"] = [(f, "x") for f in nation.COUNTRY_SCALARS.values()]
    country["numerics"] = [(f, 1.5) for f in nation.COUNTRY_NUMERICS.values()]
    return provinces, country


def rules_name_real_fields():
    """[what went wrong] with what the rules say they fill."""
    declared = set(nation.blank_nation())
    wrong = []
    # Across both tables, not within each. `fold_provinces` and `fold_country`
    # fill the same nation, so a province rule and a country rule aiming at
    # one field is the same collision as two rules in one table -- and it was
    # the one nothing looked for: pointing the province rule for `ports` at
    # the country field `states` was accepted without complaint.
    seen = {}
    for what, table, _extras in TABLES:
        for key, field, _rule in table:
            if field not in declared:
                wrong.append("%s: the rule for %r fills %r, which is not a "
                             "field of the record" % (what, key, field))
            if field in seen:
                first_what, first_key = seen[field]
                wrong.append(
                    "%r (%s) and %r (%s) both fill %r, and both folds write "
                    "the same nation"
                    % (first_key, first_what, key, what, field))
            seen[field] = (what, key)
    missing = [r for _w, t, _e in TABLES for _k, _f, r in t if r not in SAMPLES]
    if missing:
        wrong.append("no sample value for %d rule(s), so they go unexercised"
                     % len(missing))
    return wrong


def python_and_rust_name_the_same_lines():
    """[what went wrong] between the two copies of the save-key names."""
    text = rust_source()
    wrong = []
    for name, mine in (("SCALARS", nation.COUNTRY_SCALARS),
                       ("NUMERICS", nation.COUNTRY_NUMERICS)):
        theirs = rust_const(text, name)
        if theirs is None:
            wrong.append("could not find `const %s` in scanner/src/country.rs, "
                         "so the two copies of it went unchecked" % name)
            continue
        if theirs != mine:
            for key in sorted(set(mine) | set(theirs)):
                if mine.get(key) != theirs.get(key):
                    wrong.append(
                        "%s: the save's %r goes to %r in nation.py and %r in "
                        "country.rs" % (name, key, mine.get(key),
                                        theirs.get(key)))
    return wrong


def neither_side_knows_more():
    """[what went wrong] between what is sent and what is handled."""
    sent = rust_keys(rust_source())
    if len(sent) < 40:
        return ["only %d JSON keys were found in scanner/src, which is too "
                "few to be right -- the emitter has been rewritten and the "
                "patterns in `rust_keys` no longer find it" % len(sent)]
    # `fastscan` keeps the save's own bookkeeping -- who owns which province,
    # what type each pop was -- because it belongs to no one nation.
    # A serving scanner's answer for a file it turns down is one key too,
    # and so is the line that says how long a `--record` answer is.
    top = (set(fastscan.HEAD_NEEDED) | set(fastscan.NEEDED)
           | {"countries", fastscan.REFUSED, "record"})
    known = set()
    for _what, table, extras in TABLES:
        known |= {key for key, _f, _r in table} | set(extras)
    wrong = []
    for key in sorted(sent - top - known):
        wrong.append("the scanner sends %r and nothing here reads it" % key)
    for key in sorted(known - sent):
        wrong.append("nation.py folds %r and the scanner never sends it" % key)
    return wrong


def the_containers_survive():
    """[what went wrong] with the shapes after a fold."""
    provinces, country = a_scan()
    blank = nation.blank_nation()
    nat = nation.blank_nation()
    nation.fold_provinces(nat, provinces, ["farmers", "dutch"])
    nation.fold_country(nat, country)

    wrong = []
    for field, empty in sorted(blank.items()):
        if not isinstance(empty, (dict, set, list)):
            continue
        if type(nat[field]) is not type(empty):
            wrong.append(
                "%s came out of the fold as a %s, and the record declares it "
                "a %s -- something downstream counts on the second"
                % (field, type(nat[field]).__name__, type(empty).__name__))
    return wrong


def a_stray_key_is_an_error():
    """[what went wrong] when a scanner sends something new, or stops."""
    wrong = []
    for what, extra in (("provinces", nation.fold_provinces),
                        ("a country", nation.fold_country)):
        provinces, country = a_scan()
        block = provinces if what == "provinces" else country
        block["something_new"] = 1
        try:
            if what == "provinces":
                extra(nation.blank_nation(), block, ["farmers", "dutch"])
            else:
                extra(nation.blank_nation(), block)
        except ValueError:
            pass
        else:
            wrong.append("%s: a key nothing accounts for was folded in "
                         "silence" % what)

    for what, table in (("provinces", nation.SCANNED_PROVINCES),
                        ("a country", nation.SCANNED_COUNTRY)):
        provinces, country = a_scan()
        block = provinces if what == "provinces" else country
        del block[table[0][0]]
        try:
            if what == "provinces":
                nation.fold_provinces(nation.blank_nation(), block,
                                      ["farmers", "dutch"])
            else:
                nation.fold_country(nation.blank_nation(), block)
        except KeyError:
            pass
        else:
            wrong.append("%s: a key the scanner stopped sending was read as "
                         "nothing rather than refused" % what)
    return wrong


CHECKS = [
    ("every rule fills a real field, and one rule a field",
     rules_name_real_fields),
    ("Python and Rust name the same lines",
     python_and_rust_name_the_same_lines),
    ("neither side knows a field the other does not", neither_side_knows_more),
    ("the fold fills the containers, not replaces them",
     the_containers_survive),
    ("a key nobody accounted for is an error", a_stray_key_is_an_error),
]


def main():
    width = max(len(n) for n, _f in CHECKS)
    wrong = []
    for name, fn in CHECKS:
        said = fn()
        print("  %-*s %s" % (width, name, "ok" if not said else "FAIL"))
        wrong += said

    print()
    if wrong:
        print("PROBLEMS:")
        for one in sorted(set(wrong)):
            print("  %s" % one)
        return 1
    print("the record has one shape, and both readers of a save fill it")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Write save-shaped text, once, correctly.

Four files here built their own saves and each encoded the format again:
the tab depth, the brace on its own line, the CRLF endings. That is not a
style problem. The depth *is* the format -- the reader and the mod sniffer
both find things by it -- so a builder one tab out produces a file that
looks perfectly fine, parses without complaint, and carries none of what it
was supposed to.

It happened. `matching.py` wrote its technology blocks flat, the mod sniffer
found zero technologies in them, and the test that was supposed to prove a
campaign is matched by its technologies passed for an entirely different
reason until the numbers were looked at.

So the rules live here, and `selfcheck` reads a save built by these
functions back through the real reader and asserts every name it was given
came out again. A builder that is wrong now fails loudly instead of
quietly.

    python3 testkit/savefmt.py        # runs the self-check
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def head(date, player="ENG", flags=(), start="1836.1.1"):
    """The lines above the first block: scalars at the left margin."""
    out = ['date="%s"' % date, 'player="%s"' % player, "government=3"]
    if flags:
        out += ["flags=", "{"] + ["\t%s=yes" % f for f in flags] + ["}"]
    out.append('start_date="%s"' % start)
    return out


def nest(name, lines, depth):
    """`name=` / `{` / lines / `}`, every one of them `depth` tabs in."""
    tab = "\t" * depth
    return [tab + name + "="] + [tab + "{"] + list(lines) + [tab + "}"]


def pop(kind, pid, size, culture="british", religion="protestant",
        literacy=0.4, life=0.8, nested_id=False, extra=(), blocks=()):
    """
    One pop, two tabs in, inside a province block.

    The culture is the line with no key of its own -- `british=protestant`
    -- which is how the game writes it and how the reader finds it, by
    elimination against the fields it knows.

    `nested_id` writes the `id={ id= type= }` form the game uses for a pop
    in a province, rather than the bare number; `extra` takes further
    `\t\t` lines and `blocks` further `\t\t` blocks, which is how a pop
    grows its ideology and issues without this function knowing about
    either.
    """
    out = ["\t%s=" % kind, "\t{"]
    if nested_id:
        out += nest("id", ["\t\t\tid=%d" % pid, "\t\t\ttype=13"], 2)
    else:
        out.append("\t\tid=%d" % pid)
    out += ["\t\tsize=%d" % size,
            "\t\t%s=%s" % (culture, religion),
            "\t\tliteracy=%.5f" % literacy,
            "\t\tlife_needs=%.5f" % life]
    out += ["\t\t" + line for line in extra]
    for name, lines in blocks:
        out += nest(name, lines, 2)
    out.append("\t}")
    return out


def province(pid, owner=None, pops=(), name=None, extra=()):
    """One province: its number at the left margin, its fields one tab in."""
    out = ["%d=" % pid, "{", '\tname="%s"' % (name or "P%d" % pid)]
    if owner:
        out += ['\towner="%s"' % owner, '\tcontroller="%s"' % owner,
                '\tcore="%s"' % owner]
    for line in extra:
        out.append("\t" + line)
    for one in pops:
        out += one
    out.append("}")
    return out


def country(tag, culture="british", techs=(), inventions=(), capital=1,
            extra=(), religion=None, blocks=()):
    """
    One country: its tag at the left margin, its fields one tab in.

    `technology=` one tab, each technology two, each brace on its own
    line. This is the shape that was got wrong; `selfcheck` holds it. A
    technology may be a name or a (name, progress) pair.
    """
    out = ["%s=" % tag, "{", '\tprimary_culture="%s"' % culture]
    if religion:
        out.append('\treligion="%s"' % religion)
    out += ["\tgovernment=democracy", "\tcivilized=yes",
            "\tcapital=%d" % capital, "\tprestige=10.000",
            "\tmoney=100.00000"]
    out += ["\t" + line for line in extra]
    got = []
    for tech in techs:
        name, done = tech if isinstance(tech, tuple) else (tech, 0.0)
        got += nest(name, ["\t\t\t1 %.3f" % done], 2)
    out += nest("technology", got, 1)
    out += nest("active_inventions",
                ["\t\t" + " ".join(str(i) for i in inventions)]
                if inventions else [], 1)
    for name, lines in blocks:
        out += nest(name, lines, 1)
    out.append("}")
    return out


def war(name, attacker, defender, active=True, action="1870.5.1"):
    """One war block, at the left margin like a province or a country."""
    return ["%s=" % ("active_war" if active else "previous_war"), "{",
            '\tname="%s"' % name,
            '\toriginal_attacker="%s"' % attacker,
            '\toriginal_defender="%s"' % defender,
            '\tattacker="%s"' % attacker,
            '\tdefender="%s"' % defender,
            '\taction="%s"' % action, "}"]


def write(path, *parts):
    """Every line, latin-1 and CRLF, the way the game writes one."""
    lines = []
    for part in parts:
        lines.extend(part)
    with open(path, "w", encoding="latin-1", newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def selfcheck(path):
    """
    [what went wrong] when a save built here is read back.

    Every name put in has to come out: the nation, its culture, its
    technologies, its inventions, its people.

    Read twice, because this codebase reads a save two ways and they do
    not agree about how strict the format is. `readsave` finds a
    technology block however it is indented; `cross._sniff`, which decides
    which mod a campaign was played on, finds it only at the depth the
    game actually writes. A builder one tab out therefore satisfies the
    first and tells the second there are no technologies at all -- which
    is precisely what happened, and why checking against the tolerant
    reader alone would have caught nothing.
    """
    import cross
    import v2parse
    import readsave
    v2parse.register_pop_types([])

    techs = ["flintlock_rifles", "clipper_design"]
    write(path,
          head("1850.6.1", player="ENG", flags=("the_great_trek",)),
          province(1, "ENG", [pop("farmers", 1, 1234),
                              pop("soldiers", 2, 766)]),
          province(2, "FRA", [pop("artisans", 3, 500, culture="french")]),
          country("ENG", techs=techs, inventions=[3, 17]),
          country("FRA", culture="french", capital=2),
          war("A Test War", "ENG", "FRA"))

    meta, nations = readsave.analyze_save(path, verbose=False)
    wrong = []
    if meta.get("date") != "1850.6.1":
        wrong.append("the date came back as %r" % meta.get("date"))
    if meta.get("player") != "ENG":
        wrong.append("the player came back as %r" % meta.get("player"))
    if len(meta.get("wars") or ()) != 1:
        wrong.append("%d wars came back, not 1" % len(meta.get("wars") or ()))

    eng = nations.get("ENG")
    if eng is None:
        return wrong + ["ENG was not in the save at all"]
    if eng["total_pop"] != 2000:
        wrong.append("ENG has %d people, not 2000" % eng["total_pop"])
    if sorted(eng["tech_list"]) != sorted(techs):
        wrong.append("ENG's technologies came back as %s"
                     % sorted(eng["tech_list"]))
    if list(eng["invention_ids"]) != [3, 17]:
        wrong.append("ENG's inventions came back as %s"
                     % list(eng["invention_ids"]))
    if eng["primary_culture"] != "british":
        wrong.append("ENG's culture came back as %r" % eng["primary_culture"])
    if dict(eng["pop_by_culture"]).get("british") != 2000:
        wrong.append("ENG's pops by culture came back as %s"
                     % dict(eng["pop_by_culture"]))
    if "FRA" not in nations:
        wrong.append("FRA was not in the save")

    # And now the strict one.
    seen = cross._sniff(path)
    if not {"ENG", "FRA"} <= seen["tags"]:
        wrong.append("the mod sniffer saw tags %s" % sorted(seen["tags"]))
    if not set(techs) <= seen["techs"]:
        wrong.append("the mod sniffer saw technologies %s, not %s"
                     % (sorted(seen["techs"]), sorted(techs)))
    if seen["provinces"] != {1, 2}:
        wrong.append("the mod sniffer saw provinces %s"
                     % sorted(seen["provinces"]))
    if seen["top_invention"] != 17:
        wrong.append("the mod sniffer saw %s as the highest invention"
                     % seen["top_invention"])
    return wrong + rich(path + ".rich")


def rich(path):
    """
    [what went wrong] with a pop carrying everything a real one carries.

    The saves above are minimal. A real pop has its id nested, an ideology
    block, an issues block and half a dozen further numbers, and a real
    country has a stockpile and an army -- and `fake_save.py`, which
    writes the twenty-five megabyte file the parser is profiled against,
    writes all of it. Nothing ever read that file back. If its pops went a
    tab too deep again the benchmark would quietly measure the parser
    doing half the work and every number taken from it would be wrong in
    the flattering direction.
    """
    import readsave

    ideology = [("ideology", ["\t\t\t%d=%.5f" % (i, 0.1 * i)
                              for i in range(1, 7)]),
                ("issues", ["\t\t\t%d=%.5f" % (i, 0.05 * i)
                            for i in range(1, 9)])]
    write(path,
          head("1881.3.24", player="SWE"),
          province(1, "SWE",
                   [pop("farmers", 11, 1500, nested_id=True,
                        extra=["money=12.00000", "con=1.00000",
                               "mil=2.00000", "bank=3.00000"],
                        blocks=ideology),
                    pop("soldiers", 12, 500, nested_id=True,
                        blocks=ideology)],
                   extra=["garrison=10.000", "life_rating=25",
                          "railroad=", "{", "\tlevel=3", "}"]),
          country("SWE", culture="swedish", religion="protestant",
                  techs=[("tech_1", 0.5), ("tech_2", 0.25)],
                  inventions=[1, 2, 3],
                  extra=["badboy=1.000", "conscription=mandatory_service"],
                  blocks=[("stockpile", ["\t\tcoal=100.00000"]),
                          ("army", ['\t\tname="Army"'] + nest(
                              "regiment", ['\t\t\tname="1 Brigade"',
                                           "\t\t\ttype=infantry",
                                           "\t\t\tcount=2000",
                                           "\t\t\tstrength=1.000"], 2))]))

    meta, nations = readsave.analyze_save(path, verbose=False)
    swe = nations.get("SWE")
    if swe is None:
        return ["a fully furnished nation did not come back at all"]
    wrong = []
    if swe["total_pop"] != 2000:
        wrong.append("a pop with an ideology block and a nested id came "
                     "back as %d people, not 2000" % swe["total_pop"])
    if sorted(swe["tech_list"]) != ["tech_1", "tech_2"]:
        wrong.append("technologies with progress came back as %s"
                     % sorted(swe["tech_list"]))
    if list(swe["invention_ids"]) != [1, 2, 3]:
        wrong.append("inventions beside a stockpile came back as %s"
                     % list(swe["invention_ids"]))
    if meta.get("date") != "1881.3.24":
        wrong.append("the date came back as %r" % meta.get("date"))
    return wrong


def main():
    import shutil
    import tempfile
    holding = tempfile.mkdtemp(prefix="vic2fmt")
    try:
        wrong = selfcheck(os.path.join(holding, "a.v2"))
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("a save built here reads back with everything that went into it")
    return 0


if __name__ == "__main__":
    sys.exit(main())

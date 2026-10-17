"""
The worlds the checks are run on: a mod, a game install, a save, built in
a temp folder with exactly the pieces a case is about.

`a_mod` writes the smallest folder the analyzer reads as a mod, `a_game`
the least that is an install, `a_mod_in_a_game` and `a_vanilla` the two
together, `a_save` a save carrying the names a mod accounts for, and
`edge_save` a save with any number of nations, provinces and wars.
`vanilla()` is one unmodded install, made once per process.
"""

import atexit
import os
import shutil
import tempfile

import savefmt

TAGS = ["ENG", "FRA", "PRU", "RUS", "AUS", "TUR", "SPA", "USA"]
POPS = ["farmers", "labourers", "craftsmen", "soldiers", "aristocrats"]
TECHS = ["flintlock_rifles", "post_napoleonic_thought", "clipper_design",
         "the_stirrup", "iron_working"]


def a_mod(root, tags=None, techs=None, provinces=None, inventions=2,
          pops=None, pop_per_regiment=None, mob_size=0.0):
    """
    The smallest folder `_mod_facts` will read as a mod.

    The last three are for the callers that go on to *read* the mod rather
    than only match a campaign against it: which pops it lets a nation
    mobilize, what a regiment of them costs, and whether anything in it
    grants a mobilisation size at all. A mod that grants none is a mod every
    nation scores zero under, which makes a brigade count that cannot tell
    two regiment sizes apart. Left alone they write what they always wrote.
    """
    tags = TAGS if tags is None else tags
    techs = TECHS if techs is None else techs
    provinces = range(1, 41) if provinces is None else provinces
    pops = POPS if pops is None else pops

    os.makedirs(os.path.join(root, "common"), exist_ok=True)
    with open(os.path.join(root, "common", "countries.txt"), "w") as fh:
        for tag in tags:
            fh.write('%s = "countries/%s.txt"\n' % (tag, tag))

    os.makedirs(os.path.join(root, "poptypes"), exist_ok=True)
    for pop in pops:
        with open(os.path.join(root, "poptypes", pop + ".txt"), "w") as fh:
            fh.write("strata = poor\n")

    os.makedirs(os.path.join(root, "technologies"), exist_ok=True)
    with open(os.path.join(root, "technologies", "army_tech.txt"), "w") as fh:
        fh.write("folder = army_tech\n")
        for tech in techs:
            # Only the first one grants it, so a nation holding every
            # technology in the mod has a rate the test can state outright
            # rather than derive.
            grant = ("\tmobilisation_size = %.3f\n" % mob_size
                     if mob_size and tech == techs[0] else "")
            fh.write("%s = {\n\tarea = army_tech\n\tyear = 1836\n"
                     "\tcost = 100\n%s}\n" % (tech, grant))

    if pop_per_regiment is not None:
        # defines.lua is Lua, and `_read_defines` finds the key by regex
        # wherever it sits, so the real file's nesting is written out rather
        # than a flat line that would pass here and not in the game.
        with open(os.path.join(root, "common", "defines.lua"), "w") as fh:
            fh.write("NDefines = {\n\tNMilitary = {\n"
                     "\t\tPOP_SIZE_PER_REGIMENT = %d,\n\t},\n}\n"
                     % pop_per_regiment)

    os.makedirs(os.path.join(root, "inventions"), exist_ok=True)
    with open(os.path.join(root, "inventions", "army.txt"), "w") as fh:
        for i in range(inventions):
            fh.write("an_invention_%d = {\n\tlimit = {\n\t}\n"
                     "\tchance = {\n\t\tfactor = 1\n\t}\n}\n" % i)

    os.makedirs(os.path.join(root, "map"), exist_ok=True)
    with open(os.path.join(root, "map", "definition.csv"), "w") as fh:
        fh.write("province;red;green;blue;x;x\n")
        for pid in provinces:
            fh.write("%d;1;2;3;name;x\n" % pid)
    return root


def _linked(path):
    """A symlink, or on Windows a junction, which `islink` does not see."""
    return os.path.islink(path) or getattr(os.path, "isjunction", lambda p: False)(path)


def a_game(root):
    """
    The least a folder needs to be read as a Victoria II install: its map's
    `default.map`, and nothing in it to inherit.

    A mod is only read inside one: the analyzer refuses a mod anywhere but
    an install's mod folder, the way the game only loads mods from there.
    """
    # Fixture builders must never write through a link into real inputs.
    target = os.path.abspath(os.path.join(root, "map", "default.map"))
    check = target
    while True:
        if _linked(check):
            raise ValueError("refusing to write a fixture through a symlink: " + check)
        parent = os.path.dirname(check)
        if parent == check:
            break
        check = parent
    os.makedirs(os.path.join(root, "map"), exist_ok=True)
    open(target, "w").close()
    return root


def a_mod_in_a_game(holding, name, **kwargs):
    """`a_mod`, at `<holding>/game/mod/<name>`, on an `a_game` install."""
    game = a_game(os.path.join(holding, "game"))
    return a_mod(os.path.join(game, "mod", name), **kwargs)


def a_vanilla(root, **kwargs):
    """
    An install a run can be read on with no mod: `a_mod`'s rules and names,
    and the map file that makes it an install. Every report is read on an
    installed game, so a check that runs the analyzer names one of these
    with `--game-root` where it used to name nothing.
    """
    return a_game(a_mod(root, **kwargs))


def a_save(path, tags=None, techs=None, provinces=None, top_invention=1):
    """A save carrying exactly the names a mod either accounts for or not."""
    tags = TAGS if tags is None else tags
    techs = TECHS if techs is None else techs
    provinces = range(1, 41) if provinces is None else provinces

    parts = [savefmt.head("1880.1.1", player=tags[0])]
    for pid in provinces:
        parts.append(savefmt.province(
            pid, tags[0], [savefmt.pop("farmers", pid, 1000)]))
    for tag in tags:
        parts.append(savefmt.country(tag, techs=techs,
                                     inventions=[top_invention]))
    return savefmt.write(path, *parts)


def edge_save(path, date, tags=("ENG",), provinces=2, techs=(), inventions=(),
           player="ENG", wars="", extra=""):
    """
    One save with exactly the pieces a case is about, and nothing else.

    The layout comes from `savefmt`, which is checked against both readers
    -- this file used to wrap its own braces with a loop that guessed
    where a block ended from the indentation, which is the sort of thing
    that works until the day it does not.
    """
    parts = [savefmt.head(date, player=player)]
    pid = 1
    for tag in tags:
        for _ in range(provinces):
            parts.append(savefmt.province(
                pid, tag, [savefmt.pop("farmers", pid, 1000 + pid * 10)]))
            pid += 1
    first = 1
    for tag in tags:
        parts.append(savefmt.country(tag, techs=techs, inventions=inventions,
                                     capital=first))
        first += provinces
    if wars:
        parts.append(wars)
    if extra:
        parts.append(extra)
    return savefmt.write(path, *parts)


_VANILLA = []


def vanilla():
    """
    An unmodded install to read the cases on, made once. Every report is
    read on an installed game, and a case that named none would only ever
    be refused -- which passes here, and tests nothing.
    """
    if not _VANILLA:
        import atexit
        where = tempfile.mkdtemp(prefix="vic2edgegame")
        atexit.register(shutil.rmtree, where, True)
        _VANILLA.append(a_vanilla(os.path.join(where, "Victoria 2")))
    return _VANILLA[0]


def copies_of(src, dst, skip=()):
    """Copy fixture inputs, dereferencing links so writes stay in the fixture."""
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in skip:
            continue
        source, target = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(source):
            shutil.copytree(source, target, symlinks=False)
        elif os.path.isfile(source):
            shutil.copy2(source, target)

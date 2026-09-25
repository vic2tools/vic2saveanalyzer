# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""
What one run of the analyzer is asked to do: every setting, declared once
with whether it changes what the report says, and the command line that
fills them in.
"""

import argparse
import sys
from dataclasses import dataclass, field as _field, fields


def _number(read, least, most=None):
    """
    An argparse type that refuses what the rest of the program cannot use.

    A regiment of nought people is a division by zero. A map scaled by
    nought is another. A mobilisation size of minus one is neither -- it
    goes all the way through and writes a report saying every nation in the
    game can mobilize minus a hundred percent of itself.

    All three were accepted: the first two came out as a stack trace from
    somewhere deep in a worker, and the third came out as a report. A
    number the program cannot use is worth refusing at the edge, where
    argparse can say which option it was and what would have been allowed.
    """
    def take(text):
        try:
            value = read(text)
        except (TypeError, ValueError):
            raise argparse.ArgumentTypeError("%r is not a number" % text)
        if value < least or (most is not None and value > most):
            raise argparse.ArgumentTypeError(
                "%s is not allowed here; it must be %s"
                % (text, "at least %s" % least if most is None
                   else "between %s and %s" % (least, most)))
        return value
    return take


def _setting(default=None, *, report):
    """
    One setting of a run. `report` says whether it changes what the report
    says, and so has to be in the report stamp. It has no default, so a
    setting cannot be added without deciding which it is.
    """
    return _field(default=default, metadata={"report": report})


@dataclass(frozen=True)
class Run:
    """
    Everything one run of the analyzer was asked to do, declared once.

    This was argparse's namespace, handed from file to file: twenty-seven
    settings read across four modules, declared nowhere but the parser,
    written back onto by `main` once the mod had had its say, and hashed
    into the report stamp by fifteen names written out by hand -- so a new
    setting that changed a number, and was not added to that list, would
    have been answered "nothing has changed" with the old report, and no
    check would have said so. And the window could only reach any of it by
    rewriting `sys.argv`, building `"name=path"` strings for the parser to
    take apart again.

    Now each setting is declared here with whether it changes the report,
    the stamp hashes exactly those, the command line and the window each
    build one of these, and what the mod settles is a new `Run` rather
    than a write onto the old one. The model is `keeper.Options`.
    """

    saves: str = _field(metadata={"report": False})   # hashed file by file
    out: str = _setting("vic2_report", report=False)
    tags: tuple = _setting(report=True)
    mod_path: str = _setting(report=True)
    check_inventions: bool = _setting(False, report=False)
    inventions: str = _setting(report=False)
    explain_mob: str = _setting(report=False)
    mob_rate: float = _setting(1.0, report=True)
    pop_per_regiment: int = _setting(report=True)
    mob_types: tuple = _setting(report=True)
    mob_include_occupied: bool = _setting(False, report=True)
    jobs: int = _setting(report=False)
    no_cache: bool = _setting(False, report=False)
    map_scale: int = _setting(1, report=True)
    player_nations: tuple = _setting(report=True)
    explain_mob_pool: str = _setting(report=False)
    min_pop: int = _setting(0, report=True)
    no_html: bool = _setting(False, report=True)
    rebuild: bool = _setting(False, report=False)
    split: bool = _setting(False, report=True)
    peek: bool = _setting(False, report=False)
    verify: bool = _setting(False, report=False)
    cross: bool = _setting(False, report=True)
    campaign_mod: tuple = _setting((), report=True)   # ((name, mod path), ...)
    primary: str = _setting(report=True)
    game_root: str = _setting(report=True)
    quiet: bool = _setting(False, report=False)

    @classmethod
    def from_command_line(cls, ns):
        """
        A Run from what argparse made of the command line.

        Lists become tuples, because a Run is frozen, and each
        `--campaign-mod NAME=PATH` is taken apart here, once -- refused in
        a sentence if it is not a pair -- rather than by whoever reads it.
        """
        values = dict(vars(ns))
        for name in ("tags", "mob_types", "player_nations"):
            if values.get(name) is not None:
                values[name] = tuple(values[name])
        pairs = []
        for pair in values.get("campaign_mod") or ():
            name, sep, path = pair.partition("=")
            if not sep or not name.strip():
                sys.exit("--campaign-mod wants NAME=PATH, as in "
                         '--campaign-mod "NeoMgame=C:\\...\\mod\\IGoR_puir '
                         '13.0.5". Got: %r' % pair)
            pairs.append((name.strip(), path.strip()))
        values["campaign_mod"] = tuple(pairs)
        return cls(**values)


REPORTED = tuple(f.name for f in fields(Run) if f.metadata["report"])


def command_line():
    """
    Every flag the program takes, and what each one is allowed to be.

    A hundred and twenty lines of it, which is a hundred and twenty
    lines a reader of `main` had to scroll past to reach the first
    thing that happens. The numeric flags carry their own bounds
    through `_number`, so a regiment of nought people is refused here
    by name rather than dividing by zero inside a worker.
    """
    ap = argparse.ArgumentParser(
        description="Aggregate Victoria 2 saves from one campaign into per-nation time series.",
    )
    ap.add_argument("saves", help="folder of .v2 saves, or a single .v2 file")
    ap.add_argument("-o", "--out", default="vic2_report", help="output folder")
    ap.add_argument("--tags", nargs="*", help="only keep these country tags")
    ap.add_argument("--mod-path",
                    help="game or mod folder containing technologies/ and "
                         "inventions/. When given, each nation's mobilisation "
                         "size is computed from the mod's own rules and "
                         "--mobilisation-size becomes a fallback only.")
    ap.add_argument("--check-inventions", action="store_true",
                    dest="check_inventions",
                    help="check the invention decode against the saves "
                         "themselves rather than against the mod folder, and "
                         "exit. Wants a folder of saves rather than one save. "
                         "Needs --mod-path.")
    ap.add_argument("--inventions", metavar="TAG",
                    help="print every invention the last save says that nation "
                         "holds, with the index it was decoded from and the "
                         "file it lives in, then exit. Made for checking the "
                         "decode against the game's own technology screen. "
                         "Needs --mod-path.")
    ap.add_argument("--explain-mob", metavar="TAG",
                    help="print every tech and invention contributing to that "
                         "nation's mobilisation size in the last save, then "
                         "exit. Needs --mod-path.")
    ap.add_argument("--mobilisation-size", type=_number(float, 0.0, 1.0),
                    default=1.0,
                    dest="mob_rate",
                    help="mobilisation size modifier, e.g. 0.05 for 5%%. The save "
                         "does not store it; read it off the in-game military "
                         "panel. Default 1.0 reports the absolute ceiling.")
    # Both default to None rather than to the value they fall back to, so
    # `mod_defaults` can tell "the caller said nothing" from "the caller
    # asked for exactly what vanilla does". `main` writes the settled answer
    # back onto `args` below, so everything downstream still reads a number
    # and a list here.
    ap.add_argument("--pop-per-regiment", type=_number(int, 1), default=None,
                    help="POP_SIZE_PER_REGIMENT from defines.lua (default 3000, "
                         "or the mod's own where --mod-path gives one)")
    ap.add_argument("--mob-types", nargs="*", default=None,
                    help="pop types that can mobilize. With --mod-path this "
                         "comes from the mod's poptypes/ strata; the default "
                         "here is what vanilla works out to.")
    ap.add_argument("--mob-include-occupied", action="store_true",
                    help="count provinces the owner has lost control of. The "
                         "engine excludes them, which is the default, but it "
                         "moves nations under siege a lot -- Russia in 1908 "
                         "reads 558 without them and 612 with -- so it is worth "
                         "checking against the game when a nation is at war.")
    ap.add_argument("-j", "--jobs", type=_number(int, 1), default=None,
                    metavar="N",
                    help="how many saves to read at once. The default sizes "
                         "itself to the machine: one worker per core bar one, "
                         "capped by how many saves are left to read and by how "
                         "much memory is free. Pass 1 to read them one at a "
                         "time.")
    ap.add_argument("--no-cache", action="store_true",
                    help="re-read every save instead of reusing what was parsed "
                         "last time. The cache lives in the system temp folder, "
                         "keyed by the save's size and timestamp and by a hash "
                         "of the parsing code, so editing the parser expires it.")
    ap.add_argument("--map-scale", type=_number(int, 1), default=1,
                    metavar="N",
                    help="how far to shrink the province bitmap for the map tab. "
                         "Default 1, the full 5616x2160 map at about 1.4MB, "
                         "which is the sharpest the tab gets and holds up when "
                         "you zoom into a single theatre. 2 halves it to "
                         "2808x1080 for about 660KB, 3 is 410KB, and 5 is 230KB "
                         "and visibly blocky once you zoom.")
    ap.add_argument("--player-nations", nargs="*", metavar="TAG", default=None,
                    help="tags that were run by a human. Some triggered "
                         "modifiers turn on it -- IGoR and GFM both hand a "
                         "human-run UNCIVILIZED nation +2%% mobilisation size, "
                         "and GFM pays a South American player differently "
                         "from a South American AI. Every country a person is "
                         "playing carries human=yes in its own block, so this "
                         "is only needed for a save that does not, and it "
                         "overrides what the save says when given. Pass it "
                         "with no tags to treat everyone as AI.")
    ap.add_argument("--explain-mob-pool", metavar="TAG",
                    help="print the mobilization pool of that nation in the "
                         "last save -- eligible pops, what colonial, occupied "
                         "and non-accepted provinces cost it, and the ceiling "
                         "under both grouping models -- then exit.")
    ap.add_argument("--min-pop", type=_number(int, 0), default=0,
                    help="drop nations below this population")
    ap.add_argument("--no-html", action="store_true", help="skip the HTML report")
    ap.add_argument("--rebuild", action="store_true",
                    help="build the report again even when nothing has "
                         "changed since the last one")
    ap.add_argument("--split", action="store_true",
                    help="write the data beside the page instead of inside "
                         "it: a small report.html and a report.data.gz, about "
                         "a quarter smaller together and quick to open, but "
                         "both files have to be served rather than opened "
                         "from a disk")
    ap.add_argument("--peek", action="store_true",
                    help="print the structure of the first save and exit")
    ap.add_argument("--verify", action="store_true",
                    help="cross-check unit counts against an independent scan")
    ap.add_argument("--cross", action="store_true",
                    help="treat the saves path as a folder OF campaign folders "
                         "and compare the same nation across all of them. Each "
                         "campaign's mod is worked out from its own saves, so "
                         "--mod-path is not needed; --game-root says where the "
                         "mods live. The rest of the report is built from "
                         "whichever campaign has the most saves.")
    ap.add_argument("--campaign-mod", metavar="NAME=PATH", action="append",
                    default=[],
                    help="with --cross, the mod one campaign was played on, "
                         "given as its folder name then the mod path. Repeat "
                         "for as many as you like. Campaigns not named this "
                         "way are still worked out from their own saves, so "
                         "you only have to settle the ones you care about. "
                         "Beats --mod-path for the campaigns it names.")
    ap.add_argument("--primary", metavar="NAME",
                    help="with --cross, which campaign the rest of the report "
                         "is built from. The folder's own name. Without it the "
                         "one with the most saves is used.")
    ap.add_argument("--game-root",
                    help="the Victoria 2 install folder, the one with mod/ "
                         "inside. Only used by --cross, to find candidates.")
    ap.add_argument("-q", "--quiet", action="store_true")
    return ap.parse_args()

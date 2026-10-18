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
Victoria 2 campaign analyzer.

Reads a folder of .v2 saves from the same game and builds a per-nation time
series: population, accepted-culture share, literacy, brigades, ships by type,
industry, naval bases, and the usual country scalars.

    python3 vic2_analyzer.py ~/Documents/Paradox\\ Interactive/Victoria2/save\\ games
    python3 vic2_analyzer.py saves/ --out results --tags ENG FRA GER
    python3 vic2_analyzer.py saves/ --no-html

Saves must be plaintext. If yours are binary, launch the game in debug mode
and re-save; the file gets about 10x bigger but becomes readable.

The command line is read here (`command_line`, into a `Run`) and the run is
made by the scanner (`vic2scan analyze`, in `scanner/`), which does all of it
in Rust: this module finds the scanner, hands it the run, and relays what it
says to whoever is listening -- a terminal, or the window's log.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field as _field, fields


_REPORT_READY = None


def set_report_ready(fn):
    """
    Give the analyzer somewhere to say the report is on disk.

    It is written before the CSV tables are, and nothing in it comes out of
    them, so it can be opened while they are still being written. That is
    about a third of a second of a warm run -- the whole point of which is
    that pressing the button and reading the report are the same moment.
    """
    global _REPORT_READY
    _REPORT_READY = fn


def _tell_report_ready(path):
    if _REPORT_READY is not None:
        try:
            _REPORT_READY(path)
        except Exception:             # a window that has gone away
            pass




def analyze(run, cancel=None, progress=None, ready=None):
    """
    One run, for a caller that is not a command line: the window.

    It hands over a `Run` rather than rewriting `sys.argv` for the parser to
    read back, and the three things it wants told -- whether to stop, how
    far along the saves are, and where the report landed -- as arguments,
    which are set for this run and cleared after it whatever happens.

    A run refused comes back as the `RunError` it was refused with, for the
    window to show, rather than as a request to end the process.
    """
    set_cancel_check(cancel)
    set_progress(progress)
    set_report_ready(ready)
    try:
        status = _front(run, hosted=True)
        if status:
            raise RuntimeError("the scanner stopped with status %s" % status)
        return status
    finally:
        set_cancel_check(None)
        set_progress(None)
        set_report_ready(None)


def main(run=None):
    """
    One run, as `run` declares it or as the command line does, for a
    command line: a run refused ends the process with its sentence and a
    non-zero status, which is how the command line has always said no.
    """
    try:
        if run is None:
            run = Run.from_command_line(command_line())
        sys.exit(_front(run))
    except RunError as refused:
        sys.exit(str(refused))


# What `cargo` is asked for when there is no scanner to hand a run to.
BUILD = "cargo build --release --manifest-path scanner/Cargo.toml"


def _front(run, hosted=False):
    """
    The run done by the scanner (`vic2scan analyze`): its exit status. With
    no scanner to hand it to, the run is refused with how to build one.

    `hosted` is the window's run: the scanner's lines go to `sys.stdout`
    and `sys.stderr` as they come, its progress and "the report is on disk"
    to the callbacks `analyze` set, and the Stop button kills it.
    """
    binary = available()
    if not binary:
        raise RunError(
            "The scanner that makes the report is not built (%s, looked for beside this "
            "program and in scanner/target/release). Build it with:\n\n    %s\n\nThat "
            "needs Rust's cargo; see README.md." % (BINARY, BUILD))
    import dataclasses
    import json
    import subprocess
    import tempfile
    fd, path = tempfile.mkstemp(prefix="vic2_run_", suffix=".json")
    refused = path[:-len(".json")] + ".refused"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # The cache folder is named here, once, so the scanner keeps its
            # entries where the window's "empty the cache" looks.
            fh.write(json.dumps(dict(dataclasses.asdict(run), cache_dir=cache_dir())))
        # A windowed build started with arguments and no console to attach
        # to (a folder dropped on it) has no streams at all.
        silent = sys.stdout is None or sys.stderr is None
        for stream in (sys.stdout, sys.stderr):
            if stream is not None:
                stream.flush()
        argv = [binary, "analyze", "--run", path, "--refused", refused]
        if hosted:
            argv.append("--protocol")
        if silent:
            # Nowhere to say anything: the scanner says it to nowhere too,
            # and opens no window of its own to do it in.
            status = subprocess.call(argv, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=_no_window())
        elif not hosted and sys.stdout is sys.__stdout__ and sys.stderr is sys.__stderr__:
            # No CREATE_NO_WINDOW here. It gives a console program a hidden
            # console of its own, and with no handles passed its output goes
            # there: on Windows a run from a terminal printed nothing. Handed
            # this process's own streams, it writes where Python would have --
            # the console, or the file they were redirected to.
            status = subprocess.call(argv, stdout=sys.stdout, stderr=sys.stderr)
        else:
            # Someone is catching what this prints -- the window's log, or a
            # check running the analyzer in its own process -- and a child's
            # output would go past them to the real streams, so it is passed
            # on through.
            status = _relayed(argv, _no_window(), hosted)
        if status == REFUSED:
            # A run refused, in its sentence, raised as it always was.
            with open(refused, encoding="utf-8") as fh:
                raise RunError(fh.read())
    finally:
        for leftover in (path, refused):
            try:
                os.remove(leftover)
            except OSError:
                pass
    return status

# The status `vic2scan analyze` exits with when it refused the run and wrote
# the sentence to the file it was given.
REFUSED = 4


def _relayed(argv, flags, hosted=False):
    """
    Run `argv`, its output written to `sys.stdout` and `sys.stderr` as it
    comes, and its status. Hosted, the protocol lines go to the progress and
    report-ready callbacks instead, and a Stop asked for kills it and raises
    `Cancelled` -- every save it had read by then is in the engine's cache.
    """
    import subprocess
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=flags)
    failed = []

    def copy(source, target, lines):
        try:
            for raw in iter(source.readline, b""):
                line = raw.decode("utf-8", "replace")
                if lines and line.startswith("@"):
                    word, _, rest = line.rstrip("\r\n").partition(" ")
                    if word == "@progress":
                        done, total = rest.split()[:2]
                        tell_progress(int(done), int(total))
                        continue
                    if word == "@ready":
                        _tell_report_ready(rest)
                        continue
                    if word == "@done":
                        continue
                target.write(line)
        except Exception as exc:                     # noqa: BLE001
            failed.append(exc)
        finally:
            source.close()

    threads = [threading.Thread(target=copy, args=(proc.stdout, sys.stdout, hosted), daemon=True),
               threading.Thread(target=copy, args=(proc.stderr, sys.stderr, False), daemon=True)]
    for t in threads:
        t.start()
    try:
        while threads[0].is_alive():
            threads[0].join(0.1)
            if hosted:
                stop_if_asked()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        for t in threads:
            t.join()
        proc.wait()
        raise
    for t in threads:
        t.join()
    status = proc.wait()
    if failed:
        raise failed[0]
    return status


# ----------------------------------------------------------------------------
# What one run of the analyzer is asked to do: every setting, declared once
# with whether it changes what the report says, and the command line that
# fills them in.

class RunError(Exception):
    """
    A run refused, in a sentence the person running it can act on: a path
    that is not there, a mod folder that is not one, a table open in Excel.

    The analyzer is a library to the window as much as a program to the
    command line, so it says no by raising this rather than by ending the
    process. `main` turns it into the message and the exit
    status the command line has always given; the window puts it in its
    log.
    """

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
                raise RunError("--campaign-mod wants NAME=PATH, as in "
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
                    help="the mod the campaign was played on, in the mod "
                         "folder of the game it runs on: <Victoria 2>/mod/"
                         "<name>. Each nation's mobilisation size is computed "
                         "from its own rules, and --mobilisation-size becomes "
                         "a fallback only. Leave it out for the unmodded game.")
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
                    help="the folder Victoria 2 is installed in, the one "
                         "holding map/, gfx/ and mod/. Every report is read on "
                         "it: on its own rules, or on those of a mod in its "
                         "mod folder. A mod there names its install, so with "
                         "--mod-path this can be left out. With --cross, also "
                         "where to look for each campaign's mod.")
    ap.add_argument("-q", "--quiet", action="store_true")
    return ap.parse_args()


# ----------------------------------------------------------------------------
# Where the scanner is (`scanner/`, built with cargo), and how to start it
# with no window of its own.
#
# The scanner makes every run: the command line and the window hand it the
# run (`_front`). It is looked for beside the executable when frozen, beside
# the program's own folder, and in the crate's own target directory.

BINARY = "vic2scan.exe" if sys.platform == "win32" else "vic2scan"
_FOUND = None


def _candidates():
    """Where the scanner might be, nearest first."""
    # The folder holding this package: the checkout, or the unpacked exe.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Beside the executable when frozen, in the program's folder when not, and in
    # the crate's own target directory when working on it.
    yield os.path.join(getattr(sys, "_MEIPASS", here), BINARY)
    yield os.path.join(here, BINARY)
    yield os.path.join(here, "scanner", "target", "release", BINARY)


def available():
    """The scanner's path, or None. Looked for once."""
    global _FOUND
    if _FOUND is None:
        _FOUND = ""
        for path in _candidates():
            if os.path.isfile(path) and os.access(path, os.X_OK):
                _FOUND = path
                break
    return _FOUND or None


def _no_window():
    """
    What `Popen` is told so the scanner opens no window of its own.

    The executable is a windowed program and the scanner a console one, and
    on Windows a windowed program that starts a console program gets a new
    console window for it -- one flashed up for every run -- unless
    it says `CREATE_NO_WINDOW`. Everywhere else there is no such flag, and
    `Popen` refuses any.
    """
    if sys.platform != "win32":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


# ----------------------------------------------------------------------------
# The two things a running analysis shares with whoever started it -- a Stop
# button to ask between saves, a progress bar to tell -- and the folder the
# scanner keeps what it has read in, which the window can measure and empty.

class Cancelled(Exception):
    """The caller asked for the run to stop before it finished."""


# A window has a Stop button; a terminal has Ctrl-C. Whoever is driving hands a
# callable in and it is asked, between saves, whether to carry on. Between
# saves rather than inside one because a save is a few seconds at worst and
# unwinding a half-read one buys nothing.
_STOP = None


def set_cancel_check(fn):
    """Give the analyzer something to ask before it starts the next save."""
    global _STOP
    _STOP = fn


def stop_if_asked():
    if _STOP is not None and _STOP():
        raise Cancelled()


_PROGRESS = None


def set_progress(fn):
    """
    Give the analyzer somewhere to say how far through the saves it is.

    Counted in saves rather than in bytes or in stages, because a save is the
    unit the work actually comes in and the one a reader can see going by. A
    campaign of a few dozen does not need this; one of seven hundred is four
    minutes of a window that otherwise looks stuck.
    """
    global _PROGRESS
    _PROGRESS = fn


def tell_progress(done, total):
    if _PROGRESS is not None:
        try:
            _PROGRESS(done, total)
        except Exception:             # a window that has gone away
            pass


def cache_dir():
    """Where parsed saves are remembered between runs."""
    return os.path.join(tempfile.gettempdir(), "vic2_analyzer_cache")


def cache_stats():
    """How many entries the cache holds and what they weigh, as (count, bytes).

    Nothing here evicts anything. A slot is keyed by the save, the mod, and a
    hash of the parser itself, so editing the parser does not replace the old
    entries -- it stands a fresh generation up beside them, and the previous one
    can never be read again. An install that has seen a few updates is therefore
    mostly holding generations it has no use for, which is the case for offering
    to empty it.
    """
    count = size = 0
    try:
        with os.scandir(cache_dir()) as entries:
            for entry in entries:
                if not entry.name.endswith(".pkl"):
                    continue
                try:
                    size += entry.stat().st_size
                except OSError:
                    continue          # vanished under us; it is not in the total
                count += 1
    except OSError:
        return 0, 0                   # no cache folder yet, which is not a fault
    return count, size


def clear_cache():
    """Empty the cache. Returns (entries removed, bytes freed).

    Only this program's own `.pkl` files go, and the folder itself stays: it
    sits in the system temp directory, which belongs to everybody, so taking
    the tree out wholesale is not this program's business. An entry another run
    still has open is skipped rather than fought over -- it will be caught by
    the next wipe.
    """
    removed = freed = 0
    folder = cache_dir()
    try:
        names = os.listdir(folder)
    except OSError:
        return 0, 0
    for name in names:
        if not name.endswith(".pkl"):
            continue
        path = os.path.join(folder, name)
        try:
            size = os.path.getsize(path)
            os.remove(path)
        except OSError:
            continue
        removed += 1
        freed += size
    return removed, freed


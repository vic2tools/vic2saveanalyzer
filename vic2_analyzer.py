#!/usr/bin/env python3
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
"""

import argparse
import csv
import json
import hashlib
import os
import re
import tempfile
import sys
from collections import defaultdict, namedtuple
from functools import partial

import cacheio
from cacheio import load as _cache_read

import v2parse
from v2parse import (
    POP_TYPES,
    TOKEN_RE,
    Tokens,
    looks_like_country_tag,
    parse_block,
    pop_culture,
    read_save_text,
    skip_block,
    to_float,
    to_int,
    unquote,
)
from tech_groups import TECH_GROUP
# Reading a save is its own thing and lives in its own file: a path in, and
# what the save says out. Nothing in it knows about caches, workers, reports
# or the command line, which is why it could be lifted out whole.
from explain import asked, explain, save_world
from modrules import rate_for
from nation import (
    AS_PLAIN_DICTS,
    AS_PLAIN_DICTS_INSIDE,
    KEEP_FOR_INVENTIONS,
    KEEP_NATION,
    MOBILIZABLE_TYPES,
    POP_SIZE_PER_REGIMENT,
    SPENT_ON_FINALIZE,
    accepted_cultures_of,
    brigades_from_clusters,
    mobilization_clusters,
    trim_save,
)
from readsave import (
    PLAIN,
    POP_TYPE_LIST,
    STRATA,
    analyze_save,
    date_key,
    reading_for,
    reading_now,
)



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


def _stop_if_asked():
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


def _tell_progress(done, total):
    if _PROGRESS is not None:
        try:
            _PROGRESS(done, total)
        except Exception:             # a window that has gone away
            pass


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


# The engine applies no minimum pop size to *mobilization*. POP_MIN_SIZE_FOR_REGIMENT
# governs how small a *soldier* pop may be and still support a standing brigade,
# which is a different rule on a different pop type -- IGoR sets it to 1000.
#
# How the count works is in brigades_from_clusters and in the README. It was
# measured on a purpose-built test bed inside the mod rather than fitted, and
# POP_SIZE_PER_REGIMENT is the only number in it. Six earlier models -- per-pop
# truncation, a cascade up province/state/nation, a province levy, a fixed
# share of short pops, a manpower threshold, and a pooled scale factor -- were
# each fitted to in-game readings and each failed somewhere; they are gone, and
# the README records what they were and how they broke.










def _parser_fingerprint():
    """Invalidate cached parses when any parser or scanner dependency changes."""
    import fastscan
    import readsave
    import tech_groups
    source = cacheio.source_fingerprint(
        __file__, readsave.__file__, v2parse.__file__, fastscan.__file__,
        tech_groups.__file__, cacheio.__file__)
    if not source:
        return ""
    if getattr(sys, "frozen", False):
        # The bundled scanner is covered by the executable fingerprint. Its
        # temporary extraction timestamp changes on every launch.
        return source[:10]
    return hashlib.md5((source + _scanner_fingerprint()).encode()).hexdigest()[:10]


def _scanner_fingerprint():
    """
    The Rust scanner, as a version.

    It reads the provinces, so it decides what a cached save says just as
    much as the Python does -- and a rebuilt scanner that behaves differently
    would otherwise be handed the old scanner's answers out of the cache, and
    the old scanner's report off the disk. Its size and timestamp are enough:
    every build writes both.
    """
    try:
        import fastscan
        binary = fastscan.available()
        if not binary:
            return "no-scanner"
        stat = os.stat(binary)
        return "scanner|%d|%d" % (stat.st_size, stat.st_mtime_ns)
    except Exception:
        return "no-scanner"


# What a finished report was made from. If all of it is the same, the report
# on disk is the report this run would write, byte for byte.
STAMP_FILE = "report.stamp"


def report_stamp(files, args, world):
    """
    A signature of everything that decides what the report says.

    Every save it was built from and the state of each of them, the code that
    reads saves, the code that writes reports, the mod, and the settings that
    change any number in it. Anything here changing means the report has to be
    built again; nothing here changing means it does not, and that is the
    difference between pressing Analyze and waiting, and pressing Analyze and
    reading.
    """
    digest = hashlib.md5()
    for path in sorted(files):
        try:
            stat = os.stat(path)
        except OSError:
            return ""
        digest.update(f"{os.path.abspath(path)}|{stat.st_size}|"
                      f"{stat.st_mtime_ns}\n".encode("utf-8"))
    digest.update(("parser=" + _parser_fingerprint()).encode("utf-8"))
    digest.update(("world=" + str(world)).encode("utf-8"))
    # The report's own code, for the same reason the parse cache hashes the
    # parser: a change to the template is a change to the report.
    if getattr(sys, "frozen", False):
        digest.update(("frozen=" + _parser_fingerprint()).encode("utf-8"))
    else:
        # Every source file beside this one, rather than the handful that
        # were thought of at the time. That list was wrong within a day:
        # `modrules.py` was lifted out of `mod_reader.py`, which was on it,
        # and did not inherit its place -- so doubling every nation's
        # mobilisation size changed nothing the skip could see and the next
        # run answered "nothing has changed since this was built" and served
        # the old report. A list of names is a thing to forget; a folder is
        # not. The file's name is hashed too, so renaming one counts.
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            for name in sorted(os.listdir(here)):
                if not name.endswith(".py"):
                    continue
                with open(os.path.join(here, name), "rb") as fh:
                    digest.update(name.encode("utf-8"))
                    digest.update(fh.read())
        except OSError:
            return ""
    # Every setting that reaches a number in the report. Not --jobs, not
    # --quiet, not where it is written: those change how it is made, not what
    # it says.
    for name in ("tags", "min_pop", "mob_rate", "mob_types", "pop_per_regiment",
                 "mob_include_occupied", "player_nations", "map_scale",
                 "split", "no_html", "mod_path", "game_root", "cross",
                 "primary", "campaign_mod"):
        digest.update(("%s=%r\n" % (name, getattr(args, name, None)))
                      .encode("utf-8"))
    return digest.hexdigest()


def stamp_matches(outdir, stamp, filename="report.html"):
    """Whether the report already sitting there was made from exactly this."""
    if not stamp:
        return False
    report = os.path.join(outdir, filename)
    if not os.path.isfile(report) or os.path.getsize(report) == 0:
        return False
    try:
        with open(os.path.join(outdir, STAMP_FILE), encoding="utf-8") as fh:
            return fh.read().strip() == stamp
    except OSError:
        return False


def write_stamp(outdir, stamp):
    """Record what this report was made from, for the next run to compare."""
    if not stamp:
        return
    try:
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, STAMP_FILE), "w",
                  encoding="utf-8") as fh:
            fh.write(stamp)
    except OSError:
        pass                          # a report that cannot be skipped later


def cache_dir():
    """Where parsed saves are remembered between runs."""
    return os.path.join(tempfile.gettempdir(), "vic2_analyzer_cache")


def _cache_slot(path, fingerprint, world="no-mod"):
    """Where this save's parsed form lives, keyed by the file, the parser and
    the mod it is being read under."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = hashlib.md5(
        f"{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}"
        f"|{fingerprint}|{world}".encode("utf-8")).hexdigest()
    return os.path.join(cache_dir(), key + ".pkl")


def _cache_write(slot, meta, nations):
    cacheio.store(slot, (meta, dict(nations)))


def invention_summary(meta, nations):
    """The country fields needed to decode invention IDs across a campaign."""
    return ({"file": meta.get("file", "?"), "date": meta.get("date", "")},
            {tag: {"tag": nat.get("tag", tag),
                   "tech_list": nat["tech_list"],
                   "invention_ids": nat["invention_ids"]}
             for tag, nat in nations.items()})


def campaign_inventions(files, **options):
    """Cache the campaign-wide input to invention decoding as one small list.

    Raw parses remain cached for the report pass. On a miss only the fields
    needed for decoding cross the worker boundary, preserving input order.
    """
    fingerprint = _parser_fingerprint() if options.get("use_cache", True) else ""
    world = options.get("reading", PLAIN).fingerprint()
    slots = [_cache_slot(path, fingerprint, world)
             for path in files] if fingerprint else []
    slot = None
    if slots and all(slots):
        key = hashlib.sha256("\n".join(slots).encode()).hexdigest()
        slot = os.path.join(cache_dir(), "inventions_" + key + ".pkl")
    held = _cache_read(slot)
    if held is not None:
        _tell_progress(len(files), len(files))
        return held
    stream = parse_saves_stream(files, transform=invention_summary, **options)
    try:
        made = list(stream)
    finally:
        stream.close()
    cacheio.store(slot, made)
    return made


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




# What a worker needs to finish a save where it read it. A named shape
# rather than a dict of strings because it crosses a process boundary and
# is read in a loop: `spec.rate` says what it is, `spec["rate"]` says only
# that somebody hoped it would be there.
Finish = namedtuple(
    "Finish", "rate pop_per_regiment mob_types include_occupied "
              "player_nations wanted min_pop mod live keep_pools",
    defaults=(False,))

# A picklable callable applied after reading and caching a save. The parent
# can request either invention summaries or finalized nations.
_TRANSFORM = None


def _worker_setup(reading, transform=None):
    """
    What a fresh interpreter has to be told before it can read a save.

    Windows starts a worker by re-running this file, so nothing the parent
    set is set here. It used to be told three lists and had to put them back
    in the right three places; it is told the one profile and asks it to.
    """
    global _TRANSFORM
    reading.apply()
    _TRANSFORM = transform


def mod_defaults(args, mod):
    """
    The two numbers a mod has an opinion about, as this run should use them.

    `defines.lua` says how many people a regiment costs and `poptypes/` says
    which pops can be mobilized, and both are defaults rather than overrides:
    they fill in what the caller left alone and give way to
    `--pop-per-regiment` and `--mob-types`.

    Worked out here and handed back rather than written into `args`, because
    `--cross` reads several campaigns under several mods and there is one
    `args` for all of them. `main` still writes the answer back -- it has the
    one mod, and the rest of a single-campaign run reads these off `args` --
    but `run_cross` cannot, and so it used not to apply them at all.
    """
    pop_per_regiment = args.pop_per_regiment
    mob_types = list(args.mob_types)
    if mod is not None:
        defines = mod["defines"] or {}
        if ("POP_SIZE_PER_REGIMENT" in defines
                and pop_per_regiment == POP_SIZE_PER_REGIMENT):
            pop_per_regiment = int(defines["POP_SIZE_PER_REGIMENT"])
        if mod["mob_types"] and mob_types == sorted(MOBILIZABLE_TYPES):
            mob_types = sorted(mod["mob_types"])
    return pop_per_regiment, mob_types


def finish_spec(args, mod, live, wanted=None, keep_pools=False):
    """
    Everything finishing a save needs, decided in one place.

    There used to be two of these. `main` built one for the workers and
    `run_cross` built its own by hand for each campaign, and they disagreed
    about five things -- the mod's regiment size, whether `--mob-types` was
    read at all, which list the parse and the finishing each used, who
    counted as a player, and the smallest population worth measuring.

    The worst of them was the first. `--cross` puts a cross-campaign block in
    a report whose other charts are about one of those same campaigns, so the
    same nation appeared twice on one page with its brigades divided by 3000
    in one place and by the mod's own number in the other, and nothing said
    which was which.
    """
    pop_per_regiment, mob_types = mod_defaults(args, mod)
    return Finish(
        rate=args.mob_rate,
        pop_per_regiment=pop_per_regiment,
        mob_types=frozenset(mob_types),
        include_occupied=args.mob_include_occupied,
        player_nations=(set(args.player_nations)
                        if args.player_nations is not None else None),
        wanted=wanted,
        min_pop=args.min_pop,
        mod=mod,
        live=live,
        keep_pools=keep_pools)


def players_in(meta, nations, told):
    """
    Which tags a person was playing, in the order the answers are believed.

    What was said outright first. Then the save's own markers: every country
    a person is playing carries `human=yes` in its own block, so a
    multiplayer save names all of its players and not just whoever pressed
    save. Older saves and some mods write no such marker at all, hence the
    fall back to the save's own player.

    This decides more than a column. IGoR and GFM both pay a human-run
    nation a mobilisation size an AI does not get, so a run that answers it
    differently reports different brigade counts for the same save.
    """
    if told is not None:
        return set(told)
    played = {tag for tag, nat in nations.items() if nat.get("human")}
    if played:
        return played
    return {meta["player"]} if meta.get("player") else set()


def kept_by(spec, tag, nat):
    """
    Whether this run measures this nation.

    One definition, because three loops used to carry their own copy of it
    and a nation the report leaves out has to be left out everywhere:
    `is_player` is set on the nations that are kept and on no others, and
    the trim keeps that key only where it exists.
    """
    return ((not spec.wanted or tag in spec.wanted)
            and nat["total_pop"] >= spec.min_pop)


def finish_nations(meta, nations, spec):
    """
    One save's nations, finished: the players picked, the rest filtered out,
    and `finalize` run over what is left.

    This is the last step that reads a save whole, and it turns two megabytes
    of per-province tables into a few dozen numbers a nation. Done where the
    save was parsed it happens on every core at once and only the numbers are
    sent back; done in the parent it happens one save at a time, after the
    tables have already been pickled, piped and unpickled to get there.

    Every nation comes back -- finished where it was kept, untouched where it
    was not -- so a caller that needs to know which is which asks `kept_by`
    rather than repeating the filter and drifting away from it.
    """
    players = players_in(meta, nations, spec.player_nations)
    # What this save says about everyone, which is what the mod's triggered
    # modifiers ask about: the year, the great powers, who is at war and who
    # owns what. One per save rather than one per nation, and worked out
    # here rather than sent, because the worker has the save and the mod.
    stage = save_world(meta, spec.mod) if spec.mod is not None else None
    out = {}
    for tag, nat in nations.items():
        if not kept_by(spec, tag, nat):
            out[tag] = nat
            continue
        nat["is_player"] = (tag in players)
        rate = rate_for(nat, spec.mod, spec.live, stage, spec.rate)
        done = finalize(nat, rate, spec.pop_per_regiment,
                        mob_types=spec.mob_types,
                        include_occupied=spec.include_occupied,
                        mod=spec.mod, world=stage)
        done["mobilisation_size"] = round(rate, 5)
        if not spec.keep_pools:
            # A nation's mobilizable pops are one entry per pop per province
            # -- eleven thousand of them for a large nation, two megabytes a
            # save -- and `finalize` copies a nation shallowly, so the
            # finished one still points at the raw pool that made it. Only
            # `--explain-mob-pool` prints that back, so every other run lets
            # it go here instead of carrying it for the whole campaign.
            done["mobilizable_pops"] = ()
        out[tag] = done
    return out


def _finish_save(meta, nations, spec):
    """
    `finish_nations`, and then what a save needs to cross a pipe.

    Finishing in the worker is what lets a save come back as numbers rather
    than tables, so what the finishing has spent is dropped here, and the
    counters go over as the plain dicts they already are.
    """
    out = finish_nations(meta, nations, spec)
    for done in out.values():
        for name in SPENT_ON_FINALIZE:
            done.pop(name, None)
        for name in AS_PLAIN_DICTS:
            counted = done.get(name)
            if counted is not None:
                done[name] = dict(counted)
        for name in AS_PLAIN_DICTS_INSIDE:
            counted = done.get(name)
            if counted is not None:
                done[name] = {where: dict(kinds)
                              for where, kinds in counted.items()}
    return meta, out


def _worker_parse(job):
    """
    One save, in a worker.

    The cache entry is written here rather than handed back for the parent to
    write. Pickling and compressing half a megabyte is real work, and done in
    the parent it is done one save at a time while fifteen workers wait --
    which on a hundred saves is most of a second of nothing happening.

    A save that is already cached is read here for the same reason. Nothing
    is reparsed -- the entry is decompressed and unpickled, which is the
    whole cost of a warm run -- and it happens on a spare core rather than in
    the one process that has everything else left to do.

    Plain dicts, because a defaultdict of lambdas will not pickle.
    """
    index, path, slot, cached = job
    meta = nations = None
    if cached:
        got = _cache_read(slot)
        if got is not None:
            meta, nations = got
    if nations is None:
        meta, nations = analyze_save(path, verbose=False)
        nations = dict(nations)
        _cache_write(slot, meta, nations)
    if _TRANSFORM is not None:
        meta, nations = _TRANSFORM(meta, nations)
    return index, slot, meta, nations


def _spare_memory():
    """Bytes the machine can spare right now, or None if it will not say."""
    if os.name != "nt":
        try:
            return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, AttributeError, OSError):
            return None
    try:
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _Status()
        status.dwLength = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    except Exception:
        pass
    return None


def worker_count(jobs, biggest_save, asked=None):
    """
    How many saves to read at once.

    Three things bound it. The machine's cores, minus one so the rest of the
    computer stays usable. The number of saves actually left to read, since a
    worker with nothing to do is pure startup cost. And memory: a worker holds
    its whole save as text plus what it builds out of it, which measures at
    roughly three times the file, so on a small machine that is the real
    ceiling -- six workers on eight free gigabytes, whatever the core count
    says. Only 60% of what is free is spent, because the report still has to be
    built afterwards.

    Measured on 38 saves and 32 logical cores: 63s on one, 13s on eight, 8.5s
    on sixteen, 7.3s on twenty-four. It keeps paying past the physical core
    count, just less, and flattens out rather than turning back, so there is no
    ceiling here beyond what the machine itself imposes.
    """
    if asked:
        return max(1, min(asked, jobs))
    cores = max(1, (os.cpu_count() or 1) - 1)
    room = jobs
    spare = _spare_memory()
    if spare:
        room = max(1, int(spare * 0.6) // max(biggest_save * 3, 1))
    return max(1, min(cores, jobs, room))


def parse_saves(files, verbose=True, use_cache=True, reading=PLAIN,
                jobs=None):
    """
    Every save in the folder, read in parallel when that is worth doing.

    Cached saves are loaded here rather than in a worker: it costs a few
    milliseconds each and a process started to do it would cost more than it
    saves. Only what is left over is worth spreading out.
    """
    fingerprint = _parser_fingerprint() if use_cache else ""
    world = reading.fingerprint()
    slots = [_cache_slot(p, fingerprint, world) if fingerprint else None
             for p in files]

    out = [None] * len(files)
    todo = []
    done = 0
    _tell_progress(0, len(files))
    for i, path in enumerate(files):
        _stop_if_asked()
        held = _cache_read(slots[i])
        if held is not None:
            out[i] = held
            done += 1
            _tell_progress(done, len(files))
            if verbose:
                print(f"  {os.path.basename(path)} ... cached, "
                      f"{held[0].get('date', '?')}")
        else:
            todo.append(i)

    if not todo:
        return [item for item in out if item is not None]

    biggest = max((os.path.getsize(files[i]) for i in todo), default=0)
    workers = worker_count(len(todo), biggest, jobs)
    if workers > 1:
        try:
            return _parse_parallel(files, out, todo, slots, workers, verbose,
                                   reading, already=done)
        except Cancelled:
            raise                     # asked to stop, not a machine that cannot
        except Exception as exc:
            # A machine that will not start workers still has to read its saves.
            print(f"  reading one at a time ({exc})", file=sys.stderr)

    for i in todo:
        _stop_if_asked()
        try:
            meta, nations = analyze_save(files[i], verbose=verbose)
        except (ValueError, OSError) as exc:
            print(f"  skipped {os.path.basename(files[i])}: {exc}",
                  file=sys.stderr)
            continue
        _cache_write(slots[i], meta, nations)
        out[i] = (meta, nations)
        done += 1
        _tell_progress(done, len(files))
    return [item for item in out if item is not None]


DATE_IN_HEAD = re.compile(rb'date\s*=\s*"([\d.]+)"')


def date_of(path):
    """A save's in-game date, off the front of the file, without parsing it."""
    try:
        with open(path, "rb") as fh:
            found = DATE_IN_HEAD.search(fh.read(4096))
    except OSError:
        return ""
    return found.group(1).decode("ascii") if found else ""


def in_date_order(files):
    """
    The saves sorted by the date inside them, read from their first line.

    Worth the 4 KB a save: the campaign has to be walked oldest first -- war
    histories fold that way -- and knowing the order up front is what lets
    saves be handed over one at a time instead of collected and sorted.
    """
    return sorted(files, key=lambda p: (save_sort_key(p, date_of(p)), p))








def parse_saves_stream(files, verbose=True, use_cache=True, reading=PLAIN,
                       jobs=None, window=None, transform=None):
    """
    Every save, handed over one at a time, in the order given.

    `parse_saves` collects the whole campaign before the caller sees any of
    it. On a century of monthly autosaves that is four gigabytes of parsed
    saves alive at once, which is what has been running the analyzer out of
    memory -- not because anything needs them all together, but because
    nothing was given the chance to say it did not.

    At most `window` saves are in flight. The pool is fed as the caller
    consumes rather than racing ahead and stacking finished results in the
    parent, so a campaign of seven hundred saves costs what one of twenty
    does. Cached saves are read one at a time for the same reason.
    """
    from concurrent.futures import ProcessPoolExecutor
    fingerprint = _parser_fingerprint() if use_cache else ""
    world = reading.fingerprint()
    slots = [_cache_slot(p, fingerprint, world) if fingerprint else None
             for p in files]
    ready = [bool(sl) and os.path.exists(sl) for sl in slots]
    todo = [i for i, got in enumerate(ready) if not got]
    total = len(files)
    _tell_progress(0, total)

    # Which saves are worth handing to a worker. Normally only the ones that
    # have to be parsed: sending a cached save away and back is two extra
    # pickles for nothing. With `transform` set it is every save, because the
    # worker then hands back a third less than it read and the caller has one
    # less job per save to do -- and on a warm run that is the difference
    # between one core reading a hundred cache entries and all of them.
    pooled = list(range(len(files))) if transform is not None else todo
    biggest = max((os.path.getsize(files[i]) for i in pooled), default=0)
    workers = worker_count(len(pooled), biggest, jobs) if pooled else 1
    window = window or max(2, workers * 2)
    if verbose and todo:
        print(f"Reading {len(todo)} save(s) on {workers} cores.")

    pool = None
    if workers > 1:
        try:
            pool = ProcessPoolExecutor(
                max_workers=workers, initializer=_worker_setup,
                initargs=(reading, transform))
        except Exception as exc:
            print(f"  reading one at a time ({exc})", file=sys.stderr)

    futures = {}
    waiting = list(pooled)
    done = 0
    try:
        for i, path in enumerate(files):
            _stop_if_asked()
            # Keep the workers fed, but never further ahead than the window:
            # a finished result the caller has not asked for yet is memory
            # held for nothing.
            while pool is not None and waiting and len(futures) < window:
                nxt = waiting.pop(0)
                try:
                    futures[nxt] = pool.submit(
                        _worker_parse,
                        (nxt, files[nxt], slots[nxt], ready[nxt]))
                except Exception as exc:
                    # A pool only really starts its workers on the first
                    # submit, so a machine that cannot start them fails
                    # here and not at the constructor above. It is worth
                    # catching: every save can still be read one at a
                    # time, and the alternative is a stack trace out of
                    # the depths of multiprocessing for something the
                    # program can simply work around.
                    #
                    # Seen for real with a long TMPDIR. Python 3.14 starts
                    # workers through a forkserver, whose socket lives in
                    # the temp folder, and an AF_UNIX path is limited to
                    # 108 bytes -- so a deep enough temp folder took the
                    # whole run down.
                    print(f"  reading one at a time ({exc})",
                          file=sys.stderr)
                    waiting.insert(0, nxt)
                    pool.shutdown(wait=False, cancel_futures=True)
                    pool = None
                    # Anything already accepted belongs to a pool that is
                    # now gone, so those saves are read here instead.
                    futures.clear()
                    break

            got = None
            if i in futures:
                # A file the reader refuses -- a zip, a binary save, half a
                # file, something that is not a save at all with a .v2 on the
                # end -- raises here, in the worker, and used to take the
                # whole run down with a stack trace. One stray file in the
                # saves folder is an ordinary thing to have; the serial path
                # below has always skipped it by name, and so does this.
                try:
                    _index, _slot, meta, nations = futures.pop(i).result()
                except (ValueError, OSError) as exc:
                    print(f"  skipped {os.path.basename(path)}: {exc}",
                          file=sys.stderr)
                    continue
                got = (meta, nations)      # cached and finished in the worker
                if verbose:
                    print(f"  [{done + 1}/{total}] {os.path.basename(path)} "
                          f"... {meta['date']}")
            elif ready[i]:
                got = _cache_read(slots[i])
                if got is not None:
                    if transform is not None:
                        got = transform(got[0], got[1])
                    if verbose:
                        print(f"  {os.path.basename(path)} ... cached, "
                              f"{got[0].get('date', '?')}")
            if got is None:
                # No cache, no worker: either the pool never started or the
                # cached copy turned out to be unreadable. Whatever route a
                # save came by, it leaves here in the same state, so the
                # caller never has to ask which one it was.
                try:
                    got = analyze_save(path, verbose=verbose)
                except (ValueError, OSError) as exc:
                    print(f"  skipped {os.path.basename(path)}: {exc}",
                          file=sys.stderr)
                    continue
                _cache_write(slots[i], got[0], got[1])
                if transform is not None:
                    got = transform(got[0], dict(got[1]))
            done += 1
            _tell_progress(done, total)
            yield got
    finally:
        for future in futures.values():
            future.cancel()
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)


def _parse_parallel(files, out, todo, slots, workers, verbose, reading,
                    already=0):
    """
    Read the outstanding saves across several processes.

    Work is submitted one future per save rather than handed to `pool.map`, so
    a cancellation can drop everything that has not started yet. `map` gives no
    handle on the queue, and leaving the pool's context manager would then wait
    politely for all of it -- on a folder of hundreds of saves, a Stop button
    that takes ten minutes to stop.
    """
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    if verbose:
        print(f"Reading {len(todo)} save(s) on {workers} cores.")
    done = 0
    pool = ProcessPoolExecutor(max_workers=workers, initializer=_worker_setup,
                               initargs=(reading,))
    try:
        # `todo` is the saves with no cache entry, so none of these is
        # cached, and no finishing was asked of this pool.
        pending = {pool.submit(_worker_parse, (i, files[i], slots[i], False))
                   for i in todo}
        while pending:
            _stop_if_asked()
            # A short wait rather than a blocking one, so the Stop button is
            # answered while the workers are busy rather than after.
            ready, pending = wait(pending, timeout=0.25,
                                  return_when=FIRST_COMPLETED)
            for future in ready:
                # Same refusal, same answer as the streaming path: a file
                # the reader will not take is named and left out, not raised
                # over the whole campaign.
                try:
                    index, _slot, meta, nations = future.result()
                except (ValueError, OSError) as exc:
                    print(f"  skipped a save: {exc}", file=sys.stderr)
                    done += 1
                    continue
                out[index] = (meta, nations)   # cached in the worker
                done += 1
                _tell_progress(already + done, len(files))
                if verbose:
                    print(f"  [{done}/{len(todo)}] "
                          f"{os.path.basename(files[index])} ... {meta['date']}")
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()
    return [item for item in out if item is not None]


def save_sort_key(path, meta_date):
    """Sort by in-game date when we have it, filename otherwise."""
    parts = meta_date.split(".")
    try:
        return (0, int(parts[0]), int(parts[1]), int(parts[2]))
    except (IndexError, ValueError):
        return (1, 0, 0, 0)


def brigade_cap(nat, defines, pop_per_regiment=POP_SIZE_PER_REGIMENT):
    """
    How many standing brigades a nation's soldier pops could support.

    Measured on purpose-built test beds rather than fitted, the same way the
    mobilization ceiling was. Two of them, 72 provinces each, every province
    given one soldier pop of a known size across sizes either side of every
    step, and every brigade the game would allow raised from each. The second
    bed was needed because IGoR sets its non-core multiplier to 1, which cannot
    show whether a multiplier gates anything; Modus Omnino Demens carries
    vanilla's 3, 5 and 8. All 144 cells agreed with:

        nothing                              below POP_MIN_SIZE_FOR_REGIMENT
        1 + size // (POP_SIZE_PER_REGIMENT * multiplier)   at or above it

    Two things about that are worth stating because they are not what the
    define names suggest. The minimum is a *gate* and never a deduction: a pop
    of exactly 1000 raises one brigade and a pop of 3000 raises two, where
    subtracting the minimum first would have given one. And the multipliers
    scale the step, not the gate -- a colonial pop of 1000 still raises a
    brigade, though three times the minimum would have denied it one.

    Culture does not enter into it. Pops of a culture the nation does not
    accept were measured raising exactly as many brigades as accepted ones, at
    all eighteen sizes.

    A colony is charged its own multiplier and not the colonial and non-core
    ones compounded: on the mod where those are 5 and 3, a colonial pop steps
    every 15000 rather than every 45000. `is_colonial=1` is the protectorate
    the defines name, stepping every 24000 where its multiplier is 8. The
    province's own `colonial=` is what the engine charges against, which is why
    it is read in preference to the state's.

    Real campaigns cannot be used to check this: a regiment is not disbanded
    when its pop shrinks, so counts read out of a played save describe the
    pop's history rather than its capacity.
    """
    floor = int(defines.get("POP_MIN_SIZE_FOR_REGIMENT") or 1000)
    colony = float(defines.get("POP_MIN_SIZE_FOR_REGIMENT_COLONY_MULTIPLIER") or 1)
    noncore = float(defines.get("POP_MIN_SIZE_FOR_REGIMENT_NONCORE_MULTIPLIER") or 1)
    protect = float(
        defines.get("POP_MIN_SIZE_FOR_REGIMENT_PROTECTORATE_MULTIPLIER") or 1)
    colonial = nat["colonial_provinces"]
    levels = nat["colonial_level"]
    own = nat["province_colonial"]
    cored = nat["core_provinces"]

    total = 0
    for pid, sizes in nat["soldier_pops_at"].items():
        # The province's own flag first, then the state's, since it is the
        # province the multiplier is charged against.
        level = own.get(pid) or (levels.get(pid, 2) if pid in colonial else 0)
        if level:
            mult = protect if level == 1 else colony
        elif pid not in cored:
            mult = noncore
        else:
            mult = 1.0
        step = pop_per_regiment * mult
        for size in sizes:
            if size >= floor:
                total += 1 + int(size // step)
    return total


def finalize(nat, rate=1.0, pop_per_regiment=POP_SIZE_PER_REGIMENT,
             mob_types=MOBILIZABLE_TYPES, include_occupied=False, mod=None,
             world=None):
    """Derive the ratios that need the totals first."""
    total = nat["total_pop"]
    accepted_set = accepted_cultures_of(nat)
    primary = nat["primary_culture"]

    accepted_pop = sum(
        size for cul, size in nat["pop_by_culture"].items() if cul in accepted_set
    )
    primary_pop = nat["pop_by_culture"].get(primary, 0)

    buckets, pool_stated, entries = mobilization_clusters(
        nat, mob_types, include_occupied)
    brigades = brigades_from_clusters(buckets, rate, pop_per_regiment)

    out = dict(nat)
    # A nation can stand above what its pops now support, because a brigade is
    # not disbanded when the pop that raised it shrinks. Reported as the larger
    # of the two: a cap under the standing army is not a cap the nation is held
    # to, it is only a statement that it cannot recruit any more, and every
    # reading of it -- headroom, total potential, the head-to-head -- wants the
    # number the nation can actually field.
    out["life_unmet_pct"] = round(100.0 * nat["life_unmet"] / total, 3) \
        if total else 0.0
    out["starving_pct"] = round(100.0 * nat["starving"] / total, 3) \
        if total else 0.0
    out["brigade_cap"] = max(
        brigade_cap(nat, (mod or {}).get("defines") or {}, pop_per_regiment),
        nat["regular_brigades"])
    out["mobilization_pool"] = pool_stated
    out["mobilization_pops"] = entries
    # A nation already mobilized has (some of) its ceiling standing in the army
    # or in the queue; only the remainder is still potential. This is what stops
    # mobilized brigades from being counted twice in "total potential".
    # `start_mobilization` limits a mobilization to
    #     floor(max(standing regiments, MIN_MOBILIZE_LIMIT) x (1 + impact))
    # where impact is the ruling party's war policy plus every national modifier
    # that moves mobilization_impact. The save stores the party as a 1-based
    # index into the engine's global party list, which `party_sequence` rebuilds,
    # and stores active event modifiers by name.
    #
    # Both halves are measured against China, whose army is small enough for the
    # cap to bind. 1890: 8 standing, a pro-military party, no modifiers, and the
    # game offers 8 x (1 + 3) = 32 of a 95-brigade ceiling. 1908: 6 standing, the
    # same policy but a communist government carrying totalitarianism_modifier at
    # -0.2, and the game's own tooltip reads "280.0%" and offers
    # floor(6 x 3.8) = 22 of a 1056-brigade ceiling.
    policy = ""
    cap = 0
    if mod:
        table = mod.get("party_sequence") or ()
        index = int(nat.get("ruling_party") or 0) - 1
        if 0 <= index < len(table):
            policy = table[index][3]
        impact = (mod.get("mob_impacts") or {}).get(policy)
        if impact is not None:
            # Event modifiers, which the save lists by name, plus triggered
            # ones, which it does not and which have to be judged from their
            # own triggers.
            from modrules import impact_for
            impact += impact_for(nat, mod, world)
            floor_ = int(to_float((mod.get("defines") or {}).get(
                "MIN_MOBILIZE_LIMIT", 3), 3))
            cap = int(max(nat["regular_brigades"], floor_) * (1.0 + impact))
    out["war_policy"] = policy
    out["mobilization_cap"] = cap
    # What the game will actually offer: the pop ceiling, held down by the cap.
    out["mobilization_available"] = min(brigades, cap) if cap else brigades
    # Ceiling minus what is already standing. For a nation that mobilized a
    # while ago this is pop GROWTH since it mobilized, not something the game
    # will let it raise -- Victoria 2 does not top up a mobilization.
    out["mobilization_remaining"] = max(
        0, brigades - nat["mobilized_brigades"] - nat["mobilizing"])
    # `rate` is the country's mobilisation size modifier, which the save does
    # not store, so it is a parameter.
    out["mobilization_brigades"] = brigades
    out["accepted_pop"] = accepted_pop
    out["primary_culture_pop"] = primary_pop
    out["accepted_pct"] = round(100.0 * accepted_pop / total, 2) if total else 0.0
    out["avg_literacy"] = round(nat["literacy_weighted"] / total, 5) if total else 0.0
    out["avg_consciousness"] = round(nat["con_weighted"] / total, 4) if total else 0.0
    out["avg_militancy"] = round(nat["mil_weighted"] / total, 4) if total else 0.0
    # Which pop types sit in which layer is the mod's business, not a
    # constant: GFM and Divergences of Darkness add poor-strata `serfs`, IGoR
    # and Ferrum Mare rich `bankers`. Counted against the vanilla list those
    # people simply vanished -- Ferrum Mare's LCT is 98% bankers and read as a
    # nation of two thousand.
    layers = (mod or {}).get("strata") or {}
    if layers:
        for stratum in STRATA:
            out[f"pop_{stratum}"] = sum(
                size for t, size in nat["pop_by_type"].items()
                if layers.get(t) == stratum)
    else:
        for stratum, types in STRATA.items():
            out[f"pop_{stratum}"] = sum(nat["pop_by_type"].get(t, 0) for t in types)
    # Soldiers in a colonial state support no brigade, so the soldier pops that
    # matter to an army are the ones in stated land. The share is taken against
    # the whole nation, colonies included: a soldier base of five million reads
    # differently under fifty million people than under two hundred.
    colonial = nat["colonial_provinces"]
    stated = sum(size for pid, size in nat["soldiers_at"].items()
                 if pid not in colonial)
    out["soldiers_noncolonial"] = stated
    out["soldiers_noncolonial_pct"] = (
        round(100.0 * stated / total, 3) if total else 0.0)
    # Literacy the same way. A colony's pops are counted in the national average
    # and drag it down without saying anything about the metropole -- Britain
    # reads one way with India in the figure and another without. This is the
    # same restriction the soldier measure above uses, so the two agree about
    # what "our own states" means.
    home_pop = sum(size for pid, size in nat["pop_at"].items()
                   if pid not in colonial)
    home_literate = sum(v for pid, v in nat["literacy_at"].items()
                        if pid not in colonial)
    out["avg_literacy_stated"] = (
        round(home_literate / home_pop, 5) if home_pop else 0.0)
    out["pop_noncolonial"] = home_pop
    return out


BASE_COLUMNS = [
    "date", "year", "tag", "is_player", "primary_culture", "civilized",
    "provinces", "states", "total_pop", "accepted_pop", "accepted_pct",
    "primary_culture_pop", "avg_literacy", "avg_literacy_stated",
    "pop_noncolonial", "avg_consciousness", "avg_militancy",
    "brigades", "regular_brigades", "mobilized_brigades", "mobilizing",
    "brigade_cap",
    "is_mobilized", "armies", "ships", "navies",
    "factory_count", "factory_levels", "ports", "naval_base_levels",
    "max_naval_base", "railroad_levels", "fort_levels",
    "mobilisation_size", "mobilization_pool", "mobilization_pops",
    "mobilization_brigades", "mobilization_cap",
    "mobilization_available", "mobilization_remaining", "war_policy",
    "techs", "army_techs", "navy_techs", "prestige", "infamy", "treasury", "tax_base", "research_points",
    "war_exhaustion", "plurality",
    "pop_poor", "pop_middle", "pop_rich",
    "soldiers_noncolonial", "soldiers_noncolonial_pct",
    "life_unmet", "life_unmet_pct", "starving", "starving_pct",
]


GOOD_CATEGORIES = {
    "military": ["ammunition", "small_arms", "artillery", "canned_food",
                 "barrels", "tanks", "aeroplanes"],
    "raw": ["cattle", "coal", "cotton", "dye", "fish", "fruit", "grain", "iron",
            "oil", "opium", "precious_metal", "rubber", "silk", "sulphur", "tea",
            "timber", "tobacco", "tropical_wood", "wool", "coffee"],
    "industrial": ["cement", "clipper_convoy", "electric_gear", "explosives",
                   "fabric", "fertilizer", "fuel", "glass", "lumber",
                   "machine_parts", "paper", "steamer_convoy", "steel"],
    "consumer": ["automobiles", "furniture", "liquor", "luxury_clothes",
                 "luxury_furniture", "radio", "regular_clothes", "telephones",
                 "wine"],
}
GOOD_CATEGORY = {g: cat for cat, goods in GOOD_CATEGORIES.items() for g in goods}




def merge_prices(parsed):
    """
    Stitch every save's rolling price buffer into one series.

    Buffers from consecutive saves overlap heavily; keyed on (date, good) the
    duplicates collapse, and the result is continuous monthly coverage from the
    earliest buffer to the last save.
    """
    prices = {}
    # Newest save first, and the first answer for a month is the one that
    # stands. Walked oldest first, every one of the hundred and twenty
    # thousand entries a campaign has had to be weighed against which save
    # had written it -- a second dictionary the same size as the first, and
    # a lookup in it per entry -- to settle that a later save's buffer is
    # the more settled record. Coming the other way the question does not
    # arise: whatever is already there was written by a later save.
    for meta, _ in reversed(parsed):
        market = meta.get("market")
        if not market:
            continue
        # The save's own date carries the live price, which its monthly
        # buffer has not recorded yet -- so it goes in before this save's
        # own history, and after every later save's, which is exactly the
        # order it won in before.
        stamp = meta["date"]
        for good, price in market["current"].items():
            key = (stamp, good)
            if key not in prices:
                prices[key] = price
        for stamp, good, price in market["history"]:
            key = (stamp, good)
            if key not in prices:
                prices[key] = price

    rows = []
    for (stamp, good), price in prices.items():
        rows.append({
            "date": stamp,
            "year": stamp.split(".")[0],
            "good": good,
            "category": GOOD_CATEGORY.get(good, "other"),
            "price": round(price, 5),
        })
    rows.sort(key=lambda r: (date_key(r["date"]), r["good"]))
    return rows


def market_snapshot_rows(parsed):
    """Per-save supply/demand context, which the save only stores for `now`."""
    rows = []
    for meta, _ in parsed:
        market = meta.get("market")
        if not market:
            continue
        snap = market["snapshot"]
        goods = set(market["current"])
        for field in snap.values():
            goods |= set(field)
        for good in sorted(goods):
            rows.append({
                "date": meta["date"],
                "year": meta["date"].split(".")[0],
                "good": good,
                "category": GOOD_CATEGORY.get(good, "other"),
                "price": round(market["current"].get(good, 0.0), 5),
                "world_pool": round(snap["world_pool"].get(good, 0.0), 3),
                "supply": round(snap["supply"].get(good, 0.0), 3),
                "demand": round(snap["demand"].get(good, 0.0), 3),
                "real_demand": round(snap["real_demand"].get(good, 0.0), 3),
                "actual_sold": round(snap["actual_sold"].get(good, 0.0), 3),
                "discovered": int(snap["discovered"].get(good, 0.0) > 0),
            })
    return rows


def _write_csv(path, rows, columns):
    """One CSV, columns picked out of each row dict.

    This is what `csv.DictWriter` does, minus the per-row Python call: handing
    `writerows` a generator lets the C writer pull the rows itself, which is
    worth having when a campaign of monthly autosaves has a few million of them.
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        if rows and isinstance(rows[0], dict):
            writer.writerows([row.get(c, "") for c in columns] for row in rows)
        else:
            # already in column order -- see the row loop in `main`
            writer.writerows(rows)


def write_outputs(rows, ship_rows, pop_rows, culture_rows, price_rows,
                  snapshot_rows, brigade_rows, tech_rows, outdir,
                  pop_columns=None):
    os.makedirs(outdir, exist_ok=True)
    columns = (BASE_COLUMNS + [f"pop_{t}" for t in (pop_columns or POP_TYPE_LIST)]
               + ["accepted_cultures"])

    main_path = os.path.join(outdir, "nations_timeseries.csv")
    _write_csv(main_path, rows, columns)

    paths = [main_path]
    tables = [
        ("prices.csv", price_rows, ["date", "year", "good", "category", "price"]),
        ("market_snapshot.csv", snapshot_rows,
         ["date", "year", "good", "category", "price", "world_pool", "supply",
          "demand", "real_demand", "actual_sold", "discovered"]),
        ("ships_by_type.csv", ship_rows,
         ["date", "year", "tag", "ship_type", "count", "effective"]),
        ("brigades_by_type.csv", brigade_rows,
         ["date", "year", "tag", "regiment_type", "count"]),
        ("technologies.csv", tech_rows,
         ["date", "year", "tag", "technology", "branch", "line"]),
        ("pops_by_type.csv", pop_rows, ["date", "year", "tag", "pop_type", "size"]),
        ("pops_by_culture.csv", culture_rows,
         ["date", "year", "tag", "culture", "size", "accepted"]),
    ]
    for name, data, cols in tables:
        if not data:
            continue
        path = os.path.join(outdir, name)
        _write_csv(path, data, cols)
        paths.append(path)
    return paths


# A province block opens with its number; anything else opening at the left
# margin is not one. Both are anchored, because the game writes an
# ideology's entries at the left margin too and they must not be mistaken
# for the start of a block.
PROVINCE_HEAD = re.compile(r"^\d+=\s*$")
TOP_KEY = re.compile(r"^\w+=\s*$")


def verify_save(path):
    """
    Cross-check the counts against an independent brace-tracking scan.

    The analyzer walks structure; this counts `regiment` and `ship` blocks
    by raw nesting and attributes them to whichever top-level country block
    they fall in, and adds up every pop in every province by its owner. If
    the two disagree, the structured reader is missing a nesting the save
    actually uses.

    Population is worth the second walk because everything else is derived
    from it -- the accepted share, the literacy average, the mobilizable
    pool, the strata -- so a pop read wrong is a page of numbers read wrong,
    and nothing downstream could tell. It is counted by line rather than by
    token because the game writes an ideology's entries hard against the
    left margin, inside a pop, inside a province: anything that decides
    where it is by indentation gets that wrong, and quietly.
    """
    text = read_save_text(path)
    truth_reg, truth_ship = defaultdict(int), defaultdict(int)
    depth, current, pending = 0, None, None

    for match in TOKEN_RE.finditer(text):
        tok = match.group()
        if tok == "{":
            depth += 1
            if current:
                if pending == "regiment":
                    truth_reg[current] += 1
                elif pending == "ship":
                    truth_ship[current] += 1
            pending = None
        elif tok == "}":
            depth -= 1
            if depth == 0:
                current = None
        elif tok != "=":
            pending = tok
            if depth == 0 and looks_like_country_tag(unquote(tok)):
                current = unquote(tok)

    truth_pop = defaultdict(int)
    depth, in_province, owner = 0, False, None
    for line in text.split("\n"):
        line = line.rstrip("\r")
        bare = line.strip()
        if depth == 0:
            if PROVINCE_HEAD.match(line):
                in_province, owner = True, None
            elif TOP_KEY.match(line):
                in_province, owner = False, None
        if in_province and depth == 1 and bare.startswith("owner="):
            owner = unquote(bare.split("=", 1)[1].strip())
        elif in_province and depth == 2 and bare.startswith("size="):
            if owner:
                truth_pop[owner] += to_int(bare.split("=", 1)[1])
        depth += line.count("{") - line.count("}")

    _meta, nations = analyze_save(path, verbose=False)

    say = ["\n=== %s ===" % os.path.basename(path),
           f"{'tag':<6}{'brigades':>10}{'scan':>8}{'diff':>7}"
           f"{'ships':>10}{'scan':>8}{'diff':>7}"
           f"{'people':>14}{'scan':>14}"]
    mismatches = 0
    for tag in sorted(set(truth_reg) | set(truth_ship) | set(truth_pop)
                      | set(nations)):
        nat = nations.get(tag)
        if not nat:
            continue
        got_r, want_r = nat["brigades"], truth_reg.get(tag, 0)
        got_s, want_s = nat["ships"], truth_ship.get(tag, 0)
        got_p, want_p = nat["total_pop"], truth_pop.get(tag, 0)
        if got_r != want_r or got_s != want_s or got_p != want_p:
            mismatches += 1
            say.append(f"{tag:<6}{got_r:>10}{want_r:>8}{got_r - want_r:>7}"
                       f"{got_s:>10}{want_s:>8}{got_s - want_s:>7}"
                       f"{got_p:>14,}{want_p:>14,}")
    if mismatches:
        say.append("\n%d nations disagree. Please report this with the save."
                   % mismatches)
    else:
        total_r = sum(truth_reg.values())
        total_s = sum(truth_ship.values())
        total_p = sum(truth_pop.values())
        say.append(f"All nations agree: {total_r:,} regiments, "
                   f"{total_s:,} ships, {total_p:,} people.")
    say.append("")
    return "\n".join(say), mismatches


def verify_all(files, jobs=None):
    """
    Every save checked, on every core, printed in the order given.

    Each save is checked twice over -- once by the structured reader and
    once by a brace count over the whole file -- so this is the slowest
    thing here by a wide margin: 167 s for 103 saves on one core. They do
    not depend on each other, and the answers are collected rather than
    printed as they arrive, so the output is the same whichever finishes
    first.
    """
    from concurrent.futures import ProcessPoolExecutor
    workers = worker_count(len(files),
                           max((os.path.getsize(f) for f in files), default=0),
                           jobs)
    if workers <= 1 or len(files) < 2:
        for path in files:
            text, _bad = verify_save(path)
            print(text)
        return
    print("Checking %d save(s) on %d cores." % (len(files), workers))
    # `--verify` runs before a mod is chosen, so what it reads the saves
    # under is whatever the run has settled on by now. See `reading_now`.
    pool = ProcessPoolExecutor(
        max_workers=workers, initializer=_worker_setup,
        initargs=(reading_now(),))
    try:
        for text, _bad in pool.map(verify_save, files):
            print(text)
    finally:
        pool.shutdown()


def peek_save(path):
    """
    Print the shape of a save: top-level keys, and the keys inside the first
    province and country block. Useful when a mod moves things around and the
    numbers come out wrong or zero.
    """
    text = read_save_text(path)
    tok = Tokens(text)
    top_scalars, top_blocks = [], []
    first_province = first_country = None

    while True:
        t = tok.next()
        if t is None:
            break
        if t in ("}", "{", "="):
            continue
        nxt = tok.next()
        if nxt is None:
            break
        if nxt != "=":
            tok.push(nxt)
            continue
        val = tok.next()
        if val is None:
            break
        key = unquote(t)
        if val == "{":
            if key.isdigit() and first_province is None:
                first_province = (key, parse_block(tok))
            elif looks_like_country_tag(key) and first_country is None:
                first_country = (key, parse_block(tok))
            else:
                if key.isdigit():
                    top_blocks.append("<province>")
                elif looks_like_country_tag(key):
                    top_blocks.append("<country>")
                else:
                    top_blocks.append(key)
                skip_block(tok)
        else:
            top_scalars.append(f"{key}={unquote(val)[:40]}")

    print(f"\n=== {os.path.basename(path)} ===")
    print("\nTop-level scalars:")
    for item in top_scalars[:20]:
        print(f"  {item}")
    seen = []
    for name in top_blocks:
        if name not in seen:
            seen.append(name)
    print(f"\nTop-level blocks ({len(top_blocks)} total, distinct):")
    print("  " + ", ".join(seen[:40]))

    for label, found in (("province", first_province), ("country", first_country)):
        if not found:
            print(f"\nNo {label} block found -- the analyzer will report zeros.")
            continue
        key, block = found
        print(f"\nFirst {label} block ({key}) keys:")
        if isinstance(block, dict):
            for k, v in list(block.items())[:40]:
                kind = ("block" if isinstance(v, dict)
                        else "list" if isinstance(v, list) else "scalar")
                extra = ""
                if label == "province" and k in POP_TYPES:
                    pops = v if isinstance(v, list) else [v]
                    culture, religion = pop_culture(pops[0]) if isinstance(pops[0], dict) else (None, None)
                    extra = f"  <- pop, culture={culture}, religion={religion}"
                print(f"  {k:<24} {kind}{extra}")
    print()



def campaign_rows(parsed, mod, args, wanted=None):
    """
    One campaign's saves as finalized rows: (date, tag, nation).

    The same finishing the single-campaign path runs -- the same function
    against a spec from the same builder -- so a measure means here exactly
    what it means on the report's own charts.

    It said that before and was not doing it. Building the cross block out
    of fields read off the raw parse would have been an obviously different
    definition of every number; a second copy of the recipe was a quietly
    different one, and by the time the two were read side by side it had
    drifted in five places.
    """
    from mod_reader import attainable_inventions, index_base_for

    every, all_techs = [], {}
    for _meta, nations in parsed:
        for tag, nat in nations.items():
            every.append(nat)
            all_techs.setdefault(tag, set()).update(nat["tech_list"])
    live = attainable_inventions(mod, all_techs) if mod else None
    if mod is not None:
        mod["index_base"] = index_base_for(mod, every)

    spec = finish_spec(args, mod, live, wanted)
    out = []
    for meta, nations in parsed:
        for tag, done in finish_nations(meta, nations, spec).items():
            if kept_by(spec, tag, done):
                out.append((meta["date"], tag, done))
    return out


def run_cross(parent, game_root, args, verbose=True):
    """
    Read every campaign under `parent`, each under its own mod.

    Returns (cross payload, the largest campaign's files, its mod path). The
    largest campaign becomes the subject of the ordinary report, so the
    cross-campaign block is an addition rather than a replacement.

    The globals the parser keeps are reset between campaigns for the same reason
    `main` resets them between runs: a set that only grew would carry one mod's
    pop types into the next campaign's saves, which have none.
    """
    import cross as crossmod
    from mod_reader import load_mod, name_for

    # Told, rather than worked out: `--campaign-mod NAME=PATH` settles one
    # campaign each. Two mods built on the same base can agree on their
    # countries, their technologies and their whole invention array, so the
    # search is a good guess and nothing more -- being told beats it every time.
    chosen = {}
    for pair in getattr(args, "campaign_mod", None) or []:
        name, _sep, path = pair.partition("=")
        if not _sep or not name.strip():
            sys.exit("--campaign-mod wants NAME=PATH, as in "
                     '--campaign-mod "NeoMgame=C:\\...\\mod\\IGoR_puir 13.0.5". '
                     "Got: %r" % pair)
        path = os.path.expanduser(os.path.expandvars(path.strip()))
        if not os.path.isdir(os.path.join(path, "common")):
            sys.exit("--campaign-mod %s: %s has no common/ inside it, so it is "
                     "not a mod folder." % (name.strip(), path))
        chosen[name.strip().lower()] = path

    # Naming a mod is an answer, not a hint. Campaigns played on the same mod
    # are the ordinary case, and being told which one is better evidence than
    # anything that can be inferred, so the search is skipped entirely.
    if args.mod_path:
        label = os.path.basename(os.path.normpath(args.mod_path))
        survey = []
        for name, path, files in crossmod.campaigns_in(parent):
            # One mod for all of them is the general instruction; a campaign
            # named outright is the particular one, and the particular wins.
            # They used to be read in the other order, so `--campaign-mod`
            # went unread whenever `--mod-path` was there beside it.
            told = chosen.get(name.lower())
            survey.append({
                "name": name, "path": path, "files": files,
                "mod_label": os.path.basename(os.path.normpath(told))
                             if told else label,
                "mod_path": told or args.mod_path,
                "candidates": [], "told": bool(told)})
        if verbose:
            odd = sum(1 for e in survey if e.get("told"))
            print("Campaigns found under %s, read under %s%s:"
                  % (parent, label,
                     "" if not odd else " except where named"))
            for entry in survey:
                print("  %-22s %3d saves%s"
                      % (entry["name"], len(entry["files"]),
                         "  ->  %s   (as told)" % entry["mod_label"]
                         if entry.get("told") else ""))
    elif not game_root and not chosen:
        sys.exit("--cross needs --game-root (the Victoria 2 install folder, the "
                 "one with mod/ inside) to work each campaign's mod out, "
                 "--mod-path to read them all under one mod, or "
                 "--campaign-mod to name them one at a time.")
    else:
        # Every campaign named outright is settled before anything is searched
        # for; only the rest go through `survey`, and if none are left the
        # search does not run at all.
        found = crossmod.campaigns_in(parent)
        unsettled = [e for e in found if e[0].lower() not in chosen]
        survey = crossmod.survey(parent, game_root) if (unsettled and game_root) \
            else [{"name": n, "path": p, "files": f, "mod_label": None,
                   "mod_path": None, "candidates": []} for n, p, f in found]
        for entry in survey:
            override = chosen.get(entry["name"].lower())
            if override:
                entry["mod_path"] = override
                entry["mod_label"] = os.path.basename(os.path.normpath(override))
                entry["candidates"] = []
                entry["told"] = True
        if verbose:
            print("Campaigns found under %s:" % parent)
            for entry in survey:
                fits = sum(1 for _l, v, _d in entry["candidates"] if v == "fits")
                print("  %-22s %3d saves  ->  %s%s"
                      % (entry["name"], len(entry["files"]),
                         entry["mod_label"] or "no mod in that folder fits",
                         "   (as told)" if entry.get("told") else ""))
                if entry.get("told"):
                    continue
                nearest = [r for r in entry["candidates"] if r[1] == "nearest"]
                if nearest:
                    print("      WARNING: nothing in %s explains these saves. "
                          "The closest is %s, and it does not match: %s. The "
                          "numbers below are computed against a mod this "
                          "campaign was not played on -- name the right one "
                          "with --mod-path."
                          % (game_root, nearest[0][0], nearest[0][2]))
                elif fits > 1:
                    print("      note: %d mods fit these saves; picked the one "
                            "the campaign leaves least of unused. Name it with "
                            "--mod-path, or in the window pick the mod itself "
                            "instead of the folder, to settle it." % fits)
                elif not entry["mod_label"]:
                    print("      note: nothing in %s explains these saves. If "
                          "the mod is installed elsewhere, point the mod box "
                          "at it directly." % game_root)
    if verbose:
        for entry in survey:
            for stray, worst, of in crossmod.history_breaks(entry["files"]):
                print("      note: %s disagrees with all %d later saves by at "
                      "least %d event flags; it may be from another game"
                      % (stray, of, worst))

    results, names, primary = [], {}, None
    for entry in survey:
        if not entry["mod_path"]:
            if verbose:
                print("  skipping %s: no mod in %s explains its saves"
                      % (entry["name"], game_root))
            continue
        mod = load_mod(entry["mod_path"])
        # The defaults `main` applies, applied here too. The mod's list used
        # to be taken unconditionally, so `--mob-types` was read on a
        # single-campaign run and ignored on a cross one; and it was taken
        # for the parse while the finishing below went on reading the command
        # line's, which is two different lists deciding one number.
        #
        # Only the pop list is wanted here, because only the parse happens
        # here. The regiment size is read from the same function further
        # down, where `campaign_rows` builds the spec that finishes the save.
        _regiment_size, mob_types = mod_defaults(args, mod)
        # One object for how this campaign's saves are read: it sets the
        # globals and it is the cache key, so the key cannot describe a state
        # the parse is not in. The three globals used to be cleared, set,
        # and then read back out again to make the key.
        reading = reading_for(entry["mod_path"], mod, mob_types)
        reading.apply()
        if verbose:
            print("Reading %s (%d saves) under %s"
                  % (entry["name"], len(entry["files"]), entry["mod_label"]))
        parsed = parse_saves(entry["files"], verbose=False,
                             use_cache=not args.no_cache, reading=reading,
                             jobs=args.jobs)
        if not parsed:
            continue
        parsed.sort(key=lambda p: save_sort_key(p[0]["file"], p[0]["date"]))
        results.append((entry["name"], entry["mod_label"],
                        campaign_rows(parsed, mod, args,
                                      set(args.tags) if args.tags else None)))
        # Nation names come from whichever mod names them: a tag any mod names
        # is better than the bare tag, and where two mods share a tag they were
        # measured to agree on it. Country names live in the localisation, not
        # in `display_names`, which is goods and unit types.
        loc = mod.get("localisation") or {}
        for _meta, nations in parsed:
            for tag, nat in nations.items():
                if tag not in names:
                    label = name_for(tag, str(nat.get("government") or ""), loc)
                    if label and label != tag:
                        names[tag] = label
        # The report around the cross-campaign block has to be about one
        # campaign. Whichever the caller named, else the one with most saves.
        if args.primary:
            if entry["name"].lower() == args.primary.lower():
                primary = entry
        elif primary is None or len(entry["files"]) > len(primary["files"]):
            primary = entry

    if args.primary and primary is None and results:
        known = ", ".join(name for name, _m, _p in results)
        sys.exit("No campaign called %r under %s. There is: %s"
                 % (args.primary, parent, known))
    if not results or primary is None:
        return None, [], args.mod_path
    payload = crossmod.series_payload(results, names=names)
    if verbose:
        print("Cross-campaign: %d campaigns, %d nations in two or more of them."
              % (len(payload["campaigns"]), len(payload["tags"])))
        print("The rest of the report is %s%s."
              % (primary["name"],
                 "" if args.primary else " (the most saves; --primary picks "
                                         "another)"))
    return payload, primary["files"], primary["mod_path"]


# What one walk of a campaign produces, and what it was allowed to keep.
# Named shapes because `main` carried all of this as loose locals, and every
# one had to be handed by name to the things downstream that read it.
Campaign = namedtuple(
    "Campaign", "rows ship_rows pop_rows culture_rows brigade_rows "
                "tech_rows naval_profiles naval_of supply parsed war_book "
                "pop_columns")

# Which of a save's fields survive it. `whole` keeps the save entire,
# `fields` is what the trim keeps when it does not. See `keep_whole` in
# `main` for who asks. Whether the raw mobilizable pops survive is the
# finishing's business and travels in the spec, because the finishing is
# what spends them.
Keep = namedtuple("Keep", "whole fields")


def walk_campaign(stream, spec, finished, keep):
    """
    Read the campaign once, oldest save first, spending each save as it
    passes.

    Every save gives up its rows, folds its wars into the book and is then
    cut down to the handful of fields the rest of the run still asks for,
    so what is alive at any moment is one save rather than the campaign.
    `parsed` holds only those remains.

    Lifted out of `main` unchanged: it was a hundred and ten lines in the
    middle of an eight-hundred-line function, holding a dozen accumulators
    that nothing above it touched and everything below it read.

    `finished` says the stream already ran `finish_nations` out in the
    workers. When it did not -- the two diagnostics keep their saves whole,
    and finishing is what spends the tables they want to print -- it runs
    here instead, the same function against the same spec. This loop used to
    hold its own filter and its own call to a parent-side twin of the
    worker's, and the comment promising they matched was the only thing
    holding them together.
    """
    rows, ship_rows, pop_rows, culture_rows = [], [], [], []
    brigade_rows, tech_rows = [], []
    # Ship stats as each nation's own inventions leave them. Nations that
    # researched the same things have the same ships, so the profiles are kept
    # once each and referred to by number rather than repeated per save.
    # The pop types a row has a column for. Frozen at import it was the
    # vanilla twelve, so a mod's own type -- IGoR's bankers, GFM's serfs --
    # was read out of the save, counted into the totals and then dropped on
    # the way to the table.
    pop_columns = sorted(v2parse.POP_TYPES)
    naval_profiles, naval_index, naval_of = [], {}, {}
    # good -> {date: {tag: what it put on the market}}, for the production view.
    supply_by = {}

    # The campaign is walked once, oldest save first. Each save is read, spends
    # its rows, gives up its wars and is then cut down to the few fields the
    # report still wants -- so what is alive at any moment is one save, not the
    # campaign. `parsed` below holds only those remains.
    from report import fold_wars
    parsed = []
    war_book = {"wars": {}, "order": []}

    for meta, nations in stream:
        _stop_if_asked()
        date = meta["date"]
        year = date.split(".")[0] if date else ""
        if not finished:
            # Only the diagnostics reach this now. They asked for the
            # per-province tables to be kept, and finishing is what spends
            # them, so it waits for the parent.
            nations = finish_nations(meta, nations, spec)
        for tag, done in nations.items():
            # The same question the finishing asked, asked of the same spec,
            # so a nation finished out in a worker and a nation finished just
            # above are kept or dropped by one rule.
            if not kept_by(spec, tag, done):
                continue
            accepted_set = set(done["accepted_cultures"]) | {done["primary_culture"]}

            row = {
                "date": date,
                "year": year,
                "tag": tag,
                "is_player": int(done["is_player"]),
                "accepted_cultures": ";".join(sorted(done["accepted_cultures"])),
            }
            for col in BASE_COLUMNS:
                if col in done:
                    row[col] = done[col]
            for ptype in pop_columns:
                row[f"pop_{ptype}"] = done["pop_by_type"].get(ptype, 0)
            rows.append(row)

            # These four tables are the ones a campaign has millions of rows
            # of -- a hundred technologies per nation per save on its own -- so
            # they are tuples in the column order declared in `write_outputs`
            # rather than dicts. A dict per row costs about twice the memory
            # and names the same six columns over and over.
            for stype, count in sorted(done["ships_by_type"].items()):
                ship_rows.append((date, year, tag, stype, count,
                                  round(done["ship_crew"].get(stype, count), 3)))
            if spec.mod is not None and done["ships"]:
                from mod_reader import naval_profile
                profile = naval_profile(done, spec.mod)
                key = json.dumps(profile, sort_keys=True)
                if key not in naval_index:
                    naval_index[key] = len(naval_profiles)
                    naval_profiles.append(profile)
                naval_of.setdefault(tag, {})[date] = naval_index[key]
            for good, amount in done["goods_supply"].items():
                supply_by.setdefault(good, {}).setdefault(date, {})[tag] = amount
            for rtype, count in sorted(done["regiments_by_type"].items()):
                brigade_rows.append((date, year, tag, rtype, count))
            for tech in sorted(done["tech_list"]):
                branch, line, _pos = TECH_GROUP.get(tech, ("other", "Other", 0))
                tech_rows.append((date, year, tag, tech, branch, line))
            for ptype, size in sorted(done["pop_by_type"].items()):
                pop_rows.append((date, year, tag, ptype, size))
            for culture, size in sorted(done["pop_by_culture"].items(),
                                        key=lambda kv: -kv[1]):
                culture_rows.append((date, year, tag, culture, size,
                                     int(culture in accepted_set)))

        # This save's wars, folded in as it passes. The book wants them oldest
        # first, which is the order the stream is in, so folding here costs
        # nothing and means no save has to keep its own copy.
        fold_wars(war_book, meta.get("wars", ()))
        meta["wars"] = ()
        # `--explain-mob-pool` prints a nation's raw pool back, so that one
        # caller keeps the save whole.
        parsed.append((meta, nations) if keep.whole
                      else trim_save(meta, nations, keep.fields))

    return Campaign(rows=rows, ship_rows=ship_rows, pop_rows=pop_rows,
                    culture_rows=culture_rows, brigade_rows=brigade_rows,
                    tech_rows=tech_rows, naval_profiles=naval_profiles,
                    naval_of=naval_of, supply=supply_by, parsed=parsed,
                    war_book=war_book, pop_columns=pop_columns)


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


def build_html(args, mod, campaign, price_rows, snapshot_rows,
               cross_payload, tables):
    """
    The report page, or None when `--no-html` said not to build one.

    Everything here is the page and only the page: the names the mod
    gives nations, the province bitmap behind the map tab, the flags the
    great-power and battle tables fly. None of it is needed by a run that
    is writing tables alone, which is why it is no longer a hundred lines
    in the middle of `main`.

    `tables` is the CSV writer already waiting on a thread. It is handed
    over so `build_report` can start it at the one moment in the run when
    the interpreter lock is free, and it is drained here if the report
    throws, so a half-written CSV is not left behind a stack trace.
    """
    rows, ship_rows, pop_rows = (campaign.rows, campaign.ship_rows,
                                 campaign.pop_rows)
    culture_rows, brigade_rows = campaign.culture_rows, campaign.brigade_rows
    tech_rows, parsed = campaign.tech_rows, campaign.parsed
    naval_profiles, naval_of = campaign.naval_profiles, campaign.naval_of
    supply_by, war_book = campaign.supply, campaign.war_book

    html_path = None
    if not args.no_html:
        from report import (build_map, build_report, build_succession,
                            build_wars)
        # Country names come from the mod's own localisation, which is where the
        # game gets them: a bare TAG, overridden by TAG_<government> when one
        # exists -- IGoR's PBC is "Peru-Bolivia" but "Andine Federation" while
        # it is a democracy. Saves are walked in order so the name reflects the
        # government the nation ended the series with. Without --mod-path there
        # is nothing to read and tags stand in for names.
        report_names = {}
        if mod is not None and mod.get("localisation"):
            from mod_reader import name_for
            loc = mod["localisation"]
            for _meta, _nations in parsed:
                for _tag, _nat in _nations.items():
                    report_names[_tag] = name_for(
                        _tag, str(_nat.get("government") or ""), loc)
        # The map needs the mod's province bitmap; without --mod-path the tab
        # is dropped rather than shown empty.
        map_data = build_map(mod, parsed, args.map_scale) if mod else None
        if map_data and map_data.get("derived") and not args.quiet:
            print(f"map/positions.txt anchors no army counter for "
                  f"{map_data['derived']} of the provinces holding troops; "
                  f"those markers sit at the middle of the province instead.")
        # The save ranks the great powers itself, as 1-based indices into the
        # country array common/countries.txt defines, so the mod is needed to
        # turn them back into tags.
        order = (mod or {}).get("country_order") or []
        great_powers = {}
        flags = {}
        if order:
            from mod_reader import (flag_images, flag_suffixes,
                                    government_flag_types)
            styles = government_flag_types(mod["path"])
            for meta_i, nations_i in parsed:
                picks = [order[i - 1] for i in meta_i.get("great_nations", ())
                         if 0 < i <= len(order)]
                if not picks:
                    continue
                row = []
                for tag in picks:
                    gov = str((nations_i.get(tag) or {}).get("government") or "")
                    # One flag per tag and flag variant, so a nation that turns
                    # communist mid-campaign flies both in turn without the
                    # image being stored twice. The suffix that will actually be
                    # used is the discriminator, since two governments can share
                    # a flagType and still fly different flags.
                    key = tag + "|" + (flag_suffixes(gov, styles)[0] or "base")
                    if key not in flags:
                        got = flag_images(mod["path"], [tag], {tag: gov})
                        if tag in got:
                            flags[key] = got[tag]
                    row.append([tag, key])
                great_powers[meta_i.get("date") or ""] = row
            # Battle tables name a lot of nations that never made great power,
            # and a flag beside the tag reads faster than a tag alone. These
            # take the plain national flag rather than a government variant.
            fighters = set()
            for war in war_book["wars"].values():
                fighters.update(war["attackers"])
                fighters.update(war["defenders"])
                for b in war["battles"].values():
                    for who in (b.get("attacker"), b.get("defender")):
                        if who and who.get("country"):
                            fighters.add(who["country"])
            for tag in sorted(t for t in fighters if t and t != "---"):
                if tag + "|" not in flags:
                    got = flag_images(mod["path"], [tag], {})
                    if tag in got:
                        flags[tag + "|"] = got[tag]
        try:
            html_path = build_report(
                rows, ship_rows, pop_rows, culture_rows, price_rows,
                snapshot_rows, brigade_rows, tech_rows, args.out,
                tag_names=report_names,
                map_data=map_data,
                base_prices=(mod or {}).get("base_prices"),
                great_powers=great_powers,
                flags=flags,
                cross=cross_payload,
                technology=(mod or {}).get("technology"),
                wars=build_wars(parsed, (mod or {}).get("province_names"),
                                (mod or {}).get("province_regions"),
                                (mod or {}).get("state_names"),
                                (mod or {}).get("unit_kinds"), book=war_book),
                succession=build_succession(parsed,
                                            (mod or {}).get("formations")),
                culture_names=(mod or {}).get("culture_names"),
                display_names=(mod or {}).get("display_names"),
                naval={"profiles": naval_profiles, "of": naval_of,
                       "exact": (mod or {}).get("index_base") is not None}
                      if naval_profiles else None,
                supply=supply_by,
                # One number a save rather than one a nation, so it is
                # gathered here from the metas rather than from the rows.
                world_pop={m["date"]: m.get("world_pop", 0)
                           for m, _n in parsed if m.get("date")},
                split=args.split,
                alongside=tables.start,
            )
        except BaseException:
            # They may already be being written on a thread nobody is now
            # going to wait for. Let it finish before the failure goes up,
            # so a half-written CSV is not left behind a stack trace.
            try:
                tables.result()
            except BaseException:                        # noqa: BLE001
                pass
            raise
    return html_path


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
    ap.add_argument("--pop-per-regiment", type=_number(int, 1),
                    default=POP_SIZE_PER_REGIMENT,
                    help="POP_SIZE_PER_REGIMENT from defines.lua (default 3000)")
    ap.add_argument("--mob-types", nargs="*",
                    default=sorted(MOBILIZABLE_TYPES),
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


def main():
    args = command_line()

    saves_path = os.path.expanduser(os.path.expandvars(args.saves))
    if not os.path.exists(saves_path):
        sys.exit(
            f"Path not found: {saves_path}\n"
            f"If you used ~ in PowerShell, try $HOME instead, or give the full "
            f"path starting with C:\\Users\\..."
        )

    if os.path.isdir(saves_path):
        files = sorted(
            os.path.join(saves_path, f)
            for f in os.listdir(saves_path)
            if f.lower().endswith(".v2")
        )
        # With --cross the saves sit in subfolders, so a parent holding none of
        # its own is the ordinary case rather than a mistake.
        if not files and not args.cross:
            sys.exit(
                f"No .v2 files in {saves_path}\n"
                f"Point this at the folder that holds your saves, not at a "
                f"single save."
            )
    else:
        files = [saves_path]

    if not files and not args.cross:
        sys.exit(f"No .v2 saves found in {args.saves}")

    if args.peek:
        peek_save(files[0])
        return

    # Several campaigns at once. Each is read under the mod it was actually
    # played on, worked out from its own saves, and the results are kept side by
    # side. The heavy single-campaign report that follows is built from the
    # largest of them, so this adds a section rather than replacing anything.
    cross_payload = None
    if args.cross:
        cross_payload, files, args.mod_path = run_cross(
            saves_path, args.game_root, args, verbose=not args.quiet)
        if not files:
            sys.exit("--cross found no campaigns under %s" % saves_path)

    if args.verify:
        verify_all(files, args.jobs)
        return

    # Asked for now rather than after the campaign has been read. A folder
    # that cannot be made -- a typo, a drive that is not plugged in, a place
    # this user may not write -- used to surface as a stack trace out of
    # `os.makedirs` at the very end, after every save had been parsed.
    try:
        os.makedirs(args.out, exist_ok=True)
    except OSError as exc:
        sys.exit(f"Cannot write to {args.out}\n"
                 f"{exc.strerror or exc}. Choose somewhere else with --out.")

    verbose = not args.quiet
    if verbose:
        print(f"Found {len(files)} save(s).")

    # The mod is read before any save, because both the pop types read_province
    # keeps and the defines the counting uses have to be settled up front.
    #
    # Both are set from scratch rather than added to, because the window runs
    # one campaign after another in the same process: a set that only grew
    # carried the last mod's pop types and reform names into the next
    # campaign, which then read them out of saves that have none.
    # Asked before the mod is loaded, not after. The mod's own state is read
    # from its files rather than from the loaded mod, so a run with nothing
    # to do never pays the second it takes to read one.
    # Imported here rather than at the top: a run with nothing to do is
    # answered in seventy milliseconds, and loading this module costs ten of
    # them whether or not there is a mod to read.
    from mod_reader import mod_signature
    stamp = report_stamp(files, args, mod_signature(args.mod_path))
    ready = os.path.join(args.out, "report.html")
    # Only a run whose whole job is the report can be answered with the
    # report that is already there. The four `explain` answers print
    # something about a nation instead, and are not in the stamp because
    # they change nothing the report says.
    if (not args.rebuild and not args.no_html and not asked(args)
            and stamp_matches(args.out, stamp)):
        if verbose:
            print(f"Nothing has changed since this was built. "
                  f"Opening it as it is.\n\nWrote:\n  {ready}")
        return 0

    mod = None
    from v2parse import VANILLA_POP_TYPES
    if args.mod_path:
        from mod_reader import load_mod
        try:
            mod = load_mod(args.mod_path)
        except (OSError, ValueError) as exc:
            # A mod folder that has been renamed, moved or mistyped is an
            # ordinary mistake and the message already says what to do
            # about it. Wrapped in a stack trace it reads like a crash in
            # the program, which is what the window used to show.
            sys.exit(str(exc))
        extra = set(mod["pop_types"]) - VANILLA_POP_TYPES
        # Written back onto `args` because the rest of a single-campaign run
        # reads them off it -- the finishing spec, the two printed lines
        # below. `run_cross` asks the same function and keeps the answer to
        # itself, because it has a mod per campaign.
        args.pop_per_regiment, args.mob_types = mod_defaults(args, mod)
        if verbose:
            print("defines.lua: POP_SIZE_PER_REGIMENT="
                  f"{args.pop_per_regiment}")
            print(f"poptypes/: mobilizable = {' '.join(args.mob_types)}"
                  + (f"; mod-only pop types read: {' '.join(sorted(extra))}"
                     if extra else ""))

    # One object for how this run reads a save. It sets the three globals
    # the parser keeps -- here, and again in every worker, which on Windows
    # is a fresh interpreter that inherits nothing -- and it is the cache
    # key. Which mod a save is read under changes what comes out of it, so
    # two campaigns on two mods no longer share cache entries; and the key
    # cannot be worked out from a state different from the one the parse is
    # in, because there is only one state.
    reading = reading_for(args.mod_path, mod, args.mob_types)
    reading.apply()

    # Oldest first, decided from each save's own first line rather than by
    # sorting them after the fact -- the campaign is now walked in one pass
    # and a pass cannot be sorted halfway through. `stream` is a generator:
    # nothing is read until the loop below asks for it.
    files = in_date_order(files)
    wanted = set(args.tags) if args.tags else None
    # A nation's mobilizable pops are one entry per pop per province -- eleven
    # thousand of them for a large nation, two megabytes a save -- and the only
    # thing that reads them is `finalize`, which turns them into a handful of
    # numbers. Letting each save drop its own once it has been read is the
    # difference between a campaign of monthly autosaves needing a couple of
    # gigabytes and needing nothing much at all. `--explain-mob-pool` prints the
    # raw list back, so it is the one caller that keeps them.
    keep_pools = bool(args.explain_mob_pool)
    # Two diagnostics read a whole nation back out of the last save after the
    # run: --explain-mob-pool wants its raw pool, --explain-mob wants its
    # techs and inventions to explain where a mobilisation size came from.
    # Neither survives trimming, so with either of them asked for, saves are
    # kept whole. They are single-campaign diagnostics run on purpose, so the
    # memory that costs is memory somebody chose to spend.
    keep_whole = keep_pools or bool(args.explain_mob)
    # And two that want one field each rather than the whole nation.
    keep_fields = KEEP_NATION
    if args.inventions or args.check_inventions:
        keep_fields = KEEP_NATION + KEEP_FOR_INVENTIONS

    parse_options = dict(use_cache=not args.no_cache, reading=reading,
                         jobs=args.jobs)

    live = None
    if mod is not None:
        from mod_reader import (attainable_inventions, index_base_for,
                                index_coverage, validate_indices)
        from modrules import unjudged_triggers
        # Decode invention indices from compact summaries. Population and
        # province data stay in the raw cache until the report needs them.
        walked = campaign_inventions(files, verbose=verbose, **parse_options)
        every_nation = []
        all_techs = {}
        for _meta, nations in walked:
            for tag, nat in nations.items():
                every_nation.append(nat)
                all_techs.setdefault(tag, set()).update(nat["tech_list"])
        live = attainable_inventions(mod, all_techs)
        # Saves name each nation's inventions by index. Decoding them is what
        # turns the mobilisation size from "every invention this nation could
        # have" into the ones it actually rolled.
        mod["index_base"] = index_base_for(mod, every_nation)
        if verbose:
            if mod["index_base"] is None:
                print("\nInvention indices could not be decoded from "
                      f"{len(mod['invention_sequence'])} inventions; falling back "
                      "to requirement matching, which overstates unlucky nations.")
            else:
                bad, total = validate_indices(mod, every_nation, mod["index_base"])
                print(f"\nInvention indices decoded against "
                      f"{len(mod['invention_sequence'])} inventions "
                      f"(base {mod['index_base']}): {bad} of {total} nation-invention "
                      f"pairs are unreachable ({bad / total * 100:.1f}%).")
                odd, seen = index_coverage(mod, walked, mod["index_base"])
                if odd:
                    lost = sum(v[1] for v in odd.values())
                    print(
                        f"  {len(odd)} of {len(walked)} saves name inventions "
                        f"past the end of that array, so {lost} of {seen} "
                        f"holdings ({lost / seen * 100:.1f}%) cannot be read:")
                    for name in sorted(odd):
                        count, gone, lo, hi = odd[name]
                        print(f"    {name}: {count} indices, {lo}..{hi} "
                              f"({gone} holdings)")
                    print(
                        "  Those saves were written by a different build than "
                        "--mod-path -- another version of the mod, or one over "
                        "the top of it. Their ship stats and mobilisation size "
                        "are short by whatever those inventions grant; the rest "
                        "of the campaign is unaffected.")
        if verbose:
            rules = mod["invention_rules"]
            print(f"\nMod scan: {mod['tech_count']} techs "
                  f"({len(mod['tech_mob'])} grant mobilisation_size), "
                  f"{len(rules)} inventions grant it "
                  f"({len(live)} obtainable), "
                  f"{len(mod['event_mob'])} event modifiers, "
                  f"{sum(1 for _n, size, _i, _t in mod['triggered_mob'] if size)} "
                  f"triggered modifiers.")
            skipped = unjudged_triggers(mod)
            if skipped:
                print("  triggered modifiers left out, because their trigger "
                      "asks something this cannot answer: "
                      + ", ".join(skipped))
            for t, v in sorted(mod["tech_mob"].items()):
                print(f"  tech       {t:<44} +{v:.3f}")
            for n in sorted(rules):
                mark = "" if n in live else "   (unobtainable)"
                print(f"  invention  {n:<44} +{rules[n]['size']:.3f}{mark}")


    # Where `finalize` runs. It is the last step that reads a save whole --
    # two megabytes of per-province tables into a few dozen numbers -- so
    # doing it in the worker that parsed the save means every core at once
    # and a third as much coming back down the pipe.
    #
    # It used to be the no-mod runs only, because a mod's rate comes from
    # `breakdown`, which wants a list of reachable inventions that is not
    # known until the campaign has been walked once. But that walk happens
    # just above, and it is cheap now that it carries only technologies and
    # invention IDs -- so by here the rate is answerable and the mod can go
    # to the workers with the spec. It is a third of a megabyte, pickled
    # once per worker, against a hundred full saves pickled one at a time
    # into the one process that has everything else left to do.
    #
    # The diagnostics that print a nation back raw still want the tables,
    # so they keep the finishing in the parent. One spec either way: what a
    # run means by a finished nation cannot depend on where it was finished.
    spec = finish_spec(args, mod, live, wanted, keep_pools=keep_pools)
    in_workers = not keep_whole

    stream = parse_saves_stream(
        files, verbose=verbose and mod is None,
        transform=partial(_finish_save, spec=spec) if in_workers else None,
        **parse_options)
    keep = Keep(whole=keep_whole, fields=keep_fields)
    campaign = walk_campaign(stream, spec, in_workers, keep)
    # What is left in `main` is what `main` still uses: the tables it
    # starts, the two counts it prints and the saves it checks are there
    # at all. Everything the page needs travels as `campaign`.
    rows, parsed = campaign.rows, campaign.parsed
    ship_rows, pop_rows = campaign.ship_rows, campaign.pop_rows
    culture_rows, brigade_rows = campaign.culture_rows, campaign.brigade_rows
    tech_rows, pop_columns = campaign.tech_rows, campaign.pop_columns

    if not parsed:
        sys.exit("No saves could be read.")

    if explain(args, mod, live, parsed):
        return

    # `war_book` was folded save by save on the way past, above: each save
    # carries the whole war history up to its date, so collecting them first
    # and merging afterwards meant holding one overlapping copy per save --
    # fifty megabytes over thirty-eight saves, near two gigabytes over twelve
    # hundred monthly ones.

    price_rows = merge_prices(parsed)
    snapshot_rows = market_snapshot_rows(parsed)

    # The tables are written beside the report rather than before it.
    # Nothing in the report is read back out of them, they take about a third
    # of a second, and the report is the one thing anybody is waiting for --
    # so writing them first was a third of a second of the report already
    # being finished and nobody being able to open it.
    #
    # They are started at the moment the payload begins compressing, which
    # `build_report` says by calling this. That is the only stretch of the
    # run with the interpreter lock free -- gzip spends a quarter of a
    # second without it -- so it is the only stretch where a second thread
    # is worth anything. Started any earlier it merely takes turns with the
    # payload assembly, and the report lands later instead of sooner:
    # measured, 1.80 s to 1.98 s, which is the wrong direction.
    from report import Aside
    tables = Aside(lambda: write_outputs(
        rows, ship_rows, pop_rows, culture_rows, price_rows, snapshot_rows,
        brigade_rows, tech_rows, args.out, pop_columns))

    html_path = build_html(args, mod, campaign, price_rows,
                           snapshot_rows, cross_payload, tables)
    if html_path:
        _tell_report_ready(html_path)
    # Started at the compression if a report was built, and simply done
    # here if one was not.
    paths = tables.result()
    if html_path:
        paths.insert(0, html_path)
        # Last, so a run that died writing the tables is not recorded as one
        # with nothing left to do.
        write_stamp(args.out, stamp)

    if verbose:
        print(f"\n{len(rows)} nation-rows across {len(parsed)} saves.")
        if price_rows:
            months = sorted({r["date"] for r in price_rows}, key=date_key)
            print(f"{len(months)} dated price points, "
                  f"{months[0]} to {months[-1]}, "
                  f"{len({r['good'] for r in price_rows})} goods.")
        # Read back out of the rows this run just wrote, rather than
        # finalizing the last save a second time. It is quicker, it is what
        # lets a save be let go the moment its row exists -- and it settles
        # an old worry in this block's own comments, that the summary could
        # disagree with the table printed beside it. It cannot now: they are
        # the same numbers.
        latest_date = parsed[-1][0]["date"]
        latest_rows = sorted((r for r in rows if r["date"] == latest_date),
                             key=lambda r: -r["total_pop"])
        print(f"\nLargest nations at {latest_date}:")
        print(f"  {'tag':<5}{'pop':>12}{'accept%':>9}{'lit':>7}{'brig':>7}{'ships':>7}")
        for r in latest_rows[:8]:
            print(f"  {r['tag']:<5}{r['total_pop']:>12,}{r['accepted_pct']:>9.1f}"
                  f"{r['avg_literacy'] * 100:>6.1f}%{r['brigades']:>7}"
                  f"{r['ships']:>7}")
        if mod is not None:
            print(f"\nComputed mobilisation sizes at {latest_date} "
                  f"(check these against the in-game military panel):")
            for r in latest_rows[:10]:
                print(f"  {r['tag']}: {r['mobilisation_size'] * 100:.2f}%")
        print("\nWrote:")
        for path in paths:
            print(f"  {path}")


if __name__ == "__main__":
    # A worker on Windows starts by re-running this file, and without this it
    # would run the whole analysis again instead of waiting for a job.
    import multiprocessing
    multiprocessing.freeze_support()
    main()

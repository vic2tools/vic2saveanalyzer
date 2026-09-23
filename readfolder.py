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
Reading a folder of saves, on as many cores as are worth using.

`readsave` reads one save: a path in, what it says out. This reads a
campaign's worth of them -- in parallel where that pays, one at a time where
it does not or cannot, out of the disk cache where a save has been read
before -- and hands them over in the order they were asked for.

`parse_saves` collects them all; `parse_saves_stream` hands them over one at
a time, so a campaign of monthly autosaves never has to be in memory at
once. Behind those two: a process pool fed through a bounded window; workers
that start through a forkserver whose socket path must stay under 108 bytes,
and a fall-back to one at a time when they will not start at all; a Stop
button answered while the workers are busy; a disk cache keyed on the
reader's own source; and Windows, which starts each worker as a fresh
interpreter that inherits nothing and has to import this file by name to
find its job.

What it does not know is what the caller wants done with a save. That comes
in as a `transform`, run in the worker, so the finishing lives elsewhere and
nothing here imports it -- which is also why editing the finishing leaves the
parse cache alone.
"""

import hashlib
import os
import sys
import tempfile

import cacheio
from cacheio import load as _cache_read
from readsave import PLAIN, analyze_save


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


def parser_fingerprint():
    """
    Invalidate cached parses when any code that decides what one holds
    changes: this file, which writes the entry, and every file of ours it
    reaches -- `readsave` and everything that imports, and `cacheio`, which
    decides the entry's shape on disk.

    Found by following the imports, not listed. They used to be listed, six
    of them, and `nation.py` was not one -- so after the fold that fills
    every save moved into it, editing that fold rebuilt the report out of
    parses the old fold had made.

    Which is why this file must not import anything that only *uses* a save,
    the finishing above all: it would land in the key, and every edit to it
    would throw the whole cache away. That is what `transform` is for.
    """
    if getattr(sys, "frozen", False):
        # The bundled scanner is covered by the executable fingerprint. Its
        # temporary extraction timestamp changes on every launch.
        return cacheio.source_fingerprint()[:10]
    source = cacheio.source_fingerprint(*cacheio.sources_reached(__file__))
    if not source:
        return ""
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


def campaign_slot(name, files, reading=PLAIN, use_cache=True):
    """
    Where something worked out from a whole campaign is remembered, or None
    when caching is off or a save cannot be looked at.

    Keyed on the slot of every save in it, so it moves when any one save
    changes, or the reader, or the mod the saves are read under -- the same
    things that move a single save's entry, because it was made from them.
    The caller used to put this together itself out of this file's private
    parts; it is one question, and this is the file that knows the answer.
    """
    fingerprint = parser_fingerprint() if use_cache else ""
    if not fingerprint:
        return None
    world = reading.fingerprint()
    slots = [_cache_slot(path, fingerprint, world) for path in files]
    if not slots or not all(slots):
        return None
    key = hashlib.sha256("\n".join(slots).encode()).hexdigest()
    return os.path.join(cache_dir(), name + "_" + key + ".pkl")


# A picklable callable applied after reading and caching a save. The parent
# can request either invention summaries or finalized nations.
_TRANSFORM = None


def worker_setup(reading, transform=None):
    """
    What a fresh interpreter has to be told before it can read a save.

    Windows starts a worker as a new interpreter that imports this file by
    name, so nothing the parent set is set here. It used to be told three
    lists and had to put them back in the right three places; it is told the
    one profile and asks it to.
    """
    global _TRANSFORM
    reading.apply()
    _TRANSFORM = transform


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
    fingerprint = parser_fingerprint() if use_cache else ""
    world = reading.fingerprint()
    slots = [_cache_slot(p, fingerprint, world) if fingerprint else None
             for p in files]

    out = [None] * len(files)
    todo = []
    done = 0
    tell_progress(0, len(files))
    for i, path in enumerate(files):
        stop_if_asked()
        held = _cache_read(slots[i])
        if held is not None:
            out[i] = held
            done += 1
            tell_progress(done, len(files))
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
        stop_if_asked()
        try:
            meta, nations = analyze_save(files[i], verbose=verbose)
        except (ValueError, OSError) as exc:
            print(f"  skipped {os.path.basename(files[i])}: {exc}",
                  file=sys.stderr)
            continue
        _cache_write(slots[i], meta, nations)
        out[i] = (meta, nations)
        done += 1
        tell_progress(done, len(files))
    return [item for item in out if item is not None]


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
    from concurrent.futures.process import BrokenProcessPool
    fingerprint = parser_fingerprint() if use_cache else ""
    world = reading.fingerprint()
    slots = [_cache_slot(p, fingerprint, world) if fingerprint else None
             for p in files]
    ready = [bool(sl) and os.path.exists(sl) for sl in slots]
    todo = [i for i, got in enumerate(ready) if not got]
    total = len(files)
    tell_progress(0, total)

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
                max_workers=workers, initializer=worker_setup,
                initargs=(reading, transform))
        except Exception as exc:
            print(f"  reading one at a time ({exc})", file=sys.stderr)

    futures = {}
    waiting = list(pooled)
    done = 0
    try:
        for i, path in enumerate(files):
            stop_if_asked()
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
                except (BrokenProcessPool, MemoryError) as exc:
                    # A worker that died -- killed for memory, or by
                    # something on the machine -- breaks the whole pool,
                    # and every save still out with it fails the same way.
                    # That ended the run in a stack trace, where a pool that
                    # would not start has always been read one at a time.
                    # So is this: the pool is dropped, and this save and
                    # every one after it are read here.
                    print(f"  a worker stopped ({exc}); reading the rest "
                          f"one at a time", file=sys.stderr)
                    pool.shutdown(wait=False, cancel_futures=True)
                    pool = None
                    futures.clear()
                else:
                    got = (meta, nations)  # cached and finished in the worker
                    if verbose:
                        print(f"  [{done + 1}/{total}] "
                              f"{os.path.basename(path)} ... {meta['date']}")
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
            tell_progress(done, total)
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
    pool = ProcessPoolExecutor(max_workers=workers, initializer=worker_setup,
                               initargs=(reading,))
    try:
        # `todo` is the saves with no cache entry, so none of these is
        # cached, and no finishing was asked of this pool.
        pending = {pool.submit(_worker_parse, (i, files[i], slots[i], False))
                   for i in todo}
        while pending:
            stop_if_asked()
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
                tell_progress(already + done, len(files))
                if verbose:
                    print(f"  [{done}/{len(todo)}] "
                          f"{os.path.basename(files[index])} ... {meta['date']}")
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()
    return [item for item in out if item is not None]

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
The province scan, handed to `scanner/` when that has been built.

Reading a save is almost entirely scanning text and converting numbers, and
the province blocks are most of the file: they are about fifty-five percent of
the parse and they hold every pop in the game. `scanner/src/main.rs` does that
one loop, and this hands saves to it and turns what comes back into the same
structures Python would have built.

Everything here is optional. If the binary has not been built -- no Rust
compiler on the machine that made the release, a platform nobody cross-compiled
for -- `available()` says so once and every save is read the way it always was.
A missing scanner costs speed and nothing else, which is the only reason it is
safe to have a second implementation of anything.
"""

import json
import os
import subprocess
import sys
import threading

from nation import fold_country, fold_provinces

BINARY = "vic2scan.exe" if sys.platform == "win32" else "vic2scan"

# What the first line has to carry, and what the rest has to. A binary that
# does not send all of it is a binary from a different version of this
# program, and reading saves in Python is always allowed where guessing what
# a missing field meant is not.
HEAD_NEEDED = frozenset(("date", "player", "blocks"))
# The whole answer of a serving scanner to a file it turns down, in place of
# the first line. See `Served`.
REFUSED = "refused"
NEEDED = frozenset(("world_pop", "owners", "pop_ids", "pop_kinds",
                    "kind_names", "nations"))
_FOUND = None


def _candidates():
    """Where the scanner might be, nearest first."""
    here = os.path.dirname(os.path.abspath(__file__))
    # Beside the executable when frozen, beside this file when not, and in
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


def _kill(proc):
    try:
        proc.kill()
    except OSError:
        pass


class Running:
    """
    A scanner at work, and whatever has been read off it so far.

    The scanner answers in two parts, and this owns the boundary. Both
    halves are read through the buffered reader `Popen` already provides,
    never through `communicate`: that one reads the descriptor directly, so
    anything a buffered read had pulled in past the first newline would sit
    in a buffer it never looks at and simply be lost.

    The watchdog is what `communicate(timeout=...)` used to provide. A
    blocking read is the only thing that works the same way on Windows,
    where `select` does not take a pipe, so the limit is enforced from the
    outside: if the timer fires the scanner is killed, the read ends, and
    the save is read in Python instead. It is cancelled the moment the
    output ends, which is every time but the one this is here for.
    """

    __slots__ = ("proc", "_guard")

    def __init__(self, proc, timeout):
        self.proc = proc
        self._guard = threading.Timer(timeout, _kill, args=(proc,))
        self._guard.daemon = True
        self._guard.start()

    def line(self):
        """The first line, without its newline, or b"" if there was none."""
        try:
            return self.proc.stdout.readline().rstrip(b"\n")
        except (OSError, ValueError):
            return b""

    def remainder(self):
        """Everything after the first line, or None if it could not be read."""
        try:
            out = self.proc.stdout.read()
            # Read after the output rather than alongside it, which cannot
            # deadlock here: the scanner writes one line to stderr and
            # exits, or writes its timings and exits, and neither fills a
            # pipe.
            self.proc.stderr.read()
            self.proc.wait()
        except (OSError, ValueError):
            return None
        finally:
            self.abandon()
        return out

    def __del__(self):
        # The timer holds the process, not this owner, so exceptions between
        # protocol halves can release the scanner immediately.
        try:
            self.abandon()
        except Exception:
            pass

    @property
    def returncode(self):
        return self.proc.returncode

    def refused(self):
        """
        Whether the scanner turned the file down, rather than mis-answering.

        It exits non-zero for a save it will not read -- a zip, a layout
        the game does not write, a file cut in half -- and that is an
        ordinary thing to meet in a folder of saves. It exits zero and
        answers with something unusable only when it is a different
        version from the analyzer beside it. The two want different words
        said about them, and only the second is worth warning about.
        """
        return bool(self.proc.returncode)

    def abandon(self):
        """Reap the scanner and close both pipes, even on a partial read."""
        self._guard.cancel()
        if self.proc.poll() is None:
            _kill(self.proc)
        try:
            self.proc.wait()
        finally:
            self.proc.stdout.close()
            self.proc.stderr.close()


def _no_window():
    """
    What `Popen` is told so the scanner opens no window of its own.

    The executable is a windowed program and the scanner a console one, and
    on Windows a windowed program that starts a console program gets a new
    console window for it -- one flashed up for every save read -- unless
    it says `CREATE_NO_WINDOW`. Everywhere else there is no such flag, and
    `Popen` refuses any.
    """
    if sys.platform != "win32":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _launch(argv, stdin=None, stderr=subprocess.PIPE):
    """
    The scanner started, for one save or to serve many. One place, so that
    both are started without a window of their own (see `_no_window`).
    """
    return subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                            stderr=stderr, creationflags=_no_window())


class _Server:
    """
    One scanner that reads save after save for this process: `--serve`.

    A worker reads a dozen saves or more, and starting a scanner for each
    was dearer than the start. The new process was handed its 34 MB
    buffer as fresh pages, every one faulted in and zeroed by the kernel,
    so reading a save into memory took 32 ms where reading one into a
    buffer already in use takes 14 -- and on Windows starting a process is
    slow in itself. So a worker keeps one, tells it a path a line, and
    reads its answer the way it reads a scanner of its own (`Served`).

    It is told what to read for once, when it starts; a run asking for
    something else gets a new one. It ends when its stdin closes, which
    happens when this process lets it go or ends.
    """

    __slots__ = ("proc", "told", "answered")

    def __init__(self, binary, told):
        self.told = told
        self.answered = 0
        # Nothing reads its stderr, so nothing is let fill it: a pipe
        # nobody drains would stop it a few hundred saves in.
        self.proc = _launch([binary, "--serve"] + told,
                            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def ask(self, line):
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def kill(self):
        _kill(self.proc)

    def close(self):
        """Let it go: it exits when its stdin closes. Killed if it will not."""
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill(self.proc)
            self.proc.wait()
        self.proc.stdout.close()


_SERVER = None
# Whether the binary here has shown it can serve. One that cannot -- built
# before `--serve` existed -- is asked one save at a time instead, the way
# it always was.
_SERVES = True


def stop_serving():
    """Let this process's scanner go, if it has one."""
    global _SERVER
    if _SERVER is not None:
        server, _SERVER = _SERVER, None
        server.close()


class Served:
    """
    One save's answer from this process's `_Server`, read as `Running`
    reads a scanner of its own: `line`, then `remainder`.

    What a one-save scanner says by exiting, a serving one says in a line:
    `{"refused": code}` for a file it turns down, which is then the whole
    answer. A server that stops mid-answer, or is stopped by the watchdog,
    is let go, and the next save starts another.
    """

    __slots__ = ("server", "_guard", "_open", "returncode")

    def __init__(self, server, timeout):
        self.server = server
        self._open = True
        self.returncode = None
        self._guard = threading.Timer(timeout, server.kill)
        self._guard.daemon = True
        self._guard.start()

    def _read(self):
        try:
            return self.server.proc.stdout.readline()
        except (OSError, ValueError):
            return b""

    def line(self):
        got = self._read()
        if got.startswith(b'{"%s":' % REFUSED.encode()):
            try:
                self.returncode = int(json.loads(got)[REFUSED]) or 1
            except (ValueError, KeyError, TypeError):
                self.returncode = 1
            self._done()
            return b""
        if not got:
            self._lost()
        return got.rstrip(b"\n")

    def remainder(self):
        if not self._open:
            return None
        got = self._read()
        if not got.endswith(b"\n"):
            self._lost()
            return None
        self.returncode = 0
        self._done()
        return got[:-1]

    def refused(self):
        return bool(self.returncode)

    def _done(self):
        self._guard.cancel()
        self._open = False
        self.server.answered += 1

    def _lost(self):
        """The server went, or was stopped, mid-answer. So is it forgotten."""
        global _SERVER, _SERVES
        self._guard.cancel()
        self._open = False
        if self.returncode is None:
            self.returncode = -1
        if not self.server.answered:
            # Never answered anything: a binary that cannot serve.
            _SERVES = False
        if _SERVER is self.server:
            _SERVER = None
        self.server.kill()
        try:
            self.server.close()
        except OSError:
            pass

    def abandon(self):
        """Leave this answer. Half-read, the server is let go with it."""
        if self._open:
            self._lost()

    def __del__(self):
        try:
            self.abandon()
        except Exception:
            pass


def _serve(binary, path, told, timeout):
    """This save asked of this process's server, or None to start one of its own."""
    global _SERVER
    if not _SERVES:
        return None
    try:
        line = path.encode("utf-8") + b"\n"
    except UnicodeEncodeError:
        return None               # a name the line protocol cannot carry
    if b"\n" in line[:-1] or b"\r" in line:
        return None
    if _SERVER is not None and (_SERVER.told != told
                                or _SERVER.proc.poll() is not None):
        stop_serving()
    try:
        if _SERVER is None:
            _SERVER = _Server(binary, told)
        _SERVER.ask(line)
    except OSError:
        if _SERVER is not None:
            _SERVER.kill()
        _SERVER = None
        return None
    return Served(_SERVER, timeout)


def start(path, pop_types, mob_types, army_techs=(), navy_techs=(),
          reform_keys=(), timeout=600):
    """
    Set the scanner going and come straight back.

    Started before anything is read, because the caller has a share of the
    same save to do and the two are meant to happen at once. See `head`.

    Asked of this process's serving scanner when there is one to ask (see
    `_Server`), and otherwise of a scanner started for this save alone.
    """
    binary = available()
    if binary is None:
        return None
    told = ["--pop-types", ",".join(sorted(pop_types)),
            "--mob-types", ",".join(sorted(mob_types)),
            "--army-techs", ",".join(sorted(army_techs)),
            "--navy-techs", ",".join(sorted(navy_techs)),
            "--reform-keys", ",".join(sorted(reform_keys))]
    served = _serve(binary, path, told, timeout)
    if served is not None:
        return served
    try:
        return Running(_launch([binary, path] + told), timeout)
    except OSError:
        return None


def head(running):
    """
    The date, the player and where every non-province block is. Or None.

    This is the point of answering in two parts. The scanner knows all of it
    a fifth of the way through its run -- it has read the file and found the
    top-level blocks, and has the whole province and country scan still to
    do -- and it is everything the caller needs to start on its own share of
    the save: the wars, the market, the great power list, which it reads out
    of the file itself.

    Sent at the end with everything else, the caller waited through the
    province scan doing nothing and then read the wars while the scanner
    sat finished and idle, so a save cost the two added together: 127 ms and
    147 ms of it. Sent here they run at the same time and a save costs the
    longer of the two.
    """
    if running is None:
        return None
    line = running.line()
    if not line:
        return None
    try:
        got = json.loads(line)
    except ValueError:
        return None
    if not isinstance(got, dict) or not HEAD_NEEDED <= set(got):
        return None
    return got


def collect(running):
    """
    The rest of what the scanner found -- the provinces and the countries.

    None always means "read it in Python instead", never "give up": the
    binary is missing, or it refused the file -- a zip, a save some editor
    has reflowed -- or it failed in a way nobody has thought of yet.
    """
    if running is None:
        return None
    out = running.remainder()
    if out is None or running.returncode != 0 or not out:
        return None
    try:
        got = json.loads(out)
    except ValueError:
        return None
    if not isinstance(got, dict) or not NEEDED <= set(got):
        return None
    return got


_SAID = False


def note_unusable():
    """
    Say once that the binary is there and its answer was not usable.

    A missing scanner is ordinary and silent: the saves are read in Python
    and nothing is lost but speed. A scanner that is *present* and does not
    answer the way this version expects is a misconfiguration -- a stale
    build left beside a newer analyzer, half of a protocol change -- and it
    costs four times the runtime while looking exactly like a correct run,
    because the fallback is correct. It went unnoticed here for six
    commits. Once per process, so fifteen workers say it at most fifteen
    times and not once a save.
    """
    global _SAID
    if _SAID:
        return
    _SAID = True
    print("  the scanner at %s did not answer in the form this version "
          "expects, so saves are being read in Python instead -- several "
          "times slower. Rebuild it: cargo build --release "
          "--manifest-path scanner/Cargo.toml" % available(), file=sys.stderr)


def scan(path, pop_types, mob_types, timeout=600, army_techs=(),
         navy_techs=(), reform_keys=()):
    """
    Start the scanner and wait for all of it. Both halves, as one dict.

    For callers with nothing to do in between -- the tests, mostly. The
    analyzer takes the two halves separately and works between them.
    """
    running = start(path, pop_types, mob_types, army_techs, navy_techs,
                    reform_keys, timeout=timeout)
    first = head(running)
    if first is None:
        if running is not None:
            running.abandon()
        return None
    rest = collect(running)
    if rest is None:
        return None
    rest.update(first)
    return rest


def apply(got, found):
    """
    Fold a scan into what `analyze_save` is filling (`readsave._Found`).

    What belongs to a nation is handed to `nation.fold_provinces`, which is
    where the record and the rules for filling it live. What is left here is
    the save's own bookkeeping -- who owns which province, what type each pop
    was, how many people the world holds -- which is not part of any one
    nation and has no record to belong to.

    The shapes are the scanner's, chosen to be cheap to write and cheap to
    read back: pairs rather than objects, one shared table of pop type names
    rather than the name against every pop. Turning them into the dicts, sets
    and lists Python expects is the price of not parsing the file twice, and
    it is about a twentieth of what parsing it costs.
    """
    found.world_pop += got["world_pop"]
    province_owner = found.province_owner
    for pid, owner, held in got["owners"]:
        province_owner[pid] = (sys.intern(owner), sys.intern(held))

    # The one shared table of names, interned once here rather than once per
    # pop: a save has tens of thousands of pops and a few hundred names.
    names = [sys.intern(k) for k in got["kind_names"]]
    ids, kind_of = got["pop_ids"], got["pop_kinds"]
    pop_registry = found.pop_registry
    for i, pop_id in enumerate(ids):
        pop_registry[pop_id] = names[kind_of[i]]

    nations = found.nations
    for tag, block in got["nations"].items():
        fold_provinces(nations[sys.intern(tag)], block, names)


def apply_countries(got, nations):
    """Fold the scanner's country blocks into the nations being built."""
    for block in got.get("countries", ()):
        fold_country(nations[sys.intern(block["tag"])], block)

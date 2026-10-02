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

The command line is read here (`run.py`) and the run is made by the scanner
(`vic2scan analyze`, in `scanner/`), which does all of it in Rust: this file
finds the scanner, hands it the run, and relays what it says to whoever is
listening -- a terminal, or the window's log.
"""

import os
import sys
import threading

import fastscan
# The window's Stop button and progress bar, which `analyze` hands on, and
# `Cancelled`, which the window catches here.
from readfolder import (Cancelled, set_cancel_check, set_progress,  # noqa: F401
                        stop_if_asked, tell_progress)
from run import Run, RunError, command_line                         # noqa: F401


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
    binary = fastscan.available()
    if not binary:
        raise RunError(
            "The scanner that makes the report is not built (%s, looked for beside this "
            "program and in scanner/target/release). Build it with:\n\n    %s\n\nThat "
            "needs Rust's cargo; see README.md." % (fastscan.BINARY, BUILD))
    import dataclasses
    import json
    import subprocess
    import tempfile
    fd, path = tempfile.mkstemp(prefix="vic2_run_", suffix=".json")
    refused = path[:-len(".json")] + ".refused"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(dataclasses.asdict(run)))
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
                                     creationflags=fastscan._no_window())
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
            status = _relayed(argv, fastscan._no_window(), hosted)
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


if __name__ == "__main__":
    main()

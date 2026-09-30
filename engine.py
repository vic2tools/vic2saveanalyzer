# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""
The report engine: the scanner's `report` mode, which does in Rust what a
run did in Python once the game and the mod are settled.

It reads every save itself, settles the campaign's inventions, finishes
every nation, builds the tables, the wars, the prices, the map and the
page, and writes the report and the nine CSV tables. What stays here is
everything before that -- the command line, the game and the mod settled,
the stamp, the head of the mod a save is read under -- and handing the
engine what it needs: the run's settings (`spec`), with the mod folder,
which the engine reads itself (`scanner/src/engine/modread.rs`) while it
reads the saves.

A run the engine cannot do the way Python does it -- a save the scanner
refuses, a mod rule it does not copy -- it hands back before writing
anything (`DECLINED`), and the run goes on in Python as it always did.
"""

import json
import os
import subprocess
import sys
import tempfile

# The engine's exit status for "run this one in Python".
DECLINED = 3


def usable(args):
    """
    Whether this run can be handed to the engine: the scanner has been
    built, and the run is a report rather than one of the diagnostics,
    which print a nation back out of the saves and stay in Python.
    `VIC2_NO_ENGINE` in the environment keeps every run in Python.
    """
    if os.environ.get("VIC2_NO_ENGINE"):
        return False
    if (args.explain_mob or args.explain_mob_pool or args.inventions
            or args.check_inventions):
        return False
    import fastscan
    return fastscan.available() is not None


class _Relay:
    """
    The engine's output, read on threads as it comes: its own printed
    lines passed on, and the lines it says things to the analyzer with
    (`@progress`, `@ready`, `@done`) acted on.
    """

    def __init__(self, proc, verbose, progress, ready):
        import threading
        self.proc = proc
        self.done = None
        self.errors = []
        self.failure = None
        self._verbose = verbose
        self._progress = progress
        self._ready = ready
        self._out = threading.Thread(target=self._read_out, daemon=True)
        self._err = threading.Thread(target=self._read_err, daemon=True)
        self._out.start()
        self._err.start()

    def _read_out(self):
        try:
            for raw in self.proc.stdout:
                if self.failure is not None:
                    continue  # drain the pipe even when a callback has failed
                try:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line.startswith("@progress "):
                        done, total = line.split()[1:3]
                        self._progress(int(done), int(total))
                    elif line.startswith("@ready "):
                        self._ready(line[len("@ready "):])
                    elif line.startswith("@done "):
                        self.done = dict(part.split("=", 1) for part in
                                         line[len("@done "):].split(" ", 1))
                    else:
                        print(line)
                except Exception as exc:
                    self.failure = exc
        except Exception as read_error:
            self.failure = read_error
        finally:
            self.proc.stdout.close()

    def _read_err(self):
        try:
            for raw in self.proc.stderr:
                self.errors.append(raw.decode("utf-8", "replace").rstrip("\r\n"))
        finally:
            self.proc.stderr.close()

    def running(self, timeout):
        """Whether the engine is still talking, after waiting up to `timeout`."""
        self._out.join(timeout)
        return self._out.is_alive()

    def finish(self):
        self._out.join()
        self._err.join()
        code = self.proc.wait()
        if self.failure is not None:
            raise self.failure
        return code


def run_report(args, files, reading, finish, head, mod_path, signature, cross_payload,
               progress, ready, stop_if_asked):
    """
    The report and the tables, made by the engine. Returns (the report's
    path or None, the tables it could not write), or None when the engine
    handed the run back, and the caller goes on in Python.

    `mod_path` is the mod folder, made absolute (`mod_reader._mod_root`):
    the engine reads it itself, beside the saves, and keeps what it read
    under `signature` (`mod_reader.mod_signature`), when there is one.
    """
    import fastscan
    binary = fastscan.available()
    folder = tempfile.gettempdir()
    written = []
    try:
        body = spec(args, files, reading, finish, head,
                    list(reading.pop_types), cross_payload)
        body["mod_path"] = mod_path
        body["mod_signature"] = signature
        spec_path = write_json(body, folder)
        written.append(spec_path)
        progress(0, len(files))
        proc = subprocess.Popen([binary, "report", spec_path],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                creationflags=fastscan._no_window())
        relay = _Relay(proc, not args.quiet, progress, ready)
        try:
            # The output thread ends the moment the engine does, where a
            # timed `wait` would notice up to a twentieth of a second late.
            while relay.running(0.2):
                stop_if_asked()
        except BaseException:
            if proc.poll() is None:
                proc.kill()
            relay.finish()
            raise
        code = relay.finish()
    finally:
        for path in written:
            try:
                os.remove(path)
            except OSError:
                pass
    if code == 0 and relay.done is not None:
        html = relay.done.get("html") == "1"
        refused = [os.path.join(args.out, name)
                   for name in relay.done.get("refused", "").split("\t") if name]
        return (os.path.join(args.out, "report.html") if html else None), refused
    if os.environ.get("VIC2_ENGINE_REQUIRED"):
        # For the checks that hold the engine to Python: a run it handed
        # back would compare Python with itself and pass for nothing.
        raise RuntimeError("the report engine did not make this report: "
                           "status %s: %s" % (code, "; ".join(relay.errors[-3:])))
    if code != DECLINED:
        print("The report engine stopped (%s); reading the campaign in Python "
              "instead." % ("; ".join(relay.errors[-3:]) or "status %s" % code),
              file=sys.stderr)
    return None


def write_json(value, folder=None, prefix="vic2_engine_"):
    """`value` as a JSON file of its own; returns the path."""
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".json", dir=folder)
    # `dumps` and one write: `dump` to a file takes the pure-Python encoder,
    # a quarter of a second for the mod and the spec.
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(value, separators=(",", ":")))
    return path


def spec(args, files, reading, finish, head, pop_columns, cross_payload=None):
    """
    The run as the engine is told it: the saves in the order the report
    wants them, how each is read, how each nation is finished, and what is
    written where. `head` is the mod's `ModHead` (or the whole mod), which
    is what reading and preparing a save needs before the rest has loaded.
    """
    from tech_groups import ARMY_LINES, NAVY_LINES, ARMY_TECHS, NAVY_TECHS
    import market
    import report
    import spending
    from readsave import STRATA
    from template import TEMPLATE
    from readfolder import cache_dir, parser_fingerprint
    return {
        "files": list(files),
        "out": args.out,
        # This process reads the `@progress`, `@ready` and `@done` lines.
        "protocol": True,
        "reading": {
            "pop_types": sorted(reading.pop_types),
            "mob_types": sorted(reading.mob_types),
            "reform_keys": sorted(reading.reform_keys),
            "population_groups": [list(g) for g in reading.population_groups],
            "army_techs": sorted(ARMY_TECHS),
            "navy_techs": sorted(NAVY_TECHS),
        },
        "finish": {
            "rate": finish.rate,
            "pop_per_regiment": finish.pop_per_regiment,
            "mob_types": sorted(finish.mob_types),
            "include_occupied": bool(finish.include_occupied),
            "player_nations": (sorted(finish.player_nations)
                               if finish.player_nations is not None else None),
            "wanted": sorted(finish.wanted) if finish.wanted else None,
            "min_pop": finish.min_pop,
        },
        "head": {
            "defines": dict(head.defines or {}),
            "province_regions": [[p, r] for p, r in (head.province_regions or {}).items()],
        },
        "tech_lines": {"army": ARMY_LINES, "navy": NAVY_LINES},
        # The page and the tables' declarations are the Python's, handed
        # over rather than copied, so there is one of each: an edit to the
        # template or a column reaches the engine without a rebuild.
        "template": TEMPLATE,
        "tables": {
            "metrics": report.METRICS,
            "growth": report.GROWTH_METRICS,
            "gain": report.GAIN_METRICS,
            "colours": report.SERIES_COLOURS,
            "category_labels": report.CATEGORY_LABELS,
            "growth_span": report.MIN_GROWTH_SPAN,
            "supply_named": report.SUPPLY_NAMED,
            "good_categories": market.GOOD_CATEGORIES,
            "price_columns": market.PRICE_COLUMNS,
            "snapshot_columns": market.SNAPSHOT_COLUMNS,
            "base_columns": spending.BASE_COLUMNS,
            "per_save": [[name, list(spending.columns_of(name, pop_columns))]
                         for name in spending.PER_SAVE],
            "strata": STRATA,
        },
        "pop_columns": list(pop_columns),
        "no_html": bool(args.no_html),
        "split": bool(args.split),
        "map_scale": args.map_scale,
        "quiet": bool(args.quiet),
        "jobs": args.jobs,
        "cross": json.dumps(cross_payload, separators=(",", ":"))
                 if cross_payload is not None else None,
        # Where the engine keeps the saves it has read, and the version of
        # the program they were read by: the parser's own fingerprint, which
        # names the scanner binary -- and the executable, frozen -- so a new
        # build reads everything again.
        "cache": {"dir": cache_dir(), "version": parser_fingerprint(),
                  "on": not args.no_cache},
    }

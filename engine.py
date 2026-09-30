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
run did in Python once the mod is read.

It reads every save itself, settles the campaign's inventions, finishes
every nation, builds the tables, the wars, the prices, the map and the
page, and writes the report and the nine CSV tables. What stays here is
everything before that -- the command line, the game and the mod settled,
the stamp, the mod read and cached -- and handing the engine what it needs:
the run's settings (`spec`) and the mod as JSON (`export_mod`), which it
receives while it is already reading the saves.

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


def export_mod(mod):
    """
    The mod as the engine reads it: every field it uses, in JSON's terms.

    Dicts keyed by province id become lists of pairs, sets sorted lists,
    and the map's and the flags' inputs, which the report reads off the
    mod's files rather than off the `Mod`, are worked out here, once.
    """
    import mod_reader as mr
    path = mod.path

    def ordered(pairs):
        return [[k, v] for k, v in pairs]

    bmp = mr._map_file(path, "provinces.bmp")
    csv_path = mr._map_file(path, "definition.csv")
    has_map = os.path.isfile(bmp) and os.path.isfile(csv_path)
    rules = mod.invention_rules or {}
    return {
        "path": path,
        "invention_sequence": [[e["name"], e["size"], sorted(e["techs"]), sorted(e["tags"])]
                               for e in (mod.invention_sequence or ())],
        "party_policies": [p[3] for p in (mod.party_sequence or ())],
        "localisation": mod.localisation or {},
        "base_prices": mod.base_prices or {},
        "country_order": list(mod.country_order or ()),
        "formations": {tag: sorted(v) for tag, v in (mod.formations or {}).items()},
        "culture_names": mod.culture_names or {},
        "display_names": mod.display_names or {},
        "province_names": ordered((mod.province_names or {}).items()),
        "province_regions": ordered((mod.province_regions or {}).items()),
        "state_names": mod.state_names or {},
        "unit_kinds": mod.unit_kinds or {},
        "naval_units": mod.naval_units or {},
        "naval_effects": {name: {"effects": e["effects"], "techs": sorted(e["techs"]),
                                 "tags": sorted(e["tags"])}
                          for name, e in (mod.naval_effects or {}).items()},
        "naval_tech_effects": mod.naval_tech_effects or {},
        "technology": mod.technology or {},
        "mob_impacts": mod.mob_impacts or {},
        "modifier_impacts": mod.modifier_impacts or {},
        "reform_mob": [[r, o, v] for (r, o), v in (mod.reform_mob or {}).items()],
        "reform_names": sorted(mod.reform_names or ()),
        "static_mob": mod.static_mob or {},
        "triggered_mob": [[n, s, i, t] for n, s, i, t in (mod.triggered_mob or ())],
        "culture_groups": mod.culture_groups or {},
        "continents": ordered((mod.continents or {}).items()),
        "technologies": sorted(mod.technologies or ()),
        "defines": mod.defines or {},
        "strata": mod.strata or {},
        "invention_rules": {name: {"size": r["size"], "techs": sorted(r["techs"]),
                                   "tags": sorted(r["tags"]),
                                   "requires": sorted(r["requires"]),
                                   "base": r["base"],
                                   "blockers": [[f, b] for f, b in r["blockers"]]}
                            for name, r in rules.items()},
        "event_mob": mod.event_mob or {},
        "tech_mob": mod.tech_mob or {},
        "nv_mob": mod.nv_mob or {},
        "tech_count": mod.tech_count or 0,
        "colours": mr.country_colours(path) if has_map else {},
        "sea": sorted(mr.sea_provinces(path)) if has_map else [],
        "positions": [[p, x, y] for p, (x, y) in mr.unit_positions(path).items()]
                     if has_map else [],
        "flag_styles": {g: [v, e] for g, (v, e) in mr.government_flag_types(path).items()},
        "flag_roots": mr._flag_roots(path),
        "map_bmp": bmp if has_map else "",
        "map_csv": csv_path if has_map else "",
    }


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


def run_report(args, files, reading, finish, head, mod_or_loading, cross_payload,
               progress, ready, stop_if_asked):
    """
    The report and the tables, made by the engine. Returns (the report's
    path or None, the tables it could not write), or None when the engine
    handed the run back, and the caller goes on in Python.

    `mod_or_loading` is the mod, or the `Aside` still reading it: the engine
    reads the saves in the meantime and is handed the mod when it is ready.
    """
    import fastscan
    binary = fastscan.available()
    folder = tempfile.gettempdir()
    loaded = mod_or_loading if not hasattr(mod_or_loading, "result") else None
    written = []
    try:
        body = spec(args, files, reading, finish, head,
                    list(reading.pop_types), cross_payload)
        if loaded is not None:
            body["mod_file"] = write_json(export_mod(loaded), folder)
            written.append(body["mod_file"])
        spec_path = write_json(body, folder)
        written.append(spec_path)
        progress(0, len(files))
        proc = subprocess.Popen([binary, "report", spec_path],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                creationflags=fastscan._no_window())
        relay = _Relay(proc, not args.quiet, progress, ready)
        try:
            if loaded is None:
                try:
                    loaded = mod_or_loading.result()
                except BaseException:
                    proc.kill()
                    raise
                path = write_json(export_mod(loaded), folder)
                written.append(path)
                try:
                    proc.stdin.write((path + "\n").encode("utf-8"))
                    proc.stdin.flush()
                except OSError:
                    pass
            try:
                proc.stdin.close()
            except OSError:
                pass
            # The output thread ends the moment the engine does, where a
            # timed `wait` would notice up to a twentieth of a second late.
            while relay.running(0.2):
                stop_if_asked()
        except BaseException:
            if proc.poll() is None:
                proc.kill()
            proc.stdin.close()
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
        return (os.path.join(args.out, "report.html") if html else None), refused, loaded
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

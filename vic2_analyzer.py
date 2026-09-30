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

import csv
import gc
import os
import sys
import threading
from collections import namedtuple
from dataclasses import replace
from functools import partial

import cacheio
import market
from dates import date_key
from explain import explain, peek_save, verify_all
from nation import KEEP_FOR_INVENTIONS, KEEP_NATION
# Reading a save is its own thing and lives in its own file: a path in, and
# what the save says out. Nothing in it knows about caches, workers, reports
# or the command line.
from readsave import PLAIN, reading_for
# Reading a folder of saves in parallel, and the cache behind it.
from readfolder import (
    campaign_slot,
    parse_saves,
    parse_saves_stream,
    stop_if_asked,
    tell_progress,
)
# `analyze` hands a caller's Stop button and progress bar to these, and the
# window catches `Cancelled` here, because the analyzer is the thing it runs.
from readfolder import Cancelled, set_cancel_check, set_progress  # noqa: F401
from run import Run, RunError, command_line
# The front of a save, read without the rest: its date, for the order.
from savehead import dates_of, in_date_order, one_per_date
from stamp import already_built, forget_stamp, report_stamp, write_stamp
# What a nation comes to once its save is read. Called through the module,
# never imported by name: `testkit/crossrows.py` replaces
# `finishing.finish_nations` to watch both of its callers -- `campaign_rows`
# in `cross` and `finish_and_pack`, through `spending.spend`, in the workers
# -- and a copy of the name held here would go on calling the original,
# unwatched.
import finishing


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
    slot = campaign_slot("inventions", files, options["reading"],
                         options.get("use_cache", True))
    held = cacheio.load(slot)
    if held is not None:
        tell_progress(len(files), len(files))
        return held
    made = parse_saves(files, transform=invention_summary, **options)
    cacheio.store(slot, made)
    return made


def _write_csv_text(path, chunks, columns):
    """One CSV: its heading, then each save's rows as `spending` wrote them."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(columns)
        for chunk in chunks:
            fh.write(chunk)


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
            # already in column order -- see `spending.save_rows`
            writer.writerows(rows)


def write_outputs(text, price_rows, snapshot_rows, outdir, pop_columns):
    """
    Every CSV table. Returns (the paths written, the paths it could not
    open for writing).

    A table open in Excel cannot be written on Windows, and nobody reading
    a campaign's numbers is unusual for having one open. That used to end
    the run in a stack trace after the report had already been rewritten;
    now the rest of the tables are written and the ones that could not be
    are handed back, for `main` to name.

    `text` is the six tables every save writes its own rows into, as the
    saves were spent into them (`spending.PER_SAVE`): only their headings
    are written here. The prices and the market snapshot span saves, and
    are written from their rows.
    """
    import spending
    os.makedirs(outdir, exist_ok=True)

    paths, refused = [], []
    per_save = [(name, None, spending.columns_of(name, pop_columns))
                for name in spending.PER_SAVE]
    tables = (per_save[:1]
              + [("prices.csv", price_rows, market.PRICE_COLUMNS),
                 ("market_snapshot.csv", snapshot_rows,
                  market.SNAPSHOT_COLUMNS)]
              + per_save[1:])
    # Every table, even one with nothing in it this run. A table skipped for
    # being empty left the last run's copy standing in the folder -- ships
    # of forty nations beside a main table of the one `--tags` asked for,
    # and "Wrote:" not mentioning it -- so everything in the folder is
    # written by this run, a heading alone where there is nothing to say.
    for name, data, cols in tables:
        path = os.path.join(outdir, name)
        try:
            if data is None:
                _write_csv_text(path, text[name], cols)
            else:
                _write_csv(path, data, cols)
        except PermissionError:
            refused.append(path)
            continue
        paths.append(path)
    return paths, refused


# What one walk of a campaign produces, and what it was allowed to keep.
# Named shapes because `main` carried all of this as loose locals, and every
# one had to be handed by name to the things downstream that read it.
Campaign = namedtuple(
    "Campaign", "rows tables naval_profiles naval_of supply parsed war_book "
                "pop_columns text")


def walk_campaign(stream, spec, finished, pop_columns):
    """
    Read the campaign once, oldest save first, spending each save as it
    passes.

    Every save gives up its rows, folds its wars into the book and is then
    cut down to the handful of fields the rest of the run still asks for,
    so what is alive at any moment is one save rather than the campaign.
    `parsed` holds only those remains.

    `finished` says the stream already spent each save out in the workers
    (`spending.spend`): what arrives is its rows, its table text, its wars
    and what is left of it. When it did not -- the two diagnostics keep
    their saves whole, and finishing is what spends the tables they want to
    print -- the same finishing and the same `spending.save_rows` run here
    instead. This loop used to hold its own filter and its own call to a
    parent-side twin of the worker's, and the comment promising they
    matched was the only thing holding them together.

    What is left here is what spans saves: the lists the report is built
    from, the text of each table in save order, which ship profiles have
    been seen, the supply by good, and the war book.

    `pop_columns` is the pop types a row has a column for. Frozen at import
    it was the vanilla twelve, so a mod's own type -- IGoR's bankers, GFM's
    serfs -- was read out of the save, counted into the totals and then
    dropped on the way to the table.
    """
    import spending

    from wars import fold_packed_wars, fold_wars
    rows = []
    tables = spending.NationTables()
    text = {name: [] for name in spending.PER_SAVE}
    # Ship stats as each nation's own inventions leave them. Nations that
    # researched the same things have the same ships, so the profiles are kept
    # once each and referred to by number rather than repeated per save.
    naval_profiles, naval_index, naval_of = [], {}, {}
    # good -> {date: {tag: what it put on the market}}, for the production view.
    supply_by = {}

    parsed = []
    war_book = {"wars": {}, "order": []}

    for item in stream:
        stop_if_asked()
        if finished:
            meta, nations, wars, got = item
        else:
            # Only the diagnostics reach this now. They asked for the
            # per-province tables to be kept, and finishing is what spends
            # them, so it waits for the parent.
            meta, nations = item
            nations = finishing.finish_nations(meta, nations, spec)
            got = spending.save_rows(meta, nations, spec, pop_columns)
            wars = meta.get("wars", ())
        date = meta["date"]
        rows += got.rows
        tables.add(date, got.tables)
        for name, chunk in got.text.items():
            text[name].append(chunk)
        for tag, key, profile in got.naval:
            if key not in naval_index:
                naval_index[key] = len(naval_profiles)
                naval_profiles.append(profile)
            naval_of.setdefault(tag, {})[date] = naval_index[key]
        for good, tag, amount in got.supply:
            supply_by.setdefault(good, {}).setdefault(date, {})[tag] = amount

        # This save's wars, folded in as it passes. The book wants them oldest
        # first, which is the order the stream is in, so folding here costs
        # nothing and means no save has to keep its own copy. A save spent
        # in a worker sends them beside what is left of it; a save kept whole
        # keeps them, because the two diagnostics that keep saves whole judge
        # a nation's triggered modifiers again, and `war = yes` is asked of
        # these -- emptied, `--explain-mob` explained a rate without the war
        # modifier the report had counted in it.
        if finished:
            fold_packed_wars(war_book, wars)
        else:
            fold_wars(war_book, wars)
        # Kept whole only for the diagnostics, which print a nation's raw
        # pool back; everyone else's save was trimmed where it was spent.
        parsed.append((meta, nations))

    return Campaign(rows=rows, tables=tables, naval_profiles=naval_profiles,
                    naval_of=naval_of, supply=supply_by, parsed=parsed,
                    war_book=war_book, pop_columns=pop_columns, text=text)


class Aside:
    """
    A job run on a thread, whose answer and whose failure both come back.

    Two things in this program are worth a thread, and each only because of
    what it runs beside. Reading a mod that is not cached runs beside the
    saves being read, which is the workers' time rather than this process's.
    And writing the CSV tables runs beside the payload's compression: gzip
    spends a quarter of a second inside zlib, which releases the interpreter
    lock for all of it, so the tables -- three tenths of a second, needed by
    nothing the report contains -- cost the longer of the two rather than
    the sum.

    Started at the compression and not a line earlier. Assembling the payload
    is ordinary Python holding the lock the whole way, so a thread started
    before it only takes turns with it, and the report lands later rather
    than sooner -- which is the opposite of the point.

    A thread rather than a process because the tables are forty megabytes of
    tuples and sending them anywhere costs more than writing them.

    It is made ready and started separately, because the caller knows what
    the job is long before it knows when to run it -- `build_report` says
    when by calling `start`. One that is never started is not a special
    case: `result` simply does the work where it stands, which is what the
    runs that build no report want anyway.
    """

    __slots__ = ("_fn", "_thread", "_value", "_error")

    def __init__(self, fn):
        self._fn = fn
        self._value = self._error = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            self._value = self._fn()
        except BaseException as exc:                     # noqa: BLE001
            self._error = exc

    def start(self):
        """Begin, if it has not begun. Safe to call more than once."""
        if self._thread.ident is None:
            self._thread.start()

    def result(self):
        """
        Its answer, raising whatever it raised.

        Does the work here and now if nobody ever started it, so a caller
        can always ask for the answer without first asking whether it ran.
        """
        if self._thread.ident is None:
            self._run()
        else:
            self._thread.join()
        if self._error is not None:
            raise self._error
        return self._value


def build_html(args, mod, campaign, price_rows, snapshot_rows,
               cross_payload, tables, map_ahead=None):
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

    `map_ahead` is the process decoding the province bitmap since the saves
    began (see `_map_ahead`), waited for here before the map is built.
    """
    rows, parsed = campaign.rows, campaign.parsed
    naval_profiles, naval_of = campaign.naval_profiles, campaign.naval_of
    supply_by, war_book = campaign.supply, campaign.war_book

    html_path = None
    if not args.no_html:
        from report import (build_map, build_report, build_succession,
                            flags_for, nation_names)
        from wars import build_wars, war_tags
        wars = build_wars(parsed, mod.province_names, mod.province_regions,
                          mod.state_names, mod.unit_kinds, book=war_book)
        report_names = nation_names(mod, parsed, also=war_tags(wars))
        # The map needs the mod's province bitmap; without --mod-path the tab
        # is dropped rather than shown empty.
        if map_ahead is not None:
            map_ahead.join()
        map_data = build_map(mod, parsed, args.map_scale) if mod else None
        if map_data and map_data.get("derived") and not args.quiet:
            print(f"map/positions.txt anchors no army counter for "
                  f"{map_data['derived']} of the provinces holding troops; "
                  f"those markers sit at the middle of the province instead.")
        great_powers, flags = flags_for(mod, parsed, war_book)
        try:
            html_path = build_report(
                rows, campaign.tables, price_rows, snapshot_rows, args.out,
                tag_names=report_names,
                map_data=map_data,
                base_prices=mod.base_prices,
                great_powers=great_powers,
                flags=flags,
                cross=cross_payload,
                technology=mod.technology,
                wars=wars,
                succession=build_succession(parsed, mod.formations),
                culture_names=mod.culture_names,
                display_names=mod.display_names,
                naval={"profiles": naval_profiles, "of": naval_of,
                       "exact": mod.index_base is not None}
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


def _saves_in(args):
    """
    (the saves path, the .v2 files directly in it) -- or the one file, when
    that is what was given -- refused in a sentence if there is nothing.
    """
    saves_path = os.path.expanduser(os.path.expandvars(args.saves))
    if not os.path.exists(saves_path):
        raise RunError(
            f"Path not found: {saves_path}\n"
            f"If you used ~ in PowerShell, try $HOME instead, or give the full "
            f"path starting with C:\\Users\\..."
        )
    if not os.path.isdir(saves_path):
        return saves_path, [saves_path]
    files = sorted(os.path.join(saves_path, f)
                   for f in os.listdir(saves_path)
                   if f.lower().endswith(".v2"))
    # With --cross the saves sit in subfolders, so a parent holding none of
    # its own is the ordinary case rather than a mistake.
    if not files and not args.cross:
        raise RunError(
            f"No .v2 files in {saves_path}\n"
            f"Point this at the folder that holds your saves, not at a "
            f"single save."
        )
    return saves_path, files


def _open_mod(args, signature):
    """
    (the mod, what this run knows of it so far, the thread still reading it).

    A mod that has to be read from its files takes most of a second, and
    reading a save needs four things of it that take a few milliseconds: its
    `ModHead`. Nothing else in it is wanted until every save has been read
    once, for the inventions. So when the mod is not cached, the saves are
    read on the strength of the head, and the rest of the mod is read on a
    thread beside them -- whose `result` is the mod. It takes a core from the
    saves, which then take 2.6 s to read instead of 2.3, but the two together
    took 3.2 s one after the other with fifteen cores idle for the first.

    With no mod asked for, the first two are `NO_MOD`. A mod folder that has been
    renamed, moved or mistyped is refused in the words `mod_reader` gives,
    rather than as a stack trace.
    """
    from mod_reader import NO_MOD, cached_mod, has_rules, load_mod, mod_head
    if not args.mod_path:
        return NO_MOD, NO_MOD, None
    try:
        mod = cached_mod(args.mod_path, signature)
        if mod is not None:
            return mod, mod, None
        if has_rules(args.mod_path):
            loading = Aside(partial(load_mod, args.mod_path))
            loading.start()
            return None, mod_head(args.mod_path), loading
        # Nothing it could be read from, so this refuses it now, in the
        # words `load_mod` gives, rather than after every save.
        mod = load_mod(args.mod_path)
        return mod, mod, None
    except (OSError, ValueError) as exc:
        raise RunError(str(exc)) from exc


def _mod_head(args):
    """
    What reading a save needs of the mod (`mod_reader.ModHead`), for a run
    the engine makes, which reads the rest of the mod itself; `NO_MOD` with
    no mod asked for. A folder with nothing to read is refused here, in
    the words `load_mod` gives, as `_open_mod` refuses it.
    """
    from mod_reader import NO_MOD, has_rules, load_mod, mod_head
    if not args.mod_path:
        return NO_MOD
    try:
        if has_rules(args.mod_path):
            return mod_head(args.mod_path)
        # Nothing it could be read from, so this refuses it in those words.
        return load_mod(args.mod_path)
    except (OSError, ValueError) as exc:
        raise RunError(str(exc)) from exc


def _on_the_game(args):
    """
    (the run with its mod settled on an installed Victoria II, a line saying
    which), or refused in a sentence (see `mod_reader.settle_game`). With no
    mod named, the mod is the install itself, which is how the unmodded game
    is read.

    A `--cross` run settles each campaign's mod as it surveys them.
    """
    if args.cross:
        return args, ""
    from mod_reader import is_install, settle_game
    try:
        mod_path, game = settle_game(args.mod_path, args.game_root)
    except ValueError as exc:
        raise RunError(str(exc)) from exc
    said = (f"Victoria II at {game}, "
            + ("unmodded." if is_install(mod_path) else
               f"with {os.path.basename(os.path.normpath(mod_path))}."))
    return replace(args, mod_path=mod_path), said


def _say_mod(mod, live, walked, every_nation):
    """What a verbose run says about the mod, once its inventions are decoded."""
    from mod_reader import index_coverage, validate_indices
    from modrules import unjudged_triggers
    if mod.index_base is None:
        print("\nInvention indices could not be decoded from "
              f"{len(mod.invention_sequence)} inventions; falling back "
              "to requirement matching, which overstates unlucky nations.")
    else:
        bad, total = validate_indices(mod, every_nation, mod.index_base)
        print(f"\nInvention indices decoded against "
              f"{len(mod.invention_sequence)} inventions "
              f"(base {mod.index_base}): {bad} of {total} nation-invention "
              f"pairs are unreachable ({bad / total * 100:.1f}%).")
        odd, seen = index_coverage(mod, walked, mod.index_base)
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
    rules = mod.invention_rules
    print(f"\nMod scan: {mod.tech_count} techs "
          f"({len(mod.tech_mob)} grant mobilisation_size), "
          f"{len(rules)} inventions grant it "
          f"({len(live)} obtainable), "
          f"{len(mod.event_mob)} event modifiers, "
          f"{sum(1 for _n, size, _i, _t in mod.triggered_mob if size)} "
          f"triggered modifiers.")
    skipped = unjudged_triggers(mod)
    if skipped:
        print("  triggered modifiers left out, because their trigger "
              "asks something this cannot answer: "
              + ", ".join(skipped))
    for t, v in sorted(mod.tech_mob.items()):
        print(f"  tech       {t:<44} +{v:.3f}")
    for n in sorted(rules):
        mark = "" if n in live else "   (unobtainable)"
        print(f"  invention  {n:<44} +{rules[n]['size']:.3f}{mark}")


def _say_summary(rows, parsed, price_rows, modded, paths):
    """What a verbose run says at the end: the campaign, and the files written."""
    print(f"\n{len(rows)} nation-rows across {len(parsed)} saves.")
    if price_rows:
        months = sorted({r[0] for r in price_rows}, key=date_key)
        print(f"{len(months)} dated price points, "
              f"{months[0]} to {months[-1]}, "
              f"{len({r[2] for r in price_rows})} goods.")
    # Read back out of the rows this run just wrote, rather than finalizing
    # the last save a second time: it is what lets a save be let go the
    # moment its row exists, and it means the summary and the table beside
    # it are the same numbers.
    latest_date = parsed[-1][0]["date"]
    latest_rows = sorted((r for r in rows if r["date"] == latest_date),
                         key=lambda r: -r["total_pop"])
    print(f"\nLargest nations at {latest_date}:")
    print(f"  {'tag':<5}{'pop':>12}{'accept%':>9}{'lit':>7}{'brig':>7}{'ships':>7}")
    for r in latest_rows[:8]:
        print(f"  {r['tag']:<5}{r['total_pop']:>12,}{r['accepted_pct']:>9.1f}"
              f"{r['avg_literacy'] * 100:>6.1f}%{r['brigades']:>7}"
              f"{r['ships']:>7}")
    if modded:
        print(f"\nComputed mobilisation sizes at {latest_date} "
              f"(check these against the in-game military panel):")
        for r in latest_rows[:10]:
            print(f"  {r['tag']}: {r['mobilisation_size'] * 100:.2f}%")
    print("\nWrote:")
    for path in paths:
        print(f"  {path}")


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
        return _run(run)
    finally:
        set_cancel_check(None)
        set_progress(None)
        set_report_ready(None)


def _map_ahead(args):
    """
    The process decoding the map's province bitmap while the saves are read
    (`mod_reader.raster_ahead`), or None.

    Started only for a run that goes on to draw the map: one building the
    page, and not one of the diagnostics that end the run before it. A run
    it was started for needlessly loses nothing but the core it used.
    """
    if (args.no_html or not args.mod_path or args.explain_mob_pool
            or args.check_inventions or args.inventions or args.explain_mob):
        return None
    from mod_reader import raster_ahead
    return raster_ahead(args.mod_path, args.map_scale)


def start_forkserver():
    """
    Start the process workers are made from, now, with what they will need.

    Python 3.14 makes workers on Linux by asking a forkserver to fork them,
    and starts that forkserver when the first worker is wanted -- which
    then waits while it imports the analyzer, before forking anything.
    Each worker then imported the mod reader and `spending` for itself on
    its first save. Started here, once a run knows it has work
    to do, the forkserver does its importing while this process checks the
    mod and decodes the inventions, and every worker is forked with those
    modules already in it. Where workers are made another way -- Windows,
    and anything that chose spawn or fork -- this does nothing.
    """
    import multiprocessing
    if multiprocessing.get_start_method() != "forkserver":
        return
    from multiprocessing import forkserver
    multiprocessing.set_forkserver_preload(
        ["__main__", "mod_reader", "spending"])
    try:
        forkserver.ensure_running()
    except OSError:
        pass              # the pool meets it again, and says so there


def main(run=None):
    """
    One run, as `run` declares it or as the command line does, for a
    command line: a run refused ends the process with its sentence and a
    non-zero status, which is how the command line has always said no.
    """
    try:
        return _run(run)
    except RunError as refused:
        sys.exit(str(refused))


def _run(run=None):
    """
    One run, with Python's cycle collector switched off for the length of
    it, and back on afterwards for the window, which goes on to run more.

    The collector exists for reference cycles, and a run makes next to none
    -- a warm rebuild with it off left 285 unreachable objects at the end,
    and peak memory did not move -- but it cannot know that, so it keeps
    walking everything the run is holding to find out. A run holds a great
    deal by the end: every save's remains and every row of every table, a
    few million objects, walked again and again as more arrive. That was a
    quarter of a second of a 2.3 s warm rebuild. Ordinary reference counting
    still frees everything the moment it is let go, as it always did.
    """
    was_on = gc.isenabled()
    gc.disable()
    try:
        return _main(run)
    finally:
        if was_on:
            gc.enable()


def _main(run=None):
    """`main`, with the collector already off."""
    args = run if run is not None else Run.from_command_line(command_line())
    saves_path, files = _saves_in(args)

    if args.peek:
        peek_save(files[0])
        return

    # Several campaigns at once. Each is read under the mod it was actually
    # played on, worked out from its own saves, and the results are kept side by
    # side. The heavy single-campaign report that follows is built from the
    # largest of them, so this adds a section rather than replacing anything.
    cross_payload = None
    stamp = None
    # What `--verify` reads the saves under: before any mod is chosen,
    # nothing but the game; after `--cross`, the campaign the report is about.
    verify_under = PLAIN
    if args.cross:
        # Imported here: it reads mods, and a run with nothing to do is kept
        # clear of the mod reader.
        import cross
        survey = cross.survey_cross(saves_path, args.game_root, args,
                                    verbose=not args.quiet)
        # Stamped before anything is read, and over every campaign rather
        # than the one the rest of the report is about.
        stamp = cross.cross_stamp(survey, args)
        if not args.verify and already_built(args, stamp):
            return 0
        cross_payload, files, primary_mod, verify_under = cross.run_cross(
            saves_path, survey, args, verbose=not args.quiet)
        # The rest of the report is the primary campaign's, under its mod.
        args = replace(args, mod_path=primary_mod)
        if not files:
            raise RunError("--cross found no campaigns under %s" % saves_path)

    if args.verify:
        verify_all(files, verify_under, args.jobs)
        return

    # The game and the mod settled before anything else is made or read: a
    # run that is going to be refused leaves no output folder behind.
    args, settled = _on_the_game(args)

    # Asked for now rather than after the campaign has been read. A folder
    # that cannot be made -- a typo, a drive that is not plugged in, a place
    # this user may not write -- used to surface as a stack trace out of
    # `os.makedirs` at the very end, after every save had been parsed.
    try:
        os.makedirs(args.out, exist_ok=True)
    except OSError as exc:
        raise RunError(f"Cannot write to {args.out}\n"
                 f"{exc.strerror or exc}. Choose somewhere else with --out.")

    verbose = not args.quiet
    if verbose:
        print(f"Found {len(files)} save(s).")
        if settled:
            print(settled)


    # Whether there is anything to do is asked before the mod is loaded. The
    # stamp signs the mod's files rather than reading them, so a run with
    # nothing to do never pays the second it takes to read one -- and the
    # mod reader is imported here rather than at the top for the same
    # reason: a run with nothing to do is answered in seventy milliseconds,
    # and loading that module costs ten of them. A `--cross` run was stamped
    # above, before its campaigns were read.
    signature = None
    if stamp is None:
        from mod_reader import mod_signature
        signature = mod_signature(args.mod_path)
        stamp = report_stamp(files, args, signature)
    if already_built(args, stamp):
        return 0
    # The report engine does the rest of an ordinary run in Rust, and needs
    # neither Python's workers nor its map decoded ahead; a run it hands
    # back starts both where they are wanted.
    import engine
    use_engine = engine.usable(args)
    if not use_engine:
        start_forkserver()

    # The engine reads the mod itself, beside the saves, and all a save
    # needs of it here is the head. A run the engine hands back reads the
    # rest then (`_open_mod`, below the engine's block).
    mod = loading = None
    if use_engine:
        known = _mod_head(args)
        use_engine = bool(known)
    if not use_engine:
        mod, known, loading = _open_mod(args, signature)
    map_ahead = None if use_engine else _map_ahead(args)
    # The run as the mod settles it, because the rest of a single-campaign
    # run reads these two off it -- the finishing spec, the reading below,
    # the two printed lines, and `explain.py`. `run_cross` asks the same
    # function and keeps the answer to itself, because it has a mod per
    # campaign. The stamp was taken above, from the run as it was asked for.
    #
    # Outside the `if` above: with no mod this is what turns the two "nothing
    # was asked for" Nones into the vanilla numbers, and everything after here
    # expects to find those rather than a None.
    settled_size, settled_types = finishing.mod_defaults(args, known)
    args = replace(args, pop_per_regiment=settled_size,
                   mob_types=tuple(settled_types))
    if known and verbose:
        from v2parse import VANILLA_POP_TYPES
        extra = sorted(set(known.pop_types) - VANILLA_POP_TYPES)
        print("defines.lua: POP_SIZE_PER_REGIMENT="
              f"{args.pop_per_regiment}")
        print(f"poptypes/: mobilizable = {' '.join(args.mob_types)}"
              + (f"; mod-only pop types read: {' '.join(extra)}"
                 if extra else ""))

    # How this run reads a save, handed to every read and every worker with
    # the save, and the cache key besides. Which mod a save is read under
    # changes what comes out of it, so two campaigns on two mods do not
    # share cache entries.
    reading = reading_for(args.mod_path, known, args.mob_types)

    # Oldest first, decided from each save's own first line rather than by
    # sorting them after the fact -- the campaign is now walked in one pass
    # and a pass cannot be sorted halfway through. `stream` is a generator:
    # nothing is read until the loop below asks for it. Each save's date is
    # read once, and all of them at once (`dates_of`).
    dates = dates_of(files)
    files = one_per_date(in_date_order(files, dates), dates)
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

    if use_engine:
        # Everything from here to the last table, in the engine. It reads
        # the mod and the saves at once, and hands the run back -- before
        # writing anything -- when it meets what only this program reads,
        # and then the run goes on below as it always did, with the mod
        # read here.
        forget_stamp(args.out)
        from mod_reader import _mod_root
        got = engine.run_report(
            args, files, reading, finishing.finish_spec(args, known, None, wanted),
            known, _mod_root(args.mod_path), signature, cross_payload,
            tell_progress, _tell_report_ready, stop_if_asked)
        if got is not None:
            html_path, refused = got
            if html_path and not refused:
                write_stamp(args.out, stamp)
            if refused:
                raise RunError(_refused_message(refused, html_path))
            return
        mod, _known, loading = _open_mod(args, signature)

    live = None
    if known:
        from mod_reader import settle_campaign
        # Decode invention indices from compact summaries. Population and
        # province data stay in the raw cache until the report needs them.
        walked = campaign_inventions(files, verbose=verbose, **parse_options)
        if loading is not None:
            try:
                mod = loading.result()
            except (OSError, ValueError) as exc:
                raise RunError(str(exc)) from exc
        # Saves name each nation's inventions by index. Decoding them is what
        # turns the mobilisation size from "every invention this nation could
        # have" into the ones it actually rolled.
        live, every_nation = settle_campaign(mod, walked)
        if verbose:
            _say_mod(mod, live, walked, every_nation)


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
    spec = finishing.finish_spec(args, mod, live, wanted, keep_pools=keep_pools)
    in_workers = not keep_whole
    # The pop types a row has a column for: the reading's, which the mod
    # settled above. Worked out once, for the workers and the tables alike.
    # `spending` is imported here, not at the top, for the same reason the
    # mod reader is: a run with nothing to do never reaches it.
    import spending
    pop_columns = list(reading.pop_types)

    transform = (partial(spending.spend, spec=spec, keep_fields=keep_fields,
                         pop_columns=pop_columns) if in_workers else None)
    stream = parse_saves_stream(
        files, verbose=verbose and not mod, transform=transform,
        **parse_options)
    campaign = walk_campaign(stream, spec, in_workers, pop_columns)
    # What is left in `main` is what `main` still uses: the tables it
    # starts, the two counts it prints and the saves it checks are there
    # at all. Everything the page needs travels as `campaign`.
    rows, parsed = campaign.rows, campaign.parsed

    if not parsed:
        raise RunError("No saves could be read.")

    if explain(args, mod, live, parsed):
        return

    # Everything from here on writes the report, the tables or both.
    forget_stamp(args.out)

    # `war_book` was folded save by save on the way past, above: each save
    # carries the whole war history up to its date, so collecting them first
    # and merging afterwards meant holding one overlapping copy per save --
    # fifty megabytes over thirty-eight saves, near two gigabytes over twelve
    # hundred monthly ones.

    price_rows = market.merge_prices(parsed)
    snapshot_rows = market.market_snapshot_rows(parsed)

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
    tables = Aside(lambda: write_outputs(
        campaign.text, price_rows, snapshot_rows, args.out, pop_columns))

    html_path = build_html(args, mod, campaign, price_rows,
                           snapshot_rows, cross_payload, tables, map_ahead)
    if html_path:
        _tell_report_ready(html_path)
    # Started at the compression if a report was built, and simply done
    # here if one was not.
    paths, refused = tables.result()
    if html_path:
        paths.insert(0, html_path)
        # Last, and only when every table was written, so a run that could
        # not finish is not recorded as one with nothing left to do.
        if not refused:
            write_stamp(args.out, stamp)

    if verbose:
        _say_summary(rows, parsed, price_rows, bool(mod), paths)
    if refused:
        raise RunError(_refused_message(refused, html_path))


def _refused_message(refused, html_path):
    """What a run says when a table could not be written."""
    return ("\nCould not write %s: open in another program -- on "
            "Windows a table open in Excel is locked -- or not "
            "writable here. Close it and run again.%s"
            % (", ".join(os.path.basename(p) for p in refused),
               " The report itself was written." if html_path else ""))


if __name__ == "__main__":
    # A worker on Windows starts by re-running this file, and without this it
    # would run the whole analysis again instead of waiting for a job.
    import multiprocessing
    multiprocessing.freeze_support()
    main()

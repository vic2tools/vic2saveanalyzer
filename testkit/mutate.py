#!/usr/bin/env python3
"""
Does a check actually catch the bug it was written for?

A check is only worth what it refuses. This puts a known bug back into a
*copy* of the tree, one at a time, runs the check that claims to catch it,
and reports whether the check noticed. A check that still passes with the
bug in place is not doing its job, however green it looks.

    git worktree add /tmp/mut HEAD
    cp scanner/target/release/vic2scan /tmp/mut/scanner/target/release/
    python3 testkit/mutate.py --tree /tmp/mut [--saves DIR] [name ...]

It edits the tree it is pointed at and reverts with `git checkout` between
mutations, so **point it at a worktree, never at the tree you are working
in**. It refuses to run anywhere that has uncommitted changes.

A bug put back in `scanner/` is built before its check runs (`cargo build
--release` in the tree), and the scanner as committed is copied back after,
so the next mutation starts from it.

Copy the scanner in first. A fresh worktree has no `scanner/target/`, so
every save is read in Python -- four times slower, and `parity.py` has
nothing to compare against.

Every check it uses is first run on the tree with no bug in it, and must
pass there. A check that fails anyway is reported UNTESTED for each of its
mutations rather than counted as catching them: it would have failed
whatever was put back. It exits non-zero unless every mutation is caught.

This is not one of the 24 checks and `all.py` does not run it. It is the
thing you reach for when you have written a new check and want to know
whether it would fail on the code it is supposed to reject.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outcome import SKIPPED                                 # noqa: E402

TREE = ""
SAVES = ""


def revert():
    subprocess.run(["git", "checkout", "--", "."], cwd=TREE, check=True)


def scanner_touched():
    """Whether the mutation put back is in the Rust, which must be rebuilt."""
    out = subprocess.run(["git", "diff", "--name-only"], cwd=TREE,
                         capture_output=True, text=True).stdout
    return any(line.startswith("scanner/") for line in out.splitlines())


def build_scanner():
    """Build the tree's scanner. Returns (built, what cargo said)."""
    cargo = shutil.which("cargo") or os.path.expanduser("~/.cargo/bin/cargo")
    done = subprocess.run([cargo, "build", "--release"], cwd=os.path.join(TREE, "scanner"),
                          capture_output=True, text=True)
    return done.returncode == 0, done.stderr[-2000:]


def put_back(pristine, binary):
    """
    The scanner as committed, back in place, by renaming a copy over it.

    Written into, the file cannot be while any process is still running it
    (ETXTBSY), and one run of this harness met exactly that the moment a
    check returned. A rename replaces the name and leaves a running copy
    alone. Anything of this tree's still running is named, since a check
    leaving a scanner behind is a bug of its own.
    """
    if sys.platform.startswith("linux"):
        mine = os.path.realpath(os.path.join(TREE, "scanner"))
        for pid in os.listdir("/proc"):
            try:
                exe = os.readlink(os.path.join("/proc", pid, "exe"))
            except OSError:
                continue
            if exe.startswith(mine):
                print("  note: process %s is still running %s" % (pid, exe))
    fresh = binary + ".next"
    shutil.copyfile(pristine, fresh)
    shutil.copymode(pristine, fresh)
    os.replace(fresh, binary)


def patch(path, old, new, count=1):
    """Replace `old` with `new` in TREE/path. Fails loudly if it does not match."""
    full = os.path.join(TREE, path)
    src = open(full).read()
    n = src.count(old)
    if n < 1:
        raise SystemExit("MUTATION DID NOT APPLY: %r not found in %s" % (old[:70], path))
    if count and n != count:
        raise SystemExit("MUTATION AMBIGUOUS: %r appears %d times in %s"
                         % (old[:70], n, path))
    open(full, "w").write(src.replace(old, new))


class Said(str):
    """A check's output, and whether it said it could not all run here."""
    skipped = False


def check(script, args=()):
    """
    Run a check. Returns (passed, output).

    A check that skips part of itself here (`outcome.SKIPPED`) has not
    passed: a mutation it could not have seen would be counted as blind,
    and its control run as good.
    """
    done = subprocess.run([sys.executable, os.path.join("testkit", script)] + list(args),
                          capture_output=True, text=True, cwd=TREE, timeout=900)
    said = Said(done.stdout + done.stderr)
    said.skipped = done.returncode == SKIPPED
    return done.returncode == 0, said


def argv_for(extra):
    """
    What a mutation's check is handed: "saves" means the save folder, and
    "one-save" the first save in it, for the checks that damage a copy of
    one -- handed with a round count of one, because each round is a save
    read twice over.
    """
    if extra == "saves":
        return (SAVES,)
    if extra == "one-save":
        first = next((f for f in sorted(os.listdir(SAVES))
                      if f.endswith(".v2")), "") if SAVES else ""
        return (os.path.join(SAVES, first), "1")
    return tuple(extra)


# --- the mutations -------------------------------------------------------
# Each: (name, what bug is being put back, which check should catch it,
#        a function that applies it)

MUTATIONS = []


def mutation(name, bug, catcher, args=()):
    """args may be "saves" to mean "hand this check the save folder"."""
    def wrap(fn):
        MUTATIONS.append((name, bug, catcher, args, fn))
        return fn
    return wrap


# ---- commit 8ac02e5: the five divergences between --cross and the report

@mutation("cross-regiment-size", "campaign_rows ignores the mod's POP_SIZE_PER_REGIMENT",
          "crossrows.py")
def m1():
    patch("finishing.py",
          """        pop_per_regiment = int(defines.get("POP_SIZE_PER_REGIMENT",
                                           POP_SIZE_PER_REGIMENT))""",
          """        pop_per_regiment = POP_SIZE_PER_REGIMENT""")


@mutation("cross-mob-types", "the mod's pop list overrides --mob-types instead of deferring",
          "crossrows.py")
def m2():
    patch("finishing.py", "    if mob_types is None:", "    if True:")


@mutation("cross-player-human-only", "only human=yes counts as a player; --player-nations unread",
          "crossrows.py")
def m3():
    patch("finishing.py",
          """    if told is not None:
        return set(told)
    played = {tag for tag, nat in nations.items() if nat.get("human")}""",
          """    played = {tag for tag, nat in nations.items() if nat.get("human")}""")


@mutation("cross-min-pop", "the filter silently raises --min-pop to 1", "crossrows.py")
def m4():
    patch("finishing.py",
          '            and nat["total_pop"] >= spec.min_pop)',
          '            and nat["total_pop"] >= max(1, spec.min_pop))')


@mutation("cross-player-ignores-save", "the save's own player= marker goes unread",
          "crossrows.py")
def m5():
    patch("finishing.py",
          '    return {meta["player"]} if meta.get("player") else set()',
          '    return set()')


@mutation("mod-overrides-explicit-default",
          "asking for the vanilla regiment size reads as asking for nothing",
          "crossrows.py")
def m22():
    # "the caller left it alone" decided by comparing the value against the
    # default again, so --pop-per-regiment 3000 is silently overridden.
    patch("finishing.py", "    if pop_per_regiment is None:",
          "    if pop_per_regiment in (None, POP_SIZE_PER_REGIMENT):")


# ---- commit aadea15: the record both readers fill

@mutation("record-stray-key-ignored", "a key the scanner sends with no rule is dropped in silence",
          "record.py")
def m6():
    patch("nation.py",
          """    stray = sorted(set(block) - {key for key, _f, _r in table} - extras)""",
          """    stray = []""")


@mutation("record-rule-drops-field", "a scanner field is handled by no rule at all",
          "record.py")
def m7():
    patch("nation.py",
          '    ("factory_levels", "factory_levels", _add),\n', '')


@mutation("record-replaces-container", "the fold replaces a Counter instead of filling it",
          "record.py")
def m8():
    patch("nation.py",
          """def _pairs_add_interned(nat, field, value):
    # Pairs, in the order the file first mentioned each name, because a
    # stable sort downstream breaks ties on it.
    target = nat[field]
    for key, item in value:
        target[_intern(key)] += item""",
          """def _pairs_add_interned(nat, field, value):
    target = dict(nat[field])
    for key, item in value:
        target[_intern(key)] = target.get(_intern(key), 0) + item
    nat[field] = target""")


@mutation("record-field-not-declared", "a rule names a field blank_nation does not have",
          "record.py")
def m9():
    patch("nation.py",
          '    ("ports", "ports", _add),',
          '    ("ports", "portz", _add),')


@mutation("record-rs-drift", "nation.py's save-line names drift from scanner/src/country.rs",
          "record.py")
def m10():
    patch("nation.py",
          '    "war_exhaustion": "war_exhaustion",',
          '    "war_exhaust": "war_exhaustion",')


@mutation("record-field-claimed-twice", "two rules write the same record field",
          "record.py")
def m11():
    patch("nation.py",
          '    ("armies", "armies", _add),',
          '    ("armies", "brigades", _add),')


@mutation("record-collision-across-tables",
          "a province rule and a country rule write the same record field",
          "record.py")
def m20():
    # Both folds write the same nation, so the two tables must be disjoint.
    # `record.py` checks for a field claimed twice within one table only.
    patch("nation.py", '    ("ports", "ports", _add),',
                       '    ("ports", "states", _add),')


@mutation("naval-base-int-becomes-float",
          "a nation with no naval base carries 0.0 where the CSV wrote 0",
          "parity.py")
def m21():
    # `_add_if` exists so an untouched int stays an int. Nothing compares
    # types, and in Python 0 == 0.0, so every value check steps over this --
    # while 1,999 of the 4,271 rows of nations_timeseries.csv move, measured
    # on 103 saves with --no-cache on both sides.
    patch("nation.py",
          '    ("naval_base_levels", "naval_base_levels", _add_if),',
          '    ("naval_base_levels", "naval_base_levels", _add),')


# ---- the reading a save is read under, and the cache key it makes

@mutation("python-reader-ignores-reading",
          "the Python reader keeps the plain pop types whatever the reading "
          "says, so a mod's own pop type vanishes from every total",
          "caching.py")
def m12():
    patch("readsave.py", "    pop_types = frozenset(reading.pop_types)\n",
          "    pop_types = frozenset(PLAIN.pop_types)\n")


@mutation("worker-reads-plain",
          "a worker reads its save under the plain reading instead of the "
          "run's, so a campaign read in parallel loses the mod's pops and "
          "reforms", "caching.py")
def m13():
    patch("readfolder.py",
          "        meta, nations, pickled = read_save(path, reading)\n",
          "        from readsave import PLAIN\n"
          "        meta, nations, pickled = read_save(path, PLAIN)\n")


@mutation("reading-key-drops-mod", "the cache key stops naming the mod",
          "caching.py")
def m14():
    patch("readsave.py",
          '        ((os.path.abspath(mod_path) if mod_path else "no-mod")',
          '        (("no-mod")')


@mutation("reading-key-drops-pop-types", "the cache key stops naming the pop types",
          "caching.py")
def m15():
    patch("readsave.py",
          '         + "|" + ",".join(sorted(pop_types))',
          '         + "|"')


@mutation("reading-key-drops-mob-types", "the cache key stops naming the mobilizable types",
          "caching.py")
def m16():
    patch("readsave.py",
          '         + "|" + ",".join(sorted(mob_types))',
          '         + ""')


# ---- the parse cache key, which hashed six files named by hand and not the
# ---- one the fold had moved into

@mutation("parse-key-hand-list",
          "the parse cache key goes back to six files by hand, without nation.py",
          "caching.py")
def m23():
    # Exactly what the key was before it was derived. `nation.py` fills every
    # parsed save, and an edit to it was served out of the old parses.
    patch("readfolder.py",
          """    source = cacheio.source_fingerprint(*cacheio.sources_reached(__file__))""",
          """    import fastscan, readsave, tech_groups, v2parse
    source = cacheio.source_fingerprint(
        __file__, readsave.__file__, v2parse.__file__, fastscan.__file__,
        tech_groups.__file__, cacheio.__file__)""")


@mutation("parse-key-too-wide",
          "the reader imports the finishing, and the parse cache key follows it",
          "caching.py")
def m24():
    # The opposite mistake. The key is everything readfolder reaches, so
    # readfolder importing the finishing -- which reads no save, it spends
    # one -- puts the finishing, the mod rules and explain.py in the key, and
    # rewording a label in any of them throws every cached save away.
    patch("readfolder.py", "import cacheio\nfrom cacheio import load as _cache_read\n",
          "import cacheio\nimport finishing\nfrom cacheio import load as _cache_read\n")


# ---- the workers, which Windows starts as fresh interpreters

@mutation("spawn-job-not-picklable",
          "the finishing reaches the workers as a lambda, so under spawn none start",
          "spawned.py", "saves")
def m25():
    # Fork inherits the job; spawn has to send it by name, and a lambda has
    # none. The pool fails at the first submit, the analyzer reads every save
    # itself, and the files come out identical -- so a check comparing them
    # passed while Windows read a campaign on one core.
    patch("vic2_analyzer.py",
          "    transform = (partial(spending.spend, spec=spec, keep_fields=keep_fields,\n"
          "                         pop_columns=pop_columns) if in_workers else None)",
          "    transform = ((lambda m, n: spending.spend(m, n, spec, keep_fields,\n"
          "                                              pop_columns)) if in_workers else None)")


# ---- commit 8caa343: a mod refusing to guess what it has not read

@mutation("mod-answers-before-decoding", "index_base answers None instead of raising",
          "mobrate.py")
def m17():
    patch("mod_reader.py",
          """        if not self._indices_read:
            raise RuntimeError(""",
          """        if not self._indices_read:
            return self._index_base
        if False:
            raise RuntimeError(""")


@mutation("mod-born-decoded", "a fresh mod claims its indices were already decoded",
          "mobrate.py")
def m18():
    patch("mod_reader.py",
          """        self._index_base = None
        self._indices_read = False""",
          """        self._index_base = None
        self._indices_read = True""")


# ---- the --cross stamp, which covered only the campaign the report is about

@mutation("cross-stamp-primary-only",
          "the --cross stamp covers only the largest campaign, so a new save "
          "in another is answered with the old report", "staleness.py")
def m27():
    patch("cross.py",
          '    read = [entry for entry in found if entry.mod_path]\n',
          '    read = [max(found, key=lambda entry: len(entry.files))]\n')


# ---- a run that rewrote the files and did not finish left the old stamp

@mutation("stamp-outlives-unfinished-run",
          "the stamp is not taken away before the files it describes are "
          "rewritten, so a run that dies -- or --no-html -- leaves it vouching "
          "for files it never saw", "staleness.py")
def m28():
    patch("vic2_analyzer.py",
          "    # Everything from here on writes the report, the tables or both.\n"
          "    forget_stamp(args.out)\n", "")


@mutation("locked-table-stack-trace",
          "a table open in Excel ends the run in a stack trace", "staleness.py")
def m29():
    patch("vic2_analyzer.py",
          "        except PermissionError:\n            refused.append(path)",
          "        except ZeroDivisionError:\n            refused.append(path)")


# ---- who is at war, for a trigger, taken from the history's joins

@mutation("at-war-from-joins",
          "war = yes is answered from the history's joins, which keep a nation "
          "that made peace and miss one put into the war by hand", "mobrate.py")
def m30():
    patch("modrules.py", 'at_war.update(war.get("fighting") or (list(',
          'at_war.update((list(')


# ---- --explain-mob judged war triggers after the wars had been thrown away

@mutation("explain-without-wars",
          "a save kept whole for the diagnostics loses its wars, so "
          "--explain-mob explains a rate without the war modifiers in it",
          "mobrate.py")
def m31():
    patch("vic2_analyzer.py",
          "            fold_wars(war_book, wars)\n",
          "            fold_wars(war_book, wars)\n            meta[\"wars\"] = ()\n")


# ---- a war skipped as a repeat when it had changed

@mutation("packed-fold-skips-by-war",
          "a war already in the book is skipped whatever its record says, "
          "so a war still being fought stops gaining battles",
          "warfold.py", "saves")
def m46():
    patch("wars.py",
          "        if last.get(name) == blob:\n            continue\n",
          "        if name in last:\n            continue\n")


# ---- a war over before the first save was judged by that save alone

@mutation("goal-judged-before-first-save",
          "a war that ended before the first save has its goal judged by "
          "that save against itself, and reads 'none taken'", "edges.py")
def m55():
    patch("wars.py", "                and ledger_dates[0] >= year_fraction(end)):",
          "                and False):")


# ---- an empty table was skipped, and the last run's copy stayed

@mutation("empty-table-left-stale",
          "a table with nothing in it this run is not written, so the last "
          "run's copy stays in the folder", "staleness.py")
def m32():
    patch("vic2_analyzer.py",
          "    for name, data, cols in tables:\n        path = os.path.join(outdir, name)",
          "    for name, data, cols in tables:\n"
          "        if not (data or \"\".join(text.get(name, ()))) and name != "
          "\"nations_timeseries.csv\":\n            continue\n"
          "        path = os.path.join(outdir, name)")


# ---- two saves with the same date were both read into the tables

@mutation("same-date-read-twice",
          "two saves with the same in-game date are both read, doubling "
          "their rows in every table while the report shows one",
          "edges.py")
def m33():
    patch("vic2_analyzer.py",
          "    files = one_per_date(in_date_order(files, dates), dates)",
          "    files = in_date_order(files, dates)")


# ---- one worker dying took the whole run down

@mutation("dead-worker-ends-run",
          "a worker killed part-way breaks the pool, and the run ends in a "
          "stack trace instead of reading the rest one at a time",
          "noworkers.py")
def m34():
    patch("readfolder.py",
          "                except (BrokenProcessPool, MemoryError) as exc:",
          "                except (ZeroDivisionError,) as exc:")


@mutation("verify-dies-with-worker",
          "a worker that dies during --verify ends the check in a stack "
          "trace instead of checking the rest one at a time", "noworkers.py")
def m49():
    patch("explain.py",
          "        except (BrokenProcessPool, OSError, RuntimeError) as exc:",
          "        except (ZeroDivisionError,) as exc:")


# ---- a run with no mod carries NO_MOD, which has to read as no mod

@mutation("no-mod-is-a-mod",
          "NO_MOD answers true, so a run with no mod folder goes looking for "
          "the rules, the inventions and the flags of a mod that is not there",
          "edges.py")
def m53():
    patch("mod_reader.py", "        return self.path is not None\n",
          "        return True\n")


# ---- a run refused in a sentence, which the window has to show as one

@mutation("window-shows-refusal-as-traceback",
          "the window does not catch a refused run, so the sentence the "
          "analyzer refused it with reaches the log as a traceback",
          "window.py", "saves")
def m54():
    patch("gui.py", "        except RunError as refused:\n",
          "        except ZeroDivisionError as refused:\n")


# ---- the event-flag rule, which the keeper and --cross each had a copy of

@mutation("flag-gap-too-wide",
          "the flag gap that tells two games apart is ten times too wide, so "
          "a second game joins the first", "histories.py")
def m50():
    patch("savehead.py", "FLAG_GAP = 6\n", "FLAG_GAP = 60\n")


@mutation("keeper-ignores-flag-gap",
          "the keeper files a save with the campaign whatever its flags say",
          "histories.py")
def m51():
    patch("keeper.py", "        elif gap < FLAG_GAP:\n", "        elif True:\n")


@mutation("cross-names-no-stray",
          "--cross never names a save from another game in a campaign folder",
          "histories.py")
def m52():
    patch("cross.py", "        if worst >= FLAG_GAP:\n", "        if False:\n")


# ---- pressing Analyze erased the token; a refused token could not be replaced

@mutation("analyze-erases-share-settings",
          "remembering the window's paths writes them as the whole settings "
          "file, erasing the GitHub token and the report host", "window.py",
          "saves")
def m35():
    patch("settings.py", "    held = load(path)\n", "    held = {}\n")


@mutation("refused-token-kept",
          "a token GitHub refuses stays held and is handed back on every press",
          "sharing.py")
def m36():
    patch("app.py", "            settings.remember(github_token=None)\n", "")


# ---- a mod file named in other case was read beside the game's

@mutation("mod-file-case-counted-twice",
          "a mod's Army_Inventions.txt is read beside the game's "
          "army_inventions.txt, where Windows reads only the mod's",
          "modcache.py")
def m37():
    patch("mod_reader.py",
          "            chosen[name.lower()] = (name, os.path.join(target, name))",
          "            chosen[name] = (name, os.path.join(target, name))")


# ---- the scanner, started from the windowed executable, opened a console

@mutation("scanner-opens-console-window",
          "on Windows the scanner is started without CREATE_NO_WINDOW, so the "
          "windowed executable flashes a console window per save",
          "packing.py")
def m38():
    patch("fastscan.py",
          "                            stderr=stderr, creationflags=_no_window())",
          "                            stderr=stderr)")


# ---- a name out of a save ran as script in the report

@mutation("name-runs-as-script",
          "a war named <img onerror=...> runs its script when the report's "
          "Wars tab draws", "boots.py", ("--hostile",))
def m39():
    patch("report.py",
          '    raw = raw.replace("<", "\\\\u2039").replace(">", "\\\\u203a")\n', "")


# ---- a mod kept away from its game was read with nothing beneath it

@mutation("mod-forgets-its-game",
          "the mod reader ignores the install containing its mod folder",
          "modcache.py")
def m57():
    patch("mod_reader.py", "    return root\n\n\ndef _map_source",
          "    return None\n\n\ndef _map_source")


@mutation("run-never-pairs-a-game",
          "the run ignores the game and mod validation", "edges.py")
def m58():
    patch("vic2_analyzer.py",
          "        mod_path, game = settle_game(args.mod_path, args.game_root)",
          "        mod_path, game = args.mod_path or args.game_root, args.game_root")


# ---- a war's detail was drawn by nothing any check ever clicked

@mutation("war-infobox-throws",
          "the infobox a war opens into throws, where no check had ever "
          "opened a war", "boots.py", ("--hostile",))
def m56():
    patch("template.py", "  const opening = warOpening(w);\n",
          "  const opening = warOpening(w.unset.start);\n")


# ---- publishing: the token followed redirects, and failures came out raw

@mutation("token-follows-redirect",
          "a redirect to another address is handed the GitHub token",
          "sharing.py")
def m40():
    patch("publish.py",
          "        with _OPENER.open(request, timeout=TIMEOUT) as answer:",
          "        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:")


@mutation("publish-stall-raw",
          "GitHub stalling mid-answer raises a bare TimeoutError, not a sentence",
          "sharing.py")
def m41():
    patch("publish.py",
          "    except (OSError, http.client.HTTPException) as err:\n"
          "        # Once connected",
          "    except ZeroDivisionError as err:\n        # Once connected")


# ---- the keeper's "Open the folder" worked on Windows alone

@mutation("keeper-folder-windows-only",
          "the keeper's Open the folder calls os.startfile, which exists only "
          "on Windows", "window.py", "saves")
def m42():
    patch("keeper_gui.py",
          "            keeper.open_with_system(where)\n        except OSError as err:",
          "            os.startfile(where)\n        except (OSError, AttributeError) as err:")


# ---- the mod cache key, written by hand, the way the parse key went wrong

@mutation("mod-key-hand-list",
          "the mod cache key is a hand-written list that leaves out the parser "
          "a mod is read with", "modcache.py")
def m43():
    patch("mod_reader.py",
          "    return cacheio.source_fingerprint(*cacheio.sources_reached(__file__))",
          "    return cacheio.source_fingerprint(__file__, cacheio.__file__)")


# ---- the settings the report stamp covers, which were fifteen names by hand

@mutation("stamp-leaves-out-min-pop",
          "--min-pop is declared as not changing the report, so a run that "
          "changes it is answered with the old one", "staleness.py")
def m44():
    # REVIEW.md §25, in the form it can take now: the declaration is wrong
    # rather than a list. Taken off the old hand-written list it passed
    # every check there was.
    patch("run.py", "    min_pop: int = _setting(0, report=True)",
          "    min_pop: int = _setting(0, report=False)")


@mutation("stamp-ignores-declared-setting",
          "the stamp hashes fewer settings than Run declares", "staleness.py")
def m45():
    patch("stamp.py", "    for name in REPORTED:\n",
          "    for name in REPORTED[:-2]:\n")


# ---- a save cut short was read as a whole one

@mutation("cut-save-read-as-whole",
          "a save that stops part-way through is read as if it were whole",
          "mangled.py", "one-save")
def m26():
    # Two thirds of a save read as 34 of its 41 nations with no army, no
    # navy and no technology, and every war gone -- and both readers agreed,
    # so the parity check passed too.
    patch("v2parse.py", '    if not fh.read().rstrip().endswith(b"}"):',
          "    if False:")


# ---- commit d2fa289: the parity check that had stopped comparing

@mutation("parity-scanner-on-both-sides", "the 'slow' read quietly uses the Rust scanner too",
          "parity.py")
def m19():
    patch("testkit/readboth.py",
          "use_scanner=False", "use_scanner=True")


# ---- the two smaller parity checks, which compared the scanner with itself

@mutation("countries-python-reader-unseen",
          "the Python country reader doubles every country number, where "
          "countries.py never ran the Python reader at all", "countries.py")
def m47():
    # Prestige, infamy and the treasury are in no expectation of the check,
    # so only the comparison with the scanner can see this.
    patch("readsave.py", "                nat[numerics[key]] = to_float(clean)",
          "                nat[numerics[key]] = to_float(clean) * 2")


@mutation("awkward-python-reader-unseen",
          "the Python province reader doubles every pop's literacy, where "
          "awkward.py never ran the Python reader at all", "awkward.py")
def m48():
    # Literacy is in no expectation of the check, so only the comparison
    # with the scanner can see this.
    patch("readsave.py", "        literate = to_float(pop[_POP_LITERACY]) * size",
          "        literate = to_float(pop[_POP_LITERACY]) * size * 2")


# ---- the map's province bitmap, read a run at a time and decoded ahead


@mutation("raster-runs-merged-by-colour",
          "two colours naming one province, or a run carrying into the next "
          "row, ship as two runs where the map had one", "raster.py")
def m59():
    patch("mod_reader.py", "                if pid == last:",
          "                if False:")


@mutation("raster-red-channel-dropped",
          "the bitmap is read without its red channel, so provinces told "
          "apart only by red come out as one", "raster.py")
def m60():
    patch("mod_reader.py", "            wide[2::4] = row[2:span:step]\n", "")


@mutation("raster-samples-wrong-rows",
          "a scaled map samples every row instead of every scale-th, and "
          "draws the top of the world stretched", "raster.py")
def m61():
    patch("mod_reader.py", "fh.seek(offset + (oy * scale) * stride)",
          "fh.seek(offset + oy * stride)")


@mutation("raster-ahead-when-cached",
          "a run decodes the map in another process even when its entry is "
          "already cached", "raster.py")
def m62():
    patch("mod_reader.py",
          "    if not slot or (os.path.isfile(slot) and os.path.isfile(_text_slot(slot))):",
          "    if not slot:")


@mutation("raster-text-miscounted",
          "the map's runs are spelled with every count one short, and the "
          "page draws a map that drifts a cell further each run", "raster.py")
def m67():
    patch("mod_reader.py",
          '    text = " ".join(_b36(p) if c == 1 else _b36(p) + "." + _b36(c)',
          '    text = " ".join(_b36(p) if c == 1 else _b36(p) + "." + _b36(c - 1)')


@mutation("anchor-nearer-column-skipped",
          "a province's anchor measures only the column left of its middle, "
          "and lands a cell off where the right one is nearer", "raster.py")
def m63():
    patch("mod_reader.py",
          "        for x in (left, min(left + 1, x1)) if left < x1 else (left,):",
          "        for x in (left,):")


@mutation("anchor-sum-of-first-columns",
          "a stretch of a row counts only its first column toward the "
          "province's middle", "raster.py")
def m64():
    patch("mod_reader.py", "        got[0] += (x0 + x1) * n // 2",
          "        got[0] += x0 * n")


@mutation("anchor-run-not-split-at-row-end",
          "a run carrying into the next row is measured as one stretch "
          "running off the edge of the map", "raster.py")
def m65():
    patch("mod_reader.py", "                    x1 = min(width, x0 + end - at) - 1",
          "                    x1 = x0 + end - at - 1")


@mutation("positions-cache-ignores-edits",
          "an edited positions.txt keeps being served from the cache",
          "raster.py")
def m66():
    patch("mod_reader.py",
          '        f"{os.path.abspath(target)}|{info.st_size}|{info.st_mtime_ns}|{version}"',
          '        f"{os.path.abspath(target)}|{version}"')


@mutation("engine-callback-error-lost",
          "the engine relay silently drops callback failures", "engine_runtime.py")
def m68():
    patch("engine.py", "        if self.failure is not None:\n            raise self.failure",
          "        if False:\n            raise self.failure")


@mutation("fixture-writes-through-link",
          "a test fixture truncates a real file through a symlink", "engine_runtime.py")
def m69():
    patch("testkit/matching.py", "        if os.path.islink(check):",
          "        if False:")



@mutation("engine-leaks-handoff-files",
          "a stopped engine leaves its mod and settings files behind", "engine_runtime.py")
def m70():
    patch("engine.py", "                os.remove(path)", "                pass")


# ---- the engine's mod reader, which is Rust held to mod_reader.py

@mutation("modread-ascii-words",
          "the pattern matcher's \\w takes ASCII only, where Python's takes the "
          "latin-1 letters too", "modread.py", ("--rounds", "40"))
def m71():
    patch("scanner/src/pyre.rs",
          "        | 0xb9 | 0xba | 0xbc..=0xbe | 0xc0..=0xd6 | 0xd8..=0xf6 | 0xf8..=0xff)",
          "        | 0xb9 | 0xba | 0xbc..=0xbe)")


@mutation("modread-lazy-is-greedy",
          "a lazy repeat is tried longest first", "modread.py", ("--rounds", "40"))
def m72():
    patch("scanner/src/pyre.rs", "                            for c in *min..=run {",
          "                            for c in (*min..=run).rev() {")


@mutation("modread-file-case-counted-twice",
          "the Rust reads a mod's Army_Tech.txt beside the game's army_tech.txt",
          "modread.py", ("--rounds", "40"))
def m73():
    patch("scanner/src/engine/modread.rs",
          "                chosen.set(lower(&name), (name, full));",
          "                chosen.set(name.clone(), (name, full));")


@mutation("modread-no-underscores",
          "the Rust's float() refuses 1_000, which Python reads as a thousand",
          "modread.py", ("--rounds", "40"))
def m74():
    patch("scanner/src/engine/modread.rs",
          "    let t = no_underscores(num_trim(s))?;",
          "    let t = num_trim(s).to_vec();")


@mutation("modread-block-name-empty",
          "a block where a flag type belongs reads as nothing, where Python "
          "keeps its repr", "modread.py", ("--rounds", "40"))
def m75():
    patch("scanner/src/engine/modread.rs",
          "                Some(v) => unquote(unquote(&str_of(v))).to_vec(),",
          "                Some(V::Str(v)) => unquote(v).to_vec(),\n"
          "                Some(_) => Vec::new(),")


@mutation("modread-ellipsis-is-space",
          "the localisation's 0x85 is stripped as a space, where Windows-1252 "
          "makes it an ellipsis", "modread.py", ("--rounds", "40"))
def m76():
    patch("scanner/src/engine/modread.rs",
          "    let sp = |c: u8| matches!(c, 0x09..=0x0d | 0x1c..=0x20 | 0xa0);",
          "    let sp = |c: u8| matches!(c, 0x09..=0x0d | 0x1c..=0x20 | 0x85 | 0xa0);")


@mutation("modread-last-name-wins",
          "a name defined twice in the localisation takes the later one",
          "modread.py", ("--rounds", "40"))
def m77():
    patch("scanner/src/engine/modread.rs",
          "            if wanted.contains(&l.key) && !out.contains_key(&l.key) {",
          "            if wanted.contains(&l.key) {")


@mutation("modread-kept-copy-unsigned",
          "the engine keeps its read of a mod without the mod's signature in "
          "the key, so an edited mod is served from the old read",
          "modread.py", ("--rounds", "1"))
def m78():
    patch("scanner/src/engine/cache.rs",
          '    let key = format!("mod|{}|{}|{}", path, signature, store.version);',
          '    let key = format!("mod|{}|{}|{}", path, signature.len() * 0, store.version);')


# ---- the run's front end in Rust, held to the Python's

@mutation("front-stamp-ignores-settings",
          "the Rust's report stamp leaves the settings out, so a changed "
          "--min-pop is answered with the old report", "frontcheck.py")
def m79():
    patch("scanner/src/front/mod.rs", "    digest.update(settings.as_bytes());\n", "")


@mutation("front-keeps-first-of-a-date",
          "two saves of one date keep the first-named rather than the later",
          "frontcheck.py")
def m80():
    patch("scanner/src/front/mod.rs", "            *kept.last_mut().unwrap() = path;\n", "")


@mutation("front-no-expandvars",
          "$VAR in a path is taken literally", "frontcheck.py")
def m81():
    patch("scanner/src/front/mod.rs",
          "    let saves_path = pypath::expanduser(&pypath::expandvars(&args.saves));",
          "    let saves_path = pypath::expanduser(&args.saves);")


@mutation("walk-navy-not-entered",
          "a save laid out another way loses the ships and embarked armies "
          "inside its navies", "frontcheck.py")
def m82():
    patch("scanner/src/engine/walk.rs",
          '        } else if key == b"army" || key == b"navy" {',
          '        } else if key == b"army" {')


@mutation("walk-colonies-ignored",
          "a save laid out another way reads no state as colonial",
          "frontcheck.py")
def m83():
    patch("scanner/src/engine/walk.rs",
          '                        let colonial = get(&block, b"is_colonial").is_some();',
          '                        let colonial = false;')


def main():
    global TREE, SAVES
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("names", nargs="*", help="only these mutations")
    ap.add_argument("--tree", required=True,
                    help="a git worktree to mutate -- NOT your working tree")
    ap.add_argument("--saves", default="",
                    help="a folder of .v2 saves, for the checks that want one")
    args = ap.parse_args()
    TREE = os.path.abspath(args.tree)
    SAVES = args.saves
    if not os.path.isdir(os.path.join(TREE, "testkit")):
        raise SystemExit("%s does not look like a checkout of this tree" % TREE)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=TREE,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit(
            "%s has uncommitted changes. This reverts with `git checkout` "
            "between mutations and would throw them away:\n%s" % (TREE, dirty))
    if not os.path.exists(os.path.join(TREE, "scanner/target/release/vic2scan")):
        print("note: no scanner in %s, so parity.py compares Python with "
              "Python. Copy scanner/target/release/vic2scan in first.\n" % TREE)
    chosen = [m for m in MUTATIONS if not args.names or m[0] in args.names]
    # The scanner as committed, to put back after each bug put into it.
    binary = os.path.join(TREE, "scanner/target/release/vic2scan")
    pristine = binary + ".pristine"
    if os.path.exists(binary):
        shutil.copyfile(binary, pristine)
        shutil.copymode(binary, pristine)

    # Every check first runs on the tree with no bug in it, and has to pass.
    # A check that fails anyway fails for some reason of its own, and then
    # failing with a bug in place says nothing about the bug. This harness
    # reported five mutations "caught" that way: it handed `caching.py` the
    # save folder as an argument, `unittest` read the folder as the name of
    # a test, and every run failed on that before any test had been tried.
    revert()
    control = {}
    for _name, _bug, catcher, extra, _fn in chosen:
        if (catcher, extra) not in control:
            control[(catcher, extra)] = check(catcher, argv_for(extra))
    for (catcher, extra), (passed, out) in control.items():
        if not passed:
            print("CONTROL FAILED: %s %s %s, so its mutations are not "
                  "tried:\n%s\n"
                  % (catcher, " ".join(argv_for(extra)),
                     "cannot all run on this machine" if out.skipped
                     else "fails with no bug put back",
                     "\n".join("      " + l for l in out.splitlines()[-25:])))

    print("%-34s %-10s %s" % ("MUTATION", "VERDICT", "BUG PUT BACK"))
    print("-" * 100)
    results = []
    for name, bug, catcher, extra, fn in chosen:
        if not control[(catcher, extra)][0]:
            print("%-34s %-10s %s  [%s]" % (name, "UNTESTED", bug, catcher))
            results.append((name, "UNTESTED", bug, catcher, ""))
            continue
        revert()
        try:
            fn()
        except SystemExit as e:
            print("%-34s %-10s %s" % (name, "NOAPPLY", e))
            results.append((name, "NOAPPLY", bug, catcher, ""))
            continue
        # A bug put back in the Rust is only there once it is built, and
        # the scanner the other checks use is put back after.
        rust = scanner_touched()
        if rust:
            built, said = build_scanner()
            if not built:
                print("%-34s %-10s %s" % (name, "NOAPPLY", "does not build:\n" + said))
                results.append((name, "NOAPPLY", bug, catcher, ""))
                revert()
                put_back(pristine, binary)
                continue
        try:
            passed, out = check(catcher, argv_for(extra))
        except subprocess.TimeoutExpired:
            passed, out = True, "TIMEOUT"
        if rust:
            revert()
            put_back(pristine, binary)
        verdict = "BLIND" if passed else "caught"
        print("%-34s %-10s %s  [%s]" % (name, verdict, bug, catcher))
        results.append((name, verdict, bug, catcher, out))
    revert()

    print("\n" + "=" * 100)
    blind = [r for r in results if r[1] == "BLIND"]
    noapply = [r for r in results if r[1] == "NOAPPLY"]
    untested = [r for r in results if r[1] == "UNTESTED"]
    caught = len(results) - len(blind) - len(noapply) - len(untested)
    print("%d mutations: %d caught, %d BLIND, %d did not apply, %d untested"
          % (len(results), caught, len(blind), len(noapply), len(untested)))
    for name, _v, bug, catcher, out in blind:
        print("\n--- BLIND: %s (%s)\n    bug: %s\n    check output:\n%s"
              % (name, catcher, bug, "\n".join("      " + l for l in out.splitlines()[-25:])))
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

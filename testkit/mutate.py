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

Copy the scanner in first. A fresh worktree has no `scanner/target/`, and
with no scanner every run is refused, so this refuses to start.

Every check it uses is first run on the tree with no bug in it, and must
pass there. A check that fails anyway is reported UNTESTED for each of its
mutations rather than counted as catching them: it would have failed
whatever was put back. It exits non-zero unless every mutation is caught.

This is not one of the checks and `all.py` does not run it. It is the
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
    """Whether the mutation put back is in the Rust, which must be rebuilt --
    or in the page, which `scanner/build.rs` builds into it."""
    out = subprocess.run(["git", "diff", "--name-only"], cwd=TREE,
                         capture_output=True, text=True).stdout
    return any(line.startswith("scanner/") or line == "template.py"
               for line in out.splitlines())


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
    with open(full, encoding="utf-8") as fh:
        src = fh.read()
    n = src.count(old)
    if n < 1:
        raise SystemExit("MUTATION DID NOT APPLY: %r not found in %s" % (old[:70], path))
    if count and n != count:
        raise SystemExit("MUTATION AMBIGUOUS: %r appears %d times in %s"
                         % (old[:70], n, path))
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(src.replace(old, new))


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


# ---- the window, the keeper, publishing and the fixtures, which stay Python

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


@mutation("scanner-opens-console-window",
          "on Windows the window starts the scanner without CREATE_NO_WINDOW, "
          "so the windowed executable flashes a console window per run",
          "packing.py")
def m38():
    patch("vic2_analyzer.py", "            status = _relayed(argv, fastscan._no_window(), hosted)",
          "            status = _relayed(argv, 0, hosted)")


# ---- a name out of a save ran as script in the report


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


@mutation("stamp-leaves-out-min-pop",
          "--min-pop is declared as not changing the report, so a run that "
          "changes it is answered with the old one", "staleness.py")
def m44():
    # REVIEW.md §25, in the form it can take now: the declaration is wrong
    # rather than a list. Taken off the old hand-written list it passed
    # every check there was.
    patch("run.py", "    min_pop: int = _setting(0, report=True)",
          "    min_pop: int = _setting(0, report=False)")


@mutation("relay-progress-lost",
          "the window's relay passes @progress on as text instead of moving the bar",
          "engine_runtime.py")
def m68():
    patch("vic2_analyzer.py", '                    if word == "@progress":',
          '                    if word == "@progresss":')


@mutation("fixture-writes-through-link",
          "a test fixture truncates a real file through a symlink", "engine_runtime.py")
def m69():
    patch("testkit/matching.py", "        if _linked(check):",
          "        if False:")


@mutation("stop-leaves-scanner-running",
          "Stop raises in the window but leaves the scanner reading",
          "engine_runtime.py")
def m70():
    patch("vic2_analyzer.py", "        if proc.poll() is None:\n            proc.kill()\n", "")


# ---- what the Python fallback was held to, put back into the Rust that
# ---- does it now: --cross and the report reading a campaign the same way

@mutation("cross-min-pop", "the filter silently raises --min-pop to 1", "crossrows.py")
def r1():
    patch("scanner/src/engine/finish.rs", "        wanted && nat.total_pop >= self.min_pop\n",
          "        wanted && nat.total_pop >= self.min_pop.max(1)\n")


@mutation("cross-player-nations-unread", "--player-nations goes unread", "crossrows.py")
def r2():
    patch("scanner/src/engine/finish.rs",
          "    if let Some(t) = told {\n        return t.iter().cloned().collect();\n    }\n", "")


@mutation("cross-player-ignores-save", "the save's own player= marker goes unread",
          "crossrows.py")
def r3():
    patch("scanner/src/engine/finish.rs", "    if !meta.player.is_empty() {", "    if false {")


@mutation("mod-overrides-explicit-default",
          "asking for the vanilla regiment size reads as asking for nothing", "crossrows.py")
def r4():
    patch("scanner/src/front/mod.rs", "    let pop_per_regiment = match args.pop_per_regiment {",
          "    let pop_per_regiment = match args.pop_per_regiment"
          ".filter(|n| *n != POP_SIZE_PER_REGIMENT) {")


@mutation("cross-regiment-size", "the mod's POP_SIZE_PER_REGIMENT is ignored", "crossrows.py")
def r5():
    patch("scanner/src/front/mod.rs",
          "            Some(v) if v.is_finite() && v.abs() < 9.0e18 => v.trunc() as i64,",
          "            Some(v) if v.is_finite() && v.abs() < 9.0e18 => POP_SIZE_PER_REGIMENT,")


@mutation("cross-mob-types", "the mod's pop list overrides --mob-types instead of deferring",
          "crossrows.py")
def r6():
    patch("scanner/src/front/mod.rs",
          "    let mob_types: Vec<String> = match &args.mob_types {\n        Some(t) => t.clone(),\n"
          "        None => {",
          "    let mob_types: Vec<String> = match &args.mob_types {\n        _ => {")


# ---- who is at war, and the diagnostic that explains the rate

@mutation("at-war-from-joins",
          "war = yes is answered from the history's joins, which keep a nation "
          "that made peace and miss one put into the war by hand", "mobrate.py")
def r7():
    patch("scanner/src/engine/rules.rs", "        if !war.fighting.is_empty() {",
          "        if false {")


@mutation("explain-without-wars",
          "the save kept for the diagnostics loses its wars, so --explain-mob "
          "explains a rate without the war modifiers in it", "mobrate.py")
def r8():
    patch("scanner/src/engine/explain.rs", "    let world = rules::save_world(meta, m);",
          "    let world = rules::save_world(&crate::engine::model::Meta "
          "{ wars: Vec::new(), ..meta.clone() }, m);", count=0)


# ---- the stamp, and what a run that does not finish leaves

@mutation("cross-stamp-primary-only",
          "the --cross stamp covers only the largest campaign, so a new save "
          "in another is answered with the old report", "staleness.py")
def r9():
    patch("scanner/src/front/cross.rs",
          "    let read: Vec<&Surveyed> = found.iter().filter(|e| e.mod_path.is_some()).collect();",
          "    let read: Vec<&Surveyed> = found.iter().max_by_key(|e| e.files.len())"
          ".into_iter().collect();")


@mutation("stamp-outlives-unfinished-run",
          "the stamp is not taken away before the files it describes are "
          "rewritten, so a run that dies -- or --no-html -- leaves it vouching "
          "for files it never saw", "staleness.py")
def r10():
    patch("scanner/src/front/mod.rs", "        forget_stamp(&args.out);\n", "")


@mutation("locked-table-not-refused",
          "a table open in Excel is not refused in a sentence", "frontcheck.py")
def r11():
    patch("scanner/src/engine/report.rs",
          "            Err(e) if held_elsewhere(&e) => refused.push(shown),",
          "            Err(e) if false && held_elsewhere(&e) => refused.push(shown),")


@mutation("stamp-ignores-a-setting",
          "the stamp leaves --min-pop out of the settings it hashes", "staleness.py")
def r15():
    patch("scanner/src/front/mod.rs", '        ("min_pop", J::Int(args.min_pop)),\n', "")


@mutation("empty-table-left-stale",
          "a table with nothing in it this run is not written, so the last "
          "run's copy stays in the folder", "staleness.py")
def r13():
    patch("scanner/src/engine/report.rs", "    for (k, name, cols) in order {\n",
          "    for (k, name, cols) in order {\n"
          "        if k > 0 && k < 100 && c.text[k].iter().all(|s| s.is_empty()) { continue; }\n")


# ---- the edges a campaign has

@mutation("goal-judged-before-first-save",
          "a war that ended before the first save has its goal judged by "
          "that save against itself, and reads 'none taken'", "edges.py")
def r12():
    patch("scanner/src/engine/wars.rs",
          "        if !end.is_empty() && !ledger_dates.is_empty() && ledger_dates[0] >= year_fraction(&end) {",
          "        if false {")


@mutation("same-date-read-twice",
          "two saves with the same in-game date are both read, doubling "
          "their rows in every table while the report shows one", "edges.py")
def r14():
    patch("scanner/src/front/mod.rs",
          "            *kept.last_mut().unwrap() = path;\n            continue;\n",
          "            kept.push(path);\n            keys.push(key);\n            continue;\n")


@mutation("run-never-pairs-a-game",
          "the run takes --mod-path and --game-root as given, unchecked", "edges.py")
def r28():
    patch("scanner/src/front/mod.rs",
          "        let (mod_path, game) = settle_game(args.mod_path.as_deref(), args.game_root.as_deref())?;",
          "        let (mod_path, game) = (args.mod_path.clone().or(args.game_root.clone())"
          ".unwrap_or_default(), args.game_root.clone().unwrap_or_default());")


@mutation("cut-save-read-as-whole",
          "a save that stops part-way through is read as if it were whole",
          "mangled.py")
def r16():
    patch("scanner/src/engine/mod.rs", "    if end.map(|i| tail[i]) != Some(b'}') {",
          "    if false {")


@mutation("naval-base-int-becomes-float",
          "a nation with no naval base carries 0.0 where the table wrote 0",
          "saveshapes.py")
def r17():
    patch("scanner/src/engine/model.rs", "    if n.naval_base_levels != 0.0 {", "    if true {")


@mutation("name-runs-as-script",
          "a war named <img onerror=...> runs its script when the report's "
          "Wars tab draws", "boots.py", ("--hostile",))
def r27():
    patch("scanner/src/engine/finish.rs", "    if !s.contains(['<', '>']) {", "    if true {")


# ---- what the engine keeps between runs

@mutation("save-key-drops-reading",
          "a kept save is keyed without what it was read for, so a run asking "
          "for other pop types is served the last run's reading", "caching.py")
def r18():
    patch("scanner/src/engine/cache.rs", "                     self.version, context))",
          "                     self.version, \"\"))")


@mutation("save-key-drops-time",
          "a kept save is keyed by its size alone, so a save rewritten to the "
          "same size is served from the old read", "caching.py")
def r19():
    patch("scanner/src/engine/cache.rs", "full.to_string_lossy(), meta.len(), mtime,",
          "full.to_string_lossy(), meta.len(), 0,")


# ---- the map's province bitmap

@mutation("raster-runs-merged-by-colour",
          "two colours naming one province, or a run carrying into the next "
          "row, ship as two runs where the map had one", "raster.py")
def r20():
    patch("scanner/src/engine/mapflags.rs", "            if Some(pid) == last {",
          "            if false {")


@mutation("raster-red-channel-dropped",
          "the bitmap is read without its red channel, so provinces told "
          "apart only by red come out as one", "raster.py")
def r21():
    patch("scanner/src/engine/mapflags.rs",
          "row[at] as u32 | (row[at + 1] as u32) << 8 | (row[at + 2] as u32) << 16",
          "row[at] as u32 | (row[at + 1] as u32) << 8")


@mutation("raster-samples-wrong-rows",
          "a scaled map samples every row instead of every scale-th", "raster.py")
def r22():
    patch("scanner/src/engine/mapflags.rs", "offset + (oy * scale * stride) as u64",
          "offset + (oy * stride) as u64")


@mutation("raster-text-miscounted",
          "the map's runs are spelled with every count one short", "raster.py")
def r23():
    patch("scanner/src/engine/mapflags.rs", "            b36(*c, &mut out);",
          "            b36(*c - 1, &mut out);")


@mutation("anchor-nearer-column-skipped",
          "a province's anchor measures only the column left of its middle",
          "raster.py")
def r24():
    patch("scanner/src/engine/mapflags.rs", "vec![left, (left + 1).min(x1)]", "vec![left]")


@mutation("anchor-sum-of-first-columns",
          "a stretch of a row counts only its first column toward the "
          "province's middle", "raster.py")
def r25():
    patch("scanner/src/engine/mapflags.rs", "        t[0] += ((x0 + x1) * n).div_euclid(2);",
          "        t[0] += x0 * n;")


@mutation("anchor-run-not-split-at-row-end",
          "a run carrying into the next row is measured as one stretch "
          "running off the edge of the map", "raster.py")
def r26():
    patch("scanner/src/engine/mapflags.rs", "let x1 = width.min(x0 + end - at) - 1;",
          "let x1 = x0 + end - at - 1;")


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


@mutation("cross-last-fit-wins",
          "of the mods that fit a campaign, the one it leaves most unused wins",
          "frontcheck.py")
def m84():
    patch("scanner/src/front/cross.rs",
          "    fits.sort_by(|a, b| a.partial_cmp(b).unwrap());\n    let (_r, label, root) = fits.remove(0);",
          "    fits.sort_by(|a, b| a.partial_cmp(b).unwrap());\n    let (_r, label, root) = fits.pop().unwrap();")


@mutation("cross-flags-never-break",
          "a save from another game is never named, however many event flags it lacks",
          "frontcheck.py")
def m85():
    patch("scanner/src/front/cross.rs", "        if worst >= 6 {", "        if worst >= 600 {")


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
    scanner = "scanner/target/release/vic2scan" + (".exe" if sys.platform == "win32" else "")
    if not os.path.exists(os.path.join(TREE, scanner)):
        raise SystemExit("no scanner in %s, so every run would be refused. Copy "
                         "%s in first." % (TREE, scanner))
    chosen = [m for m in MUTATIONS if not args.names or m[0] in args.names]
    # The scanner as committed, to put back after each bug put into it.
    binary = os.path.join(TREE, scanner)
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

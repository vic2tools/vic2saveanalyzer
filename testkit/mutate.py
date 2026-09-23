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
import subprocess
import sys

TREE = ""
SAVES = ""


def revert():
    subprocess.run(["git", "checkout", "--", "."], cwd=TREE, check=True)


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


def check(script, args=()):
    """Run a check. Returns (passed, output)."""
    done = subprocess.run([sys.executable, os.path.join("testkit", script)] + list(args),
                          capture_output=True, text=True, cwd=TREE, timeout=900)
    return done.returncode == 0, (done.stdout + done.stderr)


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


# ---- commit 8b9f243: the reading profile and the cache key

@mutation("reading-apply-forgets-global", "apply() forgets to set REFORM_KEYS",
          "caching.py")
def m12():
    patch("readsave.py",
          """        v2parse.register_pop_types(self.pop_types)
        set_mob_candidates(self.mob_types)
        set_reform_keys(self.reform_keys)""",
          """        v2parse.register_pop_types(self.pop_types)
        set_mob_candidates(self.mob_types)""")


@mutation("reading-pop-types-accumulate", "register_pop_types grows instead of replacing",
          "caching.py")
def m13():
    src = open(os.path.join(TREE, "v2parse.py")).read()
    import re
    m = re.search(r"def register_pop_types\(.*?\n(?=\n\ndef |\n\n[A-Z_]+ =)", src, re.S)
    body = m.group(0)
    if "clear()" not in body:
        raise SystemExit("register_pop_types has no clear() to remove:\n" + body)
    patch("v2parse.py", body, body.replace("POP_TYPES.clear()", "pass"))


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
          '         + "|" + ",".join(sorted(mob_types)))',
          '         + "")')


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
          "        transform=partial(finishing.finish_and_pack, spec=spec) if in_workers else None,",
          "        transform=(lambda m, n: finishing.finish_and_pack(m, n, spec)) if in_workers else None,")


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
    patch("vic2_analyzer.py",
          '    read = [entry for entry in survey if entry["mod_path"]]\n',
          '    read = [max(survey, key=lambda entry: len(entry["files"]))]\n')


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
    patch("testkit/parity.py",
          "use_scanner=False", "use_scanner=True")


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
            print("CONTROL FAILED: %s %s fails with no bug put back, so its "
                  "mutations are not tried:\n%s\n"
                  % (catcher, " ".join(argv_for(extra)),
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
        try:
            passed, out = check(catcher, argv_for(extra))
        except subprocess.TimeoutExpired:
            passed, out = True, "TIMEOUT"
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

"""warmshift.py TREE REF: the engine cache holds no run's name ids.

One scratch cache, three runs of the real campaign through TREE: an empty-cache run with the name table
as it is, a warm rebuild of that cache with VIC2_ENGINE_NAMES_SHIFT=13, and a warm rebuild again
without. Each one's CSVs must be byte-identical to REF's (a run kept by refrun.sh, or in speed/runs/)
and its report.html identical decoded. stdout is not compared: a warm run prints less than an
empty-cache one, by design."""
import os, shutil, subprocess, sys
import cmpruns_env as E

tree = os.path.realpath(sys.argv[1])
ref = sys.argv[2]
fix = lambda p: ("C:" + p[2:]) if os.name == "nt" and p.startswith("/c/") else p
saves, mod = fix(E.env["VIC2_SAVES"]), fix(E.env["VIC2_MOD"])
scratch = os.path.join(E.WORK, "benchtmp", "warmshift")
shutil.rmtree(scratch, ignore_errors=True)
os.makedirs(os.path.join(scratch, "tmp"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "testkit"))
import expected
refout = os.path.join(E.WORK, "runs", ref, "out")
if not os.path.isdir(refout):
    refout = os.path.join(os.path.dirname(os.path.realpath(__file__)), "runs", ref, "out")
bad = 0
for step, shift in enumerate(["0", "13", "0"]):
    out = os.path.join(scratch, "out%d" % step)
    env = dict(os.environ, TMPDIR=os.path.join(scratch, "tmp"), VIC2_ENGINE_NAMES_SHIFT=shift)
    st = subprocess.run(["python3", os.path.join(tree, "vic2_analyzer.py"), saves, "--mod-path", mod, "-o", out],
                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    diffs = []
    for n in sorted(os.listdir(refout)):
        if n == "report.stamp":
            continue
        if n.endswith(".csv"):
            same = open(os.path.join(out, n), "rb").read() == open(os.path.join(refout, n), "rb").read()
        elif n == "report.html":
            same = expected.page(out) == expected.page(refout)
        else:
            continue
        if not same:
            diffs.append(n)
    print("run %d shift %-2s status %d %s" % (step + 1, shift, st, "IDENTICAL" if not diffs and st == 0 else "DIFFERENT " + " ".join(diffs)))
    bad += bool(diffs) or st != 0
sys.exit(1 if bad else 0)

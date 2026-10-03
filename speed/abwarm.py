"""abwarm.py TREE_A TREE_B [ROUNDS] [--empty]: warm-rebuild A/B, alternating, for a shell without bc or pgrep.

Both trees need their scanner built. One scratch TMPDIR (so one engine cache, made by A before the
first round) under $VIC2_SPEED_WORK; the report.stamp is removed before each run so every run is a
rebuild from a warm cache. Rounds alternate A, B, A, B...; prints each tree's walls and medians, and
the median of every engine phase (VIC2_ENGINE_TIMES), so the walk's share shows. Nothing else may be
running while it does. With --empty every run starts from an empty cache instead (and the priming run is
skipped)."""
import os, re, shutil, statistics, subprocess, sys, time
import cmpruns_env as E

empty = "--empty" in sys.argv
args = [x for x in sys.argv[1:] if x != "--empty"]
a, b = (os.path.realpath(p) for p in args[:2])
rounds = int(args[2]) if len(args) > 2 else 6
fix = lambda p: ("C:" + p[2:]) if os.name == "nt" and p.startswith("/c/") else p
saves, mod = fix(E.env["VIC2_SAVES"]), fix(E.env["VIC2_MOD"])
scratch = os.path.join(E.WORK, "benchtmp", "abwarm")
shutil.rmtree(scratch, ignore_errors=True)
os.makedirs(os.path.join(scratch, "tmp"))
out = os.path.join(scratch, "out")


def one(tree, tag):
    stamp = os.path.join(out, "report.stamp")
    if os.path.exists(stamp):
        os.remove(stamp)
    if empty:
        shutil.rmtree(os.path.join(scratch, "tmp"), ignore_errors=True)
        os.makedirs(os.path.join(scratch, "tmp"))
    phases_file = os.path.join(scratch, "phases-%s.txt" % tag)
    env = dict(os.environ, TMPDIR=os.path.join(scratch, "tmp"), VIC2_ENGINE_TIMES=phases_file)
    t = time.time()
    subprocess.run(["python3", os.path.join(tree, "vic2_analyzer.py"), saves, "--mod-path", mod, "-o", out],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    wall = time.time() - t
    phases = {}
    for line in open(phases_file):
        m = re.match(r"\[\s*([\d.]+)\] (.*)", line)
        if m:
            phases[m[2]] = float(m[1])
    return wall, phases


if not empty:
    one(a, "prime")
res = {"A": [], "B": []}
for n in range(rounds):
    for tag, tree in (("A", a), ("B", b)) if n % 2 == 0 else (("B", b), ("A", a)):
        res[tag].append(one(tree, "%s%d" % (tag, n)))
for tag, rs in res.items():
    print(tag, "wall median %.3f" % statistics.median(r[0] for r in rs), " walls", ["%.3f" % r[0] for r in rs])
    for k in rs[0][1]:
        print("   %-45s %.3f" % (k, statistics.median(r[1].get(k, 0) for r in rs)))

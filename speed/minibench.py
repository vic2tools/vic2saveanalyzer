"""minibench.py TREE: bench.sh for a shell that has no bc, uptime or pgrep (Git Bash on Windows).

TREE is a checkout with its scanner built. Empty scratch cache x3, warm rebuild x5 (report.stamp
removed before each), through vic2_analyzer.py with VIC2_ENGINE_TIMES; prints each kind's median
wall time and the median of every engine phase (seconds since the engine started). TMPDIR is a
scratch folder under $VIC2_SPEED_WORK, so the real cache is never touched. Nothing else may be
running while it does."""
import os, re, shutil, statistics, subprocess, sys, time
import cmpruns_env as E

tree = os.path.realpath(sys.argv[1])
fix = lambda p: ("C:" + p[2:]) if os.name == "nt" and p.startswith("/c/") else p
saves, mod = fix(E.env["VIC2_SAVES"]), fix(E.env["VIC2_MOD"])
scratch = os.path.join(E.WORK, "benchtmp", "minibench")
shutil.rmtree(scratch, ignore_errors=True)
os.makedirs(scratch)
out = os.path.join(scratch, "out")


def one(kind, n):
    phases_file = os.path.join(scratch, "phases-%s-%d.txt" % (kind, n))
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


def stamp():
    if os.path.exists(os.path.join(out, "report.stamp")):
        os.remove(os.path.join(out, "report.stamp"))


runs = {"empty": [], "warm": []}
for n in range(3):
    shutil.rmtree(os.path.join(scratch, "tmp"), ignore_errors=True)
    os.makedirs(os.path.join(scratch, "tmp"))
    stamp()
    runs["empty"].append(one("empty", n))
for n in range(5):
    stamp()
    runs["warm"].append(one("warm", n))
for kind, rs in runs.items():
    print(kind, "wall median %.3f" % statistics.median(r[0] for r in rs),
          " walls", ["%.2f" % r[0] for r in rs])
    for k in rs[0][1]:
        print("   %-45s %.3f" % (k, statistics.median(r[1].get(k, 0) for r in rs)))

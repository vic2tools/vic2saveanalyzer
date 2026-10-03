"""permexample.py TREE FIELD: run TREE (the probe build, see permute.sh) with FIELD reversed, keep the run
as runs/perm-FIELD, and print how it differs from the reference run speed/runs/11e1f21: the first changed
CSV lines, then the first places the decoded payload and the state chunks differ."""
import os, subprocess, sys, json, re, difflib
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "testkit"))
import expected
import cmpruns_env
tree, field = os.path.realpath(sys.argv[1]), sys.argv[2]
name = "perm-" + field.replace(".", "-")
work = cmpruns_env.WORK
env = dict(os.environ, VIC2_PERMUTE=field)
if not os.path.isdir(os.path.join(work, "runs", name, "out")) or "--again" in sys.argv:
    subprocess.run(["bash", os.path.join(HERE, "refrun.sh"), tree, name],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
a = os.path.join(HERE, "runs", "11e1f21", "out")
b = os.path.join(work, "runs", name, "out")
for n in sorted(os.listdir(a)):
    if n in ("report.stamp",):
        continue
    if n == "report.html":
        continue
    x = open(os.path.join(a, n), "rb").read(); y = open(os.path.join(b, n), "rb").read()
    if x != y:
        xl = x.decode("utf-8", "replace").split("\n"); yl = y.decode("utf-8", "replace").split("\n")
        d = [l for l in difflib.unified_diff(xl, yl, lineterm="", n=0) if not l.startswith(("---", "+++", "@@"))]
        print("CSV", n, "differs:", len(d), "changed lines; first:")
        for l in d[:6]:
            print("   ", l[:200])
def walk(p, q, path, out):
    if len(out) >= 8:
        return
    if type(p) != type(q):
        out.append((path, repr(p)[:100], repr(q)[:100])); return
    if isinstance(p, dict):
        if list(p.keys()) != list(q.keys()):
            if set(p.keys()) == set(q.keys()):
                out.append((path, "key order " + str(list(p.keys())[:6]), "key order " + str(list(q.keys())[:6])))
                return
            out.append((path, "keys differ", ""))
            return
        for k in p:
            walk(p[k], q[k], path + "/" + k, out)
    elif isinstance(p, list):
        if len(p) != len(q):
            out.append((path, "len %d" % len(p), "len %d" % len(q))); return
        for i, (u, v) in enumerate(zip(p, q)):
            if u != v:
                walk(u, v, path + "[%d]" % i, out)
                if len(out) >= 8:
                    return
    elif p != q:
        out.append((path, repr(p)[:100], repr(q)[:100]))
pa, pb = expected.page(os.path.dirname(a)+"/out"), expected.page(b)
if pa[0] != pb[0]:
    print("payload differs")
    out = []
    walk(json.loads(pa[0]), json.loads(pb[0]), "", out)
    for o in out[:6]:
        print("   ", o)
if pa[1] != pb[1]:
    print("state chunks differ")
    out = []
    walk(json.loads(pa[1]), json.loads(pb[1]), "chunks", out)
    for o in out[:4]:
        print("   ", o)

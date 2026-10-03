"""cmpruns.py A B [--payload]: compare two refrun.sh outputs.

A and B are names under $VIC2_SPEED_WORK/runs/, or under speed/runs/ (the
reference kept in the repo). CSVs byte for byte; report.html byte for
byte, or with --payload by its decoded payload (testkit/expected.py);
stdout and stderr with the machine's folders normalised (where the run
wrote, the game it found, "on N cores"); the exit status."""
import os, re, sys
def local_env():
    """speed/local.env beside this file (not committed): this machine's
    VIC2_SAVES, VIC2_MOD and VIC2_SPEED_WORK, under what the environment sets."""
    env = {}
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "local.env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = os.path.expanduser(v.strip().strip('"').strip("'").replace("$HOME", "~"))
    env.update({k: v for k, v in os.environ.items() if k.startswith("VIC2_")})
    return env
ENV = local_env()
WORK = ENV.get("VIC2_SPEED_WORK", os.path.expanduser("~/.cache/vic2speed/opt"))
KEPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "runs")


def run_dir(name):
    """A run made here, or else the one kept in the repo under that name."""
    here = os.path.join(WORK, "runs", name)
    return here if os.path.isdir(here) else os.path.join(KEPT, name)


a, b = (run_dir(x) for x in sys.argv[1:3])
payload = "--payload" in sys.argv
bad = []
def read(p):
    with open(p, "rb") as fh:
        return fh.read()
oa, ob = os.path.join(a, "out"), os.path.join(b, "out")
names = sorted(set(os.listdir(oa)) | set(os.listdir(ob)))
for n in names:
    if n == "report.stamp":
        continue
    if not (os.path.exists(os.path.join(oa, n)) and os.path.exists(os.path.join(ob, n))):
        bad.append("%s: only in one" % n); continue
    x, y = read(os.path.join(oa, n)), read(os.path.join(ob, n))
    if n == "report.html" and payload:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "testkit"))
        import expected
        x, y = expected.page(oa), expected.page(ob)
    if x != y:
        bad.append("%s differs" % n)
def norm(p, out):
    t = read(p).decode("utf-8", "replace").replace(out, "<OUT>")
    # A run kept under another name than it was made under (31a2931 was
    # made as task01-pre) says that folder.
    t = re.sub(r"/[^\s]*/opt/runs/[^/\s]+/out", "<OUT>", t)
    # What a run wrote, named in any folder on any machine: <OUT>/name.
    t = re.sub(r"(?m)^(\s+)\S[^\n]*?[\\/]([^\\/\n]+\.(?:html|csv))$", r"\1<OUT>/\2", t)
    # The game it found, which is wherever this machine installed it.
    t = re.sub(r"(?m)^Victoria II at .*?, (with |unmodded)", r"Victoria II at <GAME>, \1", t)
    return re.sub(r"on \d+ cores", "on N cores", t)
for f in ("stdout.txt", "stderr.txt", "status.txt"):
    if norm(os.path.join(a, f), oa) != norm(os.path.join(b, f), ob):
        bad.append("%s differs" % f)
print("%s vs %s: %d files compared, %s" % (sys.argv[1], sys.argv[2], len(names) - 1 + 3,
      "IDENTICAL" if not bad else "DIFFERENT: " + "; ".join(bad)))
sys.exit(1 if bad else 0)

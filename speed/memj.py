"""memj.py TREE J [J ...]: peak memory of an empty-scratch-cache run per -j.

Runs the real campaign through vic2_analyzer.py with -j J (TMPDIR in a
scratch folder, cache emptied first), samples the vic2scan process's
/proc/PID/status every 5 ms, and prints its peak RssAnon (heap: what a
thread costs), peak RssFile (mapped saves: page cache, not a cost) and
VmHWM, with the wall time. Also the RssAnon peak during pass one only is
not separable here; the peak is over the whole run."""
import os, shutil, subprocess, sys, time
TREE = os.path.realpath(sys.argv[1])
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
SAVES, MOD = ENV["VIC2_SAVES"], ENV["VIC2_MOD"]
SCRATCH = os.path.join(WORK, "benchtmp", "memj")
def kb(text, key):
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1])
    return 0
print("j    wall  anon_peak  pass1_anon  file_peak  hwm   (MB)")
for j in sys.argv[2:]:
    shutil.rmtree(SCRATCH, ignore_errors=True)
    os.makedirs(SCRATCH + "/tmp")
    env = dict(os.environ, TMPDIR=SCRATCH + "/tmp", VIC2_ENGINE_TIMES=SCRATCH + "/phases.txt")
    argv = [sys.executable, TREE + "/vic2_analyzer.py", SAVES, "--mod-path", MOD,
            "-o", SCRATCH + "/out", "-q"]
    if j != "auto":
        argv += ["-j", j]
    t0 = time.time()
    p = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    pid, anon, filep, hwm = None, 0, 0, 0
    series = []   # (seconds since the scanner was first seen, RssAnon kB)
    seen_at = None
    while p.poll() is None:
        if pid is None:
            try:
                kids = open("/proc/%d/task/%d/children" % (p.pid, p.pid)).read().split()
                pid = int(kids[0]) if kids else None
            except OSError:
                pid = None
        if pid is not None:
            try:
                st = open("/proc/%d/status" % pid).read()
                if seen_at is None:
                    seen_at = time.time()
                series.append((time.time() - seen_at, kb(st, "RssAnon")))
                anon = max(anon, kb(st, "RssAnon")); filep = max(filep, kb(st, "RssFile"))
                hwm = max(hwm, kb(st, "VmHWM"))
            except OSError:
                pass
        time.sleep(0.005)
    wall = time.time() - t0
    err = p.stderr.read()
    if p.returncode:
        print("j=%s failed %s: %s" % (j, p.returncode, err[-300:])); continue
    one = None
    for line in open(SCRATCH + "/phases.txt"):
        if "pass one" in line:
            one = float(line.split("]")[0].strip("[ "))
    # The engine starts ~20 ms after the scanner does: what the front end
    # does first. Pass one's peak is the samples up to its end.
    p1 = max((a for t, a in series if one is not None and t <= one), default=0)
    print("%-4s %.2f  %8.0f  %8.0f  %8.0f  %8.0f  (pass one %.2f s)" % (
        j, wall, anon / 1024, p1 / 1024, filep / 1024, hwm / 1024, one or 0), flush=True)

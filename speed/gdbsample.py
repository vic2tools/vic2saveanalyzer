#!/usr/bin/env python3
"""
Where pass one's time goes, by gdb samples, on any machine with gdb.

    python speed/gdbsample.py BINARY RUN.json [--repeat 40] [--samples 60]
    python speed/gdbsample.py --report SAMPLES.txt

Runs `BINARY bench-engine` on a copy of RUN.json whose saves are listed
REPEAT times over, so a handful of saves is read one after another for long
enough to sample; that is the per-save work of pass one (`read_save`:
countries, provinces, the rest, then `prepare`), on one thread. gdb attaches
SAMPLES times, dumps every thread's stack each time, and the stacks are
summed: the function each sample was in, and the share under each part.

RUN.json is the spec the front end hands the engine; nothing writes it out,
so take one with a temporary probe in `front/mod.rs` (`spec.write`) and
keep it outside the repo. This is the Windows counterpart of the laptop's
`sample_run.sh` + `gdbreport.py`, which attach to a whole `analyze` run;
gdb comes from MSYS2 there (`mingw-w64-x86_64-gdb`), reading the symbols
the `x86_64-pc-windows-gnu` build leaves in. An attach takes long enough
that samples are seconds apart, so take sixty or more.
"""
import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# Each part is the share of samples with a frame matching it anywhere on the
# stack; they overlap where one calls another (`latin1` inside countries).
PARTS = [
    ("countries", r"vic2scan::country::"),
    ("  latin1 decode", r"vic2scan::text::latin1"),
    ("provinces", r"vic2scan::province::read_province|vic2scan::province::accumulate"),
    ("top-level blocks", r"top_level_blocks"),
    ("wars, market, rest", r"vic2scan::engine::model::read_rest"),
    ("record (model::build)", r"vic2scan::engine::model::build"),
    ("prepare", r"vic2scan::engine::finish::prepare"),
    ("  gzip", r"vic2scan::deflate::"),
    ("reading the file", r"ReadFile|NtReadFile|std::fs::read|read_to_end"),
    ("malloc / free", r"\bmalloc\b|\bfree\b|\brealloc\b|HeapAlloc|HeapFree|HeapReAlloc|"
                      r"RtlAllocateHeap|RtlFreeHeap|RtlReAllocateHeap|__rust_alloc|"
                      r"__rust_dealloc|__rust_realloc"),
]
FRAME = re.compile(r"^#(\d+)\s+(?:0x[0-9a-f]+ in )?(.+?) \(")


def stacks(text):
    """The stacks of the engine's thread, one list of function names each."""
    out, cur = [], None
    for line in text.splitlines():
        if line.startswith("Thread "):
            if cur:
                out.append(cur)
            cur = []
            continue
        m = FRAME.match(line)
        if m and cur is not None:
            cur.append(m.group(2))
    if cur:
        out.append(cur)
    # gdb's own thread and the loader's idle ones carry no engine frame.
    return [s for s in out if any("vic2scan::" in f for f in s)]


def report(text):
    got = stacks(text)
    n = len(got)
    if not n:
        print("no samples with an engine frame in them")
        return
    print("%d samples" % n)
    print("\nshare of samples under each part:")
    for name, pat in PARTS:
        rx = re.compile(pat)
        k = sum(1 for s in got if any(rx.search(f) for f in s))
        print("  %-24s %5.1f%%  (%d)" % (name, 100.0 * k / n, k))
    print("\nwhere the samples were (innermost frame), the top 15:")
    for f, k in collections.Counter(s[0] for s in got).most_common(15):
        print("  %5.1f%%  %s" % (100.0 * k / n, f[:110]))


def sample(binary, spec, repeat, samples, out):
    gdb = shutil.which("gdb") or r"C:\msys64\mingw64\bin\gdb.exe"
    run = json.load(open(spec, encoding="utf-8"))
    run["files"] = run["files"] * repeat
    work = tempfile.mkdtemp(prefix="gdbsample")
    many = os.path.join(work, "run.json")
    json.dump(run, open(many, "w", encoding="utf-8"))
    proc = subprocess.Popen([binary, "bench-engine", many, str(len(run["files"]))],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(0.5)
    taken = 0
    with open(out, "w", encoding="utf-8") as f:
        while taken < samples and proc.poll() is None:
            done = subprocess.run([gdb, "-batch", "-nx", "-p", str(proc.pid),
                                   "-ex", "set pagination off",
                                   "-ex", "thread apply all bt 40"],
                                  capture_output=True, text=True, errors="replace")
            f.write("=== sample %d\n%s\n" % (taken, done.stdout))
            taken += 1
    still = proc.poll() is None
    if still:
        proc.kill()
    proc.wait()
    shutil.rmtree(work, ignore_errors=True)
    print("%d samples taken%s; stacks in %s" % (
        taken, "" if still else " (the run ended first: raise --repeat)", out))


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("binary", nargs="?")
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--repeat", type=int, default=40)
    ap.add_argument("--samples", type=int, default=60)
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "gdbsample.txt"))
    ap.add_argument("--report", metavar="SAMPLES", help="only summarise a samples file")
    a = ap.parse_args()
    if not a.report:
        if not (a.binary and a.spec):
            ap.error("BINARY and RUN.json, or --report SAMPLES")
        sample(a.binary, a.spec, a.repeat, a.samples, a.out)
    report(open(a.report or a.out, encoding="utf-8", errors="replace").read())


if __name__ == "__main__":
    sys.exit(main())

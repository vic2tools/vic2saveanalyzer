#!/bin/bash
# Exit checks through pipes: an ordinary run piped into head/cat, and the
# window's hosted run (analyze(), --protocol, relayed). Then leftovers.
# Usage: pipecheck.sh TREE SCRATCH  (replaces SCRATCH/tmp, o1, o2, piped.txt)
set -u
TREE=$1; S=$2
HERE=$(dirname "$(realpath "$0")")
# This machine's campaign, mod and work folder: speed/local.env, not committed.
[ -f "$HERE/local.env" ] && . "$HERE/local.env"
SAVES=${VIC2_SAVES:?set VIC2_SAVES in speed/local.env}
MOD=${VIC2_MOD:?set VIC2_MOD in speed/local.env}
WORK=${VIC2_SPEED_WORK:-$HOME/.cache/vic2speed/opt}
export TMPDIR=$S/tmp; rm -rf $S/tmp $S/o1 $S/o2 $S/o3; mkdir -p $TMPDIR
echo "-- ordinary run | cat"
python3 $TREE/vic2_analyzer.py "$SAVES" --mod-path "$MOD" -o $S/o1 2>&1 | cat > $S/piped.txt
echo "pipestatus ${PIPESTATUS[0]}  lines $(wc -l < $S/piped.txt)  last: $(tail -1 $S/piped.txt)"
echo "-- scanner direct, stdout | head -3 (reader goes away early), warm rebuild"
rm -f $S/o1/report.stamp
python3 $TREE/vic2_analyzer.py "$SAVES" --mod-path "$MOD" -o $S/o1 | head -3; echo "pipestatus ${PIPESTATUS[0]}"
echo "-- hosted (window) run, empty cache"
rm -rf $TMPDIR/vic2_analyzer_cache
( cd $TREE && python3 - "$SAVES" "$MOD" "$S/o2" <<'PY'
import io, sys, time
sys.argv = ["vic2_analyzer.py", sys.argv[1], "--mod-path", sys.argv[2], "-o", sys.argv[3]]
import vic2_analyzer as va
run = va.Run.from_command_line(va.command_line())
seen = {"progress": 0, "ready": None}
def prog(d, t): seen["progress"] = (d, t)
def ready(p): seen["ready"] = p
buf_out, buf_err = io.StringIO(), io.StringIO()
real = sys.stdout, sys.stderr
sys.stdout, sys.stderr = buf_out, buf_err
t0 = time.time()
try:
    st = va.analyze(run, progress=prog, ready=ready)
finally:
    sys.stdout, sys.stderr = real
print("status", st, "%.2fs" % (time.time() - t0), "progress", seen["progress"], "ready", seen["ready"])
print("stdout lines", len(buf_out.getvalue().splitlines()), "stderr lines", len(buf_err.getvalue().splitlines()))
print("last stdout:", buf_out.getvalue().splitlines()[-1])
print("any @ line leaked:", any(l.startswith("@") for l in buf_out.getvalue().splitlines()))
PY
)
sleep 0.3
echo "-- leftovers:"
# pgrep where there is one; tasklist on Windows (Git Bash has no pgrep). With neither, fail:
# "none" must never be printed for a check that could not look.
if command -v pgrep >/dev/null 2>&1; then
    pgrep -x vic2scan && ps -o pid,stat,etime,args -C vic2scan || echo "none"
elif command -v tasklist >/dev/null 2>&1; then
    left=$(tasklist //FI "IMAGENAME eq vic2scan.exe" //NH 2>/dev/null | grep -i vic2scan)
    if [ -n "$left" ]; then echo "$left"; else echo "none"; fi
else
    echo "pipecheck.sh: neither pgrep nor tasklist: cannot look for leftovers" >&2; exit 2
fi

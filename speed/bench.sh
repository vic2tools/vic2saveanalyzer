#!/bin/bash
# Bench a tree on the real campaign.
#
#   bench.sh TREE [LABEL]
#
# TREE is a checkout of vic2saveanalyzer with its scanner built
# (scanner/target/release/vic2scan). Runs, in this order:
#   empty scratch cache x3 (files in the page cache; NOT truly cold),
#   warm rebuild x5 (report.stamp removed before each),
#   nothing changed x3.
# Prints each run's wall time and the median of every VIC2_ENGINE_TIMES
# phase (its time since the engine started) per kind of run.
#
# Everything runs with TMPDIR in a scratch folder, so the real cache
# /tmp/vic2_analyzer_cache is never touched. Saves and mod are only read.
set -euo pipefail

TREE=$(realpath "${1:?usage: bench.sh TREE [LABEL]}")
LABEL=${2:-$(git -C "$TREE" rev-parse --short HEAD)}
HERE=$(dirname "$(realpath "$0")")
# This machine's campaign, mod and work folder: speed/local.env, not committed.
[ -f "$HERE/local.env" ] && . "$HERE/local.env"
SAVES=${VIC2_SAVES:?set VIC2_SAVES in speed/local.env}
MOD=${VIC2_MOD:?set VIC2_MOD in speed/local.env}
WORK=${VIC2_SPEED_WORK:-$HOME/.cache/vic2speed/opt}
SCRATCH="$WORK/benchtmp/$LABEL"

[ -x "$TREE/scanner/target/release/vic2scan" ] || { echo "no scanner built in $TREE" >&2; exit 2; }
case "$SCRATCH" in "$WORK"/benchtmp/?*) ;; *) echo "bad scratch $SCRATCH" >&2; exit 2;; esac
rm -rf "$SCRATCH"
mkdir -p "$SCRATCH/tmp" "$SCRATCH/phases"
export TMPDIR="$SCRATCH/tmp"
OUT="$SCRATCH/out"
LOG="$SCRATCH/runs.tsv"
: > "$LOG"

echo "bench $LABEL  tree $TREE  scanner $(stat -c %y "$TREE/scanner/target/release/vic2scan" | cut -d. -f1)"
echo "uptime:$(uptime)"
pgrep -af "app.py|vic2scan" | grep -v bench.sh | sed 's/^/  running: /' || true

one() {   # kind n
    local kind=$1 n=$2 ph="$SCRATCH/phases/$1-$2.txt"
    local t0 t1
    t0=$(date +%s.%N)
    VIC2_ENGINE_TIMES="$ph" python3 "$TREE/vic2_analyzer.py" "$SAVES" --mod-path "$MOD" \
        -o "$OUT" > "$SCRATCH/stdout-$kind-$n.txt" 2> "$SCRATCH/stderr-$kind-$n.txt" \
        || { echo "run $kind $n failed: $(tail -3 "$SCRATCH/stderr-$kind-$n.txt")" >&2; exit 1; }
    t1=$(date +%s.%N)
    printf '%s\t%s\t%.3f\n' "$kind" "$n" "$(echo "$t1 - $t0" | bc)" >> "$LOG"
}

for n in 1 2 3; do
    rm -rf "$TMPDIR/vic2_analyzer_cache" "$OUT/report.stamp"
    one empty "$n"
done
for n in 1 2 3 4 5; do
    rm -f "$OUT/report.stamp"
    one warm "$n"
done
for n in 1 2 3; do
    one same "$n"
done

python3 - "$LOG" "$SCRATCH/phases" <<'EOF'
import os, re, statistics, sys
log, phdir = sys.argv[1], sys.argv[2]
walls = {}
for line in open(log):
    kind, n, t = line.split("\t")
    walls.setdefault(kind, []).append(float(t))
names = {"empty": "empty scratch cache (page cache warm)", "warm": "warm rebuild",
         "same": "nothing changed"}
for kind in ("empty", "warm", "same"):
    w = walls.get(kind, [])
    print("\n%s: median %.3f s  [%s]" % (names[kind], statistics.median(w),
                                          " ".join("%.3f" % x for x in w)))
    phases, order = {}, []
    for f in sorted(os.listdir(phdir)):
        if not f.startswith(kind + "-"):
            continue
        for line in open(os.path.join(phdir, f)):
            m = re.match(r"\[\s*([\d.]+)\] (.*)", line.rstrip("\n"))
            if m:
                if m.group(2) not in phases:
                    order.append(m.group(2))
                phases.setdefault(m.group(2), []).append(float(m.group(1)))
    for p in order:
        print("    %8.3f  %s" % (statistics.median(phases[p]), p))
EOF

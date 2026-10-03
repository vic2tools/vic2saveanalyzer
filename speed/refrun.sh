#!/bin/bash
# refrun.sh TREE NAME: one run of the real campaign from an empty scratch
# cache, its outputs kept in $VIC2_SPEED_WORK/runs/NAME/ (CSVs, report.html, stdout, stderr, status).
set -uo pipefail
TREE=$(realpath "$1"); NAME=$2
HERE=$(dirname "$(realpath "$0")")
# This machine's campaign, mod and work folder: speed/local.env, not committed.
[ -f "$HERE/local.env" ] && . "$HERE/local.env"
SAVES=${VIC2_SAVES:?set VIC2_SAVES in speed/local.env}
MOD=${VIC2_MOD:?set VIC2_MOD in speed/local.env}
WORK=${VIC2_SPEED_WORK:-$HOME/.cache/vic2speed/opt}
DEST="$WORK/runs/$NAME"
rm -rf "$DEST"; mkdir -p "$DEST/tmp"
TMPDIR="$DEST/tmp" python3 "$TREE/vic2_analyzer.py" "$SAVES" --mod-path "$MOD" -o "$DEST/out" \
    > "$DEST/stdout.txt" 2> "$DEST/stderr.txt"
echo $? > "$DEST/status.txt"
rm -rf "$DEST/tmp"
ls "$DEST/out" | tr '\n' ' '; echo; cat "$DEST/status.txt"

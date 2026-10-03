#!/bin/bash
# permute.sh TREE FIELD...: which field's order reaches the output?
#
# TREE is a checkout with speed/model-probe.diff applied and the scanner
# built. For each FIELD (a name `probe_permute` in finish.rs knows) it runs
# the real campaign from an empty scratch cache with that field REVERSED in
# every nation (or save) just before `prepare`, and compares the run with
# the reference, `speed/runs/11e1f21`, by every CSV and the decoded page.
# IDENTICAL: the field's order does not reach this campaign's output.
# DIFFERENT: it does; `permexample.py TREE FIELD` shows where.
set -uo pipefail
TREE=$(realpath "${1:?usage: permute.sh TREE FIELD...}"); shift
HERE=$(dirname "$(realpath "$0")")
[ -f "$HERE/local.env" ] && . "$HERE/local.env"
WORK=${VIC2_SPEED_WORK:-$HOME/.cache/vic2speed/opt}
for f in "$@"; do
    name="perm-$(echo "$f" | tr . -)"
    VIC2_PERMUTE=$f bash "$HERE/refrun.sh" "$TREE" "$name" > /dev/null 2>&1
    echo "=== $f"
    python3 "$HERE/cmpruns.py" 11e1f21 "$name" --payload 2>&1 | head -12
    rm -rf "$WORK/runs/$name/out"
done

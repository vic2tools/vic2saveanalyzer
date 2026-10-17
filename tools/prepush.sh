#!/bin/bash
# prepush.sh: is anything private about to be committed or pushed?
#
# Greps, case-insensitively, for VIC2_PRIVATE (from the environment, or
# tools/local.env, which is not committed): the files as they are (tracked
# and new, bar what .gitignore leaves out), the index, and every commit not
# yet on origin/main (every commit, where there is no origin/main) with its
# message. Prints what it finds and exits 1; prints "clean" and exits 0;
# exits 2 when it cannot look -- never "clean" then.
HERE=$(dirname "$(realpath "$0")")
[ -z "${VIC2_PRIVATE:-}" ] && [ -f "$HERE/local.env" ] && . "$HERE/local.env"
if [ -z "${VIC2_PRIVATE:-}" ]; then
    echo "prepush.sh: set VIC2_PRIVATE (in tools/local.env) to the words that must never be pushed" >&2
    exit 2
fi
P=$VIC2_PRIVATE
cd "$HERE/.." || exit 2
git fetch -q origin 2>/dev/null
found=0
# git grep: 0 found, 1 nothing, anything else a failure -- which must not
# pass for clean.
look() {
    "$@"; local st=$?
    [ $st = 0 ] && found=1
    [ $st -gt 1 ] && { echo "prepush.sh: the search failed: $*" >&2; exit 2; }
}
look git grep --untracked -I -i -n -E "$P"
look git grep --cached -I -i -n -E "$P"
if git rev-parse -q --verify origin/main >/dev/null; then range=origin/main..HEAD; else range=HEAD; fi
log=$(git log -p "$range") || { echo "prepush.sh: git log failed" >&2; exit 2; }
if printf '%s\n' "$log" | grep -i -n -E "$P" | sed 's/^/unpushed: /' | grep .; then found=1; fi
[ $found = 0 ] && echo clean
exit $found

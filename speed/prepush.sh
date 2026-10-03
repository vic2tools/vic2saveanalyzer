#!/bin/bash
# prepush.sh: is anything private about to be committed or pushed?
#
# Greps, case-insensitively, for VIC2_PRIVATE (speed/local.env, not
# committed): the files as they are (tracked and new, bar what .gitignore
# leaves out), the index, and every commit not yet on origin/main with its
# message. Prints what it finds and exits 1; prints "clean" and exits 0.
HERE=$(dirname "$(realpath "$0")")
[ -f "$HERE/local.env" ] && . "$HERE/local.env"
P=${VIC2_PRIVATE:?set VIC2_PRIVATE in speed/local.env}
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
log=$(git log -p origin/main..HEAD) || { echo "prepush.sh: git log failed" >&2; exit 2; }
if printf '%s\n' "$log" | grep -i -n -E "$P" | sed 's/^/unpushed: /' | grep .; then found=1; fi
[ $found = 0 ] && echo clean
exit $found

#!/usr/bin/env python3
"""
Check the executable would carry every module the program needs.

`build_exe.py` names the modules to bundle explicitly, because most of them
are imported inside functions and a bundler's import scan does not always
follow that. An explicit list is the right answer and it has the obvious
failure: add a module, forget the list, and the executable builds cleanly,
starts cleanly, and dies on whichever button reaches the missing import --
on somebody else's machine, since this one runs from source and never
notices.

    python3 testkit/packing.py

Walks the imports out from `app.py` the way the program does and compares
that against the list. Names either side of the difference, because a
module in the list that nothing reaches is worth knowing about too: it is
either dead or the walk is wrong.
"""

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def local_modules():
    """Every module of this program, by name."""
    return {f[:-3] for f in os.listdir(HERE) if f.endswith(".py")}


def carried():
    """The modules `build_exe.py` says to bundle."""
    src = open(os.path.join(HERE, "build_exe.py"), encoding="utf-8").read()
    found = re.search(r"carried = \[(.*?)\]", src, re.S)
    if not found:
        return None
    return set(re.findall(r'"([^"]+)"', found.group(1)))


def reached(start="app"):
    """Every module of this program reachable from `start`, transitively."""
    local = local_modules()
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name in seen or name not in local:
            continue
        seen.add(name)
        tree = ast.parse(open(os.path.join(HERE, name + ".py"),
                              encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                todo += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                todo.append(node.module.split(".")[0])
    return seen


def main():
    named = carried()
    if named is None:
        print("could not find the module list in build_exe.py")
        return 1
    need = reached()
    local = local_modules()

    # `app` is the script handed to the bundler, not a hidden import.
    missing = sorted(need - named - {"app"})
    unused = sorted((named & local) - need)

    print("  app.py reaches %d of this program's modules" % len(need))
    print("  build_exe.py names %d" % len(named))
    if missing:
        print("\nPROBLEMS:")
        for name in missing:
            print("  %s is reached but not named in build_exe.py; the "
                  "executable may not carry it" % name)
    if unused:
        print("\n  named but not reached: %s" % ", ".join(unused))
        print("  (not a failure -- either dead, or reached a way this "
              "walk cannot see)")
    if missing:
        return 1
    print("\nthe executable would carry everything the program reaches")
    return 0


if __name__ == "__main__":
    sys.exit(main())

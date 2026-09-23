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


def the_scanner_opens_no_window():
    """
    [what went wrong] in how the scanner is started, as Windows would see it.

    The executable is built windowed and the scanner is a console program,
    and on Windows that combination opens a console window for every save
    read unless `Popen` is told `CREATE_NO_WINDOW`. Nothing here runs
    Windows, so this asks what `fastscan.start` would hand `Popen` there --
    and here, where the same flag is refused outright.
    """
    sys.path.insert(0, HERE)
    import subprocess
    import fastscan

    asked = []

    class Popen:
        def __init__(self, argv, **kwargs):
            asked.append(kwargs)
            raise OSError("not really started")

    real_popen, real_platform = subprocess.Popen, sys.platform
    real_found = fastscan._FOUND
    wrong = []
    try:
        subprocess.Popen = Popen
        fastscan._FOUND = __file__            # anything that is a file
        for platform in ("win32", real_platform):
            del asked[:]
            sys.platform = platform
            fastscan.start("a.v2", (), ())
            flags = asked[0].get("creationflags", 0) if asked else None
            if flags is None:
                wrong.append("fastscan.start never called Popen")
            elif platform == "win32" and not flags & 0x08000000:
                wrong.append("on Windows the scanner is started without "
                             "CREATE_NO_WINDOW, so every save read opens a "
                             "console window")
            elif platform != "win32" and flags:
                wrong.append("here the scanner is started with Windows-only "
                             "creation flags, which Popen refuses")
    finally:
        subprocess.Popen, sys.platform = real_popen, real_platform
        fastscan._FOUND = real_found
    return wrong


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
    window = the_scanner_opens_no_window()
    print("  the scanner is started with no window on Windows: %s"
          % ("FAILED" if window else "ok"))
    if window:
        print("\nPROBLEMS:")
        for one in window:
            print("  %s" % one)
    if missing or window:
        return 1
    print("\nthe executable would carry everything the program reaches")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""
Packs the analyzer into dist/vic2saveanalyzer.exe, for a release.

    cargo build --release --manifest-path scanner/Cargo.toml
    python build_exe.py

The bundle is the standard library, tkinter, this program's modules -- the
command line, the autosave keeper and the window that holds both -- and the
Rust scanner, which makes every run. The executable is not committed: zip it
and attach it to a GitHub Release. The icon is `vic2.ico`, beside this file.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "vic2.ico")
NAME = "vic2saveanalyzer"

def scanner_binary():
    """
    The Rust scanner, which makes every run, if this machine has built one.

    A release without it would refuse every run, so `build` requires it.
    """
    name = "vic2scan.exe" if sys.platform == "win32" else "vic2scan"
    built = os.path.join(HERE, "scanner", "target", "release", name)
    return built if os.path.isfile(built) else None


def build():
    scanner = scanner_binary()
    if scanner is None:
        print("A release requires the Rust scanner. Build it first with: "
              "cargo build --release --manifest-path scanner/Cargo.toml",
              file=sys.stderr)
        return 1
    # These are imported inside functions rather than at the top of the file, so
    # they are named here in case the bundler's scan ever stops following them.
    carried = ["vic2_analyzer", "run", "fastscan", "readfolder",
               # the window's two halves, what they remember, and the one
               # thing that leaves the machine, all reached from app.py
               "gui", "keeper", "keeper_gui", "settings", "publish",
               # what the keeper reads off a save's head, and what the window
               # asks before a run: which folder is a game, which holds
               # campaigns -- reached only from inside functions
               "savehead", "dates", "mod_reader", "cross"]
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--windowed", "--name", NAME, "--icon", ICON,
           "--distpath", os.path.join(HERE, "dist"),
           "--workpath", os.path.join(HERE, "build"),
           "--specpath", os.path.join(HERE, "build")]
    for module in carried:
        cmd += ["--hidden-import", module]
    # `.` puts it beside the unpacked modules, where fastscan looks first:
    # the scanner makes every run, so a release without it makes none.
    cmd += ["--add-binary", "%s%s." % (scanner, os.pathsep)]
    print("carrying the Rust scanner: %s" % scanner)
    for junk in ("numpy", "pandas", "matplotlib", "PIL", "scipy", "setuptools",
                 "pip", "pytest", "test"):
        cmd += ["--exclude-module", junk]
    cmd.append(os.path.join(HERE, "app.py"))
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)


if __name__ == "__main__":
    sys.exit(build())

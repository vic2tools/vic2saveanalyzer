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

# Where the crate leaves the scanner, which makes every run. `launch` needs
# nothing but the standard library, so building needs no tkinter.
from vic2tools.launch import built_scanner

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "vic2.ico")
NAME = "vic2saveanalyzer"


def build():
    # A release without the scanner would refuse every run.
    scanner = built_scanner()
    if scanner is None:
        print("A release requires the Rust scanner. Build it first with: "
              "cargo build --release --manifest-path scanner/Cargo.toml",
              file=sys.stderr)
        return 1
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--windowed", "--name", NAME, "--icon", ICON,
           "--distpath", os.path.join(HERE, "dist"),
           "--workpath", os.path.join(HERE, "build"),
           "--specpath", os.path.join(HERE, "build"),
           # the package is found from here, beside this file
           "--paths", HERE]
    # `.` puts it beside the unpacked modules, where `launch` looks first:
    # the scanner makes every run, so a release without it makes none.
    cmd += ["--add-binary", "%s%s." % (scanner, os.pathsep)]
    print("carrying the Rust scanner: %s" % scanner)
    for junk in ("numpy", "pandas", "matplotlib", "PIL", "scipy", "setuptools",
                 "pip", "pytest", "test"):
        cmd += ["--exclude-module", junk]
    cmd.append(os.path.join(HERE, "vic2tools", "__main__.py"))
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)


if __name__ == "__main__":
    sys.exit(build())

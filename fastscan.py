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
Where the scanner is (`scanner/`, built with cargo), and how to start it
with no window of its own.

The scanner makes every run: the command line and the window hand it the
run (`vic2_analyzer._front`). It is looked for beside the executable when
frozen, beside this file, and in the crate's own target directory.
"""

import os
import subprocess
import sys

BINARY = "vic2scan.exe" if sys.platform == "win32" else "vic2scan"
_FOUND = None


def _candidates():
    """Where the scanner might be, nearest first."""
    here = os.path.dirname(os.path.abspath(__file__))
    # Beside the executable when frozen, beside this file when not, and in
    # the crate's own target directory when working on it.
    yield os.path.join(getattr(sys, "_MEIPASS", here), BINARY)
    yield os.path.join(here, BINARY)
    yield os.path.join(here, "scanner", "target", "release", BINARY)


def available():
    """The scanner's path, or None. Looked for once."""
    global _FOUND
    if _FOUND is None:
        _FOUND = ""
        for path in _candidates():
            if os.path.isfile(path) and os.access(path, os.X_OK):
                _FOUND = path
                break
    return _FOUND or None


def _no_window():
    """
    What `Popen` is told so the scanner opens no window of its own.

    The executable is a windowed program and the scanner a console one, and
    on Windows a windowed program that starts a console program gets a new
    console window for it -- one flashed up for every run -- unless
    it says `CREATE_NO_WINDOW`. Everywhere else there is no such flag, and
    `Popen` refuses any.
    """
    if sys.platform != "win32":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

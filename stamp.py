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
Whether the report on disk is the one this run would write.

A report is stamped with a signature of everything it was made from -- the
saves, the code, the mod, the settings that change a number -- and a run
whose signature matches opens the report that is there instead of building
it again. That is the difference between pressing Analyze and waiting, and
pressing Analyze and reading. The stamp is taken away before anything it
describes is rewritten and written back last, so it only ever sits beside
the files it was written for.
"""

import hashlib
import os
import sys

from explain import asked
from readfolder import parser_fingerprint
from run import REPORTED


# What a finished report was made from. If all of it is the same, the report
# on disk is the report this run would write, byte for byte.
STAMP_FILE = "report.stamp"


def report_stamp(files, args, world):
    """
    A signature of everything that decides what the report says.

    Every save it was built from and the state of each of them, the code that
    reads saves, the code that writes reports, the mod, and the settings that
    change any number in it. Anything here changing means the report has to be
    built again; nothing here changing means it does not, and that is the
    difference between pressing Analyze and waiting, and pressing Analyze and
    reading.
    """
    digest = hashlib.md5()
    for path in sorted(files):
        try:
            stat = os.stat(path)
        except OSError:
            return ""
        digest.update(f"{os.path.abspath(path)}|{stat.st_size}|"
                      f"{stat.st_mtime_ns}\n".encode("utf-8"))
    digest.update(("parser=" + parser_fingerprint()).encode("utf-8"))
    digest.update(("world=" + str(world)).encode("utf-8"))
    # The report's own code, for the same reason the parse cache hashes the
    # parser: a change to the template is a change to the report.
    if getattr(sys, "frozen", False):
        digest.update(("frozen=" + parser_fingerprint()).encode("utf-8"))
    else:
        # Every source file beside this one, rather than the handful that
        # were thought of at the time. That list was wrong within a day:
        # `modrules.py` was lifted out of `mod_reader.py`, which was on it,
        # and did not inherit its place -- so doubling every nation's
        # mobilisation size changed nothing the skip could see and the next
        # run answered "nothing has changed since this was built" and served
        # the old report. A list of names is a thing to forget; a folder is
        # not. The file's name is hashed too, so renaming one counts.
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            for name in sorted(os.listdir(here)):
                if not name.endswith(".py"):
                    continue
                with open(os.path.join(here, name), "rb") as fh:
                    digest.update(name.encode("utf-8"))
                    digest.update(fh.read())
        except OSError:
            return ""
    # Every setting that reaches a number in the report. Not --jobs, not
    # --quiet, not where it is written: those change how it is made, not what
    # it says.
    # Which those are is declared once, beside each setting in `Run`.
    for name in REPORTED:
        digest.update(("%s=%r\n" % (name, getattr(args, name, None)))
                      .encode("utf-8"))
    return digest.hexdigest()


def stamp_matches(outdir, stamp, filename="report.html"):
    """Whether the report already sitting there was made from exactly this."""
    if not stamp:
        return False
    report = os.path.join(outdir, filename)
    if not os.path.isfile(report) or os.path.getsize(report) == 0:
        return False
    try:
        with open(os.path.join(outdir, STAMP_FILE), encoding="utf-8") as fh:
            return fh.read().strip() == stamp
    except OSError:
        return False


def write_stamp(outdir, stamp):
    """Record what this report was made from, for the next run to compare."""
    if not stamp:
        return
    try:
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, STAMP_FILE), "w",
                  encoding="utf-8") as fh:
            fh.write(stamp)
    except OSError:
        pass                          # a report that cannot be skipped later


def already_built(args, stamp):
    """
    Whether the report on disk is the one this run would write, said aloud.

    Only a run whose whole job is the report can be answered with the
    report that is already there. The four `explain` answers print
    something about a nation instead, and are not in the stamp because they
    change nothing the report says.
    """
    if (args.rebuild or args.no_html or asked(args)
            or not stamp_matches(args.out, stamp)):
        return False
    if not args.quiet:
        print(f"Nothing has changed since this was built. Opening it as it "
              f"is.\n\nWrote:\n  {os.path.join(args.out, 'report.html')}")
    return True


def forget_stamp(outdir):
    """
    Take the stamp away before anything it describes is rewritten.

    It says what the files beside it were made from. A run that rewrites
    them and then dies -- a table open in Excel, a full disk -- used to
    leave the last run's stamp describing this run's report, and the next
    run with the last run's settings matched it and served that report as
    its own. `--no-html` did the same without dying: it rewrites the tables
    and writes no stamp, so the old one went on vouching for tables it had
    never seen. Gone first and written last, a stamp only ever sits beside
    the files it was written for.
    """
    try:
        os.remove(os.path.join(outdir, STAMP_FILE))
    except OSError:
        pass

# Victoria 2 autosave keeper
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text.
"""
Keeps every autosave Victoria 2 writes, instead of the last three.

The game rotates `autosave.v2` -> `oldautosave.v2` -> `olderautosave.v2` and
drops whatever falls off the end, so a monthly autosave leaves three months of
history behind it and nothing else. There is no setting for this: the depth is
not configurable and never was.

Leave this running while you play. It watches the save folder, and each time an
autosave appears it copies it out under the in-game date it holds, into a folder
per campaign -- which is the shape the analyzer wants to be pointed at.

    python autosave_export.py

Windows says when the save folder changes, so the copy starts within
milliseconds of the game finishing one rather than at the end of some poll --
at speed five the three autosaves rotate past in a couple of seconds, and a
campaign kept by polling came out 59 months short. A save already held costs a
header read and no copy at all. A copy that turns out to have been taken while
the game was still writing is thrown away and retaken, and every copy lands
under a temporary name and is renamed into place, so the analyzer can be run
against the export folder mid-campaign.

Which campaign a save belongs to is decided by what the save contains rather
than by what it is called, because the country tag is not stable: Sardinia forms
Italy and every save after it says ITA. So a save joins the campaign whose
history it continues, by an event-flag test that tells two
campaigns apart, and the folder is retitled `SAR-ITA 1836` when that happens.
The same test keeps a second run as the same country in its own folder.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

# What a save's first few hundred kilobytes say, and the measured rule for
# telling one campaign's history from another's.
from savehead import FLAG_GAP, flags_lost, header, ymd

HOME = os.path.expanduser("~")
SAVES = os.path.join(
    HOME, "Documents", "Paradox Interactive", "Victoria II", "save games")
EXPORT = os.path.join(HOME, "Documents", "Exportsaves")

# The three names the game rotates through. Everything else in the folder is a
# save the player made deliberately, which the game is already keeping for them.
AUTOSAVES = ("autosave.v2", "oldautosave.v2", "olderautosave.v2")

# Our own naming, read back: `SAR1847_01_01.v2`, and `GFM SAR-ITA 1836`.
SAVE_NAME = re.compile(r"^([A-Za-z0-9]{2,4})(\d{4})_(\d{2})_(\d{2})\.v2$")
GENERATED = re.compile(r"^(?:.+ )?[A-Za-z0-9]{2,4}(?:-[A-Za-z0-9]{2,4})*"
                       r" \d{4}(?: \(\d+\))?$")

# Only a safety net: the folder itself says when it changed, and this is how
# long to wait before looking anyway.
POLL = 5.0


def folder_saves(folder):
    """What we have already put in a campaign folder, oldest date first."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for name in names:
        match = SAVE_NAME.match(name)
        if match:
            date = tuple(int(match.group(n)) for n in (2, 3, 4))
            out.append((date, match.group(1), os.path.join(folder, name)))
    out.sort()
    return out


def latest_in(folder, cache):
    """
    The newest save a campaign folder holds, read once and remembered.

    Re-read only when that newest save changes, which is when we add one, so
    watching a folder of two hundred saves costs one header read per autosave.
    """
    saves = folder_saves(folder)
    if not saves:
        return None
    date, tag, path = saves[-1]
    try:
        key = (path, os.stat(path).st_mtime_ns)
    except OSError:
        return None
    if cache.get(folder, (None, None))[0] != key:
        head = header(path)
        if head is None:
            return None
        cache[folder] = (key, {"date": date, "tag": tag,
                               "start": head.get("start_date", ""),
                               "flags": head["flags"]})
    return cache[folder][1]


def flag_gap(info, head, date):
    """
    How far the campaign in a folder is from being this save's own history.

    Event flags accumulate, so the earlier of two saves from one campaign has
    flags the later one also has. Counting the earlier one's flags that the
    later one lacks therefore stays near zero along a single game and jumps
    between two different ones. Which of the pair is earlier depends on the
    dates, because reloading means a new save can predate what we hold.
    Returns None when either side is too thin to be evidence.
    """
    if date >= info["date"]:
        return flags_lost(info["flags"], head["flags"])
    return flags_lost(head["flags"], info["flags"])


def mod_prefix(path, root):
    """The mod subfolder the game filed this save under, if it was one."""
    inside = os.path.relpath(os.path.dirname(path), root)
    return "" if inside in (".", "") else inside.replace(os.sep, " ") + " "


def title_for(prefix, tags, start):
    """`GFM SAR-ITA 1836`: where it was played, who it was, when it began."""
    return "%s%s %d" % (prefix, "-".join(tags), start[0] if start else 0)


def pick_campaign(path, args, head, cache):
    """
    The folder this save belongs in, and the name that folder should now carry.

    A save joins the campaign it continues, which is a question about content:
    the tag changes when a nation is formed, and two runs as the same country
    from the same start date are two campaigns rather than one. Where the flags
    cannot answer -- the opening years, when there are none -- the country and
    the start date do, which is as much as any of this knew before.
    """
    prefix = mod_prefix(path, args.saves)
    start = ymd(head.get("start_date", "")) or ymd(head["date"])
    date = ymd(head["date"])
    if args.campaign:
        return os.path.join(args.out, args.campaign), None

    best = None
    try:
        folders = sorted(os.listdir(args.out))
    except OSError:
        folders = []
    for name in folders:
        folder = os.path.join(args.out, name)
        if not os.path.isdir(folder):
            continue
        info = latest_in(folder, cache)
        if info is None or info["start"] != head.get("start_date", ""):
            continue
        gap = flag_gap(info, head, date)
        same_tag = info["tag"] == head["player"]
        if gap is None:
            rank = (2, 0) if same_tag else None   # nothing to go on but names
        elif gap < FLAG_GAP:
            rank = (0 if same_tag else 1, gap)    # the same history either way
        else:
            rank = None                           # a different game entirely
        if rank is not None and (best is None or rank < best[0]):
            best = (rank, folder)

    if best is None:
        return unused_folder(args.out, title_for(
            prefix, [head["player"]], start)), None

    folder = best[1]
    # In the order they were played, not the order they were copied: the first
    # sweep of a folder takes the newest autosave first, and a nation that was
    # formed in 1840 must still come second in `SWE-SCA`.
    seen = [(when, tag) for when, tag, _path in folder_saves(folder)]
    seen.append((date, head["player"]))
    tags = []
    for _when, tag in sorted(seen):
        if tag not in tags:
            tags.append(tag)
    wanted = title_for(prefix, tags, start)
    if os.path.basename(folder) == wanted or not GENERATED.match(
            os.path.basename(folder)):
        return folder, None           # already right, or a name you chose
    return folder, os.path.join(args.out, wanted)


def unused_folder(out, title):
    """`SAR 1836`, or `SAR 1836 (2)` when that is a campaign we already hold."""
    folder = os.path.join(out, title)
    count = 1
    while os.path.isdir(folder):
        count += 1
        folder = os.path.join(out, "%s (%d)" % (title, count))
    return folder


def retitle(folder, wanted, cache, report):
    """Rename a campaign folder now that we know it formed a nation."""
    try:
        os.rename(folder, wanted)
    except OSError as err:
        report("  keeping the name %s: %s" % (os.path.basename(folder), err))
        return folder
    cache.pop(folder, None)
    report("  %s is now %s" % (os.path.basename(folder),
                               os.path.basename(wanted)))
    return wanted


def saves_under(root, autosaves_only):
    """Every save worth looking at, the game's own subfolders included."""
    for where, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            if not name.lower().endswith(".v2"):
                continue
            if autosaves_only and name.lower() not in AUTOSAVES:
                continue
            yield os.path.join(where, name)


def stable_copy(src, part, tries=4):
    """
    Copy a save that the game may still be in the middle of writing.

    Waiting a second first to see whether the file has stopped moving was what
    made this too slow to keep up: a month at speed five can be written, rotated
    twice and dropped inside that wait. So the copy starts at once and is judged
    afterwards -- if the source changed size or timestamp while we read it, or
    the copy came out a different length, it was torn and is thrown away rather
    than kept. Nothing here holds a handle the game could trip over.
    """
    for attempt in range(tries):
        try:
            before = os.stat(src)
            shutil.copy2(src, part)
            after = os.stat(src)
        except OSError:
            return False
        if ((before.st_size, before.st_mtime_ns)
                == (after.st_size, after.st_mtime_ns)
                and os.path.getsize(part) == before.st_size):
            return True
        time.sleep(0.05 * (attempt + 1))
    return False


class Changes:
    """
    Windows saying when the save folder changed, rather than us asking.

    A poll loop is asleep exactly when the interesting thing happens, and at
    high speed the three autosaves rotate past inside one sleep -- which is how
    a 1836-1900 campaign came out 59 months short. This waits on the folder
    itself and wakes on the write. Where the call is not available the timeout
    alone still drives it, which is the old behaviour and no worse.
    """

    # A save appearing is a write, a rotation is a rename, and both change size.
    MASK = 0x1 | 0x8 | 0x10         # FILE_NAME | SIZE | LAST_WRITE
    SLICE = 200                     # ms between checks of the Stop button

    def __init__(self, root):
        self.api = None
        self.handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.FindFirstChangeNotificationW.restype = wintypes.HANDLE
            api.FindFirstChangeNotificationW.argtypes = [
                wintypes.LPCWSTR, wintypes.BOOL, wintypes.DWORD]
            api.FindNextChangeNotification.argtypes = [wintypes.HANDLE]
            api.FindCloseChangeNotification.argtypes = [wintypes.HANDLE]
            api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            api.WaitForSingleObject.restype = wintypes.DWORD
            handle = api.FindFirstChangeNotificationW(root, True, self.MASK)
            if handle and handle != ctypes.c_void_p(-1).value:
                self.api, self.handle = api, handle
        except (ImportError, OSError, AttributeError):
            self.api = self.handle = None

    def wait(self, seconds, stopped=None):
        """Until the folder changes, the time runs out, or Stop is pressed."""
        deadline = time.monotonic() + seconds
        while True:
            if stopped and stopped():
                return
            left = deadline - time.monotonic()
            if left <= 0:
                return
            span = min(self.SLICE, int(left * 1000) + 1)
            if self.handle is None:
                time.sleep(span / 1000.0)
                continue
            if self.api.WaitForSingleObject(self.handle, span) == 0:
                self.api.FindNextChangeNotification(self.handle)
                return

    def close(self):
        if self.handle is not None:
            self.api.FindCloseChangeNotification(self.handle)
            self.api = self.handle = None


def open_with_system(path):
    """
    Open a file or a folder in whatever this machine opens it with.

    `os.startfile` exists only on Windows, so each window had to choose
    between it, `open` and `xdg-open` -- and there were three copies of that
    choice, one of which, the keeper's "Open the folder", had only the first
    and showed an error dialog everywhere else. Raises OSError when nothing
    could be started; what to say about it is the caller's business.
    """
    if sys.platform == "win32":
        os.startfile(path)                  # noqa: S606  (Windows only)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def human_size(count):
    """A byte count the way a person would say it."""
    if count < 1024:
        return "%d byte%s" % (count, "" if count == 1 else "s")
    for unit in ("KB", "MB", "GB"):
        count /= 1024.0
        if count < 1024 or unit == "GB":
            break
    return "%.0f %s" % (count, unit) if count >= 10 else "%.1f %s" % (
        count, unit)


def say(message):
    print(message)
    sys.stdout.flush()


def export(path, args, handled, cache, tally, report):
    """Copy one save out, unless it is one we already hold."""
    try:
        st = os.stat(path)
    except OSError:
        return
    key = (st.st_size, st.st_mtime_ns)
    if handled.get(path) == key:
        return
    head = header(path)
    if head is None:
        return                      # mid-write, or not a plaintext save: later
    date = ymd(head["date"])
    if date is None:
        return
    handled[path] = key             # this version has nothing more to tell us

    if args.every > 1 and (date[1] - 1) % args.every:
        return

    folder, wanted = pick_campaign(path, args, head, cache)
    name = "%s%04d_%02d_%02d.v2" % (head["player"], date[0], date[1], date[2])
    if os.path.isdir(folder):
        dest = os.path.join(folder, name)
        if os.path.exists(dest) and os.path.getsize(dest) == st.st_size:
            return                  # already held, from an earlier rotation
    if wanted:
        folder = retitle(folder, wanted, cache, report)

    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, name)
    part = dest + ".part"
    try:
        whole = stable_copy(path, part)
        if whole:
            os.replace(part, dest)
        else:
            handled.pop(path, None)     # caught mid-write; come back to it
            if os.path.exists(part):
                os.remove(part)
            return
    except OSError as err:
        report("  could not copy %s: %s" % (os.path.basename(path), err))
        handled.pop(path, None)
        if os.path.exists(part):
            os.remove(part)
        return
    tally[0] += 1
    tally[1] += st.st_size
    report("%s  %s -> %s%s%s  (%s)" % (
        time.strftime("%H:%M:%S"), os.path.basename(path),
        os.path.basename(folder), os.sep, name, human_size(st.st_size)))


class Options:
    """
    What to watch and what to keep, for callers that are not a command line.

    The window builds one of these; argparse builds the same field names, so
    both drive the identical loop rather than a copy of it each.
    """

    def __init__(self, saves=SAVES, out=EXPORT, every=1, all=False,
                 campaign=None, once=False, poll=POLL):
        self.saves = saves
        self.out = out
        self.every = every
        self.all = all
        self.campaign = campaign or None
        self.once = once
        self.poll = poll


def trouble(args):
    """Why this cannot be run, in a sentence, or None if it can."""
    if not os.path.isdir(args.saves):
        return "There is no save folder at %s" % args.saves
    saves, out = os.path.abspath(args.saves), os.path.abspath(args.out)
    if out == saves or out.startswith(saves + os.sep):
        # Otherwise the exports are themselves saves in the watched folder, and
        # a campaign is copied out of its own copy.
        return ("Keep the exports outside the game's save folder: %s is inside "
                "%s." % (out, saves))
    return None


def watch(args, report=None, stopped=None, tally=None):
    """
    Copy out every save that appears, until asked to stop.

    `report` is handed a line at a time -- the window puts it in its log, the
    command line prints it. `stopped` is asked between saves and while waiting,
    so Stop is answered in about a second rather than at the end of a poll.
    Pass `tally` -- [saves, bytes] -- to watch the count climb from outside;
    it is what gets returned either way.
    """
    report = report or say
    handled, cache = {}, {}
    tally = tally if tally is not None else [0, 0]
    changes = Changes(args.saves)
    try:
        while True:
            for path in saves_under(args.saves, not args.all):
                if stopped and stopped():
                    return tuple(tally)
                export(path, args, handled, cache, tally, report)
            if args.once or (stopped and stopped()):
                break
            changes.wait(args.poll, stopped)
    except KeyboardInterrupt:
        report("")
    finally:
        changes.close()
    return tuple(tally)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Keep every Victoria 2 autosave, not just the last three.")
    ap.add_argument("--saves", default=SAVES,
                    help="the game's save folder (default: %(default)s)")
    ap.add_argument("--out", default=EXPORT,
                    help="where to keep them (default: %(default)s)")
    ap.add_argument("--every", type=int, default=1, metavar="N",
                    help="keep one autosave every N months, counting from "
                         "January (default: every one)")
    ap.add_argument("--all", action="store_true",
                    help="copy hand-made saves out too, not just autosaves")
    ap.add_argument("--campaign", metavar="NAME",
                    help="put everything in this folder, instead of one worked "
                         "out from each save")
    ap.add_argument("--once", action="store_true",
                    help="sweep the folder once and stop, rather than watch")
    ap.add_argument("--poll", type=float, default=POLL, metavar="SECONDS",
                    help="how long to wait before looking anyway, when the "
                         "folder has said nothing (default: %(default)s)")
    args = ap.parse_args(argv)

    bad = trouble(args)
    if bad:
        sys.exit(bad)
    os.makedirs(args.out, exist_ok=True)

    say("Watching %s" % args.saves)
    say("Keeping   %s" % args.out)
    if args.every > 1:
        say("Keeping one save every %d months." % args.every)
    say("Leave this running while you play. Ctrl-C to stop.\n")

    kept, size = watch(args)
    say("Kept %d save%s, %s in all, in %s" % (
        kept, "" if kept == 1 else "s", human_size(size), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

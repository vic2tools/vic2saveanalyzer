#!/usr/bin/env python3
"""
Run the window's own code path, without showing a window.

Everything else here drives the analyzer through its command line. Nobody
drives it through the thing people actually click, and the two are not the
same path: the window builds its own argument list, replaces stdout with a
queue, hands over a cancel check and a progress callback, and opens the
report at the end. Each of those is a place to be wrong, and one of them
was -- the report never opened at all on anything but Windows, which no
command-line test could have noticed.

    python3 testkit/window.py "/path/to/saves"

Builds the window withdrawn, runs a real campaign through it, and checks
what came back: the report on disk, nothing in the log that looks like a
crash, the progress bar counting up to the total and stopping there, and
the report handed to whatever opens one. Then presses Stop on a second run
and checks it gives up quietly.

Needs tkinter and a display; says so and passes if there is neither, since
a machine without one is not a machine anybody clicks this on.
"""

import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def a_window():
    """(root, app), or None if this machine cannot make one."""
    try:
        import tkinter as tk
    except ImportError:
        return None
    try:
        root = tk.Tk()
    except Exception:                                    # noqa: BLE001
        return None                                      # no display
    root.withdraw()
    import gui
    return root, gui.App(root)


def a_full_run(root, app, saves, out):
    """[what went wrong] for one ordinary run through the window."""
    opened, progress, early = [], [], []
    app.show_report = opened.append
    app.open_after.set(True)
    # Which route asked for it, not just that something did. The window
    # opens the report the moment it lands, while the CSV tables are still
    # being written, and falls back to doing it when the run ends. With
    # only the fallback working the report still opens, a third of a
    # second later, and no check that asked "was it opened" would notice.
    was_ready = app.on_report_ready

    def watched(path):
        early.append(path)
        return was_ready(path)

    app.on_report_ready = watched

    # Watched the same way, and for the same reason: `work` hooks its own
    # callbacks up now, so anything registered with the analyzer out here
    # would simply be replaced. What is being checked is that the window
    # wires itself, not that this file can wire it.
    was_progress = app.on_progress

    def counted(done, total):
        progress.append((done, total))
        return was_progress(done, total)

    app.on_progress = counted
    began = time.monotonic()
    app.work(saves, "", out)
    took = time.monotonic() - began

    # Let the window's own pump move the queue into the log widget, the way
    # it does between frames.
    for _ in range(40):
        root.update()
        time.sleep(0.02)
    log = app.log.get("1.0", "end")

    wrong = []
    report = os.path.join(out, "report.html")
    if not os.path.isfile(report):
        wrong.append("no report was written")
    if "Traceback" in log:
        wrong.append("the log carries a traceback")
    if "Report written to" not in log:
        wrong.append("the log never said where the report went")
    if not opened:
        wrong.append("the report was never handed to anything to open")
    if not early:
        wrong.append("the report was only opened after the run finished, "
                     "not when it was written")
    if not progress:
        wrong.append("the progress bar was never told anything")
    else:
        if any(a > b for (a, _t1), (b, _t2) in zip(progress, progress[1:])):
            wrong.append("the progress bar went backwards")
        done, total = progress[-1]
        if done != total:
            wrong.append("the progress bar stopped at %d of %d" % (done,
                                                                   total))
    print("  ran in %.1f s, %d lines of log, %d progress steps"
          % (took, len(log.strip().splitlines()), len(progress)))
    return wrong


def opens_on_this_machine(app, report):
    """
    [what went wrong] in the part that actually launches something.

    Stubbed out everywhere else in this file, and it is where the bug was:
    `os.startfile` exists only on Windows and the fallback behind it was
    `cmd /c start`, so on Linux and macOS the report was built, announced,
    and left sitting there.
    """
    import subprocess

    launched = []
    real_popen, real_start = subprocess.Popen, getattr(os, "startfile", None)
    subprocess.Popen = lambda *a, **k: (launched.append(a[0]),
                                        type("P", (), {})())[1]
    if real_start is not None:
        os.startfile = lambda path: launched.append(["startfile", path])
    try:
        app.opened = False
        app.show_report(report)
    finally:
        subprocess.Popen = real_popen
        if real_start is not None:
            os.startfile = real_start

    print("  opening a report here runs: %s"
          % (" ".join(str(x) for x in launched[0]) if launched else "nothing"))
    if not launched:
        return ["nothing was launched to open the report on %s" % sys.platform]
    return []


def a_stopped_run(root, app, saves, out):
    """[what went wrong] when Stop is pressed before it starts."""
    import vic2_analyzer

    app.show_report = lambda path: None
    app.open_after.set(False)
    app.stop.set()                       # as if Stop were pressed at once
    try:
        app.work(saves, "", out)
    finally:
        app.stop.clear()
        vic2_analyzer.set_cancel_check(None)
    for _ in range(20):
        root.update()
        time.sleep(0.02)
    log = app.log.get("1.0", "end")

    wrong = []
    if "Traceback" in log:
        wrong.append("stopping left a traceback in the log")
    if "Stopped" not in log:
        wrong.append("stopping was not reported in the log")
    print("  stopping says: %s"
          % next((l for l in log.splitlines() if "Stopped" in l),
                 "(nothing)")[:70])
    return wrong


def main():
    saves = sys.argv[1] if len(sys.argv) > 1 else ""
    if not saves or not os.path.isdir(saves):
        print(__doc__.strip())
        return 2
    made = a_window()
    if made is None:
        print("no tkinter or no display here, so no window was built")
        return 0
    root, app = made
    holding = tempfile.mkdtemp(prefix="vic2window")
    try:
        out = os.path.join(holding, "out")
        wrong = a_full_run(root, app, saves, out)
        import gui
        app.show_report = gui.App.show_report.__get__(app)   # the real one
        wrong += opens_on_this_machine(app, os.path.join(out, "report.html"))
        wrong += a_stopped_run(root, app, saves, os.path.join(holding, "two"))
    finally:
        shutil.rmtree(holding, ignore_errors=True)
        try:
            root.destroy()
        except Exception:                                # noqa: BLE001
            pass

    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("the window runs a campaign, reports it, and stops when told")
    return 0


if __name__ == "__main__":
    sys.exit(main())

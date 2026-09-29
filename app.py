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
One window for the whole of it: keep the autosaves, then read them.

These were two programs, and the seam between them was the user's to carry --
two downloads, two windows, and a folder path typed into the second one that
the first one had invented. They are one campaign's worth of work, so they are
one window now: a tab that keeps every autosave the game writes while you
play, a tab that turns a folder of them into a report, and along the bottom
the one path they share and the one thing you do with a finished report, which
is give it to somebody.

Both halves still run on their own -- `gui.py` and `keeper_gui.py` each open
their own window if started directly -- because nothing here is allowed to
make either of them harder to test.

Packaged as vic2saveanalyzer.exe by build_exe.py.
"""

import multiprocessing
import os
import sys

# Before anything else is imported. A worker in the packaged program starts
# by running this file again from the top, and stops only here: every import
# above this line is made again in every worker. The window's are not needed
# to read a save -- tkinter, and `publish` bringing the web and mail modules
# with it, about 45 ms of each worker's start -- so they come after.
if __name__ == "__main__":
    multiprocessing.freeze_support()

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import gui
import keeper
import keeper_gui
import publish
import settings

APP = "Victoria 2 campaign tools"


class Tools:
    """The window: two tabs, and the bar along the bottom that joins them."""

    def __init__(self, root):
        self.root = root
        root.title(APP)
        root.minsize(760, 660)

        book = ttk.Notebook(root)
        making = ttk.Frame(book)
        keeping = ttk.Frame(book)
        book.add(making, text="  Build the report  ")
        book.add(keeping, text="  Keep autosaves  ")
        self.book, self.making = book, making

        # The analyzer first: it is what most runs are for, and a tab that
        # opens on the job in hand beats one that opens on the preparation.
        self.analyzer = gui.App(root, parent=making)
        self.keeper = keeper_gui.Keeper(root, parent=keeping)

        # The bar is packed before the tabs and against the bottom, because
        # pack hands out room in the order it is asked and the tabs, which
        # expand, will take the lot: packed the other way round the bar is
        # simply not there on a window this size.
        bar = ttk.Frame(root, padding=(14, 8))
        bar.pack(side="bottom", fill="x")
        self.hint = ttk.Label(bar, text="", foreground="#666")
        self.hint.pack(side="left")
        # A menu rather than a button, because there is no one right way to
        # share a report and pretending otherwise picks wrong for somebody.
        # The first item needs no account, no network and nobody's server,
        # which is why it is first and why it is what most people will use.
        self.share_button = ttk.Menubutton(bar, text="Share…")
        menu = tk.Menu(self.share_button, tearoff=False)
        menu.add_command(label="Show me the file to send", command=self.reveal)
        menu.add_separator()
        menu.add_command(label="Upload to a report host…", command=self.to_host)
        menu.add_command(label="Publish to GitHub Pages…", command=self.share)
        self.share_button["menu"] = menu
        self.share_button.pack(side="right")
        self.adopt_button = ttk.Button(bar, text="Read the kept saves",
                                       command=self.adopt)
        self.adopt_button.pack(side="right", padx=6)
        # `watch` decides both of these from here on, but it does not run for
        # another tick, and a button that is live before there is anything to
        # do with it is a button somebody will press.
        self.share_button.state(["disabled"])
        self.adopt_button.state(["disabled"])

        book.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))

        root.protocol("WM_DELETE_WINDOW", self.close)
        # Kept so closing can cancel it: a tick that fires into a window being
        # torn down complains to a stream nobody reads.
        self.tick = root.after(300, self.watch)

    # ------------------------------------------------------- the shared path
    def adopt(self):
        """Point the report at the folder the keeper is filling."""
        kept = self.keeper.out.get().strip()
        if not kept:
            return
        self.analyzer.saves.set(kept)
        self.book.select(self.making)
        self.analyzer.say("Reading the campaigns kept in %s.\n" % kept)

    def watch(self):
        """Keep the bottom bar honest about what the two halves are doing."""
        kept = self.keeper.out.get().strip()
        same = os.path.normpath(kept or ".") == os.path.normpath(
            self.analyzer.saves.get().strip() or "..")
        self.adopt_button.state(["disabled" if (same or not kept) else
                                 "!disabled"])
        report = self.current_report()
        ready = bool(report)
        self.share_button.state(["!disabled" if ready else "disabled"])
        if self.keeper.worker:
            self.hint.configure(text="Keeping every autosave. %s"
                                     % self.keeper.account())
        elif ready:
            self.hint.configure(
                text="%s · %s" % (os.path.basename(report),
                                       gui.human_size(os.path.getsize(report))))
        else:
            self.hint.configure(text="")
        self.tick = self.root.after(300, self.watch)

    # ------------------------------------------------------------- the link
    def current_report(self):
        """
        The report to share: the one just built, or the one already there.

        Sharing used to wait on a run in this sitting, which meant closing the
        window lost the ability to send a report that was sitting on the disk
        the whole time. A report in the output folder is as good as one this
        window made.
        """
        made = self.analyzer.report
        if made and os.path.isfile(made):
            return made
        out = self.analyzer.out.get().strip()
        there = os.path.join(out, "report.html") if out else ""
        return there if there and os.path.isfile(there) else None

    def reveal(self):
        """
        The answer that needs nobody: here is the file, send it yourself.

        A report of a few dozen saves is a couple of megabytes and goes
        straight into a chat window. Only a campaign autosaved every month for
        a century outgrows that, and saying so plainly beats letting somebody
        find out when a chat client refuses the attachment.
        """
        report = self.current_report()
        if not report:
            return
        size = os.path.getsize(report)
        note = ""
        if size > 25 * 1048576:
            note = ("\n\nAt this size it is past what most chat clients and "
                    "mail will take. Building the report from fewer saves is "
                    "the cure, or put it on a host.")
        elif size > 10 * 1048576:
            note = ("\n\nThat will go by mail but not through Discord, "
                    "which stops at 10 MB.")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(report)
        except tk.TclError:
            pass
        self.open_folder(os.path.dirname(report))
        messagebox.showinfo(
            APP, "%s\n\n%s %s the path is on your clipboard, and the folder "
                 "is open.%s" % (report, gui.human_size(size), "\u2014", note))

    def open_folder(self, where):
        """Show a folder in whatever this machine uses to look at folders."""
        try:
            keeper.open_with_system(where)
        except OSError:
            pass                                  # the dialog still says where

    def host(self):
        """The address of a report host, asked for once and remembered."""
        held = settings.load().get("report_host", "")
        got = simpledialog.askstring(
            APP,
            "Address of a report host.\n\n"
            "This program ships without one: a host is somebody's server, and "
            "nobody should be signed up to that by a default. If you run one "
            "-- there is a server in host/ ready to deploy -- put its address "
            "here and sharing becomes one click, with no account for anybody."
            "\n\nLeave it empty to forget the one held here.",
            initialvalue=held, parent=self.root)
        if got is None:
            return held                # cancelled: keep whatever was there
        got = got.strip().rstrip("/")
        settings.remember(report_host=got)
        return got

    def to_host(self):
        report = self.current_report()
        if not report:
            return
        endpoint = settings.load().get("report_host", "") or self.host()
        if not endpoint:
            return
        name = os.path.basename(os.path.dirname(os.path.abspath(report)))
        self.share_button.state(["disabled"])
        self.analyzer.say("\nUploading the report%s\n" % "\u2026")
        threading.Thread(target=self._upload, daemon=True,
                         args=(report, endpoint, name)).start()

    def _upload(self, report, endpoint, name):
        """Off the UI thread, reporting through the queue like the rest."""
        tell = self.analyzer.log_queue.put
        try:
            url = publish.upload(report, endpoint, name=name,
                                 say=lambda line: tell("  " + line + "\n"))
        except Exception as err:                     # noqa: BLE001
            tell("Could not upload it: %s\n" % err)
            self.root.after(0, self.publish_failed, str(err))
            return
        tell("\nUploaded: %s\n" % url)
        self.root.after(0, self.published, url)

    def token(self):
        """The GitHub token, asked for once and remembered after that."""
        held = settings.load().get("github_token", "")
        if held:
            return held
        if not messagebox.askokcancel(
                APP,
                "A report is a web page, so a link to one has to be hosted "
                "somewhere.\n\n"
                "This puts it in a repository of your own on GitHub and turns "
                "GitHub Pages on, so the link is yours: it keeps working, you "
                "can delete it, and nobody else's server holds your "
                "campaign.\n\n"
                "It needs a GitHub token once. Make one at\n"
                "github.com/settings/tokens — it needs permission to "
                "create repositories and write to them.\n\n"
                "The token is kept in this program's settings file, in plain "
                "text, on this computer only."):
            return ""
        got = simpledialog.askstring(APP, "Paste the GitHub token:",
                                     show="•", parent=self.root)
        got = (got or "").strip()
        if got:
            settings.remember(github_token=got)
        return got

    def share(self):
        report = self.current_report()
        if not report:
            return
        token = self.token()
        if not token:
            return
        # A split report's data has to travel with it, or the link opens on a
        # page that says its data is missing.
        beside = os.path.splitext(report)[0] + ".data.gz"
        extra = [beside] if os.path.isfile(beside) else []
        name = os.path.basename(os.path.dirname(os.path.abspath(report)))
        self.share_button.state(["disabled"])
        self.analyzer.say("\nPublishing the report…\n")
        threading.Thread(target=self._publish, daemon=True,
                         args=(report, token, name, extra)).start()

    def _publish(self, report, token, name, extra):
        """
        Off the UI thread: uploading 20 MB is not instant.

        Nothing here touches a widget. `say` writes into the log box directly
        and belongs to the UI thread alone, so everything this thread has to
        report goes through the same queue the analyzer's own worker uses.
        """
        tell = self.analyzer.log_queue.put
        try:
            url = publish.publish(report, token, name=name, extra=extra,
                                  say=lambda line: tell("  " + line + "\n"))
        except publish.TokenRefused as err:
            # A token GitHub will not take is no use held. Kept, it was
            # handed straight back on every press, and the only way to a
            # new one was editing the settings file by hand -- which every
            # fine-grained token, expiring by default, comes to.
            settings.remember(github_token=None)
            said = "%s It has been forgotten here, so the next publish " \
                   "asks for a new one." % err
            tell("Could not publish it: %s\n" % said)
            self.root.after(0, self.publish_failed, said)
            return
        except publish.PublishError as err:
            tell("Could not publish it: %s\n" % err)
            self.root.after(0, self.publish_failed, str(err))
            return
        except Exception as err:                     # noqa: BLE001
            tell("Could not publish it: %s\n" % err)
            self.root.after(0, self.publish_failed, str(err))
            return
        tell("\nPublished: %s\n" % url)
        self.root.after(0, self.published, url)

    def publish_failed(self, message):
        self.share_button.state(["!disabled"])
        messagebox.showerror(APP, message)

    def published(self, url):
        """Hand the link over, and put it on the clipboard while at it."""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
        except tk.TclError:
            pass
        messagebox.showinfo(
            APP, "The report is at\n\n%s\n\nThe link is on your clipboard. "
                 "GitHub takes a minute or so to build the page the first "
                 "time, so give it a moment before sending it on." % url)

    # -------------------------------------------------------------- closing
    def close(self):
        if self.analyzer.running and not messagebox.askokcancel(
                APP, "The analysis is still running. Close anyway?"):
            return
        if self.keeper.worker and not messagebox.askokcancel(
                APP, "Autosaves are still being kept. Close anyway?\n\n"
                     "Autosaves written after this will not be kept."):
            return
        self.analyzer.stop.set()
        self.keeper.stop.set()
        try:
            self.root.after_cancel(self.tick)
        except tk.TclError:
            pass
        self.root.destroy()


def main():
    # Saves are read on several cores, and a worker on Windows starts by
    # re-running this program. Without this it would open a second window
    # instead of reading a save -- once per core, forever.
    import multiprocessing
    multiprocessing.freeze_support()

    if len(sys.argv) > 1:
        # Handed arguments, the executable is the command line it was built
        # from, exactly as it was before these two became one window.
        gui._attach_console()
        import vic2_analyzer
        return vic2_analyzer.main()

    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w"))

    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    Tools(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

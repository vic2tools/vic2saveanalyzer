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
The autosave keeper's half of the window.

Two folders: the one the game writes saves to, and the one to keep them in.
Press Start before you play and leave it sitting there. The watching happens on
a worker thread so the window stays alive, and every save it copies out is
reported into the log box as it goes. Both paths are remembered between runs.

Built as one tab of the campaign tools by app.py, and still
runnable on its own.
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import keeper
import settings

APP = "Victoria 2 Autosave Keeper"

def default_saves():
    """Where Victoria II writes its saves, if this machine has that folder."""
    for root in settings.game_folders():
        where = os.path.join(root, "save games")
        if os.path.isdir(where):
            return os.path.normpath(where)
    return keeper.SAVES


def default_out():
    """Where to keep them: beside Documents, never inside the game's folder."""
    for docs in settings.documents():
        if os.path.isdir(docs):
            return os.path.join(docs, "Exportsaves")
    return keeper.EXPORT


class Keeper:
    """The window: two folders, a switch, and a running account of the work."""

    def __init__(self, root, parent=None):
        # `parent` is the tab to build into when this is half of the campaign
        # tools; on its own it owns the window. Everything else is the same
        # either way, and `root` is still the toplevel -- `after` and the
        # close handler belong to it, not to a frame.
        self.root = root
        self.queue = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.tally = [0, 0]
        remembered = settings.load(settings.KEEPER,
                                   formerly=settings.KEEPER_FORMERLY)

        alone = parent is None
        if alone:
            root.title(APP)
            root.minsize(680, 420)
        frame = ttk.Frame(root if alone else parent, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self.saves = tk.StringVar(
            value=remembered.get("saves") or default_saves())
        self.out = tk.StringVar(value=remembered.get("out") or default_out())
        self.every = tk.StringVar(value=str(remembered.get("every", 1)))
        self.hand_made = tk.BooleanVar(value=bool(remembered.get("all")))

        self._folder_row(frame, 0, "The game's saves", self.saves,
                         "Where Victoria II writes autosave.v2")
        self._folder_row(frame, 2, "Keep them in", self.out,
                         "One folder per campaign is made in here")

        options = ttk.Frame(frame)
        options.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(options, text="Keep one save every").pack(side="left")
        ttk.Spinbox(options, from_=1, to=12, width=3,
                    textvariable=self.every).pack(side="left", padx=4)
        ttk.Label(options, text="month(s)").pack(side="left")
        ttk.Checkbutton(options, text="Saves I make myself, too",
                        variable=self.hand_made).pack(side="left", padx=(18, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        self.button = ttk.Button(buttons, text="Start", command=self.toggle)
        self.button.pack(side="left")
        ttk.Button(buttons, text="Open the folder",
                   command=self.reveal).pack(side="left", padx=6)
        self.status = ttk.Label(buttons, text="Not watching.")
        self.status.pack(side="left", padx=12)

        frame.rowconfigure(6, weight=1)
        box = ttk.Frame(frame)
        box.grid(row=6, column=0, columnspan=3, sticky="nsew")
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self.log = tk.Text(box, height=12, wrap="none", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(box, command=self.log.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=bar.set)

        self.write("Press Start before you play, and leave this window open.")
        self.write("Every autosave the game writes gets copied out, under the "
                   "in-game date it holds.")
        if alone:
            root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(150, self.drain)

    def _folder_row(self, frame, row, label, variable, hint):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w",
                                          padx=(0, 8), pady=(0, 2))
        ttk.Entry(frame, textvariable=variable).grid(
            row=row, column=1, sticky="ew", pady=(0, 2))
        ttk.Button(frame, text="Browse...",
                   command=lambda: self.browse(variable)).grid(
            row=row, column=2, padx=(8, 0), pady=(0, 2))
        ttk.Label(frame, text=hint, foreground="#666").grid(
            row=row + 1, column=1, sticky="w", pady=(0, 6))

    def browse(self, variable):
        start = variable.get()
        while start and not os.path.isdir(start):
            parent = os.path.dirname(start)
            start = "" if parent == start else parent
        picked = filedialog.askdirectory(
            title=APP, initialdir=start or os.path.expanduser("~"))
        if picked:
            variable.set(os.path.normpath(picked))

    def reveal(self):
        """Show the export folder, making it first if it is not there yet."""
        where = self.out.get()
        try:
            os.makedirs(where, exist_ok=True)
            keeper.open_with_system(where)
        except OSError as err:
            messagebox.showerror(APP, "Cannot open %s\n\n%s" % (where, err))

    def write(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def options(self):
        """What the boxes currently say, as the watcher wants it."""
        try:
            every = max(1, min(12, int(self.every.get())))
        except ValueError:
            every = 1
        self.every.set(str(every))
        return keeper.Options(
            saves=self.saves.get().strip(), out=self.out.get().strip(),
            every=every, all=self.hand_made.get())

    def toggle(self):
        self.stop_watching() if self.worker else self.start_watching()

    def start_watching(self):
        args = self.options()
        bad = keeper.trouble(args)
        if bad:
            messagebox.showerror(APP, bad)
            return
        settings.remember(settings.KEEPER, saves=args.saves, out=args.out,
                          every=args.every, all=args.all)
        self.tally = [0, 0]
        self.stop.clear()
        self.worker = threading.Thread(target=self.work, args=(args,),
                                       daemon=True)
        self.worker.start()
        self.button.configure(text="Stop")
        self.status.configure(text="Watching.")
        self.write("\nWatching %s" % args.saves)
        self.write("Keeping   %s" % args.out)
        if args.every > 1:
            self.write("Keeping one save every %d months." % args.every)

    def work(self, args):
        try:
            keeper.watch(args, report=self.queue.put,
                                  stopped=self.stop.is_set, tally=self.tally)
        except Exception as err:                        # a watcher that dies
            self.queue.put("Stopped: %s" % err)         # says so in the log
        self.queue.put(None)                            # finished

    def stop_watching(self):
        """Ask the worker to stop, and let `drain` tidy up when it has."""
        if self.worker:
            self.stop.set()
            self.button.configure(state="disabled", text="Stopping...")

    def finished(self):
        self.worker = None
        self.button.configure(state="normal", text="Start")
        self.status.configure(text="Not watching. %s" % self.account())
        self.write("Stopped. %s\n" % self.account())

    def account(self):
        kept, size = self.tally
        return "Kept %d save%s, %s." % (
            kept, "" if kept == 1 else "s", keeper.human_size(size))

    def drain(self):
        """Move whatever the worker has said into the log, on the UI thread."""
        try:
            while True:
                line = self.queue.get_nowait()
                if line is None:
                    self.finished()
                else:
                    self.write(line)
        except queue.Empty:
            pass
        if self.worker:
            self.status.configure(text="Watching. %s" % self.account())
        self.root.after(150, self.drain)

    def close(self):
        if self.worker and not messagebox.askokcancel(
                APP, "Stop watching and close?\n\nAutosaves written after this "
                     "will not be kept."):
            return
        self.stop.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        icon = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(
            os.path.abspath(__file__))), "vic2keeper.ico")
        if os.path.isfile(icon):
            root.iconbitmap(icon)
    except tk.TclError:
        pass                        # an iconless window still keeps saves
    Keeper(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

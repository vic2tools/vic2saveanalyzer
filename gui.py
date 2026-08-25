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
A window for the analyzer, so it can be run without a terminal.

Asks for the folder of saves and the mod folder, runs the analysis on a worker
thread so the window stays alive, and streams the same progress the command
line prints into a log box. Paths are remembered between runs.

Packaged as vic2saveanalyzer.exe by build_exe.py.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import vic2_analyzer

APP = "Victoria 2 Save Analyzer"
SETTINGS = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "vic2saveanalyzer", "settings.json")


def _documents():
    """The user's Documents folder, OneDrive's copy included.

    Windows moves Documents under OneDrive when that is switched on, and
    Victoria II follows it there, so both are worth looking at. Neither is
    guaranteed to exist; the caller checks.
    """
    home = os.path.expanduser("~")
    out = []
    for base in (os.environ.get("OneDrive"), os.environ.get("OneDriveConsumer"),
                 home):
        if base:
            out.append(os.path.join(base, "Documents"))
    return out


def _first_folder(candidates):
    """The first of these that is actually there, or ""."""
    for path in candidates:
        if path and os.path.isdir(path):
            return os.path.normpath(path)
    return ""


def default_saves():
    """Where Victoria II keeps saves, if this machine has them.

    The game writes to `Documents/Paradox Interactive/Victoria II/save games`.
    That folder is offered directly when it exists, because it is the one
    holding .v2 files -- a campaign kept in a subfolder of it is one Browse
    away, and the dialog opens there.
    """
    roots = [os.path.join(d, "Paradox Interactive", "Victoria II")
             for d in _documents()]
    return _first_folder([os.path.join(r, "save games") for r in roots] + roots)


def _steam_libraries():
    """Every Steam library folder this machine has, common ones first.

    Steam records extra libraries in `libraryfolders.vdf` beside the default
    one, which is how a game ends up on a second drive. The file is read with
    a regex rather than a vdf parser: one key is wanted out of it.
    """
    seen = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 r"C:\Program Files (x86)", r"C:\Program Files"):
        if base:
            seen.append(os.path.join(base, "Steam"))
    out = list(seen)
    for root in seen:
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if not os.path.isfile(vdf):
            continue
        try:
            with open(vdf, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        import re
        out += [p.replace("\\\\", "\\")
                for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    return out


def default_mod_home():
    """The folder Victoria II keeps its mods in, if this machine has one.

    This is where to *start browsing*, not an answer: `mod/` holds mods, it is
    not one. The entry box stays empty until a mod is picked.
    """
    return _first_folder([
        os.path.join(lib, "steamapps", "common", "Victoria 2", "mod")
        for lib in _steam_libraries()])


def default_out():
    """Where reports go by default.

    Not next to the saves. A folder of saves is the game's, gets synced and
    backed up as the game's, and a campaign folder that has quietly grown an
    `analysis` directory inside it is a folder someone has to tidy later.
    """
    return os.path.join(_first_folder(_documents()) or os.path.expanduser("~"),
                        "Victoria 2 Save Analyzer")


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    except Exception:
        pass                      # remembering paths is a convenience, not a duty


class Pipe:
    """Hands whatever is written straight to the log queue.

    Chunks go through as they were written rather than being held back until a
    line ends, because the analyzer prints "reading foo.v2 ..." and only
    finishes that line once the save is parsed. Buffering would show the two
    halves together, seconds after the interesting half was true.
    """

    def __init__(self, sink):
        self.sink = sink

    def write(self, text):
        if text:
            self.sink.put(text)
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


class App:
    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue()
        self.running = False
        # Set by Stop, read by the analyzer between saves. An Event rather than
        # a flag because the worker thread and the window both touch it.
        self.stop = threading.Event()
        self.report = None
        saved = load_settings()

        root.title(APP)
        root.minsize(680, 460)
        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        # A remembered path wins; otherwise the usual place, so a first run
        # can be one click. `mod_home` is only where Browse opens.
        self.mod_home = default_mod_home()
        self.saves = tk.StringVar(value=saved.get("saves") or default_saves())
        self.mod = tk.StringVar(value=saved.get("mod", ""))
        self.out = tk.StringVar(value=saved.get("out") or default_out())
        self.open_after = tk.BooleanVar(value=saved.get("open_after", True))

        rows = [
            ("Saves folder", self.saves,
             "The folder holding this campaign's .v2 files"),
            ("Mod folder", self.mod,
             "The mod's own folder, the one with common/ and map/ inside"),
            ("Report goes to", self.out,
             "Where to write the report and the spreadsheets"),
        ]
        for i, (label, var, hint) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=i * 2, column=0, sticky="w", pady=(0, 2))
            ttk.Entry(frame, textvariable=var).grid(
                row=i * 2, column=1, sticky="ew", padx=8, pady=(0, 2))
            ttk.Button(frame, text="Browse…", width=10,
                       command=lambda v=var, t=label: self.pick(v, t)).grid(
                row=i * 2, column=2, pady=(0, 2))
            ttk.Label(frame, text=hint, foreground="#666").grid(
                row=i * 2 + 1, column=1, sticky="w", padx=8, pady=(0, 8))

        ttk.Checkbutton(frame, text="Open the report when it is finished",
                        variable=self.open_after).grid(
            row=6, column=1, sticky="w", padx=8)

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=1, sticky="w", padx=8, pady=(10, 6))
        self.button = ttk.Button(buttons, text="Analyze", command=self.start)
        self.button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.cancel,
                                      state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        self.status = ttk.Label(frame, text="Pick a saves folder to begin.")
        self.status.grid(row=7, column=2, sticky="e", pady=(10, 6))

        self.log = tk.Text(frame, height=14, wrap="none",
                           background="#2A0F17", foreground="#F4E7CC",
                           insertbackground="#F4E7CC", relief="flat")
        self.log.grid(row=8, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(8, weight=1)
        bar = ttk.Scrollbar(frame, command=self.log.yview)
        bar.grid(row=8, column=3, sticky="ns")
        self.log.configure(yscrollcommand=bar.set, state="disabled")

        root.after(80, self.drain)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------------------------------------------------------- helpers
    def pick(self, var, label):
        start = var.get()
        if not start:
            start = (self.mod_home if var is self.mod
                     else default_saves() if var is self.saves else "")
        chosen = filedialog.askdirectory(
            title=label, initialdir=start or os.path.expanduser("~"))
        if chosen:
            var.set(os.path.normpath(chosen))

    def say(self, chunk):
        """Append output, treating a carriage return the way a console does."""
        self.log.configure(state="normal")
        for i, piece in enumerate(chunk.split("\r")):
            if i:
                self.log.delete("end-1c linestart", "end-1c")
            self.log.insert("end", piece)
        self.log.see("end")
        self.log.configure(state="disabled")

    def drain(self):
        while True:
            try:
                self.say(self.log_queue.get_nowait())
            except queue.Empty:
                break
        self.root.after(80, self.drain)

    def cancel(self):
        """Ask the run to stop at the next save it has not started."""
        if not self.running:
            return
        self.stop.set()
        self.stop_button.configure(state="disabled")
        self.status.configure(text="Stopping…")
        self.log_queue.put("\nStopping. Saves already being read will finish "
                           "first; nothing new will be started.\n")

    def close(self):
        if self.running and not messagebox.askokcancel(
                APP, "The analysis is still running. Close anyway?"):
            return
        self.stop.set()
        self.root.destroy()

    # ------------------------------------------------------------------- run
    def start(self):
        if self.running:
            return
        saves = self.saves.get().strip()
        if not saves or not os.path.exists(saves):
            messagebox.showerror(APP, "Pick the folder holding your .v2 saves.")
            return
        mod = self.mod.get().strip()
        if mod and not os.path.isdir(os.path.join(mod, "common")):
            messagebox.showerror(
                APP, "That mod folder has no common/ inside it.\n\n"
                     "Point it at the mod's own folder, the one holding "
                     "common/, map/ and history/.")
            return
        if not mod and not messagebox.askokcancel(
                APP, "Without a mod folder the report loses the map, the "
                     "technology tree, the great powers and the war goals, and "
                     "mobilisation size falls back to a fixed guess.\n\n"
                     "Carry on anyway?"):
            return
        out = self.out.get().strip() or default_out()
        self.out.set(out)
        save_settings({"saves": saves, "mod": mod, "out": out,
                       "open_after": self.open_after.get()})

        self.running = True
        self.stop.clear()
        self.button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.configure(text="Working…")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        threading.Thread(target=self.work, args=(saves, mod, out),
                         daemon=True).start()

    def work(self, saves, mod, out):
        argv = [sys.argv[0], saves, "-o", out]
        if mod:
            argv += ["--mod-path", mod]
        old_argv, old_out, old_err = sys.argv, sys.stdout, sys.stderr
        sys.argv = argv
        sys.stdout = sys.stderr = Pipe(self.log_queue)
        vic2_analyzer.set_cancel_check(self.stop.is_set)
        ok = True
        stopped = False
        try:
            vic2_analyzer.main()
        except vic2_analyzer.Cancelled:
            ok = False
            stopped = True
            self.log_queue.put("\nStopped. Every save read so far is cached, so "
                               "starting again picks up where this left off.\n")
        except SystemExit as stop:          # sys.exit on a path it cannot read
            ok = not stop.code
            if stop.code:
                self.log_queue.put(f"\n{stop.code}\n")
        except Exception:
            ok = False
            import traceback
            self.log_queue.put("\n" + traceback.format_exc())
        finally:
            vic2_analyzer.set_cancel_check(None)
            sys.argv, sys.stdout, sys.stderr = old_argv, old_out, old_err
        self.report = os.path.join(out, "report.html")
        if ok and os.path.isfile(self.report):
            self.log_queue.put(f"\nReport written to {self.report}\n")
        self.root.after(0, self.finished, ok, stopped)

    def finished(self, ok, stopped=False):
        self.running = False
        self.button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        done = ok and os.path.isfile(self.report or "")
        self.status.configure(
            text="Done." if done else "Stopped." if stopped
            else "Failed — see the log.")
        if done and self.open_after.get():
            try:
                os.startfile(self.report)       # noqa: S606  (Windows only)
            except Exception:
                subprocess.Popen(["cmd", "/c", "start", "", self.report],
                                 shell=False)
        elif not done and not stopped:
            messagebox.showerror(APP, "The analysis did not finish. The log "
                                      "has the details.")


def _attach_console():
    """Borrow the console that launched us, if there was one.

    A windowed build has no console of its own, which is the point -- double
    clicking it should not flash a black box. Run from a shell with arguments
    though, and printing to nowhere would be useless, so it attaches to the
    shell's console instead. The shell does not wait for a windowed program, so
    its prompt comes back before the output does.
    """
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return
    import ctypes
    ATTACH_PARENT_PROCESS = -1
    if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        return
    for name in ("stdout", "stderr"):
        try:
            setattr(sys, name,
                    open("CONOUT$", "w", buffering=1, errors="replace"))
        except OSError:
            pass


def main():
    # Saves are read on several cores, and a worker on Windows starts by
    # re-running this program. Without this it would open a second window
    # instead of waiting for a save to read -- once per core, forever.
    import multiprocessing
    multiprocessing.freeze_support()

    if len(sys.argv) > 1:
        # Handed arguments, the executable is the command line it was built
        # from -- every flag, --explain-mob and all.
        _attach_console()
        return vic2_analyzer.main()

    # Otherwise there are no streams at all: Python hands a windowed build None
    # for both. Anything printed before the worker swaps in the log box -- a
    # warning raised while a module is imported, say -- would land on None.
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w"))

    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

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
AUTO = "(work it out from the saves)"


def human_size(count):
    """A byte count the way a person would say it."""
    if count < 1024:
        return "%d byte%s" % (count, "" if count == 1 else "s")
    for unit in ("KB", "MB", "GB"):
        count /= 1024.0
        if count < 1024 or unit == "GB":
            break
    return "%.0f %s" % (count, unit) if count >= 10 else (
        "%.1f %s" % (count, unit))


def _plural(n, one, many):
    """`1 entry`, `12 entries`, `1,128 entries`."""
    return "%s %s" % (format(n, ","), one if n == 1 else many)


def saves_kind(path):
    """
    Whether a folder holds saves, or holds folders of saves.

    Both are things somebody would reasonably drop here: one campaign, or the
    directory all the campaigns live in. The analyzer's own walker answers this,
    rather than a second one here that could disagree with it about what counts.
    Returns (kind, how many campaigns).
    """
    try:
        import cross
        found = cross.campaigns_in(path)
    except Exception:
        return "bad", 0
    if not found:
        return "bad", 0
    if len(found) == 1 and os.path.normpath(found[0][1]) == os.path.normpath(path):
        return "one", 1
    return "many", len(found)


def mod_kind(path):
    """
    Whether this is one mod, or the folder every mod lives in.

    Pointing at `Victoria 2/mod` used to be an error. It is now the way to say
    "work out which mod each campaign used", which the analyzer can do from the
    saves themselves. Returns (kind, the game root to search from).
    """
    if not path:
        return "none", None
    if os.path.isdir(os.path.join(path, "common")):
        return "mod", path
    bare = os.path.normpath(path)
    home = bare if os.path.basename(bare).lower() == "mod" \
        else os.path.join(bare, "mod")
    if os.path.isdir(home):
        try:
            for name in os.listdir(home):
                if os.path.isdir(os.path.join(home, name, "common")):
                    return "home", os.path.dirname(home)
        except OSError:
            pass
    return "bad", None


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
        self.mod_paths = {}
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
             "One campaign's .v2 files, or the folder all your campaigns "
             "live in"),
            ("Mod folder", self.mod,
             "The mod's own folder, the one with common/ inside -- or "
             "Victoria 2/mod, to work each campaign's mod out from its saves"),
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

        # Only meaningful when the saves folder holds more than one campaign,
        # so it stays out of the way until it does.
        # One row per campaign, each with the mod it was played on. Two mods
        # built on the same base can agree on everything a save records except
        # a handful of provinces, so working it out is a good guess and no
        # more; this is where it can be settled instead.
        self.primary = tk.StringVar(value="")
        self.rows = []
        self.campaign_names = []
        self.primary_row = ttk.Frame(frame)
        head = ttk.Frame(self.primary_row)
        head.pack(fill="x")
        ttk.Label(head, text="Campaigns").pack(side="left")
        ttk.Label(head, text="the marked one is what the map, wars and tech "
                             "tree are about", foreground="#666").pack(
            side="left", padx=8)
        # A canvas, because thirty campaigns will not fit and must scroll.
        holder = ttk.Frame(self.primary_row)
        holder.pack(fill="both", expand=True)
        # Height is set from the row count in `refresh_campaigns`; a fixed one
        # left two campaigns sitting above four rows of nothing.
        self.camp_canvas = tk.Canvas(holder, height=26, highlightthickness=0,
                                     borderwidth=0)
        self.camp_canvas.pack(side="left", fill="both", expand=True)
        camp_bar = ttk.Scrollbar(holder, orient="vertical",
                                 command=self.camp_canvas.yview)
        camp_bar.pack(side="right", fill="y")
        self.camp_canvas.configure(yscrollcommand=camp_bar.set)
        self.camp_inner = ttk.Frame(self.camp_canvas)
        self.camp_window = self.camp_canvas.create_window(
            (0, 0), window=self.camp_inner, anchor="nw")
        self.camp_inner.bind(
            "<Configure>",
            lambda _e: self.camp_canvas.configure(
                scrollregion=self.camp_canvas.bbox("all")))
        self.camp_canvas.bind(
            "<Configure>",
            lambda e: self.camp_canvas.itemconfigure(self.camp_window,
                                                     width=e.width))
        self.primary_row.grid(row=6, column=0, columnspan=3, sticky="ew",
                              padx=8, pady=(0, 6))
        self.primary_row.grid_remove()

        ttk.Checkbutton(frame, text="Open the report when it is finished",
                        variable=self.open_after).grid(
            row=7, column=1, sticky="w", padx=8)

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=1, sticky="w", padx=8, pady=(10, 6))
        self.button = ttk.Button(buttons, text="Analyze", command=self.start)
        self.button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.cancel,
                                      state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        self.status = ttk.Label(frame, text="Pick a saves folder to begin.")
        self.status.grid(row=8, column=2, sticky="e", pady=(10, 6))

        self.log = tk.Text(frame, height=14, wrap="none",
                           background="#2A0F17", foreground="#F4E7CC",
                           insertbackground="#F4E7CC", relief="flat")
        self.log.grid(row=9, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(9, weight=1)
        bar = ttk.Scrollbar(frame, command=self.log.yview)
        bar.grid(row=9, column=3, sticky="ns")
        self.log.configure(yscrollcommand=bar.set, state="disabled")

        # A footer rather than a place in the main flow: emptying the
        # cache is housekeeping, not a step in running an analysis.
        foot = ttk.Frame(frame)
        foot.grid(row=10, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.cache_label = ttk.Label(foot, text="", foreground="#666")
        self.cache_label.pack(side="left")
        self.cache_button = ttk.Button(foot, text="Wipe cache", width=12,
                                       command=self.wipe_cache)
        self.cache_button.pack(side="right")
        self.refresh_cache()

        self.saves.trace_add("write", lambda *_a: self.refresh_campaigns())
        self.mod.trace_add("write", lambda *_a: self.refresh_campaigns())
        self.refresh_campaigns()

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

    def mod_choices(self):
        """`(work it out)` plus every mod beside the one in the mod box."""
        mod = self.mod.get().strip()
        kind, where = mod_kind(mod)
        if kind == "home":
            home = os.path.join(where, "mod")
        elif kind == "mod":
            home = os.path.dirname(os.path.normpath(mod))
        else:
            return [AUTO]
        out = {}
        try:
            for name in sorted(os.listdir(home)):
                path = os.path.join(home, name)
                if os.path.isdir(os.path.join(path, "common")):
                    out[name] = path
        except OSError:
            pass
        self.mod_paths = out
        return [AUTO] + list(out)

    def refresh_campaigns(self):
        """
        A row per campaign under the saves folder, when there is more than one.

        Only the folders are read here, never the saves: this runs on every
        keystroke in the saves box, and identifying a mod means reading a whole
        30 MB file. Rows default to working it out, which happens during the
        run, and a row set to a named mod skips that entirely.
        """
        path = self.saves.get().strip()
        found = []
        if path and os.path.isdir(path):
            try:
                import cross
                found = sorted(cross.campaigns_in(path),
                               key=lambda e: -len(e[2]))
            except Exception:
                found = []
        if len(found) < 2:
            self.primary_row.grid_remove()
            self.rows, self.campaign_names = [], []
            self.primary.set("")
            return

        keep_main = self.primary.get()
        keep_mods = {r["name"]: r["mod"].get() for r in self.rows}
        for child in self.camp_inner.winfo_children():
            child.destroy()
        self.rows = []
        choices = self.mod_choices()
        for name, _path, files in found:
            line = ttk.Frame(self.camp_inner)
            line.pack(fill="x", pady=1)
            ttk.Radiobutton(line, value=name, variable=self.primary).pack(
                side="left")
            ttk.Label(line, text=name, width=22).pack(side="left")
            ttk.Label(line, text="%d saves" % len(files), width=9,
                      foreground="#666").pack(side="left")
            picked = tk.StringVar(
                value=keep_mods.get(name) if keep_mods.get(name) in choices
                else AUTO)
            box = ttk.Combobox(line, state="readonly", width=32,
                               textvariable=picked, values=choices)
            box.pack(side="left", padx=6)
            self.rows.append({"name": name, "mod": picked})
        self.campaign_names = [r["name"] for r in self.rows]
        # Room for the rows there are, up to five; past that it scrolls.
        self.camp_canvas.configure(height=min(len(self.rows), 5) * 26 + 2)
        self.primary_row.grid()
        if keep_main not in self.campaign_names:
            self.primary.set(self.campaign_names[0])   # the most saves

    def refresh_cache(self):
        """Put what the cache currently weighs on the footer."""
        count, size = vic2_analyzer.cache_stats()
        if not count:
            self.cache_label.configure(text="Parse cache: empty")
            self.cache_button.configure(state="disabled")
            return
        self.cache_label.configure(
            text="Parse cache: %s in %s"
                 % (human_size(size), _plural(count, "entry", "entries")))
        self.cache_button.configure(
            state="disabled" if self.running else "normal")

    def wipe_cache(self):
        """Empty the cache, having said plainly what that costs."""
        if self.running:
            return
        count, size = vic2_analyzer.cache_stats()
        if not count:
            self.refresh_cache()
            return
        if not messagebox.askokcancel(
                APP,
                "Delete %s of remembered saves?\n\n"
                "Your saves and your reports are untouched. What goes is "
                "the record of what each save was read as, which is what "
                "makes a second run of the same campaign take seconds "
                "instead of reading every file again. The cost is one "
                "slow run per campaign.\n\n"
                "Most of it is usually spent already: an entry is tied to "
                "the version of the program that wrote it, so every update "
                "leaves the previous entries behind unread."
                % human_size(size)):
            return
        removed, freed = vic2_analyzer.clear_cache()
        self.say("\nWiped %s from the parse cache, freeing %s.\n"
                 % (_plural(removed, "entry", "entries"),
                    human_size(freed)))
        self.refresh_cache()

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
        shape, campaigns = saves_kind(saves)
        if shape == "bad":
            messagebox.showerror(
                APP, "No .v2 saves in that folder, or in any folder inside "
                     "it.\n\nPoint it either at one campaign's saves, or at "
                     "the folder all your campaigns live in.")
            return

        mod = self.mod.get().strip()
        # `mod_kind` hands back the mod when one was picked and the game root
        # when the folder of mods was, so only the second is a search root.
        kind, where = mod_kind(mod)
        game_root = where if kind == "home" else None
        if kind == "bad":
            messagebox.showerror(
                APP, "That folder is neither a mod nor the folder mods live "
                     "in.\n\nPoint it at the mod's own folder, the one "
                     "holding common/, map/ and history/ -- or at "
                     "Victoria 2/mod itself, and each campaign's mod will be "
                     "worked out from its own saves.")
            return
        if not mod and not messagebox.askokcancel(
                APP, "Without a mod folder the report loses the map, the "
                     "technology tree, the great powers and the war goals, and "
                     "mobilisation size falls back to a fixed guess.\n\n"
                     "Carry on anyway?"):
            return
        # Several campaigns, or a mod that has to be identified, both mean
        # the cross-campaign path. It reads one campaign quite happily, so a
        # single folder with an unidentified mod goes through it too.
        cross = shape == "many" or kind == "home"
        if cross and shape == "many":
            self.log_queue.put(
                "%d campaigns under that folder. Each will be read under the "
                "mod its own saves point to.\n\n" % campaigns)

        out = self.out.get().strip() or default_out()
        self.out.set(out)
        save_settings({"saves": saves, "mod": mod, "out": out,
                       "open_after": self.open_after.get()})

        self.running = True
        self.stop.clear()
        self.cache_button.configure(state="disabled")
        self.button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.configure(text="Working…")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        chosen = self.primary.get() if cross else ""
        told = []
        if cross:
            for row in self.rows:
                pick = row["mod"].get()
                if pick and pick != AUTO:
                    told.append("%s=%s" % (row["name"],
                                           self.mod_paths.get(pick, pick)))
        threading.Thread(target=self.work,
                         args=(saves, mod, out, cross, game_root, chosen, told),
                         daemon=True).start()

    def work(self, saves, mod, out, cross=False, game_root=None, primary="",
             told=()):
        argv = [sys.argv[0], saves, "-o", out]
        if cross:
            argv += ["--cross"]
            if primary:
                argv += ["--primary", primary]
            for pair in told:
                argv += ["--campaign-mod", pair]
        # Naming one mod and naming the folder mods live in are different
        # instructions and must not be run together. `--mod-path` says "this
        # one, for every campaign"; `--game-root` says "work it out from each
        # campaign's own saves, searching here". Passing a chosen mod as the
        # root made the search look for candidates *inside* that mod, where
        # the only thing it could find was the mod itself under the wrong
        # name -- so every campaign was matched to it whether it fitted or not.
        if game_root:
            argv += ["--game-root", game_root]
        elif mod:
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
        self.refresh_cache()          # the run just added to it
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

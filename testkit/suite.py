#!/usr/bin/env python3
"""
Every check, in the order they run, and what each needs.

`all.py` runs this list, `all.py --update-expected` re-records the ones that
hold records, and the README points here rather than keeping a copy:

    python3 testkit/suite.py --list

What a check can need:

    scanner   the Rust scanner built (cargo build --release in scanner/)
    saves     a folder of .v2 saves from one campaign
    mod       that campaign's mod folder
    report    a report built from those saves (all.py builds one)
    firefox   Firefox, run headless
    display   a desktop for a Tk window
    rustc     the Rust compiler
    baseline  a recorded baseline ($VIC2_BASELINE)

A check whose needs are not met here is skipped and says which; one that
finds a need missing itself exits 77 (`outcome.SKIPPED`).
"""
import os
import sys
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass(frozen=True)
class Check:
    script: str
    title: str
    needs: frozenset = frozenset()
    records: bool = False       # holds recorded answers; --update re-records
    exclusive: bool = False     # drives a window or a browser: runs alone
    after_report: bool = False  # reads the report all.py builds first
    optional: frozenset = frozenset()  # handed when given: "saves", "mod"
    extra: tuple = ()           # arguments after the needs


def _c(script, title, needs=(), optional=(), **kw):
    return Check(script, title, frozenset(needs), optional=frozenset(optional), **kw)


CHECKS = [
    # First: every check below that writes a save writes it with savefmt.
    _c("savefmt.py", "the save-builder the tests use", ["scanner"]),
    _c("tooearly.py", "names read before they exist"),
    _c("saveshapes.py", "the shapes a save can take", ["scanner"], records=True),
    _c("keeping.py", "the keeper"),
    _c("histories.py", "one game's saves told from another's", ["scanner"]),
    _c("mangled.py", "damaged saves", ["scanner"], records=True),
    _c("sharing.py", "sharing a report", ["display"], exclusive=True),
    _c("packing.py", "what the executable carries", ["scanner"]),
    _c("matching.py", "matching a campaign to its mod", ["scanner"]),
    _c("engine_runtime.py", "the engine process and test fixtures", ["scanner"]),
    _c("modread.py", "the mod reader", ["scanner"], optional=["mod"], records=True),
    _c("frontcheck.py", "the run's front end", ["scanner"], records=True),
    _c("enginefmt.py", "the engine's number formatting", ["scanner"],
       extra=("SCANNER", "20000")),
    _c("enginecompress.py", "the engine's compression", ["scanner"], extra=("SCANNER",)),
    _c("raster.py", "the map's province bitmap", ["scanner"]),
    _c("caching.py", "what the engine keeps between runs", ["scanner"]),
    _c("staleness.py", "what can make a report stale", ["scanner"]),
    _c("mobrate.py", "the mobilisation rate rule", ["scanner"]),
    _c("crossrows.py", "the cross block against the report", ["scanner"], records=True),
    # The real campaign.
    _c("mangled.py", "a real save, damaged", ["scanner", "saves"], extra=("ONE-SAVE", "4")),
    _c("invariants.py", "the numbers against each other", ["report"], after_report=True,
       extra=("TABLE", "REPORT")),
    _c("facts.py", "the payload split", ["report"], after_report=True, extra=("REPORT",)),
    _c("boots.py", "the report in a browser", ["report", "firefox"], after_report=True,
       exclusive=True, extra=("REPORT",)),
    _c("state_history_ui.py", "state history decoded in the browser", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("war_legacy_ui.py", "the war view's layouts and losses", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("compare_ui.py", "the Compare tab's metrics and hull chart", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("export_ui.py", "PNG downloads of the charts and the map", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("war_export_ui.py", "a war's summary as a PNG", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("military_ui.py", "the military ledgers", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("population_history_ui.py", "the population history chart", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("map_rendering.py", "the map's pixels, seams and cache", ["report", "firefox"],
       after_report=True, exclusive=True, extra=("REPORT",)),
    _c("window.py", "the window", ["saves", "display"], exclusive=True),
    _c("enginecheck.py", "the report engine against its recorded answers",
       ["scanner"], optional=["saves", "mod"], records=True),
]


def scanner_path():
    return os.path.join(ROOT, "scanner", "target", "release",
                        "vic2scan" + (".exe" if os.name == "nt" else ""))


def unmet(check, *, saves="", mod="", report="", baseline="", have=None):
    """The needs of `check` not met here, by name. `have` overrides the
    probes for tools (a set of the tool needs present)."""
    present = set(have if have is not None else tools_here())
    if saves:
        present.add("saves")
    if mod:
        present.add("mod")
    if report:
        present.add("report")
    if baseline:
        present.add("baseline")
    return sorted(check.needs - present)


def tools_here():
    """Which of scanner, firefox, display and rustc this machine has."""
    import shutil
    found = set()
    if os.path.isfile(scanner_path()):
        found.add("scanner")
    try:
        import browser
        if browser.firefox():
            found.add("firefox")
    except ImportError:
        pass
    if os.name == "nt" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        found.add("display")
    if shutil.which("rustc") or os.path.isfile(os.path.join(
            os.path.expanduser("~"), ".cargo", "bin", "rustc" + (".exe" if os.name == "nt" else ""))):
        found.add("rustc")
    return found


def argv_for(check, *, saves="", mod="", report="", baseline="", have=None):
    """[the check's script, its arguments], or None if a need is unmet."""
    if unmet(check, saves=saves, mod=mod, report=report, baseline=baseline, have=have):
        return None
    out = os.path.dirname(report) if report else ""
    words = {"SCANNER": scanner_path(), "REPORT": report,
             "TABLE": os.path.join(out, "nations_timeseries.csv")}
    argv = [os.path.join(ROOT, "testkit", check.script)]
    wanted = check.needs | {o for o in check.optional if {"saves": saves, "mod": mod}[o]}
    if "saves" in wanted and "ONE-SAVE" not in check.extra:
        argv.append(saves)
    if "mod" in wanted:
        argv += ["--mod", mod]
    if "baseline" in check.needs:
        argv += ["--from", baseline]
    for e in check.extra:
        if e == "ONE-SAVE":
            first = next((f for f in sorted(os.listdir(saves)) if f.endswith(".v2")), None)
            if first is None:
                return None
            argv.append(os.path.join(saves, first))
        else:
            argv.append(words.get(e, e))
    return argv


def main():
    if "--list" not in sys.argv[1:]:
        print(__doc__.strip())
        return 0
    width = max(len(c.title) for c in CHECKS)
    for c in CHECKS:
        print("%-*s  %-22s %s" % (width, c.title, c.script, " ".join(sorted(c.needs)) or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

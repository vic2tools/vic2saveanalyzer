"""
What every check leans on: where the repo and the scanner are, running the
analyzer, a temp folder of its own, and skipping when something a check
needs is not on this machine.

A check is run as `python testkit/NAME.py`, which puts `testkit/` on the
import path; importing this puts the repo itself there too, for the checks
that import the program's own modules.
"""
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile

from outcome import SKIPPED

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNER = os.path.join(ROOT, "scanner", "target", "release",
                       "vic2scan" + (".exe" if os.name == "nt" else ""))

if ROOT not in sys.path:
    sys.path.insert(1, ROOT)


def analyze(*argv, env=None, cwd=ROOT, timeout=900):
    """`vic2_analyzer.py ARGV` run to the end, its output captured as text."""
    return subprocess.run([sys.executable, os.path.join(ROOT, "vic2_analyzer.py")] + list(argv),
                          capture_output=True, text=True, env=env, cwd=cwd, timeout=timeout)


def env_in(folder):
    """The environment with every temp-folder variable pointing into
    `folder`, so nothing run under it touches the real caches."""
    os.makedirs(folder, exist_ok=True)
    return dict(os.environ, TMPDIR=folder, TEMP=folder, TMP=folder)


@contextlib.contextmanager
def holding(prefix):
    """(a temp folder, an environment whose temp folder is inside it),
    removed afterwards."""
    where = tempfile.mkdtemp(prefix=prefix)
    try:
        yield where, env_in(os.path.join(where, "tmp"))
    finally:
        shutil.rmtree(where, ignore_errors=True)


def skip(why):
    print(why)
    sys.exit(SKIPPED)


def need_scanner():
    if not os.path.isfile(SCANNER):
        skip("needs the scanner built: cargo build --release --manifest-path scanner/Cargo.toml")


def need_firefox():
    import browser
    if browser.firefox() is None:
        skip("no firefox here, so nothing was opened")


def need_display():
    if os.name != "nt" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        skip("no display here, so no window was opened")


def need_rustc():
    found = shutil.which("rustc") or os.path.isfile(os.path.join(
        os.path.expanduser("~"), ".cargo", "bin", "rustc" + (".exe" if os.name == "nt" else "")))
    if not found:
        skip("needs rustc")

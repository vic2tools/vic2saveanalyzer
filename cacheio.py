"""Optional disk caches: compressed pickles, replaced atomically.

A failed read is a cache miss. A failed write must leave the previous entry
intact, including when another analyzer is reading or writing the same slot.
"""

import hashlib
import os
import pickle
import re
import sys
import tempfile
import zlib


# A line that imports something -- `import a, b.c` or `from a import ...` --
# at any indentation, because the imports that most need finding are the ones
# made inside a function.
_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+([A-Za-z_]\w*)[ \t]+import\b"
    r"|import[ \t]+([A-Za-z_][\w.]*(?:[ \t]*,[ \t]*[A-Za-z_][\w.]*)*))",
    re.M)


def sources_reached(*paths):
    """
    These source files, and every file of this program they import, and
    every one those import, as a sorted list of paths.

    A cache keyed on a hash of the code that fills it has to hash all of
    that code, and a list of files written out by hand stops being all of it
    the first time code moves from a file on the list to one that is not.
    The parse cache's list did exactly that: the fold that fills every
    parsed save moved out of `fastscan.py`, which was on it, into
    `nation.py`, which was not, and an edit to that fold went on being
    served out of parses the old fold had made.

    Read off the source a line at a time rather than parsed. A real parse of
    the reader's five files costs 12 ms, and this is asked on the way to
    answering a run that has nothing to do, which takes 80 in all. The price
    is that an import written oddly -- two on a line after a semicolon, one
    after an `if x:` -- goes unfollowed, which is why `testkit/caching.py`
    walks the same imports properly and edits each file in turn to see the
    key move.
    """
    folder = os.path.dirname(os.path.abspath(paths[0]))
    try:
        ours = {name[:-3] for name in os.listdir(folder)
                if name.endswith(".py")}
    except OSError:
        ours = set()
    seen, todo = set(), [os.path.abspath(path) for path in paths]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError:
            continue              # hashing it fails too, and turns caching off
        for single, several in _IMPORT.findall(source):
            for name in [single] if single else several.split(","):
                name = name.strip().split(".")[0]
                if name in ours:
                    todo.append(os.path.join(folder, name + ".py"))
    return sorted(seen)


def source_fingerprint(*paths):
    """Version derived from source files, or from the packaged executable."""
    digest = hashlib.sha256()
    try:
        if getattr(sys, "frozen", False):
            stat = os.stat(sys.executable)
            digest.update(f"{sys.executable}|{stat.st_size}|{stat.st_mtime_ns}"
                          .encode("utf-8"))
        else:
            for path in paths:
                with open(path, "rb") as fh:
                    digest.update(fh.read())
    except OSError:
        return ""
    return digest.hexdigest()


def load(slot):
    """Return a cached value, or None for a missing or unreadable entry."""
    if not slot:
        return None
    try:
        with open(slot, "rb") as fh:
            return pickle.loads(zlib.decompress(fh.read()))
    except (OSError, EOFError, pickle.PickleError, zlib.error,
            ValueError, TypeError, AttributeError, ImportError):
        return None


def store(slot, value):
    """Publish one complete entry. Cache failures never prevent analysis."""
    if not slot:
        return
    temporary = None
    try:
        data = zlib.compress(pickle.dumps(value, protocol=5), 1)
        folder = os.path.dirname(slot)
        os.makedirs(folder, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp",
                                         delete=False) as fh:
            temporary = fh.name
            fh.write(data)
        os.replace(temporary, slot)
    except (OSError, pickle.PickleError, TypeError):
        pass
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass

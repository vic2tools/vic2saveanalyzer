"""Optional disk caches: compressed pickles, replaced atomically.

A failed read is a cache miss. A failed write must leave the previous entry
intact, including when another analyzer is reading or writing the same slot.
"""

import hashlib
import os
import pickle
import sys
import tempfile
import zlib


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

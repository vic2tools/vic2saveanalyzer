"""
The two ways a run is made, for the checks that have to see both.

An ordinary run is made by the report engine (`engine.py`, the scanner's
`report` mode), and a run the engine hands back -- a save it will not read,
a diagnostic -- is made in Python, as every run used to be. A check of how a
run behaves (what it writes when a table is locked, what it leaves behind,
how it judges a war, what it does with a name that is markup) holds for
both only if it is run both ways, so the bug it was written for is caught in
whichever of the two it is put back into.
"""

import os

# (name, what the environment says). `strict` makes a run that the engine
# hands back an error rather than a quiet run in Python, so a check that
# meant to test the engine cannot pass on the Python instead; the edge cases
# leave it off, because handing some of them back is the right answer.
WAYS = (("engine", {"VIC2_NO_ENGINE": None}),
        ("python", {"VIC2_NO_ENGINE": "1"}))


def env(way, base=None, strict=False):
    """`base` (or this process's environment) set up for one way."""
    out = dict(os.environ if base is None else base)
    for key, value in dict(WAYS)[way].items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    out.pop("VIC2_ENGINE_REQUIRED", None)
    if strict and way == "engine":
        out["VIC2_ENGINE_REQUIRED"] = "1"
    return out


class set_way:
    """`with set_way("python"):` -- this process's environment, for a while."""

    def __init__(self, way, strict=False):
        self.way = way
        self.strict = strict
        self.saved = None

    def __enter__(self):
        self.saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(env(self.way, self.saved, self.strict))
        return self

    def __exit__(self, *exc):
        os.environ.clear()
        os.environ.update(self.saved)
        return False

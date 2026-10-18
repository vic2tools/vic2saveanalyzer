"""
Recorded answers, and holding a run to them.

A check runs each of its cases and compares the answer with the one
recorded for it: the exit status, what was printed to stdout and to stderr, and every
file the run left but the stamp. The page is kept as what it carries -- the
payload as indented JSON with each flag's PNG and each state snapshot
decoded, the state chunks beside it, and the page around them as its
difference from the template -- because its compressed parts are one
compressor's bytes and only what they hold is the answer.

    <root>/<check>/<case>/status.txt, stdout.txt, stderr.txt, written.txt
    <root>/<check>/<case>/<file>         (a file of more than a megabyte: <file>.gz)

The records are kept in `testkit/expected/`; a campaign's own answers are
kept by `baseline.py`, outside the repository, in the same layout.

After a deliberate change to what the program answers, one command writes
the new answers over the old (`python3 testkit/all.py --update-expected`, or
`--update` to one check), and `git diff testkit/expected` shows what changed.
"""

import base64
import difflib
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zlib
import kit                                                  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(HERE, "testkit", "expected")
BIG = 1 << 20

# How many cores a read takes follows the memory free at that moment, so
# that one number is not part of an answer.
CORES = re.compile(r"(save\(s\) on )\d+( cores)")


# ------------------------------------------------------------- the page

def png_pixels(uri):
    """A PNG data URI as its header and a hash of its pixels."""
    raw = base64.b64decode(uri.split(",", 1)[1])
    at, ihdr, idat = 8, b"", b""
    while at < len(raw):
        n = int.from_bytes(raw[at:at + 4], "big")
        tag = raw[at + 4:at + 8]
        if tag == b"IHDR":
            ihdr = raw[at + 8:at + 8 + n]
        elif tag == b"IDAT":
            idat += raw[at + 8:at + 8 + n]
        at += 12 + n
    return "png:%s:%s" % (ihdr.hex(), hashlib.sha256(zlib.decompress(idat)).hexdigest())


def chunk_text(b64):
    return gzip.decompress(base64.b64decode(b64)).decode("utf-8")


def template():
    """The page the scanner is built from: the files `scanner/src/page/order.txt`
    names, joined in its order, as `scanner/build.rs` joins them."""
    page = os.path.join(HERE, "scanner", "src", "page")
    with open(os.path.join(page, "order.txt"), encoding="utf-8") as fh:
        names = [l.strip() for l in fh if l.strip() and not l.strip().startswith("#")]
    text = []
    for name in names:
        with open(os.path.join(page, name), encoding="utf-8", newline="") as fh:
            text.append(fh.read())
    return "".join(text)


def page(folder):
    """
    (the payload as normal JSON text, the state chunks, the page around
    them) of the report in `folder`.
    """
    html = open(os.path.join(folder, "report.html"), encoding="utf-8").read()
    packed = re.search(r'const PACKED = "([^"]*)"', html)[1]
    if packed:
        text = gzip.decompress(base64.b64decode(packed)).decode("utf-8")
    else:
        with open(os.path.join(folder, "report.data.gz"), "rb") as fh:
            text = gzip.decompress(fh.read()).decode("utf-8")
    data = json.loads(text)
    if data.get("flags"):
        data["flags"] = {k: png_pixels(v) for k, v in data["flags"].items()}
    board = data.get("map")
    if board and board.get("populationStateChunks"):
        board["populationStateChunks"] = [[d, chunk_text(c)]
                                          for d, c in board["populationStateChunks"]]
    beside = re.search(r'const STATE_CHUNKS = (\[.*?\]);\n', html, re.S)
    states = [[d, chunk_text(c)] for d, c in json.loads(beside[1])] if beside else []
    shell = html.replace(packed, "<DATA>") if packed else html
    if beside:
        shell = shell.replace(beside[0], "<STATES>")
    return json.dumps(data, separators=(",", ":")), json.dumps(states), shell


def indented(text):
    """Compact JSON text as one value to a line or so, for reading a difference."""
    return json.dumps(json.loads(text), indent=1, ensure_ascii=False) + "\n"


def shell_diff(shell):
    """The page around the payload as its difference from the template."""
    lines = difflib.unified_diff(template().splitlines(), shell.splitlines(),
                                 lineterm="", n=0)
    # Without the template's line numbers, so an edit elsewhere in the
    # template does not move every record.
    return "".join("@@\n" if l.startswith("@@") else l + "\n" for l in list(lines)[2:])


# ------------------------------------------------------------- an answer

def stand_in_for(path, stand_in, text):
    """
    `text` with the folder `path` written as `stand_in`. On Windows the
    program prints what lies below that folder with a backslash -- two, where
    it quotes a path as Python would -- and the record has `/`, so the
    separators of the names that follow the stand-in are turned into `/`:
    those, and no other backslash in the text.
    """
    if os.sep == "/":
        return text.replace(path, stand_in)
    name = r"""[^\\/\s,:;"'*?<>|]+"""
    for sep in ("\\", "\\\\"):                  # as written, and as quoted
        text = re.sub(re.escape(path.replace("\\", sep))
                      + "((?:" + re.escape(sep) + name + ")*)",
                      lambda m: stand_in + m.group(1).replace(sep, "/"), text)
    return text


def os_wording(text):
    """
    What Windows says where the record has Linux's words, said Linux's way.
    Only the operating system's own text: opening a folder as a file is
    "Permission denied" on Windows (and only for a path that is a folder
    here, so a file refused for real stays "Permission denied"), and a
    folder made below a file is "Cannot create a file when that file already
    exists" where Linux says "Not a directory".
    """
    if os.name != "nt":
        return text

    def opened(m):
        path = m.group(1).replace("\\\\", "\\")
        if os.path.isdir(path):
            return "[Errno 21] Is a directory: '%s'" % m.group(1)
        return m.group(0)
    text = re.sub(r"\[Errno 13\] Permission denied: '((?:[^'\\]|\\\\)+)'", opened, text)
    return text.replace("Cannot create a file when that file already exists.", "Not a directory")


def answer(status, stdout, stderr, out, places=()):
    """
    What a run came to, as text: {name: str or bytes}. `places` are
    (path, stand-in) pairs taken out of everything printed and written, so
    that where a check built its world is not part of the answer.
    """
    places = sorted(((p, s) for p, s in places if p), key=lambda ps: -len(ps[0]))

    def clean(text):
        text = os_wording(text)
        for path, stand_in in places:
            text = stand_in_for(path, stand_in, text)
        return CORES.sub(r"\1N\2", text)

    got = {"status.txt": "%d\n" % status, "stdout.txt": clean(stdout),
           "stderr.txt": clean(stderr)}
    written = []
    if os.path.isdir(out):
        for name in sorted(os.listdir(out)):
            path = os.path.join(out, name)
            if name == "report.stamp" or not os.path.isfile(path):
                continue
            written.append(name)
            if name == "report.data.gz":
                continue                    # read with the page
            if name == "report.html":
                payload, states, shell = page(out)
                got["report.payload.json"] = clean(indented(payload))
                got["report.states.json"] = clean(indented(states))
                got["report.page.diff"] = clean(shell_diff(shell))
                continue
            with open(path, "rb") as fh:
                data = fh.read()
            try:
                got[name] = clean(data.decode("utf-8"))
            except UnicodeDecodeError:
                got[name] = data
    got["written.txt"] = "".join(n + "\n" for n in written)
    return got


def run(argv, cwd, env, out, places=(), timeout=900):
    """Run the analyzer with `argv` and take its answer."""
    done = kit.analyze(*argv, env=env, cwd=cwd, timeout=timeout)
    return answer(done.returncode, done.stdout, done.stderr, out,
                  [(out, "OUT")] + list(places))


# ------------------------------------------------------------- the record

def slug(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_-")


def folder(root, check, case):
    return os.path.join(root, check, slug(case))


def save(root, check, case, got):
    """Write `got` as the expected answer, over whatever was there."""
    where = folder(root, check, case)
    shutil.rmtree(where, ignore_errors=True)
    os.makedirs(where)
    for name, value in got.items():
        data = value.encode("utf-8") if isinstance(value, str) else value
        if len(data) > BIG:
            with gzip.open(os.path.join(where, name + ".gz"), "wb", compresslevel=6) as fh:
                fh.write(data)
        else:
            with open(os.path.join(where, name), "wb") as fh:
                fh.write(data)


def load(root, check, case):
    """The expected answer, or None if none was recorded."""
    where = folder(root, check, case)
    if not os.path.isdir(where):
        return None
    got = {}
    for name in sorted(os.listdir(where)):
        path = os.path.join(where, name)
        if name.endswith(".gz"):
            with gzip.open(path, "rb") as fh:
                data = fh.read()
            name = name[:-3]
        else:
            with open(path, "rb") as fh:
                data = fh.read()
        try:
            got[name] = data.decode("utf-8")
        except UnicodeDecodeError:
            got[name] = data
    return got


def prune(root, check, cases):
    """Remove the record of any case of `check` that is no longer asked."""
    top = os.path.join(root, check)
    if not os.path.isdir(top):
        return []
    keep = {slug(c) for c in cases}
    gone = [n for n in sorted(os.listdir(top))
            if n not in keep and os.path.isdir(os.path.join(top, n))]
    for name in gone:
        shutil.rmtree(os.path.join(top, name))
    return gone


def text_difference(name, want, got, context=3, most=40):
    """A unified difference between two texts, shortened to what differs."""
    a, b = want.splitlines(), got.splitlines()
    # Only the stretch between the common head and tail is diffed, so a
    # payload of a million lines with one wrong number is quick to show.
    head = 0
    while head < min(len(a), len(b)) and a[head] == b[head]:
        head += 1
    tail = 0
    while (tail < min(len(a), len(b)) - head
           and a[len(a) - 1 - tail] == b[len(b) - 1 - tail]):
        tail += 1
    lo = max(0, head - context)
    mid_a, mid_b = a[lo:len(a) - tail + context], b[lo:len(b) - tail + context]
    if len(mid_a) + len(mid_b) > 4000:
        mid_a, mid_b = mid_a[:most], mid_b[:most]
    lines = list(difflib.unified_diff(mid_a, mid_b, "expected " + name, "got " + name,
                                      lineterm="", n=context))
    lines = [l if not l.startswith("@@") else "@@ from line %d @@" % (lo + 1)
             for l in lines]
    if not lines and want != got:
        lines = ["%s: the same lines, different line ends or final newline" % name]
    if len(lines) > most:
        lines = lines[:most] + ["... %d more lines of difference" % (len(lines) - most)]
    return "\n".join(l[:300] for l in lines)


def without(want, got, ignore):
    """`want` and `got` with each ignored payload key taken out of both.
    A key is a dotted path into the payload, `[]` meaning every element of
    a list: `payload.wars[].side_losses`."""
    name = "report.payload.json"
    paths = [k.split(".")[1:] for k in ignore if k.startswith("payload.")]
    if not paths or name not in want or name not in got:
        return want, got

    def drop(node, path):
        if not path:
            return
        key, rest = path[0], path[1:]
        many = key.endswith("[]")
        key = key[:-2] if many else key
        if not isinstance(node, dict) or key not in node:
            return
        if not rest:
            del node[key]
        elif many:
            for item in node[key]:
                drop(item, rest)
        else:
            drop(node[key], rest)

    def cut(text):
        data = json.loads(text)
        for path in paths:
            drop(data, path)
        return json.dumps(data, indent=1, ensure_ascii=False) + "\n"

    return dict(want, **{name: cut(want[name])}), dict(got, **{name: cut(got[name])})


def differences(want, got, ignore=()):
    """[a readable difference] between an expected answer and a run's,
    leaving out the payload keys in `ignore` (see `without`)."""
    want, got = without(want, got, ignore)
    out = []
    for name in sorted(set(want) | set(got)):
        if name not in got:
            out.append("%s was expected and not written" % name)
        elif name not in want:
            out.append("%s was written and not expected" % name)
        elif want[name] != got[name]:
            a, b = want[name], got[name]
            if isinstance(a, bytes) or isinstance(b, bytes):
                if isinstance(a, str):
                    a = a.encode("utf-8")
                if isinstance(b, str):
                    b = b.encode("utf-8")
                j = next((j for j, (p, q) in enumerate(zip(a, b)) if p != q), min(len(a), len(b)))
                out.append("%s differs at byte %d: expected %r, got %r"
                           % (name, j, a[max(0, j - 40):j + 40], b[max(0, j - 40):j + 40]))
            else:
                out.append(text_difference(name, a, b))
    return out


class Book:
    """
    The record of one check's cases in one place, and what was found
    comparing against it. `update` writes each answer as the new record
    instead of comparing.
    """

    def __init__(self, root, check, update=False, ignore=()):
        self.root, self.check, self.update, self.ignore = root, check, update, ignore
        self.asked, self.wrong, self.missing = [], [], []

    def hold(self, case, got):
        """[what differs] for one case (empty when it holds or is recorded)."""
        self.asked.append(case)
        if self.update:
            save(self.root, self.check, case, got)
            return []
        want = load(self.root, self.check, case)
        if want is None:
            self.missing.append(case)
            return ["no answer is recorded for this case (run with --update)"]
        found = differences(want, got, self.ignore)
        if found:
            self.wrong.append(case)
        return found

    def finish(self):
        """Drop the records of cases no longer asked, when updating."""
        if self.update:
            return prune(self.root, self.check, self.asked)
        return []


def report(case, found, width=0):
    """Print one case's outcome, and its differences in full."""
    print("  %-*s %s" % (width, case, "ok" if not found else "DIFFERS"))
    for f in found:
        print("      " + f.replace("\n", "\n      "))


def hold_cases(root, check, cases, update, ignore=()):
    """
    Hold each of `cases` -- (name, a function that runs it and returns its
    answer) -- to its record under `root/check`, or record it when
    `update`. Prints each case's outcome; 0 if all held, 1 if not.
    """
    book = Book(root, check, update, ignore)
    width = max((len(name) for name, _run in cases), default=0)
    bad = 0
    for name, run in cases:
        found = book.hold(name, run())
        bad += bool(found)
        report(name, found, width)
    gone = book.finish()
    if gone:
        print("dropped the record of %d cases no longer asked: %s" % (len(gone), gone))
    print()
    if update:
        print("recorded %d" % len(cases))
        return 0
    if bad:
        print("%d of %d differ from the recorded answers" % (bad, len(cases)))
        return 1
    return 0

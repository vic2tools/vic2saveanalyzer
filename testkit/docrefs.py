#!/usr/bin/env python3
"""
Every file the docs name has to exist.

A reader -- or an assistant reading for them -- takes a doc at its word:
a doc that sends them to `stamp.py` when there is no such file costs them
the search and their trust in the rest. This reads every Markdown file at
the top of the repository, every README.md below it and the pages in
docs/how-it-works/, finds the repository paths they name (in backticks, or
as a link), and fails on each one that is not there, with the doc and line.

    python3 testkit/docrefs.py

What counts as a path to check:
- one with a `/` ending in .py .rs .md .js .css .toml or .sh, relative to
  the repository or to the doc's own folder;
- a folder (ending in `/`) under one of the repository's own top folders;
- a bare file name with one of those endings, which has to exist somewhere
  in the repository.
Anything with `~`, `$`, `<`, `*`, a drive or a scheme, or an all-capitals
placeholder (`testkit/NAME.py`), is an example, not a path. docs/superpowers/
is the record of the cleanup that made these docs, and is not read.
"""
import os
import re
import subprocess
import sys

import kit

ENDINGS = (".py", ".rs", ".md", ".js", ".css", ".toml", ".sh")
CODE = re.compile(r"`([^`\s]+)`")
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def tracked():
    """The repository's files as they are on disk: committed or new, bar what
    .gitignore leaves out, and not ones deleted but not yet committed."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=kit.ROOT, capture_output=True, text=True).stdout.split("\n")
    return [p for p in out if p and os.path.isfile(os.path.join(kit.ROOT, p))]


def docs(files):
    out = [p for p in files if p.endswith(".md") and "/" not in p]
    out += [p for p in files if p.endswith("/README.md") and not p.startswith("docs/superpowers/")]
    out += [p for p in files if p.startswith("docs/how-it-works/") and p.endswith(".md")]
    return sorted(set(out))


def is_example(word):
    return (any(c in word for c in "~$<>*{}") or re.match(r"^[A-Za-z]:", word)
            or "://" in word or word.startswith("/")
            or any(part.isupper() and len(part) > 1 for part in re.split(r"[/.]", word)))


def wanted(word, tops):
    """Whether `word` names a repository path this check holds to existing."""
    word = re.sub(r":\d+(-\d+)?$", "", word)
    if is_example(word):
        return None
    if word.endswith("/"):
        return word if word.split("/")[0] in tops else None
    if word.endswith(ENDINGS):
        return word
    return None


def missing(doc, word, files, names):
    """True when `word`, named in `doc`, is not in the repository."""
    if "/" not in word.rstrip("/"):
        if word.endswith("/"):
            return not os.path.isdir(os.path.join(kit.ROOT, word))
        return word not in names
    here = os.path.dirname(doc)
    for base in ("", here):
        path = os.path.normpath(os.path.join(base, word)).replace(os.sep, "/")
        if path in files or os.path.isdir(os.path.join(kit.ROOT, path)):
            return False
    return True


def main():
    files = set(tracked())
    names = {p.rsplit("/", 1)[-1] for p in files}
    tops = {p.split("/")[0] for p in files}
    wrong = []
    read = docs(files)
    for doc in read:
        with open(os.path.join(kit.ROOT, doc), encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                for word in CODE.findall(line) + LINK.findall(line):
                    path = wanted(word, tops)
                    if path and missing(doc, path, files, names):
                        wrong.append("%s:%d  %s" % (doc, n, path))
    for w in wrong:
        print("  no such file: " + w)
    print("%d docs read, %d paths named that are not there" % (len(read), len(wrong)))
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())

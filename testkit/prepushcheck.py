#!/usr/bin/env python3
"""
The privacy guard, `tools/prepush.sh`, on a repository made up here: it
finds a private word committed, says `clean` when there is none, and
refuses -- never saying `clean` -- when it has no words to look for.

    python3 testkit/prepushcheck.py
"""
import os
import shutil
import subprocess
import sys

import kit

GUARD = os.path.join(kit.ROOT, "tools", "prepush.sh")


def git(where, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=where, check=True, capture_output=True)


def guard(where, private):
    env = {k: v for k, v in os.environ.items() if k != "VIC2_PRIVATE"}
    if private:
        env["VIC2_PRIVATE"] = private
    done = subprocess.run(["bash", os.path.join(where, "tools", "prepush.sh")], cwd=where,
                          capture_output=True, text=True, env=env)
    return done.returncode, done.stdout + done.stderr


def main():
    if not shutil.which("bash"):
        kit.skip("needs bash")
    if not os.path.isfile(GUARD):
        print("no guard at tools/prepush.sh")
        return 1
    wrong = []
    with kit.holding("vic2guard") as (holding, _env):
        repo = os.path.join(holding, "repo")
        os.makedirs(os.path.join(repo, "tools"))
        shutil.copy(GUARD, os.path.join(repo, "tools", "prepush.sh"))
        git(repo, "init", "-q")
        with open(os.path.join(repo, "notes.txt"), "w") as fh:
            fh.write("written by zzsecretzz\n")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "one")

        code, said = guard(repo, "zzsecretzz")
        if code != 1 or "notes.txt" not in said:
            wrong.append("a private word committed: exit %s, said %r" % (code, said[-300:]))
        code, said = guard(repo, "nowhereword")
        if code != 0 or "clean" not in said:
            wrong.append("nothing private: exit %s, said %r" % (code, said[-300:]))
        code, said = guard(repo, "")
        if code != 2 or "clean" in said:
            wrong.append("no words to look for: exit %s, said %r" % (code, said[-300:]))
    for w in wrong:
        print("WRONG: " + w)
    print("the guard finds a private word, says clean when there is none, and refuses "
          "with nothing to look for" if not wrong else "")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Every source file must be able to make the report stale.

A finished run writes a stamp beside the report, and a later run that
matches it skips everything and says "Nothing has changed since this was
built." That is the difference between pressing Analyze and waiting, and
pressing Analyze and reading -- and it is also the most dangerous switch
in the program, because when it is wrong nothing looks wrong. The report
opens, every number in it is plausible, and every number in it is from
the last time somebody looked.

It has been wrong. The stamp used to hash a hand-written list of five
filenames. `modrules.py`, which decides every nation's mobilisation size,
was lifted out of `mod_reader.py` -- which was on that list -- and did not
inherit its place. Doubling every rate in it then changed nothing the
stamp could see, and the next run served the old report. Nothing in the
suite could catch that, because the suite tested that the skip *happens*
and never what it is keyed on.

So this checks the property rather than the list: touch any source file
the program has, and the stamp must move.

    python3 testkit/staleness.py

The touching happens to a **copy** of the program in a temp folder, never
to the real tree, so a failure here cannot leave the working copy edited.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Run inside the copy, so `report_stamp` hashes the copy's own folder.
INSIDE = r'''
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vic2_analyzer as va


class Settings:
    """Whatever `report_stamp` asks for, answered with a default."""
    def __getattr__(self, name):
        return None


here = os.path.dirname(os.path.abspath(__file__))
saves = [os.path.join(here, "a.v2")]
with open(saves[0], "w") as fh:
    fh.write("date=\"1836.1.1\"\n")

args = Settings()
first = va.report_stamp(saves, args, "no-mod")
if not first:
    print("BLANK|the stamp came back empty, so nothing below means anything")
    raise SystemExit(0)

for name in sorted(os.listdir(here)):
    if not name.endswith(".py"):
        continue
    path = os.path.join(here, name)
    was = open(path, "rb").read()
    try:
        with open(path, "ab") as fh:
            fh.write(b"\n# touched\n")
        now = va.report_stamp(saves, args, "no-mod")
    finally:
        with open(path, "wb") as fh:
            fh.write(was)
    print("%s|%s" % ("MOVED" if now != first else "SAME", name))

# And the other direction: nothing touched, nothing moved.
print("%s|%s" % ("MOVED" if va.report_stamp(saves, args, "no-mod") != first
                 else "SAME", "(nothing touched)"))
'''


def main():
    holding = tempfile.mkdtemp(prefix="vic2stale")
    copy = os.path.join(holding, "program")
    os.makedirs(copy)
    try:
        for name in os.listdir(HERE):
            if name.endswith(".py"):
                shutil.copy2(os.path.join(HERE, name),
                             os.path.join(copy, name))
        driver = os.path.join(copy, "_stale_driver.py")
        with open(driver, "w") as fh:
            fh.write(INSIDE)
        # The driver is itself a .py in the folder, so it is one of the
        # files under test, which is fine and one more than we need.
        done = subprocess.run([sys.executable, driver], capture_output=True,
                              text=True, cwd=copy)
        if done.returncode:
            print("the stamp could not be taken at all:")
            print((done.stdout + done.stderr).strip()[-1500:])
            return 1

        deaf = []
        counted = 0
        for line in done.stdout.strip().splitlines():
            if "|" not in line:
                continue
            verdict, name = line.split("|", 1)
            if verdict == "BLANK":
                print("  %s" % name)
                return 1
            if name == "(nothing touched)":
                if verdict == "MOVED":
                    deaf.append("the stamp moved when nothing was touched, "
                                "so it can never skip anything")
                continue
            counted += 1
            if verdict == "SAME":
                deaf.append("editing %s does not change the stamp, so a run "
                            "after that edit serves the old report" % name)

        print("  %d source files, each touched in a copy of the program"
              % counted)
        print("  %-46s %s" % ("every one of them moves the stamp",
                              "FAILED" if deaf else "ok"))
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    print()
    if deaf:
        print("PROBLEMS:")
        for one in deaf:
            print("  %s" % one)
        return 1
    print("nothing the program is made of can change behind the stamp's back")
    return 0


if __name__ == "__main__":
    sys.exit(main())

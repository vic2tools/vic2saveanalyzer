#!/usr/bin/env python3
"""
The report page is built from the files `scanner/src/page/order.txt` names,
in that order, and from nothing else.

`scanner/build.rs` joins them into the page the scanner carries. This runs
that build script on a copy of `scanner/` and holds it to three things:

- the page it builds is the page `expected.template()` reads, which the
  recorded answers' page differences are taken against;
- a file in `src/page/` that `order.txt` does not name stops the build, by
  name: a page file nothing includes is a change that silently is not there;
- a file `order.txt` names twice stops the build, by name;
- a file without a last newline, or with a byte-order mark or a carriage
  return, stops the build, by name.

    python3 testkit/pagebuild.py
"""
import os
import shutil
import sys

import kit
import expected


def a_copy(holding):
    copy = os.path.join(holding, "scanner")
    shutil.copytree(os.path.join(kit.ROOT, "scanner"), copy,
                    ignore=shutil.ignore_patterns("target"))
    return copy


def main():
    if not kit.rustc():
        kit.skip("needs rustc")
    wrong = []
    with kit.holding("vic2page") as (holding, _env):
        copy = a_copy(holding)
        page = os.path.join(copy, "src", "page")
        if not os.path.isfile(os.path.join(page, "order.txt")):
            print("no scanner/src/page/order.txt")
            return 1
        run = kit.build_script(copy, os.path.join(holding, "work"))

        status, said, out = run()
        built = os.path.join(out, "template.html")
        if status or not os.path.isfile(built):
            wrong.append("the build script failed: %s" % said[-500:])
        else:
            with open(built, encoding="utf-8", newline="") as fh:
                if fh.read() != expected.template():
                    wrong.append("the page built differs from expected.template()")

        stray = os.path.join(page, "js", "stray.js")
        with open(stray, "w") as fh:
            fh.write("// nobody includes this\n")
        status, said, _out = run()
        if status == 0 or "stray.js" not in said:
            wrong.append("a page file order.txt does not name was built past: %s" % said[-300:])
        os.remove(stray)

        order = os.path.join(page, "order.txt")
        with open(order, encoding="utf-8") as fh:
            kept = fh.read()
        first = next(l for l in kept.splitlines() if l.strip() and not l.strip().startswith("#"))
        with open(order, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(kept + first + "\n")
        status, said, _out = run()
        if status == 0 or first not in said:
            wrong.append("a page file named twice was built past: %s" % said[-300:])
        with open(order, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(kept)

        # Files are joined as they are, so a missing last newline would run one
        # file's last line into the next file's first, and a BOM or a CR would
        # land in the middle of the page.
        boot = os.path.join(page, "js", "boot.js")
        with open(boot, "rb") as fh:
            body = fh.read()
        for what, bad in (("no last newline", body.rstrip(b"\n")),
                          ("a byte-order mark", b"\xef\xbb\xbf" + body),
                          ("a carriage return", body.replace(b"\n", b"\r\n"))):
            with open(boot, "wb") as fh:
                fh.write(bad)
            status, said, _out = run()
            if status == 0 or "boot.js" not in said:
                wrong.append("a page file with %s was built past: %s" % (what, said[-300:]))
        with open(boot, "wb") as fh:
            fh.write(body)

    for w in wrong:
        print("WRONG: " + w)
    if not wrong:
        print("the page is built from order.txt's files, in order, and from nothing else")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())

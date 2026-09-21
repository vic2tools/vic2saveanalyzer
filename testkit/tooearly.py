#!/usr/bin/env python3
"""
Find locals that are read above the line that first assigns them.

`main` is two thousand lines and mostly straight-line, and twice now a name
has been read in a branch that runs before the loop which builds it --
`parsed`, both times, in code only the mod path reaches. Python raises
`UnboundLocalError` at runtime and only on that path, so the tests passed and
the program crashed.

Nothing general can decide this: a name assigned in a loop is legitimately
read below it on the next turn, and a name assigned in both arms of an `if`
is fine after it. What is nearly always wrong is a *read* whose line number
is smaller than every *binding* of that name in the same function, because a
reader going down the page meets the use before anything has put a value
there. That is the shape of both bugs and it is cheap to look for.

    python3 testkit/tooearly.py [files...]

Says nothing and exits 0 when there is nothing above its own definition.
"""

import ast
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bindings_and_loads(fn):
    """({name: first line bound}, [(name, line)] read), for one function."""
    bound, loads = {}, []
    # Comprehensions and nested functions have their own scopes: a name bound
    # inside one is not bound out here, and a name read inside one may well
    # run later than the page suggests. Both are skipped whole.
    inner = set()
    for node in ast.walk(fn):
        if node is not fn and isinstance(node, (ast.FunctionDef,
                                                ast.AsyncFunctionDef,
                                                ast.Lambda, ast.ListComp,
                                                ast.SetComp, ast.DictComp,
                                                ast.GeneratorExp)):
            inner.update(id(n) for n in ast.walk(node))

    for node in ast.walk(fn):
        if id(node) in inner:
            continue
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                if node.id not in bound or node.lineno < bound[node.id]:
                    bound[node.id] = node.lineno
            elif isinstance(node.ctx, ast.Load):
                loads.append((node.id, node.lineno))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = (alias.asname or alias.name).split(".")[0]
                if name not in bound or node.lineno < bound[name]:
                    bound[name] = node.lineno
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.setdefault(node.name, node.lineno)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            for name in node.names:
                bound[name] = -1          # not a local at all
    return bound, loads


def loops_over(fn):
    """Line spans of every loop, where reading above the binding is normal."""
    spans = []
    for node in ast.walk(fn):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            spans.append((node.lineno, max(
                (n.lineno for n in ast.walk(node) if hasattr(n, "lineno")),
                default=node.lineno)))
    return spans


def check(path):
    """[(function, name, read at, bound at)] for one file."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
    except SyntaxError as exc:
        return [("<file>", str(exc), 0, 0)]
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = fn.args
        given = {a.arg for a in (args.posonlyargs + args.args
                                 + args.kwonlyargs)}
        for a in (args.vararg, args.kwarg):
            if a:
                given.add(a.arg)
        bound, loads = bindings_and_loads(fn)
        spans = loops_over(fn)
        for name, line in loads:
            if name in given or name not in bound or bound[name] < 0:
                continue
            if line >= bound[name]:
                continue
            # Inside a loop that also contains the binding: the second turn
            # round has a value, which is the whole point of the loop.
            if any(lo <= line <= hi and lo <= bound[name] <= hi
                   for lo, hi in spans):
                continue
            bad.append((fn.name, name, line, bound[name]))
    return bad


def main():
    files = sys.argv[1:] or [
        os.path.join(HERE, f) for f in sorted(os.listdir(HERE))
        if f.endswith(".py")]
    found = 0
    for path in files:
        for fn, name, line, at in check(path):
            found += 1
            print("%s:%d  %s() reads `%s` before line %d, which binds it"
                  % (os.path.relpath(path, HERE), line, fn, name, at))
    if found:
        print("\n%d name(s) read above their own definition. Each one is an "
              "UnboundLocalError\non whatever path reaches it first." % found)
        return 1
    print("no name is read above the line that defines it")
    return 0


if __name__ == "__main__":
    sys.exit(main())

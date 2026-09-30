"""Hold pyfmt.rs to Python: repr, round(x, n), //, json.dumps of strings,
float() of text, on random and awkward values.

    python3 fmtcheck.py BINARY [COUNT]
"""
import json, math, random, struct, subprocess, sys

from pathlib import Path
from outcome import SKIPPED

binary = sys.argv[1]
if not Path(binary).is_file():
    print("needs a built Rust scanner")
    sys.exit(SKIPPED)
count = int(sys.argv[2]) if len(sys.argv) > 2 else 200000
rnd = random.Random(20260929)

def h(x):
    return "%016x" % struct.unpack("<Q", struct.pack("<d", x))[0]

def randfloat():
    k = rnd.random()
    if k < 0.25:
        return struct.unpack("<d", struct.pack("<Q", rnd.getrandbits(64)))[0]
    if k < 0.5:
        return rnd.uniform(-1e9, 1e9)
    if k < 0.7:
        # values of the kind the analyzer rounds: ratios, percentages
        a = rnd.randint(0, 10**9); b = rnd.randint(1, 10**9)
        return a / b * rnd.choice([1, 100, 1000, 0.001])
    if k < 0.85:
        # decimals that sit on or near a rounding half
        n = rnd.randint(0, 7)
        return round(rnd.randint(-10**8, 10**8) / 10**n + rnd.choice([0, 0.5, 5e-6, 5e-5, 5e-4]) , 9)
    return rnd.choice([0.0, -0.0, 1e16, 1e15, 1e-4, 1e-5, 0.1, 0.5, 2.5, 1.5,
                       123456789012345678.0, 5e-324, 1.7976931348623157e308,
                       0.125, 0.375, 2.675, 1e22, 1e-7, 99999999999999999.0])

lines, want = [], []
for _ in range(count):
    x = randfloat()
    if math.isnan(x) or math.isinf(x):
        continue
    lines.append("f " + h(x)); want.append(repr(x))
    n = rnd.randint(0, 7)
    try:
        r = round(x, n)
        lines.append("r %s %d" % (h(x), n)); want.append(repr(r))
    except OverflowError:
        pass
    y = randfloat()
    if y != 0 and not math.isinf(x / y if y else 0):
        try:
            d = x // y
            lines.append("d %s %s" % (h(x), h(y))); want.append(repr(d))
        except (OverflowError, ZeroDivisionError):
            pass
# floor division of the shapes the brigade rules use
for _ in range(count // 4):
    size = rnd.randint(0, 5_000_000); rate = rnd.choice([0.02, 0.05, 0.07, 0.08, 0.1, 0.125, 1.0, rnd.random()])
    step = rnd.choice([3000, 1000, 2000, 3000 * 3.0, 3000 * 5.0, 3000 * 8.0, 1500.5])
    x = size * rate
    lines.append("d %s %s" % (h(x), h(float(step)))); want.append(repr(x // step))
# sum() as CPython 3.12+ adds floats
for _ in range(count // 10):
    n = rnd.randint(0, 20)
    xs = [randfloat() for _ in range(n)]
    xs = [x for x in xs if not (math.isnan(x) or math.isinf(x))]
    if rnd.random() < 0.5:
        xs = [round(x % 1000, rnd.randint(0, 3)) for x in xs]
    try:
        total = sum(xs)
    except OverflowError:
        continue
    lines.append("s " + " ".join(h(x) for x in xs)); want.append(repr(total) if xs else "0")
# json strings
alphabet = [chr(c) for c in range(0, 0x250)] + ["–", "€", "�", "\U0001F600", "<", ">", '"', "\\"]
for _ in range(count // 10):
    s = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 12)))
    lines.append("j " + s.encode("utf-8").hex()); want.append(json.dumps(s))
# a save's numbers as the scanner reads them (`text::to_float_b`, whose
# fast path divides the digits by a power of ten): every spelling a save
# writes, and the ones near it
for _ in range(count // 5):
    whole = str(rnd.randint(0, 10 ** rnd.randint(0, 12)))
    frac = "".join(rnd.choice("0123456789") for _ in range(rnd.randint(0, 9)))
    text = whole + ("." + frac if rnd.random() < 0.8 else "")
    if rnd.random() < 0.2:
        text = "-" + text
    if rnd.random() < 0.05:
        text = "." + frac if frac else text
    lines.append("b " + text); want.append(repr(float(text)))
# float() of text
texts = ["1", "1.5", " 2.5 ", "\xa03\x1c", "-0", "+7.", ".5", "1e5", "1E-2", "inf", "-Infinity",
         "nan", "abc", "", "1.2.3", "1e", "--1", "0x10", "1_000", "12345.000", "\x853\x85"]
for t in texts:
    if "_" in t:
        continue
    lines.append("p " + t)
    try:
        want.append(repr(float(t)))
    except ValueError:
        want.append("E")

p = subprocess.run([binary, "selftest-fmt"], input="\n".join(lines) + "\n",
                   capture_output=True, text=True)
if p.returncode:
    raise RuntimeError(p.stderr)
got = p.stdout.splitlines()
if len(got) != len(want):
    raise RuntimeError("engine returned %d of %d answers" % (len(got), len(want)))
bad = 0
for line, w, g in zip(lines, want, got):
    if w != g:
        bad += 1
        if bad <= 20:
            print("DIFF", line[:80], "python", w, "rust", g)
print("%d checks, %d differ" % (len(want), bad))
sys.exit(1 if bad else 0)

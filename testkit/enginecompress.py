"""Hold deflate.rs to zlib: every stream it makes decompresses to its input.

    python3 deflatecheck.py BINARY [files...]
"""
import base64, gzip, os, random, subprocess, sys, tempfile, time, zlib
import shutil

from pathlib import Path
from outcome import SKIPPED

binary = sys.argv[1]
if not Path(binary).is_file():
    print("needs a built Rust scanner")
    sys.exit(SKIPPED)
rnd = random.Random(7)
cases = {
    "empty": b"", "one": b"a", "two": b"ab", "three": b"abc",
    "zeros": bytes(300000), "ones": b"\xff" * 70000,
    "random": bytes(rnd.getrandbits(8) for _ in range(200000)),
    "text": ("".join(rnd.choice("abcdefghij ,.:{}[]\"0123456789") for _ in range(500000))).encode(),
    "repeats": (b"the quick brown fox jumps over the lazy dog " * 5000),
    "stored-ish": bytes(rnd.getrandbits(8) for _ in range(70000)) + b"x" * 10,
    "biglen": b"ab" * 200000 + b"xyz" * 100000,
}
# Skewed alphabets that push code lengths past the limits.
fib = [1, 1]
while len(fib) < 30:
    fib.append(fib[-1] + fib[-2])
skew = b"".join(bytes([i]) * min(f, 5000) for i, f in enumerate(fib))
cases["skewed"] = bytes(rnd.sample(list(skew), len(skew)))
for path in sys.argv[2:]:
    cases[os.path.basename(path)] = open(path, "rb").read()

bad = 0
tmp = tempfile.mkdtemp(prefix="vic2compress")
for name, data in cases.items():
    path = os.path.join(tmp, "in")
    open(path, "wb").write(data)
    for mode in ("gzip", "gz4", "gz5", "zlib", "pgzip", "b64"):
        t = time.perf_counter()
        out = subprocess.run([binary, "selftest-deflate", mode, path], capture_output=True, check=True).stdout
        took = time.perf_counter() - t
        try:
            back = (gzip.decompress(out) if mode not in ("zlib", "b64") else
                    zlib.decompress(out) if mode == "zlib" else base64.b64decode(out))
            ok = back == data
            if mode == "b64":
                ok = ok and out == base64.b64encode(data)
        except Exception as exc:
            ok = False
            back = repr(exc)
        if not ok:
            bad += 1
            print("FAIL", name, mode, len(data), str(back)[:100])
        elif mode != "b64" and len(data) > 100000:
            py = len(gzip.compress(data, 6))
            print("ok   %-22s %-5s %9d -> %9d (python %9d, %+.2f%%) %.3f s" % (
                name, mode, len(data), len(out), py, 100 * (len(out) - py) / py, took))
print("failures:", bad)

shutil.rmtree(tmp)
sys.exit(1 if bad else 0)

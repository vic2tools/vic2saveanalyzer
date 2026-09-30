"""Compare py.jsonl (pydump.py) with rust.jsonl (vic2scan report --dump):
text-exact where the tables are concerned, value-exact for the rest.

    python3 dumpcheck.py FOLDER
"""
import base64, gzip, json, os, sys

folder = sys.argv[1]
py = open(os.path.join(folder, "py.jsonl")).read().split("\n")
rs = open(os.path.join(folder, "rust.jsonl")).read().split("\n")
py = [l for l in py if l]
rs = [l for l in rs if l]
print("lines:", len(py), len(rs))
bad = int(len(py) != len(rs))
if bad:
    print("intermediate row counts differ")

def note(msg):
    global bad
    bad += 1
    if bad <= 30:
        print(msg)

hp, hr = json.loads(py[0]), json.loads(rs[0])
if hp != hr:
    note(f"settlement differs: {hp} vs {hr}")
for i, (a, b) in enumerate(zip(py[1:], rs[1:])):
    a, b = json.loads(a), json.loads(b)
    date = a["date"]
    if len(a["text"]) != len(b["text"]):
        note(f"{date}: table counts differ")
    for k, (x, y) in enumerate(zip(a["text"], b["text"])):
        if x != y:
            xl, yl = x.split("\r\n"), y.split("\r\n")
            first = next((j for j, (p, q) in enumerate(zip(xl, yl)) if p != q), min(len(xl), len(yl)))
            note(f"{date} text[{k}] line {first}:\n   py {xl[first] if first < len(xl) else None!r:.300}\n   rs {yl[first] if first < len(yl) else None!r:.300}")
    for key in ("tables", "naval", "supply", "nations"):
        xs = json.dumps(a[key], separators=(",", ":"))
        ys = json.dumps(b[key], separators=(",", ":"))
        if xs != ys:
            j = next((j for j, (p, q) in enumerate(zip(xs, ys)) if p != q), min(len(xs), len(ys)))
            note(f"{date} {key} differs at {j}:\n   py {xs[max(0, j - 120):j + 120]}\n   rs {ys[max(0, j - 120):j + 120]}")
    if json.dumps(a["meta"], separators=(",", ":")) != json.dumps(b["meta"], separators=(",", ":")):
        note(f"{date}: meta values, types or key order differ")
        for k in a["meta"]:
            if a["meta"][k] != b["meta"].get(k):
                note(f"{date} meta.{k} differs: {str(a['meta'][k])[:200]} / {str(b['meta'].get(k))[:200]}")
    ca = gzip.decompress(base64.b64decode(a["chunk"])).decode()
    cb = gzip.decompress(base64.b64decode(b["chunk"])).decode()
    if ca != cb:
        j = next((j for j, (p, q) in enumerate(zip(ca, cb)) if p != q), min(len(ca), len(cb)))
        note(f"{date} chunk differs at {j}:\n   py {ca[max(0, j - 100):j + 100]}\n   rs {cb[max(0, j - 100):j + 100]}")
print("differences:", bad)
sys.exit(1 if bad else 0)

"""Dump the Python intermediate oracle for engineintermediate.py: catch what every save came to on its
way into the walk, and dump it as the engine's `--dump` does; also write the
engine's spec and mod export for the same run.

    python3 testkit/engine_oracle.py SAVES MOD OUT [extra analyzer flags...]
"""
import base64, gzip, json, os, sys
START = os.getcwd()
TREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["VIC2_NO_ENGINE"] = "1"
sys.path.insert(0, TREE)
os.chdir(TREE)
import vic2_analyzer as va
import engine
import modexport
import spending

def main():
    saves, mod_path, out = sys.argv[1:4]
    out = os.path.abspath(os.path.join(START, out))
    extra = sys.argv[4:]
    os.makedirs(out, exist_ok=True)
    caught = {}
    items = []

    orig_walk = va.walk_campaign
    def walk(stream, spec, finished, pop_columns):
        def tap():
            for item in stream:
                items.append(item)
                yield item
        caught["spec"] = spec
        caught["pop_columns"] = pop_columns
        return orig_walk(tap(), spec, finished, pop_columns)
    va.walk_campaign = walk

    orig_stream = va.parse_saves_stream
    def stream(files, **options):
        caught["files"] = list(files)
        caught["reading"] = options["reading"]
        return orig_stream(files, **options)
    va.parse_saves_stream = stream

    sys.argv = ["vic2_analyzer.py", saves, "--out", os.path.join(out, "report"), "--mod-path",
                mod_path, "--rebuild", "--no-cache", "-q"] + extra
    args_holder = {}
    orig_from = va.Run.from_command_line
    def from_cl(ns):
        r = orig_from(ns)
        args_holder["args"] = r
        return r
    va.Run.from_command_line = staticmethod(from_cl)
    va.main()

    spec = caught["spec"]
    mod = spec.mod

    def market(m):
        if not m:
            return None
        return {"current": m["current"], "history": [list(h) for h in m["history"]],
                "snapshot": m["snapshot"]}

    with open(os.path.join(out, "py.jsonl"), "w") as fh:
        fh.write(json.dumps({"live": sorted(spec.live or ()), "index_base": mod.index_base},
                            separators=(",", ":")) + "\n")
        for meta, nations, wars, got in items:
            t = got.tables
            line = {
                "date": meta["date"],
                "text": [got.text[name] for name in spending.PER_SAVE],
                "tables": {"ships": t.ships, "crews": t.crews, "brigades": t.brigades,
                           "techs": t.techs, "pops": t.pops, "cultures": t.cultures},
                "naval": [[tag, profile] for tag, _key, profile in got.naval],
                "supply": [list(s) for s in got.supply],
                "meta": {"date": meta["date"], "player": meta["player"], "file": meta["file"],
                         "province_owner": {p: list(v) for p, v in meta["province_owner"].items()},
                         "great_nations": meta["great_nations"], "world_pop": meta["world_pop"],
                         "market": market(meta.get("market"))},
                "nations": nations,
                "chunk": meta.get("population_chunk"),
            }
            fh.write(json.dumps(line, separators=(",", ":")) + "\n")

    args = args_holder["args"]
    args = va.replace(args, pop_per_regiment=spec.pop_per_regiment, mob_types=tuple(sorted(spec.mob_types)))
    s = engine.spec(args, caught["files"], caught["reading"], spec, mod, caught["pop_columns"])
    s["mod_file"] = os.path.join(out, "mod.json")
    s["out"] = os.path.join(out, "rust_report")
    json.dump(s, open(os.path.join(out, "spec.json"), "w"), separators=(",", ":"))
    json.dump(modexport.export_mod(mod), open(os.path.join(out, "mod.json"), "w"), separators=(",", ":"))
    print("saves:", len(items))


if __name__ == "__main__":
    main()

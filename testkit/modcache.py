#!/usr/bin/env python3
"""Behavioral checks for mod cache reuse, invalidation and atomic replacement."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cacheio
import mod_reader
from matching import a_mod


class ModCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vic2modcache")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = patch.object(tempfile, "tempdir", str(self.root))
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.mod = Path(a_mod(str(self.root / "standalone")))

    def test_reuse_and_mutation_isolation(self):
        fresh = mod_reader.load_mod(str(self.mod))
        with patch.object(mod_reader, "_load_mod", side_effect=AssertionError("cache miss")):
            cached = mod_reader.load_mod(str(self.mod))
            self.assertEqual(fresh, cached)
            cached.decode_indices([])
            cached.defines["POP_SIZE_PER_REGIMENT"] = 99
            self.assertEqual(fresh, mod_reader.load_mod(str(self.mod)))

    def test_edits_additions_and_deletions_change_loaded_data(self):
        before = mod_reader.load_mod(str(self.mod))
        tech = self.mod / "technologies/army_tech.txt"
        tech.write_text(tech.read_text() + "\nnew_tech = { mobilisation_size = 0.125 }\n")
        after = mod_reader.load_mod(str(self.mod))
        self.assertEqual(after.tech_count, before.tech_count + 1)
        self.assertEqual(after.tech_mob["new_tech"], 0.125)
        added = self.mod / "inventions/extra.txt"
        added.write_text("new_invention = { mobilisation_size = 0.25 }\n")
        self.assertIn("new_invention",
                      mod_reader.load_mod(str(self.mod)).invention_rules)
        added.unlink()
        self.assertNotIn("new_invention",
                         mod_reader.load_mod(str(self.mod)).invention_rules)

    def test_inherited_data_and_local_override(self):
        game = self.root / "game"
        (game / "map").mkdir(parents=True)
        (game / "map/default.map").write_text("max_provinces = 40\n")
        (game / "common").mkdir()
        base_defines = game / "common/defines.lua"
        base_defines.write_text("POP_SIZE_PER_REGIMENT = 3000,\n")
        mod = Path(a_mod(str(game / "mod/partial")))
        first_stamp = mod_reader.mod_signature(str(mod))
        self.assertEqual(mod_reader.load_mod(str(mod)).defines["POP_SIZE_PER_REGIMENT"], 3000)
        base_defines.write_text("POP_SIZE_PER_REGIMENT = 2000,\n")
        self.assertNotEqual(first_stamp, mod_reader.mod_signature(str(mod)))
        self.assertEqual(mod_reader.load_mod(str(mod)).defines["POP_SIZE_PER_REGIMENT"], 2000)
        own = mod / "common/defines.lua"
        own.write_text("POP_SIZE_PER_REGIMENT = 1000,\n")
        self.assertEqual(mod_reader.load_mod(str(mod)).defines["POP_SIZE_PER_REGIMENT"], 1000)
        own.unlink()
        self.assertEqual(mod_reader.load_mod(str(mod)).defines["POP_SIZE_PER_REGIMENT"], 2000)
        stamp = mod_reader.mod_signature(str(mod))
        (game / "save games").mkdir()
        (game / "save games/autosave.v2").write_text("unrelated")
        self.assertEqual(stamp, mod_reader.mod_signature(str(mod)))

    def test_a_mod_file_named_in_other_case_replaces_the_games(self):
        # Windows, where the game runs, does not tell these two names apart,
        # so the mod's file replaces the game's there. Read as two files
        # the game's inventions joined the array and moved every index
        # after them.
        game = self.root / "game"
        (game / "map").mkdir(parents=True)
        (game / "map/default.map").write_text("max_provinces = 40\n")
        (game / "inventions").mkdir()
        (game / "inventions/army_inventions.txt").write_text(
            "base_one = { limit = { } }\nbase_two = { limit = { } }\n")
        (game / "inventions/commerce_inventions.txt").write_text(
            "base_kept = { limit = { } }\n")
        mod = game / "mod/cased"
        (mod / "inventions").mkdir(parents=True)
        (mod / "inventions/Army_Inventions.txt").write_text(
            "mod_one = { limit = { } }\n")
        names = [e["name"] for e in mod_reader.invention_sequence(str(mod))]
        self.assertEqual(names, ["mod_one", "base_kept"])

    def test_the_key_moves_with_exactly_the_code_that_reads_a_mod(self):
        # Not the key's list of files: every file of the program is edited
        # in turn, in a copy, and exactly what mod_reader reaches has to
        # move the key. Too few serves a mod read by old code; too many
        # throws the cached mod away for a reworded label somewhere else.
        # The list used to be written by hand, which is how the parse
        # cache's went wrong (REVIEW.md §9).
        from packing import reached
        wanted = reached("mod_reader")
        here = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="vic2modkey") as copy:
            for name in os.listdir(here):
                if name.endswith(".py"):
                    shutil.copy2(here / name, os.path.join(copy, name))
            probe = os.path.join(copy, "edit_each.py")
            with open(probe, "w") as fh:
                fh.write(EDIT_EACH)
            done = subprocess.run([sys.executable, probe], cwd=copy,
                                  capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = dict(line.split(" ", 1) for line in done.stdout.splitlines()
                    if " " in line)
        self.assertTrue(said.get("BEFORE"), "the mod key came back empty")
        moved = set(said.get("MOVED", "").split())
        self.assertIn("v2parse", wanted, "the walk no longer reaches the "
                      "parser a mod is read with; the walk is wrong")
        self.assertEqual(sorted(wanted - moved), [],
                         "these files decide what a cached mod holds, and "
                         "editing them does not move the mod cache key")
        self.assertEqual(sorted(moved - wanted), [],
                         "editing these moves the mod cache key although "
                         "reading a mod never reaches them")

    def test_corrupt_entry_is_rebuilt(self):
        expected = mod_reader.load_mod(str(self.mod))
        Path(mod_reader._mod_slot(str(self.mod))).write_bytes(b"broken cache")
        self.assertEqual(expected, mod_reader.load_mod(str(self.mod)))

    def test_failed_atomic_replace_preserves_previous_entry(self):
        slot = str(self.root / "atomic.pkl")
        cacheio.store(slot, {"generation": 1})
        with patch.object(cacheio.os, "replace", side_effect=OSError("busy")):
            cacheio.store(slot, {"generation": 2})
        self.assertEqual(cacheio.load(slot), {"generation": 1})
        self.assertEqual(list(self.root.glob("*.tmp")), [])


EDIT_EACH = r'''
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import mod_reader
before = mod_reader._reader_fingerprint()
moved = []
for name in sorted(os.listdir(here)):
    if not name.endswith(".py") or name == "edit_each.py":
        continue
    path = os.path.join(here, name)
    with open(path, "rb") as fh:
        was = fh.read()
    with open(path, "ab") as fh:
        fh.write(b"\n# edited\n")
    try:
        if mod_reader._reader_fingerprint() != before:
            moved.append(name[:-3])
    finally:
        with open(path, "wb") as fh:
            fh.write(was)
print("BEFORE", before)
print("MOVED", " ".join(moved))
'''


class BlockBoundaryTests(unittest.TestCase):
    def test_mod_blocks_ignore_quoted_braces(self):
        text = 'wanted = { title = "a } brace" inner = { n = 1 } } next = { x = 2 }'
        body = ' title = "a } brace" inner = { n = 1 } '
        self.assertEqual(mod_reader._block_text(text, "wanted"), body)
        self.assertEqual(mod_reader._named_blocks(text, "wanted"), [body])
        self.assertEqual(mod_reader._drop_block(text, "wanted"), ' next = { x = 2 }')

    def test_token_skip_leaves_the_next_token(self):
        tokens = mod_reader.Tokens('{ note = "{ literal" inner = { x = 1 } } next = 2')
        self.assertEqual(tokens.next(), "{")
        tokens.skip_to_close()
        self.assertEqual(tokens.next(), "next")
        self.assertIsNone(mod_reader.block_end('x = { n = 1', 5))


if __name__ == "__main__":
    unittest.main()

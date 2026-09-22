#!/usr/bin/env python3
"""Behavioral checks for mod cache reuse, invalidation and atomic replacement."""

from pathlib import Path
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
            cached["index_base"] = 1
            cached["defines"]["POP_SIZE_PER_REGIMENT"] = 99
            self.assertEqual(fresh, mod_reader.load_mod(str(self.mod)))

    def test_edits_additions_and_deletions_change_loaded_data(self):
        before = mod_reader.load_mod(str(self.mod))
        tech = self.mod / "technologies/army_tech.txt"
        tech.write_text(tech.read_text() + "\nnew_tech = { mobilisation_size = 0.125 }\n")
        after = mod_reader.load_mod(str(self.mod))
        self.assertEqual(after["tech_count"], before["tech_count"] + 1)
        self.assertEqual(after["tech_mob"]["new_tech"], 0.125)
        added = self.mod / "inventions/extra.txt"
        added.write_text("new_invention = { mobilisation_size = 0.25 }\n")
        self.assertIn("new_invention", mod_reader.load_mod(str(self.mod))["invention_rules"])
        added.unlink()
        self.assertNotIn("new_invention", mod_reader.load_mod(str(self.mod))["invention_rules"])

    def test_inherited_data_and_local_override(self):
        game = self.root / "game"
        (game / "map").mkdir(parents=True)
        (game / "map/default.map").write_text("max_provinces = 40\n")
        (game / "common").mkdir()
        base_defines = game / "common/defines.lua"
        base_defines.write_text("POP_SIZE_PER_REGIMENT = 3000,\n")
        mod = Path(a_mod(str(game / "mod/partial")))
        first_stamp = mod_reader.mod_signature(str(mod))
        self.assertEqual(mod_reader.load_mod(str(mod))["defines"]["POP_SIZE_PER_REGIMENT"], 3000)
        base_defines.write_text("POP_SIZE_PER_REGIMENT = 2000,\n")
        self.assertNotEqual(first_stamp, mod_reader.mod_signature(str(mod)))
        self.assertEqual(mod_reader.load_mod(str(mod))["defines"]["POP_SIZE_PER_REGIMENT"], 2000)
        own = mod / "common/defines.lua"
        own.write_text("POP_SIZE_PER_REGIMENT = 1000,\n")
        self.assertEqual(mod_reader.load_mod(str(mod))["defines"]["POP_SIZE_PER_REGIMENT"], 1000)
        own.unlink()
        self.assertEqual(mod_reader.load_mod(str(mod))["defines"]["POP_SIZE_PER_REGIMENT"], 2000)
        stamp = mod_reader.mod_signature(str(mod))
        (game / "save games").mkdir()
        (game / "save games/autosave.v2").write_text("unrelated")
        self.assertEqual(stamp, mod_reader.mod_signature(str(mod)))

    def test_parser_dependency_changes_expire_mod_cache(self):
        source = self.root / "parser.py"
        source.write_text("first version")
        with patch.object(mod_reader.v2parse, "__file__", str(source)):
            mod_reader.load_mod(str(self.mod))
            source.write_text("second version")
            with patch.object(mod_reader, "_load_mod", wraps=mod_reader._load_mod) as read:
                mod_reader.load_mod(str(self.mod))
                read.assert_called_once()

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

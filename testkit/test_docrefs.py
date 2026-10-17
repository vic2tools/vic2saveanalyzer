"""
What `docrefs.py` holds to existing, and what it leaves alone.

    python -m unittest discover -s testkit -p "test_*.py"
"""
import unittest

import docrefs

TOPS = {"testkit", "scanner", "docs", "speed", "README.md"}


class Wanted(unittest.TestCase):
    def test_capitalised_doc_names_are_checked(self):
        for word in ("README.md", "DEVELOPING.md", "INTERNALS.md", "testkit/README.md",
                     "docs/how-it-works/NOPE.md"):
            with self.subTest(word=word):
                self.assertEqual(docrefs.wanted(word, TOPS), word)

    def test_placeholders_are_examples(self):
        for word in ("testkit/NAME.py", "TREE/scanner/", "~/vic2-baseline", "$VIC2_SAVES/x.py"):
            with self.subTest(word=word):
                self.assertIsNone(docrefs.wanted(word, TOPS))

    def test_a_folder_the_repository_once_had_is_checked(self):
        self.assertEqual(docrefs.wanted("speed/", TOPS), "speed/")

    def test_the_top_folders_include_ones_the_history_had(self):
        tops = docrefs.tops_ever()
        self.assertIn("speed", tops)
        self.assertIn("testkit", tops)
        self.assertNotIn("technologies", tops)

    def test_a_game_folder_is_left_alone(self):
        self.assertIsNone(docrefs.wanted("technologies/", TOPS))


class Missing(unittest.TestCase):
    def test_a_folder_that_is_gone_is_missing(self):
        self.assertTrue(docrefs.missing("README.md", "speed/", set(), set()))

    def test_a_doc_that_is_gone_is_missing(self):
        self.assertTrue(docrefs.missing("README.md", "INTERNALS.md", set(), {"README.md"}))


if __name__ == "__main__":
    unittest.main()

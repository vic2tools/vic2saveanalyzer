"""
Holding a check's cases to their records: record, hold, differ, prune, and
leave out a payload key on purpose.

    python -m unittest discover -s testkit -p "test_*.py"
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import expected


def answer(**payload):
    return {"status.txt": "0\n",
            "report.payload.json": json.dumps(payload, indent=1, sort_keys=True)}


class HoldCases(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="holdtest")
        self.addCleanup(shutil.rmtree, self.root, True)

    def hold(self, cases, update=False, ignore=()):
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = expected.hold_cases(self.root, "check", cases, update, ignore=ignore)
        return code, said.getvalue()

    def test_recorded_then_held(self):
        cases = [("one", lambda: answer(a=1)), ("two", lambda: answer(a=2))]
        self.assertEqual(self.hold(cases, update=True)[0], 0)
        self.assertEqual(self.hold(cases)[0], 0)

    def test_a_difference_fails_and_is_shown(self):
        self.hold([("one", lambda: answer(a=1))], update=True)
        code, said = self.hold([("one", lambda: answer(a=9))])
        self.assertEqual(code, 1)
        self.assertIn("DIFFERS", said)

    def test_a_case_never_recorded_fails(self):
        self.assertEqual(self.hold([("new", lambda: answer(a=1))])[0], 1)

    def test_updating_prunes_cases_no_longer_asked(self):
        self.hold([("one", lambda: answer()), ("old", lambda: answer())], update=True)
        self.hold([("one", lambda: answer())], update=True)
        self.assertFalse(os.path.exists(expected.folder(self.root, "check", "old")))

    def test_an_ignored_key_is_left_out_of_every_element(self):
        self.hold([("w", lambda: answer(wars=[{"n": 1, "side_losses": [1, 2]}]))], update=True)
        changed = [("w", lambda: answer(wars=[{"n": 1}]))]
        self.assertEqual(self.hold(changed)[0], 1)
        self.assertEqual(self.hold(changed, ignore=("payload.wars[].side_losses",))[0], 0)

    def test_ignoring_a_key_hides_nothing_else(self):
        self.hold([("w", lambda: answer(wars=[{"n": 1, "side_losses": [1]}]))], update=True)
        other = [("w", lambda: answer(wars=[{"n": 2}]))]
        self.assertEqual(self.hold(other, ignore=("payload.wars[].side_losses",))[0], 1)


if __name__ == "__main__":
    unittest.main()

"""
The mutation harness's own logic: what a check's run says about a bug, and
whether every mutation in the table still finds the text it patches.

    python -m unittest discover -s testkit -p "test_*.py"
"""
import os
import unittest

import mutations
from mutate import Outcome, Verdict, verdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK = Outcome(0, False, "")
FAIL = Outcome(1, False, "")
SKIP = Outcome(77, False, "")
HUNG = Outcome(None, True, "")


class Verdicts(unittest.TestCase):
    def test_a_failure_is_caught(self):
        self.assertIs(verdict(OK, FAIL), Verdict.CAUGHT)

    def test_a_pass_is_blind(self):
        self.assertIs(verdict(OK, OK), Verdict.BLIND)

    def test_a_skip_is_not_caught(self):
        self.assertIs(verdict(OK, SKIP), Verdict.SKIPPED)

    def test_a_timeout_is_not_blind(self):
        self.assertIs(verdict(OK, HUNG), Verdict.TIMEOUT)

    def test_a_control_that_did_not_hold_leaves_it_untested(self):
        for control in (FAIL, SKIP, HUNG):
            self.assertIs(verdict(control, FAIL), Verdict.UNTESTED)


class Table(unittest.TestCase):
    def test_83_mutations_with_unique_names(self):
        names = [m.name for m in mutations.MUTATIONS]
        self.assertEqual(len(names), 83)
        self.assertEqual(len(set(names)), 83)

    def test_every_patch_finds_its_text_as_often_as_it_expects(self):
        for m in mutations.MUTATIONS:
            for patch in m.patches:
                path, old = patch[0], patch[1]
                count = patch[3] if len(patch) > 3 else 1
                with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
                    found = fh.read().count(old)
                with self.subTest(mutation=m.name, path=path):
                    if count:
                        self.assertEqual(found, count)
                    else:
                        self.assertGreater(found, 0)


class Cleanup(unittest.TestCase):
    def test_an_interrupted_run_leaves_no_worktree(self):
        import subprocess
        from mutate import Worktree
        made = []
        with self.assertRaises(KeyboardInterrupt):
            with Worktree(need_scanner=False) as tree:
                made.append(tree)
                # Build output nests deep enough to defeat plain deletion.
                deep = os.path.join(tree, *["nested_folder_%02d" % i for i in range(16)])
                os.makedirs("\\\\?\\" + deep if os.name == "nt" else deep)
                raise KeyboardInterrupt
        self.assertFalse(os.path.exists(made[0]))
        listed = subprocess.run(["git", "worktree", "list"], cwd=ROOT,
                                capture_output=True, text=True).stdout
        self.assertNotIn(os.path.basename(made[0]), listed)


if __name__ == "__main__":
    unittest.main()

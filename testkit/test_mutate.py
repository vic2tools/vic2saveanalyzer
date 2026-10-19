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
    def test_85_mutations_with_unique_names(self):
        names = [m.name for m in mutations.MUTATIONS]
        self.assertEqual(len(names), 85)
        self.assertEqual(len(set(names)), 85)

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


    def test_a_failure_while_setting_up_leaves_no_worktree(self):
        import subprocess
        from unittest import mock
        import mutate
        # Only this worktree is looked for: another run may be making its own.
        tree = mutate.Worktree(need_scanner=True)
        with mock.patch.object(mutate, "build", side_effect=RuntimeError("on purpose")):
            with self.assertRaises(RuntimeError):
                with tree:
                    pass
        self.assertFalse(os.path.exists(tree.path))
        listed = subprocess.run(["git", "worktree", "list"], cwd=ROOT,
                                capture_output=True, text=True).stdout
        self.assertNotIn(os.path.basename(tree.path), listed)


class Untested(unittest.TestCase):
    def test_each_missing_input_is_explained_once_with_a_count(self):
        from mutate import argv_for, untested_notes
        # Made up here: whether the list holds a row the baseline catches
        # changes as made-up worlds learn to catch them.
        rows = [mutations.Mutation(name, "a bug", "baseline.py",
                                   ("compare", "saves", "mod", "baseline"), [])
                for name in ("one", "two")]
        rows += [m for m in mutations.MUTATIONS if m.needs == ("saves",)][:1]
        unmet = {(m.catcher, m.needs): argv_for(m.needs, "", "", "") for m in rows}
        notes = untested_notes(rows, unmet)
        self.assertEqual(len(notes), 2)
        baseline = next(n for n in notes if "baseline" in n)
        self.assertIn("2 mutations", baseline)
        self.assertIn("baseline.py record", baseline)


class Checks(unittest.TestCase):
    def test_each_check_gets_a_temp_folder_of_its_own(self):
        import tempfile
        from unittest import mock
        import mutate
        seen = []

        class Done:
            returncode = 0
            def communicate(self, timeout=None):
                return "", None

        def popen(*args, **kw):
            seen.append(kw["env"])
            return Done()
        with mock.patch.object(mutate.subprocess, "Popen", side_effect=popen):
            mutate.check(ROOT, "x.py", [], 5)
            mutate.check(ROOT, "x.py", [], 5)
        real = tempfile.gettempdir()
        for env in seen:
            for name in ("TMPDIR", "TEMP", "TMP"):
                self.assertNotEqual(os.path.normcase(env[name]), os.path.normcase(real))
        self.assertNotEqual(seen[0]["TMPDIR"], seen[1]["TMPDIR"])


class Patches(unittest.TestCase):
    def test_a_file_that_is_not_there_does_not_apply(self):
        import tempfile
        from mutate import Unapplied, patch
        with tempfile.TemporaryDirectory() as tree:
            with self.assertRaises(Unapplied):
                patch(tree, "scanner/src/page/js/gone.js", "a", "b")


if __name__ == "__main__":
    unittest.main()

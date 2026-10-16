"""
What every check leans on: where things are, running the analyzer, and
skipping when something it needs is not here.

    python -m unittest discover -s testkit -p "test_*.py"
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import kit
from outcome import SKIPPED


class Paths(unittest.TestCase):
    def test_root_holds_the_analyzer(self):
        self.assertTrue(os.path.isfile(os.path.join(kit.ROOT, "vic2_analyzer.py")))

    def test_scanner_is_the_release_build(self):
        self.assertEqual(os.path.relpath(kit.SCANNER, kit.ROOT),
                         os.path.join("scanner", "target", "release",
                                      "vic2scan" + (".exe" if os.name == "nt" else "")))


class Analyze(unittest.TestCase):
    def test_runs_the_analyzer_with_the_arguments_given(self):
        done = kit.analyze("--help")
        self.assertEqual(done.returncode, 0)
        self.assertIn("--out", done.stdout)

    def test_hands_on_the_environment(self):
        with mock.patch.object(subprocess, "run") as run:
            kit.analyze("x", env={"A": "1"}, cwd="here", timeout=5)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:2], [sys.executable, os.path.join(kit.ROOT, "vic2_analyzer.py")])
        self.assertEqual(argv[2:], ["x"])
        self.assertEqual(run.call_args.kwargs["env"], {"A": "1"})
        self.assertEqual(run.call_args.kwargs["cwd"], "here")
        self.assertEqual(run.call_args.kwargs["timeout"], 5)


class Holding(unittest.TestCase):
    def test_every_temp_variable_points_inside_and_it_is_removed(self):
        with kit.holding("kittest") as (where, env):
            for name in ("TMPDIR", "TEMP", "TMP"):
                self.assertTrue(env[name].startswith(where))
            self.assertTrue(os.path.isdir(env["TMPDIR"]))
        self.assertFalse(os.path.exists(where))


class Needs(unittest.TestCase):
    def test_a_missing_scanner_skips(self):
        with mock.patch.object(kit, "SCANNER", os.path.join(tempfile.gettempdir(), "no-such")):
            with self.assertRaises(SystemExit) as stop:
                kit.need_scanner()
        self.assertEqual(stop.exception.code, SKIPPED)

    def test_a_missing_firefox_skips(self):
        with mock.patch("browser.firefox", return_value=None):
            with self.assertRaises(SystemExit) as stop:
                kit.need_firefox()
        self.assertEqual(stop.exception.code, SKIPPED)

    def test_a_present_scanner_passes(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            pass
        try:
            with mock.patch.object(kit, "SCANNER", fh.name):
                kit.need_scanner()
        finally:
            os.remove(fh.name)


if __name__ == "__main__":
    unittest.main()

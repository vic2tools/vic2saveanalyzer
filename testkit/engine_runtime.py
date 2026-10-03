"""The scanner relayed to the window, a missing scanner, and isolation of
writable test worlds."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vic2_analyzer
from matching import a_game
from enginecheck import copies_of


class Relay(unittest.TestCase):
    """
    `vic2_analyzer._relayed`: the scanner's output passed on to whoever is
    listening -- the window's log, or a check running the analyzer in its
    own process -- with the protocol lines turned into callbacks.
    """

    # The scanner ends its lines with a bare newline. A Python stand-in in a
    # pipe ends them as its system does, with a carriage return too on
    # Windows, so the stand-ins here are told which to use; the relay passes
    # on whatever it is given.

    def relay(self, body, hosted=True):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = vic2_analyzer._relayed([sys.executable, "-c", body], 0, hosted)
        return status, out.getvalue(), err.getvalue()

    def test_large_pipes_are_drained_and_progress_told(self):
        seen = []
        vic2_analyzer.set_progress(lambda *a: seen.append(a))
        self.addCleanup(vic2_analyzer.set_progress, None)
        status, out, err = self.relay(
            "import sys; sys.stdout.reconfigure(newline='\\n'); "
            "sys.stderr.write('x' * 200000); "
            "print('said'); print('@progress 1 2'); print('@done'); sys.exit(5)")
        self.assertEqual(status, 5)
        self.assertEqual(seen, [(1, 2)])
        self.assertEqual(out, "said\n")
        self.assertEqual(len(err), 200000)

    def test_report_ready_is_told_its_path(self):
        ready = []
        vic2_analyzer.set_report_ready(ready.append)
        self.addCleanup(vic2_analyzer.set_report_ready, None)
        self.relay("print('@ready /some/report.html')")
        self.assertEqual(ready, ["/some/report.html"])

    def test_unhosted_lines_are_passed_on_as_they_are(self):
        _status, out, _err = self.relay("import sys; sys.stdout.reconfigure(newline='\\n'); "
                                        "print('@progress 1 2')", hosted=False)
        self.assertEqual(out, "@progress 1 2\n")

    def test_stop_kills_the_child(self):
        vic2_analyzer.set_cancel_check(lambda: True)
        self.addCleanup(vic2_analyzer.set_cancel_check, None)
        started = []
        real = subprocess.Popen

        def launch(*args, **kwargs):
            child = real(*args, **kwargs)
            started.append(child)
            return child
        began = time.monotonic()
        with patch.object(subprocess, "Popen", side_effect=launch):
            with self.assertRaises(vic2_analyzer.Cancelled):
                self.relay("import time; print('x', flush=True); time.sleep(30)")
        # Stopped, not waited for: a scanner left reading would end on its
        # own in thirty seconds, with status 0, and Stop would have done
        # nothing but hide it.
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(len(started), 1)
        self.assertIsNotNone(started[0].returncode)
        self.assertNotEqual(started[0].returncode, 0)

    def test_a_missing_scanner_is_refused_with_how_to_build_it(self):
        from run import Run
        with patch.object(vic2_analyzer.fastscan, "available", return_value=None):
            with self.assertRaises(vic2_analyzer.RunError) as said:
                vic2_analyzer._front(Run(saves="."))
        self.assertIn("cargo build --release --manifest-path scanner/Cargo.toml",
                      str(said.exception))


class Fixtures(unittest.TestCase):
    def test_fixture_builder_refuses_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp, "real")
            a_game(str(real))
            original = real / "map/default.map"
            original.write_text("sea_starts = { 4 5 }\n")
            fake = Path(tmp, "fixture")
            fake.mkdir()
            try:
                (fake / "map").symlink_to(real / "map", target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(ValueError, "symlink"):
                a_game(str(fake))
            self.assertEqual(original.read_text(), "sea_starts = { 4 5 }\n")
            # Also guard a direct link to the file, not just its directory.
            (fake / "map").unlink()
            (fake / "map").mkdir()
            (fake / "map/default.map").symlink_to(original)
            with self.assertRaisesRegex(ValueError, "symlink"):
                a_game(str(fake))
            self.assertEqual(original.read_text(), "sea_starts = { 4 5 }\n")

    def test_fixture_copies_do_not_share_writable_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp, "src"), Path(tmp, "dst")
            a_game(str(src))
            (src / "map/default.map").write_text("keep this")
            copies_of(str(src), str(dst))
            a_game(str(dst))
            self.assertEqual((src / "map/default.map").read_text(), "keep this")
            self.assertFalse(any(p.is_symlink() for p in dst.rglob("*")))


if __name__ == "__main__":
    unittest.main()

"""Pipe failures, callback failures, and isolation of writable test worlds."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
from matching import a_game
from enginecheck import copies_of


class EngineRuntime(unittest.TestCase):
    def relay(self, body, progress=lambda *args: None):
        proc = subprocess.Popen([sys.executable, "-c", body],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        relay = engine._Relay(proc, True, progress, lambda path: None)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return proc, relay

    def test_large_pipes_are_drained_and_closed(self):
        seen = []
        proc, relay = self.relay(
            "import sys; sys.stderr.write('x' * 200000); "
            "print('@progress 1 1'); print('@done html=1 refused=')",
            lambda *args: seen.append(args))
        self.assertEqual(relay.finish(), 0)
        self.assertEqual(seen, [(1, 1)])
        self.assertEqual(relay.done, {"html": "1", "refused": ""})
        self.assertTrue(proc.stdout.closed and proc.stderr.closed)
        self.assertEqual(proc.returncode, 0)

    def test_callback_failure_is_raised_after_reaping(self):
        def fail(*args):
            raise RuntimeError("progress callback failed")
        with contextlib.redirect_stdout(io.StringIO()):
            proc, relay = self.relay(
                "print('@progress 1 1'); print('x' * 200000)", fail)
            with self.assertRaisesRegex(RuntimeError, "progress callback failed"):
                relay.finish()
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.closed and proc.stderr.closed)

    def test_malformed_protocol_is_not_silent_success(self):
        proc, relay = self.relay("print('@progress bad'); print('@done html=1 refused=')")
        with self.assertRaises(ValueError):
            relay.finish()
        self.assertEqual(proc.returncode, 0)

    def test_cancel_reaps_child_and_removes_handoff_files(self):
        class Stopped(Exception):
            pass
        def stop():
            raise Stopped()
        children = []
        real_popen = subprocess.Popen
        def launch(*args, **kwargs):
            child = real_popen([sys.executable, "-c",
                                "import time; time.sleep(30)"], **kwargs)
            children.append(child)
            return child
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(quiet=True)
            with patch("engine.spec", return_value={}), \
                 patch("engine.tempfile.gettempdir", return_value=tmp), \
                 patch("fastscan.available", return_value="fake-scanner"), \
                 patch("engine.subprocess.Popen", side_effect=launch):
                with self.assertRaises(Stopped):
                    engine.run_report(args, [], SimpleNamespace(pop_types=[]),
                                      None, None, "/no/mod", None, None, lambda *a: None,
                                      lambda *a: None, stop)
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].returncode)
            self.assertTrue(children[0].stdout.closed)
            self.assertTrue(children[0].stderr.closed)
            self.assertEqual(os.listdir(tmp), [])

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

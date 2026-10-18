"""The scanner relayed to the window, a missing scanner, and isolation of
writable test worlds."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import kit                                                  # noqa: E402
from vic2tools import launch
from fixtures import a_game
from fixtures import copies_of


class Relay(unittest.TestCase):
    """
    `launch._relayed`: the scanner's output passed on to whoever is
    listening -- the window's log, or a check running the analyzer in its
    own process -- with the protocol lines turned into callbacks.
    """

    # The scanner ends its lines with a bare newline. A Python stand-in in a
    # pipe ends them as its system does, with a carriage return too on
    # Windows, so the stand-ins here are told which to use; the relay passes
    # on whatever it is given.

    def relay(self, body, hosted=True, **told):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = launch._relayed([sys.executable, "-c", body], 0, hosted=hosted, **told)
        return status, out.getvalue(), err.getvalue()

    def test_large_pipes_are_drained_and_progress_told(self):
        seen = []
        status, out, err = self.relay(
            "import sys; sys.stdout.reconfigure(newline='\\n'); "
            "sys.stderr.write('x' * 200000); "
            "print('said'); print('@progress 1 2'); print('@done'); sys.exit(5)",
            progress=lambda *a: seen.append(a))
        self.assertEqual(status, 5)
        self.assertEqual(seen, [(1, 2)])
        self.assertEqual(out, "said\n")
        self.assertEqual(len(err), 200000)

    def test_report_ready_is_told_its_path(self):
        ready = []
        self.relay("print('@ready /some/report.html')", ready=ready.append)
        self.assertEqual(ready, ["/some/report.html"])

    def test_unhosted_lines_are_passed_on_as_they_are(self):
        _status, out, _err = self.relay("import sys; sys.stdout.reconfigure(newline='\\n'); "
                                        "print('@progress 1 2')", hosted=False)
        self.assertEqual(out, "@progress 1 2\n")

    def test_stop_kills_the_child(self):
        started = []
        real = subprocess.Popen

        def starting(*args, **kwargs):
            child = real(*args, **kwargs)
            started.append(child)
            return child
        began = time.monotonic()
        with patch.object(subprocess, "Popen", side_effect=starting):
            with self.assertRaises(launch.Cancelled):
                self.relay("import time; print('x', flush=True); time.sleep(30)",
                           cancel=lambda: True)
        # Stopped, not waited for: a scanner left reading would end on its
        # own in thirty seconds, with status 0, and Stop would have done
        # nothing but hide it.
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(len(started), 1)
        self.assertIsNotNone(started[0].returncode)
        self.assertNotEqual(started[0].returncode, 0)

    def test_a_missing_scanner_is_refused_with_how_to_build_it(self):
        with patch.object(launch, "available", return_value=None):
            with self.assertRaises(launch.RunError) as said:
                launch._front(launch.Run(saves="."))
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
            # A link to the folder: a symlink, or on Windows, where making
            # one takes administrator rights, a junction, which does not.
            try:
                (fake / "map").symlink_to(real / "map", target_is_directory=True)
            except OSError:
                if os.name != "nt":
                    self.skipTest("symlink creation unavailable")
                made = subprocess.run(["cmd", "/c", "mklink", "/J", str(fake / "map"),
                                       str(real / "map")], capture_output=True)
                if made.returncode:
                    self.skipTest("neither a symlink nor a junction can be made")
            with self.assertRaisesRegex(ValueError, "symlink"):
                a_game(str(fake))
            self.assertEqual(original.read_text(), "sea_starts = { 4 5 }\n")
            # Also guard a direct link to the file, not just its directory.
            try:
                (fake / "map").unlink()
            except OSError:
                os.rmdir(fake / "map")      # a junction is taken away as a folder
            (fake / "map").mkdir()
            try:
                (fake / "map/default.map").symlink_to(original)
            except OSError:
                return          # no right to make a link to a file here
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


def scanners_started_by(parents):
    """The ids (as text) of the scanner processes running now whose parent is
    one of `parents`, or None if this machine has no way to list them --
    which must never be read as "none left". Only a scanner this test
    started counts: another run on the machine may have its own going."""
    import shutil
    parents = {str(p) for p in parents}
    if os.name == "nt" and shutil.which("powershell"):
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='vic2scan.exe'\" | "
             "ForEach-Object { \"$($_.ProcessId) $($_.ParentProcessId)\" }"],
            capture_output=True, text=True).stdout
        pairs = [line.split() for line in out.splitlines() if line.strip()]
        return {pid for pid, parent in pairs if parent in parents}
    if shutil.which("pgrep"):
        found = set()
        for parent in parents:
            out = subprocess.run(["pgrep", "-x", "-P", parent, "vic2scan"],
                                 capture_output=True, text=True).stdout
            found |= set(out.split())
        return found
    return None


class Leftovers(unittest.TestCase):
    """Only a scanner this test started counts as left behind: another run on
    the machine -- another session's suite -- may have its own going."""

    def fake_scanner(self):
        import shutil
        where = tempfile.mkdtemp(prefix="vic2fake")
        self.addCleanup(shutil.rmtree, where, True)
        fake = os.path.join(where, "vic2scan" + (".exe" if os.name == "nt" else ""))
        shutil.copy(shutil.which("ping"), fake)
        return fake

    def test_a_scanner_this_process_started_is_seen(self):
        fake = self.fake_scanner()
        proc = subprocess.Popen([fake, "-n" if os.name == "nt" else "-c", "20", "127.0.0.1"],
                                stdout=subprocess.DEVNULL)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.5)
        seen = scanners_started_by({os.getpid()})
        if seen is None:
            self.skipTest("no way to list processes here")
        self.assertIn(str(proc.pid), seen)

    def test_a_scanner_someone_else_started_is_not(self):
        fake = self.fake_scanner()
        flag = "-n" if os.name == "nt" else "-c"
        starter = subprocess.run(
            [sys.executable, "-c",
             "import subprocess, sys; p = subprocess.Popen([sys.argv[1], sys.argv[2], '20', "
             "'127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); print(p.pid)", fake, flag],
            capture_output=True, text=True)
        other = starter.stdout.strip()
        self.addCleanup(subprocess.run, ["taskkill", "/F", "/PID", other] if os.name == "nt"
                        else ["kill", other], capture_output=True)
        time.sleep(0.5)
        seen = scanners_started_by({os.getpid()})
        if seen is None:
            self.skipTest("no way to list processes here")
        self.assertNotIn(other, seen)


class Pipes(unittest.TestCase):
    """
    A run's way out: piped into a reader that stops reading, and hosted by
    the window. Neither may crash on the way out, leak the protocol the
    scanner speaks to the window, or leave a scanner running.
    """

    def setUp(self):
        if not os.path.isfile(kit.SCANNER):
            self.skipTest("needs the scanner built")
        import fixtures
        self.where = tempfile.mkdtemp(prefix="vic2pipes")
        self.addCleanup(__import__("shutil").rmtree, self.where, True)
        self.env = kit.env_in(os.path.join(self.where, "tmp"))
        self.game = fixtures.a_vanilla(os.path.join(self.where, "Victoria 2"))
        self.saves = os.path.join(self.where, "saves")
        os.makedirs(self.saves)
        for n, date in enumerate(("1840.1.1", "1841.1.1", "1842.1.1")):
            fixtures.edge_save(os.path.join(self.saves, "s%d.v2" % n), date, tags=("ENG", "FRA"))
        self.parents = {os.getpid()}
        self.addCleanup(self.none_left)

    def none_left(self):
        # A scanner told to stop can take a moment to go; one of this test's
        # still there after five seconds was left behind.
        give_up = time.monotonic() + 5
        while True:
            left = scanners_started_by(self.parents)
            if not left or time.monotonic() > give_up:
                break
            time.sleep(0.2)
        if left:
            self.fail("a scanner was left running: %s" % sorted(left))

    def test_a_reader_that_goes_away_early(self):
        proc = subprocess.Popen(
            [sys.executable, os.path.join(kit.ROOT, "vic2_analyzer.py"), self.saves,
             "--out", os.path.join(self.where, "out"), "--game-root", self.game, "--rebuild"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, cwd=kit.ROOT)
        self.parents.add(proc.pid)
        for _ in range(3):
            proc.stdout.readline()
        proc.stdout.close()
        proc.stdout = None                  # gone: communicate() reads stderr only
        try:
            err = proc.communicate(timeout=60)[1].decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            proc.kill()
            self.fail("the run did not end within 60 s once its reader went away")
        self.assertNotIn("Traceback", err)
        self.assertNotIn("panicked", err)

    def test_a_hosted_run_leaks_no_protocol_lines(self):
        argv = ["vic2_analyzer.py", self.saves, "--out", os.path.join(self.where, "hosted"),
                "--game-root", self.game, "--rebuild"]
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", argv), patch.dict(os.environ, self.env):
            run = launch.Run.from_command_line(launch.command_line())
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                launch.analyze(run)
        leaked = [l for l in (out.getvalue() + err.getvalue()).splitlines() if l.startswith("@")]
        self.assertFalse(leaked, "protocol lines reached the log: %s" % leaked[:3])
        self.assertTrue(out.getvalue().strip(), "the hosted run said nothing at all")

    def test_processes_can_be_listed_here(self):
        if scanners_started_by({os.getpid()}) is None:
            self.skipTest("no tasklist or pgrep here, so leftover scanners cannot be looked for")


if __name__ == "__main__":
    unittest.main()

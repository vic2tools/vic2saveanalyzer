"""
The program's own package, `vic2tools/`: what it holds and where it keeps
what it remembers.

    python -m unittest discover -s testkit -p "test_*.py"
"""
import contextlib
import glob
import io
import os
import sys
import tempfile
import unittest

import kit                                               # noqa: F401  (the repo on the path)


class Package(unittest.TestCase):
    def test_the_package_names_each_module(self):
        import vic2tools.keeper                          # noqa: F401
        import vic2tools.keeper_tab                      # noqa: F401
        import vic2tools.launch                          # noqa: F401
        import vic2tools.report_tab                      # noqa: F401
        import vic2tools.settings                        # noqa: F401
        import vic2tools.share                           # noqa: F401

    def test_settings_files_stay_where_they_were(self):
        from vic2tools import settings
        self.assertTrue(settings.ANALYZER.replace(os.sep, "/").endswith(
            "vic2saveanalyzer/settings.json"), settings.ANALYZER)
        self.assertEqual(settings.KEEPER,
                         os.path.join(os.path.dirname(settings.ANALYZER), "keeper.json"))

    def test_no_program_module_is_left_at_the_root(self):
        found = {os.path.basename(p) for p in glob.glob(os.path.join(kit.ROOT, "*.py"))}
        self.assertEqual(found, {"vic2_analyzer.py", "build_exe.py"})

    def test_first_folder_skips_what_is_not_there(self):
        from vic2tools import settings
        with tempfile.TemporaryDirectory() as tmp:
            there = os.path.join(tmp, "there")
            os.makedirs(there)
            a_file = os.path.join(tmp, "a file")
            open(a_file, "w").close()
            self.assertEqual(settings.first_folder(
                ["", None, os.path.join(tmp, "missing"), a_file, there + "/", tmp]),
                os.path.normpath(there))
            self.assertEqual(settings.first_folder([os.path.join(tmp, "missing")]), "")

    def test_a_release_without_the_scanner_is_refused_before_bundling(self):
        # Refused before PyInstaller is started, not after a slow build of a
        # release that would refuse every run.
        from unittest.mock import patch
        import build_exe
        with patch.object(build_exe, "scanner_binary", return_value=None), \
                patch.object(build_exe.subprocess, "call") as bundle, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(build_exe.build(), 1)
        bundle.assert_not_called()

    def test_nothing_starts_a_python_worker(self):
        # Every run is the scanner's, a subprocess: no module of the package
        # starts a multiprocessing worker, or needs freeze_support for one.
        import ast
        for path in sorted(glob.glob(os.path.join(kit.ROOT, "vic2tools", "*.py"))):
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    with self.subTest(module=os.path.basename(path)):
                        self.assertNotEqual(name.split(".")[0], "multiprocessing")

    def test_analyze_hands_every_line_to_say(self):
        # A stand-in scanner: two lines out, one line err, and a progress
        # mark, each a moment apart so their order of arrival is theirs.
        from unittest.mock import patch
        from vic2tools import launch
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "stub.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write("import sys, time\n"
                         "sys.stdout.reconfigure(newline='\\n')\n"
                         "sys.stderr.reconfigure(newline='\\n')\n"
                         "for stream, line in ((sys.stdout, 'one'), (sys.stdout, '@progress 1 2'),\n"
                         "                     (sys.stdout, 'two'), (sys.stderr, 'three')):\n"
                         "    stream.write(line + '\\n'); stream.flush(); time.sleep(0.2)\n")
            if os.name == "nt":
                binary = os.path.join(tmp, "stub.cmd")
                with open(binary, "w", encoding="utf-8") as fh:
                    fh.write('@"%s" "%s" %%*\n' % (sys.executable, script))
            else:
                binary = os.path.join(tmp, "stub")
                with open(binary, "w", encoding="utf-8") as fh:
                    fh.write("#!/bin/sh\nexec '%s' '%s' \"$@\"\n" % (sys.executable, script))
                os.chmod(binary, 0o755)
            said, steps, real = [], [], io.StringIO()
            with patch.object(launch, "available", return_value=binary), \
                    contextlib.redirect_stdout(real), contextlib.redirect_stderr(real):
                launch.analyze(launch.Run(saves=tmp), say=said.append,
                               progress=lambda *a: steps.append(a))
        self.assertEqual(said, ["one\n", "two\n", "three\n"])
        self.assertEqual(steps, [(1, 2)])
        self.assertEqual(real.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

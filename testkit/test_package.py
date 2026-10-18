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

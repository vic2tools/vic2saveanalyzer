"""
The program's own package, `vic2tools/`: what it holds and where it keeps
what it remembers.

    python -m unittest discover -s testkit -p "test_*.py"
"""
import glob
import os
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


if __name__ == "__main__":
    unittest.main()

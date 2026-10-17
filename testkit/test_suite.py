"""
The one list of checks: what each is handed, and when it is skipped.

    python -m unittest discover -s testkit -p "test_*.py"
"""
import os
import unittest

import suite

EVERYTHING = {"scanner", "firefox", "display", "rustc"}


def named(script, title=None):
    return next(c for c in suite.CHECKS
                if c.script == script and (title is None or c.title == title))


class Lists(unittest.TestCase):
    def test_every_listed_script_exists(self):
        for c in suite.CHECKS:
            with self.subTest(script=c.script):
                self.assertTrue(os.path.isfile(os.path.join(suite.ROOT, "testkit", c.script)))

    def test_titles_are_unique(self):
        titles = [c.title for c in suite.CHECKS]
        self.assertEqual(len(titles), len(set(titles)))

    def test_browser_and_window_checks_run_alone(self):
        for c in suite.CHECKS:
            if c.needs & {"firefox", "display"}:
                with self.subTest(script=c.script):
                    self.assertTrue(c.exclusive)


class Skips(unittest.TestCase):
    def test_a_missing_need_is_named(self):
        self.assertEqual(suite.unmet(named("window.py"), have=EVERYTHING), ["saves"])

    def test_a_missing_need_means_no_command(self):
        self.assertIsNone(suite.argv_for(named("window.py"), have=EVERYTHING))


class Arguments(unittest.TestCase):
    def test_the_baseline_is_compared_with_the_campaign_it_names(self):
        argv = suite.argv_for(named("baseline.py"), saves="S", mod="M", baseline="B",
                              have=EVERYTHING)
        self.assertEqual(argv[1:], ["compare", "S", "--mod", "M", "--from", "B"])

    def test_no_baseline_means_the_comparison_is_skipped(self):
        self.assertEqual(suite.unmet(named("baseline.py"), saves="S", mod="M",
                                     have=EVERYTHING), ["baseline"])

    def test_report_words_become_paths(self):
        argv = suite.argv_for(named("invariants.py"), report=os.path.join("o", "report.html"),
                              have=EVERYTHING)
        self.assertEqual(argv[1:], [os.path.join("o", "nations_timeseries.csv"),
                                    os.path.join("o", "report.html")])


if __name__ == "__main__":
    unittest.main()

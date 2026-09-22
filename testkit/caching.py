#!/usr/bin/env python3
"""Cache reuse must preserve campaign data across file and option changes."""

import csv
import gc
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import fastscan
import savefmt
import vic2_analyzer as analyzer


class SaveCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vic2savecache")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        cache = patch.object(analyzer, "cache_dir",
                             return_value=str(self.root / "vic2_analyzer_cache"))
        cache.start()
        self.addCleanup(cache.stop)
        self.files = [str(self.root / f"{i}.v2") for i in range(2)]
        for i in range(2):
            self.write_save(i, i + 1)
        self.options = dict(jobs=1, verbose=False, mob_types=("farmers", "craftsmen"))

    def write_save(self, index, invention):
        return savefmt.write(
            self.files[index], savefmt.head(f"1880.{index + 1}.1"),
            savefmt.province(1, "ENG", [savefmt.pop("farmers", 1, 1000),
                                      savefmt.pop("craftsmen", 2, 2000)]),
            savefmt.country("ENG", techs=["flintlock_rifles"], inventions=[invention]))

    def test_summary_reuse_and_changed_campaign(self):
        first = analyzer.campaign_inventions(self.files, **self.options)
        self.assertEqual([p[1]["ENG"]["invention_ids"] for p in first], [[1], [2]])
        with patch.object(analyzer, "parse_saves_stream", side_effect=AssertionError("re-read")):
            self.assertEqual(first, analyzer.campaign_inventions(self.files, **self.options))
        self.write_save(1, 3)
        changed = analyzer.campaign_inventions(self.files, **self.options)
        self.assertEqual([p[1]["ENG"]["invention_ids"] for p in changed], [[1], [3]])

    def test_packaged_cache_survives_scanner_reextraction(self):
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(analyzer, "_scanner_fingerprint", return_value="first extraction"):
                first = analyzer._parser_fingerprint()
            with patch.object(analyzer, "_scanner_fingerprint", return_value="next extraction"):
                self.assertEqual(first, analyzer._parser_fingerprint())

    def test_same_size_edit_within_one_second(self):
        path = self.files[0]
        os.utime(path, ns=(1700000000100000000, 1700000000100000000))
        first = analyzer.campaign_inventions([path], **self.options)
        size = os.path.getsize(path)
        self.write_save(0, 3)
        os.utime(path, ns=(1700000000200000000, 1700000000200000000))
        self.assertEqual(size, os.path.getsize(path))
        second = analyzer.campaign_inventions([path], **self.options)
        self.assertEqual(first[0][1]["ENG"]["invention_ids"], [1])
        self.assertEqual(second[0][1]["ENG"]["invention_ids"], [3])

    def test_corrupt_summary_recovers_and_no_cache_bypasses_it(self):
        first = analyzer.campaign_inventions(self.files, **self.options)
        slot, = (self.root / "vic2_analyzer_cache").glob("inventions_*.pkl")
        slot.write_bytes(b"broken")
        self.assertEqual(first, analyzer.campaign_inventions(self.files, **self.options))
        with patch.object(analyzer, "parse_saves_stream", wraps=analyzer.parse_saves_stream) as read:
            self.assertEqual(first, analyzer.campaign_inventions(
                self.files, use_cache=False, **self.options))
            read.assert_called_once()

    def test_parallel_projection_and_invalid_file(self):
        bad = self.root / "bad.v2"
        bad.write_bytes(b"PK\x03\x04not a plaintext save")
        files = [self.files[0], str(bad), self.files[1]]
        serial = analyzer.campaign_inventions(files, use_cache=False, **self.options)
        parallel = analyzer.campaign_inventions(
            files, use_cache=False, **{**self.options, "jobs": 2})
        self.assertEqual(serial, parallel)
        self.assertEqual([p[0]["file"] for p in parallel], ["0.v2", "1.v2"])

    def test_changing_mobilizable_types_matches_uncached_run(self):
        def build(kind, output, cached=True):
            args = [sys.executable, str(HERE / "vic2_analyzer.py"), self.files[0],
                    "--out", str(self.root / output), "--no-html", "-q", "--jobs", "1",
                    "--mob-types", kind]
            if not cached:
                args.append("--no-cache")
            done = subprocess.run(args, capture_output=True, text=True,
                                  env={**os.environ, "TMPDIR": str(self.root),
                                       "TEMP": str(self.root), "TMP": str(self.root)})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            with (self.root / output / "nations_timeseries.csv").open() as fh:
                return next(csv.DictReader(fh))
        farmers = build("farmers", "farmers")
        craftsmen = build("craftsmen", "craftsmen")
        self.assertEqual(craftsmen, build("craftsmen", "fresh", cached=False))
        self.assertEqual(float(farmers["mobilization_pool"]), 1000)
        self.assertEqual(float(craftsmen["mobilization_pool"]), 2000)


class ScannerLifetimeTests(unittest.TestCase):
    def process(self, program):
        proc = subprocess.Popen([sys.executable, "-c", program],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()
        self.addCleanup(cleanup)
        return proc

    def test_collection_closes_pipes(self):
        proc = self.process("print('head'); print('tail')")
        running = fastscan.Running(proc, timeout=5)
        self.assertEqual(running.line(), b"head")
        self.assertEqual(running.remainder(), b"tail\n")
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.closed and proc.stderr.closed)

    def test_abandoned_owner_is_not_kept_alive_by_watchdog(self):
        proc = self.process("import time; time.sleep(60)")
        running = fastscan.Running(proc, timeout=60)
        del running
        gc.collect()
        proc.wait(timeout=2)
        self.assertTrue(proc.stdout.closed and proc.stderr.closed)

    def test_watchdog_interrupts_read(self):
        proc = self.process("import time; time.sleep(60)")
        running = fastscan.Running(proc, timeout=0.1)
        self.assertEqual(running.remainder(), b"")
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.closed and proc.stderr.closed)


if __name__ == "__main__":
    unittest.main()

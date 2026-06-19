"""Unit tests for CSV import logic."""

import sys
import tempfile
import unittest
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from database import Database
from import_manager import ImportManager
from utils import is_late, is_weekend, minutes_late, normalize_enno, parse_datetime


class TestImport(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db = Database(Path(self.tmp_db.name))
        self.config = Config()
        self.config._data["database"]["path"] = self.tmp_db.name
        self.import_mgr = ImportManager(self.db, self.config)
        self.sample = Path(__file__).parent / "sample_AGLog.csv"

    def tearDown(self):
        Path(self.tmp_db.name).unlink(missing_ok=True)

    def test_late_threshold_0801(self):
        self.assertTrue(is_late(time(8, 1, 0), time(8, 1, 0)))
        self.assertFalse(is_late(time(8, 0, 59), time(8, 1, 0)))
        self.assertEqual(minutes_late(time(8, 15, 0), time(8, 1, 0)), 14)

    def test_weekend_exclusion(self):
        dt = parse_datetime("2026/05/02 08:00:00")  # Saturday
        self.assertTrue(is_weekend(dt.date()))

    def test_validate_sample_file(self):
        valid, msg, meta = self.import_mgr.validate_file(self.sample)
        self.assertTrue(valid, msg)
        self.assertGreater(meta["row_count"], 0)

    def test_import_sample_file(self):
        result = self.import_mgr.import_file(self.sample)
        self.assertTrue(result.success)
        self.assertGreater(result.records_imported, 0)

    def test_import_aglog_misaligned_header(self):
        sample = Path(__file__).parent / "sample_AGLog_misaligned.txt"
        valid, msg, meta = self.import_mgr.validate_file(sample)
        self.assertTrue(valid, msg)
        self.assertEqual(meta["format"], "aglog")
        result = self.import_mgr.import_file(sample)
        self.assertTrue(result.success)
        self.assertGreater(result.records_imported, 0)
        emp = self.db.get_employee_by_enno("20")
        self.assertIsNotNone(emp)
        self.assertEqual(emp["enno"], "20")
        self.assertEqual(emp["export_name"], "ISAAC")

    def test_normalize_enno(self):
        self.assertEqual(normalize_enno("000000020"), "20")
        self.assertEqual(normalize_enno("7"), "7")
        self.assertEqual(normalize_enno("0"), "0")
        self.assertEqual(normalize_enno("ABC"), "ABC")

    def test_parse_double_space_datetime(self):
        dt = parse_datetime("2026/05/18  05:47:50")
        self.assertEqual(dt.hour, 5)
        self.assertEqual(dt.minute, 47)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            f.write("No\tMchn\tEnNo\tName\tMode\tIOMd\tDateTime\n")
            empty_path = Path(f.name)
        valid, msg, _ = self.import_mgr.validate_file(empty_path)
        self.assertFalse(valid)
        empty_path.unlink()


if __name__ == "__main__":
    unittest.main()

"""Unit tests for report generation."""

import sys
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from database import Database
from report_generator import ReportGenerator


class TestReports(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db = Database(Path(self.tmp_db.name))
        self.config = Config()
        self.config._data["database"]["path"] = self.tmp_db.name
        self.config._data["paths"]["exports"] = str(Path(tempfile.mkdtemp()))
        self.report_gen = ReportGenerator(self.db, self.config)

        emp_id = self.db.get_or_create_employee("1001", "John Smith")
        self.db.upsert_attendance(
            emp_id, date(2026, 5, 1), time(8, 0), time(17, 0), False, 0, "test.csv"
        )

    def tearDown(self):
        Path(self.tmp_db.name).unlink(missing_ok=True)

    def test_generate_html_dashboard(self):
        paths = self.report_gen.generate(
            "executive", date(2026, 5, 1), date(2026, 5, 31), "html"
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].exists())
        content = paths[0].read_text(encoding="utf-8")
        self.assertIn("Attendance Analytics Dashboard", content)
        self.assertIn("chart.js", content)
        paths = self.report_gen.generate(
            "executive", date(2026, 5, 1), date(2026, 5, 31), "pdf"
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].exists())
        self.assertGreater(paths[0].stat().st_size, 0)

    def test_generate_excel(self):
        paths = self.report_gen.generate(
            "executive", date(2026, 5, 1), date(2026, 5, 31), "excel", include_raw=True
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].exists())

    def test_late_offenders_report(self):
        emp_id = self.db.get_or_create_employee("1002", "Jane Doe")
        self.db.upsert_attendance(
            emp_id, date(2026, 5, 2), time(9, 0), time(17, 0), True, 59, "test.csv"
        )
        paths = self.report_gen.generate(
            "late_offenders", date(2026, 5, 1), date(2026, 5, 31), "pdf"
        )
        self.assertTrue(paths[0].exists())

    def test_leave_workbook_report(self):
        emp_id = self.db.get_or_create_employee("1003", "Test Employee")
        self.db.upsert_leave_record(emp_id, date(2026, 3, 15), "V")
        paths = self.report_gen.generate(
            "leave_workbook", date(2026, 1, 1), date(2026, 12, 31), "excel"
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].exists())


if __name__ == "__main__":
    unittest.main()

"""Unit tests for database operations."""

import sys
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import Database
from utils import effective_display_name, normalize_enno


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(Path(self.tmp.name))

    def tearDown(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_create_employee(self):
        emp_id = self.db.get_or_create_employee("1001", "John Smith")
        self.assertIsNotNone(emp_id)
        emp = self.db.get_employee_by_enno("1001")
        self.assertEqual(emp["export_name"], "John Smith")

    def test_upsert_attendance(self):
        emp_id = self.db.get_or_create_employee("1001", "John Smith")
        self.db.upsert_attendance(
            emp_id, date(2026, 5, 1), time(8, 0), time(17, 0), False, 0, "test.csv"
        )
        records = self.db.get_attendance_for_employee(emp_id, date(2026, 5, 1), date(2026, 5, 1))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["is_late"], 0)

    def test_display_name_update(self):
        emp_id = self.db.get_or_create_employee("1001", "John Smith")
        self.db.update_display_name(emp_id, "John S.", "test")
        emp = self.db.get_employee(emp_id)
        self.assertEqual(emp["display_name"], "John S.")
        changes = self.db.get_name_changes(emp_id)
        self.assertEqual(len(changes), 1)

    def test_employee_summary(self):
        emp_id = self.db.get_or_create_employee("1001", "John Smith")
        self.db.upsert_attendance(
            emp_id, date(2026, 5, 4), time(8, 0), time(17, 0), False, 0, "test.csv"
        )
        self.db.upsert_attendance(
            emp_id, date(2026, 5, 5), time(8, 30), time(17, 0), True, 29, "test.csv"
        )
        summary = self.db.compute_employee_summary(
            date(2026, 5, 1), date(2026, 5, 31), [0, 1, 2, 3, 4]
        )
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["days_present"], 2)
        self.assertEqual(summary[0]["late_days"], 1)
        self.assertEqual(summary[0]["absent_days"], summary[0]["working_days"] - 2)

    def test_enno_migration(self):
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO employees (enno, export_name) VALUES (?, ?)",
                ("000000020", "Test User"),
            )
        self.db.migrate_enno()
        emp = self.db.get_employee_by_enno("20")
        self.assertIsNotNone(emp)
        self.assertEqual(emp["enno"], "20")

    def test_normalize_enno_helper(self):
        self.assertEqual(normalize_enno("000000016"), "16")

    def test_effective_display_name(self):
        self.assertEqual(
            effective_display_name({"display_name": "Jane Doe", "export_name": "JANE"}),
            "Jane Doe",
        )
        self.assertEqual(
            effective_display_name({"display_name": None, "export_name": "JANE"}),
            "JANE",
        )
        self.assertEqual(
            effective_display_name({"display_name": "  ", "export_name": "JANE"}),
            "JANE",
        )

    def test_register_summary_uses_display_name(self):
        emp_id = self.db.get_or_create_employee("1001", "MACHINE NAME")
        self.db.update_display_name(emp_id, "Friendly Name")
        self.db.upsert_attendance(
            emp_id, date(2026, 5, 4), time(8, 0), time(17, 0), False, 0, "test.csv"
        )
        summary = self.db.compute_employee_summary(
            date(2026, 5, 1), date(2026, 5, 31), [0, 1, 2, 3, 4]
        )
        self.assertEqual(summary[0]["display_name"], "Friendly Name")

    def test_absent_days_calculation(self):
        emp_jane = self.db.get_or_create_employee("1002", "Jane Doe")
        emp_john = self.db.get_or_create_employee("1001", "John Smith")
        for d in (date(2026, 5, 18), date(2026, 5, 19), date(2026, 5, 20)):
            self.db.upsert_attendance(
                emp_john, d, time(8, 0), time(17, 0), False, 0, "test.csv"
            )
        self.db.upsert_attendance(
            emp_jane, date(2026, 5, 19), time(8, 0), time(17, 0), False, 0, "test.csv"
        )
        summary = self.db.compute_employee_summary(
            date(2026, 5, 18), date(2026, 5, 22), [0, 1, 2, 3, 4]
        )
        jane = next(s for s in summary if s["enno"] == "1002")
        self.assertEqual(jane["days_present"], 1)
        self.assertEqual(jane["working_days"], 3)
        self.assertEqual(jane["absent_days"], 2)


if __name__ == "__main__":
    unittest.main()

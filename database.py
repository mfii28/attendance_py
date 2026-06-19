"""SQLite database operations for the Attendance Management System."""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from utils import (
    effective_display_name,
    format_date,
    format_time,
    is_weekend,
    logger,
    normalize_enno,
    working_days_in_range,
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    enno TEXT UNIQUE NOT NULL,
    export_name TEXT NOT NULL,
    display_name TEXT,
    department TEXT,
    is_active BOOLEAN DEFAULT 1,
    hire_date DATE,
    termination_date DATE,
    notes TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    date DATE NOT NULL,
    arrival_time TIME,
    departure_time TIME,
    is_late BOOLEAN DEFAULT 0,
    late_minutes INTEGER DEFAULT 0,
    source_file TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    UNIQUE(employee_id, date)
);

CREATE TABLE IF NOT EXISTS imported_files (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    original_filename TEXT,
    date_range_start DATE,
    date_range_end DATE,
    record_count INTEGER,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS name_changes (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER,
    old_display_name TEXT,
    new_display_name TEXT,
    changed_by TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS monthly_metrics (
    id INTEGER PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    avg_attendance_rate REAL,
    total_late_incidents INTEGER,
    avg_lateness_minutes REAL,
    perfect_attendance_count INTEGER,
    UNIQUE(year, month)
);

CREATE TABLE IF NOT EXISTS leave_types (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    deduction REAL NOT NULL,
    counts_toward_balance INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS leave_entitlements (
    employee_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    annual_allocation REAL DEFAULT 0,
    carry_over REAL DEFAULT 0,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    UNIQUE(employee_id, year)
);

CREATE TABLE IF NOT EXISTS leave_records (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    date DATE NOT NULL,
    code TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (code) REFERENCES leave_types(code),
    UNIQUE(employee_id, date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_records(date);
CREATE INDEX IF NOT EXISTS idx_attendance_employee ON attendance_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_employees_enno ON employees(enno);
CREATE INDEX IF NOT EXISTS idx_leave_records_date ON leave_records(date);
CREATE INDEX IF NOT EXISTS idx_leave_records_employee ON leave_records(employee_id);
"""

DEFAULT_LEAVE_TYPES = [
    ("H", "Holiday", 1.0, 1),
    ("H1", "Half Day (morning)", 0.5, 1),
    ("H2", "Half Day (afternoon)", 0.5, 1),
    ("Q", "Quarter day", 0.25, 1),
    ("V", "Vacation", 1.0, 1),
    ("S", "Sickness", 1.0, 1),
    ("M", "Maternity/Paternity", 1.0, 1),
    ("C", "Compassionate", 1.0, 1),
    ("A", "Absent/No Show", 1.0, 1),
    ("I", "Inactive", 1.0, 1),
]


class Database:
    """SQLite database wrapper."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self.migrate_enno()
        self.migrate_display_names()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
            self._seed_leave_types(conn)
        logger.info("Database initialized at %s", self.db_path)

    def _seed_leave_types(self, conn: sqlite3.Connection) -> None:
        for code, name, deduction, counts in DEFAULT_LEAVE_TYPES:
            conn.execute(
                """INSERT OR IGNORE INTO leave_types (code, name, deduction, counts_toward_balance)
                   VALUES (?, ?, ?, ?)""",
                (code, name, deduction, counts),
            )

    def compact(self) -> None:
        with self.connection() as conn:
            conn.execute("VACUUM")
        logger.info("Database compacted")

    # --- Employee operations ---

    def migrate_enno(self) -> None:
        """Normalize employee IDs and merge duplicates created by leading zeros."""
        with self.connection() as conn:
            rows = conn.execute("SELECT id, enno FROM employees").fetchall()
            for row in rows:
                old_enno = row["enno"]
                new_enno = normalize_enno(old_enno)
                if new_enno == old_enno:
                    continue
                existing = conn.execute(
                    "SELECT id FROM employees WHERE enno = ?", (new_enno,)
                ).fetchone()
                if existing:
                    keeper_id = existing["id"]
                    dup_id = row["id"]
                    dup_records = conn.execute(
                        """SELECT date, arrival_time, departure_time, is_late, late_minutes,
                                  source_file, imported_at
                           FROM attendance_records WHERE employee_id = ?""",
                        (dup_id,),
                    ).fetchall()
                    for rec in dup_records:
                        conn.execute(
                            """INSERT OR IGNORE INTO attendance_records
                               (employee_id, date, arrival_time, departure_time, is_late,
                                late_minutes, source_file, imported_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                keeper_id, rec["date"], rec["arrival_time"],
                                rec["departure_time"], rec["is_late"], rec["late_minutes"],
                                rec["source_file"], rec["imported_at"],
                            ),
                        )
                    conn.execute(
                        "DELETE FROM attendance_records WHERE employee_id = ?", (dup_id,)
                    )
                    conn.execute(
                        "UPDATE name_changes SET employee_id = ? WHERE employee_id = ?",
                        (keeper_id, dup_id),
                    )
                    conn.execute("DELETE FROM employees WHERE id = ?", (dup_id,))
                    logger.warning("Merged duplicate employee %s into %s", old_enno, new_enno)
                else:
                    conn.execute(
                        "UPDATE employees SET enno = ? WHERE id = ?",
                        (new_enno, row["id"]),
                    )

    def get_or_create_employee(
        self, enno: str, export_name: str, display_name: Optional[str] = None
    ) -> int:
        enno = normalize_enno(enno)
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id, export_name FROM employees WHERE enno = ?", (enno,)
            ).fetchone()
            if row:
                if row["export_name"] != export_name:
                    conn.execute(
                        "UPDATE employees SET export_name = ?, last_updated = ? WHERE id = ?",
                        (export_name, datetime.now().isoformat(), row["id"]),
                    )
                return row["id"]
            cur = conn.execute(
                """INSERT INTO employees (enno, export_name, display_name, last_updated)
                   VALUES (?, ?, ?, ?)""",
                (enno, export_name, display_name, datetime.now().isoformat()),
            )
            return cur.lastrowid

    def migrate_display_names(self) -> None:
        """Clear auto-copied display names so export name remains the default."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT e.id FROM employees e
                   WHERE e.display_name IS NOT NULL
                     AND e.display_name = e.export_name
                     AND NOT EXISTS (
                         SELECT 1 FROM name_changes nc WHERE nc.employee_id = e.id
                     )"""
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE employees SET display_name = NULL WHERE id = ?",
                    (row["id"],),
                )

    def get_employee(self, employee_id: int) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
            return dict(row) if row else None

    def get_employee_by_enno(self, enno: str) -> Optional[Dict[str, Any]]:
        enno = normalize_enno(enno)
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM employees WHERE enno = ?", (enno,)).fetchone()
            return dict(row) if row else None

    def get_all_employees(self, active_only: bool = True) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            sql = "SELECT * FROM employees"
            if active_only:
                sql += " WHERE is_active = 1"
            sql += " ORDER BY COALESCE(NULLIF(TRIM(display_name), ''), export_name)"
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def update_display_name(
        self, employee_id: int, new_name: str, changed_by: str = "user"
    ) -> None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT display_name FROM employees WHERE id = ?", (employee_id,)
            ).fetchone()
            old_name = row["display_name"] if row else None
            conn.execute(
                "UPDATE employees SET display_name = ?, last_updated = ? WHERE id = ?",
                (new_name, datetime.now().isoformat(), employee_id),
            )
            conn.execute(
                """INSERT INTO name_changes (employee_id, old_display_name, new_display_name, changed_by)
                   VALUES (?, ?, ?, ?)""",
                (employee_id, old_name, new_name, changed_by),
            )
        logger.info("Name changed for employee %s: %s -> %s", employee_id, old_name, new_name)

    def bulk_update_display_names(self, updates: List[Tuple[int, str]], changed_by: str = "user") -> int:
        count = 0
        for emp_id, new_name in updates:
            self.update_display_name(emp_id, new_name, changed_by)
            count += 1
        return count

    def reset_display_name(self, employee_id: int, changed_by: str = "user") -> None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT display_name, export_name FROM employees WHERE id = ?",
                (employee_id,),
            ).fetchone()
            if not row:
                return
            old_name = row["display_name"]
            conn.execute(
                "UPDATE employees SET display_name = NULL, last_updated = ? WHERE id = ?",
                (datetime.now().isoformat(), employee_id),
            )
            conn.execute(
                """INSERT INTO name_changes (employee_id, old_display_name, new_display_name, changed_by)
                   VALUES (?, ?, ?, ?)""",
                (employee_id, old_name, row["export_name"], changed_by),
            )

    def search_employees(self, query: str) -> List[Dict[str, Any]]:
        q = f"%{query}%"
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM employees
                   WHERE enno LIKE ? OR export_name LIKE ? OR display_name LIKE ?
                   ORDER BY display_name""",
                (q, q, q),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_name_changes(self, employee_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            if employee_id:
                rows = conn.execute(
                    "SELECT * FROM name_changes WHERE employee_id = ? ORDER BY changed_at DESC",
                    (employee_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM name_changes ORDER BY changed_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    # --- Attendance operations ---

    def upsert_attendance(
        self,
        employee_id: int,
        record_date: date,
        arrival: Optional[time],
        departure: Optional[time],
        is_late_flag: bool,
        late_mins: int,
        source_file: str,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO attendance_records
                   (employee_id, date, arrival_time, departure_time, is_late, late_minutes, source_file, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(employee_id, date) DO UPDATE SET
                   arrival_time = excluded.arrival_time,
                   departure_time = excluded.departure_time,
                   is_late = excluded.is_late,
                   late_minutes = excluded.late_minutes,
                   source_file = excluded.source_file,
                   imported_at = excluded.imported_at""",
                (
                    employee_id,
                    record_date.isoformat(),
                    arrival.isoformat() if arrival else None,
                    departure.isoformat() if departure else None,
                    int(is_late_flag),
                    late_mins,
                    source_file,
                    datetime.now().isoformat(),
                ),
            )

    def record_exists(self, employee_id: int, record_date: date, arrival: time) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                """SELECT id FROM attendance_records
                   WHERE employee_id = ? AND date = ? AND arrival_time = ?""",
                (employee_id, record_date.isoformat(), arrival.isoformat()),
            ).fetchone()
            return row is not None

    def get_attendance_for_employee(
        self, employee_id: int, start: date, end: date
    ) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM attendance_records
                   WHERE employee_id = ? AND date BETWEEN ? AND ?
                   ORDER BY date""",
                (employee_id, start.isoformat(), end.isoformat()),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_attendance(self, start: date, end: date) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT ar.*, e.enno, e.display_name, e.export_name
                   FROM attendance_records ar
                   JOIN employees e ON ar.employee_id = e.id
                   WHERE ar.date BETWEEN ? AND ?
                   ORDER BY ar.date, COALESCE(NULLIF(TRIM(e.display_name), ''), e.export_name)""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return [dict(r) for r in rows]

    def archive_old_records(self, cutoff: date) -> int:
        """Move records older than cutoff to archive table/file; delete from main."""
        with self.connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as c FROM attendance_records WHERE date < ?",
                (cutoff.isoformat(),),
            ).fetchone()["c"]
            if count == 0:
                return 0
            conn.execute(
                "DELETE FROM attendance_records WHERE date < ?",
                (cutoff.isoformat(),),
            )
        logger.info("Archived %d records before %s", count, cutoff)
        return count

    def delete_attendance_in_range(self, start: date, end: date) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                "DELETE FROM attendance_records WHERE date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            )
            return cur.rowcount

    # --- Import file tracking ---

    def add_imported_file(
        self,
        filename: str,
        original_filename: str,
        date_start: date,
        date_end: date,
        record_count: int,
    ) -> int:
        with self.connection() as conn:
            conn.execute("UPDATE imported_files SET is_active = 0")
            cur = conn.execute(
                """INSERT INTO imported_files
                   (filename, original_filename, date_range_start, date_range_end, record_count, is_active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (
                    filename,
                    original_filename,
                    date_start.isoformat(),
                    date_end.isoformat(),
                    record_count,
                ),
            )
            return cur.lastrowid

    def get_active_import(self) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM imported_files WHERE is_active = 1 ORDER BY import_date DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_all_imports(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM imported_files ORDER BY import_date DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Metrics ---

    def upsert_monthly_metrics(
        self,
        year: int,
        month: int,
        avg_rate: float,
        late_incidents: int,
        avg_late_mins: float,
        perfect_count: int,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO monthly_metrics
                   (year, month, avg_attendance_rate, total_late_incidents, avg_lateness_minutes, perfect_attendance_count)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(year, month) DO UPDATE SET
                   avg_attendance_rate = excluded.avg_attendance_rate,
                   total_late_incidents = excluded.total_late_incidents,
                   avg_lateness_minutes = excluded.avg_lateness_minutes,
                   perfect_attendance_count = excluded.perfect_attendance_count""",
                (year, month, avg_rate, late_incidents, avg_late_mins, perfect_count),
            )

    def get_monthly_metrics(self, months: int = 12) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM monthly_metrics
                   ORDER BY year DESC, month DESC LIMIT ?""",
                (months,),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_working_days_count(
        self,
        start: date,
        end: date,
        working_days: List[int],
        holidays: Optional[List[date]] = None,
        mode: str = "data",
    ) -> int:
        """Count working days: 'data' = unique weekday dates in records (bash script logic)."""
        if mode == "calendar":
            return working_days_in_range(start, end, working_days, holidays)
        holidays_set = set(holidays or [])
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT DISTINCT date FROM attendance_records
                   WHERE date BETWEEN ? AND ?""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        count = 0
        for row in rows:
            d = datetime.strptime(row["date"], "%Y-%m-%d").date()
            if not is_weekend(d, working_days) and d not in holidays_set:
                count += 1
        return count

    def get_working_dates(
        self,
        start: date,
        end: date,
        working_days: List[int],
        holidays: Optional[List[date]] = None,
    ) -> List[date]:
        """Return sorted unique weekday dates with attendance records in range."""
        holidays_set = set(holidays or [])
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT DISTINCT date FROM attendance_records
                   WHERE date BETWEEN ? AND ? ORDER BY date""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        dates = []
        for row in rows:
            d = datetime.strptime(row["date"], "%Y-%m-%d").date()
            if not is_weekend(d, working_days) and d not in holidays_set:
                dates.append(d)
        return dates

    def compute_employee_summary(
        self,
        start: date,
        end: date,
        working_days: List[int],
        holidays: Optional[List[date]] = None,
        working_days_mode: str = "data",
        excused_codes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Compute attendance summary per employee for date range."""
        employees = self.get_all_employees(active_only=True)
        work_days = self.get_working_days_count(
            start, end, working_days, holidays, mode=working_days_mode
        )
        holidays_set = set(holidays or [])
        excused_set = set(excused_codes or [])
        results = []

        with self.connection() as conn:
            for emp in employees:
                rows = conn.execute(
                    """SELECT * FROM attendance_records
                       WHERE employee_id = ? AND date BETWEEN ? AND ?""",
                    (emp["id"], start.isoformat(), end.isoformat()),
                ).fetchall()
                records = [dict(r) for r in rows]
                present_dates = {
                    datetime.strptime(r["date"], "%Y-%m-%d").date()
                    for r in records
                }
                weekday_records = [
                    r for r in records
                    if not is_weekend(
                        datetime.strptime(r["date"], "%Y-%m-%d").date(), working_days
                    )
                    and datetime.strptime(r["date"], "%Y-%m-%d").date() not in holidays_set
                ]
                present = len(weekday_records)
                late_days = sum(1 for r in weekday_records if r["is_late"])
                attendance_rate = (present * 100 // work_days) if work_days > 0 else 0
                lateness_rate = (late_days * 100 // present) if present > 0 else 0

                arrivals = [
                    datetime.strptime(r["arrival_time"], "%H:%M:%S").time()
                    for r in weekday_records
                    if r["arrival_time"]
                ]
                avg_arrival = None
                earliest = None
                latest = None
                if arrivals:
                    total_secs = sum(t.hour * 3600 + t.minute * 60 + t.second for t in arrivals)
                    avg_secs = total_secs // len(arrivals)
                    avg_arrival = time(avg_secs // 3600, (avg_secs % 3600) // 60, avg_secs % 60)
                    earliest = min(arrivals)
                    latest = max(arrivals)

                leave_rows = self.get_leave_for_employee(emp["id"], start, end)
                leave_by_date = {
                    datetime.strptime(r["date"], "%Y-%m-%d").date(): r["code"]
                    for r in leave_rows
                }
                excused_days = 0
                leave_days_by_code: Dict[str, int] = {}
                for leave_date, code in leave_by_date.items():
                    if is_weekend(leave_date, working_days) or leave_date in holidays_set:
                        continue
                    leave_days_by_code[code] = leave_days_by_code.get(code, 0) + 1
                    if leave_date not in present_dates and code in excused_set:
                        excused_days += 1

                raw_absent = max(0, work_days - present)
                absent_days = max(0, raw_absent - excused_days)

                results.append({
                    "employee_id": emp["id"],
                    "enno": emp["enno"],
                    "export_name": emp["export_name"],
                    "display_name": effective_display_name(emp),
                    "days_present": present,
                    "absent_days": absent_days,
                    "excused_days": excused_days,
                    "leave_days_by_code": leave_days_by_code,
                    "working_days": work_days,
                    "attendance_rate": attendance_rate,
                    "late_days": late_days,
                    "lateness_rate": lateness_rate,
                    "avg_arrival": format_time(avg_arrival),
                    "earliest_arrival": format_time(earliest),
                    "latest_arrival": format_time(latest),
                })
        results.sort(key=lambda x: x["lateness_rate"], reverse=True)
        return results

    def get_dashboard_kpis(
        self,
        start: date,
        end: date,
        working_days: List[int],
        holidays: Optional[List[date]] = None,
        excused_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        summaries = self.compute_employee_summary(
            start, end, working_days, holidays, excused_codes=excused_codes
        )
        active_count = len(summaries) or len(self.get_all_employees(active_only=True))
        if not summaries:
            return {
                "active_employees": active_count,
                "attendance_rate": 0,
                "late_incidents": 0,
                "perfect_attendance": 0,
                "working_days": 0,
                "high_late_count": 0,
            }
        work_days = summaries[0]["working_days"] if summaries else 0
        total_present = sum(s["days_present"] for s in summaries)
        late_total = sum(s["late_days"] for s in summaries)
        # Bash script: total_present * 100 / (working_days * total_employees)
        if work_days * active_count > 0:
            avg_rate = total_present * 100 // (work_days * active_count)
        else:
            avg_rate = 0
        perfect = sum(1 for s in summaries if s["late_days"] == 0)
        high_late = sum(1 for s in summaries if s["late_days"] >= 5)
        return {
            "active_employees": active_count,
            "attendance_rate": avg_rate,
            "late_incidents": late_total,
            "perfect_attendance": perfect,
            "working_days": work_days,
            "high_late_count": high_late,
        }

    def get_top_offenders(
        self,
        start: date,
        end: date,
        limit: int = 5,
        working_days: Optional[List[int]] = None,
        holidays: Optional[List[date]] = None,
        excused_codes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        working_days = working_days or [0, 1, 2, 3, 4]
        summaries = self.compute_employee_summary(
            start, end, working_days, holidays, excused_codes=excused_codes
        )
        offenders = sorted(summaries, key=lambda x: x["late_days"], reverse=True)
        return [o for o in offenders if o["late_days"] > 0][:limit]

    def get_health_stats(self) -> Dict[str, Any]:
        with self.connection() as conn:
            emp_count = conn.execute("SELECT COUNT(*) as c FROM employees").fetchone()["c"]
            rec_count = conn.execute("SELECT COUNT(*) as c FROM attendance_records").fetchone()["c"]
            file_count = conn.execute("SELECT COUNT(*) as c FROM imported_files").fetchone()["c"]
            min_date = conn.execute("SELECT MIN(date) as d FROM attendance_records").fetchone()["d"]
            max_date = conn.execute("SELECT MAX(date) as d FROM attendance_records").fetchone()["d"]
        size_mb = self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
        return {
            "employees": emp_count,
            "records": rec_count,
            "imports": file_count,
            "date_range": f"{min_date or 'N/A'} to {max_date or 'N/A'}",
            "size_mb": round(size_mb, 2),
        }

    # --- Leave operations ---

    def get_leave_types(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM leave_types ORDER BY code"
            ).fetchall()
            return [dict(r) for r in rows]

    def upsert_leave_record(
        self, employee_id: int, record_date: date, code: str, notes: Optional[str] = None
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO leave_records (employee_id, date, code, notes)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(employee_id, date) DO UPDATE SET
                   code = excluded.code, notes = excluded.notes""",
                (employee_id, record_date.isoformat(), code, notes),
            )

    def delete_leave_record(self, employee_id: int, record_date: date) -> bool:
        with self.connection() as conn:
            cur = conn.execute(
                "DELETE FROM leave_records WHERE employee_id = ? AND date = ?",
                (employee_id, record_date.isoformat()),
            )
            return cur.rowcount > 0

    def get_leave_for_employee(
        self, employee_id: int, start: date, end: date
    ) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT lr.*, lt.name as type_name, lt.deduction
                   FROM leave_records lr
                   JOIN leave_types lt ON lr.code = lt.code
                   WHERE lr.employee_id = ? AND lr.date BETWEEN ? AND ?
                   ORDER BY lr.date""",
                (employee_id, start.isoformat(), end.isoformat()),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_leave_for_month(self, year: int, month: int) -> List[Dict[str, Any]]:
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        start = date(year, month, 1)
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT lr.*, lt.name as type_name, lt.deduction,
                          e.enno, e.export_name, e.display_name
                   FROM leave_records lr
                   JOIN leave_types lt ON lr.code = lt.code
                   JOIN employees e ON lr.employee_id = e.id
                   WHERE lr.date BETWEEN ? AND ?
                   ORDER BY e.export_name, lr.date""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_leave_for_year(self, year: int) -> List[Dict[str, Any]]:
        return self._get_leave_in_range(date(year, 1, 1), date(year, 12, 31))

    def _get_leave_in_range(self, start: date, end: date) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT lr.*, lt.name as type_name, lt.deduction,
                          e.enno, e.export_name, e.display_name
                   FROM leave_records lr
                   JOIN leave_types lt ON lr.code = lt.code
                   JOIN employees e ON lr.employee_id = e.id
                   WHERE lr.date BETWEEN ? AND ?
                   ORDER BY e.export_name, lr.date""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_entitlement(self, employee_id: int, year: int) -> Dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute(
                """SELECT * FROM leave_entitlements
                   WHERE employee_id = ? AND year = ?""",
                (employee_id, year),
            ).fetchone()
            if row:
                return dict(row)
            return {
                "employee_id": employee_id,
                "year": year,
                "annual_allocation": 0.0,
                "carry_over": 0.0,
            }

    def set_entitlement(
        self,
        employee_id: int,
        year: int,
        annual_allocation: float,
        carry_over: float = 0.0,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO leave_entitlements (employee_id, year, annual_allocation, carry_over)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(employee_id, year) DO UPDATE SET
                   annual_allocation = excluded.annual_allocation,
                   carry_over = excluded.carry_over""",
                (employee_id, year, annual_allocation, carry_over),
            )

    def get_leave_on_date(self, employee_id: int, record_date: date) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                """SELECT lr.*, lt.name as type_name, lt.deduction
                   FROM leave_records lr
                   JOIN leave_types lt ON lr.code = lt.code
                   WHERE lr.employee_id = ? AND lr.date = ?""",
                (employee_id, record_date.isoformat()),
            ).fetchone()
            return dict(row) if row else None

    def has_attendance_on_date(self, employee_id: int, record_date: date) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id FROM attendance_records WHERE employee_id = ? AND date = ?",
                (employee_id, record_date.isoformat()),
            ).fetchone()
            return row is not None


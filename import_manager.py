"""CSV import logic for attendance machine exports."""

import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import Config
from database import Database
from utils import (
    AGLOG_COLUMNS,
    detect_encoding,
    is_late,
    is_weekend,
    logger,
    minutes_late,
    normalize_enno,
    parse_datetime,
    parse_time,
    sanitize_filename,
    suggest_filename,
    validate_csv_columns,
)


class ImportResult:
    """Result of a CSV import operation."""

    def __init__(self):
        self.success = False
        self.records_imported = 0
        self.records_skipped = 0
        self.new_employees = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.date_start: Optional[date] = None
        self.date_end: Optional[date] = None
        self.suggested_filename = ""


class ImportManager:
    """Handles CSV file validation, parsing, and database import."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    def preview_file(self, file_path: Path, max_rows: int = 5) -> Tuple[List[Dict], Dict[str, Any]]:
        """Preview first rows and detect metadata."""
        meta = self._analyze_file(file_path)
        df = self._load_dataframe(file_path, meta["encoding"], nrows=max_rows)
        records = df.to_dict(orient="records")
        return records, meta

    def _detect_delimiter(self, file_path: Path, encoding: str) -> str:
        with open(file_path, "r", encoding=encoding) as f:
            first_line = f.readline()
        if "\t" in first_line:
            return "\t"
        if ";" in first_line:
            return ";"
        return ","

    def _is_aglog_format(self, file_path: Path, encoding: str) -> bool:
        """Detect AGLog export with extra empty tab columns in header."""
        with open(file_path, "r", encoding=encoding) as f:
            header = f.readline()
            data = f.readline()
        if not header or not data:
            return False
        header_parts = header.rstrip("\n\r").split("\t")
        data_parts = data.rstrip("\n\r").split("\t")
        header_fields = {p.strip() for p in header_parts if p.strip()}
        return (
            "DateTime" in header_fields
            and "EnNo" in header_fields
            and len(data_parts) == 7
            and len(header_parts) != len(data_parts)
        )

    def _read_aglog_dataframe(
        self, file_path: Path, encoding: str, nrows: Optional[int] = None
    ) -> pd.DataFrame:
        """Parse AGLog files where header has extra empty tab columns vs 7-column data rows."""
        rows: List[List[str]] = []
        with open(file_path, "r", encoding=encoding) as f:
            f.readline()  # skip header
            for line in f:
                line = line.rstrip("\n\r")
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                rows.append(parts[:7])
                if nrows and len(rows) >= nrows:
                    break

        df = pd.DataFrame(rows, columns=AGLOG_COLUMNS)
        df = df.fillna("")
        df["EnNo"] = df["EnNo"].astype(str).str.strip()
        df["Name"] = df["Name"].astype(str).str.strip()
        df["DateTime"] = df["DateTime"].astype(str).str.strip()
        return df

    def _load_dataframe(
        self, file_path: Path, encoding: str, nrows: Optional[int] = None
    ) -> pd.DataFrame:
        """Load attendance export, using AGLog parser when header/data columns differ."""
        if self._is_aglog_format(file_path, encoding):
            return self._read_aglog_dataframe(file_path, encoding, nrows)

        delimiter = self._detect_delimiter(file_path, encoding)
        df = pd.read_csv(
            file_path, sep=delimiter, encoding=encoding, nrows=nrows, dtype=str
        )
        df = df.fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        if "EnNo" in df.columns:
            df["EnNo"] = df["EnNo"].astype(str).str.strip()
        if "Name" in df.columns:
            df["Name"] = df["Name"].astype(str).str.strip()
        if "DateTime" in df.columns:
            df["DateTime"] = df["DateTime"].astype(str).str.strip()
        return df

    def _analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze file for date range and validation."""
        encoding = detect_encoding(file_path)
        delimiter = self._detect_delimiter(file_path, encoding)
        use_aglog = self._is_aglog_format(file_path, encoding)
        df = self._load_dataframe(file_path, encoding)
        columns = list(AGLOG_COLUMNS if use_aglog else df.columns)
        valid, msg = validate_csv_columns(columns)
        meta: Dict[str, Any] = {
            "encoding": encoding,
            "delimiter": delimiter,
            "columns": columns,
            "row_count": len(df),
            "valid": valid,
            "validation_message": msg,
            "date_start": None,
            "date_end": None,
            "suggested_filename": "",
            "format": "aglog" if use_aglog else "csv",
        }
        if not valid:
            return meta

        dates = []
        corrupt = 0
        for _, row in df.iterrows():
            try:
                dt = parse_datetime(str(row["DateTime"]))
                dates.append(dt.date())
            except (ValueError, KeyError):
                corrupt += 1

        if dates:
            meta["date_start"] = min(dates)
            meta["date_end"] = max(dates)
            meta["suggested_filename"] = suggest_filename(meta["date_start"], meta["date_end"])
        meta["corrupt_records"] = corrupt
        return meta

    def validate_file(self, file_path: Path) -> Tuple[bool, str, Dict[str, Any]]:
        """Full validation before import."""
        if not file_path.exists():
            return False, "File not found.", {}
        meta = self._analyze_file(file_path)
        if not meta["valid"]:
            return False, meta["validation_message"], meta
        if meta["row_count"] == 0:
            return False, "File is empty.", meta
        if meta.get("corrupt_records", 0) == meta["row_count"]:
            return False, "All records have invalid date/time format.", meta
        return True, "", meta

    def import_file(
        self,
        source_path: Path,
        target_filename: Optional[str] = None,
        replace_existing: bool = True,
    ) -> ImportResult:
        """Import cumulative CSV file into database."""
        result = ImportResult()
        valid, msg, meta = self.validate_file(source_path)
        if not valid:
            result.errors.append(msg)
            return result

        result.date_start = meta["date_start"]
        result.date_end = meta["date_end"]
        result.suggested_filename = meta["suggested_filename"]

        filename = sanitize_filename(target_filename or meta["suggested_filename"])
        dest_path = self.config.imports_dir / filename
        self.config.imports_dir.mkdir(parents=True, exist_ok=True)

        if self.config.get("data_management", "auto_archive_on_import", True):
            self.config.backup_database()

        encoding = meta["encoding"]
        df = self._load_dataframe(source_path, encoding)

        threshold_str = self.config.get("attendance", "late_threshold", "08:01:00")
        threshold = parse_time(threshold_str)
        working_days = self.config.get("attendance", "working_days", [0, 1, 2, 3, 4])
        holidays = [
            datetime.strptime(h, "%Y-%m-%d").date()
            for h in self.config.get("attendance", "holidays", [])
        ]

        daily_scans: Dict[Tuple[str, date], List[datetime]] = defaultdict(list)
        employee_names: Dict[str, str] = {}
        seen_keys: set = set()

        with self.db.connection() as conn:
            known_employees = {e["enno"] for e in self.db.get_all_employees(active_only=False, conn=conn)}

            for _, row in df.iterrows():
                try:
                    enno = normalize_enno(str(row["EnNo"]).strip())
                    name = str(row["Name"]).strip()
                    if not name or name.lower() in ("nan", "null", "none"):
                        name = f"Employee {enno}"
                    dt = parse_datetime(str(row["DateTime"]))
                    record_date = dt.date()

                    employee_names[enno] = name

                    dup_key = (enno, record_date.isoformat(), dt.strftime("%H:%M:%S"))
                    if dup_key in seen_keys:
                        result.records_skipped += 1
                        continue
                    seen_keys.add(dup_key)

                    if is_weekend(record_date, working_days) or record_date in holidays:
                        continue

                    if enno not in known_employees:
                        self.db.get_or_create_employee(enno, name, conn=conn)
                        known_employees.add(enno)
                        result.new_employees += 1

                    daily_scans[(enno, record_date)].append(dt)
                except (ValueError, KeyError) as exc:
                    result.warnings.append(f"Skipped corrupt record: {exc}")

            for (enno, record_date), scans in daily_scans.items():
                scans.sort()
                arrival = scans[0].time()
                departure = scans[-1].time() if len(scans) > 1 else None
                name = employee_names.get(enno, enno)
                emp_id = self.db.get_or_create_employee(enno, name, conn=conn)

                late_flag = is_late(arrival, threshold)
                late_mins = minutes_late(arrival, threshold)

                self.db.upsert_attendance(
                    emp_id, record_date, arrival, departure, late_flag, late_mins, filename, conn=conn
                )
                result.records_imported += 1

        if replace_existing and result.date_start and result.date_end:
            shutil.copy2(source_path, dest_path)

        retention = int(self.config.get("data_management", "retention_months", 12))
        cutoff = date.today() - timedelta(days=retention * 30)
        self.db.archive_old_records(cutoff)

        self.db.add_imported_file(
            filename,
            source_path.name,
            result.date_start,
            result.date_end,
            result.records_imported,
        )

        self._update_monthly_metrics(working_days, holidays)

        result.success = True
        logger.info(
            "Import complete: %d records, %d skipped",
            result.records_imported,
            result.records_skipped,
        )
        return result

    def _update_monthly_metrics(self, working_days: List[int], holidays: List[date]) -> None:
        """Recalculate monthly metrics for last 12 months."""
        today = date.today()
        current = today.replace(day=1)
        with self.db.connection() as conn:
            for _ in range(12):
                month_start = current
                if current.month == 12:
                    month_end = date(current.year, 12, 31)
                else:
                    month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
                if current.year == today.year and current.month == today.month:
                    month_end = today

                summaries = self.db.compute_employee_summary(month_start, month_end, working_days, holidays, conn=conn)
                if summaries:
                    avg_rate = sum(s["attendance_rate"] for s in summaries) / len(summaries)
                    late_total = sum(s["late_days"] for s in summaries)
                    rows = conn.execute(
                        """SELECT late_minutes FROM attendance_records
                           WHERE date BETWEEN ? AND ? AND is_late = 1""",
                        (month_start.isoformat(), month_end.isoformat()),
                    ).fetchall()
                    late_mins = [r["late_minutes"] for r in rows]
                    avg_late = sum(late_mins) / len(late_mins) if late_mins else 0
                    perfect = sum(1 for s in summaries if s["late_days"] == 0 and s["days_present"] > 0)
                    self.db.upsert_monthly_metrics(
                        current.year, current.month, avg_rate, late_total, avg_late, perfect, conn=conn
                    )

                if current.month == 1:
                    current = date(current.year - 1, 12, 1)
                else:
                    current = date(current.year, current.month - 1, 1)

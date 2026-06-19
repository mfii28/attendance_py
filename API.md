# Developer API Documentation

## Module Overview

### utils.py
Helper functions for encoding detection, datetime parsing, late calculation, and logging.

Key functions:
- `detect_encoding(file_path)` → str
- `parse_datetime(value)` → datetime
- `is_late(arrival, threshold)` → bool
- `minutes_late(arrival, threshold)` → int
- `working_days_in_range(start, end, working_days, holidays)` → int

### config.py
Settings management with JSON persistence.

```python
from config import Config
cfg = Config()
cfg.get("attendance", "late_threshold")  # "08:01:00"
cfg.set("attendance", "late_threshold", "08:30:00")
cfg.save()
cfg.backup_database()  # → Path
```

### database.py
SQLite wrapper with full schema.

```python
from database import Database
db = Database(Path("attendance.db"))

emp_id = db.get_or_create_employee("1001", "John Smith")
db.upsert_attendance(emp_id, date(2026,5,1), time(8,0), time(17,0), False, 0, "file.csv")
summary = db.compute_employee_summary(start, end, [0,1,2,3,4])
kpis = db.get_dashboard_kpis(start, end, [0,1,2,3,4])
```

### import_manager.py
CSV import with validation and duplicate detection.

```python
from import_manager import ImportManager
mgr = ImportManager(db, config)
valid, msg, meta = mgr.validate_file(Path("AGLog.csv"))
result = mgr.import_file(Path("AGLog.csv"), "AGLog_2026-05-01_to_2026-06-09.csv")
# result.success, result.records_imported, result.records_skipped
```

### name_manager.py
Display name management with audit trail.

```python
from name_manager import NameManager
nm = NameManager(db, config)
nm.update_name(emp_id, "John S.")
nm.export_mappings(Path("names.csv"))
nm.import_mappings(Path("names.csv"))
```

### report_generator.py
PDF and Excel report generation.

```python
from report_generator import ReportGenerator
rg = ReportGenerator(db, config)
paths = rg.generate("executive", start, end, "both", include_raw=True)
paths = rg.generate("leave_workbook", date(2026, 1, 1), date(2026, 12, 31), "excel")
```

### leave_manager.py
Leave rules, monthly grid data, name matching, and conflict detection.

```python
from leave_manager import LeaveManager
lm = LeaveManager(db, config)
grid = lm.get_month_grid(2026, 6)
lm.set_leave_code(emp_id, date(2026, 6, 15), "V")
totals = lm.compute_annual_leave_totals(emp_id, 2026)
emp_id = lm.match_employee_by_name("Patience Tsikudo")
```

### leave_importer.py
Import Leave Tracker Excel workbooks.

```python
from leave_importer import LeaveImporter
li = LeaveImporter(db, config)
meta, warnings = li.preview_file(Path("Leave Tracker 2026.xlsx"))
result = li.import_file(Path("Leave Tracker 2026.xlsx"), year=2026)
```

### charts.py
Matplotlib chart creation.

```python
from charts import create_trend_chart, create_offenders_chart, embed_chart
fig = create_trend_chart(metrics, dark=False)
canvas = embed_chart(tk_frame, fig)
```

## Database Schema

See `database.py` SCHEMA_SQL for full table definitions:
- `employees` — employee records with export/display names
- `attendance_records` — daily arrival/departure with late flags
- `imported_files` — import history tracking
- `name_changes` — audit log for name edits
- `monthly_metrics` — precomputed monthly statistics
- `leave_types` — absence code definitions and deduction weights
- `leave_entitlements` — per-employee annual allocation and carry-over
- `leave_records` — one code per employee per calendar day

## Error Handling

All modules use the centralized logger from `utils.setup_logging()`. Log files rotate daily with 30-day retention in `logs/attendance.log`.

## Testing

```bash
python -m unittest discover -s tests -v
```

Test files:
- `test_database.py` — schema, CRUD, summaries
- `test_import.py` — late threshold, weekend exclusion, CSV import
- `test_reports.py` — PDF and Excel generation
- `test_leave.py` — leave logic, import/export, attendance integration

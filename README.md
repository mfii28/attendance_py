# Attendance Management System

A Tkinter-based desktop application for managing employee attendance from cumulative CSV exports of attendance machines.

## Features

- **CSV Import**: Auto-detect encoding, date range, and new employees from tab-separated AGLog exports
- **Late Detection**: Configurable late threshold (default 08:01:00 AM)
- **Weekend Exclusion**: Automatically excludes weekends from working day calculations
- **12-Month Rolling History**: Archives data older than 12 months
- **Name Management**: Edit display names with full audit trail
- **Dashboard**: KPI cards, trend charts, top offenders, month-over-month comparison
- **Reports**: PDF and Excel exports (Executive Summary, Late Offenders, Perfect Attendance, Leave Tracker Workbook)
- **Cross-Platform**: Windows 10/11 and Linux Ubuntu 20.04+

## Quick Start

```bash
cd attendance_system
python -m venv venv

# Windows
venv\Scripts\activate
pip install -r requirements.txt
python main.py

# Linux
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Or use the launch scripts:
- Windows: `run.bat`
- Linux: `./run.sh`

## Sample Data

Import the sample file at `tests/sample_AGLog.csv` to test the system.

## Project Structure

```
attendance_system/
├── main.py              # GUI entry point
├── database.py          # SQLite operations
├── import_manager.py    # CSV import logic
├── leave_manager.py     # Leave tracking rules and grid data
├── leave_importer.py    # Leave Tracker Excel import
├── name_manager.py      # Employee name management
├── report_generator.py  # PDF/Excel generation
├── charts.py            # Matplotlib charts
├── config.py            # Settings management
├── utils.py             # Helper functions
├── tests/               # Unit tests
└── assets/              # Icons and logos
```

## Running Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT License

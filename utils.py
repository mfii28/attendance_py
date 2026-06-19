"""Helper functions for the Attendance Management System."""

import logging
import platform
import re
import sys
from datetime import date, datetime, time, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import List, Optional, Tuple

import chardet

APP_NAME = "AttendanceSystem"


def _resolve_base_dir() -> Path:
    """Writable app folder; when frozen (PyInstaller) use user config dir."""
    if getattr(sys, "frozen", False):
        return get_app_data_dir()
    return Path(__file__).resolve().parent


def get_app_data_dir() -> Path:
    """Return platform-specific application data directory."""
    system = platform.system()
    if system == "Windows":
        base = Path.home() / "AppData" / "Local" / APP_NAME
    else:
        base = Path.home() / ".config" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


BASE_DIR = _resolve_base_dir()


def setup_logging(log_dir: Optional[Path] = None) -> logging.Logger:
    """Configure rotating file logger (30-day retention)."""
    log_dir = log_dir or (BASE_DIR / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "attendance.log"

    logger = logging.getLogger(APP_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    handler = TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger


logger = setup_logging()


def detect_encoding(file_path: Path) -> str:
    """Detect file encoding using chardet with fallbacks."""
    raw = file_path.read_bytes()
    result = chardet.detect(raw)
    encoding = result.get("encoding") or "utf-8"
    for candidate in (encoding, "utf-8-sig", "utf-8", "latin-1"):
        try:
            raw.decode(candidate)
            return candidate
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1"


def parse_datetime(value: str) -> datetime:
    """Parse DateTime from attendance machine format YYYY/MM/DD HH:MM:SS."""
    value = re.sub(r"\s+", " ", str(value).strip())
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid datetime format: {value}")


def parse_time(value: str) -> time:
    """Parse time string HH:MM:SS or HH:MM."""
    value = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time format: {value}")


def format_time(t: Optional[time]) -> str:
    """Format time for display."""
    if t is None:
        return "-"
    return t.strftime("%H:%M:%S")


def format_date(d: Optional[date]) -> str:
    """Format date for display."""
    if d is None:
        return "-"
    return d.strftime("%Y-%m-%d")


def is_weekend(d: date, working_days: Optional[List[int]] = None) -> bool:
    """Return True if date is not a working day (weekday 0=Mon .. 6=Sun)."""
    working_days = working_days or [0, 1, 2, 3, 4]
    return d.weekday() not in working_days


def working_days_in_range(
    start: date, end: date, working_days: Optional[List[int]] = None, holidays: Optional[List[date]] = None
) -> int:
    """Count working days between start and end inclusive."""
    holidays = set(holidays or [])
    count = 0
    current = start
    while current <= end:
        if not is_weekend(current, working_days) and current not in holidays:
            count += 1
        current += timedelta(days=1)
    return count


def suggest_filename(start: date, end: date) -> str:
    """Generate suggested import filename."""
    return f"AGLog_{start.strftime('%Y-%m-%d')}_to_{end.strftime('%Y-%m-%d')}.csv"


def normalize_enno(enno: str) -> str:
    """Strip redundant leading zeros: 000000020 -> 20."""
    s = str(enno).strip()
    if s.isdigit():
        return str(int(s))
    return s


def effective_display_name(employee: dict) -> str:
    """Return custom display name when set, otherwise the machine export name."""
    custom = (employee.get("display_name") or "").strip()
    if custom:
        return custom
    return (employee.get("export_name") or "").strip()


def auto_capitalize(name: str) -> str:
    """Title-case employee name."""
    return " ".join(part.capitalize() for part in name.split())


def time_to_minutes(t: time) -> int:
    """Convert time to minutes since midnight."""
    return t.hour * 60 + t.minute + (1 if t.second > 0 else 0)


def minutes_late(arrival: time, threshold: time) -> int:
    """Calculate minutes late; 0 if on time or early."""
    if not is_late(arrival, threshold):
        return 0
    arr = arrival.hour * 3600 + arrival.minute * 60 + arrival.second
    thr = threshold.hour * 3600 + threshold.minute * 60 + threshold.second
    return (arr - thr) // 60


def is_late(arrival: time, threshold: time) -> bool:
    """Return True if arrival is at or after threshold."""
    arr = arrival.hour * 3600 + arrival.minute * 60 + arrival.second
    thr = threshold.hour * 3600 + threshold.minute * 60 + threshold.second
    return arr >= thr


def validate_csv_columns(columns: List[str]) -> Tuple[bool, str]:
    """Validate minimum required columns exist."""
    required = {"EnNo", "Name", "DateTime"}
    normalized = {c.strip() for c in columns if c and not str(c).startswith("Unnamed")}
    missing = required - normalized
    if missing:
        return False, f"Missing required columns: {', '.join(sorted(missing))}"
    return True, ""


AGLOG_COLUMNS = ["No", "Mchn", "EnNo", "Name", "Mode", "IOMd", "DateTime"]


def sanitize_filename(name: str) -> str:
    """Remove invalid filename characters."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def pct_change(current: float, previous: float) -> Optional[float]:
    """Calculate percentage change; None if previous is zero."""
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def trend_indicator(current: float, previous: float, higher_is_better: bool = True) -> str:
    """Return trend arrow based on comparison."""
    if current > previous:
        return "↑" if higher_is_better else "↓"
    if current < previous:
        return "↓" if higher_is_better else "↑"
    return "→"

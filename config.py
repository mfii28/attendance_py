"""Settings management for the Attendance Management System."""

import json
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils import BASE_DIR, get_app_data_dir, logger

DEFAULT_CONFIG: Dict[str, Any] = {
    "attendance": {
        "late_threshold": "08:01:00",
        "working_days": [0, 1, 2, 3, 4],
        "exclude_weekends": True,
        "holidays": [],
    },
    "data_management": {
        "retention_months": 12,
        "auto_archive_on_import": True,
        "backup_reminder_days": 7,
    },
    "display": {
        "theme": "system",
        "font_size": 12,
        "date_format": "%Y-%m-%d",
    },
    "name_management": {
        "auto_capitalize": True,
        "new_employee_default": "active",
        "display_name_format": "title",
    },
    "leave": {
        "default_annual_allocation": 0,
        "excused_codes": ["V", "S", "M", "C", "H", "H1", "H2", "Q", "I"],
        "year": 2026,
        "deduction_weights": {
            "H": {"weight": 1.0, "desc": "Holiday"},
            "H1": {"weight": 0.5, "desc": "Half Day AM"},
            "H2": {"weight": 0.5, "desc": "Half Day PM"},
            "Q": {"weight": 0.25, "desc": "Quarter Day"},
            "V": {"weight": 1.0, "desc": "Vacation"},
            "S": {"weight": 1.0, "desc": "Sickness"},
            "M": {"weight": 1.0, "desc": "Maternity/Paternity"},
            "C": {"weight": 1.0, "desc": "Compassionate"},
            "A": {"weight": 1.0, "desc": "Absent / No Show"},
            "I": {"weight": 1.0, "desc": "Inactive"},
        }
    },
    "export": {
        "default_format": "pdf",
        "use_custom_export_dir": False,
        "custom_export_dir": "",
        "include_logo_in_pdf": True,
        "smtp_enabled": False,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "",
        "smtp_to": "",
    },
    "database": {
        "path": str(BASE_DIR / "attendance.db"),
        "backup_dir": str(BASE_DIR / "backups"),
        "max_backups": 5,
    },
    "paths": {
        "imports": str(BASE_DIR / "imports"),
        "exports": str(BASE_DIR / "exports"),
        "archives": str(BASE_DIR / "archives"),
        "logs": str(BASE_DIR / "logs"),
        "assets": str(BASE_DIR / "assets"),
    },
}


class Config:
    """Load, save, and access application settings."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (get_app_data_dir() / "config.json")
        self._data = deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """Load config from disk or create defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._merge_defaults(stored)
                logger.info("Configuration loaded from %s", self.config_path)
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to load config: %s", exc)
        else:
            self.save()

    def save(self) -> None:
        """Persist config to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        logger.info("Configuration saved to %s", self.config_path)

    def _merge_defaults(self, stored: Dict[str, Any]) -> None:
        """Deep-merge stored values into defaults."""
        for section, values in stored.items():
            if section not in self._data:
                self._data[section] = values
            elif isinstance(values, dict):
                self._data[section].update(values)
            else:
                self._data[section] = values

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a config value."""
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        """Set a config value."""
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value

    def get_section(self, section: str) -> Dict[str, Any]:
        """Return entire config section."""
        return deepcopy(self._data.get(section, {}))

    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        """Update multiple keys in a section."""
        if section not in self._data:
            self._data[section] = {}
        self._data[section].update(values)

    @property
    def db_path(self) -> Path:
        return Path(self.get("database", "path", DEFAULT_CONFIG["database"]["path"]))

    @property
    def backup_dir(self) -> Path:
        return Path(self.get("database", "backup_dir", DEFAULT_CONFIG["database"]["backup_dir"]))

    @property
    def imports_dir(self) -> Path:
        return Path(self.get("paths", "imports", DEFAULT_CONFIG["paths"]["imports"]))

    @property
    def exports_dir(self) -> Path:
        return Path(self.get("paths", "exports", DEFAULT_CONFIG["paths"]["exports"]))

    def get_export_dir(self) -> Path:
        """Return active export directory (default or custom)."""
        if self.get("export", "use_custom_export_dir", False):
            custom = self.get("export", "custom_export_dir", "")
            if custom:
                path = Path(custom)
                path.mkdir(parents=True, exist_ok=True)
                return path
        path = self.exports_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def archives_dir(self) -> Path:
        return Path(self.get("paths", "archives", DEFAULT_CONFIG["paths"]["archives"]))

    @property
    def assets_dir(self) -> Path:
        return Path(self.get("paths", "assets", DEFAULT_CONFIG["paths"]["assets"]))

    def ensure_directories(self) -> None:
        """Create all required directories."""
        for path in (
            self.imports_dir,
            self.exports_dir,
            self.archives_dir,
            self.backup_dir,
            Path(self.get("paths", "logs", DEFAULT_CONFIG["paths"]["logs"])),
            self.assets_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def backup_database(self) -> Optional[Path]:
        """Create timestamped database backup, keep last N."""
        db = self.db_path
        if not db.exists():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"attendance_backup_{stamp}.db"
        shutil.copy2(db, dest)
        logger.info("Database backed up to %s", dest)

        backups = sorted(self.backup_dir.glob("attendance_backup_*.db"), reverse=True)
        max_backups = int(self.get("database", "max_backups", 5))
        for old in backups[max_backups:]:
            old.unlink(missing_ok=True)
        return dest

    def restore_database(self, backup_path: Path) -> None:
        """Restore database from backup file."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        self.backup_database()
        shutil.copy2(backup_path, self.db_path)
        logger.info("Database restored from %s", backup_path)

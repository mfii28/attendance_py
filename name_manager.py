"""Employee name management."""

import csv
from pathlib import Path
from typing import Dict, List, Optional

from config import Config
from database import Database
from utils import auto_capitalize, logger


class NameManager:
    """Manage employee display names with audit trail."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    def get_all(self, search: str = "") -> List[Dict]:
        if search:
            return self.db.search_employees(search)
        return self.db.get_all_employees(active_only=False)

    def update_name(self, employee_id: int, new_name: str, changed_by: str = "user") -> None:
        if self.config.get("name_management", "auto_capitalize", True):
            new_name = auto_capitalize(new_name)
        self.db.update_display_name(employee_id, new_name, changed_by)

    def bulk_update(self, updates: List[tuple], changed_by: str = "user") -> int:
        processed = []
        for emp_id, name in updates:
            if self.config.get("name_management", "auto_capitalize", True):
                name = auto_capitalize(name)
            processed.append((emp_id, name))
        return self.db.bulk_update_display_names(processed, changed_by)

    def reset_to_export_name(self, employee_id: int) -> None:
        self.db.reset_display_name(employee_id)

    def export_mappings(self, file_path: Path) -> int:
        employees = self.db.get_all_employees(active_only=False)
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["EnNo", "Export Name", "Display Name", "Department", "Active"])
            for emp in employees:
                writer.writerow([
                    emp["enno"],
                    emp["export_name"],
                    emp["display_name"],
                    emp.get("department") or "",
                    emp["is_active"],
                ])
        logger.info("Exported %d name mappings to %s", len(employees), file_path)
        return len(employees)

    def import_mappings(self, file_path: Path, changed_by: str = "import") -> int:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        count = 0
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                enno = row.get("EnNo", "").strip()
                display_name = row.get("Display Name", "").strip()
                if not enno or not display_name:
                    continue
                emp = self.db.get_employee_by_enno(enno)
                if emp:
                    self.update_name(emp["id"], display_name, changed_by)
                    count += 1
        logger.info("Imported %d name mappings from %s", count, file_path)
        return count

    def get_audit_log(self, employee_id: Optional[int] = None) -> List[Dict]:
        return self.db.get_name_changes(employee_id)

"""Leave tracking business logic for the Attendance Management System."""

import calendar
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from config import Config
from database import Database
from utils import effective_display_name, logger

DEDUCTION_WEIGHTS: Dict[str, float] = {
    "H": 1.0,
    "H1": 0.5,
    "H2": 0.5,
    "Q": 0.25,
    "V": 1.0,
    "S": 1.0,
    "M": 1.0,
    "C": 1.0,
    "A": 1.0,
    "I": 1.0,
}

LEAVE_TYPE_ORDER = ["H", "H1", "H2", "Q", "I", "S", "M", "C", "V", "A"]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

MONTH_ABBREV = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

DAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def normalize_name(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def get_weights_dict(config: Optional[Config]) -> Dict[str, float]:
    if not config:
        return DEDUCTION_WEIGHTS
    raw = config.get("leave", "deduction_weights", {})
    if not raw:
        return DEDUCTION_WEIGHTS
    weights = {}
    for code, data in raw.items():
        if isinstance(data, dict):
            weights[code] = float(data.get("weight", 1.0))
        elif isinstance(data, (list, tuple)):
            weights[code] = float(data[0])
        else:
            weights[code] = float(data)
    return weights


def is_valid_leave_code(code: str, config: Optional[Config] = None) -> bool:
    weights = get_weights_dict(config)
    return str(code).upper().strip() in weights


def monthly_absences(codes: List[str], config: Optional[Config] = None) -> float:
    weights = get_weights_dict(config)
    total = 0.0
    for code in codes:
        c = str(code).upper().strip()
        if c in weights:
            total += weights[c]
    return total


def count_codes_by_type(codes: List[str], config: Optional[Config] = None) -> Dict[str, int]:
    weights = get_weights_dict(config)
    counts = {code: 0 for code in weights.keys()}
    for code in codes:
        c = str(code).upper().strip()
        if c in counts:
            counts[c] += 1
    return counts


def annual_balance(
    allocation: float, carry_over: float, monthly_totals: List[float]
) -> Dict[str, float]:
    entitlement = allocation + carry_over
    used = sum(monthly_totals)
    return {
        "entitlement": entitlement,
        "used": used,
        "balance": entitlement - used,
    }


def month_date_range(year: int, month: int) -> Tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def day_column_index(day: int) -> int:
    """Excel column offset: day 1 -> column C (index 3)."""
    return day + 2


def day_from_column(col_index: int) -> Optional[int]:
    day = col_index - 2
    if 1 <= day <= 31:
        return day
    return None


class LeaveManager:
    """High-level leave operations."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    def get_weights(self) -> Dict[str, float]:
        return get_weights_dict(self.config)

    def is_valid_leave_code(self, code: str) -> bool:
        return is_valid_leave_code(code, self.config)

    def get_code_details(self) -> Dict[str, Dict[str, Any]]:
        raw = self.config.get("leave", "deduction_weights", {})
        if not raw:
            return {code: {"weight": w, "desc": ""} for code, w in DEDUCTION_WEIGHTS.items()}
        details = {}
        for code, data in raw.items():
            if isinstance(data, dict):
                details[code] = {
                    "weight": float(data.get("weight", 1.0)),
                    "desc": str(data.get("desc", ""))
                }
            elif isinstance(data, (list, tuple)):
                details[code] = {
                    "weight": float(data[0]),
                    "desc": str(data[1]) if len(data) > 1 else ""
                }
            else:
                details[code] = {
                    "weight": float(data),
                    "desc": ""
                }
        return details

    def get_excused_codes(self) -> List[str]:
        return self.config.get("leave", "excused_codes", list(self.get_weights().keys()))

    def match_employee_by_name(self, name: str) -> Optional[int]:
        normalized = normalize_name(name)
        if not normalized:
            return None
        for emp in self.db.get_all_employees(active_only=False):
            for field in ("export_name", "display_name"):
                value = emp.get(field)
                if value and normalize_name(value) == normalized:
                    return emp["id"]
        return None

    def compute_monthly_deduction(self, employee_id: int, year: int, month: int) -> float:
        start, end = month_date_range(year, month)
        records = self.db.get_leave_for_employee(employee_id, start, end)
        return monthly_absences([r["code"] for r in records], self.config)

    def compute_annual_leave_totals(self, employee_id: int, year: int) -> Dict[str, Any]:
        entitlement = self.db.get_entitlement(employee_id, year)
        monthly_totals: List[float] = []
        all_codes: List[str] = []
        for month in range(1, 13):
            start, end = month_date_range(year, month)
            records = self.db.get_leave_for_employee(employee_id, start, end)
            codes = [r["code"] for r in records]
            all_codes.extend(codes)
            monthly_totals.append(monthly_absences(codes, self.config))
        balance = annual_balance(
            entitlement["annual_allocation"],
            entitlement["carry_over"],
            monthly_totals,
        )
        return {
            **entitlement,
            **balance,
            "code_counts": count_codes_by_type(all_codes, self.config),
            "monthly_totals": monthly_totals,
        }

    def get_month_grid(self, year: int, month: int) -> Dict[str, Any]:
        """Return month calendar metadata and per-employee day codes."""
        start, end = month_date_range(year, month)
        days_in_month = end.day
        employees = self.db.get_all_employees(active_only=True)
        leave_rows = self.db.get_leave_for_month(year, month)
        by_emp_day: Dict[int, Dict[int, str]] = {}
        for row in leave_rows:
            emp_id = row["employee_id"]
            day_num = int(row["date"].split("-")[2])
            by_emp_day.setdefault(emp_id, {})[day_num] = row["code"]

        grid = []
        for i, emp in enumerate(employees, 1):
            emp_days = by_emp_day.get(emp["id"], {})
            deduction = monthly_absences(list(emp_days.values()), self.config)
            grid.append({
                "num": i,
                "employee_id": emp["id"],
                "enno": emp["enno"],
                "export_name": emp["export_name"],
                "display_name": effective_display_name(emp),
                "days": emp_days,
                "monthly_deduction": deduction,
            })
        return {
            "year": year,
            "month": month,
            "month_name": MONTH_NAMES[month - 1],
            "days_in_month": days_in_month,
            "employees": grid,
        }

    def set_leave_code(
        self, employee_id: int, record_date: date, code: Optional[str]
    ) -> None:
        if code is None or code == "":
            self.db.delete_leave_record(employee_id, record_date)
            return
        if not is_valid_leave_code(code, self.config):
            raise ValueError(f"Invalid leave code: {code}")
        self.db.upsert_leave_record(employee_id, record_date, code)

    def get_conflicts(self, employee_id: int, record_date: date) -> List[str]:
        conflicts: List[str] = []
        leave = self.db.get_leave_on_date(employee_id, record_date)
        has_attendance = self.db.has_attendance_on_date(employee_id, record_date)
        if leave and has_attendance:
            if leave["code"] in ("V", "S", "M", "C", "H", "I"):
                conflicts.append(
                    f"Leave ({leave['code']}) recorded but attendance punch exists"
                )
        if has_attendance and not leave:
            pass
        if leave and leave["code"] == "A" and has_attendance:
            conflicts.append("Marked absent/no show but attendance punch exists")
        return conflicts

    def get_all_conflicts_in_range(
        self, start: date, end: date
    ) -> List[Dict[str, Any]]:
        results = []
        current = start
        while current <= end:
            for emp in self.db.get_all_employees(active_only=True):
                msgs = self.get_conflicts(emp["id"], current)
                if msgs:
                    results.append({
                        "employee_id": emp["id"],
                        "display_name": effective_display_name(emp),
                        "enno": emp["enno"],
                        "date": current.isoformat(),
                        "messages": msgs,
                    })
            current = date.fromordinal(current.toordinal() + 1)
        return results

    def ensure_default_entitlement(self, employee_id: int, year: int) -> None:
        ent = self.db.get_entitlement(employee_id, year)
        if ent.get("annual_allocation", 0) == 0 and ent.get("carry_over", 0) == 0:
            default_alloc = float(
                self.config.get("leave", "default_annual_allocation", 0)
            )
            if default_alloc:
                self.db.set_entitlement(employee_id, year, default_alloc, 0.0)

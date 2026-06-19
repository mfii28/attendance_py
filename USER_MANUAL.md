# User Manual

## Getting Started

1. Launch the application using `run.bat` (Windows) or `./run.sh` (Linux)
2. Go to **File Manager** tab and click **Import New File**
3. Select your cumulative AGLog CSV export from the attendance machine
4. Review the preview and click **Import**

## Tabs Overview

### Dashboard
View KPI cards (active employees, attendance rate, working days), 12-month trend chart, top late offenders (click a bar for employee details), and period comparison vs the previous equal-length period.

### Attendance Register
Sortable table of all employees with attendance metrics. Use the search box and date range filters. Double-click a row for daily attendance details. Color coding: green (≥90%), yellow (75-89%), red (<75%). The **Excused Leave** column shows weekdays covered by approved leave codes (vacation, sickness, etc.) that are not counted as unexcused absences.

### Leave Tracker
Track annual leave and absences in a calendar grid matching the **Leave Tracker** Excel workbook.

- Select **year** and **month**, then use the grid to view or edit leave codes per employee per day
- **Double-click** a day cell to set a code (V, S, H, H1, H2, Q, M, C, A, I) or clear it
- Rows with data conflicts (e.g. vacation recorded but attendance punch exists) are highlighted in red
- The right panel shows annual allocation, carry-over, entitlement, used days, balance, and per-code counts
- **Import Excel** loads an existing `Leave Tracker YYYY.xlsx` (File → Import Leave Tracker Excel…)
- **Export Excel** generates a full 13-sheet workbook (12 months + Totals)

Employees must already exist in the database (from attendance CSV import). Names are matched to **export name**; the grid displays **display name** when set.

### File Manager
View imported files, active file status, and database health statistics. Import new cumulative CSV files here.

**Export Location:** Choose the default `exports/` folder or set a custom export directory. Use **Open Export Folder** to view saved reports.

### Reports
Configure and generate reports:
- **Executive Summary**: Full overview with KPIs and employee table
- **Late Offenders**: Employees with late arrivals
- **Perfect Attendance**: Employees with zero late days
- **Leave Tracker Workbook**: Full-year leave Excel export (12 monthly sheets + Totals)
- **Custom**: Configurable date range and options

Choose PDF, Excel, HTML, or both. When generating a report, confirm the export folder or pick a one-off location.

### Settings
- **Attendance**: Late threshold, working days
- **Display**: Theme, font size
- **Name Management**: Edit display names, import/export CSV mappings
- **Database**: Backup, restore, compact

## Name Management

The system stores two names per employee:
- **Export Name**: From the attendance machine (read-only from imports)
- **Display Name**: User-editable name shown in reports

Double-click a name in Settings → Name Management to edit. All changes are logged in the audit trail.

## Late Threshold

Default: 08:01:00 AM. Employees arriving at or before 08:00:59 are on time. Arrivals at 08:01:00 or later are marked late.

## Working Days

Monday through Friday by default. Weekends are excluded from attendance rate calculations. Configure working days in Settings → Attendance.

## Backup & Restore

Before each import, an automatic backup is created (if enabled). Manual backups available in Settings → Database. Last 5 backups are retained.

## File Format

Expected CSV format (tab-separated):
```
No  Mchn  EnNo  Name  Mode  IOMd  DateTime
1   1     1001  John  1     0     2026/05/01 07:55:00
```

DateTime format: `YYYY/MM/DD HH:MM:SS`

Employee IDs are stored without redundant leading zeros (e.g. `000000020` becomes `20`).

## Leave Codes

| Code | Meaning | Deduction |
|------|---------|-----------|
| H | Holiday | 1.0 day |
| H1 | Half day (morning) | 0.5 |
| H2 | Half day (afternoon) | 0.5 |
| Q | Quarter day | 0.25 |
| V | Vacation | 1.0 |
| S | Sickness | 1.0 |
| M | Maternity/Paternity | 1.0 |
| C | Compassionate | 1.0 |
| A | Absent/No show | 1.0 |
| I | Inactive | 1.0 |

Monthly **used** totals use weighted deductions. Annual **balance** = (allocation + carry-over) − sum of monthly weighted totals.

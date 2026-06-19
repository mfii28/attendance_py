# Checklist - Spacing, Legend Removal, and Leave Settings

- [x] Remove day names from calendar header:
  - [x] Format headers to show only the date number (e.g., `1`, `2`, `3`)
- [x] Spacing & Layout adjustments:
  - [x] Increase `pady` top/bottom on toolbars and main container frames to `10` or `12`
  - [x] Increase KPI card vertical paddings for a more spacious, premium feel
- [x] Remove Legend sidebar from Leave Monthly Grid:
  - [x] Delete `legend_frame` and its contents
  - [x] Configure `tab_grid` to let `grid_frame` span 100% width
- [x] Implement Dynamic Leave Codes Settings:
  - [x] Update `DEFAULT_CONFIG` in `config.py` with default weights and descriptions
  - [x] Update `leave_manager.py` methods (`get_weights`, `monthly_absences`, `is_valid_leave_code`, `count_codes_by_type`) to use configuration
  - [x] Decouple `leave_importer.py` from static `DEDUCTION_WEIGHTS`
  - [x] Add the `"Leave Codes"` management sub-tab in Settings with a Treeview grid and sidebar form
- [x] Improve Gridlines Visibility:
  - [x] Increase `border_color` contrast in Treeview styles
- [x] Verification:
  - [x] Launch application via `run.bat` or `python main.py`
  - [x] Confirm scaling, font sizes, and input borders render correctly

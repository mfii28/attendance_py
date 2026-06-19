"""Application entry point - Modernized CustomTkinter Attendance Management System GUI."""

import os
import platform
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional
import calendar

import customtkinter as ctk

from charts import (
    close_figure,
    create_offenders_chart,
    create_trend_chart,
    embed_chart,
    set_chart_font_size,
)
from config import Config
from database import Database
from import_manager import ImportManager
from leave_importer import LeaveImporter
from leave_manager import MONTH_NAMES, LeaveManager
from name_manager import NameManager
from report_generator import ReportGenerator
from ui_helpers import auto_fit_columns, configure_tree_columns, open_folder
from utils import (
    effective_display_name,
    format_date,
    logger,
    normalize_enno,
    pct_change,
    trend_indicator,
)

# Try to set Windows Process DPI Awareness for sharp rendering on high-res screens
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # 2 = PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Set base appearance mode and theme
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class AttendanceApp(ctk.CTk):
    """Main application window using CustomTkinter with enhanced scaling and visibility."""

    def _safe_grab_set(self, window) -> None:
        """Safely set grab on a window, avoiding TclError if it is not yet viewable."""
        window.deiconify()
        window.update_idletasks()
        try:
            window.grab_set()
        except tk.TclError:
            pass

    def __init__(self):
        super().__init__()
        
        # Initialize configurations & databases
        self.config_mgr = Config()
        font_size = int(self.config_mgr.get("display", "font_size", 12))
        if font_size < 12:
            font_size = 12
            self.config_mgr.set("display", "font_size", 12)
            self.config_mgr.save()
        self.config_mgr.ensure_directories()
        self.db = Database(self.config_mgr.db_path)
        self.import_mgr = ImportManager(self.db, self.config_mgr)
        self.leave_mgr = LeaveManager(self.db, self.config_mgr)
        self.leave_importer = LeaveImporter(self.db, self.config_mgr)
        self.name_mgr = NameManager(self.db, self.config_mgr)
        self.report_gen = ReportGenerator(self.db, self.config_mgr)

        # Set appearance mode from config
        self._theme_config = self.config_mgr.get("display", "theme", "system").lower()
        ctk.set_appearance_mode(self._theme_config)

        self._sort_reverse: Dict[str, bool] = {}
        self._dashboard_offenders: List[Dict] = []
        self._dashboard_range: tuple = (date.today().replace(day=1), date.today())
        self._last_leave_row: Optional[str] = None
        self._last_leave_col: Optional[str] = None
        self._active_combo: Optional[ttk.Combobox] = None

        # Build UI styles and fonts
        self._setup_styles()
        
        # Scale window geometry using CustomTkinter native scaling
        scale_factor = font_size / 12.0
        self._scale_factor = scale_factor
        
        # Apply CustomTkinter native widget and window scaling
        ctk.set_widget_scaling(scale_factor)
        ctk.set_window_scaling(scale_factor)
        
        self.title("Attendance Management System")
        self.geometry("1400x900")
        self.minsize(1024, 768)

        # Build menus and notebooks
        self._build_menu()
        self._build_notebook()
        
        # Trigger dynamic theme styling configuration
        self.update_idletasks()
        self._update_treeview_styles()
        self._refresh_all()

    def _setup_styles(self) -> None:
        """Configure fonts and treeview themes."""
        font_size = int(self.config_mgr.get("display", "font_size", 12))
        self._font_size = font_size
        self._font = ("Segoe UI", font_size)
        self._font_bold = ("Segoe UI", font_size, "bold")
        
        # Measure actual DPI-scaled font linespace to prevent text clipping/overlap
        import tkinter.font as tkfont
        try:
            font_obj = tkfont.Font(family="Segoe UI", size=font_size)
            font_linespace = font_obj.metrics("linespace")
        except Exception:
            font_linespace = int(font_size * 1.7)
            
        # Dynamically set row height with comfortable vertical spacing (padding)
        # Adding 12 pixels of padding (6px top, 6px bottom) for high legibility
        self._row_height = max(28, font_linespace + 12)

        # Create CustomTkinter Fonts (unscaled base sizes, CTk scales them natively)
        self._ctk_font = ctk.CTkFont(family="Segoe UI", size=12)
        self._ctk_font_bold = ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        self._ctk_font_large = ctk.CTkFont(family="Segoe UI", size=16, weight="bold")
        self._ctk_font_value = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")

        set_chart_font_size(font_size)

        # Apply fallback options for standard dialogs
        self.option_add("*Font", self._font)
        self.option_add("*Menu.font", self._font)
        self.option_add("*Toplevel*Font", self._font)

    def _update_treeview_styles(self) -> None:
        """Update standard Tkinter widgets to match CustomTkinter theme palette with high contrast."""
        style = ttk.Style()
        style.theme_use("clam")

        # Determine actual background and text colors based on current mode
        mode = ctk.get_appearance_mode().lower()
        self._dark_mode = (mode == "dark")
        
        if self._dark_mode:
            bg_color = "#2a2a2a"        # CTk dark frame color
            fg_color = "#ffffff"
            field_bg = "#1e1e1e"        # Inset dark textbox color for contrast
            heading_bg = "#1f1f1f"
            heading_fg = "#ffffff"
            select_bg = "#1f538d"       # Default blue accent
            select_fg = "#ffffff"
            border_color = "#444444"    # Subtle dark gray cell borders
        else:
            bg_color = "#ffffff"
            fg_color = "#000000"
            field_bg = "#ffffff"
            heading_bg = "#eaeaea"
            heading_fg = "#000000"
            select_bg = "#3a7ebf"       # Default light blue selection
            select_fg = "#ffffff"
            border_color = "#D0D0D0"    # Light gray borders (#D0D0D0)

        # Apply configuration styles to Treeviews, enabling visible gridlines via gridcolor
        style.configure("Treeview",
                        background=bg_color,
                        foreground=fg_color,
                        fieldbackground=field_bg,
                        font=self._font,
                        rowheight=self._row_height,
                        bordercolor=border_color,
                        gridcolor=border_color, # Visible spreadsheet-like gridlines
                        borderwidth=1)
        
        # Determine heading padding dynamically based on font size
        import tkinter.font as tkfont
        try:
            font_obj_bold = tkfont.Font(family="Segoe UI", size=self._font_size, weight="bold")
            bold_linespace = font_obj_bold.metrics("linespace")
        except Exception:
            bold_linespace = int(self._font_size * 1.7)
            
        heading_padding_y = max(6, int(bold_linespace * 0.3))
        heading_padding_x = max(10, int(bold_linespace * 0.5))

        style.configure("Treeview.Heading",
                        background=heading_bg,
                        foreground=heading_fg,
                        font=self._font_bold,
                        bordercolor=border_color,
                        borderwidth=1,
                        padding=(heading_padding_x, heading_padding_y))

        style.map("Treeview",
                  background=[("selected", select_bg)],
                  foreground=[("selected", select_fg)])

        # Style standard Spinbox and Combobox inputs for consistent look & border lines
        style.configure("TSpinbox",
                        arrowcolor=fg_color,
                        background=bg_color,
                        foreground=fg_color,
                        fieldbackground=field_bg,
                        bordercolor=border_color,
                        lightcolor=border_color,
                        darkcolor=border_color,
                        font=self._font)
        
        style.configure("TCombobox",
                        arrowcolor=fg_color,
                        background=bg_color,
                        foreground=fg_color,
                        fieldbackground=field_bg,
                        bordercolor=border_color,
                        lightcolor=border_color,
                        darkcolor=border_color,
                        font=self._font)

        # Update Treeview tags based on color mode readability with high text contrast
        trees_to_tag = []
        for name in ["register_tree", "leave_tree_left", "leave_tree", "leave_totals_tree"]:
            t = getattr(self, name, None)
            if t:
                trees_to_tag.append(t)
                
        for tree in trees_to_tag:
            if self._dark_mode:
                # Use clean foreground colors to preserve underlying grid lines
                tree.tag_configure("green", foreground="#81C784")
                tree.tag_configure("yellow", foreground="#FFF176")
                tree.tag_configure("red", foreground="#E57373")
                tree.tag_configure("conflict", foreground="#E57373")
            else:
                tree.tag_configure("green", foreground="#2E7D32")
                tree.tag_configure("yellow", foreground="#F57F17")
                tree.tag_configure("red", foreground="#C62828")
                tree.tag_configure("conflict", foreground="#C62828")

    def on_leave_y_scroll(self, *args) -> None:
        if hasattr(self, "leave_tree_left") and hasattr(self, "leave_tree"):
            self.leave_tree_left.yview(*args)
            self.leave_tree.yview(*args)

    def on_leave_left_mousewheel(self, event) -> str:
        if hasattr(self, "leave_tree_left") and hasattr(self, "leave_tree"):
            self.leave_tree.yview_scroll(int(-1*(event.delta/120)), "units")
            self.leave_tree_left.yview_scroll(int(-1*(event.delta/120)), "units")
        return "break"

    def on_leave_right_mousewheel(self, event) -> str:
        if hasattr(self, "leave_tree_left") and hasattr(self, "leave_tree"):
            self.leave_tree_left.yview_scroll(int(-1*(event.delta/120)), "units")
            self.leave_tree.yview_scroll(int(-1*(event.delta/120)), "units")
        return "break"

    def sync_leave_left_to_right(self, event) -> None:
        if getattr(self, "_syncing_leave_selection", False):
            return
        self._syncing_leave_selection = True
        try:
            if hasattr(self, "leave_tree_left") and hasattr(self, "leave_tree"):
                selection = self.leave_tree_left.selection()
                self.leave_tree.selection_set(selection)
        finally:
            self._syncing_leave_selection = False
        self._show_leave_employee_detail("grid")

    def sync_leave_right_to_left(self, event) -> None:
        if getattr(self, "_syncing_leave_selection", False):
            return
        self._syncing_leave_selection = True
        try:
            if hasattr(self, "leave_tree_left") and hasattr(self, "leave_tree"):
                selection = self.leave_tree.selection()
                self.leave_tree_left.selection_set(selection)
        finally:
            self._syncing_leave_selection = False
        self._show_leave_employee_detail("grid")



    def _build_menu(self) -> None:
        """Create standard application menu."""
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Import CSV...", command=self._show_import_dialog)
        file_menu.add_command(label="Import Leave Tracker Excel...", command=self._show_leave_import_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Backup Database", command=self._backup_db)
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

    def _build_notebook(self) -> None:
        """Create primary CTkTabview navigation."""
        self.notebook = ctk.CTkTabview(
            self, 
            segmented_button_selected_color="#1f538d"
        )
        self.notebook._segmented_button.configure(font=self._ctk_font_bold)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=12)

        self.tab_dashboard = self.notebook.add("Dashboard")
        self.tab_register = self.notebook.add("Attendance Register")
        self.tab_leave = self.notebook.add("Leave Tracker")
        self.tab_files = self.notebook.add("File Manager")
        self.tab_reports = self.notebook.add("Reports")
        self.tab_settings = self.notebook.add("Settings")

        self._build_dashboard_tab()
        self._build_register_tab()
        self._build_leave_tab()
        self._build_files_tab()
        self._build_reports_tab()
        self._build_settings_tab()

    # --- Dashboard Tab ---

    def _build_dashboard_tab(self) -> None:
        frame = self.tab_dashboard

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.pack(fill=tk.X, padx=10, pady=5)

        ctk.CTkLabel(toolbar, text="Period:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(5, 2))
        self.dash_period = ctk.CTkOptionMenu(
            toolbar,
            values=["This Month", "Last Month", "Last 3 Months", "Last 6 Months", "Custom"],
            width=140,
            font=self._ctk_font,
            dropdown_font=self._ctk_font,
            command=self._on_dash_period_change
        )
        self.dash_period.set("This Month")
        self.dash_period.pack(side=tk.LEFT, padx=5)

        ctk.CTkLabel(toolbar, text="From:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(10, 2))
        self.dash_start = ctk.CTkEntry(
            toolbar, width=120, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.dash_start.pack(side=tk.LEFT, padx=2)
        self.dash_start.insert(0, date.today().replace(day=1).isoformat())

        ctk.CTkLabel(toolbar, text="To:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(10, 2))
        self.dash_end = ctk.CTkEntry(
            toolbar, width=120, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.dash_end.pack(side=tk.LEFT, padx=2)
        self.dash_end.insert(0, date.today().isoformat())

        ctk.CTkButton(
            toolbar,
            text="Apply",
            font=self._ctk_font_bold,
            width=90,
            command=self._refresh_dashboard
        ).pack(side=tk.LEFT, padx=8)

        # KPI Layout Frame
        kpi_frame = ctk.CTkFrame(frame, fg_color="transparent")
        kpi_frame.pack(fill=tk.X, padx=10, pady=5)

        self.kpi_cards: Dict[str, ctk.CTkFrame] = {}
        self.kpi_labels: Dict[str, ctk.CTkLabel] = {}
        
        kpi_defs = [
            ("active_employees", "Active Employees"),
            ("attendance_rate", "Attendance Rate"),
            ("working_days", "Working Days"),
        ]
        
        for i, (key, title) in enumerate(kpi_defs):
            card = ctk.CTkFrame(kpi_frame, corner_radius=10, border_width=1, border_color=("#dbdbdb", "#383838"))
            card.grid(row=0, column=i, padx=5, pady=10, sticky="nsew")
            kpi_frame.columnconfigure(i, weight=1)

            # Title
            ctk.CTkLabel(card, text=title, font=self._ctk_font_bold, text_color=("#666666", "#aaaaaa")).pack(anchor="w", padx=15, pady=(15, 5))
            
            # Value
            lbl = ctk.CTkLabel(card, text="-", font=self._ctk_font_value)
            lbl.pack(anchor="w", padx=15, pady=(5, 5))
            
            # Trend
            trend = ctk.CTkLabel(card, text="", font=self._ctk_font)
            trend.pack(anchor="w", padx=15, pady=(0, 15))

            self.kpi_labels[key] = lbl
            self.kpi_labels[f"{key}_trend"] = trend
            self.kpi_cards[key] = card

        # Charts Section
        chart_frame = ctk.CTkFrame(frame, fg_color="transparent")
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        chart_frame.columnconfigure(0, weight=3)
        chart_frame.columnconfigure(1, weight=2)
        chart_frame.rowconfigure(0, weight=1)

        self.trend_chart_frame = ctk.CTkFrame(chart_frame, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        self.trend_chart_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=5)

        self.offenders_chart_frame = ctk.CTkFrame(chart_frame, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        self.offenders_chart_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=5)

        # Comparison Section
        comp_frame = ctk.CTkFrame(frame, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        comp_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ctk.CTkLabel(comp_frame, text="Period Comparison (vs previous equal-length period)", font=self._ctk_font_bold).pack(anchor="w", padx=15, pady=(10, 5))

        comp_cols = ("Metric", "Current", "Previous", "Change", "Trend")
        
        # Grid frame setup for scrollbars
        comp_table_frame = ctk.CTkFrame(comp_frame, fg_color="transparent")
        comp_table_frame.pack(fill=tk.X, padx=15, pady=(5, 15))
        comp_table_frame.rowconfigure(0, weight=1)
        comp_table_frame.columnconfigure(0, weight=1)
        
        self.comparison_tree = ttk.Treeview(comp_table_frame, columns=comp_cols, show="headings", height=3)
        configure_tree_columns(
            self.comparison_tree,
            dict(zip(comp_cols, comp_cols)),
            {c: 180 for c in comp_cols},
        )
        
        scroll_y = ttk.Scrollbar(comp_table_frame, orient=tk.VERTICAL, command=self.comparison_tree.yview)
        scroll_x = ttk.Scrollbar(comp_table_frame, orient=tk.HORIZONTAL, command=self.comparison_tree.xview)
        self.comparison_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        self.comparison_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")


    def _on_dash_period_change(self, period: str) -> None:
        today = date.today()
        if period == "This Month":
            start, end = today.replace(day=1), today
        elif period == "Last Month":
            end = today.replace(day=1) - timedelta(days=1)
            start = end.replace(day=1)
        elif period == "Last 3 Months":
            end = today
            start = today - timedelta(days=90)
        elif period == "Last 6 Months":
            end = today
            start = today - timedelta(days=180)
        else:
            return
        self.dash_start.delete(0, tk.END)
        self.dash_start.insert(0, start.isoformat())
        self.dash_end.delete(0, tk.END)
        self.dash_end.insert(0, end.isoformat())
        self._refresh_dashboard()

    def _get_dashboard_range(self) -> tuple:
        try:
            start = datetime.strptime(self.dash_start.get(), "%Y-%m-%d").date()
            end = datetime.strptime(self.dash_end.get(), "%Y-%m-%d").date()
            if start > end:
                messagebox.showwarning("Date Range", "Start date must be before end date.")
                start, end = end, start
            return start, end
        except ValueError:
            messagebox.showerror("Date Range", "Invalid date format. Use YYYY-MM-DD.")
            today = date.today()
            return today.replace(day=1), today

    @staticmethod
    def _get_previous_period(start: date, end: date) -> tuple:
        length = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        return prev_start, prev_end

    def _clear_chart_frame(self, frame: ctk.CTkFrame) -> None:
        fig = getattr(frame, "_chart_figure", None)
        if fig is not None:
            close_figure(fig)
            frame._chart_figure = None  # type: ignore[attr-defined]
        for widget in frame.winfo_children():
            widget.destroy()

    def _embed_in_frame(self, frame: ctk.CTkFrame, figure, on_pick=None) -> None:
        frame._chart_figure = figure  # type: ignore[attr-defined]
        embed_chart(frame, figure, on_pick=on_pick).get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _refresh_dashboard(self) -> None:
        start, end = self._get_dashboard_range()
        self._dashboard_range = (start, end)
        prev_start, prev_end = self._get_previous_period(start, end)

        working_days = self.config_mgr.get("attendance", "working_days", [0, 1, 2, 3, 4])
        holidays = [
            datetime.strptime(h, "%Y-%m-%d").date()
            for h in self.config_mgr.get("attendance", "holidays", [])
        ]
        excused = self.config_mgr.get("leave", "excused_codes", [])
        kpis = self.db.get_dashboard_kpis(start, end, working_days, holidays, excused)
        prev_kpis = self.db.get_dashboard_kpis(
            prev_start, prev_end, working_days, holidays, excused
        )

        kpi_display = {
            "active_employees": (str(kpis["active_employees"]), str(prev_kpis["active_employees"]), True),
            "attendance_rate": (f"{kpis['attendance_rate']}%", f"{prev_kpis['attendance_rate']}%", True),
            "working_days": (str(kpis.get("working_days", 0)), str(prev_kpis.get("working_days", 0)), True),
        }
        for key, (curr, prev, higher_better) in kpi_display.items():
            self.kpi_labels[key].configure(text=curr)
            try:
                c_val = float(curr.replace("%", ""))
                p_val = float(prev.replace("%", ""))
                arrow = trend_indicator(c_val, p_val, higher_better)
                diff = c_val - p_val
                sign = "+" if diff > 0 else ""
                val_diff = f" ({sign}{diff:.1f}%)" if "%" in curr else f" ({sign}{int(diff)})"
                self.kpi_labels[f"{key}_trend"].configure(
                    text=f"{arrow}{val_diff} vs prev",
                    text_color="green" if (diff > 0) == higher_better else "red"
                )
            except ValueError:
                self.kpi_labels[f"{key}_trend"].configure(text="")

        self._clear_chart_frame(self.trend_chart_frame)
        self._clear_chart_frame(self.offenders_chart_frame)

        # Matplotlib uses dark background matching CustomTkinter
        metrics = self.db.get_monthly_metrics(12)
        trend_fig = create_trend_chart(metrics, dark=self._dark_mode)
        self._embed_in_frame(self.trend_chart_frame, trend_fig)

        self._dashboard_offenders = self.db.get_top_offenders(
            start, end, 5, working_days, holidays, excused
        )
        off_fig = create_offenders_chart(self._dashboard_offenders, dark=self._dark_mode)
        self._embed_in_frame(
            self.offenders_chart_frame, off_fig, on_pick=self._on_offender_chart_pick
        )

        for item in self.comparison_tree.get_children():
            self.comparison_tree.delete(item)

        comparisons = [
            ("Attendance Rate", f"{kpis['attendance_rate']}%", f"{prev_kpis['attendance_rate']}%", True),
            ("Working Days", str(kpis.get("working_days", 0)), str(prev_kpis.get("working_days", 0)), True),
            ("Active Employees", str(kpis["active_employees"]), str(prev_kpis["active_employees"]), True),
        ]
        for metric, curr, prev, higher_better in comparisons:
            try:
                c_val = float(curr.replace("%", ""))
                p_val = float(prev.replace("%", ""))
                diff = c_val - p_val
            except ValueError:
                diff = 0
                c_val = p_val = 0
            pct = pct_change(c_val, p_val) if p_val else None
            change_str = f"{diff:+.0f}" + ("%" if "%" in curr else "")
            if pct is not None:
                change_str = f"{change_str} ({pct:+.1f}%)"
            trend = trend_indicator(c_val, p_val, higher_better)
            self.comparison_tree.insert("", tk.END, values=(metric, curr, prev, change_str, trend))

        auto_fit_columns(self.comparison_tree)

    def _on_offender_chart_pick(self, event) -> None:
        if not self._dashboard_offenders or event.ind is None:
            return
        idx = event.ind[0]
        if idx >= len(self._dashboard_offenders):
            return
        emp_id = self._dashboard_offenders[idx]["employee_id"]
        start, end = self._dashboard_range
        self._open_employee_detail(emp_id, start, end)

    def _open_employee_detail(self, emp_id: int, start: date, end: date) -> None:
        emp = self.db.get_employee(emp_id)
        if not emp:
            return
        records = self.db.get_attendance_for_employee(emp_id, start, end)

        win = ctk.CTkToplevel(self)
        win.title(f"Employee Detail - {effective_display_name(emp)}")
        
        # Standard unscaled dialog geometry (natively scaled by CTk)
        win.geometry("700x500")
        win.transient(self)
        self._safe_grab_set(win)

        ctk.CTkLabel(
            win,
            text=f"Period: {format_date(start)} to {format_date(end)}",
            font=self._ctk_font_large,
        ).pack(pady=15)
        
        detail_cols = ("date", "arrival", "departure", "late", "minutes")
        
        frame = ctk.CTkFrame(win, fg_color="transparent")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        
        tree = ttk.Treeview(frame, columns=detail_cols, show="headings")
        configure_tree_columns(
            tree,
            dict(zip(detail_cols, ["Date", "Arrival", "Departure", "Late", "Minutes"])),
            {c: int(120 * self._scale_factor) for c in detail_cols},
        )
        
        scroll_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scroll_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        
        for r in records:
            tree.insert("", tk.END, values=(
                r["date"], r.get("arrival_time", "-"), r.get("departure_time", "-"),
                "Yes" if r["is_late"] else "No", r.get("late_minutes", 0),
            ))

        auto_fit_columns(tree)


    # --- Register Tab ---

    def _build_register_tab(self) -> None:
        frame = self.tab_register
        
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.pack(fill=tk.X, padx=10, pady=5)

        ctk.CTkLabel(toolbar, text="Search:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(5, 2))
        self.register_search = ctk.CTkEntry(
            toolbar, width=200, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.register_search.pack(side=tk.LEFT, padx=5)
        self.register_search.bind("<KeyRelease>", lambda e: self._refresh_register())

        ctk.CTkLabel(toolbar, text="From:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(15, 2))
        self.reg_start = ctk.CTkEntry(
            toolbar, width=120, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.reg_start.pack(side=tk.LEFT, padx=2)
        self.reg_start.insert(0, date.today().replace(day=1).isoformat())

        ctk.CTkLabel(toolbar, text="To:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(15, 2))
        self.reg_end = ctk.CTkEntry(
            toolbar, width=120, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.reg_end.pack(side=tk.LEFT, padx=2)
        self.reg_end.insert(0, date.today().isoformat())

        ctk.CTkButton(toolbar, text="Apply", font=self._ctk_font_bold, width=80, command=self._refresh_register).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(toolbar, text="Export Excel", font=self._ctk_font_bold, width=110, command=lambda: self._quick_export("excel")).pack(side=tk.RIGHT, padx=3)
        ctk.CTkButton(toolbar, text="Export PDF", font=self._ctk_font_bold, width=110, command=lambda: self._quick_export("pdf")).pack(side=tk.RIGHT, padx=3)

        table_frame = ctk.CTkFrame(frame, fg_color="transparent")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        reg_cols = ("num", "enno", "name", "present", "absent", "excused", "attendance", "late", "lateness")
        self.register_tree = ttk.Treeview(table_frame, columns=reg_cols, show="headings")
        reg_headers = {
            "num": "#", "enno": "Employee ID", "name": "Name", "present": "Days Present",
            "absent": "Absent Days", "excused": "Excused Leave", "attendance": "Attendance %",
            "late": "Late Days", "lateness": "Lateness %",
        }
        reg_widths = {
            "num": int(40 * self._scale_factor), 
            "enno": int(110 * self._scale_factor), 
            "name": int(220 * self._scale_factor), 
            "present": int(110 * self._scale_factor), 
            "absent": int(110 * self._scale_factor),
            "excused": int(110 * self._scale_factor), 
            "attendance": int(125 * self._scale_factor), 
            "late": int(110 * self._scale_factor), 
            "lateness": int(125 * self._scale_factor),
        }
        configure_tree_columns(
            self.register_tree,
            reg_headers,
            reg_widths,
            left_align={"name"},
            heading_commands={c: (lambda col=c: self._sort_register(col)) for c in reg_cols},
        )

        reg_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.register_tree.yview)
        reg_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.register_tree.xview)
        self.register_tree.configure(yscrollcommand=reg_scroll_y.set, xscrollcommand=reg_scroll_x.set)
        
        self.register_tree.grid(row=0, column=0, sticky="nsew")
        reg_scroll_y.grid(row=0, column=1, sticky="ns")
        reg_scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.register_tree.bind("<Double-1>", self._show_employee_detail)

    def _refresh_register(self) -> None:
        try:
            start = datetime.strptime(self.reg_start.get(), "%Y-%m-%d").date()
            end = datetime.strptime(self.reg_end.get(), "%Y-%m-%d").date()
        except ValueError:
            start = date.today().replace(day=1)
            end = date.today()

        working_days = self.config_mgr.get("attendance", "working_days", [0, 1, 2, 3, 4])
        holidays = [
            datetime.strptime(h, "%Y-%m-%d").date()
            for h in self.config_mgr.get("attendance", "holidays", [])
        ]
        excused = self.config_mgr.get("leave", "excused_codes", [])
        summaries = self.db.compute_employee_summary(
            start, end, working_days, holidays, excused_codes=excused
        )
        search = self.register_search.get().lower()
        filtered = [
            s for s in summaries
            if not search
            or search in s["display_name"].lower()
            or search in s.get("export_name", "").lower()
            or search in s["enno"].lower()
        ]

        for item in self.register_tree.get_children():
            self.register_tree.delete(item)

        for i, s in enumerate(filtered, 1):
            rate = s["attendance_rate"]
            tag = "green" if rate >= 90 else "yellow" if rate >= 75 else "red"
            self.register_tree.insert("", tk.END, iid=str(s["employee_id"]), tags=(tag,), values=(
                i, normalize_enno(s["enno"]), s["display_name"], s["days_present"], s["absent_days"],
                s.get("excused_days", 0), f"{s['attendance_rate']}%", s["late_days"],
                f"{s['lateness_rate']}%",
            ))

        auto_fit_columns(self.register_tree)

    def _sort_register(self, col: str) -> None:
        items = [(self.register_tree.set(k, col), k) for k in self.register_tree.get_children("")]
        reverse = self._sort_reverse.get(col, False)
        try:
            items.sort(key=lambda x: float(x[0].replace("%", "")), reverse=reverse)
        except ValueError:
            items.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, k) in enumerate(items):
            self.register_tree.move(k, "", index)
        self._sort_reverse[col] = not reverse

    def _show_employee_detail(self, event) -> None:
        sel = self.register_tree.selection()
        if not sel:
            return
        emp_id = int(sel[0])
        try:
            start = datetime.strptime(self.reg_start.get(), "%Y-%m-%d").date()
            end = datetime.strptime(self.reg_end.get(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Error", "Invalid date range.")
            return
        self._open_employee_detail(emp_id, start, end)

    def _quick_export(self, fmt: str) -> None:
        try:
            start = datetime.strptime(self.reg_start.get(), "%Y-%m-%d").date()
            end = datetime.strptime(self.reg_end.get(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Error", "Invalid date range.")
            return
        output_dir = self._confirm_export_location()
        if output_dir is None:
            return
        self._run_async(
            lambda: self.report_gen.generate(
                "executive", start, end, fmt,
                include_charts=True, include_raw=True, output_dir=output_dir,
            ),
            "Report generated successfully.",
        )

    # --- Leave Tracker Tab ---

    def _build_leave_tab(self) -> None:
        frame = self.tab_leave
        
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.pack(fill=tk.X, padx=10, pady=5)

        ctk.CTkLabel(toolbar, text="Year:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(5, 2))
        self.leave_year = ttk.Spinbox(toolbar, from_=2020, to=2035, width=6)
        self.leave_year.set(self.config_mgr.get("leave", "year", date.today().year))
        self.leave_year.pack(side=tk.LEFT, padx=5)

        ctk.CTkLabel(toolbar, text="Month:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(10, 2))
        self.leave_month = ctk.CTkOptionMenu(
            toolbar, values=MONTH_NAMES, width=130,
            font=self._ctk_font,
            dropdown_font=self._ctk_font,
            command=lambda val: self._refresh_leave()
        )
        self.leave_month.set(MONTH_NAMES[date.today().month - 1])
        self.leave_month.pack(side=tk.LEFT, padx=5)

        ctk.CTkLabel(toolbar, text="Search:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(15, 2))
        self.leave_search = ctk.CTkEntry(
            toolbar, width=180, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.leave_search.pack(side=tk.LEFT, padx=5)
        self.leave_search.bind("<KeyRelease>", lambda e: self._refresh_leave())

        ctk.CTkButton(toolbar, text="Apply", font=self._ctk_font_bold, width=80, command=self._refresh_leave).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(toolbar, text="Import Excel", font=self._ctk_font_bold, width=110, command=self._show_leave_import_dialog).pack(side=tk.RIGHT, padx=3)
        ctk.CTkButton(toolbar, text="Export Excel", font=self._ctk_font_bold, width=110, command=self._export_leave_workbook).pack(side=tk.RIGHT, padx=3)

        # Tabview to cleanly separate grid entry from annual totals
        self.leave_sub_tabs = ctk.CTkTabview(
            frame, 
            segmented_button_selected_color="#1f538d"
        )
        self.leave_sub_tabs._segmented_button.configure(font=self._ctk_font_bold)
        self.leave_sub_tabs.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tab_grid = self.leave_sub_tabs.add("Monthly Leave Grid")
        tab_totals = self.leave_sub_tabs.add("Annual Summary & Entitlements")

        # --- Sub-Tab 1: Monthly Leave Grid Layout ---
        tab_grid.columnconfigure(0, weight=1)
        tab_grid.rowconfigure(0, weight=1)

        grid_frame = ctk.CTkFrame(tab_grid, fg_color="transparent")
        grid_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.columnconfigure(0, weight=0)  # Frozen columns (no stretching)
        grid_frame.columnconfigure(1, weight=1)  # Day columns (takes remaining space)
        grid_frame.columnconfigure(2, weight=0)  # Scrollbar Y

        self.leave_tree_left = ttk.Treeview(grid_frame, show="headings", height=18)
        self.leave_tree = ttk.Treeview(grid_frame, show="headings", height=18)
        
        leave_scroll_y = ttk.Scrollbar(grid_frame, orient=tk.VERTICAL, command=self.on_leave_y_scroll)
        leave_scroll_x = ttk.Scrollbar(grid_frame, orient=tk.HORIZONTAL, command=self.leave_tree.xview)
        
        self.leave_tree_left.configure(yscrollcommand=leave_scroll_y.set)
        self.leave_tree.configure(yscrollcommand=leave_scroll_y.set, xscrollcommand=leave_scroll_x.set)
        
        self.leave_tree_left.grid(row=0, column=0, sticky="ns")
        self.leave_tree.grid(row=0, column=1, sticky="nsew")
        leave_scroll_y.grid(row=0, column=2, sticky="ns")
        leave_scroll_x.grid(row=1, column=1, sticky="ew")

        # Double click overlay + Direct keys bindings on scrollable part (since cells are there)
        self.leave_tree.bind("<Double-1>", self._edit_leave_cell)
        self.leave_tree.bind("<Button-1>", self._on_leave_tree_click)
        self.leave_tree.bind("<KeyPress>", self._on_leave_tree_keypress)

        # Synced Selection and Mouse Wheel scrolling
        self.leave_tree_left.bind("<MouseWheel>", self.on_leave_left_mousewheel)
        self.leave_tree.bind("<MouseWheel>", self.on_leave_right_mousewheel)
        
        self.leave_tree_left.bind("<<TreeviewSelect>>", self.sync_leave_left_to_right)
        self.leave_tree.bind("<<TreeviewSelect>>", self.sync_leave_right_to_left)


        # --- Sub-Tab 2: Annual Summary & Entitlements Layout ---
        tab_totals.columnconfigure(0, weight=4)
        tab_totals.columnconfigure(1, weight=1)
        tab_totals.rowconfigure(0, weight=1)

        totals_frame = ctk.CTkFrame(tab_totals, fg_color="transparent")
        totals_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=5)
        totals_frame.rowconfigure(0, weight=1)
        totals_frame.columnconfigure(0, weight=1)

        totals_cols = ("num", "enno", "name", "carry", "alloc", "entitlement", "vac", "sick", "hol", "used", "balance")
        self.leave_totals_tree = ttk.Treeview(totals_frame, columns=totals_cols, show="headings", height=18)
        
        totals_headers = {
            "num": "#", "enno": "ID", "name": "Name", "carry": "Carry Over", "alloc": "Allocation",
            "entitlement": "Entitlement", "vac": "Vacation (V)", "sick": "Sick (S)", "hol": "Holidays (H)",
            "used": "Total Used", "balance": "Days Left"
        }
        totals_widths = {
            "num": int(40 * self._scale_factor), 
            "enno": int(65 * self._scale_factor), 
            "name": int(180 * self._scale_factor), 
            "carry": int(85 * self._scale_factor), 
            "alloc": int(85 * self._scale_factor), 
            "entitlement": int(85 * self._scale_factor),
            "vac": int(90 * self._scale_factor), 
            "sick": int(90 * self._scale_factor), 
            "hol": int(90 * self._scale_factor), 
            "used": int(90 * self._scale_factor), 
            "balance": int(90 * self._scale_factor)
        }
        configure_tree_columns(self.leave_totals_tree, totals_headers, totals_widths, left_align={"name"})

        totals_scroll_y = ttk.Scrollbar(totals_frame, orient=tk.VERTICAL, command=self.leave_totals_tree.yview)
        totals_scroll_x = ttk.Scrollbar(totals_frame, orient=tk.HORIZONTAL, command=self.leave_totals_tree.xview)
        self.leave_totals_tree.configure(yscrollcommand=totals_scroll_y.set, xscrollcommand=totals_scroll_x.set)
        
        self.leave_totals_tree.grid(row=0, column=0, sticky="nsew")
        totals_scroll_y.grid(row=0, column=1, sticky="ns")
        totals_scroll_x.grid(row=1, column=0, sticky="ew")

        # Edit Entitlements Right Sidebar Form
        ent_sidebar = ctk.CTkFrame(tab_totals, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        ent_sidebar.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=5)

        ctk.CTkLabel(ent_sidebar, text="Edit Entitlements", font=self._font_bold).pack(anchor="w", padx=15, pady=(15, 10))
        
        ctk.CTkLabel(ent_sidebar, text="Employee:", font=self._ctk_font_bold, text_color=("#666666", "#aaaaaa")).pack(anchor="w", padx=15, pady=(5, 2))
        self.leave_target_lbl = ctk.CTkLabel(ent_sidebar, text="-", font=self._ctk_font_bold)
        self.leave_target_lbl.pack(anchor="w", padx=15, pady=(0, 15))

        ctk.CTkLabel(ent_sidebar, text="Carry Over:", font=self._ctk_font_bold).pack(anchor="w", padx=15, pady=2)
        self.leave_carry_entry = ctk.CTkEntry(
            ent_sidebar, placeholder_text="0.0", font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.leave_carry_entry.pack(fill=tk.X, padx=15, pady=(0, 10))

        ctk.CTkLabel(ent_sidebar, text="Annual Allocation:", font=self._ctk_font_bold).pack(anchor="w", padx=15, pady=2)
        self.leave_alloc_entry = ctk.CTkEntry(
            ent_sidebar, placeholder_text="0.0", font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.leave_alloc_entry.pack(fill=tk.X, padx=15, pady=(0, 15))

        self.leave_save_btn = ctk.CTkButton(ent_sidebar, text="Save Settings", font=self._ctk_font_bold, command=self._save_leave_entitlement)
        self.leave_save_btn.pack(fill=tk.X, padx=15, pady=10)

        # Sync selection bindings
        self.leave_totals_tree.bind("<<TreeviewSelect>>", lambda e: self._show_leave_employee_detail("totals"))

    def _get_leave_year_month(self) -> tuple:
        try:
            year = int(self.leave_year.get())
        except ValueError:
            year = date.today().year
        month_name = self.leave_month.get()
        try:
            month = MONTH_NAMES.index(month_name) + 1
        except ValueError:
            month = date.today().month
        return year, month

    def _destroy_active_combo(self) -> None:
        """Destroy active inline combobox if it exists."""
        if hasattr(self, "_active_combo") and self._active_combo:
            try:
                self._active_combo.destroy()
            except Exception:
                pass
            self._active_combo = None

    def _refresh_leave(self) -> None:
        """Populate the leave tab grid and totals tab."""
        self._destroy_active_combo()
        year, month = self._get_leave_year_month()
        grid = self.leave_mgr.get_month_grid(year, month)
        days_in_month = grid["days_in_month"]
        search = self.leave_search.get().lower()

        # Build column definitions including weekday abbreviation in heading
        left_cols = ["num", "enno", "name"]
        day_cols = [f"d{day}" for day in range(1, days_in_month + 1)]
        right_cols = day_cols + ["total"]

        self.leave_tree_left.configure(columns=left_cols)
        self.leave_tree.configure(columns=right_cols)
        
        left_headers = {
            "num": "#", "enno": "ID", "name": "Name",
        }
        left_widths = {
            "num": int(36 * self._scale_factor), 
            "enno": int(65 * self._scale_factor), 
            "name": int(180 * self._scale_factor),
        }
        
        right_headers = {
            "total": "Total",
        }
        right_widths = {
            "total": int(60 * self._scale_factor)
        }
        for day in range(1, days_in_month + 1):
            right_headers[f"d{day}"] = f"{day}"
            right_widths[f"d{day}"] = int(32 * self._scale_factor)

        configure_tree_columns(
            self.leave_tree_left,
            left_headers,
            left_widths,
            left_align={"name"},
        )
        configure_tree_columns(
            self.leave_tree,
            right_headers,
            right_widths,
        )

        for item in self.leave_tree_left.get_children():
            self.leave_tree_left.delete(item)
        for item in self.leave_tree.get_children():
            self.leave_tree.delete(item)

        for emp in grid["employees"]:
            if search and search not in emp["display_name"].lower() and search not in emp["enno"].lower():
                continue
            
            left_values = [emp["num"], normalize_enno(emp["enno"]), emp["display_name"]]
            right_values = []
            tags: tuple = ()
            for day in range(1, days_in_month + 1):
                code = emp["days"].get(day, "")
                right_values.append(code)
                if code:
                    record_date = date(year, month, day)
                    if self.leave_mgr.get_conflicts(emp["employee_id"], record_date):
                        tags = ("conflict",)
            right_values.append(f"{emp['monthly_deduction']:.2g}")
            
            self.leave_tree_left.insert(
                "", tk.END, iid=str(emp["employee_id"]), values=left_values, tags=tags
            )
            self.leave_tree.insert(
                "", tk.END, iid=str(emp["employee_id"]), values=right_values, tags=tags
            )

        auto_fit_columns(self.leave_tree_left, min_width=36)
        auto_fit_columns(self.leave_tree, min_width=32)

        self._refresh_leave_totals()

    def _refresh_leave_totals(self) -> None:
        """Populate the annual leave summaries sub-tab."""
        year, _ = self._get_leave_year_month()
        employees = self.db.get_all_employees(active_only=True)
        search = self.leave_search.get().lower()

        for item in self.leave_totals_tree.get_children():
            self.leave_totals_tree.delete(item)

        for i, emp in enumerate(employees, 1):
            if search and search not in emp["export_name"].lower() and search not in (emp.get("display_name") or "").lower() and search not in emp["enno"].lower():
                continue
            
            totals = self.leave_mgr.compute_annual_leave_totals(emp["id"], year)
            counts = totals.get("code_counts", {})
            
            # Extract individual code metrics
            vac_days = counts.get("V", 0.0)
            sick_days = counts.get("S", 0.0)
            hol_days = counts.get("H", 0.0) + counts.get("H1", 0.0)*0.5 + counts.get("H2", 0.0)*0.5

            self.leave_totals_tree.insert("", tk.END, iid=str(emp["id"]), values=(
                i,
                normalize_enno(emp["enno"]),
                effective_display_name(emp),
                f"{totals['carry_over']:.2g}",
                f"{totals['annual_allocation']:.2g}",
                f"{totals['entitlement']:.2g}",
                f"{vac_days:.2g}",
                f"{sick_days:.2g}",
                f"{hol_days:.2g}",
                f"{totals['used']:.2g}",
                f"{totals['balance']:.2g}"
            ))

        auto_fit_columns(self.leave_totals_tree, min_width=40)

    def _on_leave_tree_click(self, event) -> None:
        """Track row and column of standard day click."""
        self._destroy_active_combo()
        row_id = self.leave_tree.identify_row(event.y)
        col_id = self.leave_tree.identify_column(event.x)
        if not row_id or not col_id:
            return
        col_index = int(col_id.replace("#", "")) - 1
        columns = self.leave_tree["columns"]
        if 0 <= col_index < len(columns):
            self._last_leave_col = columns[col_index]
            self._last_leave_row = row_id

    def _on_leave_tree_keypress(self, event) -> None:
        """Excel-style rapid keyboard entries."""
        if not self._last_leave_row or not self._last_leave_col:
            return
        
        col_name = self._last_leave_col
        if not col_name.startswith("d"):
            return
        
        char = event.char.upper()
        if event.keysym in ("BackSpace", "Delete") or char == " ":
            code = None
        elif char in self.leave_mgr.get_weights():
            code = char
        else:
            return  # Ignore keys that aren't leave codes

        day = int(col_name[1:])
        year, month = self._get_leave_year_month()
        emp_id = int(self._last_leave_row)
        record_date = date(year, month, day)

        try:
            self.leave_mgr.set_leave_code(emp_id, record_date, code)
        except ValueError as exc:
            messagebox.showerror("Invalid Code", str(exc))
            return

        self._refresh_leave()
        self._show_leave_employee_detail("grid")

        # Auto-advance selection to the right (Excel behavior)
        days_in_month = calendar.monthrange(year, month)[1]
        if day < days_in_month and code is not None:
            self._last_leave_col = f"d{day + 1}"
            # Ensure visual selection focus matches
            self.leave_tree.selection_set(self._last_leave_row)

    def _edit_leave_cell(self, event) -> None:
        """Display an inline Combobox over the double-clicked cell."""
        self._destroy_active_combo()
        row_id = self.leave_tree.identify_row(event.y)
        col_id = self.leave_tree.identify_column(event.x)
        if not row_id or not col_id:
            return
        col_index = int(col_id.replace("#", "")) - 1
        columns = self.leave_tree["columns"]
        if col_index < 0 or col_index >= len(columns):
            return
        col_name = columns[col_index]
        if not col_name.startswith("d"):
            return

        day = int(col_name[1:])
        year, month = self._get_leave_year_month()
        emp_id = int(row_id)
        record_date = date(year, month, day)
        current = self.db.get_leave_on_date(emp_id, record_date)
        current_code = current["code"] if current else ""

        # Retrieve cell bounding box
        bbox = self.leave_tree.bbox(row_id, col_name)
        if not bbox:
            return
        x, y, w, h = bbox

        # Overlay standard Combobox directly matching the style of Treeview
        code_var = tk.StringVar(value=current_code)
        codes = [""] + sorted(self.leave_mgr.get_weights().keys())
        combo = ttk.Combobox(self.leave_tree, textvariable=code_var, values=codes, state="readonly")
        self._active_combo = combo
        combo.place(x=x, y=y, width=w, height=h)
        combo.focus_set()
        
        # Trigger drop-down automatically
        combo.event_generate('<Down>')

        def commit(event=None):
            code = code_var.get().strip()
            try:
                self.leave_mgr.set_leave_code(emp_id, record_date, code or None)
            except ValueError as exc:
                messagebox.showerror("Invalid Code", str(exc))
            combo.destroy()
            if self._active_combo == combo:
                self._active_combo = None
            self._refresh_leave()
            self._show_leave_employee_detail("grid")

        def check_focus():
            if not combo.winfo_exists():
                return
            focused = self.focus_get()
            if focused != combo and not str(focused).startswith(str(combo)):
                combo.destroy()
                if self._active_combo == combo:
                    self._active_combo = None

        combo.bind("<<ComboboxSelected>>", commit)
        combo.bind("<Return>", commit)
        combo.bind("<Escape>", lambda e: combo.destroy())
        combo.bind("<FocusOut>", lambda e: self.after(100, check_focus))

    def _show_leave_employee_detail(self, source: str = "grid") -> None:
        """Load annual data for selected employee in entitlements form."""
        if source == "grid":
            sel = self.leave_tree.selection()
            tree = self.leave_tree
        else:
            sel = self.leave_totals_tree.selection()
            tree = self.leave_totals_tree

        if not sel:
            return
        emp_id = int(sel[0])
        year, _ = self._get_leave_year_month()
        emp = self.db.get_employee(emp_id)
        if not emp:
            return

        self._last_leave_row = str(emp_id)
        totals = self.leave_mgr.compute_annual_leave_totals(emp_id, year)
        
        # Update sidebar
        self.leave_target_lbl.configure(text=effective_display_name(emp))
        self.leave_alloc_entry.delete(0, tk.END)
        self.leave_alloc_entry.insert(0, f"{totals['annual_allocation']:.2g}")
        self.leave_carry_entry.delete(0, tk.END)
        self.leave_carry_entry.insert(0, f"{totals['carry_over']:.2g}")

    def _save_leave_entitlement(self) -> None:
        """Save allocation and carryover settings."""
        # Check selection in either sub-tab treeview
        sel_grid = self.leave_tree.selection()
        sel_totals = self.leave_totals_tree.selection()
        sel = sel_grid or sel_totals

        if not sel:
            messagebox.showwarning("Entitlement", "Select an employee first.")
            return
        emp_id = int(sel[0])
        year, _ = self._get_leave_year_month()
        try:
            allocation = float(self.leave_alloc_entry.get())
            carry_over = float(self.leave_carry_entry.get())
        except ValueError:
            messagebox.showerror("Entitlement", "Allocation and carry over must be numbers.")
            return
        self.db.set_entitlement(emp_id, year, allocation, carry_over)
        self._refresh_leave()
        messagebox.showinfo("Entitlement", "Leave entitlement saved.")

    def _export_leave_workbook(self) -> None:
        try:
            year = int(self.leave_year.get())
        except ValueError:
            messagebox.showerror("Export", "Invalid year.")
            return
        output_dir = self._confirm_export_location()
        if output_dir is None:
            return
        self._run_async(
            lambda: self.report_gen.generate(
                "leave_workbook",
                date(year, 1, 1),
                date(year, 12, 31),
                "excel",
                output_dir=output_dir,
            ),
            "Leave workbook exported successfully.",
        )

    def _show_leave_import_dialog(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select Leave Tracker Excel",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if not file_path:
            return

        try:
            meta, warnings = self.leave_importer.preview_file(Path(file_path))
        except Exception as exc:
            messagebox.showerror("Import Error", f"Failed to read file:\n{exc}")
            return

        if not meta.get("valid"):
            messagebox.showerror("Validation Error", meta.get("validation_message", "Invalid workbook."))
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Import Leave Tracker")
        
        # Standard unscaled dialog geometry (natively scaled by CTk)
        dlg.geometry("550x380")
        dlg.transient(self)
        self._safe_grab_set(dlg)

        ctk.CTkLabel(dlg, text=f"Source: {os.path.basename(file_path)}", font=self._ctk_font_large).pack(pady=15)
        ctk.CTkLabel(dlg, text=f"Year: {meta.get('year')}", font=self._ctk_font).pack(pady=2)
        ctk.CTkLabel(dlg, text=f"Month sheets: {len(meta.get('month_sheets', []))}", font=self._ctk_font).pack(pady=2)
        ctk.CTkLabel(
            dlg,
            text=f"Matched employees: {meta.get('matched_count', 0)} | "
                 f"Estimated records: {meta.get('record_estimate', 0)}",
            font=self._ctk_font,
        ).pack(pady=2)
        
        if meta.get("unmatched_names"):
            ctk.CTkLabel(dlg, text="Unmatched names (sample):", font=self._ctk_font_bold).pack(pady=(12, 2))
            ctk.CTkLabel(dlg, text=", ".join(meta["unmatched_names"][:10]), font=self._ctk_font, wraplength=480, text_color=("#666666", "#aaaaaa")).pack()
            
        if warnings:
            ctk.CTkLabel(dlg, text="\n".join(warnings), font=self._ctk_font, text_color="orange", wraplength=480).pack(pady=5)

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(pady=20)

        def do_import():
            dlg.destroy()
            self._run_leave_import(Path(file_path), meta.get("year"))

        ctk.CTkButton(btn_frame, text="Import", font=self._ctk_font_bold, width=100, command=do_import).pack(side=tk.LEFT, padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", font=self._ctk_font_bold, width=100, command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    def _run_leave_import(self, path: Path, year: Optional[int]) -> None:
        progress = ctk.CTkToplevel(self)
        progress.title("Importing...")
        
        # Standard unscaled dialog geometry (natively scaled by CTk)
        progress.geometry("300x120")
        progress.transient(self)
        self._safe_grab_set(progress)
        ctk.CTkLabel(progress, text="Processing workbook, please wait...", font=self._ctk_font).pack(padx=20, pady=40)
        progress.update()

        def task():
            try:
                result = self.leave_importer.import_file(path, year)
                self.after(0, lambda: self._leave_import_complete(result, progress))
            except Exception as exc:
                logger.exception("Leave import failed")
                self.after(0, lambda: self._import_error(str(exc), progress))

        threading.Thread(target=task, daemon=True).start()

    def _leave_import_complete(self, result, progress_win) -> None:
        progress_win.destroy()
        if result.success:
            msg = (
                f"Imported {result.records_imported} leave records.\n"
                f"Updated {result.entitlements_imported} entitlements."
            )
            if result.warnings:
                msg += f"\n\nWarnings: {len(result.warnings)}"
            messagebox.showinfo("Import Complete", msg)
            self._refresh_leave()
            self._refresh_register()
        else:
            messagebox.showerror("Import Failed", "\n".join(result.errors))

    # --- Files Tab ---

    def _build_files_tab(self) -> None:
        frame = self.tab_files
        
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill=tk.X, padx=10, pady=10)

        ctk.CTkButton(top, text="Import New File...", font=self._ctk_font_bold, width=140, command=self._show_import_dialog).pack(side=tk.LEFT)
        ctk.CTkButton(top, text="Refresh", font=self._ctk_font_bold, width=100, command=self._refresh_files).pack(side=tk.LEFT, padx=10)

        export_frame = ctk.CTkFrame(frame, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        export_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ctk.CTkLabel(export_frame, text="Export Location", font=self._font_bold).pack(anchor="w", padx=15, pady=(10, 5))

        use_custom = self.config_mgr.get("export", "use_custom_export_dir", False)
        self.export_location_mode = tk.StringVar(
            value="custom" if use_custom else "default"
        )
        
        default_path = str(self.config_mgr.exports_dir)
        ctk.CTkRadioButton(
            export_frame,
            text=f"Default ({default_path})",
            font=self._ctk_font,
            variable=self.export_location_mode,
            value="default",
            command=self._on_export_location_change,
        ).pack(anchor="w", padx=15, pady=3)
        
        custom_row = ctk.CTkFrame(export_frame, fg_color="transparent")
        custom_row.pack(fill=tk.X, padx=15, pady=5)
        
        ctk.CTkRadioButton(
            custom_row,
            text="Custom folder:",
            font=self._ctk_font,
            variable=self.export_location_mode,
            value="custom",
            command=self._on_export_location_change,
        ).pack(side=tk.LEFT)
        
        self.export_browse_btn = ctk.CTkButton(
            custom_row, text="Browse...", font=self._ctk_font_bold, width=90, command=self._browse_export_dir
        )
        self.export_browse_btn.pack(side=tk.LEFT, padx=10)
        
        self.export_path_label = ctk.CTkLabel(export_frame, text="", font=self._ctk_font, text_color=("#666666", "#aaaaaa"))
        self.export_path_label.pack(anchor="w", padx=15, pady=(2, 5))
        
        ctk.CTkButton(
            export_frame, text="Open Export Folder", font=self._ctk_font_bold, width=160, command=self._open_export_folder
        ).pack(anchor="w", padx=15, pady=(5, 15))
        
        self._update_export_path_label()

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left = ctk.CTkFrame(content, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5), pady=5)
        
        ctk.CTkLabel(left, text="Imported Files", font=self._font_bold).pack(anchor="w", padx=15, pady=(10, 5))

        file_cols = ("filename", "date_range", "records", "import_date", "active")
        
        # Grid frame setup for scrollbars
        files_table_frame = ctk.CTkFrame(left, fg_color="transparent")
        files_table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 15))
        files_table_frame.rowconfigure(0, weight=1)
        files_table_frame.columnconfigure(0, weight=1)
        
        self.files_tree = ttk.Treeview(files_table_frame, columns=file_cols, show="headings", height=15)
        configure_tree_columns(
            self.files_tree,
            dict(zip(file_cols, ["Filename", "Date Range", "Records", "Import Date", "Active"])),
            {c: int(155 * self._scale_factor) for c in file_cols},
            left_align={"filename"},
        )
        
        scroll_y = ttk.Scrollbar(files_table_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        scroll_x = ttk.Scrollbar(files_table_frame, orient=tk.HORIZONTAL, command=self.files_tree.xview)
        self.files_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        self.files_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")


        right = ctk.CTkFrame(content, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(5, 0), pady=5)
        
        ctk.CTkLabel(right, text="Database Health", font=self._font_bold).pack(anchor="w", padx=15, pady=(10, 15))
        
        self.health_labels: Dict[str, ctk.CTkLabel] = {}
        for key, label in [
            ("employees", "Employees"), ("records", "Records"), ("imports", "Imports"),
            ("date_range", "Date Range"), ("size_mb", "Database Size (MB)"),
        ]:
            row = ctk.CTkFrame(right, fg_color="transparent")
            row.pack(fill=tk.X, padx=15, pady=4)
            ctk.CTkLabel(row, text=f"{label}:", font=self._ctk_font, width=160, anchor="w").pack(side=tk.LEFT)
            lbl = ctk.CTkLabel(row, text="-", font=self._ctk_font_bold)
            lbl.pack(side=tk.LEFT)
            self.health_labels[key] = lbl

    def _on_export_location_change(self) -> None:
        use_custom = self.export_location_mode.get() == "custom"
        self.config_mgr.set("export", "use_custom_export_dir", use_custom)
        self.export_browse_btn.configure(state=tk.NORMAL if use_custom else tk.DISABLED)
        self.config_mgr.save()
        self._update_export_path_label()

    def _browse_export_dir(self) -> None:
        folder = filedialog.askdirectory(
            initialdir=self.config_mgr.get("export", "custom_export_dir", "")
            or str(self.config_mgr.exports_dir),
        )
        if folder:
            self.config_mgr.set("export", "custom_export_dir", folder)
            self.export_location_mode.set("custom")
            self.config_mgr.set("export", "use_custom_export_dir", True)
            self.config_mgr.save()
            self._update_export_path_label()

    def _update_export_path_label(self) -> None:
        active = self.config_mgr.get_export_dir()
        self.export_path_label.configure(text=f"Active export folder: {active}")
        use_custom = self.export_location_mode.get() == "custom"
        self.export_browse_btn.configure(state=tk.NORMAL if use_custom else tk.DISABLED)

    def _open_export_folder(self) -> None:
        open_folder(self.config_mgr.get_export_dir())

    def _confirm_export_location(self) -> Optional[Path]:
        """Show themed popup for export confirmations."""
        export_dir = self.config_mgr.get_export_dir()
        chosen = {"path": export_dir}

        dlg = ctk.CTkToplevel(self)
        dlg.title("Export Location")
        
        # Standard unscaled dialog geometry (natively scaled by CTk)
        dlg.geometry("500x200")
        dlg.transient(self)
        self._safe_grab_set(dlg)
        
        result: Dict[str, Optional[Path]] = {"path": None}

        ctk.CTkLabel(dlg, text="Reports will be saved to:", font=self._ctk_font_bold).pack(padx=20, pady=(20, 5))
        path_var = tk.StringVar(value=str(export_dir))
        ctk.CTkLabel(dlg, textvariable=path_var, font=self._ctk_font, wraplength=450, text_color=("#666666", "#aaaaaa")).pack(padx=20, pady=5)

        def change_folder() -> None:
            folder = filedialog.askdirectory(initialdir=str(chosen["path"]))
            if folder:
                chosen["path"] = Path(folder)
                path_var.set(folder)

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Change...", font=self._ctk_font_bold, width=100, command=change_folder).pack(side=tk.LEFT, padx=10)
        ctk.CTkButton(
            btn_frame,
            text="Export",
            font=self._ctk_font_bold,
            width=100,
            command=lambda: (result.update({"path": chosen["path"]}), dlg.destroy()),
        ).pack(side=tk.LEFT, padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", font=self._ctk_font_bold, width=100, command=dlg.destroy).pack(side=tk.LEFT, padx=10)
        
        dlg.wait_window()
        return result["path"]

    def _refresh_files(self) -> None:
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        for f in self.db.get_all_imports():
            date_range = f"{f.get('date_range_start', '')} to {f.get('date_range_end', '')}"
            self.files_tree.insert("", tk.END, values=(
                f["filename"], date_range, f.get("record_count", 0),
                f.get("import_date", ""), "Yes" if f.get("is_active") else "No",
            ))
        stats = self.db.get_health_stats()
        for key, lbl in self.health_labels.items():
            lbl.configure(text=str(stats.get(key, "-")))

        auto_fit_columns(self.files_tree)

    def _show_import_dialog(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select Attendance CSV",
            filetypes=[
                ("Attendance logs", "*.txt;*.csv"),
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            preview, meta = self.import_mgr.preview_file(Path(file_path))
        except Exception as exc:
            messagebox.showerror("Import Error", f"Failed to read file:\n{exc}")
            return

        if not meta.get("valid"):
            messagebox.showerror("Validation Error", meta.get("validation_message", "Invalid file."))
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Import Attendance File")
        
        # Standard unscaled dialog geometry (natively scaled by CTk)
        dlg.geometry("750x500")
        dlg.transient(self)
        self._safe_grab_set(dlg)

        ctk.CTkLabel(dlg, text=f"Source: {os.path.basename(file_path)}", font=self._ctk_font_large).pack(pady=15)
        ctk.CTkLabel(dlg, text=f"Date Range: {meta.get('date_start')} to {meta.get('date_end')}", font=self._ctk_font).pack(pady=2)
        ctk.CTkLabel(dlg, text=f"Records: {meta.get('row_count')} ({meta.get('corrupt_records', 0)} corrupt)", font=self._ctk_font).pack(pady=2)

        ctk.CTkLabel(dlg, text="Suggested Filename:", font=self._ctk_font_bold).pack(pady=(10, 2))
        filename_var = tk.StringVar(value=meta.get("suggested_filename", ""))
        ctk.CTkEntry(
            dlg, textvariable=filename_var, width=400, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        ).pack(pady=5)

        preview_frame = ctk.CTkFrame(dlg, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        preview_cols = list(preview[0].keys()) if preview else ["No", "EnNo", "Name", "DateTime"]
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        
        tree = ttk.Treeview(preview_frame, columns=preview_cols, show="headings", height=5)
        configure_tree_columns(
            tree,
            {c: c for c in preview_cols},
            {c: int(110 * self._scale_factor) for c in preview_cols},
            left_align={"Name"} if "Name" in preview_cols else set(),
        )
        
        scroll_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=tree.yview)
        scroll_x = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        tree.grid(row=0, column=0, sticky="nsew", padx=(15, 0), pady=(15, 0))
        scroll_y.grid(row=0, column=1, sticky="ns", pady=(15, 0), padx=(0, 15))
        scroll_x.grid(row=1, column=0, sticky="ew", padx=(15, 0), pady=(0, 15))
        
        for row in preview:
            values = []
            for c in preview_cols:
                val = str(row.get(c, ""))
                if c == "EnNo":
                    val = normalize_enno(val)
                values.append(val)
            tree.insert("", tk.END, values=values)

        auto_fit_columns(tree)


        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(pady=15)

        def do_import():
            dlg.destroy()
            self._run_import(Path(file_path), filename_var.get())

        ctk.CTkButton(btn_frame, text="Import", font=self._ctk_font_bold, width=100, command=do_import).pack(side=tk.LEFT, padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", font=self._ctk_font_bold, width=100, command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    def _run_import(self, path, filename: str) -> None:
        progress = ctk.CTkToplevel(self)
        progress.title("Importing...")
        
        # Standard unscaled dialog geometry (natively scaled by CTk)
        progress.geometry("300x120")
        progress.transient(self)
        self._safe_grab_set(progress)
        ctk.CTkLabel(progress, text="Processing file, please wait...", font=self._ctk_font).pack(padx=20, pady=40)
        progress.update()

        def task():
            try:
                result = self.import_mgr.import_file(path, filename)
                self.after(0, lambda: self._import_complete(result, progress))
            except Exception as exc:
                logger.exception("Import failed")
                self.after(0, lambda: self._import_error(str(exc), progress))

        threading.Thread(target=task, daemon=True).start()

    def _import_complete(self, result, progress_win) -> None:
        progress_win.destroy()
        if result.success:
            msg = f"Imported {result.records_imported} records.\nSkipped {result.records_skipped} duplicates."
            if result.warnings:
                msg += f"\n\nWarnings: {len(result.warnings)}"
            messagebox.showinfo("Import Complete", msg)
            self._refresh_all()
        else:
            messagebox.showerror("Import Failed", "\n".join(result.errors))

    def _import_error(self, msg: str, progress_win) -> None:
        progress_win.destroy()
        messagebox.showerror("Import Error", msg)

    # --- Reports Tab ---

    def _build_reports_tab(self) -> None:
        frame = self.tab_reports
        
        config_frame = ctk.CTkFrame(frame, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        config_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ctk.CTkLabel(config_frame, text="Report Configuration", font=self._font_bold).pack(anchor="w", padx=20, pady=(15, 10))

        row1 = ctk.CTkFrame(config_frame, fg_color="transparent")
        row1.pack(fill=tk.X, padx=20, pady=5)
        ctk.CTkLabel(row1, text="Report Type:", font=self._ctk_font_bold, width=100, anchor="w").pack(side=tk.LEFT)
        self.report_type = ctk.CTkOptionMenu(
            row1, values=[
                "Executive Summary", "Employee Register", "Late Offenders", "Perfect Attendance",
                "Leave Tracker Workbook", "Custom",
            ], width=200,
            font=self._ctk_font,
            dropdown_font=self._ctk_font
        )
        self.report_type.set("Executive Summary")
        self.report_type.pack(side=tk.LEFT, padx=10)

        row2 = ctk.CTkFrame(config_frame, fg_color="transparent")
        row2.pack(fill=tk.X, padx=20, pady=5)
        ctk.CTkLabel(row2, text="From:", font=self._ctk_font_bold, width=100, anchor="w").pack(side=tk.LEFT)
        self.report_start = ctk.CTkEntry(
            row2, width=120, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.report_start.pack(side=tk.LEFT, padx=10)
        self.report_start.insert(0, date.today().replace(day=1).isoformat())
        
        ctk.CTkLabel(row2, text="To:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=5)
        self.report_end = ctk.CTkEntry(
            row2, width=120, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.report_end.pack(side=tk.LEFT, padx=10)
        self.report_end.insert(0, date.today().isoformat())

        row3 = ctk.CTkFrame(config_frame, fg_color="transparent")
        row3.pack(fill=tk.X, padx=20, pady=5)
        
        self.include_charts_var = tk.BooleanVar(value=True)
        self.include_raw_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(row3, text="Include charts", font=self._ctk_font, variable=self.include_charts_var).pack(side=tk.LEFT, padx=5)
        ctk.CTkCheckBox(row3, text="Include raw data", font=self._ctk_font, variable=self.include_raw_var).pack(side=tk.LEFT, padx=20)

        ctk.CTkLabel(row3, text="Format:", font=self._ctk_font_bold).pack(side=tk.LEFT, padx=(20, 5))
        self.report_format = ctk.CTkOptionMenu(
            row3, values=["PDF", "Excel", "HTML", "Both"], width=100,
            font=self._ctk_font,
            dropdown_font=self._ctk_font
        )
        self.report_format.set("PDF")
        self.report_format.pack(side=tk.LEFT, padx=5)

        ctk.CTkButton(config_frame, text="Generate Report", font=self._ctk_font_bold, width=160, command=self._generate_report).pack(pady=20)

        self.report_status = ctk.CTkLabel(frame, text="", font=self._ctk_font, text_color=("#666666", "#aaaaaa"))
        self.report_status.pack(pady=10)

    def _generate_report(self) -> None:
        try:
            start = datetime.strptime(self.report_start.get(), "%Y-%m-%d").date()
            end = datetime.strptime(self.report_end.get(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Error", "Invalid date range.")
            return

        type_map = {
            "Executive Summary": "executive",
            "Employee Register": "executive",
            "Late Offenders": "late_offenders",
            "Perfect Attendance": "perfect_attendance",
            "Leave Tracker Workbook": "leave_workbook",
            "Custom": "executive",
        }
        fmt_map = {"PDF": "pdf", "Excel": "excel", "HTML": "html", "Both": "both"}
        report_type = type_map.get(self.report_type.get(), "executive")
        fmt = fmt_map.get(self.report_format.get(), "pdf")
        
        output_dir = self._confirm_export_location()
        if output_dir is None:
            return

        def task():
            paths = self.report_gen.generate(
                report_type, start, end, fmt,
                self.include_charts_var.get(), self.include_raw_var.get(),
                output_dir=output_dir,
            )
            self.after(0, lambda: self.report_status.configure(
                text=f"Generated: {', '.join(str(p.name) for p in paths)}"
            ))

        self._run_async(task, "Report generated successfully.")

    # --- Settings Tab ---

    def _build_settings_tab(self) -> None:
        frame = self.tab_settings
        
        # Sub-tabview inside settings
        self.settings_notebook = ctk.CTkTabview(
            frame, 
            segmented_button_selected_color="#1f538d"
        )
        self.settings_notebook._segmented_button.configure(font=self._ctk_font_bold)
        self.settings_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=12)

        # Tabs creation
        att_frame = self.settings_notebook.add("Attendance")
        disp_frame = self.settings_notebook.add("Display")
        name_frame = self.settings_notebook.add("Name Management")
        leave_codes_frame = self.settings_notebook.add("Leave Codes")
        db_frame = self.settings_notebook.add("Database")

        self._build_settings_leave_codes(leave_codes_frame)

        # 1. Attendance Settings
        att_frame.columnconfigure(0, weight=0)
        att_frame.columnconfigure(1, weight=1)
        
        ctk.CTkLabel(att_frame, text="Late Threshold (HH:MM:SS):", font=self._ctk_font_bold).grid(row=0, column=0, sticky="w", padx=20, pady=10)
        self.setting_late = ctk.CTkEntry(
            att_frame, width=150, font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.setting_late.insert(0, self.config_mgr.get("attendance", "late_threshold", "08:01:00"))
        self.setting_late.grid(row=0, column=1, sticky="w", padx=10, pady=10)

        self.workday_vars = {}
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        working = self.config_mgr.get("attendance", "working_days", [0, 1, 2, 3, 4])
        
        ctk.CTkLabel(att_frame, text="Working Days:", font=self._ctk_font_bold).grid(row=1, column=0, sticky="nw", padx=20, pady=10)
        wd_frame = ctk.CTkFrame(att_frame, fg_color="transparent")
        wd_frame.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        for i, day in enumerate(days):
            var = tk.BooleanVar(value=i in working)
            self.workday_vars[i] = var
            ctk.CTkCheckBox(wd_frame, text=day, font=self._ctk_font, variable=var, width=70).pack(side=tk.LEFT, padx=2)

        # 2. Display Settings
        disp_frame.columnconfigure(0, weight=0)
        disp_frame.columnconfigure(1, weight=1)
        
        ctk.CTkLabel(disp_frame, text="Theme:", font=self._ctk_font_bold).grid(row=0, column=0, sticky="w", padx=20, pady=10)
        self.setting_theme = ctk.CTkOptionMenu(
            disp_frame, values=["Light", "Dark", "System"], width=150,
            font=self._ctk_font,
            dropdown_font=self._ctk_font
        )
        self.setting_theme.set(self.config_mgr.get("display", "theme", "system").title())
        self.setting_theme.grid(row=0, column=1, sticky="w", padx=10, pady=10)

        ctk.CTkLabel(disp_frame, text="Font Size:", font=self._ctk_font_bold).grid(row=1, column=0, sticky="w", padx=20, pady=10)
        self.setting_font = ttk.Spinbox(disp_frame, from_=10, to=24, width=5)
        self.setting_font.set(self.config_mgr.get("display", "font_size", 12))
        self.setting_font.grid(row=1, column=1, sticky="w", padx=10, pady=10)

        # 3. Name Management
        self.setting_autocap = tk.BooleanVar(value=self.config_mgr.get("name_management", "auto_capitalize", True))
        ctk.CTkCheckBox(name_frame, text="Auto-capitalize names", font=self._ctk_font, variable=self.setting_autocap).pack(anchor="w", padx=20, pady=10)

        name_toolbar = ctk.CTkFrame(name_frame, fg_color="transparent")
        name_toolbar.pack(fill=tk.X, padx=20, pady=5)
        ctk.CTkButton(name_toolbar, text="Export Names CSV", font=self._ctk_font_bold, width=140, command=self._export_names).pack(side=tk.LEFT, padx=3)
        ctk.CTkButton(name_toolbar, text="Import Names CSV", font=self._ctk_font_bold, width=140, command=self._import_names).pack(side=tk.LEFT, padx=3)

        name_cols = ("enno", "export_name", "display_name")
        
        # Grid frame setup for scrollbars
        names_table_frame = ctk.CTkFrame(name_frame, fg_color="transparent")
        names_table_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))
        names_table_frame.rowconfigure(0, weight=1)
        names_table_frame.columnconfigure(0, weight=1)
        
        self.names_tree = ttk.Treeview(names_table_frame, columns=name_cols, show="headings", height=10)
        configure_tree_columns(
            self.names_tree,
            dict(zip(name_cols, ["Employee ID", "Export Name", "Display Name"])),
            {c: int(220 * self._scale_factor) for c in name_cols},
            left_align={"export_name", "display_name"},
        )
        
        scroll_y = ttk.Scrollbar(names_table_frame, orient=tk.VERTICAL, command=self.names_tree.yview)
        scroll_x = ttk.Scrollbar(names_table_frame, orient=tk.HORIZONTAL, command=self.names_tree.xview)
        self.names_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        self.names_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        
        self.names_tree.bind("<Double-1>", self._edit_display_name)


        # 4. Database Settings
        ctk.CTkLabel(db_frame, text=f"Database: {self.config_mgr.db_path}", font=self._ctk_font).pack(anchor="w", padx=20, pady=5)
        ctk.CTkLabel(db_frame, text=f"Retention: {self.config_mgr.get('data_management', 'retention_months', 12)} months", font=self._ctk_font).pack(anchor="w", padx=20, pady=2)

        db_btns = ctk.CTkFrame(db_frame, fg_color="transparent")
        db_btns.pack(anchor="w", padx=20, pady=15)
        ctk.CTkButton(db_btns, text="Backup", font=self._ctk_font_bold, width=100, command=self._backup_db).pack(side=tk.LEFT, padx=3)
        ctk.CTkButton(db_btns, text="Restore", font=self._ctk_font_bold, width=100, command=self._restore_db).pack(side=tk.LEFT, padx=3)
        ctk.CTkButton(db_btns, text="Compact", font=self._ctk_font_bold, width=100, command=self._compact_db).pack(side=tk.LEFT, padx=3)

        # Save Settings Bottom Frame (Aligned cleanly)
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=tk.X, pady=10)
        ctk.CTkButton(btn_frame, text="Save Settings", font=self._ctk_font_bold, width=180, command=self._save_settings).pack(anchor="center")

    def _refresh_names(self) -> None:
        for item in self.names_tree.get_children():
            self.names_tree.delete(item)
        for emp in self.name_mgr.get_all():
            self.names_tree.insert("", tk.END, iid=str(emp["id"]), values=(
                normalize_enno(emp["enno"]), emp["export_name"], emp["display_name"],
            ))

        auto_fit_columns(self.names_tree)

    def _edit_display_name(self, event) -> None:
        sel = self.names_tree.selection()
        if not sel:
            return
        emp_id = int(sel[0])
        current = self.names_tree.item(sel[0])["values"][2]
        
        # Simpledialog is standard Tk, still operates fine
        new_name = simpledialog.askstring("Edit Display Name", "Enter new display name:", initialvalue=current)
        if new_name:
            self.name_mgr.update_name(emp_id, new_name)
            self._refresh_names()

    def _export_names(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            count = self.name_mgr.export_mappings(Path(path))
            messagebox.showinfo("Export", f"Exported {count} name mappings.")

    def _import_names(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            count = self.name_mgr.import_mappings(Path(path))
            messagebox.showinfo("Import", f"Updated {count} names.")
            self._refresh_names()

    def _save_settings(self) -> None:
        working_days = [i for i, var in self.workday_vars.items() if var.get()]
        self.config_mgr.update_section("attendance", {
            "late_threshold": self.setting_late.get(),
            "working_days": working_days,
        })
        
        theme = self.setting_theme.get().lower()
        font_size = int(self.setting_font.get())
        self.config_mgr.update_section("display", {
            "theme": theme,
            "font_size": font_size,
        })
        self.config_mgr.update_section("name_management", {
            "auto_capitalize": self.setting_autocap.get(),
        })
        self.config_mgr.save()
        
        # Scale window geometry based on font size
        scale_factor = font_size / 12.0
        self._scale_factor = scale_factor
        
        # Apply CustomTkinter native scaling dynamically
        ctk.set_widget_scaling(scale_factor)
        ctk.set_window_scaling(scale_factor)
        
        self.geometry("1400x900")
        self.minsize(1024, 768)

        # Dynamically transition appearance theme
        ctk.set_appearance_mode(theme)
        
        # Redraw style configs dynamically
        self.update_idletasks()
        self._setup_styles()
        self._update_treeview_styles()
        
        messagebox.showinfo("Settings", "Settings saved successfully.")
        self._refresh_all()

    def _backup_db(self) -> None:
        path = self.config_mgr.backup_database()
        if path:
            messagebox.showinfo("Backup", f"Database backed up to:\n{path}")
        else:
            messagebox.showwarning("Backup", "No database to backup.")

    def _restore_db(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=str(self.config_mgr.backup_dir),
            filetypes=[("Database", "*.db")],
        )
        if path:
            if messagebox.askyesno("Confirm Restore", "Restore will replace current database. Continue?"):
                try:
                    self.config_mgr.restore_database(Path(path))
                    self.db = Database(self.config_mgr.db_path)
                    self.import_mgr = ImportManager(self.db, self.config_mgr)
                    self.leave_mgr = LeaveManager(self.db, self.config_mgr)
                    self.leave_importer = LeaveImporter(self.db, self.config_mgr)
                    self.name_mgr = NameManager(self.db, self.config_mgr)
                    self.report_gen = ReportGenerator(self.db, self.config_mgr)
                    messagebox.showinfo("Restore", "Database restored successfully.")
                    
                    self.update_idletasks()
                    self._update_treeview_styles()
                    self._refresh_all()
                except Exception as exc:
                    messagebox.showerror("Restore Error", str(exc))

    def _compact_db(self) -> None:
        self.db.compact()
        messagebox.showinfo("Compact", "Database compacted successfully.")

    # --- Leave Codes Management ---

    def _build_settings_leave_codes(self, frame) -> None:
        frame.columnconfigure(0, weight=4)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        # Left Column: Table of active leave codes
        table_frame = ctk.CTkFrame(frame, fg_color="transparent")
        table_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        cols = ("num", "code", "weight", "desc")
        self.leave_codes_tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        configure_tree_columns(
            self.leave_codes_tree,
            {"num": "#", "code": "Leave Code", "weight": "Deduction Weight", "desc": "Description"},
            {"num": int(40 * self._scale_factor), "code": int(100 * self._scale_factor), "weight": int(150 * self._scale_factor), "desc": int(280 * self._scale_factor)},
            left_align={"desc"}
        )
        self.leave_codes_tree.grid(row=0, column=0, sticky="nsew")
        
        scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.leave_codes_tree.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.leave_codes_tree.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.leave_codes_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)


        # Right Column: Sidebar form
        sidebar = ctk.CTkFrame(frame, corner_radius=8, border_width=1, border_color=("#dbdbdb", "#383838"))
        sidebar.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(sidebar, text="Manage Leave Code", font=self._font_bold).pack(anchor="w", padx=15, pady=(15, 10))

        ctk.CTkLabel(sidebar, text="Leave Code (e.g. V):", font=self._ctk_font_bold).pack(anchor="w", padx=15, pady=2)
        self.setting_code_entry = ctk.CTkEntry(
            sidebar, placeholder_text="Code", font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.setting_code_entry.pack(fill=tk.X, padx=15, pady=(0, 10))

        ctk.CTkLabel(sidebar, text="Weight (0.0 to 1.0):", font=self._ctk_font_bold).pack(anchor="w", padx=15, pady=2)
        self.setting_weight_entry = ctk.CTkEntry(
            sidebar, placeholder_text="1.0", font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.setting_weight_entry.pack(fill=tk.X, padx=15, pady=(0, 10))

        ctk.CTkLabel(sidebar, text="Description:", font=self._ctk_font_bold).pack(anchor="w", padx=15, pady=2)
        self.setting_desc_entry = ctk.CTkEntry(
            sidebar, placeholder_text="Vacation", font=self._ctk_font, border_width=2,
            border_color=("#777777", "#aaaaaa"), fg_color=("#ffffff", "#1e1e1e")
        )
        self.setting_desc_entry.pack(fill=tk.X, padx=15, pady=(0, 15))

        self.setting_save_code_btn = ctk.CTkButton(sidebar, text="Add / Update", font=self._ctk_font_bold, command=self._save_leave_code)
        self.setting_save_code_btn.pack(fill=tk.X, padx=15, pady=5)

        self.setting_delete_code_btn = ctk.CTkButton(sidebar, text="Delete Code", fg_color="#c0392b", hover_color="#e74c3c", font=self._ctk_font_bold, command=self._delete_leave_code)
        self.setting_delete_code_btn.pack(fill=tk.X, padx=15, pady=5)

        self.leave_codes_tree.bind("<<TreeviewSelect>>", self._on_leave_code_select)

    def _on_leave_code_select(self, event) -> None:
        sel = self.leave_codes_tree.selection()
        if not sel:
            return
        vals = self.leave_codes_tree.item(sel[0])["values"]
        code = vals[1]
        weight = vals[2]
        desc = vals[3]

        self.setting_code_entry.delete(0, tk.END)
        self.setting_code_entry.insert(0, str(code))
        self.setting_weight_entry.delete(0, tk.END)
        self.setting_weight_entry.insert(0, str(weight))
        self.setting_desc_entry.delete(0, tk.END)
        self.setting_desc_entry.insert(0, str(desc))

    def _refresh_leave_codes(self) -> None:
        if not hasattr(self, "leave_codes_tree") or not self.leave_codes_tree:
            return
        for item in self.leave_codes_tree.get_children():
            self.leave_codes_tree.delete(item)
        
        details = self.leave_mgr.get_code_details()
        for i, (code, data) in enumerate(sorted(details.items()), 1):
            self.leave_codes_tree.insert("", tk.END, values=(
                i, code, f"{data['weight']:.2g}", data["desc"]
            ))

        auto_fit_columns(self.leave_codes_tree)

    def _save_leave_code(self) -> None:
        code = self.setting_code_entry.get().strip().upper()
        if not code:
            messagebox.showwarning("Save Code", "Please enter a leave code.")
            return
        try:
            weight = float(self.setting_weight_entry.get().strip())
            if not (0.0 <= weight <= 1.0):
                raise ValueError()
        except ValueError:
            messagebox.showerror("Save Code", "Weight must be a number between 0.0 and 1.0.")
            return
        desc = self.setting_desc_entry.get().strip()

        # Update configuration
        raw = self.config_mgr.get("leave", "deduction_weights", {})
        if not raw:
            raw = {}
        raw[code] = {"weight": weight, "desc": desc}
        self.config_mgr.set("leave", "deduction_weights", raw)
        self.config_mgr.save()

        messagebox.showinfo("Save Code", f"Leave code '{code}' saved successfully.")
        self._refresh_leave_codes()
        self._refresh_leave()

    def _delete_leave_code(self) -> None:
        code = self.setting_code_entry.get().strip().upper()
        if not code:
            messagebox.showwarning("Delete Code", "Please select or enter a leave code.")
            return
        
        raw = self.config_mgr.get("leave", "deduction_weights", {})
        if not raw or code not in raw:
            messagebox.showwarning("Delete Code", f"Leave code '{code}' not found.")
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete leave code '{code}'?"):
            del raw[code]
            self.config_mgr.set("leave", "deduction_weights", raw)
            self.config_mgr.save()
            
            # Clear entries
            self.setting_code_entry.delete(0, tk.END)
            self.setting_weight_entry.delete(0, tk.END)
            self.setting_desc_entry.delete(0, tk.END)

            messagebox.showinfo("Delete Code", f"Leave code '{code}' deleted.")
            self._refresh_leave_codes()
            self._refresh_leave()

    # --- Helpers ---

    def _refresh_all(self) -> None:
        self._refresh_dashboard()
        self._refresh_register()
        self._refresh_leave()
        self._refresh_files()
        self._refresh_names()
        self._refresh_leave_codes()

    def _run_async(self, func, success_msg: str = "") -> None:
        def task():
            try:
                func()
                if success_msg:
                    self.after(0, lambda: messagebox.showinfo("Success", success_msg))
            except Exception as exc:
                logger.exception("Async task failed")
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
        threading.Thread(target=task, daemon=True).start()

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "Attendance Management System v1.2\n\n"
            "CustomTkinter GUI Migration complete.\n"
            "Import cumulative CSV logs, track attendance, edit leave records,\n"
            "and generate professional reports.\n\n"
            "Compatible with Windows 10/11 and Linux.",
        )


def main():
    app = AttendanceApp()
    app.mainloop()


if __name__ == "__main__":
    main()

"""UI helper utilities."""

import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import tkinter as tk
from tkinter import ttk


def configure_tree_columns(
    tree: ttk.Treeview,
    headers: Dict[str, str],
    widths: Dict[str, int],
    left_align: Optional[set] = None,
    heading_commands: Optional[Dict[str, Any]] = None,
) -> None:
    """Configure Treeview headings and columns; center all except left_align set."""
    left_align = left_align or set()
    heading_commands = heading_commands or {}
    for col, text in headers.items():
        anchor = "w" if col in left_align else "center"
        cmd = heading_commands.get(col)
        if cmd:
            tree.heading(col, text=text, anchor=anchor, command=cmd)
        else:
            tree.heading(col, text=text, anchor=anchor)
        tree.column(col, width=widths.get(col, 100), anchor=anchor)


def open_folder(path: Path) -> None:
    """Open a folder in the system file manager."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Windows":
        subprocess.run(["explorer", str(path)], check=False)
    elif system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def auto_fit_columns(tree: ttk.Treeview, min_width: int = 50, padding: int = 24) -> None:
    """Dynamically adjust columns to fit their longest content (header or rows).
    Enforces stretch=False on all columns to support horizontal scrolling.
    """
    import tkinter.font as tkfont
    style = ttk.Style()
    
    # Try to find style fonts, otherwise fallback to defaults
    heading_font_str = style.lookup("Treeview.Heading", "font") or "{Segoe UI} 12 bold"
    tree_font_str = style.lookup("Treeview", "font") or "{Segoe UI} 12"
    
    try:
        heading_font = tkfont.Font(font=heading_font_str)
    except Exception:
        heading_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        
    try:
        tree_font = tkfont.Font(font=tree_font_str)
    except Exception:
        tree_font = tkfont.Font(family="Segoe UI", size=12)

    columns = tree["columns"]
    for col in columns:
        heading_text = tree.heading(col, "text")
        max_w = heading_font.measure(heading_text)
        
        for item in tree.get_children():
            col_index = columns.index(col)
            values = tree.item(item, "values")
            if values and col_index < len(values):
                val_str = str(values[col_index])
                w = tree_font.measure(val_str)
                if w > max_w:
                    max_w = w
        
        final_w = max(max_w + padding, min_width)
        tree.column(col, width=final_w, stretch=False)


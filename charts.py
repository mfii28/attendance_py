"""Matplotlib chart functions for the Attendance Management System."""

from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

_chart_font_size = 12


def set_chart_font_size(size: int) -> None:
    """Set base font size for matplotlib charts."""
    global _chart_font_size
    _chart_font_size = max(8, size)
    plt.rcParams.update({
        "font.size": _chart_font_size,
        "axes.titlesize": _chart_font_size + 2,
        "axes.labelsize": _chart_font_size,
        "xtick.labelsize": _chart_font_size - 1,
        "ytick.labelsize": _chart_font_size - 1,
        "legend.fontsize": _chart_font_size - 1,
    })


def _apply_theme(fig: Figure, dark: bool = False) -> None:
    bg = "#2b2b2b" if dark else "#ffffff"
    fg = "#ffffff" if dark else "#333333"
    fig.patch.set_facecolor(bg)
    for ax in fig.axes:
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg)
        ax.xaxis.label.set_color(fg)
        ax.yaxis.label.set_color(fg)
        ax.title.set_color(fg)
        for spine in ax.spines.values():
            spine.set_color(fg)


def create_trend_chart(
    metrics: List[Dict],
    title: str = "Attendance Trend",
    dark: bool = False,
) -> Figure:
    """Line chart of monthly attendance rate."""
    fig, ax = plt.subplots(figsize=(8, 4))
    if not metrics:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center", transform=ax.transAxes)
        ax.set_title(title)
        _apply_theme(fig, dark)
        return fig

    labels = [f"{m['year']}-{m['month']:02d}" for m in metrics]
    rates = [m.get("avg_attendance_rate", 0) or 0 for m in metrics]
    late = [m.get("total_late_incidents", 0) or 0 for m in metrics]

    ax.plot(labels, rates, marker="o", color="#2196F3", linewidth=2, label="Attendance %")
    ax2 = ax.twinx()
    ax2.bar(labels, late, alpha=0.3, color="#FF5722", label="Late Incidents")
    ax.set_ylabel("Attendance Rate (%)")
    ax2.set_ylabel("Late Incidents")
    ax.set_title(title)
    ax.set_ylim(0, 100)
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    fig.tight_layout()
    _apply_theme(fig, dark)
    return fig


def create_offenders_chart(
    offenders: List[Dict],
    title: str = "Top Late Offenders",
    dark: bool = False,
) -> Figure:
    """Horizontal bar chart of top late employees."""
    fig, ax = plt.subplots(figsize=(5, 4))
    if not offenders:
        ax.text(0.5, 0.5, "No late incidents", ha="center", va="center", transform=ax.transAxes)
        ax.set_title(title)
        _apply_theme(fig, dark)
        return fig

    names = [o["display_name"][:20] for o in offenders]
    late_days = [o["late_days"] for o in offenders]
    colors = ["#F44336" if d > 5 else "#FFC107" if d >= 2 else "#4CAF50" for d in late_days]

    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, late_days, color=colors, picker=True)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("Late Days")
    ax.set_title(title)
    fig.tight_layout()
    _apply_theme(fig, dark)
    fig._offender_bars = bars  # type: ignore[attr-defined]
    return fig


def embed_chart(parent, figure: Figure, on_pick=None) -> FigureCanvasTkAgg:
    """Embed matplotlib figure in Tkinter widget; optional pick handler for bar clicks."""
    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.draw()
    if on_pick is not None:
        canvas.mpl_connect("pick_event", on_pick)
    return canvas


def close_figure(figure: Figure) -> None:
    """Release matplotlib figure memory."""
    plt.close(figure)


def save_chart(figure: Figure, path: str, dpi: int = 150) -> None:
    """Save figure to file."""
    figure.savefig(path, dpi=dpi, bbox_inches="tight")


set_chart_font_size(12)

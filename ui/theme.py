# -*- coding: utf-8 -*-
"""ui/theme.py — AutoReach v14 design tokens and ttk style setup."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

# ── Color Palette ─────────────────────────────────────────────
BG      = "#0A0E17"   # deep navy-black background
CARD    = "#111827"   # card surface
CARD2   = "#1A2233"   # card surface alt / input bg
ACCENT  = "#3B82F6"   # primary blue
ACCENT2 = "#6366F1"   # indigo for gradients
TEXT    = "#E2E8F0"   # primary text
MUTED   = "#64748B"   # secondary / hint text
GREEN   = "#22C55E"   # success
RED     = "#EF4444"   # danger
AMBER   = "#F59E0B"   # warning
BLUE    = "#60A5FA"   # info blue
PURPLE  = "#A78BFA"   # purple
TEAL    = "#14B8A6"   # teal
PINK    = "#F472B6"   # pink
BORDER  = "#1E2D45"   # card border
GLOW    = "#3B82F633" # accent glow (transparent)

STATUS_COLORS = {
    "queued":    AMBER,
    "sending":   BLUE,
    "sent":      GREEN,
    "failed":    RED,
    "skipped":   MUTED,
    "delivered": TEAL,
    "read":      PURPLE,
    "running":   GREEN,
    "paused":    AMBER,
    "cancelled": RED,
    "completed": MUTED,
    "crashed":   RED,
}

STATUS_ICONS = {
    "queued":    "⏳",
    "sending":   "📤",
    "sent":      "✅",
    "failed":    "❌",
    "skipped":   "⏭",
    "delivered": "✔✔",
    "read":      "👁",
    "running":   "🔄",
    "paused":    "⏸",
    "cancelled": "⏹",
    "completed": "🏁",
    "crashed":   "💥",
    "draft":     "📝",
}


def apply_styles(root: tk.Tk) -> None:
    """Apply global ttk styles to the application."""
    s = ttk.Style(root)
    s.theme_use("clam")

    # ── Default Button ──────────────────────────────────────────
    s.configure("TButton",
                background=CARD2, foreground=TEXT,
                font=("Segoe UI", 9, "bold"), borderwidth=0,
                relief="flat", padding=(10, 7), focuscolor=ACCENT)
    s.map("TButton",
          background=[("active", "#243049"), ("disabled", CARD)],
          foreground=[("disabled", MUTED)])

    # ── Accent (primary action) Button ──────────────────────────
    s.configure("A.TButton",
                background=ACCENT, foreground="#fff",
                font=("Segoe UI", 10, "bold"), padding=(12, 9))
    s.map("A.TButton",
          background=[("active", "#2563EB"), ("pressed", "#1D4ED8")])

    # ── Danger Button ────────────────────────────────────────────
    s.configure("D.TButton",
                background="#450A0A", foreground=RED,
                font=("Segoe UI", 9, "bold"), padding=(10, 7))
    s.map("D.TButton", background=[("active", "#7F1D1D")])

    # ── Warning Button ───────────────────────────────────────────
    s.configure("W.TButton",
                background="#3B2500", foreground=AMBER,
                font=("Segoe UI", 9, "bold"), padding=(10, 7))
    s.map("W.TButton", background=[("active", "#78350F")])

    # ── Success Button ───────────────────────────────────────────
    s.configure("G.TButton",
                background="#052E16", foreground=GREEN,
                font=("Segoe UI", 9, "bold"), padding=(10, 7))
    s.map("G.TButton", background=[("active", "#14532D")])

    # ── Notebook ─────────────────────────────────────────────────
    s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
    s.configure("TNotebook.Tab",
                background=CARD, foreground=MUTED,
                font=("Segoe UI", 9, "bold"),
                padding=[20, 10], borderwidth=0)
    s.map("TNotebook.Tab",
          background=[("selected", CARD2)],
          foreground=[("selected", ACCENT)],
          padding=[("selected", [20, 10])])

    # ── Progress Bars ────────────────────────────────────────────
    s.configure("Horizontal.TProgressbar",
                troughcolor=CARD2, background=ACCENT,
                borderwidth=0, thickness=8, lightcolor=ACCENT, darkcolor=ACCENT)
    s.configure("Green.Horizontal.TProgressbar",
                troughcolor=CARD2, background=GREEN,
                borderwidth=0, thickness=8, lightcolor=GREEN, darkcolor=GREEN)
    s.configure("Vertical.TProgressbar",
                troughcolor=CARD2, background=ACCENT,
                borderwidth=0, thickness=10, lightcolor=ACCENT, darkcolor=ACCENT)

    # ── Entry / Spinbox ──────────────────────────────────────────
    s.configure("TSpinbox",
                background=CARD2, foreground=TEXT,
                fieldbackground=CARD2, bordercolor=BORDER,
                arrowcolor=MUTED, insertcolor=TEXT)
    s.configure("TEntry",
                background=CARD2, foreground=TEXT,
                fieldbackground=CARD2, bordercolor=BORDER,
                insertcolor=TEXT, selectbackground=ACCENT)
    s.map("TEntry", bordercolor=[("focus", ACCENT)])

    # ── Treeview ─────────────────────────────────────────────────
    s.configure("Treeview",
                background=CARD, foreground=TEXT,
                fieldbackground=CARD, rowheight=28,
                borderwidth=0, font=("Segoe UI", 9))
    s.configure("Treeview.Heading",
                background=CARD2, foreground=BLUE,
                font=("Segoe UI", 9, "bold"), borderwidth=0,
                relief="flat", padding=(8, 6))
    s.map("Treeview",
          background=[("selected", ACCENT2)],
          foreground=[("selected", "#fff")])

    # ── Checkbutton ──────────────────────────────────────────────
    s.configure("TCheckbutton",
                background=CARD, foreground=TEXT,
                font=("Segoe UI", 9), focuscolor=ACCENT)
    s.map("TCheckbutton",
          background=[("active", CARD), ("hover", CARD)])

    # ── Scrollbar ────────────────────────────────────────────────
    s.configure("Vertical.TScrollbar",
                background=CARD2, troughcolor=CARD,
                borderwidth=0, arrowcolor=MUTED)
    s.configure("Horizontal.TScrollbar",
                background=CARD2, troughcolor=CARD,
                borderwidth=0, arrowcolor=MUTED)


# ── Reusable UI helpers ────────────────────────────────────────

def scrolled_frame(parent: tk.Widget) -> tuple[tk.Canvas, tk.Frame]:
    """Return (canvas, inner_frame) with styled vertical scrollbar."""
    canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
    vsb    = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    frame  = tk.Frame(canvas, bg=BG)
    fid    = canvas.create_window((0, 0), window=frame, anchor="nw")

    def _resize(e):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(fid, width=e.width)
    canvas.bind("<Configure>", _resize)
    frame.bind("<Configure>", lambda e: canvas.configure(
        scrollregion=canvas.bbox("all")))
    canvas.bind_all("<MouseWheel>",
        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
    return canvas, frame


def card(parent, *, bg=CARD2, padx=14, pady=10, radius=0, **kw) -> tk.Frame:
    """Return a styled card frame."""
    return tk.Frame(parent, bg=bg, padx=padx, pady=pady,
                    relief="flat", bd=0, **kw)


def section_header(parent: tk.Widget, text: str, bg=BG) -> tk.Label:
    lbl = tk.Label(parent, text=text, bg=bg, fg=ACCENT,
                   font=("Segoe UI", 11, "bold"))
    lbl.pack(anchor="w", padx=18, pady=(14, 2))
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(0, 8))
    return lbl


def label(parent, text, size=9, color=TEXT, bold=False, **kw) -> tk.Label:
    font_weight = "bold" if bold else "normal"
    return tk.Label(parent, text=text, bg=kw.pop("bg", BG),
                    fg=color, font=("Segoe UI", size, font_weight), **kw)


def stat_card(parent, title: str, value: str, color: str = TEXT,
              icon: str = "") -> dict:
    """Premium stat card with icon, title, and big value label."""
    f = tk.Frame(parent, bg=CARD2, padx=14, pady=12)
    # Top row: icon + title
    top = tk.Frame(f, bg=CARD2)
    top.pack(fill="x")
    if icon:
        tk.Label(top, text=icon, bg=CARD2, fg=color,
                 font=("Segoe UI", 12)).pack(side="left")
    tk.Label(top, text=f"  {title}", bg=CARD2, fg=MUTED,
             font=("Segoe UI", 8, "bold")).pack(side="left")
    # Value
    lbl = tk.Label(f, text=value, bg=CARD2, fg=color,
                   font=("Segoe UI", 22, "bold"))
    lbl.pack(pady=(4, 0))
    # Bottom accent line
    tk.Frame(f, bg=color, height=2).pack(fill="x", pady=(8, 0))
    return {"frame": f, "label": lbl}


def pill(parent, text: str, color: str, bg=CARD2) -> tk.Label:
    """Colored pill/badge label."""
    return tk.Label(parent, text=f"  {text}  ", bg=color,
                    fg="#fff", font=("Segoe UI", 8, "bold"),
                    relief="flat", padx=2, pady=1)


def icon_button(parent, text: str, cmd, bg=CARD2, fg=TEXT,
                size=9, bold=True) -> tk.Button:
    """Flat icon button with hand cursor."""
    return tk.Button(parent, text=text, command=cmd,
                     bg=bg, fg=fg, relief="flat",
                     font=("Segoe UI", size, "bold" if bold else "normal"),
                     cursor="hand2", padx=10, pady=6,
                     activebackground=ACCENT, activeforeground="#fff",
                     bd=0)

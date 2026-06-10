# -*- coding: utf-8 -*-
"""ui/tab_dashboard.py — Real-time monitoring dashboard."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from ui.theme import (BG, CARD, CARD2, ACCENT, ACCENT2, TEXT, MUTED,
                      GREEN, RED, AMBER, BLUE, PURPLE, TEAL, BORDER,
                      stat_card, section_header, icon_button, STATUS_COLORS)
from analytics.insights import get_insights


_STAT_DEFS = [
    ("Total",    "0", TEXT,  "📨"),
    ("Sent",     "0", GREEN, "✅"),
    ("Failed",   "0", RED,   "❌"),
    ("Queued",   "0", AMBER, "⏳"),
    ("Skipped",  "0", MUTED, "⏭"),
    ("Rate %",   "—", BLUE,  "📈"),
]


class DashboardTab:
    def __init__(self, parent: tk.Frame, app) -> None:
        self.app = app
        self.db  = app.db
        self._stat_labels: dict = {}
        self._build(parent)
        self.refresh()

    def _build(self, parent: tk.Frame) -> None:
        # ── Header row ──────────────────────────────────────────
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(hdr, text="📊  Live Dashboard", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")

        right = tk.Frame(hdr, bg=BG)
        right.pack(side="right")
        self.lbl_ts = tk.Label(right, text="", bg=BG, fg=MUTED,
                               font=("Segoe UI", 8))
        self.lbl_ts.pack(side="right", padx=(8, 0))
        icon_button(right, "🔄 Refresh", self.refresh,
                    bg=CARD2, fg=BLUE, size=8).pack(side="right")

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(0, 10))

        # ── Stat cards ──────────────────────────────────────────
        sf = tk.Frame(parent, bg=BG)
        sf.pack(fill="x", padx=14, pady=(0, 8))
        for i, (nm, val, col, icon) in enumerate(_STAT_DEFS):
            sc = stat_card(sf, nm, val, col, icon)
            sc["frame"].grid(row=0, column=i, padx=6, pady=4, sticky="ew")
            self._stat_labels[nm] = sc["label"]
        for i in range(6):
            sf.columnconfigure(i, weight=1)

        # ── Broadcast Treeview ────────────────────────────────────
        ct_hdr = tk.Frame(parent, bg=BG)
        ct_hdr.pack(fill="x", padx=18, pady=(4, 2))
        tk.Label(ct_hdr, text="📋  Recent Broadcasts", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        tree_frame = tk.Frame(parent, bg=BG)
        tree_frame.pack(fill="x", padx=14, pady=(0, 6))

        cols = ("Name", "Status", "Sent", "Failed", "Pending", "Rate%", "Started")
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                 show="headings", height=6)
        widths = [200, 100, 65, 65, 65, 65, 150]
        anchors = ["w", "center", "center", "center", "center", "center", "center"]
        for col, w, anc in zip(cols, widths, anchors):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=anc, minwidth=w)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="x")
        self.tree.tag_configure("odd",  background=CARD)
        self.tree.tag_configure("even", background=CARD2)
        self.tree.tag_configure("running",   foreground=GREEN)
        self.tree.tag_configure("failed",    foreground=RED)
        self.tree.tag_configure("paused",    foreground=AMBER)
        self.tree.tag_configure("crashed",   foreground=RED)
        self.tree.tag_configure("completed", foreground=MUTED)

        # ── Hourly chart ─────────────────────────────────────────
        chart_hdr = tk.Frame(parent, bg=BG)
        chart_hdr.pack(fill="x", padx=18, pady=(8, 2))
        tk.Label(chart_hdr, text="⏱  Hourly Activity (last 7 days)",
                 bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")

        self.canvas_chart = tk.Canvas(parent, bg=CARD2, height=100,
                                      highlightthickness=0)
        self.canvas_chart.pack(fill="x", padx=14, pady=(0, 6))

        # ── Insights ─────────────────────────────────────────────
        tk.Label(parent, text="💡  Insights & Alerts",
                 bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(4, 2))
        self.insight_frame = tk.Frame(parent, bg=BG)
        self.insight_frame.pack(fill="x", padx=14, pady=(0, 10))

    # ── Refresh ───────────────────────────────────────────────

    def refresh(self) -> None:
        stats = self.db.global_stats()
        total = stats.get("total", 0)
        sent  = stats.get("sent",  0)
        rate  = f"{stats.get('success_rate', 0.0):.1f}%"
        self._stat_labels["Total"].config(text=str(total))
        self._stat_labels["Sent"].config(text=str(sent))
        self._stat_labels["Failed"].config(text=str(stats.get("failed", 0)))
        self._stat_labels["Queued"].config(text=str(stats.get("queued", 0)))
        self._stat_labels["Skipped"].config(text=str(stats.get("skipped", 0)))
        self._stat_labels["Rate %"].config(text=rate)
        self.lbl_ts.config(
            text=f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
        self._refresh_campaigns()
        self._draw_chart()
        self._refresh_insights()

    def _refresh_campaigns(self) -> None:
        self.tree.delete(*self.tree.get_children())
        campaigns = self.db.list_campaigns()[:20]
        for i, c in enumerate(campaigns):
            pending = max(0, c.total_contacts
                         - c.sent_count - c.failed_count - c.skipped_count)
            status_icon = {
                "running": "🔄", "completed": "🏁", "failed": "❌",
                "paused": "⏸", "crashed": "💥", "cancelled": "⏹",
                "draft": "📝",
            }.get(c.status.value, "")
            tags = (c.status.value, "odd" if i % 2 else "even")
            self.tree.insert("", "end", tags=tags, values=(
                c.name[:32],
                f"{status_icon} {c.status.value}",
                c.sent_count, c.failed_count,
                pending,
                f"{c.success_rate:.1f}",
                str(c.started_at)[:16] if c.started_at else "—",
            ))

    def _draw_chart(self) -> None:
        c = self.canvas_chart
        c.delete("all")
        c.update_idletasks()
        W = c.winfo_width() or 860
        H = 90
        PAD_L, PAD_R = 36, 12
        bar_area = W - PAD_L - PAD_R

        activity = self.db.hourly_activity(days=7)
        by_hour: dict[int, int] = {}
        for row in activity:
            h = row["hour"]
            by_hour[h] = by_hour.get(h, 0) + row["sent_count"]

        max_val = max(by_hour.values(), default=1) or 1
        bar_w   = max(3, bar_area // 24)

        # y-axis labels
        for step in [0.0, 0.5, 1.0]:
            y = int(H - step * (H - 16)) + 4
            v = int(step * max_val)
            c.create_line(PAD_L - 4, y, W - PAD_R, y,
                          fill=BORDER, dash=(2, 4))
            c.create_text(PAD_L - 6, y, text=str(v),
                          fill=MUTED, font=("Segoe UI", 6), anchor="e")

        for h in range(24):
            val = by_hour.get(h, 0)
            bh  = max(2, int((val / max_val) * (H - 20))) if val else 2
            x0  = PAD_L + h * bar_w
            x1  = x0 + bar_w - 2
            y0  = H - bh
            col = ACCENT if val else CARD

            # Draw bar with subtle gradient effect (two rects)
            c.create_rectangle(x0, y0, x1, H, fill=col, outline="")
            if val and bh > 4:
                c.create_rectangle(x0, y0, x1, y0 + 3,
                                   fill=BLUE, outline="")

            if h % 6 == 0:
                c.create_text(x0 + bar_w // 2, H + 6,
                              text=f"{h:02d}:00",
                              fill=MUTED, font=("Segoe UI", 6))

        c.create_text(W // 2, H + 15, text="Hour of day",
                      fill=MUTED, font=("Segoe UI", 7))

        if not by_hour:
            c.create_text(W // 2, H // 2,
                          text="No activity data yet — run a broadcast to see stats",
                          fill=MUTED, font=("Segoe UI", 9))

    def _refresh_insights(self) -> None:
        for w in self.insight_frame.winfo_children():
            w.destroy()
        sev_colors  = {"info": BLUE, "warning": AMBER, "critical": RED}
        sev_icons   = {"info": "ℹ", "warning": "⚠", "critical": "🔴"}
        insights = get_insights(self.db)
        if not insights:
            tk.Label(self.insight_frame,
                     text="✅  All systems healthy — no alerts at this time.",
                     bg=BG, fg=GREEN, font=("Segoe UI", 9)).pack(anchor="w", pady=4)
            return
        for ins in insights:
            col  = sev_colors.get(ins.severity, MUTED)
            icon = sev_icons.get(ins.severity, "•")
            row  = tk.Frame(self.insight_frame, bg=CARD2)
            row.pack(fill="x", pady=2)
            # Left color bar
            tk.Frame(row, bg=col, width=4).pack(side="left", fill="y")
            body = tk.Frame(row, bg=CARD2, padx=10, pady=6)
            body.pack(fill="x", expand=True, side="left")
            tk.Label(body, text=f"{icon}  {ins.title}",
                     bg=CARD2, fg=col,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(body, text=ins.description, bg=CARD2, fg=TEXT,
                     font=("Segoe UI", 8), wraplength=820,
                     justify="left").pack(anchor="w")

    def on_focus(self) -> None:
        self.refresh()

# -*- coding: utf-8 -*-
"""ui/tab_log.py — Audit log viewer with search, filter, and live append."""
from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from ui.theme import (BG, CARD, CARD2, ACCENT, TEXT, MUTED,
                      GREEN, RED, AMBER, BLUE, BORDER, PURPLE, icon_button)

_LEVEL_COLORS = {
    "DEBUG":    MUTED,
    "INFO":     BLUE,
    "WARNING":  AMBER,
    "ERROR":    RED,
    "CRITICAL": RED,
}

_LEVEL_ICONS = {
    "DEBUG":    "🔍",
    "INFO":     "ℹ",
    "WARNING":  "⚠",
    "ERROR":    "❌",
    "CRITICAL": "🔴",
}


class LogTab:
    def __init__(self, parent: tk.Frame, app) -> None:
        self.app = app
        self.db  = app.db
        self._line_count = 0
        self._build(parent)

    def _build(self, parent: tk.Frame) -> None:
        # ── Header ──────────────────────────────────────────────
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(hdr, text="📜  Audit Log",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(0, 6))

        # ── Toolbar ──────────────────────────────────────────────
        tb = tk.Frame(parent, bg=CARD2)
        tb.pack(fill="x", padx=14, pady=(0, 4))

        # Level filter buttons
        tk.Label(tb, text="  Level:", bg=CARD2, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", pady=6)

        self.v_level = tk.StringVar(value="ALL")
        for lvl in ["ALL", "INFO", "WARNING", "ERROR", "DEBUG"]:
            col = _LEVEL_COLORS.get(lvl, TEXT)
            rb  = tk.Radiobutton(
                tb, text=lvl, variable=self.v_level, value=lvl,
                command=self._load_db,
                bg=CARD2, fg=col, selectcolor=CARD,
                activebackground=CARD2, activeforeground=col,
                font=("Segoe UI", 8, "bold"),
                indicatoron=False, relief="flat",
                padx=8, pady=4, cursor="hand2")
            rb.pack(side="left", padx=1)

        # Search
        tk.Label(tb, text="  🔍", bg=CARD2, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 2), pady=6)
        self.v_search = tk.StringVar()
        self.v_search.trace_add("write", lambda *_: self._load_db())
        tk.Entry(tb, textvariable=self.v_search, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Segoe UI", 9), width=22).pack(side="left", padx=(0, 8), pady=4)

        # Auto-scroll toggle
        self.v_auto = tk.BooleanVar(value=True)
        tk.Checkbutton(
            tb, text="↓ Auto-scroll", variable=self.v_auto,
            bg=CARD2, fg=GREEN, selectcolor=CARD,
            activebackground=CARD2,
            font=("Segoe UI", 8, "bold")).pack(side="left")

        # Right-side action buttons
        icon_button(tb, "🗑  Clear",
                    self._clear, bg=CARD2, fg=MUTED, size=8).pack(side="right", padx=3, pady=3)
        icon_button(tb, "💾  Export",
                    self._export, bg=CARD2, fg=TEXT, size=8).pack(side="right", padx=3, pady=3)
        icon_button(tb, "📋  Copy All",
                    self._copy_all, bg=CARD2, fg=BLUE, size=8).pack(side="right", padx=3, pady=3)
        icon_button(tb, "⟳  Reload DB",
                    self._load_db, bg=CARD2, fg=ACCENT, size=8).pack(side="right", padx=3, pady=3)

        # ── Text area ────────────────────────────────────────────
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True, padx=14, pady=(0, 0))

        vsb = ttk.Scrollbar(wrap, orient="vertical")
        hsb = ttk.Scrollbar(wrap, orient="horizontal")
        self.txt = tk.Text(
            wrap, bg=CARD, fg=TEXT,
            font=("Consolas", 8),
            relief="flat", padx=14, pady=10,
            wrap="none",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            state="disabled",
            selectbackground=ACCENT,
            insertbackground=ACCENT)
        vsb.config(command=self.txt.yview)
        hsb.config(command=self.txt.xview)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.txt.pack(fill="both", expand=True)

        # Tag colors
        for level, col in _LEVEL_COLORS.items():
            self.txt.tag_configure(level, foreground=col)
        self.txt.tag_configure("ts", foreground=MUTED)
        self.txt.tag_configure("sep", foreground=BORDER)

        # ── Status bar ───────────────────────────────────────────
        sbar = tk.Frame(parent, bg="#080C14")
        sbar.pack(fill="x")
        self.lbl_count = tk.Label(
            sbar, text="0 records",
            bg="#080C14", fg=MUTED,
            font=("Segoe UI", 7), anchor="w", padx=18, pady=4)
        self.lbl_count.pack(side="left")

        self.lbl_live = tk.Label(
            sbar, text="● Live",
            bg="#080C14", fg=GREEN,
            font=("Segoe UI", 7, "bold"), anchor="e", padx=18)
        self.lbl_live.pack(side="right")

    # ── Live append (from scheduler callbacks) ────────────────

    def append(self, level: str, msg: str) -> None:
        """Append a live log line (thread-safe via UI queue)."""
        self._line_count += 1
        self.txt.config(state="normal")
        import datetime
        ts  = datetime.datetime.now().strftime("%H:%M:%S")
        icon = _LEVEL_ICONS.get(level, "•")
        self.txt.insert("end", f"[{ts}] ", "ts")
        self.txt.insert("end", f"{icon} [{level}] ", level)
        self.txt.insert("end", f"{msg}\n")
        if self.v_auto.get():
            self.txt.see("end")
        self.txt.config(state="disabled")
        self.lbl_count.config(text=f"{self._line_count} live entries")

    # ── DB load ───────────────────────────────────────────────

    def _load_db(self) -> None:
        level  = self.v_level.get()
        search = self.v_search.get().strip() or None
        logs   = self.db.query_audit_logs(
            level  = None if level == "ALL" else level,
            search = search,
            limit  = 500,
        )
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)

        for log in logs:
            lv   = log.level.value if hasattr(log.level, "value") else str(log.level)
            ts   = str(log.created_at)[:19]
            icon = _LEVEL_ICONS.get(lv, "•")
            self.txt.insert("end", f"[{ts}] ", "ts")
            self.txt.insert("end", f"{icon} [{lv}] ", lv if lv in _LEVEL_COLORS else "INFO")
            self.txt.insert("end", f"{log.text}\n")

        self.txt.see("end")
        self.txt.config(state="disabled")
        self.lbl_count.config(text=f"{len(logs)} records shown")
        self._line_count = len(logs)

    # ── Actions ───────────────────────────────────────────────

    def _clear(self) -> None:
        self._line_count = 0
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)
        self.txt.config(state="disabled")
        self.lbl_count.config(text="0 records")

    def _copy_all(self) -> None:
        content = self.txt.get("1.0", tk.END)
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(content)
        self.lbl_count.config(text="Copied to clipboard!")
        self.app.root.after(2000, lambda: self.lbl_count.config(
            text=f"{self._line_count} records"))

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("CSV", "*.csv")],
            initialfile="autoreach_log")
        if not path:
            return
        logs = self.db.query_audit_logs(limit=50000)
        with open(path, "w", encoding="utf-8") as f:
            for log in logs:
                lv = log.level.value if hasattr(log.level, "value") else str(log.level)
                f.write(f"[{str(log.created_at)[:19]}] [{lv}] {log.text}\n")
        messagebox.showinfo("Exported",
                            f"✅  {len(logs):,} log entries saved\n→ {path}")

    def _reset_db(self) -> None:
        if messagebox.askyesno(
                "Reset All Logs",
                "⚠  Permanently delete ALL audit log records from the database?\n\n"
                "This cannot be undone.",
                icon="warning"):
            self.db._conn.execute("DELETE FROM audit_logs")
            self.db._conn.commit()
            self._clear()
            messagebox.showinfo("Done", "All audit logs cleared.")

    def on_focus(self) -> None:
        self._load_db()

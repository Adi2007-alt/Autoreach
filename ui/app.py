# -*- coding: utf-8 -*-
"""ui/app.py — Main AutoReach v14 window, tab orchestration."""
from __future__ import annotations
import queue, time
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime

from core.database  import Database
from core.settings  import SettingsManager
from core.scheduler import CampaignScheduler, SchedulerCallbacks
from ui.theme import (apply_styles, BG, CARD, CARD2, ACCENT, ACCENT2,
                      TEXT, MUTED, GREEN, RED, AMBER, BLUE, BORDER, PURPLE)

VERSION = "14.0"


class AutoReachApp:
    """
    Root application controller.
    Owns the notebook, wires callbacks between scheduler and tabs.
    """

    def __init__(self, root: tk.Tk, db: Database,
                 mgr: SettingsManager,
                 scheduler: CampaignScheduler) -> None:
        self.root      = root
        self.db        = db
        self.mgr       = mgr
        self.scheduler = scheduler
        self._ui_q:    queue.Queue = queue.Queue()
        self._dot      = 0
        self._pulse    = 0

        self._build_header()
        self._build_tabs()
        self._wire_scheduler()
        self._poll_ui()
        self._anim_header()
        self._refresh_status()
        self._tick_clock()

    # ── Header ─────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg="#080C14", height=70)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Left: logo + title
        left = tk.Frame(hdr, bg="#080C14")
        left.pack(side="left", padx=20, pady=10)

        tk.Label(left, text="⚡", bg="#080C14", fg=ACCENT,
                 font=("Segoe UI", 20)).pack(side="left", padx=(0, 6))

        title_stack = tk.Frame(left, bg="#080C14")
        title_stack.pack(side="left")
        tk.Label(title_stack, text="AutoReach",
                 fg=TEXT, bg="#080C14",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(title_stack,
                 text="WhatsApp Bulk Messenger  ·  v" + VERSION,
                 fg=MUTED, bg="#080C14",
                 font=("Segoe UI", 8)).pack(anchor="w")

        # Right: clock + status indicator
        right = tk.Frame(hdr, bg="#080C14")
        right.pack(side="right", padx=20)

        self.lbl_clock = tk.Label(right, text="", fg=MUTED, bg="#080C14",
                                  font=("Segoe UI", 9))
        self.lbl_clock.pack(anchor="e")

        self.lbl_hdr = tk.Label(right, text="● IDLE",
                                fg=AMBER, bg="#080C14",
                                font=("Segoe UI", 9, "bold"))
        self.lbl_hdr.pack(anchor="e")

        # Bottom border gradient effect (two lines)
        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

    # ── Tabs ───────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        from ui.tab_dashboard import DashboardTab
        from ui.tab_send      import SendTab
        from ui.tab_campaigns import CampaignsTab
        from ui.tab_contacts  import ContactsTab
        from ui.tab_log       import LogTab
        from ui.tab_settings  import SettingsTab
        from ui.tab_help      import HelpTab

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=0, pady=0)
        self._nb = nb

        tabs_def = [
            ("📊  Dashboard",  DashboardTab),
            ("✉  Send",        SendTab),
            ("📋  Broadcasts", CampaignsTab),
            ("👥  Contacts",   ContactsTab),
            ("📜  Log",        LogTab),
            ("⚙  Settings",   SettingsTab),
            ("❓  Help",       HelpTab),
        ]
        self._tabs: dict = {}
        for label, Cls in tabs_def:
            frame = tk.Frame(nb, bg=BG)
            nb.add(frame, text=f" {label} ")
            try:
                self._tabs[label] = Cls(frame, app=self)
            except Exception as exc:
                tk.Label(frame, text=f"⚠  Tab load error:\n{exc}",
                         bg=BG, fg=RED,
                         font=("Consolas", 9),
                         justify="left").pack(padx=30, pady=30, anchor="w")

        nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, _=None) -> None:
        idx   = self._nb.index("current")
        label = list(self._tabs.keys())[idx]
        tab   = self._tabs.get(label)
        if tab and hasattr(tab, "on_focus"):
            tab.on_focus()

    # ── Scheduler callbacks ────────────────────────────────────

    def _wire_scheduler(self) -> None:
        self.scheduler._cb = SchedulerCallbacks(
            on_status   = lambda m:       self._ui_q.put(("status", m)),
            on_log      = lambda lv, m:   self._ui_q.put(("log", lv, m)),
            on_stats    = lambda:         self._ui_q.put(("stats",)),
            on_done     = lambda c, st:   self._ui_q.put(("done", c, st)),
            on_progress = lambda c, t, e: self._ui_q.put(("progress", c, t, e)),
        )

    # ── UI poll loop ───────────────────────────────────────────

    def _poll_ui(self) -> None:
        try:
            while True:
                item = self._ui_q.get_nowait()
                cmd  = item[0]
                if cmd == "status":
                    self._set_status(item[1])
                elif cmd == "log":
                    self._dispatch_log(item[1], item[2])
                elif cmd == "stats":
                    self._refresh_stats()
                elif cmd == "done":
                    self._on_campaign_done(item[1], item[2])
                elif cmd == "progress":
                    self._on_progress(item[1], item[2], item[3])
        except queue.Empty:
            pass
        self.root.after(50, self._poll_ui)

    def _set_status(self, msg: str) -> None:
        self.lbl_hdr.config(text=msg)
        tab = self._tabs.get("✉  Send")
        if tab and hasattr(tab, "set_status"):
            tab.set_status(msg)

    def _dispatch_log(self, level: str, msg: str) -> None:
        tab = self._tabs.get("📜  Log")
        if tab and hasattr(tab, "append"):
            tab.append(level, msg)

    def _refresh_stats(self) -> None:
        tab = self._tabs.get("📊  Dashboard")
        if tab and hasattr(tab, "refresh"):
            tab.refresh()
        tab2 = self._tabs.get("✉  Send")
        if tab2 and hasattr(tab2, "refresh_stats"):
            tab2.refresh_stats()

    def _on_campaign_done(self, campaign_id: int, status: str) -> None:
        self._refresh_stats()
        tab_c = self._tabs.get("📋  Broadcasts")
        if tab_c and hasattr(tab_c, "refresh"):
            tab_c.refresh()
        tab_s = self._tabs.get("✉  Send")
        if tab_s and hasattr(tab_s, "on_campaign_done"):
            tab_s.on_campaign_done(status)

    def _on_progress(self, current: int, total: int, eta: float) -> None:
        tab = self._tabs.get("✉  Send")
        if tab and hasattr(tab, "set_progress"):
            tab.set_progress(current, total, eta)

    def _refresh_status(self) -> None:
        self._refresh_stats()
        self.root.after(3000, self._refresh_status)

    # ── Clock ─────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        now = datetime.now().strftime("%a  %d %b  %H:%M:%S")
        self.lbl_clock.config(text=now)
        self.root.after(1000, self._tick_clock)

    # ── Header animation ───────────────────────────────────────

    def _anim_header(self) -> None:
        running = self.scheduler.is_running
        if running:
            dots = ["● ", "◉ ", "○ ", "◉ "]
            self._dot = (self._dot + 1) % 4
            cur = self.lbl_hdr.cget("text")
            # replace leading dot
            if cur and cur[0] in "●○◉":
                new = dots[self._dot] + cur.lstrip("●○◉ ")
                self.lbl_hdr.config(text=new, fg=GREEN)
        else:
            self.lbl_hdr.config(fg=AMBER)
        self.root.after(500, self._anim_header)

    # ── Window close ──────────────────────────────────────────

    def on_close(self) -> None:
        if self.scheduler.is_running:
            if not messagebox.askyesno(
                    "Broadcast Running",
                    "A broadcast is currently running.\n\nStop it and exit?",
                    icon="warning"):
                return
            self.scheduler.cancel()
        self.mgr.save()
        self.root.after(400, self.root.destroy)

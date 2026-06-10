# -*- coding: utf-8 -*-
"""ui/tab_settings.py — All application settings including PIN lock."""
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from core.settings import SettingsManager
from security.auth import PINLock
from ui.theme import (BG, CARD, CARD2, ACCENT, TEXT, MUTED, GREEN,
                      RED, AMBER, BLUE, PURPLE, BORDER, apply_styles, icon_button)


class SettingsTab:
    """Settings tab: delays, limits, PIN lock, backup, adapter mode."""

    def __init__(self, parent: tk.Frame, app) -> None:
        self._app   = app
        self._mgr: SettingsManager = app.mgr
        self._s     = self._mgr.settings
        self._vars: dict = {}

        apply_styles(parent.winfo_toplevel())
        self._build(parent)

    # ── Build ─────────────────────────────────────────────────

    def _build(self, parent: tk.Frame) -> None:
        # ── Scrollable canvas ────────────────────────────────────
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        wid   = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(wid, width=e.width)
        canvas.bind("<Configure>", on_resize)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ── Page title ───────────────────────────────────────────
        hdr = tk.Frame(inner, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(hdr, text="⚙  Settings", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        icon_button(hdr, "↺ Reset to Defaults", self._reset_defaults,
                    bg=CARD2, fg=AMBER, size=8).pack(side="right")
        tk.Frame(inner, bg=ACCENT, height=2).pack(fill="x", padx=20)

        # ── Sections ─────────────────────────────────────────────
        self._build_timing(inner)
        self._build_limits(inner)
        self._build_adapter(inner)
        self._build_pin(inner)
        self._build_backup(inner)
        self._build_advanced(inner)
        self._build_data_management(inner)
        self._build_save_btn(inner)

    # ── Section helpers ───────────────────────────────────────

    def _section(self, parent: tk.Frame, title: str,
                 color: str = ACCENT) -> tk.Frame:
        """Card-style section with left color accent bar."""
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="x", padx=20, pady=(12, 0))

        # Title row
        title_row = tk.Frame(outer, bg=BG)
        title_row.pack(fill="x", pady=(0, 4))
        tk.Frame(title_row, bg=color, width=4, height=20).pack(
            side="left", fill="y", padx=(0, 8))
        tk.Label(title_row, text=title, bg=BG, fg=color,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        # Body card
        body = tk.Frame(outer, bg=CARD, relief="flat", bd=0)
        body.pack(fill="x")
        return body

    def _row(self, parent: tk.Frame, label: str, widget_factory,
             row: int, tip: str = "") -> tk.Widget:
        tk.Label(parent, text=label, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9), anchor="w",
                 width=28).grid(row=row, column=0, padx=(16, 6), pady=6, sticky="w")
        w = widget_factory(parent)
        w.grid(row=row, column=1, padx=6, pady=6, sticky="ew")
        if tip:
            tk.Label(parent, text=tip, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 7.5),
                     wraplength=280,
                     justify="left").grid(
                         row=row, column=2, padx=(4, 16), sticky="w")
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=2)
        return w

    def _dvar(self, name: str, default=None):
        """Get or create a tk variable mapped to a setting key."""
        if name not in self._vars:
            val = getattr(self._s, name, default)
            if isinstance(val, bool):
                v = tk.BooleanVar(value=val)
            elif isinstance(val, float):
                v = tk.DoubleVar(value=val)
            elif isinstance(val, int):
                v = tk.IntVar(value=val)
            else:
                v = tk.StringVar(value=str(val) if val is not None else "")
            self._vars[name] = v
        return self._vars[name]

    # ── Sections ──────────────────────────────────────────────

    def _build_timing(self, parent: tk.Frame) -> None:
        sec = self._section(parent, "⏱  Timing & Delays", BLUE)

        self._row(sec, "Min delay between messages (s)",
                  lambda p: ttk.Spinbox(p, from_=1.0, to=120.0, increment=0.5,
                                        textvariable=self._dvar("dmin", 45), width=10),
                  row=0, tip="Minimum seconds between sends. Lower = faster but riskier.")

        self._row(sec, "Max delay between messages (s)",
                  lambda p: ttk.Spinbox(p, from_=1.0, to=300.0, increment=0.5,
                                        textvariable=self._dvar("dmax", 90), width=10),
                  row=1, tip="A random value between min and max is chosen each time.")

        self._row(sec, "Message variation (anti-spam)",
                  lambda p: ttk.Checkbutton(p, text="Append invisible characters",
                                            variable=self._dvar("vary", True)),
                  row=2, tip="Adds random zero-width chars to avoid duplicate detection.")

        self._row(sec, "Page-ready timeout (s)",
                  lambda p: ttk.Spinbox(p, from_=5, to=120, increment=5,
                                        textvariable=self._dvar("load", 25), width=10),
                  row=3, tip="Max seconds to wait for WhatsApp Web to load a chat.")

        self._row(sec, "Post-send pause (s)",
                  lambda p: ttk.Spinbox(p, from_=0, to=30, increment=1,
                                        textvariable=self._dvar("postsend", 2), width=10),
                  row=4, tip="Extra pause after each send before moving to next contact.")

    def _build_limits(self, parent: tk.Frame) -> None:
        sec = self._section(parent, "📊  Rate Limits", AMBER)

        self._row(sec, "Daily send limit  (0 = unlimited)",
                  lambda p: ttk.Spinbox(p, from_=0, to=1000, increment=5,
                                        textvariable=self._dvar("dlimit", 30), width=10),
                  row=0, tip="Max messages per calendar day. Resets at midnight.")

        self._row(sec, "Hourly send limit  (0 = unlimited)",
                  lambda p: ttk.Spinbox(p, from_=0, to=200, increment=5,
                                        textvariable=self._dvar("rate_limit_per_hour", 0), width=10),
                  row=1, tip="Max messages per hour. 0 = no hourly cap.")

        self._row(sec, "Max retries per message",
                  lambda p: ttk.Spinbox(p, from_=0, to=10, increment=1,
                                        textvariable=self._dvar("retries", 2), width=10),
                  row=2, tip="How many times to retry a failed send before marking it 'failed'.")

        self._row(sec, "Connection delay (s)",
                  lambda p: ttk.Spinbox(p, from_=3, to=30, increment=1,
                                        textvariable=self._dvar("conn_delay", 7), width=10),
                  row=3, tip="Seconds to wait after opening browser before starting to type.")

    def _build_adapter(self, parent: tk.Frame) -> None:
        sec = self._section(parent, "🔌  Adapter & Mode", PURPLE)

        self._row(sec, "Dry-run mode",
                  lambda p: ttk.Checkbutton(p, text="Simulate sends (no browser opened)",
                                            variable=self._dvar("dry_run", False)),
                  row=0, tip="Safe testing mode — messages are simulated, nothing is sent.")

        self._row(sec, "Health check before broadcast",
                  lambda p: ttk.Checkbutton(p, text="Verify WhatsApp Web is reachable",
                                            variable=self._dvar("health_check", True)),
                  row=1, tip="Quick connectivity test before starting each broadcast.")

        self._row(sec, "Stop on first failure",
                  lambda p: ttk.Checkbutton(p, text="Halt broadcast on first unrecoverable error",
                                            variable=self._dvar("stop_on_fail", False)),
                  row=2, tip="If enabled, the entire broadcast stops after the first failure.")

    def _build_pin(self, parent: tk.Frame) -> None:
        sec = self._section(parent, "🔒  PIN Lock  (Optional)", RED)

        self._row(sec, "Require PIN on launch",
                  lambda p: ttk.Checkbutton(p, text="Enable PIN lock",
                                            variable=self._dvar("pin_lock_enabled", False)),
                  row=0, tip="Prompt for PIN each time the app is opened.")

        btn_row = tk.Frame(sec, bg=CARD)
        btn_row.grid(row=1, column=0, columnspan=3,
                     padx=16, pady=(2, 10), sticky="w")

        self._lbl_pin_status = tk.Label(
            btn_row, text=self._pin_status_text(),
            bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self._lbl_pin_status.pack(side="left", padx=(0, 14))

        icon_button(btn_row, "🔑 Set / Change PIN", self._change_pin,
                    bg=ACCENT, fg="#000", size=9).pack(side="left", padx=4)
        icon_button(btn_row, "🗑 Clear PIN", self._clear_pin,
                    bg="#450A0A", fg=RED, size=9).pack(side="left", padx=4)

    def _build_backup(self, parent: tk.Frame) -> None:
        sec = self._section(parent, "💾  Database Backup", GREEN)

        self._row(sec, "Auto-backup before broadcast",
                  lambda p: ttk.Checkbutton(p, text="Enabled  (recommended)",
                                            variable=self._dvar("backup_on_start", True)),
                  row=0)

        self._row(sec, "Auto-backup after broadcast",
                  lambda p: ttk.Checkbutton(p, text="Enabled",
                                            variable=self._dvar("backup_on_end", True)),
                  row=1)

        self._row(sec, "Max backup files to keep",
                  lambda p: ttk.Spinbox(p, from_=1, to=50, increment=1,
                                        textvariable=self._dvar("max_backup_count", 10), width=8),
                  row=2, tip="Oldest backups are auto-deleted when this limit is exceeded.")

        btn_row = tk.Frame(sec, bg=CARD)
        btn_row.grid(row=3, column=0, columnspan=3,
                     padx=16, pady=(2, 10), sticky="w")
        icon_button(btn_row, "🗄  Backup Now", self._backup_now,
                    bg="#052E16", fg=GREEN, size=9).pack(side="left")

    def _build_advanced(self, parent: tk.Frame) -> None:
        sec = self._section(parent, "🛠  Advanced", MUTED)

        tk.Label(sec, text="  ℹ  Logs are written to autoreach.log and the 📜 Log tab.",
                 bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).grid(
                     row=0, column=0, columnspan=3,
                     padx=16, pady=(8, 2), sticky="w")

        self._row(sec, "Screenshot on failure",
                  lambda p: ttk.Checkbutton(p, text="Save browser screenshot when a send fails",
                                            variable=self._dvar("screenshot_on_fail", True)),
                  row=1)

        self._row(sec, "Human-like delays",
                  lambda p: ttk.Checkbutton(p, text="Add Gaussian jitter to delays",
                                            variable=self._dvar("human_delays", True)),
                  row=2, tip="Randomises send timing to reduce automation fingerprinting.")

        self._row(sec, "Diagnostic logging",
                  lambda p: ttk.Checkbutton(p, text="Log every sub-step (verbose mode)",
                                            variable=self._dvar("diagnostic", False)),
                  row=3, tip="Very detailed per-step logging. May slow down sends.")

        self._row(sec, "Broadcast crash recovery",
                  lambda p: ttk.Checkbutton(p, text="Auto-resume interrupted broadcasts on launch",
                                            variable=self._dvar("campaign_recovery", True)),
                  row=4)

    def _build_data_management(self, parent: tk.Frame) -> None:
        sec = self._section(parent, "⚠️  Data Management", RED)

        tk.Label(sec, text="  WARNING: Factory Reset will permanently delete all contacts, broadcasts, logs, and messages.",
                 bg=CARD, fg=RED, font=("Segoe UI", 8, "bold")).grid(
                     row=0, column=0, columnspan=3, padx=16, pady=(8, 2), sticky="w")

        btn_row = tk.Frame(sec, bg=CARD)
        btn_row.grid(row=1, column=0, columnspan=3, padx=16, pady=(2, 10), sticky="w")
        icon_button(btn_row, "🗑  Factory Reset", self._factory_reset,
                    bg="#450A0A", fg=RED, size=9).pack(side="left")

    def _build_save_btn(self, parent: tk.Frame) -> None:
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=20, pady=(16, 24))

        self._lbl_saved = tk.Label(bar, text="", bg=BG, fg=GREEN,
                                   font=("Segoe UI", 9, "bold"))
        self._lbl_saved.pack(side="right", padx=(0, 16))

        icon_button(bar, "💾  Save Settings", self._save,
                    bg=ACCENT, fg="#fff", size=10).pack(side="right", ipady=4)

    # ── Actions ───────────────────────────────────────────────

    def _save(self) -> None:
        s = self._s
        for key, var in self._vars.items():
            if hasattr(s, key):
                try:
                    cur = getattr(s, key)
                    raw = var.get()
                    if isinstance(cur, bool):
                        setattr(s, key, bool(raw))
                    elif isinstance(cur, int):
                        setattr(s, key, int(float(raw)))
                    elif isinstance(cur, float):
                        setattr(s, key, float(raw))
                    else:
                        setattr(s, key, str(raw))
                except (ValueError, tk.TclError):
                    pass
        self._mgr.save()
        self._lbl_saved.config(text="✅  Settings saved")
        self._lbl_saved.after(3000, lambda: self._lbl_saved.config(text=""))

    def _reset_defaults(self) -> None:
        if messagebox.askyesno("Reset Settings",
                               "Reset all settings to their default values?\n\n"
                               "Your PIN and database will not be affected.",
                               icon="warning"):
            from core.settings import Settings
            defaults = Settings()
            for key, var in self._vars.items():
                if hasattr(defaults, key):
                    try:
                        var.set(getattr(defaults, key))
                    except Exception:
                        pass
            self._lbl_saved.config(text="↺  Defaults loaded — click Save to apply")

    def _backup_now(self) -> None:
        try:
            path = self._app.db.backup("manual")
            messagebox.showinfo("Backup Complete", f"✅  Backup saved:\n{path}")
        except Exception as e:
            messagebox.showerror("Backup Failed", str(e))

    def _factory_reset(self) -> None:
        if messagebox.askyesno("Factory Reset",
                               "Are you absolutely sure you want to factory reset?\n\n"
                               "This will permanently delete all Broadcasts, Contacts, "
                               "and Logs from the database.\n\n"
                               "This action CANNOT be undone.", icon="warning"):
            try:
                self._app.db.factory_reset()
                self._reset_defaults()
                messagebox.showinfo("Factory Reset", "✅  Factory Reset complete. The application data has been wiped.")
            except Exception as e:
                messagebox.showerror("Reset Error", f"Failed to reset database:\n{e}")

    def _pin_status_text(self) -> str:
        pin_lock = PINLock(self._mgr)
        return "🔒  PIN is currently SET" if pin_lock.is_enabled() else "🔓  No PIN set"

    def _change_pin(self) -> None:
        from tkinter import simpledialog
        pin_lock = PINLock(self._mgr)
        if pin_lock.is_enabled():
            old = simpledialog.askstring(
                "Current PIN", "Enter your current PIN:", show="*",
                parent=self._app.root)
            if old is None:
                return
            if not pin_lock.verify(old):
                messagebox.showerror("Wrong PIN", "Incorrect current PIN.")
                return
        new_pin = simpledialog.askstring(
            "Set New PIN", "Enter new PIN (4–12 digits):", show="*",
            parent=self._app.root)
        if new_pin is None:
            return
        confirm = simpledialog.askstring(
            "Confirm PIN", "Re-enter the new PIN to confirm:", show="*",
            parent=self._app.root)
        if new_pin != confirm:
            messagebox.showerror("PIN Mismatch", "The two PINs you entered do not match.")
            return
        pin_lock.set_pin(new_pin)
        self._lbl_pin_status.config(text=self._pin_status_text())
        messagebox.showinfo("PIN Set", "✅  PIN has been set successfully.")

    def _clear_pin(self) -> None:
        from tkinter import simpledialog
        pin_lock = PINLock(self._mgr)
        if not pin_lock.is_enabled():
            messagebox.showinfo("No PIN", "No PIN is currently set.")
            return
        old = simpledialog.askstring(
            "Clear PIN", "Enter your current PIN to remove it:", show="*",
            parent=self._app.root)
        if old is None:
            return
        if not pin_lock.verify(old):
            messagebox.showerror("Wrong PIN", "Incorrect PIN.")
            return
        pin_lock.remove()
        self._lbl_pin_status.config(text=self._pin_status_text())
        messagebox.showinfo("PIN Removed", "✅  PIN lock has been removed.")

    def on_focus(self) -> None:
        pass

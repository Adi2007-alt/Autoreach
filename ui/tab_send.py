# -*- coding: utf-8 -*-
"""ui/tab_send.py — Quick-send tab, v14.2 redesign."""
from __future__ import annotations
import os, threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from datetime import date, datetime, timedelta

from core.phone  import batch_validate
from core.models import Campaign, Message, CampaignStatus
from ui.theme    import (BG, CARD, CARD2, ACCENT, TEXT, MUTED,
                          GREEN, RED, AMBER, BLUE, BORDER, PURPLE,
                          icon_button, STATUS_COLORS)

_DEFAULT_MSG = ("Hello 👋\n\n"
                "I hope this message finds you well.\n\n"
                "Type your personalised message here.\n"
                "This will be sent to each contact individually.")

_INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060"]


class SendTab:
    def __init__(self, parent: tk.Frame, app) -> None:
        self.app   = app
        self.db    = app.db
        self.mgr   = app.mgr
        self.sched = app.scheduler
        self._numbers:     list[str] = []
        self._campaign_id: int       = 0
        self._build(parent)
        self.refresh_stats()

    # ══════════════════════════════════════════════════════════════
    #  Build
    # ══════════════════════════════════════════════════════════════

    def _build(self, P: tk.Frame) -> None:
        # ── Page header ───────────────────────────────────────────
        hdr = tk.Frame(P, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(hdr, text="✉  Quick Send", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Frame(P, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(0, 10))

        # ── Two-column layout: 60 / 40 ────────────────────────────
        cols = tk.Frame(P, bg=BG)
        cols.pack(fill="both", expand=True, padx=14)
        left  = tk.Frame(cols, bg=BG)
        right = tk.Frame(cols, bg=BG)
        left.pack(side="left",  fill="both", expand=True, padx=(0, 8))
        right.pack(side="right", fill="y",   padx=(8, 0), ipadx=10)

        self._build_message(left)
        self._build_contacts(left)
        self._build_campaign(left)
        self._build_actions(left)
        self._build_stats_sidebar(right)
        self._build_status_bar(P)

    # ── Message box ───────────────────────────────────────────────

    def _build_message(self, parent: tk.Frame) -> None:
        # Header row
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="✉  Message Template",
                 bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")

        s = self.mgr.settings
        self.v_vary = tk.BooleanVar(value=getattr(s, "vary", True))
        tk.Checkbutton(hdr, text="🔀 Vary (anti-spam)",
                       variable=self.v_vary,
                       bg=BG, fg=PURPLE, selectcolor=CARD2,
                       activebackground=BG,
                       font=("Segoe UI", 8)).pack(side="right", padx=4)
        icon_button(hdr, "↺ Reset", self._reset_message,
                    bg=CARD2, fg=MUTED, size=8).pack(side="right", padx=4)

        # Message text area
        mf = tk.Frame(parent, bg=BORDER, bd=1, relief="flat")
        mf.pack(fill="both", expand=True, pady=(0, 2))
        sc = ttk.Scrollbar(mf, orient="vertical")
        sc.pack(side="right", fill="y")
        self.msg_box = tk.Text(
            mf, height=9, bg=CARD, fg=TEXT,
            insertbackground=ACCENT, font=("Segoe UI", 10),
            relief="flat", padx=14, pady=10, undo=True,
            wrap="word", yscrollcommand=sc.set,
            selectbackground=ACCENT, selectforeground="#fff")
        self.msg_box.pack(fill="both", expand=True)
        sc.config(command=self.msg_box.yview)
        self.msg_box.insert("1.0", _DEFAULT_MSG)
        self.msg_box.bind("<KeyRelease>", self._char_count)

        # Counter
        self.lbl_chars = tk.Label(parent, text="", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 7), anchor="e")
        self.lbl_chars.pack(fill="x", pady=(0, 6))
        self._char_count()

    # ── Contacts section ──────────────────────────────────────────

    def _build_contacts(self, parent: tk.Frame) -> None:
        f = self._card(parent, "👥  Contact List")

        row1 = tk.Frame(f, bg=CARD)
        row1.pack(fill="x", padx=14, pady=(8, 4))
        self.lbl_loaded = tk.Label(
            row1, text="No list loaded  ·  Import a .txt or .csv file",
            bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_loaded.pack(side="left")
        icon_button(row1, "✕ Clear", self._reset_list,
                    bg=CARD2, fg=RED, size=8).pack(side="right")

        btns = tk.Frame(f, bg=CARD)
        btns.pack(fill="x", padx=14, pady=(0, 10))
        self._big_btn(btns, "📁  Import Contacts", self.do_import,
                      bg=ACCENT, fg="#fff").pack(side="left", padx=(0, 6))
        icon_button(btns, "🚫 Blacklist", self.do_blacklist,
                    bg=CARD2, fg=RED).pack(side="left")

    # ── Campaign settings ─────────────────────────────────────────

    def _build_campaign(self, parent: tk.Frame) -> None:
        f = self._card(parent, "📋  Broadcast Settings")

        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x", padx=14, pady=(8, 4))
        tk.Label(row, text="Name:", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        self.v_camp_name = tk.StringVar(value=f"Broadcast {date.today()}")
        tk.Entry(row, textvariable=self.v_camp_name, bg=CARD2, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Segoe UI", 9), width=28).pack(side="left", fill="x", expand=True)
        icon_button(row, "↺", lambda: self.v_camp_name.set(f"Broadcast {date.today()}"),
                    bg=CARD2, fg=MUTED, size=8).pack(side="left", padx=4)

        mrow = tk.Frame(f, bg=CARD)
        mrow.pack(fill="x", padx=14, pady=(0, 10))
        self.v_dry = tk.BooleanVar(value=self.mgr.settings.dry_run)
        tk.Checkbutton(mrow, text="🧪  Dry-Run mode (no real sends, safe to test)",
                       variable=self.v_dry,
                       bg=CARD, fg=BLUE, selectcolor=CARD2,
                       activebackground=CARD,
                       font=("Segoe UI", 9)).pack(side="left")

    # ── Action buttons ────────────────────────────────────────────

    def _build_actions(self, parent: tk.Frame) -> None:
        f = self._card(parent, "🚀  Actions")

        # Primary action row
        prow = tk.Frame(f, bg=CARD)
        prow.pack(fill="x", padx=14, pady=(8, 4))
        self.btn_start = self._big_btn(
            prow, "▶  START BROADCAST", self.do_start,
            bg="#16A34A", fg="#fff", bold=True, size=11)
        self.btn_start.pack(fill="x", ipady=4)

        # Secondary row
        srow = tk.Frame(f, bg=CARD)
        srow.pack(fill="x", padx=14, pady=(2, 4))
        self.btn_pause = icon_button(srow, "⏸  Pause",  self.do_pause,
                                     bg="#3B2500", fg=AMBER)
        self.btn_stop  = icon_button(srow, "⏹  Stop",   self.do_stop,
                                     bg="#450A0A", fg=RED)
        self.btn_pause.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_stop.pack(side="left",  fill="x", expand=True)
        self.btn_pause.config(state="disabled")

        # Utility row
        urow = tk.Frame(f, bg=CARD)
        urow.pack(fill="x", padx=14, pady=(2, 10))
        self.btn_test  = icon_button(urow, "🔬 Test 1",   self.do_test,  bg=CARD2, fg=BLUE)
        self.btn_retry = icon_button(urow, "🔁 Retry",    self.do_retry, bg=CARD2, fg=AMBER)
        self.btn_exp   = icon_button(urow, "💾 Export",   self.do_export,bg=CARD2, fg=TEXT)
        for b in [self.btn_test, self.btn_retry, self.btn_exp]:
            b.pack(side="left", fill="x", expand=True, padx=2)

        tk.Label(f,
                 text="⚠  Emergency stop: move mouse to TOP-LEFT corner of screen",
                 bg=CARD, fg=RED, font=("Segoe UI", 7)).pack(pady=(0, 6))

    # ── Stats sidebar ─────────────────────────────────────────────

    def _build_stats_sidebar(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="📊  Live Stats",
                 bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

        self._sl: dict = {}
        defs = [
            ("Loaded",    "0",     TEXT,  "📋"),
            ("Sent",      "0",     GREEN, "✅"),
            ("Failed",    "0",     RED,   "❌"),
            ("Remaining", "0",     AMBER, "⏳"),
            ("ETA",       "--:--", BLUE,  "⏱"),
        ]
        for nm, val, col, icon in defs:
            f = tk.Frame(parent, bg=CARD2, padx=12, pady=10)
            f.pack(fill="x", pady=3)
            top = tk.Frame(f, bg=CARD2)
            top.pack(fill="x")
            tk.Label(top, text=icon, bg=CARD2, fg=col,
                     font=("Segoe UI", 10)).pack(side="left")
            tk.Label(top, text=f"  {nm}", bg=CARD2, fg=MUTED,
                     font=("Segoe UI", 7, "bold")).pack(side="left")
            lbl = tk.Label(f, text=val, bg=CARD2, fg=col,
                           font=("Segoe UI", 18, "bold"))
            lbl.pack()
            tk.Frame(f, bg=col, height=2).pack(fill="x", pady=(4, 0))
            self._sl[nm] = lbl

        # Progress bar
        tk.Label(parent, text="Progress", bg=BG, fg=MUTED,
                 font=("Segoe UI", 7)).pack(anchor="w", pady=(10, 2))
        self.v_prog = tk.DoubleVar(value=0)
        self.prog_bar = ttk.Progressbar(parent, variable=self.v_prog,
                                        maximum=100, orient="horizontal",
                                        length=160,
                                        style="Green.Horizontal.TProgressbar")
        self.prog_bar.pack(fill="x")
        self.lbl_pct = tk.Label(parent, text="0%", bg=BG, fg=GREEN,
                                font=("Segoe UI", 8, "bold"))
        self.lbl_pct.pack(anchor="e")

        icon_button(parent, "↺ Reset Stats", self._reset_stats,
                    bg=CARD2, fg=MUTED, size=8).pack(pady=(10, 0), fill="x")

    # ── Status bar ────────────────────────────────────────────────

    def _build_status_bar(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(8, 0))
        bar = tk.Frame(parent, bg="#080C14")
        bar.pack(fill="x")
        self.lbl_status = tk.Label(
            bar, text="● Idle  ·  Import a contact list to begin",
            bg="#080C14", fg=AMBER,
            font=("Segoe UI", 9, "bold"), anchor="w", padx=18, pady=6)
        self.lbl_status.pack(fill="x")

    # ── Helpers ───────────────────────────────────────────────────

    def _card(self, parent: tk.Frame, title: str) -> tk.Frame:
        tk.Label(parent, text=title, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))
        f = tk.Frame(parent, bg=CARD, relief="flat", bd=0)
        f.pack(fill="x", pady=(0, 4))
        return f

    def _big_btn(self, parent, text, cmd, bg=CARD2, fg=TEXT,
                 bold=False, size=9) -> tk.Button:
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg=fg, relief="flat",
                         font=("Segoe UI", size, "bold" if bold else "normal"),
                         cursor="hand2", padx=10, pady=8,
                         activebackground=ACCENT, activeforeground="#fff", bd=0)

    def _char_count(self, _=None) -> None:
        t = self.msg_box.get("1.0", tk.END).strip()
        words = len(t.split()) if t else 0
        chars = len(t)
        lines = t.count("\n") + 1 if t else 0
        self.lbl_chars.config(
            text=f"Lines: {lines}  ·  Words: {words}  ·  Chars: {chars}")

    # ══════════════════════════════════════════════════════════════
    #  Reset actions
    # ══════════════════════════════════════════════════════════════

    def _reset_message(self) -> None:
        if messagebox.askyesno("Reset Message",
                               "Clear message and restore the default template?"):
            self.msg_box.delete("1.0", tk.END)
            self.msg_box.insert("1.0", _DEFAULT_MSG)
            self._char_count()

    def _reset_list(self) -> None:
        if messagebox.askyesno("Clear List", "Remove all loaded numbers?"):
            self._numbers = []
            self.lbl_loaded.config(
                text="No list loaded  ·  Import a .txt or .csv file",
                fg=MUTED)
            self._sl["Loaded"].config(text="0")

    def _reset_stats(self) -> None:
        for key, lbl in self._sl.items():
            lbl.config(text="0" if key != "ETA" else "--:--")
        self.v_prog.set(0)
        self.lbl_pct.config(text="0%")

    # ══════════════════════════════════════════════════════════════
    #  Core actions
    # ══════════════════════════════════════════════════════════════

    def do_import(self) -> None:
        path = filedialog.askopenfilename(
            title="Select contact list",
            filetypes=[
                ("Text/CSV", "*.txt *.csv"),
                ("Excel", "*.xlsx"),
                ("All files", "*.*"),
            ])
        if not path:
            return
        raw: list[str] = []
        try:
            if path.endswith(".xlsx"):
                import openpyxl
                wb = openpyxl.load_workbook(path, read_only=True)
                ws = wb.active
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if row and row[0]:
                        raw.append(str(row[0]).strip())
            else:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    for ln in f:
                        ln = ln.strip().split(",")[0].strip()
                        if ln:
                            raw.append(ln)
        except Exception as e:
            messagebox.showerror("Import Error", str(e))
            return

        report = batch_validate(raw)
        self._numbers = report.valid_numbers
        fname = os.path.basename(path)
        n = len(self._numbers)
        self._sl["Loaded"].config(text=str(n))
        self.lbl_loaded.config(
            text=f"✅  {n:,} numbers loaded  ·  {fname}", fg=GREEN)
        messagebox.showinfo(
            "Import Complete",
            f"✅  {report.valid_count:,} valid numbers\n"
            f"⚠   {report.invalid_count:,} invalid (skipped)\n"
            f"🔁  {report.duplicate_count:,} duplicates removed\n\n"
            f"Ready to send to {n:,} contacts.")

    def do_start(self) -> None:
        if not self._numbers:
            messagebox.showwarning("No Contacts",
                                   "Please import a contact list first."); return
        msg = self.msg_box.get("1.0", tk.END).strip()
        if not msg:
            messagebox.showwarning("No Message",
                                   "Please write a message before starting."); return

        s    = self.mgr.settings
        name = self.v_camp_name.get().strip() or f"Broadcast {date.today()}"
        dry  = self.v_dry.get()
        cid  = self.db.create_campaign(Campaign(
            id=None, name=name, message=msg,
            daily_limit=s.dlimit, dry_run=dry,
            total_contacts=len(self._numbers)))
        self._campaign_id = cid
        msgs = [Message(id=None, campaign_id=cid, number=n, message_text=msg)
                for n in self._numbers]
        inserted = self.db.bulk_insert_messages(msgs)
        with self.db._tx() as cur:
            cur.execute("UPDATE campaigns SET total_contacts=? WHERE id=?",
                        (inserted, cid))
        if dry:
            from core.sender import DryRunAdapter, Sender
            self.sched._sender = Sender(self.db, s, DryRunAdapter())
        self.sched.enqueue(cid, priority=1)
        self.sched.start()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.lbl_status.config(
            text=f"🔄  Running  ·  Broadcast: {name}  ·  {inserted:,} messages queued",
            fg=GREEN)
        self._sl["Remaining"].config(text=str(inserted))

    def do_pause(self) -> None:
        if self.sched.is_paused:
            self.sched.resume()
            self.btn_pause.config(text="⏸  Pause", fg=AMBER)
            self.lbl_status.config(text="🔄  Resumed — broadcast running", fg=GREEN)
        else:
            self.sched.pause()
            self.btn_pause.config(text="▶  Resume", fg=GREEN)
            self.lbl_status.config(text="⏸  Paused — click Resume to continue", fg=AMBER)

    def do_stop(self) -> None:
        if not messagebox.askyesno("Stop Broadcast",
                                   "Stop the current broadcast?\n\n"
                                   "Already-sent messages are recorded."):
            return
        self.sched.cancel()
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸  Pause", fg=AMBER)
        self.lbl_status.config(text="⏹  Stopped by user", fg=RED)

    def do_test(self) -> None:
        val = simpledialog.askstring(
            "Test Send",
            "Enter phone number (10 or 12 digits) to send a test message:",
            parent=self.app.root)
        if not val:
            return
        from core.phone import normalize
        n = normalize(val.strip())
        if not n:
            messagebox.showwarning("Invalid Number",
                                   "Could not parse that phone number."); return
        msg = self.msg_box.get("1.0", tk.END).strip()
        if not msg:
            messagebox.showwarning("No Message",
                                   "Write a message first."); return
        dry = self.v_dry.get()
        s   = self.mgr.settings
        from core.sender import DryRunAdapter, WhatsAppWebAdapter, Sender
        c   = Campaign(id=None, name="Test Send", message=msg,
                       daily_limit=1, dry_run=dry, total_contacts=1)
        cid = self.db.create_campaign(c)
        m   = Message(id=None, campaign_id=cid, number=n, message_text=msg)
        self.db.bulk_insert_messages([m])
        mid = self.db.get_queued_messages(cid)[0].id
        adapter = DryRunAdapter() if dry else WhatsAppWebAdapter(s)
        sender  = Sender(self.db, s, adapter)
        self.lbl_status.config(text=f"📤  Testing → {n}…", fg=BLUE)

        def _t():
            r = sender.send_with_retry(mid, n, msg, cid)
            res = "✅ Test sent successfully!" if r.ok else f"❌ Failed\n{r.reason}"
            col = GREEN if r.ok else RED
            self.app.root.after(0, lambda: (
                messagebox.showinfo("Test Result", res),
                self.lbl_status.config(
                    text=f"{'✅ Test passed' if r.ok else '❌ Test failed'}  ·  {n}",
                    fg=col),
            ))
        threading.Thread(target=_t, daemon=True).start()

    def do_retry(self) -> None:
        if not self._campaign_id:
            messagebox.showinfo("No Broadcast",
                                "Start a broadcast first before retrying."); return
        stats = self.db.get_campaign_stats(self._campaign_id)
        failed_count = stats.get("failed", 0)
        if not failed_count:
            messagebox.showinfo("Nothing to Retry",
                                "No failed messages in this campaign."); return
        if not messagebox.askyesno("Retry Failed",
                                   f"Retry {failed_count} failed message(s)?"):
            return
        with self.db._tx() as cur:
            cur.execute(
                "UPDATE messages SET status='queued', failed_at=NULL, "
                "failure_reason=NULL, failure_screenshot=NULL, retry_count=0 "
                "WHERE campaign_id=? AND status='failed'",
                (self._campaign_id,))
        self.sched.enqueue(self._campaign_id, priority=1)
        self.sched.start()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.lbl_status.config(
            text=f"🔁  Retrying {failed_count} failed message(s)…", fg=AMBER)
        self._sl["Failed"].config(text="0")

    def do_export(self) -> None:
        from reports.exporter import export_csv, export_txt
        try:
            from reports.exporter import export_excel
            filetypes = [("CSV", "*.csv"), ("Excel", "*.xlsx"), ("Text", "*.txt")]
        except ImportError:
            filetypes = [("CSV", "*.csv"), ("Text", "*.txt")]
            export_excel = None

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=filetypes,
            initialfile="autoreach_export")
        if not path:
            return
        kw = {"campaign_id": self._campaign_id} if self._campaign_id else {}
        try:
            if path.endswith(".xlsx") and export_excel:
                n = export_excel(self.db, path, **kw)
            elif path.endswith(".txt"):
                n = export_txt(self.db, path, **kw)
            else:
                n = export_csv(self.db, path, **kw)
            messagebox.showinfo("Export Complete",
                                f"✅  {n:,} rows exported\n→ {path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def do_blacklist(self) -> None:
        val = simpledialog.askstring(
            "Add to Blacklist",
            "Enter phone number to blacklist\n(they will be skipped in all future broadcasts):",
            parent=self.app.root)
        if not val:
            return
        from core.phone import normalize
        n = normalize(val.strip())
        if n:
            self.db.set_blacklisted(n, True)
            messagebox.showinfo("Blacklisted",
                                f"✅  {n} added to the blacklist.")
        else:
            messagebox.showwarning("Invalid Number",
                                   "Could not parse that phone number.")

    # ══════════════════════════════════════════════════════════════
    #  Scheduler callbacks (called from app.py)
    # ══════════════════════════════════════════════════════════════

    def set_status(self, msg: str) -> None:
        self.lbl_status.config(text=msg)

    def set_progress(self, current: int, total: int, eta: float) -> None:
        pct = (current / total * 100) if total else 0
        self.v_prog.set(pct)
        self.lbl_pct.config(text=f"{pct:.0f}%")
        self._sl["ETA"].config(
            text=str(timedelta(seconds=int(max(0, eta)))))
        self._sl["Remaining"].config(text=str(max(0, total - current)))

    def refresh_stats(self) -> None:
        if not self._campaign_id:
            return
        stats = self.db.get_campaign_stats(self._campaign_id)
        sent   = stats.get("sent",   0)
        failed = stats.get("failed", 0)
        total  = stats.get("total",  0)
        self._sl["Sent"].config(text=str(sent))
        self._sl["Failed"].config(text=str(failed))
        self._sl["Remaining"].config(text=str(max(0, total - sent - failed)))
        pct = (sent / total * 100) if total else 0
        self.v_prog.set(pct)
        self.lbl_pct.config(text=f"{pct:.0f}%")

    def on_campaign_done(self, status: str) -> None:
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸  Pause", fg=AMBER)
        icons = {"completed": "🏁", "cancelled": "⏹", "paused": "⏸", "crashed": "💥"}
        cols  = {"completed": GREEN, "cancelled": RED, "paused": AMBER, "crashed": RED}
        icon  = icons.get(status, "●")
        col   = cols.get(status, AMBER)
        self.lbl_status.config(
            text=f"{icon}  Broadcast {status.upper()}",
            fg=col)
        self.refresh_stats()

    def on_focus(self) -> None:
        self.refresh_stats()

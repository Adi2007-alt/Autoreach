# -*- coding: utf-8 -*-
"""ui/tab_campaigns.py — Campaign manager tab."""
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from core.models import CampaignStatus
from ui.theme import (BG, CARD, CARD2, ACCENT, TEXT, MUTED,
                      GREEN, RED, AMBER, BLUE, BORDER,
                      icon_button, STATUS_COLORS, STATUS_ICONS)


class CampaignsTab:
    def __init__(self, parent: tk.Frame, app) -> None:
        self.app = app
        self.db  = app.db
        self._all_campaigns: list = []
        self._build(parent)
        self.refresh()

    def _build(self, parent: tk.Frame) -> None:
        # ── Header ──────────────────────────────────────────────
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(hdr, text="📋  Broadcasts", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        icon_button(hdr, "🔄 Refresh", self.refresh,
                    bg=CARD2, fg=BLUE).pack(side="right", padx=(4, 0))
        icon_button(hdr, "📤 Export Summary", self._export_summary,
                    bg=CARD2, fg=TEXT).pack(side="right", padx=4)
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(0, 6))

        # ── Search / filter bar ──────────────────────────────────
        fbar = tk.Frame(parent, bg=CARD2)
        fbar.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(fbar, text="🔍", bg=CARD2, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        self.v_search = tk.StringVar()
        self.v_search.trace_add("write", lambda *_: self._apply_filter())
        tk.Entry(fbar, textvariable=self.v_search, bg=CARD2, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Segoe UI", 9), width=30).pack(side="left", pady=6)

        tk.Label(fbar, text="Filter:", bg=CARD2, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(14, 4))
        self.v_filter = tk.StringVar(value="All")
        statuses = ["All", "running", "completed", "paused", "failed",
                    "cancelled", "crashed", "draft"]
        om = tk.OptionMenu(fbar, self.v_filter, *statuses,
                           command=lambda _: self._apply_filter())
        om.config(bg=CARD2, fg=TEXT, activebackground=ACCENT,
                  activeforeground="#fff", font=("Segoe UI", 8),
                  relief="flat", bd=0, highlightthickness=0)
        om["menu"].config(bg=CARD2, fg=TEXT, activebackground=ACCENT,
                          activeforeground="#fff", relief="flat")
        om.pack(side="left")

        # ── Treeview ─────────────────────────────────────────────
        tree_wrap = tk.Frame(parent, bg=BG)
        tree_wrap.pack(fill="both", expand=True, padx=14)

        cols = ("ID", "Name", "Status", "Total", "Sent", "Failed",
                "Skip", "Rate%", "Started", "Dry")
        self.tree = ttk.Treeview(tree_wrap, columns=cols,
                                 show="headings", height=13)
        widths  = [38, 200, 105, 65, 65, 65, 55, 65, 150, 45]
        anchors = ["c", "w", "c", "c", "c", "c", "c", "c", "c", "c"]
        for col, w, anc in zip(cols, widths, anchors):
            self.tree.heading(col, text=col,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor=anc, minwidth=w)

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        # Row tags
        self.tree.tag_configure("odd",       background=CARD)
        self.tree.tag_configure("even",      background=CARD2)
        self.tree.tag_configure("running",   foreground=GREEN)
        self.tree.tag_configure("failed",    foreground=RED)
        self.tree.tag_configure("paused",    foreground=AMBER)
        self.tree.tag_configure("crashed",   foreground=RED)
        self.tree.tag_configure("completed", foreground=MUTED)
        self.tree.tag_configure("cancelled", foreground=RED)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Action buttons ───────────────────────────────────────
        bf = tk.Frame(parent, bg=BG)
        bf.pack(fill="x", padx=14, pady=(6, 4))
        buttons = [
            ("▶  Resume",   self._resume, CARD2, GREEN),
            ("⏸  Pause",    self._pause,  CARD2, AMBER),
            ("⏹  Cancel",   self._cancel, CARD2, RED),
            ("🗑  Delete",   self._delete, "#450A0A", RED),
            ("📜  View Log", self._view_log, CARD2, BLUE),
        ]
        for txt, cmd, bg, fg in buttons:
            icon_button(bf, txt, cmd, bg=bg, fg=fg).pack(side="left", padx=3)

        # ── Detail card ──────────────────────────────────────────
        self.detail_frame = tk.Frame(parent, bg=CARD2)
        self.detail_frame.pack(fill="x", padx=14, pady=(4, 10))
        tk.Frame(self.detail_frame, bg=ACCENT, width=4).pack(
            side="left", fill="y")
        self.detail_inner = tk.Frame(self.detail_frame, bg=CARD2, padx=12, pady=8)
        self.detail_inner.pack(fill="x", side="left", expand=True)
        self.detail_lbl = tk.Label(
            self.detail_inner,
            text="Select a broadcast above to view details",
            bg=CARD2, fg=MUTED, font=("Segoe UI", 8),
            justify="left", wraplength=860)
        self.detail_lbl.pack(anchor="w")

        self._sort_col = None
        self._sort_rev = False

    # ── Data ──────────────────────────────────────────────────

    def refresh(self) -> None:
        self._all_campaigns = self.db.list_campaigns()
        self._apply_filter()

    def _apply_filter(self) -> None:
        query  = self.v_search.get().lower()
        status = self.v_filter.get()
        self.tree.delete(*self.tree.get_children())
        row_i = 0
        for c in self._all_campaigns:
            if status != "All" and c.status.value != status:
                continue
            if query and query not in c.name.lower():
                continue
            icon    = STATUS_ICONS.get(c.status.value, "")
            tag_row = "odd" if row_i % 2 else "even"
            pending = max(0, c.total_contacts
                         - c.sent_count - c.failed_count - c.skipped_count)
            self.tree.insert("", "end", iid=str(c.id),
                             tags=(tag_row, c.status.value), values=(
                c.id,
                c.name[:30],
                f"{icon} {c.status.value}",
                c.total_contacts, c.sent_count,
                c.failed_count, c.skipped_count,
                f"{c.success_rate:.1f}",
                str(c.started_at)[:16] if c.started_at else "—",
                "✓" if c.dry_run else "—",
            ))
            row_i += 1

    def _sort_by(self, col: str) -> None:
        """Sort treeview by column header click."""
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            items.sort(key=lambda t: float(t[0]) if t[0].replace(".", "").isdigit() else t[0].lower(),
                       reverse=self._sort_rev)
        except Exception:
            items.sort(key=lambda t: t[0].lower(), reverse=self._sort_rev)
        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _on_select(self, _=None) -> None:
        cid = self._selected_id()
        if not cid:
            return
        c = self.db.get_campaign(cid)
        if not c:
            return
        s = self.db.get_campaign_stats(cid)
        rate = f"{c.success_rate:.1f}%"
        for w in self.detail_inner.winfo_children():
            w.destroy()

        pairs = [
            ("Name",      c.name),
            ("Status",    f"{STATUS_ICONS.get(c.status.value,'')} {c.status.value}"),
            ("Total",     str(c.total_contacts)),
            ("Sent",      str(s.get("sent", 0))),
            ("Failed",    str(s.get("failed", 0))),
            ("Queued",    str(s.get("queued", 0))),
            ("Rate",      rate),
            ("Started",   str(c.started_at or "—")),
            ("Completed", str(c.completed_at or "—")),
            ("Dry Run",   "Yes" if c.dry_run else "No"),
        ]
        row = tk.Frame(self.detail_inner, bg=CARD2)
        row.pack(fill="x")
        for i, (k, v) in enumerate(pairs):
            col_frame = tk.Frame(row, bg=CARD2)
            col_frame.pack(side="left", padx=(0, 18))
            tk.Label(col_frame, text=k, bg=CARD2, fg=MUTED,
                     font=("Segoe UI", 7, "bold")).pack(anchor="w")
            col = STATUS_COLORS.get(c.status.value, TEXT) if k == "Status" else TEXT
            tk.Label(col_frame, text=v, bg=CARD2, fg=col,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")

    # ── Actions ───────────────────────────────────────────────

    def _resume(self) -> None:
        cid = self._selected_id()
        if not cid:
            return
        c = self.db.get_campaign(cid)
        if not c or c.status.value not in ("paused", "crashed", "running"):
            messagebox.showinfo("Cannot Resume",
                "Only paused or crashed broadcasts can be resumed."); return
        self.app.scheduler.enqueue(cid, priority=1)
        self.app.scheduler.start()
        self.refresh()
        messagebox.showinfo("Resumed",
            f"Broadcast '{c.name}' re-queued.\nIt will start shortly.")

    def _pause(self) -> None:
        self.app.scheduler.pause()
        self.refresh()

    def _cancel(self) -> None:
        cid = self._selected_id()
        if cid:
            self.app.scheduler.cancel(cid)
            self.refresh()

    def _delete(self) -> None:
        cid = self._selected_id()
        if not cid:
            return
        c = self.db.get_campaign(cid)
        if not messagebox.askyesno(
                "Confirm Delete",
                f"Delete '{c.name if c else cid}' and ALL its messages?\n\n"
                "⚠  This cannot be undone.",
                icon="warning"):
            return
        try:
            with self.db._tx() as cur:
                cur.execute("DELETE FROM messages  WHERE campaign_id=?", (cid,))
                cur.execute("DELETE FROM campaigns WHERE id=?",          (cid,))
        except Exception as exc:
            messagebox.showerror("Delete Failed", str(exc))
            return
        self.refresh()

    def _view_log(self) -> None:
        cid = self._selected_id()
        if not cid:
            return
        logs = self.db.query_audit_logs(campaign_id=cid)
        w    = tk.Toplevel(self.app.root, bg=BG)
        w.title(f"Audit Log — Broadcast {cid}")
        w.geometry("860x540")
        w.resizable(True, True)

        # Toolbar
        tb = tk.Frame(w, bg=CARD2)
        tb.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(tb, text=f"📜  Audit Log — Broadcast {cid}",
                 bg=CARD2, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=10, pady=6)
        icon_button(tb, "📋 Copy All",
                    lambda: (w.clipboard_clear(),
                             w.clipboard_append(txt_widget.get("1.0", tk.END))),
                    bg=CARD2, fg=BLUE, size=8).pack(side="right", padx=6)

        txt_widget = tk.Text(w, bg=CARD, fg=TEXT, font=("Consolas", 8),
                             relief="flat", padx=12, pady=10, wrap="none")
        vsb = ttk.Scrollbar(w, orient="vertical", command=txt_widget.yview)
        hsb = ttk.Scrollbar(w, orient="horizontal", command=txt_widget.xview)
        txt_widget.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        txt_widget.pack(fill="both", expand=True, padx=(10, 0), pady=(4, 0))
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x", padx=10)

        # Color-coded log lines
        txt_widget.tag_configure("INFO",    foreground=BLUE)
        txt_widget.tag_configure("WARNING", foreground=AMBER)
        txt_widget.tag_configure("ERROR",   foreground=RED)
        txt_widget.tag_configure("ts",      foreground=MUTED)

        for l in logs[-200:]:
            ts   = f"[{str(l.created_at)[:19]}]  "
            line = f"[{l.level.value}]  {l.text}\n"
            txt_widget.insert(tk.END, ts, "ts")
            txt_widget.insert(tk.END, line, l.level.value)

        if not logs:
            txt_widget.insert("1.0", "(no audit log entries for this broadcast)")

        txt_widget.config(state="disabled")
        txt_widget.see(tk.END)

    def _export_summary(self) -> None:
        from tkinter import filedialog
        from reports.exporter import export_campaign_summary
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx")],
            initialfile="campaigns_summary")
        if path:
            n = export_campaign_summary(self.db, path)
            messagebox.showinfo("Exported",
                                f"✅  {n} broadcasts exported\n→ {path}")

    def on_focus(self) -> None:
        self.refresh()

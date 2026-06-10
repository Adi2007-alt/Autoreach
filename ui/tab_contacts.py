# -*- coding: utf-8 -*-
"""ui/tab_contacts.py — Contact book and group manager."""
from __future__ import annotations
import csv
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from core.models import Contact
from core.phone  import batch_validate
from ui.theme import (BG, CARD, CARD2, ACCENT, TEXT, MUTED,
                      GREEN, RED, AMBER, BLUE, BORDER, icon_button)


class ContactsTab:
    def __init__(self, parent: tk.Frame, app) -> None:
        self.app = app
        self.db  = app.db
        self._build(parent)
        self.refresh()

    def _build(self, parent: tk.Frame) -> None:
        # ── Header ──────────────────────────────────────────────
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(hdr, text="👥  Contacts",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(0, 6))

        # ── Toolbar ──────────────────────────────────────────────
        tb = tk.Frame(parent, bg=CARD2)
        tb.pack(fill="x", padx=14, pady=(0, 6))

        # Search
        tk.Label(tb, text="  🔍", bg=CARD2, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", pady=6)
        self.v_search = tk.StringVar()
        self.v_search.trace_add("write", lambda *_: self.refresh())
        tk.Entry(tb, textvariable=self.v_search, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Segoe UI", 9), width=26).pack(side="left", padx=6, pady=4)

        # Filter: all / blacklisted
        tk.Label(tb, text="Show:", bg=CARD2, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 4))
        self.v_bl_filter = tk.StringVar(value="All")
        om = tk.OptionMenu(tb, self.v_bl_filter,
                           "All", "Active only", "Blacklisted only",
                           command=lambda _: self.refresh())
        om.config(bg=CARD2, fg=TEXT, activebackground=ACCENT,
                  activeforeground="#fff", relief="flat", bd=0,
                  highlightthickness=0, font=("Segoe UI", 8))
        om["menu"].config(bg=CARD2, fg=TEXT, activebackground=ACCENT,
                          activeforeground="#fff", relief="flat")
        om.pack(side="left")

        # Right buttons
        icon_button(tb, "🔄 Refresh", self.refresh,
                    bg=CARD2, fg=BLUE, size=8).pack(side="right", padx=3, pady=3)
        icon_button(tb, "📥 Import", self._import,
                    bg=ACCENT, fg="#fff", size=8).pack(side="right", padx=3, pady=3)
        icon_button(tb, "➕ Add", self._add,
                    bg=CARD2, fg=GREEN, size=8).pack(side="right", padx=3, pady=3)

        # ── Contact Treeview ─────────────────────────────────────
        tree_wrap = tk.Frame(parent, bg=BG)
        tree_wrap.pack(fill="both", expand=True, padx=14)

        cols = ("Number", "Name", "Group", "Status", "Added")
        self.tree = ttk.Treeview(tree_wrap, columns=cols,
                                 show="headings", height=14)
        widths  = [140, 160, 110, 100, 120]
        anchors = ["c", "w", "c", "c", "c"]
        for col, w, anc in zip(cols, widths, anchors):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=anc)

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        self.tree.tag_configure("odd",  background=CARD)
        self.tree.tag_configure("even", background=CARD2)
        self.tree.tag_configure("bl",   foreground=RED)

        # ── Action buttons ───────────────────────────────────────
        bf = tk.Frame(parent, bg=BG)
        bf.pack(fill="x", padx=14, pady=(6, 4))
        actions = [
            ("✏  Edit Name",    self._edit,         CARD2, TEXT),
            ("🚫 Blacklist",    self._blacklist,     CARD2, RED),
            ("✅ Un-blacklist", self._unblacklist,   CARD2, GREEN),
            ("🗑  Delete",      self._delete,        "#450A0A", RED),
            ("📤  Export CSV",  self._export,        CARD2, BLUE),
            ("🧹 Clear Blacklist", self._clear_blacklist, CARD2, AMBER),
        ]
        for txt, cmd, bg, fg in actions:
            icon_button(bf, txt, cmd, bg=bg, fg=fg, size=8).pack(
                side="left", padx=3)

        # ── Count label ──────────────────────────────────────────
        self.lbl_count = tk.Label(parent, text="",
                                  bg=BG, fg=MUTED, font=("Segoe UI", 7))
        self.lbl_count.pack(anchor="e", padx=14)

        # ── Groups section ───────────────────────────────────────
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(4, 6))
        ghdr = tk.Frame(parent, bg=BG)
        ghdr.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(ghdr, text="📂  Groups",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        icon_button(ghdr, "➕ New Group", self._new_group,
                    bg=CARD2, fg=GREEN, size=8).pack(side="right")

        gcols = ("ID", "Group Name", "Description")
        self.grp_tree = ttk.Treeview(parent, columns=gcols,
                                     show="headings", height=3)
        for col, w in zip(gcols, [50, 200, 450]):
            self.grp_tree.heading(col, text=col)
            self.grp_tree.column(col, width=w)
        self.grp_tree.pack(fill="x", padx=14, pady=(0, 10))
        self._refresh_groups()

    # ── Data ──────────────────────────────────────────────────

    def refresh(self) -> None:
        q      = self.v_search.get().strip()
        bl_flt = self.v_bl_filter.get()
        self.tree.delete(*self.tree.get_children())
        contacts = self.db.list_contacts(search=q if q else None)

        if bl_flt == "Blacklisted only":
            contacts = [c for c in contacts if c.is_blacklisted]
        elif bl_flt == "Active only":
            contacts = [c for c in contacts if not c.is_blacklisted]

        for i, c in enumerate(contacts):
            status  = "🚫 Blacklisted" if c.is_blacklisted else "✅ Active"
            tag_row = "odd" if i % 2 else "even"
            tags    = (tag_row, "bl") if c.is_blacklisted else (tag_row,)
            self.tree.insert("", "end", iid=str(c.id), tags=tags, values=(
                c.number,
                c.display_name or "—",
                c.group or "—",
                status,
                str(c.created_at)[:10] if c.created_at else "—",
            ))
        total      = len(contacts)
        blacklisted = sum(1 for c in contacts if c.is_blacklisted)
        self.lbl_count.config(
            text=f"{total:,} contacts  ·  {blacklisted:,} blacklisted")

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _selected_contact(self):
        cid = self._selected_id()
        if not cid:
            return None
        contacts = self.db.list_contacts()
        return next((c for c in contacts if c.id == cid), None)

    # ── CRUD ──────────────────────────────────────────────────

    def _add(self) -> None:
        num = simpledialog.askstring("Add Contact", "Enter phone number:")
        if not num:
            return
        from core.phone import normalize
        n = normalize(num.strip())
        if not n:
            messagebox.showwarning("Invalid Number",
                                   "Could not parse that number."); return
        name = simpledialog.askstring(
            "Add Contact", "Display name (optional):") or ""
        self.db.upsert_contact(Contact(id=None, number=n, display_name=name))
        self.refresh()

    def _edit(self) -> None:
        c = self._selected_contact()
        if not c:
            return
        name = simpledialog.askstring(
            "Edit Display Name", "New display name:",
            initialvalue=c.display_name or "")
        if name is not None:
            c.display_name = name
            self.db.upsert_contact(c)
            self.refresh()

    def _blacklist(self) -> None:
        c = self._selected_contact()
        if c:
            self.db.set_blacklisted(c.number, True)
            self.refresh()

    def _unblacklist(self) -> None:
        c = self._selected_contact()
        if c:
            self.db.set_blacklisted(c.number, False)
            self.refresh()

    def _delete(self) -> None:
        c = self._selected_contact()
        if not c:
            return
        if messagebox.askyesno("Delete Contact",
                               f"Delete {c.number}?\n\n"
                               "This contact will be removed from the address book."):
            self.db._conn.execute("DELETE FROM contacts WHERE id=?", (c.id,))
            self.db._conn.commit()
            self.refresh()

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Contacts",
            filetypes=[("Text/CSV", "*.txt *.csv"),
                       ("Excel", "*.xlsx"),
                       ("All files", "*.*")])
        if not path:
            return
        raw: list[str] = []
        try:
            if path.endswith(".xlsx"):
                import openpyxl
                wb = openpyxl.load_workbook(path, read_only=True)
                for row in wb.active.iter_rows(min_row=2, values_only=True):
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
        for n in report.valid_numbers:
            self.db.upsert_contact(Contact(id=None, number=n))
        messagebox.showinfo(
            "Import Complete",
            f"✅  {report.valid_count:,} contacts added / updated\n"
            f"⚠   {report.invalid_count:,} invalid (skipped)\n"
            f"🔁  {report.duplicate_count:,} duplicates ignored")
        self.refresh()

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="contacts")
        if not path:
            return
        contacts = self.db.list_contacts()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Number", "Name", "Group", "Blacklisted", "Added"])
            for c in contacts:
                w.writerow([
                    c.number,
                    c.display_name or "",
                    c.group or "",
                    "Yes" if c.is_blacklisted else "No",
                    str(c.created_at)[:10] if c.created_at else "",
                ])
        messagebox.showinfo("Exported",
                            f"✅  {len(contacts):,} contacts exported\n→ {path}")

    def _new_group(self) -> None:
        name = simpledialog.askstring("New Group", "Group name:")
        if name:
            self.db.create_group(name.strip())
            self._refresh_groups()

    def _refresh_groups(self) -> None:
        self.grp_tree.delete(*self.grp_tree.get_children())
        for g in self.db.list_groups():
            self.grp_tree.insert("", "end",
                                 values=(g.id, g.name, g.description or ""))

    def _clear_blacklist(self) -> None:
        if messagebox.askyesno("Clear Blacklist",
                               "Remove blacklist flag from ALL contacts?"):
            self.db._conn.execute("UPDATE contacts SET is_blacklisted=0")
            self.db._conn.commit()
            self.refresh()

    def on_focus(self) -> None:
        self.refresh()

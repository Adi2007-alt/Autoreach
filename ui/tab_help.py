# -*- coding: utf-8 -*-
"""ui/tab_help.py — Help & Troubleshooting reference."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from ui.theme import (BG, CARD, CARD2, ACCENT, TEXT, MUTED,
                      GREEN, RED, AMBER, BLUE, BORDER, PURPLE)

_SHORTCUTS = [
    ("Ctrl + S",        "Save settings (when on Settings tab)"),
    ("F5",              "Refresh current tab data"),
    ("Mouse wheel",     "Scroll any list or log"),
    ("Click heading",   "Sort table by that column (Broadcasts tab)"),
    ("Top-left corner", "Emergency stop (pyautogui failsafe)"),
]

_SECTIONS = [
    ("🚀  Quick-Start Guide", GREEN, [
        ("1.  Install dependencies",
         "Open a terminal in the AutoReach folder and run:\n"
         "     pip install -r requirements.txt\n\n"
         "Requires Python 3.9+, and Google Chrome or Edge."),
        ("2.  Import contacts",
         "Go to ✉ Send tab → click Import Contacts.\n"
         "Accepted formats: TXT (one number per line), CSV, Excel (.xlsx)."),
        ("3.  Compose your message",
         "Type your message in the editor. Enable 'Message Variation' in ⚙ Settings\n"
         "to append invisible characters that prevent WhatsApp duplicate-message filtering."),
        ("4.  Start sending",
         "Click ▶ START BROADCAST. A broadcast record is created automatically.\n"
         "Use Dry-Run mode to simulate the full flow safely before going live."),
        ("5.  Monitor progress",
         "Watch the Live Stats sidebar on the Send tab, or switch to 📊 Dashboard\n"
         "for charts and insights. All events appear in the 📜 Log tab in real time."),
    ]),
    ("📋  Broadcast Manager", BLUE, [
        ("Creating a broadcast",
         "Go to ✉ Send → fill in the message and contacts → click START.\n"
         "You can manage all broadcasts in the 📋 Broadcasts tab."),
        ("Pause / Resume",
         "Click ⏸ Pause during an active broadcast to pause it mid-way.\n"
         "Click ▶ Resume (or use the Broadcasts tab) to continue from where it stopped.\n"
         "State is saved in the database automatically."),
        ("Cancel a broadcast",
         "Click ⏹ Stop to cancel permanently. Already-sent messages are preserved."),
        ("Crash recovery",
         "If AutoReach closes unexpectedly, 'sending' messages are reset to 'queued'\n"
         "on next launch. Interrupted broadcasts are automatically re-queued."),
        ("Retry failed messages",
         "Click 🔁 Retry on the Send tab to re-queue all failed messages\n"
         "in the current broadcast and try again."),
    ]),
    ("👥  Contacts", PURPLE, [
        ("Import formats",
         "• TXT — one phone number per line\n"
         "• CSV — first column used as number, or column named 'number' / 'phone'\n"
         "• Excel (.xlsx) — same column requirement (row 1 = headers)"),
        ("Phone number formats accepted",
         "• 10-digit local:   9876543210  →  +91 9876543210\n"
         "• 12-digit:         919876543210\n"
         "• E.164 format:     +919876543210  (always accepted)\n\n"
         "Change the default country code in ⚙ Settings."),
        ("Blacklisting",
         "Select a contact → click 🚫 Blacklist.\n"
         "Blacklisted contacts are automatically skipped in all future broadcasts.\n"
         "They still appear in the contact list (marked red) and can be un-blacklisted."),
        ("Groups",
         "Create groups in the lower section of the Contacts tab.\n"
         "Groups can be used to organise contacts (future feature: filter by group)."),
    ]),
    ("⚙  Settings Reference", AMBER, [
        ("Min / Max delay (seconds)",
         "A random delay between min and max is chosen before each send.\n"
         "Recommended: 15–45 s for new numbers, 5–15 s for established ones.\n"
         "Lower values send faster but increase ban risk."),
        ("Daily limit",
         "Max messages per calendar day. WhatsApp may restrict accounts sending\n"
         "> 50–80 msgs/day from a new number. Set 0 for no limit."),
        ("Dry-run mode",
         "Simulates the send cycle with no browser interaction.\n"
         "Use to test a broadcast flow, check contact normalization, and verify stats."),
        ("PIN lock",
         "Optional 4–12 digit PIN required at launch.\n"
         "Stored as a salted SHA-256 hash — not recoverable if forgotten."),
        ("Human-like delays",
         "Applies Gaussian jitter to the configured delay range, making send timing\n"
         "less predictable and reducing automation fingerprinting risk."),
        ("Screenshot on failure",
         "Saves a screenshot of the browser window whenever a send fails.\n"
         "Files are saved in the screenshots/ folder (auto-created)."),
    ]),
    ("🔴  Troubleshooting", RED, [
        ("WhatsApp shows QR code every launch",
         "You need a persistent Chrome profile. The browser must be able to remember\n"
         "your WhatsApp Web session between runs.\n\n"
         "Tip: Log in manually once, then keep the profile path consistent."),
        ("Messages stuck in 'sending' after crash",
         "These are auto-reset to 'queued' on next launch.\n"
         "If they persist: 📋 Broadcasts tab → select broadcast → ▶ Resume."),
        ("'Rate limit hit' warning",
         "Your daily or hourly limit has been reached.\n"
         "AutoReach will automatically continue after midnight or the next hour."),
        ("ImportError on launch",
         "Run in the AutoReach folder:\n"
         "     pip install -r requirements.txt\n\n"
         "If openpyxl is missing:  pip install openpyxl"),
        ("'Invalid number' for valid-looking numbers",
         "Check the country code in ⚙ Settings.\n"
         "Numbers without a country prefix use the default code (91 = India).\n"
         "E.164 format (+XX...) is always accepted regardless of default setting."),
    ]),
    ("📦  Technical Details", MUTED, [
        ("Database",
         "SQLite3 with WAL mode. File: autoreach.db (auto-created on first launch).\n"
         "Schema: campaigns, contacts, contact_groups, messages, audit_logs,\n"
         "        rate_limits, settings."),
        ("Message states",
         "queued → sending → sent / failed / skipped\n\n"
         "'delivered' and 'read' are NOT set automatically —\n"
         "WhatsApp Web does not expose reliable delivery receipts to automation."),
        ("Adapter architecture",
         "The send engine uses a SenderAdapter interface:\n"
         "• WhatsAppWebAdapter — real browser automation via pyautogui + webbrowser\n"
         "• DryRunAdapter      — simulation (no browser, configurable failure rate)\n\n"
         "Custom adapters can be added by implementing the adapter ABC."),
        ("Exporting data",
         "📋 Broadcasts tab → select broadcast → 📤 Export Summary\n"
         "✉ Send tab → 💾 Export (exports current broadcast messages)\n"
         "Fields: number, status, sent_at, failed_at, failure_reason, retry_count."),
    ]),
]


class HelpTab:
    """Help & Troubleshooting tab — searchable accordion sections."""

    def __init__(self, parent: tk.Frame, app) -> None:
        self._app = app
        self._panels: list[tuple[str, tk.Frame]] = []  # (search_content, body)
        self._build(parent)

    def _build(self, parent: tk.Frame) -> None:
        # ── Header ──────────────────────────────────────────────
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(14, 4))
        tk.Label(hdr, text="❓  Help & Troubleshooting",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")

        # Search box
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        se = tk.Entry(hdr, textvariable=self._search_var,
                      bg=CARD2, fg=TEXT, insertbackground=TEXT,
                      relief="flat", font=("Segoe UI", 10), width=28)
        se.pack(side="right", ipady=4, ipadx=6)
        tk.Label(hdr, text="🔍", bg=BG, fg=MUTED,
                 font=("Segoe UI", 11)).pack(side="right", padx=(0, 4))

        tk.Frame(parent, bg=ACCENT, height=2).pack(fill="x", padx=20)

        # ── Keyboard shortcuts card ──────────────────────────────
        sc = tk.Frame(parent, bg=CARD2)
        sc.pack(fill="x", padx=20, pady=(10, 4))
        tk.Frame(sc, bg=BLUE, width=4).pack(side="left", fill="y")
        sc_body = tk.Frame(sc, bg=CARD2, padx=14, pady=10)
        sc_body.pack(fill="x", side="left", expand=True)
        tk.Label(sc_body, text="⌨  Keyboard Shortcuts",
                 bg=CARD2, fg=BLUE,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0,
                                                    columnspan=3, sticky="w", pady=(0, 6))
        for i, (key, desc) in enumerate(_SHORTCUTS):
            tk.Label(sc_body, text=key, bg=CARD, fg=TEXT,
                     font=("Consolas", 8, "bold"),
                     padx=8, pady=2, relief="flat").grid(
                         row=i+1, column=0, padx=(0, 10), pady=1, sticky="w")
            tk.Label(sc_body, text=desc, bg=CARD2, fg=MUTED,
                     font=("Segoe UI", 8)).grid(
                         row=i+1, column=1, sticky="w")

        # ── Scrollable accordion ─────────────────────────────────
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        self._inner = tk.Frame(canvas, bg=BG)
        wid = canvas.create_window((0, 0), window=self._inner, anchor="nw")

        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(wid, width=e.width))
        self._inner.bind("<Configure>",
                         lambda e: canvas.configure(
                             scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        self._build_sections()

    def _build_sections(self) -> None:
        for sec_title, color, items in _SECTIONS:
            # Outer wrapper
            wrapper = tk.Frame(self._inner, bg=BG)
            wrapper.pack(fill="x", padx=16, pady=(6, 0))

            # Clickable header
            header = tk.Frame(wrapper, bg=CARD, cursor="hand2")
            header.pack(fill="x")
            tk.Frame(header, bg=color, width=5).pack(side="left", fill="y")
            lbl = tk.Label(header, text=sec_title, bg=CARD, fg=TEXT,
                           font=("Segoe UI", 10, "bold"),
                           anchor="w", padx=14, pady=10)
            lbl.pack(side="left", fill="x", expand=True)
            arrow = tk.Label(header, text="▾", bg=CARD, fg=MUTED,
                             font=("Segoe UI", 12), padx=14)
            arrow.pack(side="right")

            # Body
            body = tk.Frame(wrapper, bg=CARD2)
            body.pack(fill="x")
            for q_title, q_text in items:
                self._add_item(body, q_title, q_text, color)

            # Toggle state
            is_open = [True]

            def toggle(b=body, a=arrow, o=is_open):
                if o[0]:
                    b.pack_forget()
                    a.config(text="▸")
                else:
                    b.pack(fill="x")
                    a.config(text="▾")
                o[0] = not o[0]

            for widget in [header, lbl, arrow]:
                widget.bind("<Button-1>", lambda e, t=toggle: t())

            # Build search content string
            content = sec_title.lower() + " " + " ".join(
                t.lower() + " " + tx.lower() for t, tx in items)
            self._panels.append((content, body, wrapper))

    def _add_item(self, parent: tk.Frame, title: str,
                  text: str, color: str = ACCENT) -> None:
        item = tk.Frame(parent, bg=CARD2)
        item.pack(fill="x", padx=6, pady=1)

        hdr = tk.Frame(item, bg=CARD2)
        hdr.pack(fill="x", padx=10, pady=(8, 2))
        tk.Frame(hdr, bg=color, width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(hdr, text=title, bg=CARD2, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        tk.Label(item, text=text, bg=CARD2, fg=TEXT,
                 font=("Segoe UI", 8.5),
                 anchor="w", justify="left",
                 wraplength=760).pack(fill="x", padx=22, pady=(0, 10))

    def _filter(self) -> None:
        query = self._search_var.get().strip().lower()
        for content, body, wrapper in self._panels:
            if not query or query in content:
                wrapper.pack(fill="x", padx=16, pady=(6, 0))
                body.pack(fill="x")
            else:
                wrapper.pack_forget()

    def on_focus(self) -> None:
        pass

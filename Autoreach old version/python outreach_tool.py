# -*- coding: utf-8 -*-
"""
AutoReach v4.0 — WhatsApp Outreach Automation
IMPORTANT: Only message people who have opted in or are expected to
receive your message (e.g. fellow program members). Bulk unsolicited
messaging violates WhatsApp's Terms of Service.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import urllib.parse
import webbrowser
import threading
import time
import random
import os
import json
import pyautogui
import pyperclip
from datetime import datetime, timedelta

try:
    import pygetwindow as gw
except ImportError:
    gw = None

# ═══════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════
LOG_FILE       = "autoreach_log.json"
BLACKLIST_FILE = "blacklist.txt"
VERSION        = "4.0"

# Colours (reused across tabs — defined at module level)
BG     = "#0F1115"
CARD   = "#161A1F"
ACCENT = "#4F8CFF"
TEXT   = "#E6E6E6"
MUTED  = "#9AA0A6"
GREEN  = "#22C55E"
RED    = "#EF4444"
AMBER  = "#F59E0B"
BLUE   = "#60A5FA"


# ═══════════════════════════════════════════════════════════
#  SESSION LOGGER
# ═══════════════════════════════════════════════════════════
class Logger:
    def __init__(self):
        self.log = self._load()

    def _load(self):
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"all_sent": [], "all_failed": []}

    def save(self):
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.log, f, indent=2)
        except Exception:
            pass

    def log_sent(self, number):
        self.log["all_sent"].append({
            "number": number,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "sent"
        })
        self.save()

    def log_failed(self, number):
        self.log["all_failed"].append({
            "number": number,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "failed"
        })
        self.save()

    def get_all_sent_numbers(self):
        return {e["number"] for e in self.log["all_sent"]}

    def total_sent_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return sum(1 for e in self.log["all_sent"] if e["time"].startswith(today))


# ═══════════════════════════════════════════════════════════
#  BLACKLIST
# ═══════════════════════════════════════════════════════════
class Blacklist:
    def __init__(self):
        self.numbers = self._load()

    def _load(self):
        if os.path.exists(BLACKLIST_FILE):
            try:
                with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
                    return {ln.strip() for ln in f if ln.strip()}
            except Exception:
                pass
        return set()

    def add(self, number):
        if number not in self.numbers:
            self.numbers.add(number)
            try:
                with open(BLACKLIST_FILE, "a", encoding="utf-8") as f:
                    f.write(number + "\n")
            except Exception:
                pass

    def contains(self, number):
        return number in self.numbers


# ═══════════════════════════════════════════════════════════
#  MESSAGE VARIATION — reduces risk of identical-message flags
# ═══════════════════════════════════════════════════════════
# Zero-width Unicode characters that are invisible but make each
# message technically unique (different byte string = not duplicate).
_INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060"]

def vary_message(text: str) -> str:
    """
    Insert a random invisible character at a random whitespace
    position so each message is a different byte string, making
    it harder for WhatsApp's dedup filters to flag it as spam.
    """
    words = text.split(" ")
    if len(words) < 4:
        return text
    insert_pos = random.randint(1, len(words) - 2)
    invis = random.choice(_INVISIBLE)
    words[insert_pos] = words[insert_pos] + invis
    return " ".join(words)


# ═══════════════════════════════════════════════════════════
#  HUMAN-LIKE DELAY
# ═══════════════════════════════════════════════════════════
def human_delay(min_s: float, max_s: float) -> float:
    """
    Return a delay sampled from a Gaussian centred between min and max,
    clamped to [min_s, max_s].  Looks more natural than pure uniform random.
    """
    mu    = (min_s + max_s) / 2
    sigma = (max_s - min_s) / 4
    return max(min_s, min(max_s, random.gauss(mu, sigma)))


# ═══════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════
class OutreachTool:
    def __init__(self, root):
        self.root = root
        self.root.title(f"AutoReach v{VERSION}")
        self.root.geometry("800x920")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # State
        self.numbers      = []
        self.current_idx  = 0
        self.total        = 0
        self.sent_count   = 0
        self.failed_list  = []
        self.skipped_count= 0
        self.running      = False
        self.paused       = False
        self.start_time   = None
        self._stop_event  = threading.Event()

        # Helpers
        self.logger    = Logger()
        self.blacklist = Blacklist()

        # Style ttk
        self._style_ttk()
        self._build_ui()
        self._update_daily_label()

    # ─────────────────────────────────────────────────────
    #  TTK styling
    # ─────────────────────────────────────────────────────
    def _style_ttk(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TButton",   background=CARD,   foreground=TEXT,
                    font=("Segoe UI", 9, "bold"), borderwidth=0, focusthickness=0)
        s.map("TButton", background=[("active", ACCENT)])
        s.configure("TNotebook",       background=BG,   borderwidth=0)
        s.configure("TNotebook.Tab",   background=CARD, foreground=MUTED,
                    font=("Segoe UI", 9), padding=[12, 6])
        s.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#FFFFFF")])
        s.configure("Horizontal.TProgressbar",
                    troughcolor=CARD, background=ACCENT, borderwidth=0)
        s.configure("TSpinbox", fieldbackground=CARD, foreground=TEXT, borderwidth=0)
        s.configure("TCheckbutton", background=BG, foreground=TEXT)

    # ─────────────────────────────────────────────────────
    #  TOP-LEVEL UI
    # ─────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#111827", height=70)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text=f"🚀 AutoReach v{VERSION}", fg=ACCENT, bg="#111827",
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=20, pady=14)
        tk.Label(hdr, text="Smart WhatsApp Outreach  •  v4", fg=MUTED, bg="#111827",
                 font=("Segoe UI", 9)).pack(side="left", pady=20)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=10)

        tabs = {}
        for name in ("Send", "Log", "Settings", "Tips"):
            f = tk.Frame(nb, bg=BG)
            nb.add(f, text=f"  {name}  ")
            tabs[name] = f

        self._build_send_tab(tabs["Send"])
        self._build_log_tab(tabs["Log"])
        self._build_set_tab(tabs["Settings"])
        self._build_tips_tab(tabs["Tips"])

    # ─────────────────────────────────────────────────────
    #  SEND TAB
    # ─────────────────────────────────────────────────────
    def _build_send_tab(self, tab):
        tk.Label(tab, text="Message Template  (supports multi-line)",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 11, "bold")).pack(
                     anchor="w", padx=15, pady=(10, 4))

        # Message box
        msg_frame = tk.Frame(tab, bg=CARD, bd=1, relief="flat")
        msg_frame.pack(padx=15, pady=4, fill="x")
        self.msg_box = tk.Text(msg_frame, height=10, width=78,
                               bg=CARD, fg=TEXT, insertbackground=TEXT,
                               font=("Consolas", 9), relief="flat",
                               padx=10, pady=8, borderwidth=0)
        self.msg_box.pack()
        self.msg_box.insert("1.0", (
            "Hello 👋\n\n"
            "A separate student-led support community has been created for "
            "Google Gemini Student Ambassadors to help members with tasks, "
            "updates, resources, networking, collaboration, and doubt solving "
            "throughout the program.\n\n"
            "You're welcome to join the group here:\n"
            "https://chat.whatsapp.com/HBF8OYOOvfm7ihIutciSaw\n\n"
            "This group is independently organized by students and is only "
            "meant for helping and supporting fellow ambassadors.\n\n"
            "Feel free to join and also share it with other ambassadors you know 🚀"
        ))

        # Char counter
        self.lbl_chars = tk.Label(tab, text="Chars: 0", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 8))
        self.lbl_chars.pack(anchor="e", padx=15)
        self.msg_box.bind("<KeyRelease>", self._update_char_count)
        self._update_char_count()

        # Stats bar
        stats = tk.Frame(tab, bg="#111827", pady=8)
        stats.pack(fill="x", padx=15, pady=6)
        self.lbl_loaded  = tk.Label(stats, text="Loaded: 0",   bg="#111827", fg=TEXT,  font=("Segoe UI", 9, "bold"))
        self.lbl_sent    = tk.Label(stats, text="Sent: 0",     bg="#111827", fg=GREEN, font=("Segoe UI", 9, "bold"))
        self.lbl_failed  = tk.Label(stats, text="Failed: 0",   bg="#111827", fg=RED,   font=("Segoe UI", 9, "bold"))
        self.lbl_skipped = tk.Label(stats, text="Skipped: 0",  bg="#111827", fg=AMBER, font=("Segoe UI", 9, "bold"))
        self.lbl_eta     = tk.Label(stats, text="ETA: --:--",  bg="#111827", fg=BLUE,  font=("Segoe UI", 9, "bold"))
        for i, lbl in enumerate([self.lbl_loaded, self.lbl_sent, self.lbl_failed,
                                  self.lbl_skipped, self.lbl_eta]):
            lbl.grid(row=0, column=i, padx=12)

        # Progress
        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(tab, variable=self.progress_var,
                        maximum=100, length=740,
                        style="Horizontal.TProgressbar").pack(padx=15, pady=4)

        # Status
        self.lbl_status = tk.Label(tab, text="● Idle — Import your list to begin",
                                   bg=BG, fg=AMBER, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(pady=4)

        # Daily counter
        self.lbl_daily = tk.Label(tab, text="Sent today: 0/50",
                                  bg=BG, fg=GREEN, font=("Segoe UI", 9))
        self.lbl_daily.pack()

        # Dry-run checkbox
        self.dry_run_var = tk.BooleanVar(value=False)
        tk.Checkbutton(tab, text="🧪 Dry-Run mode (simulate without sending)",
                       variable=self.dry_run_var, bg=BG, fg=BLUE,
                       selectcolor=CARD, font=("Segoe UI", 9)).pack(pady=2)

        # Buttons (2 rows × 4 cols)
        btns = tk.Frame(tab, bg=BG)
        btns.pack(pady=8)
        self.btn_import  = ttk.Button(btns, text="📁 Import List",     command=self.import_list)
        self.btn_start   = ttk.Button(btns, text="▶  START",           command=self.start)
        self.btn_pause   = ttk.Button(btns, text="⏸ PAUSE",            command=self.toggle_pause, state="disabled")
        self.btn_stop    = ttk.Button(btns, text="⏹ STOP",             command=self.stop)
        self.btn_test    = ttk.Button(btns, text="🔬 Test 1 Number",   command=self.test_single)
        self.btn_retry   = ttk.Button(btns, text="🔁 Retry Failed",    command=self.retry_failed)
        self.btn_export  = ttk.Button(btns, text="💾 Export Failed",   command=self.export_failed)
        self.btn_black   = ttk.Button(btns, text="🔕 Blacklist",       command=self.add_to_blacklist)
        self.btn_clear   = ttk.Button(btns, text="🗑️ Clear Log",       command=self.clear_log)
        grid = [
            (0,0,self.btn_import),(0,1,self.btn_start),(0,2,self.btn_pause),(0,3,self.btn_stop),
            (1,0,self.btn_test),  (1,1,self.btn_retry),(1,2,self.btn_export),(1,3,self.btn_black),
            (2,0,self.btn_clear),
        ]
        for r, c, b in grid:
            b.grid(row=r, column=c, padx=6, pady=4, sticky="ew")

        # Warning
        tk.Label(tab,
                 text="⚠️  Keep WhatsApp Web open & logged in. Don't touch mouse/keyboard while running.",
                 bg=BG, fg=RED, font=("Segoe UI", 8, "bold")).pack(pady=6)

    # ─────────────────────────────────────────────────────
    #  LOG TAB
    # ─────────────────────────────────────────────────────
    def _build_log_tab(self, tab):
        tk.Label(tab, text="Session Log", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(pady=8)
        frm = tk.Frame(tab, bg=BG)
        frm.pack(fill="both", expand=True, padx=10, pady=4)
        scrl = tk.Scrollbar(frm)
        scrl.pack(side="right", fill="y")
        self.log_box = tk.Text(frm, bg=CARD, fg=MUTED, font=("Consolas", 9),
                               yscrollcommand=scrl.set, state="disabled",
                               relief="flat", borderwidth=0)
        self.log_box.pack(fill="both", expand=True)
        scrl.config(command=self.log_box.yview)
        # Colour tags
        self.log_box.tag_config("info",   foreground=BLUE)
        self.log_box.tag_config("sent",   foreground=GREEN)
        self.log_box.tag_config("failed", foreground=RED)
        self.log_box.tag_config("skip",   foreground=AMBER)
        self.log_box.tag_config("warn",   foreground="#FBBF24")
        self._log("info", f"AutoReach v{VERSION} ready.")

    # ─────────────────────────────────────────────────────
    #  SETTINGS TAB
    # ─────────────────────────────────────────────────────
    def _build_set_tab(self, tab):
        tk.Label(tab, text="Settings", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(pady=10)
        frm = tk.Frame(tab, bg=BG)
        frm.pack(padx=30, fill="x")

        self.delay_min_var  = tk.IntVar(value=20)
        self.delay_max_var  = tk.IntVar(value=40)
        self.load_var       = tk.IntVar(value=20)
        self.daily_lim_var  = tk.IntVar(value=40)
        self.retry_var      = tk.IntVar(value=2)
        self.type_speed_var = tk.IntVar(value=2)   # ms between keystrokes
        self.skip_sent_var  = tk.BooleanVar(value=True)
        self.skip_blk_var   = tk.BooleanVar(value=True)
        self.vary_msg_var   = tk.BooleanVar(value=True)
        self.type_msg_var   = tk.BooleanVar(value=True)  # type vs paste
        self.sound_var      = tk.BooleanVar(value=True)

        def row(label, var, from_, to_, r, note=""):
            full = label + ("  " + note if note else "")
            tk.Label(frm, text=full, bg=BG, fg=MUTED,
                     width=52, anchor="w").grid(row=r, column=0, pady=5, sticky="w")
            ttk.Spinbox(frm, from_=from_, to=to_, textvariable=var,
                        width=8).grid(row=r, column=1, pady=5)

        row("Min delay between messages (s):",        self.delay_min_var,  10, 90,  0, "↑ higher = safer")
        row("Max delay between messages (s):",        self.delay_max_var,  15, 180, 1)
        row("Max page-load wait (s):",                self.load_var,       10, 60,  2)
        row("Daily send limit (max 40 recommended):", self.daily_lim_var,   5, 200, 3)
        row("Retry attempts per number:",             self.retry_var,       1,  5,  4)
        row("Typing speed (ms between keystrokes):",  self.type_speed_var,  0, 50,  5)

        checks = [
            (6,  self.skip_sent_var, "Skip already-sent numbers"),
            (7,  self.skip_blk_var,  "Skip blacklisted numbers"),
            (8,  self.vary_msg_var,  "✅ Vary each message (anti-ban — adds invisible char)"),
            (9,  self.type_msg_var,  "✅ Type message (more human-like than paste)"),
            (10, self.sound_var,     "Play sound alert on finish"),
        ]
        for r, var, txt in checks:
            tk.Checkbutton(frm, text=txt, variable=var, bg=BG, fg=TEXT,
                           selectcolor=CARD).grid(row=r, column=0, columnspan=2,
                                                   sticky="w", pady=4)

    # ─────────────────────────────────────────────────────
    #  TIPS TAB
    # ─────────────────────────────────────────────────────
    def _build_tips_tab(self, tab):
        tk.Label(tab, text="Anti-Ban & Safety Tips", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=12)
        tips = [
            ("🔴 MOST IMPORTANT", RED,
             "Only message people who expect your message (program members, opt-ins).\n"
             "Messaging strangers = reports = permanent ban."),
            ("⏱  Delays", AMBER,
             "Keep min delay ≥ 20 s, max ≥ 40 s.\n"
             "WhatsApp flags rapid-fire identical sends immediately."),
            ("📊  Daily Limit", AMBER,
             "Stay under 40 messages/day on a new number.\n"
             "Older/verified accounts can safely do up to 80-100."),
            ("🔀  Message Variation", BLUE,
             "The 'Vary each message' setting inserts an invisible Unicode character\n"
             "so every send is a different byte string — much harder to auto-flag."),
            ("⌨️  Typing vs Paste", BLUE,
             "'Type message' mode simulates keystroke-by-keystroke, mimicking a human.\n"
             "Pasting large text blocks is a known bot signal."),
            ("🌐  WhatsApp Web", GREEN,
             "Keep WhatsApp Web open, logged in, and in the FOREGROUND.\n"
             "Use Chrome or Edge for best compatibility."),
            ("⚠️  Legal Note", MUTED,
             "WhatsApp ToS §4 prohibits bulk / automated messaging.\n"
             "Use only for consented recipients. You bear full responsibility."),
        ]
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0)
        scroll = tk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True, padx=15)
        inner = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        for title, col, body in tips:
            tk.Label(inner, text=title, bg=BG, fg=col,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
            tk.Label(inner, text=body, bg=CARD, fg=TEXT,
                     font=("Segoe UI", 9), wraplength=680, justify="left",
                     padx=12, pady=8).pack(fill="x", pady=2)
        inner.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    # ─────────────────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────────────────
    def _update_char_count(self, _evt=None):
        n = len(self.msg_box.get("1.0", tk.END).strip())
        self.lbl_chars.config(text=f"Chars: {n}")

    def _log(self, tag, text):
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}\n"
        def ins():
            self.log_box.config(state="normal")
            self.log_box.insert("end", line, tag)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.root.after(0, ins)

    def _update_daily_label(self):
        sent_today = self.logger.total_sent_today()
        limit      = self.daily_lim_var.get() if hasattr(self, "daily_lim_var") else 40
        fg         = RED if sent_today >= limit else GREEN
        self.lbl_daily.config(text=f"Sent today: {sent_today}/{limit}", fg=fg)

    def update_stats(self):
        def _up():
            self.lbl_loaded.config(text=f"Loaded: {self.total}")
            self.lbl_sent.config(text=f"Sent: {self.sent_count}")
            self.lbl_failed.config(text=f"Failed: {len(self.failed_list)}")
            self.lbl_skipped.config(text=f"Skipped: {self.skipped_count}")
            pct = (self.current_idx / self.total * 100) if self.total > 0 else 0.0
            self.progress_var.set(pct)
            if self.start_time and self.current_idx > 0:
                elapsed = time.time() - self.start_time
                rate    = elapsed / self.current_idx
                left    = self.total - self.current_idx
                eta_str = str(timedelta(seconds=int(rate * left)))
            else:
                eta_str = "--:--"
            self.lbl_eta.config(text=f"ETA: {eta_str}")
            self._update_daily_label()
        self.root.after(0, _up)

    def update_status(self, text):
        self.root.after(0, lambda: self.lbl_status.config(text=text))

    # ─────────────────────────────────────────────────────
    #  WINDOW ACTIVATION
    # ─────────────────────────────────────────────────────
    def _activate_whatsapp(self):
        if gw is None:
            return
        try:
            wins = gw.getWindowsWithTitle("WhatsApp")
            if not wins:
                wins = [w for w in gw.getAllWindows()
                        if "whatsapp" in getattr(w, "title", "").lower()]
            if wins:
                try:
                    wins[0].activate()
                except Exception:
                    pass
                try:
                    wins[0].maximize()
                except Exception:
                    pass
        except Exception:
            pass

    # ─────────────────────────────────────────────────────
    #  CLIPBOARD HELPER
    # ─────────────────────────────────────────────────────
    def _clipboard_get(self) -> str:
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    # ─────────────────────────────────────────────────────
    #  HUMAN-LIKE MOUSE JITTER (optional naturalness)
    # ─────────────────────────────────────────────────────
    def _mouse_jitter(self):
        """Move mouse slightly to simulate idle human presence."""
        try:
            x, y = pyautogui.position()
            dx = random.randint(-6, 6)
            dy = random.randint(-4, 4)
            pyautogui.moveTo(x + dx, y + dy, duration=random.uniform(0.1, 0.3))
        except Exception:
            pass

    # ─────────────────────────────────────────────────────
    #  WAIT FOR MESSAGE BOX LOADED (via clipboard check)
    # ─────────────────────────────────────────────────────
    def _wait_for_msgbox(self, expected: str, max_seconds: float) -> bool:
        """
        After opening the URL, WhatsApp Web pre-fills the text box.
        Poll the clipboard until the box content matches the expected text.
        """
        elapsed  = 0.0
        interval = 0.5
        while elapsed < max_seconds:
            if not self.running:
                return False
            while self.paused:
                time.sleep(0.2)
            try:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.15)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.15)
            except Exception:
                pass
            if self._clipboard_get().strip() == expected.strip():
                return True
            elapsed += interval
            self.update_status(f"● Waiting for WhatsApp… ({int(max_seconds - elapsed)}s)")
            time.sleep(interval)
        return False

    # ─────────────────────────────────────────────────────
    #  WAIT FOR SEND CONFIRMED (text box clears after send)
    # ─────────────────────────────────────────────────────
    def _wait_send_confirmed(self, max_seconds: float = 8.0) -> bool:
        elapsed  = 0.0
        interval = 0.4
        while elapsed < max_seconds:
            if not self.running:
                return False
            while self.paused:
                time.sleep(0.2)
            try:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.12)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.12)
            except Exception:
                pass
            if self._clipboard_get().strip() == "":
                return True
            elapsed += interval
            time.sleep(interval)
        return False

    # ─────────────────────────────────────────────────────
    #  TYPE MESSAGE (keystroke-by-keystroke)
    # ─────────────────────────────────────────────────────
    def _type_message(self, text: str):
        interval = self.type_speed_var.get() / 1000.0   # ms → s
        for char in text:
            if not self.running:
                return
            try:
                pyautogui.typewrite(char, interval=0)
            except Exception:
                # fallback for special chars (emoji, unicode)
                try:
                    pyperclip.copy(char)
                    pyautogui.hotkey("ctrl", "v")
                except Exception:
                    pass
            if interval > 0:
                time.sleep(interval + random.uniform(0, interval))

    # ─────────────────────────────────────────────────────
    #  CORE SEND LOGIC
    # ─────────────────────────────────────────────────────
    def _open_chat(self, number: str):
        """Open WhatsApp Web for a number (no pre-filled text — we type it)."""
        url = (f"https://web.whatsapp.com/send/"
               f"?phone={number}&type=phone_number&app_absent=0")
        webbrowser.open(url)

    def _open_chat_prefilled(self, number: str, encoded: str):
        """Open WhatsApp Web with pre-filled text (for paste mode)."""
        url = (f"https://web.whatsapp.com/send/"
               f"?phone={number}&text={encoded}&type=phone_number&app_absent=0")
        webbrowser.open(url)

    def send_message(self, number: str, raw_msg: str, msg_encoded: str) -> bool:
        """
        Attempt to send a message with up to `retry_var` tries.
        Returns True on success, False otherwise.
        """
        # Dry run: pretend it worked
        if self.dry_run_var.get():
            time.sleep(random.uniform(1.5, 3.0))
            return True

        retries  = self.retry_var.get()
        max_load = self.load_var.get()
        use_type = self.type_msg_var.get()
        vary     = self.vary_msg_var.get()

        for attempt in range(1, retries + 1):
            if not self.running:
                return False
            if attempt > 1:
                self._log("warn", f"  Retry {attempt}/{retries} for {number}")
                time.sleep(human_delay(3, 6))

            # Build per-attempt message (varied if enabled)
            msg_to_send   = vary_message(raw_msg) if vary else raw_msg
            msg_enc_local = urllib.parse.quote(msg_to_send)

            # ── Open WhatsApp Web ──
            if use_type:
                self._open_chat(number)
            else:
                self._open_chat_prefilled(number, msg_enc_local)

            time.sleep(2.5)
            self._activate_whatsapp()
            time.sleep(1.0)

            if use_type:
                # ── Type mode ──
                # Wait for page load by sleeping (configurable)
                for i in range(max_load):
                    if not self.running:
                        return False
                    while self.paused:
                        time.sleep(0.2)
                    self.update_status(f"● Waiting for chat… ({max_load - i}s)")
                    time.sleep(1.0)

                # Focus message box: click bottom-centre of screen (where WA input lives)
                try:
                    sw, sh = pyautogui.size()
                    self._mouse_jitter()
                    # Click the typical WhatsApp Web message-input region
                    pyautogui.click(sw // 2, int(sh * 0.93),
                                    duration=random.uniform(0.1, 0.25))
                    time.sleep(0.5)
                except Exception:
                    pass

                # Type the message
                self._type_message(msg_to_send)
                time.sleep(0.4)

                # Press Enter to send
                try:
                    pyautogui.press("enter")
                except Exception:
                    pass

                confirmed = self._wait_send_confirmed(8.0)

            else:
                # ── Paste / pre-filled mode ──
                loaded = self._wait_for_msgbox(msg_to_send, max_load)
                if not loaded:
                    self._log("warn", f"  Pre-fill not detected for {number} "
                                      f"(attempt {attempt})")
                    try:
                        pyautogui.hotkey("ctrl", "w")
                        time.sleep(1.0)
                    except Exception:
                        pass
                    if attempt == retries:
                        return False
                    continue

                self._mouse_jitter()
                try:
                    pyautogui.press("enter")
                except Exception:
                    pass
                confirmed = self._wait_send_confirmed(8.0)

            # ── Close tab ──
            try:
                pyautogui.hotkey("ctrl", "w")
                time.sleep(1.2)
            except Exception:
                pass

            if confirmed:
                return True
            else:
                self._log("warn", f"  Send not confirmed for {number} "
                                  f"(attempt {attempt})")
                if attempt == retries:
                    return False

        return False

    # ─────────────────────────────────────────────────────
    #  ACTIONS
    # ─────────────────────────────────────────────────────
    def import_list(self):
        path = filedialog.askopenfilename(
            title="Select phone number list",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_lines = [ln.strip() for ln in f if ln.strip()]
        except Exception as e:
            messagebox.showerror("Read Error", str(e))
            return

        clean, seen = [], set()
        skipped = 0
        for s in raw_lines:
            digits = "".join(filter(str.isdigit, s))
            # Auto-prepend India country code for 10-digit numbers
            if len(digits) == 10:
                digits = "91" + digits
            if len(digits) == 12 and digits not in seen:
                seen.add(digits)
                clean.append(digits)
            else:
                skipped += 1

        self.numbers      = clean
        self.total        = len(clean)
        self.current_idx  = 0
        self.sent_count   = 0
        self.failed_list  = []
        self.skipped_count= 0
        self.update_stats()
        self._log("info", f"Imported {self.total} numbers "
                          f"({skipped} invalid/duplicate skipped).")
        messagebox.showinfo("Import Complete",
                            f"✅ {self.total} valid numbers loaded.\n"
                            f"⚠️ {skipped} lines skipped (invalid/duplicate).")

    def test_single(self):
        val = simpledialog.askstring("Test Single Number",
                                     "Enter a number to test send (10 or 12 digits):")
        if not val:
            return
        digits = "".join(filter(str.isdigit, val))
        if len(digits) == 10:
            digits = "91" + digits
        if len(digits) != 12:
            messagebox.showwarning("Invalid", "Enter a valid 10 or 12-digit number.")
            return
        raw_msg     = self.msg_box.get("1.0", tk.END).strip()
        msg_encoded = urllib.parse.quote(raw_msg)
        self._log("info", f"Test send to {digits}…")
        def _run():
            ok = self.send_message(digits, raw_msg, msg_encoded)
            result = "✅ Test sent successfully!" if ok else "❌ Test FAILED."
            self._log("sent" if ok else "failed", result)
            self.root.after(0, lambda: messagebox.showinfo("Test Result", result))
        threading.Thread(target=_run, daemon=True).start()

    def start(self):
        if not self.numbers:
            messagebox.showwarning("No List", "Import a number list first.")
            return
        if self.current_idx >= self.total:
            messagebox.showinfo("Done", "All processed. Re-import to restart.")
            return
        limit = self.daily_lim_var.get()
        if self.logger.total_sent_today() >= limit:
            messagebox.showwarning("Daily Limit",
                                   f"You've hit today's limit of {limit} messages.\n"
                                   "Change the limit in Settings or wait until tomorrow.")
            return
        self.running    = True
        self.paused     = False
        self.start_time = time.time()
        self._stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ PAUSE")
        self.update_status("● Running…")
        self._log("info", f"Session started — {self.total - self.current_idx} numbers remaining.")
        if self.dry_run_var.get():
            self._log("warn", "⚠️  DRY RUN MODE — no messages will be sent.")
        threading.Thread(target=self.run_loop, daemon=True).start()

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RESUME")
            self.update_status(f"● Paused at {self.current_idx}/{self.total}")
            self._log("warn", "Paused by user.")
        else:
            self.btn_pause.config(text="⏸ PAUSE")
            self.update_status("● Running…")
            self._log("info", "Resumed.")

    def stop(self):
        self.running = False
        self.paused  = False
        self._stop_event.set()
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ PAUSE")
        self.update_status(f"● Stopped at {self.current_idx}/{self.total}")
        self._log("warn", "Stopped by user.")

    def retry_failed(self):
        if not self.failed_list:
            messagebox.showinfo("Nothing to Retry", "No failed numbers.")
            return
        self.numbers      = list(self.failed_list)
        self.total        = len(self.numbers)
        self.current_idx  = 0
        self.sent_count   = 0
        self.failed_list  = []
        self.skipped_count= 0
        self.update_stats()
        self._log("info", f"Loaded {self.total} failed numbers for retry.")
        messagebox.showinfo("Retry", f"Loaded {self.total} failed numbers.")

    def export_failed(self):
        if not self.failed_list:
            messagebox.showinfo("Nothing to Export", "No failed numbers.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="failed_numbers.txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for n in self.failed_list:
                    f.write(n + "\n")
            messagebox.showinfo("Exported", f"Saved {len(self.failed_list)} numbers to file.")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def add_to_blacklist(self):
        val = simpledialog.askstring(
            "Add to Blacklist",
            "Enter number to blacklist (or leave blank to blacklist all failed):")
        if val:
            digits = "".join(filter(str.isdigit, val))
            if len(digits) == 10:
                digits = "91" + digits
            if len(digits) == 12:
                self.blacklist.add(digits)
                self._log("warn", f"Blacklisted: {digits}")
                messagebox.showinfo("Done", f"Added {digits} to blacklist.")
            else:
                messagebox.showwarning("Invalid", "Enter a valid 10 or 12-digit number.")
        elif self.failed_list:
            for n in self.failed_list:
                self.blacklist.add(n)
            self._log("warn", f"Blacklisted {len(self.failed_list)} failed numbers.")
            messagebox.showinfo("Done", f"Blacklisted {len(self.failed_list)} failed numbers.")
        else:
            messagebox.showinfo("Empty", "No failed numbers and no input provided.")

    def clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")
        self._log("info", "Log cleared.")

    # ─────────────────────────────────────────────────────
    #  MAIN SEND LOOP
    # ─────────────────────────────────────────────────────
    def run_loop(self):
        raw_msg     = self.msg_box.get("1.0", tk.END).strip()
        msg_encoded = urllib.parse.quote(raw_msg)
        sent_set    = self.logger.get_all_sent_numbers()
        limit       = self.daily_lim_var.get()

        while self.current_idx < self.total and self.running:
            # Pause
            if self.paused:
                time.sleep(0.3)
                continue

            # Daily limit guard
            if self.logger.total_sent_today() >= limit:
                self._log("warn", f"Daily limit of {limit} reached. Stopping.")
                messagebox.showwarning("Daily Limit",
                                       f"Reached today's limit of {limit} messages.\n"
                                       "Session stopped.")
                break

            number = self.numbers[self.current_idx]
            idx    = self.current_idx + 1

            # Skip checks
            if self.skip_sent_var.get() and number in sent_set:
                self._log("skip", f"↷ Already sent: {number}")
                self.skipped_count  += 1
                self.current_idx    += 1
                self.update_stats()
                continue

            if self.skip_blk_var.get() and self.blacklist.contains(number):
                self._log("skip", f"↷ Blacklisted: {number}")
                self.skipped_count  += 1
                self.current_idx    += 1
                self.update_stats()
                continue

            # Send
            self._log("info", f"► {idx}/{self.total}  {number}")
            self.update_status(f"● Sending {idx}/{self.total} → {number}")
            ok = self.send_message(number, raw_msg, msg_encoded)

            self.current_idx += 1
            if ok:
                self.sent_count += 1
                sent_set.add(number)
                self.logger.log_sent(number)
                self._log("sent", f"✅ Sent → {number}")
            else:
                self.failed_list.append(number)
                self.logger.log_failed(number)
                self._log("failed", f"❌ Failed → {number}")

            self.update_stats()

            # Inter-message delay (human-like Gaussian)
            if self.current_idx < self.total and self.running:
                dmin  = self.delay_min_var.get()
                dmax  = self.delay_max_var.get()
                delay = human_delay(dmin, dmax)
                self._log("info", f"  Waiting {delay:.1f}s …")
                elapsed  = 0.0
                interval = 0.5
                while elapsed < delay:
                    if not self.running:
                        break
                    while self.paused:
                        time.sleep(0.2)
                    rem = int(delay - elapsed)
                    self.update_status(f"● Next in {rem}s …")
                    # Occasional mouse jitter during idle wait
                    if random.random() < 0.15:
                        self._mouse_jitter()
                    time.sleep(interval)
                    elapsed += interval
                if not self.running:
                    break

        # ── Finished ──
        self.running = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))

        if self.current_idx >= self.total:
            self._log("info", "🎉 All messages processed!")
            self.update_status("● All Done! 🎉")
            summary = (f"✅ Sent:    {self.sent_count}\n"
                       f"❌ Failed:  {len(self.failed_list)}\n"
                       f"↷ Skipped: {self.skipped_count}\n\n"
                       f"{'(DRY RUN — nothing was actually sent)' if self.dry_run_var.get() else ''}")
            self.root.after(0, lambda: messagebox.showinfo("Session Finished", summary))
            if self.sound_var.get():
                try:
                    self.root.bell()
                except Exception:
                    pass
        else:
            self.update_status(f"● Stopped at {self.current_idx}/{self.total}")


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = OutreachTool(root)
    root.mainloop()
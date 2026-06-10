# -*- coding: utf-8 -*-
"""
AutoReach v5.0 — WhatsApp Outreach Automation
Only message people who have opted in / expect your message.
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

# ═══════════════════════════════════════════
VERSION        = "5.0"
LOG_FILE       = "autoreach_log.json"
BLACKLIST_FILE = "blacklist.txt"
CALIB_FILE     = "calibration.json"

BG     = "#0F1115"
CARD   = "#161A1F"
ACCENT = "#4F8CFF"
TEXT   = "#E6E6E6"
MUTED  = "#9AA0A6"
GREEN  = "#22C55E"
RED    = "#EF4444"
AMBER  = "#F59E0B"
BLUE   = "#60A5FA"

_INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060"]

pyautogui.FAILSAFE = True   # move mouse to top-left corner to emergency-stop
pyautogui.PAUSE    = 0.05


# ═══════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════
def human_delay(mn, mx):
    mu = (mn + mx) / 2
    sg = (mx - mn) / 4
    return max(mn, min(mx, random.gauss(mu, sg)))

def vary_msg(text):
    words = text.split(" ")
    if len(words) < 4:
        return text
    pos = random.randint(1, len(words) - 2)
    words[pos] += random.choice(_INVISIBLE)
    return " ".join(words)

def clean_number(s):
    d = "".join(filter(str.isdigit, s))
    if len(d) == 10: d = "91" + d
    return d if len(d) == 12 else None


# ═══════════════════════════════════════════
#  LOGGER
# ═══════════════════════════════════════════
class Logger:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"sent": [], "failed": []}

    def _save(self):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def log_sent(self, n):
        self.data["sent"].append({"n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self._save()

    def log_failed(self, n):
        self.data["failed"].append({"n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self._save()

    def sent_numbers(self):
        return {e["n"] for e in self.data["sent"]}

    def sent_today(self):
        d = datetime.now().strftime("%Y-%m-%d")
        return sum(1 for e in self.data["sent"] if e["t"].startswith(d))


# ═══════════════════════════════════════════
#  BLACKLIST
# ═══════════════════════════════════════════
class Blacklist:
    def __init__(self):
        self.nums = self._load()

    def _load(self):
        if os.path.exists(BLACKLIST_FILE):
            try:
                with open(BLACKLIST_FILE, encoding="utf-8") as f:
                    return {l.strip() for l in f if l.strip()}
            except Exception:
                pass
        return set()

    def add(self, n):
        if n not in self.nums:
            self.nums.add(n)
            with open(BLACKLIST_FILE, "a", encoding="utf-8") as f:
                f.write(n + "\n")

    def has(self, n):
        return n in self.nums


# ═══════════════════════════════════════════
#  CALIBRATION  (where to click the WA input box)
# ═══════════════════════════════════════════
class Calibration:
    def __init__(self):
        self.x = None
        self.y = None
        self._load()

    def _load(self):
        if os.path.exists(CALIB_FILE):
            try:
                d = json.load(open(CALIB_FILE))
                self.x = d.get("x")
                self.y = d.get("y")
            except Exception:
                pass

    def save(self, x, y):
        self.x = x
        self.y = y
        with open(CALIB_FILE, "w") as f:
            json.dump({"x": x, "y": y}, f)

    def get(self):
        """Return calibrated (x,y) or fall back to 50% × 93% of screen."""
        if self.x and self.y:
            return self.x, self.y
        sw, sh = pyautogui.size()
        return int(sw * 0.50), int(sh * 0.93)


# ═══════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════
class OutreachTool:
    def __init__(self, root):
        self.root = root
        self.root.title(f"AutoReach v{VERSION}")
        self.root.geometry("820x950")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # state
        self.numbers       = []
        self.current_idx   = 0
        self.total         = 0
        self.sent_count    = 0
        self.failed_list   = []
        self.skipped_count = 0
        self.running       = False
        self.paused        = False
        self.start_time    = None

        self.logger    = Logger()
        self.blacklist = Blacklist()
        self.calib     = Calibration()

        self._style()
        self._build_ui()
        self._refresh_daily()

    # ───────────────────────────────────────
    #  STYLE
    # ───────────────────────────────────────
    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TButton", background=CARD, foreground=TEXT,
                    font=("Segoe UI", 9, "bold"), borderwidth=0)
        s.map("TButton", background=[("active", ACCENT)])
        s.configure("TNotebook",     background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=MUTED,
                    font=("Segoe UI", 9), padding=[14, 6])
        s.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#fff")])
        s.configure("Horizontal.TProgressbar",
                    troughcolor=CARD, background=ACCENT, borderwidth=0)

    # ───────────────────────────────────────
    #  BUILD UI
    # ───────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#111827", height=65)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text=f"🚀 AutoReach v{VERSION}",
                 fg=ACCENT, bg="#111827",
                 font=("Segoe UI", 17, "bold")).pack(side="left", padx=18, pady=12)
        tk.Label(hdr, text="WhatsApp Outreach — Fully Automated",
                 fg=MUTED, bg="#111827",
                 font=("Segoe UI", 9)).pack(side="left", pady=18)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=8)

        t = {n: tk.Frame(nb, bg=BG) for n in ("Send", "Log", "Settings", "Calibrate")}
        for name, frame in t.items():
            nb.add(frame, text=f"  {name}  ")

        self._tab_send(t["Send"])
        self._tab_log(t["Log"])
        self._tab_settings(t["Settings"])
        self._tab_calibrate(t["Calibrate"])

    # ───────────────────────────────────────
    #  SEND TAB
    # ───────────────────────────────────────
    def _tab_send(self, tab):
        # ── message label row ──
        top = tk.Frame(tab, bg=BG)
        top.pack(fill="x", padx=15, pady=(10, 3))
        tk.Label(top, text="Message Template", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")

        # Send-mode toggle  (right side of label row)
        self.single_send_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            top,
            text="📋 One message (preserve formatting)",
            variable=self.single_send_var,
            bg=BG, fg=BLUE, selectcolor=CARD,
            font=("Segoe UI", 9, "bold"),
            command=self._on_mode_change
        ).pack(side="right")

        # Mode hint label
        self.lbl_mode = tk.Label(tab,
            text="▸ Mode: single send  (newlines → Shift+Enter in WhatsApp)",
            bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_mode.pack(anchor="e", padx=15)

        # ── message box ──
        mf = tk.Frame(tab, bg=CARD, bd=0)
        mf.pack(padx=15, pady=3, fill="x")
        self.msg_box = tk.Text(mf, height=10, bg=CARD, fg=TEXT,
                               insertbackground=TEXT,
                               font=("Consolas", 9),
                               relief="flat", padx=10, pady=8, borderwidth=0,
                               undo=True)
        self.msg_box.pack(fill="x")
        self.msg_box.insert("1.0",
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
        )
        self.msg_box.bind("<KeyRelease>", self._update_chars)
        self.lbl_chars = tk.Label(tab, text="", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 8))
        self.lbl_chars.pack(anchor="e", padx=15)
        self._update_chars()

        # ── stats bar ──
        sf = tk.Frame(tab, bg="#111827", pady=7)
        sf.pack(fill="x", padx=15, pady=6)
        self.lbl_loaded  = tk.Label(sf, text="Loaded: 0",  bg="#111827", fg=TEXT,   font=("Segoe UI", 9, "bold"))
        self.lbl_sent    = tk.Label(sf, text="Sent: 0",    bg="#111827", fg=GREEN,  font=("Segoe UI", 9, "bold"))
        self.lbl_failed  = tk.Label(sf, text="Failed: 0",  bg="#111827", fg=RED,    font=("Segoe UI", 9, "bold"))
        self.lbl_skipped = tk.Label(sf, text="Skipped: 0", bg="#111827", fg=AMBER,  font=("Segoe UI", 9, "bold"))
        self.lbl_eta     = tk.Label(sf, text="ETA: --",    bg="#111827", fg=BLUE,   font=("Segoe UI", 9, "bold"))
        for i, l in enumerate([self.lbl_loaded, self.lbl_sent, self.lbl_failed,
                                self.lbl_skipped, self.lbl_eta]):
            l.grid(row=0, column=i, padx=11)

        # ── progress ──
        self.prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(tab, variable=self.prog_var, maximum=100,
                        length=750).pack(padx=15, pady=3)

        # ── status ──
        self.lbl_status = tk.Label(tab,
            text="● Idle — Import your list to begin",
            bg=BG, fg=AMBER, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(pady=3)
        self.lbl_daily = tk.Label(tab, text="Sent today: 0/40",
                                  bg=BG, fg=GREEN, font=("Segoe UI", 9))
        self.lbl_daily.pack()

        # ── dry run ──
        self.dry_var = tk.BooleanVar(value=False)
        tk.Checkbutton(tab, text="🧪 Dry-Run (simulate — no real sends)",
                       variable=self.dry_var, bg=BG, fg=BLUE,
                       selectcolor=CARD, font=("Segoe UI", 9)).pack(pady=2)

        # ── buttons ──
        bf = tk.Frame(tab, bg=BG)
        bf.pack(pady=7)
        self.btn_import = ttk.Button(bf, text="📁 Import List",    command=self.import_list)
        self.btn_start  = ttk.Button(bf, text="▶  START",          command=self.start)
        self.btn_pause  = ttk.Button(bf, text="⏸ PAUSE",           command=self.toggle_pause, state="disabled")
        self.btn_stop   = ttk.Button(bf, text="⏹ STOP",            command=self.stop)
        self.btn_test   = ttk.Button(bf, text="🔬 Test 1 Number",  command=self.test_single)
        self.btn_retry  = ttk.Button(bf, text="🔁 Retry Failed",   command=self.retry_failed)
        self.btn_export = ttk.Button(bf, text="💾 Export Failed",  command=self.export_failed)
        self.btn_bl     = ttk.Button(bf, text="🔕 Blacklist",      command=self.add_blacklist)
        self.btn_clear  = ttk.Button(bf, text="🗑 Clear Log",      command=self.clear_log)
        grid = [
            (0,0,self.btn_import),(0,1,self.btn_start),(0,2,self.btn_pause),(0,3,self.btn_stop),
            (1,0,self.btn_test),  (1,1,self.btn_retry),(1,2,self.btn_export),(1,3,self.btn_bl),
            (2,0,self.btn_clear),
        ]
        for r,c,b in grid:
            b.grid(row=r, column=c, padx=6, pady=4, sticky="ew")

        # ── warning ──
        tk.Label(tab,
            text="⚠  Keep WhatsApp Web open in Chrome/Edge.  "
                 "Move mouse to TOP-LEFT CORNER to emergency-stop.",
            bg=BG, fg=RED, font=("Segoe UI", 8, "bold")).pack(pady=5)

    # ───────────────────────────────────────
    #  LOG TAB
    # ───────────────────────────────────────
    def _tab_log(self, tab):
        tk.Label(tab, text="Session Log", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(pady=8)
        fr = tk.Frame(tab, bg=BG)
        fr.pack(fill="both", expand=True, padx=10, pady=4)
        sc = tk.Scrollbar(fr)
        sc.pack(side="right", fill="y")
        self.log_box = tk.Text(fr, bg=CARD, fg=MUTED, font=("Consolas", 9),
                               yscrollcommand=sc.set, state="disabled",
                               relief="flat", borderwidth=0)
        self.log_box.pack(fill="both", expand=True)
        sc.config(command=self.log_box.yview)
        self.log_box.tag_config("info",   foreground=BLUE)
        self.log_box.tag_config("sent",   foreground=GREEN)
        self.log_box.tag_config("failed", foreground=RED)
        self.log_box.tag_config("skip",   foreground=AMBER)
        self.log_box.tag_config("warn",   foreground="#FBBF24")
        self._log("info", f"AutoReach v{VERSION} ready.")

    # ───────────────────────────────────────
    #  SETTINGS TAB
    # ───────────────────────────────────────
    def _tab_settings(self, tab):
        tk.Label(tab, text="Settings", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(pady=10)
        fr = tk.Frame(tab, bg=BG)
        fr.pack(padx=30, fill="x")

        self.v_dmin      = tk.IntVar(value=22)
        self.v_dmax      = tk.IntVar(value=45)
        self.v_timeout   = tk.IntVar(value=30)   # per-message timeout
        self.v_load      = tk.IntVar(value=15)   # extra wait after URL open
        self.v_dlimit    = tk.IntVar(value=40)
        self.v_retries   = tk.IntVar(value=2)
        self.v_skip_sent = tk.BooleanVar(value=True)
        self.v_skip_bl   = tk.BooleanVar(value=True)
        self.v_vary      = tk.BooleanVar(value=True)
        self.v_bg        = tk.BooleanVar(value=True)   # background mode
        self.v_sound     = tk.BooleanVar(value=True)

        def row(lbl, var, lo, hi, r, note=""):
            tk.Label(fr, text=lbl + ("  " + note if note else ""),
                     bg=BG, fg=MUTED, width=52, anchor="w").grid(
                         row=r, column=0, pady=5, sticky="w")
            ttk.Spinbox(fr, from_=lo, to=hi, textvariable=var,
                        width=8).grid(row=r, column=1, pady=5)

        row("Min delay between messages (s):",           self.v_dmin,    10, 120, 0, "↑ safer")
        row("Max delay between messages (s):",           self.v_dmax,    15, 240, 1)
        row("Per-message timeout (s) — then skip:",      self.v_timeout, 15, 120, 2, "closes tab & moves on")
        row("Extra wait after URL opens (s):",           self.v_load,     5,  60, 3, "for slow connections")
        row("Daily send limit:",                         self.v_dlimit,   5, 200, 4)
        row("Retry attempts per number:",                self.v_retries,  1,   5, 5)

        checks = [
            (6,  self.v_skip_sent, "Skip already-sent numbers"),
            (7,  self.v_skip_bl,   "Skip blacklisted numbers"),
            (8,  self.v_vary,      "✅ Vary each message (anti-spam — invisible char)"),
            (9,  self.v_bg,        "✅ Background mode (minimize window while running)"),
            (10, self.v_sound,     "Play sound when all done"),
        ]
        for r, var, txt in checks:
            tk.Checkbutton(fr, text=txt, variable=var,
                           bg=BG, fg=TEXT, selectcolor=CARD).grid(
                               row=r, column=0, columnspan=2,
                               sticky="w", pady=4)

    # ───────────────────────────────────────
    #  CALIBRATE TAB
    # ───────────────────────────────────────
    def _tab_calibrate(self, tab):
        tk.Label(tab, text="Click-Position Calibration",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 12, "bold")).pack(pady=14)

        info = (
            "AutoReach needs to click the WhatsApp Web message-input box automatically.\n\n"
            "HOW TO CALIBRATE (one-time setup):\n"
            "  1. Open WhatsApp Web in your browser and open any chat.\n"
            "  2. Come back to this window.\n"
            "  3. Click  'Start 3-second countdown'  below.\n"
            "  4. Within 3 seconds, move your mouse to the message-input box in WhatsApp Web\n"
            "     (the text field at the bottom where you type).\n"
            "  5. Hold still — the position is saved automatically.\n\n"
            "If WhatsApp Web layout changes, just calibrate again."
        )
        tk.Label(tab, text=info, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9), justify="left",
                 wraplength=680, padx=18, pady=14).pack(padx=20, fill="x")

        self.lbl_calib_status = tk.Label(tab, bg=BG, fg=GREEN,
                                         font=("Segoe UI", 10, "bold"))
        self.lbl_calib_status.pack(pady=10)
        self._refresh_calib_status()

        self.lbl_countdown = tk.Label(tab, text="", bg=BG, fg=AMBER,
                                      font=("Segoe UI", 28, "bold"))
        self.lbl_countdown.pack(pady=6)

        ttk.Button(tab, text="🎯  Start 3-second countdown",
                   command=self._calibrate_start).pack(pady=8)
        ttk.Button(tab, text="🔄  Reset to default position",
                   command=self._calibrate_reset).pack(pady=4)

    # ───────────────────────────────────────
    #  CALIBRATE LOGIC
    # ───────────────────────────────────────
    def _refresh_calib_status(self):
        cx, cy = self.calib.get()
        src = "calibrated" if self.calib.x else "default (estimated)"
        self.lbl_calib_status.config(
            text=f"Current click target: X={cx}  Y={cy}   [{src}]")

    def _calibrate_start(self):
        def _run():
            for i in range(3, 0, -1):
                self.lbl_countdown.config(text=str(i))
                time.sleep(1.0)
            x, y = pyautogui.position()
            self.calib.save(x, y)
            self.lbl_countdown.config(text="✅  Saved!")
            self._refresh_calib_status()
            time.sleep(1.5)
            self.lbl_countdown.config(text="")
        threading.Thread(target=_run, daemon=True).start()

    def _calibrate_reset(self):
        if os.path.exists(CALIB_FILE):
            os.remove(CALIB_FILE)
        self.calib.x = None
        self.calib.y = None
        self._refresh_calib_status()
        messagebox.showinfo("Reset", "Calibration reset to default screen position.")

    # ───────────────────────────────────────
    #  HELPERS
    # ───────────────────────────────────────
    def _on_mode_change(self):
        if self.single_send_var.get():
            self.lbl_mode.config(
                text="▸ Mode: single send  (newlines → Shift+Enter in WhatsApp)")
        else:
            self.lbl_mode.config(
                text="▸ Mode: paragraph split  (each paragraph = separate message)")

    def _update_chars(self, _=None):
        n = len(self.msg_box.get("1.0", tk.END).strip())
        self.lbl_chars.config(text=f"Characters: {n}")

    def _log(self, tag, text):
        ts = datetime.now().strftime("%H:%M:%S")
        def _ins():
            self.log_box.config(state="normal")
            self.log_box.insert("end", f"[{ts}] {text}\n", tag)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.root.after(0, _ins)

    def _set_status(self, txt):
        self.root.after(0, lambda: self.lbl_status.config(text=txt))

    def _refresh_daily(self):
        today = self.logger.sent_today()
        lim   = self.v_dlimit.get() if hasattr(self, "v_dlimit") else 40
        fg    = RED if today >= lim else GREEN
        self.lbl_daily.config(text=f"Sent today: {today}/{lim}", fg=fg)

    def _update_stats(self):
        def _up():
            self.lbl_loaded.config(text=f"Loaded: {self.total}")
            self.lbl_sent.config(text=f"Sent: {self.sent_count}")
            self.lbl_failed.config(text=f"Failed: {len(self.failed_list)}")
            self.lbl_skipped.config(text=f"Skipped: {self.skipped_count}")
            pct = (self.current_idx / self.total * 100) if self.total else 0
            self.prog_var.set(pct)
            if self.start_time and self.current_idx > 0:
                e = time.time() - self.start_time
                r = (self.total - self.current_idx) * (e / self.current_idx)
                eta = str(timedelta(seconds=int(r)))
            else:
                eta = "--:--"
            self.lbl_eta.config(text=f"ETA: {eta}")
            self._refresh_daily()
        self.root.after(0, _up)

    # ───────────────────────────────────────
    #  WINDOW MANAGEMENT
    # ───────────────────────────────────────
    def _minimize(self):
        self.root.after(0, lambda: self.root.iconify())

    def _restore(self):
        self.root.after(0, lambda: (self.root.deiconify(),
                                    self.root.lift()))

    def _activate_browser(self):
        if gw is None:
            return
        try:
            for title_kw in ("WhatsApp", "whatsapp"):
                wins = [w for w in gw.getAllWindows()
                        if title_kw.lower() in getattr(w, "title", "").lower()]
                if wins:
                    try: wins[0].activate()
                    except Exception: pass
                    try: wins[0].maximize()
                    except Exception: pass
                    return
        except Exception:
            pass

    # ───────────────────────────────────────
    #  CLIPBOARD
    # ───────────────────────────────────────
    def _clip(self):
        try: return pyperclip.paste()
        except Exception: return ""

    # ───────────────────────────────────────
    #  CLOSE CURRENT TAB
    # ───────────────────────────────────────
    def _close_tab(self):
        try:
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.8)
        except Exception:
            pass

    # ───────────────────────────────────────
    #  CLICK MESSAGE BOX
    # ───────────────────────────────────────
    def _click_msgbox(self):
        """
        Click the WhatsApp Web message-input area.
        Uses calibrated position, falls back to 50% × 93% of screen.
        """
        cx, cy = self.calib.get()
        try:
            # Small random offset so it doesn't look robotic
            ox = random.randint(-8, 8)
            oy = random.randint(-4, 4)
            pyautogui.moveTo(cx + ox, cy + oy,
                             duration=random.uniform(0.15, 0.35))
            time.sleep(0.1)
            pyautogui.click()
            time.sleep(0.4)
        except Exception:
            pass

    # ───────────────────────────────────────
    #  WAIT FOR INPUT-BOX TO BE EMPTY (send confirmed)
    # ───────────────────────────────────────
    def _wait_empty(self, max_sec=8.0):
        deadline = time.time() + max_sec
        while time.time() < deadline:
            if not self.running: return False
            while self.paused: time.sleep(0.2)
            try:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.12)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.12)
            except Exception: pass
            if self._clip().strip() == "":
                return True
            time.sleep(0.35)
        return False

    # ───────────────────────────────────────
    #  PASTE FULL MESSAGE (preserves formatting)
    # ───────────────────────────────────────
    def _paste_message(self, text):
        """Copy text to clipboard and paste into focused element."""
        try:
            pyperclip.copy(text)
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
        except Exception:
            pass

    # ───────────────────────────────────────
    #  SEND ONE MESSAGE  (single-send mode)
    # ───────────────────────────────────────
    def _send_single(self, number, msg):
        """
        Open WA Web, click the box, paste the whole message,
        press Enter once.  Returns True/False.
        """
        timeout   = self.v_timeout.get()
        extra_wait= self.v_load.get()
        deadline  = time.time() + timeout

        url = (f"https://web.whatsapp.com/send/"
               f"?phone={number}&type=phone_number&app_absent=0")
        webbrowser.open(url)
        time.sleep(2.5)
        self._activate_browser()
        time.sleep(0.5)

        # Wait for page to load (extra_wait seconds)
        for i in range(extra_wait):
            if not self.running or time.time() > deadline:
                self._close_tab()
                return False
            while self.paused: time.sleep(0.2)
            self._set_status(f"● Loading WA… ({extra_wait - i}s)")
            time.sleep(1.0)

        if time.time() > deadline:
            self._close_tab()
            return False

        # Click the message input box
        self._click_msgbox()

        # Paste message (preserves ALL newlines & formatting)
        self._paste_message(msg)

        # Verify something is in the box
        time.sleep(0.3)
        try:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.12)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.12)
        except Exception: pass
        if self._clip().strip() == "":
            # Paste didn't land — try once more
            self._click_msgbox()
            self._paste_message(msg)
            time.sleep(0.3)

        # Send (Enter)
        try:
            pyautogui.press("enter")
        except Exception: pass

        # Wait for box to clear (confirms send)
        confirmed = self._wait_empty(min(8.0, deadline - time.time()))

        self._close_tab()
        return confirmed

    # ───────────────────────────────────────
    #  SEND PARAGRAPH-SPLIT MODE
    # ───────────────────────────────────────
    def _send_paragraphs(self, number, msg):
        """
        Split by blank line and send each paragraph as a separate message.
        Opens only one tab; sends each part with a short pause between.
        """
        timeout    = self.v_timeout.get()
        extra_wait = self.v_load.get()
        deadline   = time.time() + timeout

        parts = [p.strip() for p in msg.split("\n\n") if p.strip()]
        if not parts:
            return False

        url = (f"https://web.whatsapp.com/send/"
               f"?phone={number}&type=phone_number&app_absent=0")
        webbrowser.open(url)
        time.sleep(2.5)
        self._activate_browser()
        time.sleep(0.5)

        for i in range(extra_wait):
            if not self.running or time.time() > deadline:
                self._close_tab(); return False
            while self.paused: time.sleep(0.2)
            self._set_status(f"● Loading WA… ({extra_wait - i}s)")
            time.sleep(1.0)

        if time.time() > deadline:
            self._close_tab(); return False

        self._click_msgbox()

        ok_all = True
        for i, part in enumerate(parts):
            if not self.running or time.time() > deadline:
                ok_all = False; break
            self._paste_message(part)
            time.sleep(0.3)
            pyautogui.press("enter")
            confirmed = self._wait_empty(min(5.0, deadline - time.time()))
            if not confirmed:
                ok_all = False; break
            if i < len(parts) - 1:
                time.sleep(human_delay(1.0, 2.5))

        self._close_tab()
        return ok_all

    # ───────────────────────────────────────
    #  TOP-LEVEL SEND (retry wrapper)
    # ───────────────────────────────────────
    def send_message(self, number, raw_msg):
        if self.dry_var.get():
            time.sleep(random.uniform(1.5, 3.0))
            return True

        retries = self.v_retries.get()
        vary    = self.v_vary.get()
        single  = self.single_send_var.get()

        for attempt in range(1, retries + 1):
            if not self.running: return False
            if attempt > 1:
                self._log("warn", f"  Retry {attempt}/{retries} → {number}")
                time.sleep(human_delay(3, 7))

            msg = vary_msg(raw_msg) if vary else raw_msg

            try:
                if single:
                    ok = self._send_single(number, msg)
                else:
                    ok = self._send_paragraphs(number, msg)
            except pyautogui.FailSafeException:
                self._log("warn", "Emergency stop triggered (mouse moved to corner).")
                self.stop()
                return False
            except Exception as ex:
                self._log("warn", f"  Exception: {ex}")
                ok = False

            if ok:
                return True

        return False

    # ───────────────────────────────────────
    #  ACTIONS
    # ───────────────────────────────────────
    def import_list(self):
        path = filedialog.askopenfilename(
            title="Select number list (.txt)",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path: return
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except Exception as e:
            messagebox.showerror("Error", str(e)); return

        clean, seen, bad = [], set(), 0
        for ln in lines:
            n = clean_number(ln)
            if n and n not in seen:
                seen.add(n); clean.append(n)
            else:
                bad += 1

        self.numbers = clean; self.total = len(clean)
        self.current_idx = self.sent_count = self.skipped_count = 0
        self.failed_list = []
        self._update_stats()
        self._log("info", f"Imported {self.total} numbers  ({bad} invalid/dup skipped).")
        messagebox.showinfo("Imported",
            f"✅  {self.total} numbers loaded.\n⚠  {bad} lines skipped.")

    def start(self):
        if not self.numbers:
            messagebox.showwarning("No list", "Import a number list first."); return
        if self.current_idx >= self.total:
            messagebox.showinfo("Done", "All processed. Re-import to restart."); return
        lim = self.v_dlimit.get()
        if self.logger.sent_today() >= lim:
            messagebox.showwarning("Limit",
                f"Daily limit of {lim} reached.\nChange in Settings or wait tomorrow."); return

        self.running    = True
        self.paused     = False
        self.start_time = time.time()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ PAUSE")
        self._set_status("● Running…")
        self._log("info", f"Session started — {self.total - self.current_idx} numbers remaining.")
        if self.dry_var.get():
            self._log("warn", "⚠  DRY RUN — no real messages sent.")
        if self.v_bg.get():
            self._minimize()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def toggle_pause(self):
        if not self.running: return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RESUME")
            self._set_status(f"● Paused at {self.current_idx}/{self.total}")
            self._log("warn", "Paused.")
        else:
            self.btn_pause.config(text="⏸ PAUSE")
            self._set_status("● Running…")
            self._log("info", "Resumed.")

    def stop(self):
        self.running = False; self.paused = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))
        self._set_status(f"● Stopped at {self.current_idx}/{self.total}")
        self._log("warn", "Stopped by user.")
        if self.v_bg.get(): self._restore()

    def test_single(self):
        val = simpledialog.askstring("Test",
            "Enter a number to test (10 or 12 digits):")
        if not val: return
        n = clean_number(val)
        if not n:
            messagebox.showwarning("Invalid", "Enter a valid 10 or 12-digit number."); return
        raw = self.msg_box.get("1.0", tk.END).strip()
        self._log("info", f"Test send → {n}")
        def _t():
            ok = self.send_message(n, raw)
            res = "✅ Test sent!" if ok else "❌ Test FAILED"
            self._log("sent" if ok else "failed", res)
            self.root.after(0, lambda: messagebox.showinfo("Test", res))
        threading.Thread(target=_t, daemon=True).start()

    def retry_failed(self):
        if not self.failed_list:
            messagebox.showinfo("Empty", "No failed numbers to retry."); return
        self.numbers = list(self.failed_list)
        self.total = len(self.numbers)
        self.current_idx = self.sent_count = self.skipped_count = 0
        self.failed_list = []
        self._update_stats()
        messagebox.showinfo("Retry", f"Loaded {self.total} failed numbers.")

    def export_failed(self):
        if not self.failed_list:
            messagebox.showinfo("Empty", "No failed numbers."); return
        p = filedialog.asksaveasfilename(defaultextension=".txt",
            filetypes=[("Text", "*.txt")], initialfile="failed.txt")
        if not p: return
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(self.failed_list))
        messagebox.showinfo("Exported", f"Saved {len(self.failed_list)} numbers.")

    def add_blacklist(self):
        val = simpledialog.askstring("Blacklist",
            "Enter number to blacklist\n(or leave blank to blacklist all failed):")
        if val:
            n = clean_number(val)
            if n: self.blacklist.add(n); messagebox.showinfo("Done", f"{n} blacklisted.")
            else: messagebox.showwarning("Invalid", "Not a valid number.")
        elif self.failed_list:
            for n in self.failed_list: self.blacklist.add(n)
            messagebox.showinfo("Done", f"{len(self.failed_list)} numbers blacklisted.")

    def clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")
        self._log("info", "Log cleared.")

    # ───────────────────────────────────────
    #  MAIN SEND LOOP
    # ───────────────────────────────────────
    def _run_loop(self):
        raw      = self.msg_box.get("1.0", tk.END).strip()
        sent_set = self.logger.sent_numbers()
        lim      = self.v_dlimit.get()

        while self.current_idx < self.total and self.running:
            if self.paused: time.sleep(0.3); continue

            if self.logger.sent_today() >= lim:
                self._log("warn", f"Daily limit {lim} reached. Stopping.")
                self.root.after(0, lambda: messagebox.showwarning(
                    "Daily Limit", f"Reached daily limit of {lim}."))
                break

            number = self.numbers[self.current_idx]
            idx    = self.current_idx + 1

            # Skip checks
            if self.v_skip_sent.get() and number in sent_set:
                self._log("skip", f"↷ Already sent: {number}")
                self.skipped_count += 1; self.current_idx += 1
                self._update_stats(); continue

            if self.v_skip_bl.get() and self.blacklist.has(number):
                self._log("skip", f"↷ Blacklisted: {number}")
                self.skipped_count += 1; self.current_idx += 1
                self._update_stats(); continue

            # Send
            self._log("info", f"► {idx}/{self.total}  {number}")
            self._set_status(f"● Sending {idx}/{self.total} → {number}")

            ok = self.send_message(number, raw)

            self.current_idx += 1
            if ok:
                self.sent_count += 1; sent_set.add(number)
                self.logger.log_sent(number)
                self._log("sent", f"✅ Sent → {number}")
            else:
                self.failed_list.append(number)
                self.logger.log_failed(number)
                self._log("failed", f"❌ Failed → {number}")

            self._update_stats()

            # ── inter-message delay ──
            if self.current_idx < self.total and self.running:
                delay   = human_delay(self.v_dmin.get(), self.v_dmax.get())
                elapsed = 0.0
                self._log("info", f"  Waiting {delay:.0f}s before next…")
                while elapsed < delay and self.running:
                    while self.paused: time.sleep(0.3)
                    rem = int(delay - elapsed)
                    self._set_status(f"● Next message in {rem}s …")
                    time.sleep(0.5); elapsed += 0.5

        # ── done ──
        self.running = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))

        if self.v_bg.get():
            self._restore()

        if self.current_idx >= self.total:
            self._log("info", "🎉 All done!")
            self._set_status("● All Done! 🎉")
            dry_note = "\n(DRY RUN — nothing actually sent)" if self.dry_var.get() else ""
            summary  = (f"✅ Sent:    {self.sent_count}\n"
                        f"❌ Failed:  {len(self.failed_list)}\n"
                        f"↷ Skipped: {self.skipped_count}{dry_note}")
            self.root.after(0, lambda: messagebox.showinfo("Done!", summary))
            if self.v_sound.get():
                try: self.root.bell()
                except Exception: pass
        else:
            self._set_status(f"● Stopped at {self.current_idx}/{self.total}")


# ═══════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = OutreachTool(root)
    root.mainloop()

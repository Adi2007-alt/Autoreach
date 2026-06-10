# -*- coding: utf-8 -*-
"""
AutoReach v12.0 — WhatsApp Web Outreach Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIXED IN v12 (all root causes of "browser not opening" / "unknown error"):
  ✅ os.startfile() used on Windows — webbrowser.open() is unreliable
  ✅ _wait_for_browser now NEVER fails the session — proceeds even on timeout
  ✅ _wait_page_ready: smarter title check + longer poll interval
  ✅ conn_delay sleep happens BEFORE window search (sequential, not parallel)
  ✅ Browser keywords expanded to catch all Chrome/Edge window titles
  ✅ Anti-ban defaults: 45–90s delay, 30/day, vary ON, 5s postsend
  ✅ Diagnostic mode logs every sub-step — easy to find new failures
  ✅ All exceptions caught with full traceback in log
  ✅ Settings persist across restarts
  ✅ Reset Settings button
  ✅ Enter sent via keyboard — zero mouse movement for sending

Install:  pip install pyautogui pyperclip pygetwindow
Run:      python autoreach_v12.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import webbrowser, threading, time, random, os, json, queue, sys, traceback
import subprocess
import re
import pyautogui, pyperclip
from datetime import datetime, timedelta

try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    gw = None
    HAS_GW = False

VERSION        = "12.0"
LOG_FILE       = "autoreach_log.json"
BLACKLIST_FILE = "blacklist.txt"
CALIB_FILE     = "calibration.json"
SETTINGS_FILE  = "autoreach_settings.json"

BG     = "#0D1117"; CARD  = "#161B22"; CARD2  = "#1C2128"
ACCENT = "#2F81F7"; TEXT  = "#E6EDF3"; MUTED  = "#8B949E"
GREEN  = "#3FB950"; RED   = "#F85149"; AMBER  = "#D29922"
BLUE   = "#79C0FF"; PURPLE= "#BC8CFF"; BORDER = "#30363D"

# WhatsApp Web signals page is invalid / number not found
_INVALID_KEYS = [
    "invalid phone number",
    "not on whatsapp",
    "phone number shared via url is invalid",
    "link you opened is invalid",
]

_INVISIBLE  = ["\u200b", "\u200c", "\u200d", "\u2060"]

# All window-title fragments that could be a browser showing WA Web
_BROWSER_KW = (
    "whatsapp",
    "google chrome",
    "chrome",
    "microsoft edge",
    "msedge",
    "edge",
    "firefox",
    "brave",
    "opera",
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.02

# ── Anti-ban safe defaults ──────────────────────────────
DEFAULTS = {
    "dmin":        45,    # min 45s between messages
    "dmax":        90,    # max 90s — human-like randomness
    "conn_delay":  6,     # wait 6s after URL opens (browser launch time)
    "load":        20,    # wait up to 20s for WA page to load
    "postsend":    5,     # 5s after send before closing tab
    "timeout":     80,    # hard timeout per number
    "dlimit":      30,    # 30 messages/day — safe limit
    "retries":     1,     # 1 retry only — repeated attempts raise flags
    "skip_sent":   True,
    "skip_bl":     True,
    "vary":        True,  # KEEP ON — critical anti-spam
    "sound":       True,
    "hide_browser":False,
    "single_msg":  True,
    "stop_on_fail":False,
    "diagnostic":  False,
}


# ═══════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════

def gauss(mn, mx):
    return max(mn, min(mx, random.gauss((mn + mx) / 2, (mx - mn) / 4)))

def vary_msg(text):
    """Insert invisible char to make each message unique hash."""
    w = text.split(" ")
    if len(w) < 4:
        return text
    w[random.randint(1, len(w) - 2)] += random.choice(_INVISIBLE)
    return " ".join(w)

def to_e164(s):
    """Normalise to 12-digit Indian E.164. Returns None if unrecognised."""
    d = "".join(filter(str.isdigit, s))
    # strip leading 0 from 091...
    if len(d) == 12 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    return d if len(d) == 12 else None

def fmt_time(s):
    return str(timedelta(seconds=int(max(0, s))))

def open_url(url):
    """
    Open a URL in the default or a detected browser.
    First tries to find and launch Chrome, Edge, Brave, or Firefox via subprocess.Popen (most robust).
    Falls back to os.startfile on Windows / open on macOS / xdg-open on Linux,
    and finally to webbrowser.open.
    """
    if sys.platform == "win32":
        # Search paths for Chrome, Edge, Brave, Firefox
        browsers = [
            # Chrome
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("LocalAppData", "C:\\Users\\adity\\AppData\\Local"), "Google\\Chrome\\Application\\chrome.exe"),
            # Edge
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Microsoft\\Edge\\Application\\msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Microsoft\\Edge\\Application\\msedge.exe"),
            # Brave
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            os.path.join(os.environ.get("LocalAppData", "C:\\Users\\adity\\AppData\\Local"), "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            # Firefox
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Mozilla Firefox\\firefox.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Mozilla Firefox\\firefox.exe"),
        ]
        
        for path in browsers:
            if path and os.path.exists(path):
                try:
                    subprocess.Popen([path, url])
                    return
                except Exception:
                    pass

    try:
        if sys.platform == "win32":
            os.startfile(url)
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", url])
            return
        subprocess.Popen(["xdg-open", url])
    except Exception:
        try:
            webbrowser.open(url)
        except Exception:
            pass

def play_sound():
    try:
        if sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif sys.platform == "darwin":
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
        else:
            os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || true")
    except Exception:
        pass

def read_clip(retries=4):
    for _ in range(retries):
        try:
            return pyperclip.paste() or ""
        except Exception:
            time.sleep(0.05)
    return ""

def write_clip(text, retries=4):
    for _ in range(retries):
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            time.sleep(0.05)
    return False


# ═══════════════════════════════════════════
#  LOGGER
# ═══════════════════════════════════════════

class Logger:
    def __init__(self):
        self.data = {"sent": [], "failed": []}
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, encoding="utf-8") as f:
                    d = json.load(f)
                self.data["sent"]   = d.get("sent", [])
                self.data["failed"] = d.get("failed", [])
            except Exception:
                pass

    def _save(self):
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def mark_sent(self, n):
        self.data["sent"].append(
            {"n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self._save()

    def mark_failed(self, n, reason=""):
        self.data["failed"].append(
            {"n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "reason": reason})
        self._save()

    def sent_set(self):
        return {e["n"] for e in self.data["sent"]}

    def sent_today(self):
        d = datetime.now().strftime("%Y-%m-%d")
        return sum(1 for e in self.data["sent"] if e["t"].startswith(d))

    def total_sent(self):
        return len(self.data["sent"])

    def clear_all(self):
        self.data = {"sent": [], "failed": []}
        self._save()


# ═══════════════════════════════════════════
#  BLACKLIST
# ═══════════════════════════════════════════

class Blacklist:
    def __init__(self):
        self.nums = set()
        if os.path.exists(BLACKLIST_FILE):
            try:
                with open(BLACKLIST_FILE, encoding="utf-8") as f:
                    self.nums = {l.strip() for l in f if l.strip()}
            except Exception:
                pass

    def add(self, n):
        if n not in self.nums:
            self.nums.add(n)
            try:
                with open(BLACKLIST_FILE, "a", encoding="utf-8") as f:
                    f.write(n + "\n")
            except Exception:
                pass

    def has(self, n):
        return n in self.nums

    def count(self):
        return len(self.nums)


# ═══════════════════════════════════════════
#  CALIBRATION
# ═══════════════════════════════════════════

class Calib:
    def __init__(self):
        self.x = self.y = None
        if os.path.exists(CALIB_FILE):
            try:
                d = json.load(open(CALIB_FILE))
                self.x, self.y = d.get("x"), d.get("y")
            except Exception:
                pass

    def save(self, x, y):
        self.x, self.y = x, y
        try:
            json.dump({"x": x, "y": y}, open(CALIB_FILE, "w"))
        except Exception:
            pass

    def get(self):
        if self.x and self.y:
            return self.x, self.y
        sw, sh = pyautogui.size()
        return int(sw * 0.50), int(sh * 0.935)

    def is_set(self):
        return self.x is not None


# ═══════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════

def load_settings():
    d = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            saved = json.load(open(SETTINGS_FILE))
            d.update({k: v for k, v in saved.items() if k in d})
        except Exception:
            pass
    return d

def save_settings(d):
    m = dict(DEFAULTS)
    m.update({k: v for k, v in d.items() if k in DEFAULTS})
    try:
        json.dump(m, open(SETTINGS_FILE, "w"), indent=2)
    except Exception:
        pass


# ═══════════════════════════════════════════
#  BROWSER MANAGER — never raises, always safe
# ═══════════════════════════════════════════

class BrowserMgr:

    def _all_wins(self):
        if not HAS_GW:
            return []
        try:
            return list(gw.getAllWindows())
        except Exception:
            return []

    def _wa_wins(self):
        out = []
        for w in self._all_wins():
            t = getattr(w, "title", "").lower().replace("\u200b", " ")
            if "whatsapp" in t:
                out.append(w)
                continue
            # Check other browsers with word boundaries to avoid false positives like Notepad
            browsers = ["chrome", "msedge", "firefox", "brave", "opera"]
            if any(re.search(r"\b" + re.escape(b) + r"\b", t) for b in browsers):
                out.append(w)
            elif "microsoft edge" in t:
                out.append(w)
        # Prioritize windows that have "whatsapp" in their title
        out.sort(key=lambda w: "whatsapp" not in getattr(w, "title", "").lower())
        return out

    def wait_for_window(self, max_sec=12.0):
        """
        Poll until a browser window appears after open_url().
        NEVER returns False — always proceeds (some systems hide windows).
        """
        if not HAS_GW:
            return True          # can't check — assume browser opened
        deadline = time.time() + max_sec
        while time.time() < deadline:
            if self._wa_wins():
                return True
            time.sleep(0.4)
        return True              # proceed anyway — don't abort on timeout

    def activate(self):
        if not HAS_GW:
            return True
        for w in self._wa_wins():
            try:
                w.restore()
                time.sleep(0.08)
                w.activate()
                time.sleep(0.14)
                return True
            except Exception:
                pass
        return False

    def hide(self):
        for w in self._wa_wins():
            try:
                w.minimize()
            except Exception:
                pass

    def title(self):
        wins = self._wa_wins()
        return getattr(wins[0], "title", "").lower() if wins else ""

    def close_tab(self, hide_after=False):
        """Close current browser tab. Fully guarded — never raises."""
        try:
            self.activate()
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.5)
        except Exception:
            pass
        try:
            if hide_after:
                time.sleep(0.15)
                self.hide()
        except Exception:
            pass


# ═══════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════

class AutoReach:

    def __init__(self, root):
        self.root = root
        self.root.title(f"AutoReach v{VERSION}")
        self.root.geometry("900x1020")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(800, 860)

        self.numbers = []; self.current_idx = 0; self.total = 0
        self.sent_count = 0; self.failed_list = []; self.skipped_count = 0
        self.running = False; self.paused = False; self.start_time = None
        self._ui_q = queue.Queue(); self._dot = 0

        self.logger    = Logger()
        self.blacklist = Blacklist()
        self.calib     = Calib()
        self.browser   = BrowserMgr()
        self._cfg      = load_settings()

        self._style(); self._build()
        self._apply_cfg(); self._refresh_daily()
        self._poll_ui(); self._anim_header()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Style ───────────────────────────────
    def _style(self):
        s = ttk.Style(); s.theme_use("clam")
        s.configure("TButton", background=CARD2, foreground=TEXT,
                    font=("Segoe UI", 9, "bold"), borderwidth=1,
                    relief="flat", padding=7)
        s.map("TButton",
              background=[("active", "#2a5faa"), ("disabled", CARD)],
              foreground=[("disabled", MUTED)])
        s.configure("A.TButton", background=ACCENT, foreground="#fff",
                    font=("Segoe UI", 10, "bold"), padding=9)
        s.map("A.TButton", background=[("active", "#1a5fcc")])
        s.configure("D.TButton", background="#3a1010", foreground=RED,
                    font=("Segoe UI", 9, "bold"), padding=7)
        s.map("D.TButton", background=[("active", "#5a1515")])
        s.configure("W.TButton", background="#3a2a00", foreground=AMBER,
                    font=("Segoe UI", 9, "bold"), padding=7)
        s.map("W.TButton", background=[("active", "#5a4000")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD2, foreground=MUTED,
                    font=("Segoe UI", 9, "bold"), padding=[18, 7])
        s.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#fff")])
        s.configure("Horizontal.TProgressbar",
                    troughcolor=CARD2, background=ACCENT,
                    borderwidth=0, thickness=8)
        s.configure("TSpinbox", background=CARD2, foreground=TEXT,
                    fieldbackground=CARD2, bordercolor=BORDER)

    # ── Build ───────────────────────────────
    def _build(self):
        hdr = tk.Frame(self.root, bg="#080D13", height=64)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text=f"⚡ AutoReach v{VERSION}",
                 fg=ACCENT, bg="#080D13",
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=20, pady=12)
        tk.Label(hdr, text="WhatsApp Web Automation",
                 fg=MUTED, bg="#080D13",
                 font=("Segoe UI", 9)).pack(side="left", pady=20)
        self.lbl_hdr = tk.Label(hdr, text="● IDLE", fg=AMBER, bg="#080D13",
                                font=("Segoe UI", 9, "bold"))
        self.lbl_hdr.pack(side="right", padx=20)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=8)
        self._tabs = {}
        for name in ("Send", "Log", "Settings", "Calibrate", "Help"):
            f = tk.Frame(nb, bg=BG)
            nb.add(f, text=f"  {name}  ")
            self._tabs[name] = f

        self._tab_send(self._tabs["Send"])
        self._tab_log(self._tabs["Log"])
        self._tab_settings(self._tabs["Settings"])
        self._tab_calibrate(self._tabs["Calibrate"])
        self._tab_help(self._tabs["Help"])

    # ════════════════════════════════════════
    #  SEND TAB
    # ════════════════════════════════════════
    def _tab_send(self, T):
        top = tk.Frame(T, bg=BG); top.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(top, text="✉  Message Template", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        self.v_single = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="📋 One message (keep formatting)",
                       variable=self.v_single, bg=BG, fg=BLUE,
                       selectcolor=CARD2, activebackground=BG,
                       font=("Segoe UI", 9, "bold"),
                       command=self._mode_hint).pack(side="right")

        self.lbl_mode = tk.Label(T,
            text="▸ Entire message sent in one go — formatting preserved",
            bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_mode.pack(anchor="e", padx=14)

        mf = tk.Frame(T, bg=BORDER, bd=1); mf.pack(padx=14, pady=4, fill="x")
        sc = tk.Scrollbar(mf, bg=CARD2); sc.pack(side="right", fill="y")
        self.msg_box = tk.Text(mf, height=9, bg=CARD, fg=TEXT,
                               insertbackground=TEXT, font=("Consolas", 9),
                               relief="flat", padx=10, pady=8, undo=True,
                               wrap="word", yscrollcommand=sc.set)
        self.msg_box.pack(fill="both"); sc.config(command=self.msg_box.yview)
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
            "Feel free to join and share it with other ambassadors you know 🚀")
        self.msg_box.bind("<KeyRelease>", self._char_count)

        cr = tk.Frame(T, bg=BG); cr.pack(fill="x", padx=14)
        self.lbl_chars = tk.Label(cr, text="", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 8))
        self.lbl_chars.pack(side="right")
        self._char_count()

        # Stats bar
        sf = tk.Frame(T, bg=CARD2, pady=8); sf.pack(fill="x", padx=14, pady=(6, 3))
        self._sl = {}
        for i, (nm, val, col) in enumerate([
            ("Loaded", "0", TEXT), ("Sent", "0", GREEN),
            ("Failed", "0", RED),  ("Skipped", "0", AMBER),
            ("ETA", "--:--", BLUE)
        ]):
            cf = tk.Frame(sf, bg=CARD2); cf.grid(row=0, column=i, padx=14, pady=2)
            tk.Label(cf, text=nm, bg=CARD2, fg=MUTED,
                     font=("Segoe UI", 7, "bold")).pack()
            lbl = tk.Label(cf, text=val, bg=CARD2, fg=col,
                           font=("Segoe UI", 13, "bold")); lbl.pack()
            self._sl[nm] = lbl
        for i in range(5): sf.columnconfigure(i, weight=1)

        self.v_prog = tk.DoubleVar(value=0)
        ttk.Progressbar(T, variable=self.v_prog, maximum=100).pack(
            fill="x", padx=14, pady=3)
        self.lbl_prog = tk.Label(T, text="", bg=BG, fg=MUTED,
                                 font=("Segoe UI", 8))
        self.lbl_prog.pack()

        self.lbl_status = tk.Label(T,
            text="● Idle — Import a number list to begin",
            bg=BG, fg=AMBER, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(pady=2)

        dl = tk.Frame(T, bg=BG); dl.pack()
        self.lbl_daily    = tk.Label(dl, text="Today: 0/30",  bg=BG, fg=GREEN, font=("Segoe UI", 9))
        self.lbl_alltime  = tk.Label(dl, text="All-time: 0",  bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_bl_count = tk.Label(dl, text="Blacklist: 0", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        for l in (self.lbl_daily, self.lbl_alltime, self.lbl_bl_count):
            l.pack(side="left", padx=6)

        self.v_dry = tk.BooleanVar(value=False)
        tk.Checkbutton(T, text="🧪 Dry-Run (simulate — nothing sent)",
                       variable=self.v_dry, bg=BG, fg=BLUE,
                       selectcolor=CARD2, activebackground=BG,
                       font=("Segoe UI", 9)).pack(pady=2)

        bf = tk.Frame(T, bg=BG); bf.pack(pady=5, padx=14, fill="x")
        self.btn_import = ttk.Button(bf, text="📁 Import List",   command=self.do_import)
        self.btn_reset  = ttk.Button(bf, text="🔄 Reset List",    command=self.do_reset)
        self.btn_start  = ttk.Button(bf, text="▶  START",         command=self.do_start,  style="A.TButton")
        self.btn_pause  = ttk.Button(bf, text="⏸ PAUSE",          command=self.do_pause,  state="disabled")
        self.btn_stop   = ttk.Button(bf, text="⏹ STOP",           command=self.do_stop,   style="D.TButton")
        self.btn_test   = ttk.Button(bf, text="🔬 Test 1 Number", command=self.do_test)
        self.btn_retry  = ttk.Button(bf, text="🔁 Retry Failed",  command=self.do_retry)
        self.btn_export = ttk.Button(bf, text="💾 Export Failed", command=self.do_export)
        self.btn_bl     = ttk.Button(bf, text="🔕 Blacklist",     command=self.do_blacklist)
        self.btn_vf     = ttk.Button(bf, text="📋 View Failed",   command=self.do_view_failed)

        for r, c, b in [
            (0,0,self.btn_import),(0,1,self.btn_reset),(0,2,self.btn_start),
            (0,3,self.btn_pause),(0,4,self.btn_stop),
            (1,0,self.btn_test),(1,1,self.btn_retry),(1,2,self.btn_export),
            (1,3,self.btn_bl),(1,4,self.btn_vf),
        ]:
            b.grid(row=r, column=c, padx=4, pady=3, sticky="ew")
        for c in range(5): bf.columnconfigure(c, weight=1)

        tk.Label(T, text="⚠  Keep WhatsApp Web open in Chrome/Edge  ·  "
                         "Move mouse to TOP-LEFT corner to emergency-stop",
                 bg=BG, fg=RED, font=("Segoe UI", 8, "bold")).pack(pady=6)

    # ════════════════════════════════════════
    #  LOG TAB
    # ════════════════════════════════════════
    def _tab_log(self, T):
        hdr = tk.Frame(T, bg=BG); hdr.pack(fill="x", padx=10, pady=8)
        tk.Label(hdr, text="📋  Session Log", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(hdr, text="📋 Copy",    command=self._copy_log).pack(side="right", padx=4)
        ttk.Button(hdr, text="🗑 Clear",   command=self.do_clear_log).pack(side="right", padx=4)
        ttk.Button(hdr, text="📂 Open JSON", command=self._open_log_file).pack(side="right", padx=4)

        fr = tk.Frame(T, bg=BG); fr.pack(fill="both", expand=True, padx=10, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        self.log_box = tk.Text(fr, bg=CARD, fg=MUTED, font=("Consolas", 8),
                               yscrollcommand=sc.set, state="disabled",
                               relief="flat", padx=8, pady=6)
        self.log_box.pack(fill="both", expand=True)
        sc.config(command=self.log_box.yview)
        for t, c in [("info", BLUE), ("sent", GREEN), ("failed", RED),
                     ("skip", AMBER), ("warn", PURPLE), ("system", MUTED),
                     ("header", ACCENT), ("debug", "#4a5568")]:
            self.log_box.tag_config(t, foreground=c)
        self._log("system", f"AutoReach v{VERSION} ready  |  Python {sys.version.split()[0]}")
        self._log("system", f"All-time sent: {self.logger.total_sent()}  |  Blacklist: {self.blacklist.count()}")
        if not HAS_GW:
            self._log("warn", "pygetwindow not installed — browser hide disabled. Run: pip install pygetwindow")

    # ════════════════════════════════════════
    #  SETTINGS TAB
    # ════════════════════════════════════════
    def _tab_settings(self, T):
        canvas = tk.Canvas(T, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(T, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        fr = tk.Frame(canvas, bg=BG)
        fid = canvas.create_window((0, 0), window=fr, anchor="nw")
        def _resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(fid, width=e.width)
        canvas.bind("<Configure>", _resize)
        fr.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        row = [0]

        def section(title):
            tk.Label(fr, text=title, bg=BG, fg=ACCENT,
                     font=("Segoe UI", 10, "bold")).grid(
                row=row[0], column=0, columnspan=3,
                sticky="w", padx=20, pady=(16, 2))
            row[0] += 1
            tk.Frame(fr, bg=BORDER, height=1).grid(
                row=row[0], column=0, columnspan=3,
                sticky="ew", padx=20, pady=(0, 6))
            row[0] += 1

        def spin(label, var, lo, hi, tip=""):
            tk.Label(fr, text=label + (f"  ← {tip}" if tip else ""),
                     bg=BG, fg=TEXT, anchor="w",
                     font=("Segoe UI", 9), width=65).grid(
                row=row[0], column=0, padx=22, pady=5, sticky="w")
            ttk.Spinbox(fr, from_=lo, to=hi, textvariable=var, width=8).grid(
                row=row[0], column=1, padx=8, pady=5, sticky="w")
            row[0] += 1
            var.trace_add("write", lambda *_: self._autosave())

        def note(txt):
            tk.Label(fr, text=txt, bg=BG, fg=MUTED,
                     font=("Segoe UI", 8), justify="left").grid(
                row=row[0], column=0, columnspan=3,
                sticky="w", padx=32, pady=(0, 4))
            row[0] += 1

        def check(label, var, color=TEXT, disabled=False, tip=""):
            full = label + (f"  [{tip}]" if tip else "")
            cb = tk.Checkbutton(fr, text=full, variable=var,
                                bg=BG, fg=color, selectcolor=CARD2,
                                activebackground=BG, font=("Segoe UI", 9),
                                command=self._autosave)
            if disabled:
                cb.config(state="disabled", fg=MUTED)
            cb.grid(row=row[0], column=0, columnspan=3,
                    sticky="w", padx=22, pady=4)
            row[0] += 1

        # Tk vars
        self.v_dmin       = tk.IntVar(); self.v_dmax      = tk.IntVar()
        self.v_conn_delay = tk.IntVar(); self.v_load       = tk.IntVar()
        self.v_postsend   = tk.IntVar(); self.v_timeout    = tk.IntVar()
        self.v_dlimit     = tk.IntVar(); self.v_retries    = tk.IntVar()
        self.v_skip_sent  = tk.BooleanVar(); self.v_skip_bl = tk.BooleanVar()
        self.v_vary       = tk.BooleanVar(); self.v_sound   = tk.BooleanVar()
        self.v_hide_browser = tk.BooleanVar()
        self.v_stop_on_fail = tk.BooleanVar()
        self.v_diagnostic   = tk.BooleanVar()

        section("⏱  Timing & Delays  (anti-ban safe defaults shown)")
        spin("Min delay between messages (s):", self.v_dmin, 5, 600,
             "≥45s recommended")
        spin("Max delay between messages (s):", self.v_dmax, 10, 600)
        spin("Browser launch wait after URL opens (s):", self.v_conn_delay, 2, 30,
             "6s default — increase for slow PC")
        spin("WhatsApp Web page load wait (s):", self.v_load, 5, 120,
             "20s recommended")
        spin("Post-send wait before closing tab (s):", self.v_postsend, 2, 30,
             "5s — let WA register the send")
        spin("Hard timeout per number (s):", self.v_timeout, 20, 300,
             "80s recommended")

        section("📊  Limits & Reliability")
        spin("Daily send limit (messages/day):", self.v_dlimit, 5, 500,
             "≤30 to avoid ban")
        spin("Retry attempts per failed number:", self.v_retries, 1, 5,
             "1 retry — more raises ban flags")
        note("Lower daily limit = safer account. Start with 20/day for new accounts.")

        section("⚙  Behaviour")
        check("Skip already-sent numbers (recommended)", self.v_skip_sent, GREEN)
        check("Skip blacklisted numbers (recommended)", self.v_skip_bl, GREEN)
        check("✅ Vary each message slightly — anti-spam invisible character",
              self.v_vary, BLUE)
        note("Keep 'Vary' ON always — identical messages are flagged by WhatsApp.")
        check("Stop entire session on first failure (strict mode)",
              self.v_stop_on_fail, AMBER)
        check("Play sound when session finishes", self.v_sound)
        check("🔬 Diagnostic mode — log every sub-step (use when troubleshooting)",
              self.v_diagnostic, PURPLE)

        section("🌐  Browser Visibility")
        if HAS_GW:
            check("🙈 Hide browser while sending — runs silently in background",
                  self.v_hide_browser, BLUE)
            note("AutoReach window stays visible. Only Chrome/Edge is minimized.")
        else:
            check("🙈 Hide browser — install pygetwindow to enable",
                  self.v_hide_browser, MUTED, disabled=True)
            note("Run:  pip install pygetwindow   then restart AutoReach.")

        section("🔧  Actions")
        br = tk.Frame(fr, bg=BG)
        br.grid(row=row[0], column=0, columnspan=3,
                sticky="w", padx=20, pady=8)
        row[0] += 1
        ttk.Button(br, text="💾 Save Settings",
                   command=self._autosave, style="A.TButton").pack(side="left", padx=6)
        ttk.Button(br, text="🔁 Reset to Defaults",
                   command=self._reset_settings, style="W.TButton").pack(side="left", padx=6)
        ttk.Button(br, text="🗑 Clear All History",
                   command=self._clear_history).pack(side="left", padx=6)
        self.lbl_save = tk.Label(fr, text="", bg=BG, fg=GREEN,
                                 font=("Segoe UI", 8))
        self.lbl_save.grid(row=row[0], column=0, columnspan=3,
                           sticky="w", padx=22, pady=(0, 4))
        row[0] += 1
        note("Settings auto-save whenever you change any value.")

    # ════════════════════════════════════════
    #  CALIBRATE TAB
    # ════════════════════════════════════════
    def _tab_calibrate(self, T):
        tk.Label(T, text="🎯  Click-Target Calibration",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=14)
        info = tk.Frame(T, bg=CARD); info.pack(padx=20, fill="x")
        tk.Label(info, text=(
            "AutoReach clicks the WhatsApp Web message input box ONCE to focus it,\n"
            "then does everything else by keyboard (no more mouse needed for sending).\n\n"
            "ONE-TIME SETUP:\n"
            "  1. Open WhatsApp Web in Chrome/Edge and open any existing chat.\n"
            "  2. Click  '🎯 Start 3s Countdown'  below.\n"
            "  3. Within 3 seconds, hover your mouse over the message\n"
            "     input box at the BOTTOM of WhatsApp Web.\n"
            "  4. Stay still — position saves automatically.\n\n"
            "Redo this whenever you move or resize the browser window."
        ), bg=CARD, fg=TEXT, font=("Segoe UI", 9),
        justify="left", wraplength=720, padx=18, pady=14).pack(fill="x")

        self.lbl_calib = tk.Label(T, bg=BG, fg=GREEN,
                                  font=("Segoe UI", 10, "bold"))
        self.lbl_calib.pack(pady=8); self._calib_refresh()
        self.lbl_cdown = tk.Label(T, text="", bg=BG, fg=AMBER,
                                  font=("Segoe UI", 42, "bold"))
        self.lbl_cdown.pack(pady=4)
        self.lbl_mouse = tk.Label(T, text="Mouse: — , —", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 9))
        self.lbl_mouse.pack(); self._track_mouse()

        bf = tk.Frame(T, bg=BG); bf.pack(pady=12)
        ttk.Button(bf, text="🎯  Start 3s Countdown",
                   command=self._calib_start,
                   style="A.TButton").pack(side="left", padx=8)
        ttk.Button(bf, text="🔄  Reset to Default",
                   command=self._calib_reset).pack(side="left", padx=8)

    # ════════════════════════════════════════
    #  HELP TAB
    # ════════════════════════════════════════
    def _tab_help(self, T):
        canvas = tk.Canvas(T, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(T, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y"); canvas.pack(fill="both", expand=True)
        fr = tk.Frame(canvas, bg=BG)
        fid = canvas.create_window((0, 0), window=fr, anchor="nw")
        canvas.bind("<Configure>", lambda e: (
            canvas.configure(scrollregion=canvas.bbox("all")),
            canvas.itemconfig(fid, width=e.width)))
        fr.bind("<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def H(txt):
            tk.Label(fr, text=txt, bg=BG, fg=ACCENT,
                     font=("Segoe UI", 10, "bold")).pack(
                anchor="w", padx=20, pady=(14, 2))
            tk.Frame(fr, bg=BORDER, height=1).pack(
                fill="x", padx=20, pady=(0, 4))

        def P(txt):
            tk.Label(fr, text=txt, bg=BG, fg=TEXT,
                     font=("Segoe UI", 9), justify="left",
                     wraplength=820).pack(anchor="w", padx=28, pady=2)

        tk.Label(fr, text=f"⚡ AutoReach v{VERSION} — Help & Troubleshooting",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=(18, 6))

        H("🚀  Quick Start (do these steps in order)")
        P("1. pip install pyautogui pyperclip pygetwindow")
        P("2. Open WhatsApp Web in Chrome or Edge — log in completely.")
        P("3. Go to Calibrate tab → click '🎯 Start 3s Countdown' → hover over the WA message box.")
        P("4. Go to Send tab → Import List → click ▶ START.")
        P("5. Keep WhatsApp Web open in the browser throughout the session.")

        H("❌  Browser not opening / 'unknown error'")
        P("• Make sure Chrome or Edge is your DEFAULT browser.")
        P("  (Windows: Settings → Default Apps → Web Browser → Chrome/Edge)")
        P("• Increase 'Browser launch wait' in Settings to 8–10s.")
        P("• Increase 'WA page load wait' to 25s if your internet is slow.")
        P("• Turn ON Diagnostic mode in Settings → check Log tab for exact step failure.")
        P("• Try the '🔬 Test 1 Number' button before a full session.")
        P("• If still failing: open Chrome manually, go to web.whatsapp.com, log in, then run.")

        H("🔒  Anti-Ban Rules")
        P("• Keep daily limit ≤ 30 messages. New accounts: start with 10–15/day.")
        P("• Min delay ≥ 45s, Max delay ≥ 90s. Never go below 30s.")
        P("• Always keep 'Vary message' ON — identical messages get flagged fast.")
        P("• Do NOT send to numbers that never heard of you — only to opted-in contacts.")
        P("• Take a day off every few days. Continuous daily sending raises risk.")
        P("• If WhatsApp shows a warning, stop immediately for 2–3 days.")

        H("🎯  Calibration tips")
        P("• Calibrate with the browser at the EXACT size and position you use for sending.")
        P("• The input box is the text field at the very bottom of WhatsApp Web.")
        P("• The live Mouse position display helps you aim accurately.")
        P("• If messages paste in the wrong place, redo calibration.")

        H("📋  What each setting does")
        P("Min/Max delay — Random wait between messages. Higher = safer, slower.")
        P("Browser launch wait — How long to wait for Chrome/Edge to open after URL fires.")
        P("WA page load wait — How long to wait for WhatsApp Web to fully render.")
        P("Post-send wait — Time after sending before closing the tab (WA needs this).")
        P("Hard timeout — If one number takes longer than this, skip it automatically.")
        P("Daily limit — Maximum messages per day across all sessions.")
        P("Vary message — Adds invisible character so each message has a unique hash.")
        P("Diagnostic mode — Logs every internal action. Use when something fails.")

        H("🔢  Accepted phone number formats")
        P("9876543210  (10-digit Indian — auto-gets +91 prefix)")
        P("919876543210  (12-digit with country code)")
        P("+919876543210  (with + sign — also accepted)")
        P("Numbers in .txt or .csv files — one per line (CSV reads first column).")

    # ── Settings helpers ─────────────────────
    def _apply_cfg(self):
        c = self._cfg
        self.v_dmin.set(c["dmin"]); self.v_dmax.set(c["dmax"])
        self.v_conn_delay.set(c["conn_delay"]); self.v_load.set(c["load"])
        self.v_postsend.set(c["postsend"]); self.v_timeout.set(c["timeout"])
        self.v_dlimit.set(c["dlimit"]); self.v_retries.set(c["retries"])
        self.v_skip_sent.set(c["skip_sent"]); self.v_skip_bl.set(c["skip_bl"])
        self.v_vary.set(c["vary"]); self.v_sound.set(c["sound"])
        self.v_hide_browser.set(c["hide_browser"])
        self.v_stop_on_fail.set(c["stop_on_fail"])
        self.v_diagnostic.set(c["diagnostic"])
        self.v_single.set(c["single_msg"])

    def _cur_cfg(self):
        return {
            "dmin":         self.v_dmin.get(),
            "dmax":         self.v_dmax.get(),
            "conn_delay":   self.v_conn_delay.get(),
            "load":         self.v_load.get(),
            "postsend":     self.v_postsend.get(),
            "timeout":      self.v_timeout.get(),
            "dlimit":       self.v_dlimit.get(),
            "retries":      self.v_retries.get(),
            "skip_sent":    self.v_skip_sent.get(),
            "skip_bl":      self.v_skip_bl.get(),
            "vary":         self.v_vary.get(),
            "sound":        self.v_sound.get(),
            "hide_browser": self.v_hide_browser.get(),
            "stop_on_fail": self.v_stop_on_fail.get(),
            "diagnostic":   self.v_diagnostic.get(),
            "single_msg":   self.v_single.get(),
        }

    def _autosave(self, *_):
        try:
            c = self._cur_cfg(); save_settings(c); self._cfg = c
            self.lbl_save.config(
                text=f"✅ Saved  {datetime.now().strftime('%H:%M:%S')}",
                fg=GREEN)
        except Exception as e:
            self.lbl_save.config(text=f"⚠ {e}", fg=RED)

    def _reset_settings(self):
        if not messagebox.askyesno("Reset Settings",
            "Reset all settings to safe defaults?\n\n"
            "List, log, and blacklist are NOT affected."):
            return
        self._cfg = dict(DEFAULTS); self._apply_cfg()
        save_settings(self._cfg)
        self.lbl_save.config(text="🔁 Reset to defaults.", fg=AMBER)
        self._log("warn", "Settings reset to factory defaults.")

    def _clear_history(self):
        if messagebox.askyesno("Clear History",
            "Delete all sent/failed history from the log file?"):
            self.logger.clear_all()
            self._log("warn", "History cleared.")
            self._refresh_daily()

    # ── Calibrate helpers ────────────────────
    def _calib_refresh(self):
        cx, cy = self.calib.get()
        src = "✅ Calibrated" if self.calib.is_set() \
              else "⚠ Default estimate — calibrate for accuracy"
        self.lbl_calib.config(
            text=f"Target →  X: {cx}   Y: {cy}   [ {src} ]",
            fg=GREEN if self.calib.is_set() else AMBER)

    def _calib_start(self):
        def _r():
            for i in (3, 2, 1):
                self._ui_q.put(("cdown", str(i))); time.sleep(1)
            x, y = pyautogui.position()
            self.calib.save(x, y)
            self._ui_q.put(("cdown", "✅ Saved!"))
            self.root.after(0, self._calib_refresh)
            time.sleep(1.8); self._ui_q.put(("cdown", ""))
        threading.Thread(target=_r, daemon=True).start()

    def _calib_reset(self):
        if os.path.exists(CALIB_FILE): os.remove(CALIB_FILE)
        self.calib.x = self.calib.y = None; self._calib_refresh()

    def _track_mouse(self):
        try:
            x, y = pyautogui.position()
            self.lbl_mouse.config(text=f"Mouse:  X = {x}   Y = {y}")
        except Exception: pass
        self.root.after(180, self._track_mouse)

    # ── Small UI helpers ─────────────────────
    def _mode_hint(self):
        self.lbl_mode.config(
            text="▸ Entire message sent in one go — formatting preserved"
            if self.v_single.get()
            else "▸ Each paragraph sent as a separate bubble")
        self._autosave()

    def _char_count(self, _=None):
        t = self.msg_box.get("1.0", tk.END).strip()
        self.lbl_chars.config(
            text=f"Words: {len(t.split()) if t else 0}  ·  Chars: {len(t)}")

    def _log(self, tag, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self._ui_q.put(("log", tag, f"[{ts}] {text}"))

    def _dlog(self, text):
        if self._cfg.get("diagnostic", False):
            self._log("debug", f"  [DBG] {text}")

    def _status(self, txt, color=None):
        self._ui_q.put(("status", txt, color or AMBER))

    def _refresh_daily(self):
        today = self.logger.sent_today()
        lim   = self._cfg.get("dlimit", 30)
        pct   = today / lim if lim else 0
        fg    = RED if pct >= 1.0 else (AMBER if pct >= 0.8 else GREEN)
        self.lbl_daily.config(text=f"Today: {today}/{lim}", fg=fg)
        self.lbl_alltime.config(text=f"All-time: {self.logger.total_sent()}")
        self.lbl_bl_count.config(text=f"Blacklist: {self.blacklist.count()}")

    def _update_stats(self):
        self._ui_q.put(("stats",))

    def _do_stats(self):
        s = self._sl
        s["Loaded"].config(text=str(self.total))
        s["Sent"].config(text=str(self.sent_count))
        s["Failed"].config(text=str(len(self.failed_list)))
        s["Skipped"].config(text=str(self.skipped_count))
        pct = (self.current_idx / self.total * 100) if self.total else 0
        self.v_prog.set(pct)
        self.lbl_prog.config(
            text=f"{self.current_idx}/{self.total}" if self.total else "")
        if self.start_time and self.current_idx > 0:
            e = time.time() - self.start_time
            r = (self.total - self.current_idx) * (e / self.current_idx)
            s["ETA"].config(text=fmt_time(r))
        else:
            s["ETA"].config(text="--:--")
        self._refresh_daily()

    def _poll_ui(self):
        try:
            while True:
                item = self._ui_q.get_nowait(); cmd = item[0]
                if cmd == "log":
                    _, tag, text = item
                    self.log_box.config(state="normal")
                    self.log_box.insert("end", text + "\n", tag)
                    self.log_box.see("end")
                    self.log_box.config(state="disabled")
                elif cmd == "status":
                    txt = item[1]; col = item[2] if len(item) > 2 else AMBER
                    self.lbl_status.config(text=txt, fg=col)
                    self.lbl_hdr.config(text=txt, fg=col)
                elif cmd == "stats":
                    self._do_stats()
                elif cmd == "cdown":
                    self.lbl_cdown.config(text=item[1])
        except queue.Empty:
            pass
        self.root.after(40, self._poll_ui)

    def _anim_header(self):
        if self.running and not self.paused:
            dots = ["●", "○", "◉", "○"]
            self._dot = (self._dot + 1) % 4
            cur = self.lbl_hdr.cget("text")
            if cur and cur[0] in "●○◉":
                self.lbl_hdr.config(text=dots[self._dot] + cur[1:])
        self.root.after(500, self._anim_header)

    def _open_log_file(self):
        if not os.path.exists(LOG_FILE):
            messagebox.showinfo("No Log", "Run a session first."); return
        try:
            os.startfile(LOG_FILE)
        except AttributeError:
            subprocess.call(
                ["open" if sys.platform == "darwin" else "xdg-open", LOG_FILE])

    def _copy_log(self):
        try:
            write_clip(self.log_box.get("1.0", tk.END))
            messagebox.showinfo("Copied", "Log copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_close(self):
        self._autosave()
        if self.running:
            if messagebox.askyesno("Running", "Session running. Stop and exit?"):
                self.running = False; self.root.after(700, self.root.destroy)
        else:
            self.root.destroy()

    # ════════════════════════════════════════
    #  CORE SEND ENGINE
    # ════════════════════════════════════════

    def _want_hide(self):
        return self.v_hide_browser.get() and HAS_GW

    def _browser_on(self):
        try:
            self.browser.activate(); time.sleep(0.18)
        except Exception: pass

    def _browser_off(self):
        try:
            if self._want_hide():
                time.sleep(0.06); self.browser.hide()
        except Exception: pass

    def _click_box(self):
        """Click the WA message input box. Handles hide-browser mode."""
        if self._want_hide():
            try: self.browser.activate(); time.sleep(0.15)
            except Exception: pass
        cx, cy = self.calib.get()
        try:
            pyautogui.moveTo(cx + random.randint(-3, 3),
                             cy + random.randint(-2, 2),
                             duration=random.uniform(0.06, 0.14))
            time.sleep(0.05); pyautogui.click(); time.sleep(0.25)
            self._dlog(f"clicked box at ({cx},{cy})")
        except Exception as e:
            self._dlog(f"click_box error: {e}")
        if self._want_hide():
            try: self.browser.hide()
            except Exception: pass

    def _wait_page_ready(self, deadline):
        """
        Poll until WA Web page is interactive using corrected clipboard probing.
        Returns (True,"") or (False,"reason").
        """
        load_max = self.v_load.get(); waited = 0.0
        self._dlog(f"wait_page_ready max={load_max}s")
        self._browser_on()
        try:
            while waited < load_max:
                if not self.running or time.time() > deadline:
                    return False, "timeout"
                while self.paused: time.sleep(0.2)

                # ── Title check for invalid numbers only ───────────────────
                title = self.browser.title()
                self._dlog(f"  title='{title[:70]}'")
                for kw in _INVALID_KEYS:
                    if kw in title:
                        return False, f"WA says number invalid: {title[:60]}"

                # ── Clipboard probe (safe, fast, leaves box clean) ────────
                try:
                    write_clip("AR_PROBE")
                    time.sleep(0.05)
                    self._click_box()
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(0.1)
                    write_clip("")
                    time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "c")
                    time.sleep(0.1)
                except Exception:
                    pass
                
                clip = read_clip()
                self._dlog(f"  clip='{clip[:50]}'")
                if "AR_PROBE" in clip:
                    self._dlog("page ready via clipboard probe")
                    try:
                        pyautogui.press("backspace") # Clear the probe text
                        time.sleep(0.05)
                    except Exception:
                        pass
                    return True, ""

                self._status(
                    f"● Waiting for WA Web… ({int(load_max-waited)}s left)", AMBER)
                time.sleep(0.8); waited += 0.8

            self._dlog("page_ready timeout")
            return False, "page load timeout"
        finally:
            self._browser_off()

    def _paste_verified(self, text):
        """Paste text. Verifies it landed in the box. Retries up to 3x."""
        self._dlog("paste_verified")
        self._browser_on()
        try:
            for attempt in range(3):
                try:
                    write_clip(text); time.sleep(0.15)
                    # Clear any text in the box first by selecting all
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(0.3)
                    
                    # Verify by copying back
                    write_clip("AR_PROBE"); time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "c")
                    time.sleep(0.1)
                except Exception as e:
                    self._dlog(f"  paste attempt {attempt+1} error: {e}")
                    continue
                clip = read_clip()
                self._dlog(f"  paste attempt {attempt+1} clip='{clip[:40]}'")
                if clip and clip != "AR_PROBE":
                    # Restore text focus (re-deselect)
                    self._click_box()
                    return True
                self._log("warn", f"  Paste attempt {attempt+1} empty — retrying")
                self._click_box(); time.sleep(0.2)
            return False
        finally:
            self._browser_off()

    def _press_enter(self):
        """Send via keyboard Enter — no mouse click needed."""
        self._dlog("press_enter")
        self._browser_on()
        try:
            pyautogui.press("enter"); time.sleep(0.22)
        except Exception as e:
            self._dlog(f"press_enter error: {e}")
        self._browser_off()

    def _confirm_sent(self, max_sec=10.0):
        """Wait for input box to clear after Enter (confirms WA queued the send)."""
        self._dlog(f"confirm_sent max={max_sec}s")
        deadline = time.time() + max_sec
        self._browser_on()
        try:
            while time.time() < deadline:
                if not self.running: return False
                try:
                    write_clip("AR_PROBE"); time.sleep(0.07)
                    pyautogui.hotkey("ctrl", "a"); time.sleep(0.09)
                    pyautogui.hotkey("ctrl", "c"); time.sleep(0.10)
                except Exception: pass
                clip = read_clip()
                self._dlog(f"  confirm clip='{clip[:30]}'")
                if clip == "AR_PROBE" or clip.strip() == "":
                    self._dlog("confirm_sent OK ✅"); return True
                time.sleep(0.35)
            self._dlog("confirm_sent TIMEOUT"); return False
        finally:
            self._browser_off()

    # ── _send_single ────────────────────────
    def _send_single(self, number, msg):
        timeout = self.v_timeout.get(); deadline = time.time() + timeout
        try:
            # Step 1: Open URL with reliable OS method
            url = (f"https://web.whatsapp.com/send/"
                   f"?phone={number}&type=phone_number&app_absent=0")
            self._dlog(f"open_url {url}")
            self._status(f"● Opening browser → {number}", BLUE)
            open_url(url)

            # Step 2: Fixed sleep for browser to launch (conn_delay)
            conn = self.v_conn_delay.get()
            self._status(f"● Browser launching… waiting {conn}s", AMBER)
            time.sleep(conn)

            # Step 3: Wait for browser window (never hard-fails)
            self._dlog("waiting for browser window")
            self.browser.wait_for_window(max_sec=min(12.0, deadline - time.time() - 5))

            # Step 4: Bring to front, then hide if option set
            self._dlog("activating browser")
            self.browser.activate(); time.sleep(0.45)
            if self._want_hide():
                time.sleep(0.3); self.browser.hide()

            if time.time() > deadline:
                return False, "timeout after browser open"

            # Step 5: Wait for WA page to be interactive
            self._status(f"● Waiting for WA page… ({number})", AMBER)
            ready, reason = self._wait_page_ready(deadline)
            if not ready: return False, reason
            if time.time() > deadline: return False, "timeout after page load"

            # Step 6: Paste message (verified, retried up to 3x)
            self._status(f"● Pasting message → {number}", BLUE)
            if not self._paste_verified(msg):
                return False, "paste failed after 3 attempts — redo calibration"
            time.sleep(0.4)

            # Step 7: Send via keyboard Enter — NO mouse click needed
            self._status(f"● Sending → {number}", BLUE)
            self._press_enter()

            # Step 8: Confirm (input box clears = WA accepted the send)
            self._status(f"● Confirming send… ({number})", AMBER)
            secs = min(10.0, deadline - time.time())
            if secs < 2.0: return False, "no time left to confirm"
            if not self._confirm_sent(max_sec=secs):
                return False, "box did not clear — check calibration (Help tab)"

            # Step 9: Post-send countdown
            for i in range(self.v_postsend.get(), 0, -1):
                if not self.running: break
                self._status(f"● Sent ✅  closing tab in {i}s…", GREEN)
                time.sleep(1.0)

            return True, ""

        except pyautogui.FailSafeException:
            raise
        except Exception as ex:
            tb = traceback.format_exc().strip().splitlines()[-1]
            self._dlog(f"_send_single exception: {tb}")
            return False, str(ex)
        finally:
            # ALWAYS close the tab no matter what happened
            try: self.browser.close_tab(hide_after=self._want_hide())
            except Exception: pass

    # ── _send_split ─────────────────────────
    def _send_split(self, number, msg):
        timeout = self.v_timeout.get(); deadline = time.time() + timeout
        parts = [p.strip() for p in msg.split("\n\n") if p.strip()]
        if not parts: return False, "empty message"
        try:
            url = (f"https://web.whatsapp.com/send/"
                   f"?phone={number}&type=phone_number&app_absent=0")
            open_url(url)
            conn = self.v_conn_delay.get()
            self._status(f"● Browser launching… waiting {conn}s", AMBER)
            time.sleep(conn)
            self.browser.wait_for_window(max_sec=min(12.0, deadline - time.time() - 5))
            self.browser.activate(); time.sleep(0.45)
            if self._want_hide(): time.sleep(0.3); self.browser.hide()

            ready, reason = self._wait_page_ready(deadline)
            if not ready: return False, reason

            for i, part in enumerate(parts):
                if not self.running or time.time() > deadline:
                    return False, "stopped or timed out"
                if not self._paste_verified(part):
                    return False, f"paste failed on part {i+1}"
                time.sleep(0.35); self._press_enter()
                if not self._confirm_sent(min(8.0, deadline - time.time())):
                    return False, f"box did not clear after part {i+1}"
                if i < len(parts) - 1:
                    time.sleep(gauss(0.9, 2.0))

            for i in range(self.v_postsend.get(), 0, -1):
                if not self.running: break
                self._status(f"● Sent ✅  closing tab in {i}s…", GREEN)
                time.sleep(1.0)
            return True, ""

        except pyautogui.FailSafeException:
            raise
        except Exception as ex:
            tb = traceback.format_exc().strip().splitlines()[-1]
            self._dlog(f"_send_split exception: {tb}")
            return False, str(ex)
        finally:
            try: self.browser.close_tab(hide_after=self._want_hide())
            except Exception: pass

    # ── send_message (retry wrapper) ────────
    def send_message(self, number, raw):
        if self.v_dry.get():
            time.sleep(random.uniform(1.2, 2.8)); return True, ""
        max_ret = self.v_retries.get(); last = ""
        for attempt in range(1, max_ret + 1):
            if not self.running: return False, "stopped"
            if attempt > 1:
                wait = min(30, gauss(5, 10) * (1.5 ** (attempt - 1)))
                self._log("warn",
                    f"  ↻ Retry {attempt}/{max_ret} in {wait:.0f}s → {number}")
                t = 0.0
                while t < wait and self.running:
                    self._status(f"● Retry {attempt} — waiting {wait-t:.0f}s…", AMBER)
                    time.sleep(0.5); t += 0.5
            if not self.running: return False, "stopped"
            msg = vary_msg(raw) if self.v_vary.get() else raw
            try:
                fn = self._send_single if self.v_single.get() else self._send_split
                ok, reason = fn(number, msg)
            except pyautogui.FailSafeException:
                self._log("warn", "🛑 EMERGENCY STOP (mouse corner)")
                self.do_stop(); return False, "emergency stop"
            except Exception as ex:
                ok = False
                reason = traceback.format_exc().strip().splitlines()[-1]
            last = reason
            if ok: return True, ""
            self._log("warn", f"  Attempt {attempt} failed: {reason}")
        return False, last

    # ════════════════════════════════════════
    #  MAIN LOOP
    # ════════════════════════════════════════
    def _loop(self):
        raw      = self.msg_box.get("1.0", tk.END).strip()
        dlim     = self.v_dlimit.get()
        sent_set = self.logger.sent_set() if self.v_skip_sent.get() else set()

        while self.current_idx < self.total and self.running:
            while self.paused and self.running: time.sleep(0.25)
            if not self.running: break

            if self.logger.sent_today() >= dlim:
                self._log("warn", f"⚠ Daily limit {dlim} reached.")
                self.root.after(0, lambda: messagebox.showwarning(
                    "Daily Limit", f"Reached {dlim} messages today. Session stopped."))
                break

            number = self.numbers[self.current_idx]
            self.current_idx += 1
            self._update_stats()

            if self.v_skip_sent.get() and number in sent_set:
                self.skipped_count += 1
                self._log("skip", f"⏭ Already sent: {number}")
                self._update_stats(); continue
            if self.v_skip_bl.get() and self.blacklist.has(number):
                self.skipped_count += 1
                self._log("skip", f"⏭ Blacklisted: {number}")
                self._update_stats(); continue

            self._status(
                f"● {self.current_idx}/{self.total} → {number}", BLUE)
            self._log("info",
                f"→ {self.current_idx}/{self.total}  {number}")

            ok, reason = self.send_message(number, raw)

            if ok:
                self.sent_count += 1; sent_set.add(number)
                self.logger.mark_sent(number)
                self._log("sent", f"✅ {number}")
            else:
                self.failed_list.append((number, reason))
                self.logger.mark_failed(number, reason)
                self._log("failed", f"❌ {number}  →  {reason}")
                if self.v_stop_on_fail.get():
                    self._log("warn", "🛑 Stop-on-fail: stopping.")
                    self.running = False; break

            self._update_stats()

            if self.running and self.current_idx < self.total:
                mn  = self.v_dmin.get()
                mx  = max(mn + 5, self.v_dmax.get())
                delay = gauss(mn, mx)
                self._log("info",
                    f"  ⏳ Next in {delay:.0f}s  "
                    f"({self.current_idx}/{self.total}  ·  "
                    f"{self.sent_count}✅  {len(self.failed_list)}❌)")
                elapsed = 0.0
                while elapsed < delay and self.running:
                    while self.paused and self.running: time.sleep(0.25)
                    self._status(
                        f"● Next in {delay-elapsed:.0f}s  "
                        f"({self.current_idx}/{self.total} done  ·  "
                        f"{self.sent_count}✅ {len(self.failed_list)}❌)", MUTED)
                    time.sleep(0.5); elapsed += 0.5

        # ── Session done ─────────────────────
        self.running = False
        dur = fmt_time(time.time() - self.start_time) if self.start_time else "?"
        self._log("header", "━" * 55)
        self._log("header",
            f"DONE  ✅{self.sent_count}  ❌{len(self.failed_list)}"
            f"  ⏭{self.skipped_count}  ⏱{dur}")
        self._log("header", "━" * 55)
        if self.v_sound.get(): play_sound()
        self.root.after(0, self._done_ui)

    def _done_ui(self):
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ PAUSE")
        self._status(
            f"● Done  ✅{self.sent_count} ❌{len(self.failed_list)} ⏭{self.skipped_count}",
            GREEN if not self.failed_list else AMBER)
        self._update_stats(); self._show_summary()

    def _show_summary(self):
        dur = fmt_time(time.time() - self.start_time) if self.start_time else "?"
        lines = [
            "Session Complete\n",
            f"  ✅  Sent     : {self.sent_count}",
            f"  ❌  Failed   : {len(self.failed_list)}",
            f"  ⏭  Skipped  : {self.skipped_count}",
            f"  ⏱  Duration : {dur}",
        ]
        if self.failed_list:
            lines += ["", "── Failed numbers ──────────────────────────"]
            for n, r in self.failed_list:
                lines.append(f"  {n}  →  {r}")
            lines += ["", "Use 'View Failed' → 'Retry' or 'Export'."]

        p = tk.Toplevel(self.root); p.title("Summary")
        p.configure(bg=BG); p.geometry("620x460"); p.resizable(True, True)
        tk.Label(p, text="⚡ Session Summary", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=(14, 6))
        fr = tk.Frame(p, bg=BG); fr.pack(fill="both", expand=True, padx=16, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        box = tk.Text(fr, bg=CARD, fg=TEXT, font=("Consolas", 9),
                      relief="flat", padx=10, pady=8, yscrollcommand=sc.set)
        box.pack(fill="both", expand=True); sc.config(command=box.yview)
        box.insert("end", "\n".join(lines)); box.config(state="disabled")
        bf = tk.Frame(p, bg=BG); bf.pack(pady=10)
        ttk.Button(bf, text="✅ OK", command=p.destroy,
                   style="A.TButton").pack(side="left", padx=6)
        if self.failed_list:
            ttk.Button(bf, text="💾 Export",
                       command=lambda: (p.destroy(), self.do_export())
                       ).pack(side="left", padx=6)
            ttk.Button(bf, text="🔁 Retry",
                       command=lambda: (p.destroy(), self.do_retry())
                       ).pack(side="left", padx=6)

    # ════════════════════════════════════════
    #  BUTTON ACTIONS
    # ════════════════════════════════════════
    def do_import(self):
        path = filedialog.askopenfilename(
            title="Select number list",
            filetypes=[("Text/CSV", "*.txt *.csv"), ("All", "*.*")])
        if not path: return
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except Exception as e:
            messagebox.showerror("Error", str(e)); return
        clean, seen, bad = [], set(), 0
        for ln in lines:
            ln = ln.strip().split(",")[0].strip()
            n  = to_e164(ln)
            if n and n not in seen: seen.add(n); clean.append(n)
            elif ln: bad += 1
        self.numbers = clean; self.total = len(clean)
        self.current_idx = 0; self.sent_count = 0
        self.skipped_count = 0; self.failed_list = []
        self._update_stats()
        prev = "\n".join(f"  {n}" for n in clean[:6])
        if len(clean) > 6: prev += f"\n  … +{len(clean)-6} more"
        self._log("info",
            f"Imported {self.total} numbers from "
            f"'{os.path.basename(path)}'  ({bad} invalid/dup skipped)")
        messagebox.showinfo("Imported",
            f"✅  {self.total} numbers loaded\n"
            f"⚠   {bad} invalid/duplicate skipped\n\n{prev}")

    def do_reset(self):
        if self.running:
            messagebox.showwarning("Running", "Stop the session first."); return
        if not messagebox.askyesno("Reset", "Clear list and reset counters?"): return
        self.numbers = []; self.total = 0; self.current_idx = 0
        self.sent_count = 0; self.failed_list = []; self.skipped_count = 0
        self._update_stats()
        self._status("● Idle — import a new list", AMBER)
        self._log("info", "List reset.")

    def do_start(self):
        if not self.numbers:
            messagebox.showwarning("No List", "Import a number list first."); return
        if self.current_idx >= self.total:
            messagebox.showinfo("Done", "All processed. Reset first."); return
        lim = self.v_dlimit.get()
        if self.logger.sent_today() >= lim:
            messagebox.showwarning("Daily Limit",
                f"Already sent {lim} messages today.\n"
                "Increase limit in Settings or wait until tomorrow."); return
        if not self.calib.is_set():
            if not messagebox.askyesno("Not Calibrated",
                "Click position not calibrated — using estimated default.\n\n"
                "For best results, go to Calibrate tab first.\n\nStart anyway?"): return
        msg = self.msg_box.get("1.0", tk.END).strip()
        if not msg:
            messagebox.showwarning("No Message", "Write a message first."); return

        self.running = True; self.paused = False
        self.start_time = time.time()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ PAUSE")
        self._status("● Running…", GREEN)
        self._log("info",
            f"▶ Session started — {self.total - self.current_idx} numbers"
            + ("  [DRY RUN]" if self.v_dry.get() else "")
            + ("  [DIAGNOSTIC]" if self.v_diagnostic.get() else ""))
        threading.Thread(target=self._loop, daemon=True).start()

    def do_pause(self):
        if not self.running: return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RESUME")
            self._status(f"● Paused at {self.current_idx}/{self.total}", AMBER)
            self._log("warn", "⏸ Paused.")
        else:
            self.btn_pause.config(text="⏸ PAUSE")
            self._status("● Running…", GREEN)
            self._log("info", "▶ Resumed.")

    def do_stop(self):
        self.running = False; self.paused = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))
        self._status(
            f"● Stopped  ✅{self.sent_count} ❌{len(self.failed_list)}", RED)
        self._log("warn",
            f"⏹ Stopped — {self.sent_count} sent, "
            f"{len(self.failed_list)} failed")

    def do_test(self):
        val = simpledialog.askstring(
            "Test Send", "Enter phone number (10 or 12 digits):")
        if not val: return
        n = to_e164(val.strip())
        if not n:
            messagebox.showwarning("Invalid",
                "Cannot parse that number. Use 10 or 12 digits."); return
        raw = self.msg_box.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("Empty", "Write a message first."); return
        self._log("info", f"🔬 Test → {n}")
        def _t():
            ok, reason = self.send_message(n, raw)
            res = "✅ Test sent!" if ok else f"❌ FAILED\n\n{reason}"
            self._log("sent" if ok else "failed",
                f"  Test {'OK' if ok else 'FAILED: ' + reason}")
            self.root.after(0, lambda: messagebox.showinfo("Test Result", res))
        threading.Thread(target=_t, daemon=True).start()

    def do_retry(self):
        if not self.failed_list:
            messagebox.showinfo("Empty", "No failed numbers to retry."); return
        self.numbers     = [n for n, _ in self.failed_list]
        self.total       = len(self.numbers)
        self.current_idx = 0; self.sent_count = 0
        self.skipped_count = 0; self.failed_list = []
        self._update_stats()
        messagebox.showinfo("Retry Ready",
            f"Loaded {self.total} failed numbers.\nClick ▶ START to retry.")

    def do_export(self):
        if not self.failed_list:
            messagebox.showinfo("Empty", "No failed numbers to export."); return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
            initialfile="failed_numbers.txt")
        if not p: return
        try:
            with open(p, "w", encoding="utf-8") as f:
                for n, r in self.failed_list:
                    f.write(f"{n}  |  {r}\n")
            messagebox.showinfo("Exported",
                f"Saved {len(self.failed_list)} numbers to:\n{p}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def do_blacklist(self):
        if not self.failed_list:
            val = simpledialog.askstring(
                "Blacklist", "Enter number to blacklist:")
            if not val: return
            n = to_e164(val.strip())
            if not n:
                messagebox.showwarning("Invalid", "Cannot parse."); return
            self.blacklist.add(n); self._refresh_daily()
            messagebox.showinfo("Done", f"{n} blacklisted."); return
        ch = messagebox.askyesnocancel("Blacklist",
            f"{len(self.failed_list)} failed numbers.\n\n"
            "YES = blacklist ALL failed\n"
            "NO  = enter one number\n"
            "CANCEL = do nothing")
        if ch is None: return
        if ch:
            for n, _ in self.failed_list: self.blacklist.add(n)
            self._refresh_daily()
            messagebox.showinfo("Done",
                f"{len(self.failed_list)} numbers blacklisted.")
        else:
            val = simpledialog.askstring("Blacklist", "Enter number:")
            if val:
                n = to_e164(val.strip())
                if n:
                    self.blacklist.add(n); self._refresh_daily()
                    messagebox.showinfo("Done", f"{n} blacklisted.")

    def do_view_failed(self):
        if not self.failed_list:
            messagebox.showinfo("Empty", "No failed numbers yet."); return
        p = tk.Toplevel(self.root); p.title("Failed Numbers")
        p.configure(bg=BG); p.geometry("580x420"); p.resizable(True, True)
        tk.Label(p, text=f"❌  {len(self.failed_list)} Failed Numbers",
                 bg=BG, fg=RED,
                 font=("Segoe UI", 11, "bold")).pack(pady=(14, 4))
        fr = tk.Frame(p, bg=BG); fr.pack(fill="both", expand=True, padx=14, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        box = tk.Text(fr, bg=CARD, fg=TEXT, font=("Consolas", 9),
                      relief="flat", padx=8, pady=6, yscrollcommand=sc.set)
        box.pack(fill="both", expand=True); sc.config(command=box.yview)
        box.tag_config("n", foreground=RED); box.tag_config("r", foreground=MUTED)
        for n, r in self.failed_list:
            box.insert("end", f"  {n}", "n")
            box.insert("end", f"  →  {r}\n", "r")
        box.config(state="disabled")
        bf = tk.Frame(p, bg=BG); bf.pack(pady=10)
        for txt, cmd in [
            ("Close",     p.destroy),
            ("💾 Export", lambda: (p.destroy(), self.do_export())),
            ("🔁 Retry",  lambda: (p.destroy(), self.do_retry())),
            ("🔕 BL All", lambda: (p.destroy(), self.do_blacklist())),
        ]:
            ttk.Button(bf, text=txt, command=cmd).pack(side="left", padx=4)

    def do_clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")
        self._log("system", "Log cleared.")


# ═══════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    AutoReach(root)
    root.mainloop()

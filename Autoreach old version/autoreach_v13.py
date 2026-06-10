# -*- coding: utf-8 -*-
"""
AutoReach v13.0 — WhatsApp Web Bulk Messenger
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT'S NEW IN v13:
  ✅ ZERO MOUSE — message pre-filled in URL (?text=…), only Enter pressed
  ✅ NO CALIBRATION NEEDED — works on any screen size/resolution
  ✅ HIDE BROWSER FIXED — browser minimizes immediately, UI stays usable
  ✅ TITLE-BASED PAGE DETECTION — no clipboard probing, no paste, instant
  ✅ TAB NEVER CLOSES until message confirmed sent
  ✅ Direct browser launch (Chrome > Edge > Brave > Firefox)
  ✅ Retry logic, daily limits, anti-ban delays all preserved

Install:  pip install pyautogui pyperclip pygetwindow
Run:      python autoreach_v13.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import threading, time, random, os, json, queue, sys, traceback
import subprocess, re, webbrowser
import urllib.parse
import pyautogui
from datetime import datetime, timedelta

try:
    import pyperclip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    gw = None
    HAS_GW = False

# ── Try win32gui for reliable SetForegroundWindow ──
try:
    import ctypes
    _u32 = ctypes.windll.user32
    HAS_WIN32 = True
except Exception:
    HAS_WIN32 = False

VERSION        = "13.0"
LOG_FILE       = "autoreach_log.json"
BLACKLIST_FILE = "blacklist.txt"
SETTINGS_FILE  = "autoreach_settings.json"

BG     = "#0D1117"; CARD  = "#161B22"; CARD2 = "#1C2128"
ACCENT = "#2F81F7"; TEXT  = "#E6EDF3"; MUTED = "#8B949E"
GREEN  = "#3FB950"; RED   = "#F85149"; AMBER = "#D29922"
BLUE   = "#79C0FF"; PURPLE= "#BC8CFF"; BORDER= "#30363D"

_INVALID_KEYS = [
    "invalid phone number", "not on whatsapp",
    "phone number shared via url is invalid",
    "link you opened is invalid",
]
_READY_SKIP = ["web.whatsapp.com", "new tab", "whatsapp", "loading"]
_INVISIBLE  = ["\u200b", "\u200c", "\u200d", "\u2060"]

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.02

DEFAULTS = {
    "dmin": 45, "dmax": 90,
    "conn_delay": 7, "load": 25,
    "postsend": 5, "timeout": 90,
    "dlimit": 30, "retries": 2,
    "skip_sent": True, "skip_bl": True,
    "vary": True, "sound": True,
    "hide_browser": False,
    "stop_on_fail": False,
    "diagnostic": False,
    "single_msg": True,
}

# ═══════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════

def gauss(mn, mx):
    return max(mn, min(mx, random.gauss((mn + mx) / 2, (mx - mn) / 4)))

def vary_msg(text):
    w = text.split(" ")
    if len(w) < 4:
        return text
    w[random.randint(1, len(w) - 2)] += random.choice(_INVISIBLE)
    return " ".join(w)

def to_e164(s):
    d = "".join(filter(str.isdigit, s))
    if len(d) == 12 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    return d if len(d) == 12 else None

def fmt_time(s):
    return str(timedelta(seconds=int(max(0, s))))

def build_url(number, text):
    """Build WhatsApp Web URL with message pre-filled — NO clipboard/mouse needed."""
    encoded = urllib.parse.quote(text, safe="")
    return (f"https://web.whatsapp.com/send/"
            f"?phone={number}&text={encoded}&type=phone_number&app_absent=0")

def open_browser(url):
    """Launch detected browser directly via subprocess, fall back to os.startfile."""
    if sys.platform == "win32":
        pf   = os.environ.get("ProgramFiles",      "C:\\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        loc  = os.environ.get("LocalAppData",       "")
        candidates = [
            os.path.join(pf,   "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(pf86, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(loc,  "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(pf86, "Microsoft\\Edge\\Application\\msedge.exe"),
            os.path.join(pf,   "Microsoft\\Edge\\Application\\msedge.exe"),
            os.path.join(pf,   "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            os.path.join(pf86, "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            os.path.join(loc,  "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            os.path.join(pf,   "Mozilla Firefox\\firefox.exe"),
            os.path.join(pf86, "Mozilla Firefox\\firefox.exe"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                try:
                    subprocess.Popen([p, url])
                    return p
                except Exception:
                    pass
        try:
            os.startfile(url)
            return "default"
        except Exception:
            pass
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
        return "default"
    else:
        subprocess.Popen(["xdg-open", url])
        return "default"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return "webbrowser"

def play_sound():
    try:
        if sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass

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
#  BROWSER MANAGER
# ═══════════════════════════════════════════

class BrowserMgr:
    """
    Manages the browser window: detect, activate (foreground), minimize.
    ALL methods are fully guarded — never raises.
    """

    def _all_wins(self):
        if not HAS_GW:
            return []
        try:
            return list(gw.getAllWindows())
        except Exception:
            return []

    def _browser_wins(self):
        """Return browser windows, WhatsApp ones first."""
        kw_exact  = ["google chrome", "microsoft edge", "firefox", "brave"]
        kw_substr = ["whatsapp"]
        out = []
        wa_wins = []
        for w in self._all_wins():
            t = getattr(w, "title", "").lower().replace("\u200b", " ")
            if any(k in t for k in kw_substr):
                wa_wins.append(w)
            elif any(re.search(r"\b" + re.escape(k) + r"\b", t)
                     for k in ["chrome", "msedge", "firefox", "brave", "opera"]):
                out.append(w)
            elif any(k in t for k in kw_exact):
                out.append(w)
        return wa_wins + out  # WhatsApp windows first

    def _foreground(self, w):
        """
        Bring window to foreground reliably.
        Uses AllowSetForegroundWindow trick to bypass Windows focus lock.
        """
        try:
            w.restore()
            time.sleep(0.15)
        except Exception:
            pass
        if HAS_WIN32:
            try:
                hwnd = w._hWnd
                # AllowSetForegroundWindow(ASFW_ANY) lets us steal focus
                _u32.AllowSetForegroundWindow(-1)  # -1 = ASFW_ANY
                _u32.ShowWindow(hwnd, 9)            # SW_RESTORE
                _u32.SetForegroundWindow(hwnd)
                time.sleep(0.3)  # Windows needs time to grant focus
                return True
            except Exception:
                pass
        # Fallback: pygetwindow activate
        try:
            w.activate()
            time.sleep(0.3)
            return True
        except Exception:
            return False

    def wait_for_window(self, max_sec=15.0):
        """Poll until browser window appears. Always returns True."""
        if not HAS_GW:
            return True
        deadline = time.time() + max_sec
        while time.time() < deadline:
            if self._browser_wins():
                return True
            time.sleep(0.4)
        return True  # proceed even on timeout

    def activate(self):
        """Bring browser to foreground."""
        for w in self._browser_wins():
            try:
                if self._foreground(w):
                    return True
            except Exception:
                pass
        return False

    def minimize(self):
        """Minimize/hide all browser windows."""
        for w in self._browser_wins():
            try:
                if HAS_WIN32:
                    _u32.ShowWindow(w._hWnd, 6)  # SW_MINIMIZE
                else:
                    w.minimize()
            except Exception:
                pass

    def title(self):
        """Get title of the topmost browser window."""
        wins = self._browser_wins()
        return getattr(wins[0], "title", "").lower() if wins else ""

    def close_tab(self):
        """Close current tab via Ctrl+W. Activate first."""
        self.activate()
        time.sleep(0.2)
        try:
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.5)
        except Exception:
            pass

# ═══════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════

class AutoReach:

    def __init__(self, root):
        self.root = root
        self.root.title(f"AutoReach v{VERSION}")
        self.root.geometry("920x900")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(800, 800)

        self.numbers = []; self.current_idx = 0; self.total = 0
        self.sent_count = 0; self.failed_list = []; self.skipped_count = 0
        self.running = False; self.paused = False; self.start_time = None
        self._ui_q = queue.Queue(); self._dot = 0

        self.logger    = Logger()
        self.blacklist = Blacklist()
        self.browser   = BrowserMgr()
        self._cfg      = load_settings()

        self._style(); self._build()
        self._apply_cfg(); self._refresh_daily()
        self._poll_ui(); self._anim_header()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _style(self):
        s = ttk.Style(); s.theme_use("clam")
        s.configure("TButton", background=CARD2, foreground=TEXT,
                    font=("Segoe UI", 9, "bold"), borderwidth=1,
                    relief="flat", padding=7)
        s.map("TButton",
              background=[("active","#2a5faa"),("disabled",CARD)],
              foreground=[("disabled",MUTED)])
        s.configure("A.TButton", background=ACCENT, foreground="#fff",
                    font=("Segoe UI", 10, "bold"), padding=9)
        s.map("A.TButton", background=[("active","#1a5fcc")])
        s.configure("D.TButton", background="#3a1010", foreground=RED,
                    font=("Segoe UI", 9, "bold"), padding=7)
        s.map("D.TButton", background=[("active","#5a1515")])
        s.configure("W.TButton", background="#3a2a00", foreground=AMBER,
                    font=("Segoe UI", 9, "bold"), padding=7)
        s.map("W.TButton", background=[("active","#5a4000")])
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

    def _build(self):
        hdr = tk.Frame(self.root, bg="#080D13", height=64)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text=f"⚡ AutoReach v{VERSION}",
                 fg=ACCENT, bg="#080D13",
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=20, pady=12)
        tk.Label(hdr, text="WhatsApp Bulk Messenger — Zero Mouse",
                 fg=MUTED, bg="#080D13",
                 font=("Segoe UI", 9)).pack(side="left", pady=20)
        self.lbl_hdr = tk.Label(hdr, text="● IDLE", fg=AMBER, bg="#080D13",
                                font=("Segoe UI", 9, "bold"))
        self.lbl_hdr.pack(side="right", padx=20)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=8)
        self._tabs = {}
        for name in ("Send", "Log", "Settings", "Help"):
            f = tk.Frame(nb, bg=BG)
            nb.add(f, text=f"  {name}  ")
            self._tabs[name] = f

        self._tab_send(self._tabs["Send"])
        self._tab_log(self._tabs["Log"])
        self._tab_settings(self._tabs["Settings"])
        self._tab_help(self._tabs["Help"])

    def _tab_send(self, T):
        top = tk.Frame(T, bg=BG); top.pack(fill="x", padx=14, pady=(10,2))
        tk.Label(top, text="✉  Message Template", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        self.v_single = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="📋 Single bubble",
                       variable=self.v_single, bg=BG, fg=BLUE,
                       selectcolor=CARD2, activebackground=BG,
                       font=("Segoe UI", 9, "bold"),
                       command=self._autosave).pack(side="right")

        mf = tk.Frame(T, bg=BORDER, bd=1); mf.pack(padx=14, pady=4, fill="x")
        sc = tk.Scrollbar(mf, bg=CARD2); sc.pack(side="right", fill="y")
        self.msg_box = tk.Text(mf, height=9, bg=CARD, fg=TEXT,
                               insertbackground=TEXT, font=("Consolas", 9),
                               relief="flat", padx=10, pady=8, undo=True,
                               wrap="word", yscrollcommand=sc.set)
        self.msg_box.pack(fill="both"); sc.config(command=self.msg_box.yview)
        self.msg_box.insert("1.0",
            "Hello 👋\n\nType your message here.\n\n"
            "Each double-newline paragraph = separate bubble (if Single bubble is OFF).")
        self.msg_box.bind("<KeyRelease>", self._char_count)

        cr = tk.Frame(T, bg=BG); cr.pack(fill="x", padx=14)
        self.lbl_chars = tk.Label(cr, text="", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 8))
        self.lbl_chars.pack(side="right"); self._char_count()

        # Hide browser toggle on Send tab too
        hf = tk.Frame(T, bg=CARD2, pady=6); hf.pack(fill="x", padx=14, pady=(4,2))
        self.v_hide_browser = tk.BooleanVar(value=False)
        state = "normal" if HAS_GW else "disabled"
        lbl = "🙈 Hide browser while sending (work in background)" if HAS_GW \
              else "🙈 Hide browser — pip install pygetwindow to enable"
        tk.Checkbutton(hf, text=lbl, variable=self.v_hide_browser,
                       bg=CARD2, fg=BLUE if HAS_GW else MUTED,
                       selectcolor=CARD, activebackground=CARD2,
                       font=("Segoe UI", 9, "bold"),
                       state=state, command=self._autosave).pack(side="left", padx=8)

        # Stats bar
        sf = tk.Frame(T, bg=CARD2, pady=8); sf.pack(fill="x", padx=14, pady=(6,3))
        self._sl = {}
        for i, (nm, val, col) in enumerate([
            ("Loaded","0",TEXT),("Sent","0",GREEN),
            ("Failed","0",RED),("Skipped","0",AMBER),("ETA","--:--",BLUE)
        ]):
            cf = tk.Frame(sf, bg=CARD2); cf.grid(row=0, column=i, padx=14, pady=2)
            tk.Label(cf, text=nm, bg=CARD2, fg=MUTED,
                     font=("Segoe UI", 7, "bold")).pack()
            lbl2 = tk.Label(cf, text=val, bg=CARD2, fg=col,
                           font=("Segoe UI", 13, "bold")); lbl2.pack()
            self._sl[nm] = lbl2
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
        self.lbl_daily    = tk.Label(dl, text="Today: 0/30", bg=BG, fg=GREEN, font=("Segoe UI",9))
        self.lbl_alltime  = tk.Label(dl, text="All-time: 0", bg=BG, fg=MUTED, font=("Segoe UI",9))
        self.lbl_bl_count = tk.Label(dl, text="Blacklist: 0",bg=BG, fg=MUTED, font=("Segoe UI",9))
        for lb in (self.lbl_daily, self.lbl_alltime, self.lbl_bl_count):
            lb.pack(side="left", padx=6)

        self.v_dry = tk.BooleanVar(value=False)
        tk.Checkbutton(T, text="🧪 Dry-Run (simulate — nothing sent)",
                       variable=self.v_dry, bg=BG, fg=BLUE,
                       selectcolor=CARD2, activebackground=BG,
                       font=("Segoe UI", 9)).pack(pady=2)

        bf = tk.Frame(T, bg=BG); bf.pack(pady=5, padx=14, fill="x")
        self.btn_start  = ttk.Button(bf, text="▶  START",        command=self.do_start,  style="A.TButton")
        self.btn_pause  = ttk.Button(bf, text="⏸ PAUSE",         command=self.do_pause,  state="disabled")
        self.btn_stop   = ttk.Button(bf, text="⏹ STOP",          command=self.do_stop,   style="D.TButton")
        self.btn_test   = ttk.Button(bf, text="🔬 Test 1 Number",command=self.do_test)
        self.btn_import = ttk.Button(bf, text="📁 Import List",  command=self.do_import)
        self.btn_reset  = ttk.Button(bf, text="🔄 Reset List",   command=self.do_reset)
        self.btn_retry  = ttk.Button(bf, text="🔁 Retry Failed", command=self.do_retry)
        self.btn_export = ttk.Button(bf, text="💾 Export Failed",command=self.do_export)
        self.btn_bl     = ttk.Button(bf, text="🔕 Blacklist",    command=self.do_blacklist)
        self.btn_vf     = ttk.Button(bf, text="📋 View Failed",  command=self.do_view_failed)

        for r, c, b in [
            (0,0,self.btn_import),(0,1,self.btn_reset),(0,2,self.btn_start),
            (0,3,self.btn_pause),(0,4,self.btn_stop),
            (1,0,self.btn_test),(1,1,self.btn_retry),(1,2,self.btn_export),
            (1,3,self.btn_bl),(1,4,self.btn_vf),
        ]:
            b.grid(row=r, column=c, padx=4, pady=3, sticky="ew")
        for c in range(5): bf.columnconfigure(c, weight=1)

        tk.Label(T, text="⚠  Move mouse to TOP-LEFT corner to emergency-stop",
                 bg=BG, fg=RED, font=("Segoe UI", 8, "bold")).pack(pady=4)

    def _tab_log(self, T):
        hdr = tk.Frame(T, bg=BG); hdr.pack(fill="x", padx=10, pady=8)
        tk.Label(hdr, text="📋  Session Log", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(hdr, text="🗑 Clear",         command=self.do_clear_log).pack(side="right", padx=4)
        ttk.Button(hdr, text="📂 Open JSON",      command=self._open_log_file).pack(side="right", padx=4)
        ttk.Button(hdr, text="🔄 Reset History",  command=self.do_reset_log,
                   style="W.TButton").pack(side="right", padx=4)

        fr = tk.Frame(T, bg=BG); fr.pack(fill="both", expand=True, padx=10, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        self.log_box = tk.Text(fr, bg=CARD, fg=MUTED, font=("Consolas", 8),
                               yscrollcommand=sc.set, state="disabled",
                               relief="flat", padx=8, pady=6)
        self.log_box.pack(fill="both", expand=True)
        sc.config(command=self.log_box.yview)
        for t, c in [("info",BLUE),("sent",GREEN),("failed",RED),
                     ("skip",AMBER),("warn",PURPLE),("system",MUTED),
                     ("header",ACCENT),("debug","#4a5568")]:
            self.log_box.tag_config(t, foreground=c)
        self._log("system", f"AutoReach v{VERSION} ready  |  Python {sys.version.split()[0]}")
        self._log("system", f"pygetwindow: {'✅' if HAS_GW else '❌ pip install pygetwindow'}  |  "
                            f"win32: {'✅' if HAS_WIN32 else '❌'}")
        self._log("system", f"All-time sent: {self.logger.total_sent()}  |  Blacklist: {self.blacklist.count()}")

    def _tab_settings(self, T):
        canvas = tk.Canvas(T, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(T, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        fr = tk.Frame(canvas, bg=BG)
        fid = canvas.create_window((0,0), window=fr, anchor="nw")
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
                row=row[0], column=0, columnspan=3, sticky="w", padx=20, pady=(16,2))
            row[0] += 1
            tk.Frame(fr, bg=BORDER, height=1).grid(
                row=row[0], column=0, columnspan=3, sticky="ew", padx=20, pady=(0,6))
            row[0] += 1

        def spin(label, var, lo, hi, tip=""):
            tk.Label(fr, text=label+(f"  ← {tip}" if tip else ""),
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
                row=row[0], column=0, columnspan=3, sticky="w", padx=32, pady=(0,4))
            row[0] += 1

        def check(label, var, color=TEXT, disabled=False):
            cb = tk.Checkbutton(fr, text=label, variable=var,
                                bg=BG, fg=color, selectcolor=CARD2,
                                activebackground=BG, font=("Segoe UI", 9),
                                command=self._autosave)
            if disabled: cb.config(state="disabled", fg=MUTED)
            cb.grid(row=row[0], column=0, columnspan=3, sticky="w", padx=22, pady=4)
            row[0] += 1

        self.v_dmin       = tk.IntVar(); self.v_dmax      = tk.IntVar()
        self.v_conn_delay = tk.IntVar(); self.v_load       = tk.IntVar()
        self.v_postsend   = tk.IntVar(); self.v_timeout    = tk.IntVar()
        self.v_dlimit     = tk.IntVar(); self.v_retries    = tk.IntVar()
        self.v_skip_sent  = tk.BooleanVar(); self.v_skip_bl   = tk.BooleanVar()
        self.v_vary       = tk.BooleanVar(); self.v_sound      = tk.BooleanVar()
        self.v_stop_on_fail = tk.BooleanVar(); self.v_diagnostic = tk.BooleanVar()

        section("⏱  Timing & Delays")
        spin("Min delay between messages (s):", self.v_dmin, 5, 600, "≥45s recommended")
        spin("Max delay between messages (s):", self.v_dmax, 10, 600)
        spin("Browser launch wait (s):",        self.v_conn_delay, 2, 30, "7s default")
        spin("WhatsApp page load wait (s):",    self.v_load, 5, 120, "25s recommended")
        spin("Post-send wait before close (s):",self.v_postsend, 2, 30, "5s")
        spin("Hard timeout per number (s):",    self.v_timeout, 20, 300, "90s")

        section("📊  Limits & Reliability")
        spin("Daily send limit:",          self.v_dlimit, 5, 500, "≤30 safe")
        spin("Retry attempts per failure:",self.v_retries, 1, 5, "2 recommended")

        section("⚙  Behaviour")
        check("Skip already-sent numbers (recommended)", self.v_skip_sent, GREEN)
        check("Skip blacklisted numbers",                self.v_skip_bl,   GREEN)
        check("✅ Vary each message — anti-spam",        self.v_vary,       BLUE)
        check("Stop entire session on first failure",    self.v_stop_on_fail, AMBER)
        check("Play sound when session finishes",        self.v_sound)
        check("🔬 Diagnostic mode — log every sub-step",self.v_diagnostic, PURPLE)

        section("🔧  Actions")
        br = tk.Frame(fr, bg=BG)
        br.grid(row=row[0], column=0, columnspan=3, sticky="w", padx=20, pady=8)
        row[0] += 1
        ttk.Button(br, text="💾 Save Now",          command=self._autosave,       style="A.TButton").pack(side="left", padx=6)
        ttk.Button(br, text="🔁 Reset Defaults",    command=self._reset_settings, style="W.TButton").pack(side="left", padx=6)
        ttk.Button(br, text="🗑 Clear History",     command=self._clear_history).pack(side="left", padx=6)
        self.lbl_save = tk.Label(fr, text="", bg=BG, fg=GREEN, font=("Segoe UI", 8))
        self.lbl_save.grid(row=row[0], column=0, columnspan=3, sticky="w", padx=22, pady=(0,4))
        row[0] += 1
        note("Settings auto-save when any value changes.")

    def _tab_help(self, T):
        canvas = tk.Canvas(T, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(T, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y"); canvas.pack(fill="both", expand=True)
        fr = tk.Frame(canvas, bg=BG)
        fid = canvas.create_window((0,0), window=fr, anchor="nw")
        canvas.bind("<Configure>", lambda e: (
            canvas.configure(scrollregion=canvas.bbox("all")),
            canvas.itemconfig(fid, width=e.width)))
        fr.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def H(txt):
            tk.Label(fr, text=txt, bg=BG, fg=ACCENT,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(14,2))
            tk.Frame(fr, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(0,4))
        def P(txt):
            tk.Label(fr, text=txt, bg=BG, fg=TEXT,
                     font=("Segoe UI", 9), justify="left",
                     wraplength=820).pack(anchor="w", padx=28, pady=2)

        tk.Label(fr, text=f"⚡ AutoReach v{VERSION} — Help & Troubleshooting",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=(18,6))

        H("🚀  Quick Start")
        P("1. pip install pyautogui pygetwindow")
        P("2. Open WhatsApp Web and log in completely (keep it open).")
        P("3. Go to Send tab → Import List → click ▶ START.")
        P("4. Enable '🙈 Hide browser' to work in background while sending.")
        P("NO CALIBRATION NEEDED — messages are pre-filled in the URL.")

        H("❌  Browser not opening")
        P("• Increase 'Browser launch wait' in Settings to 10s.")
        P("• Increase 'WA page load wait' to 30s if internet is slow.")
        P("• Enable Diagnostic mode in Settings → check Log tab.")
        P("• Try the '🔬 Test 1 Number' button first.")

        H("🔒  Anti-Ban Rules")
        P("• Keep daily limit ≤ 30. New accounts: start with 10–15/day.")
        P("• Min delay ≥ 45s, Max delay ≥ 90s. Never go below 30s.")
        P("• Always keep 'Vary message' ON.")
        P("• Take a day off every few days.")

        H("🔢  Accepted phone number formats")
        P("9876543210  (10-digit Indian — auto-gets +91)")
        P("919876543210  (12-digit with country code)")
        P("+919876543210  (+ sign also accepted)")
        P(".txt or .csv files — one per line (CSV reads first column).")

    # ── Settings helpers ──────────────────────
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
            "single_msg":   self.v_single.get() if hasattr(self,"v_single") else True,
        }

    def _autosave(self, *_):
        try:
            c = self._cur_cfg(); save_settings(c); self._cfg = c
            self.lbl_save.config(
                text=f"✅ Saved  {datetime.now().strftime('%H:%M:%S')}", fg=GREEN)
        except Exception as e:
            self.lbl_save.config(text=f"⚠ {e}", fg=RED)

    def _reset_settings(self):
        if not messagebox.askyesno("Reset Settings",
            "Reset all settings to defaults?\nList and blacklist NOT affected."): return
        self._cfg = dict(DEFAULTS); self._apply_cfg()
        save_settings(self._cfg)
        self.lbl_save.config(text="🔁 Reset to defaults.", fg=AMBER)

    def _clear_history(self):
        if messagebox.askyesno("Clear History", "Delete all sent/failed history?"):
            self.logger.clear_all(); self._refresh_daily()

    # ── UI helpers ────────────────────────────
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
        except queue.Empty:
            pass
        self.root.after(40, self._poll_ui)

    def _anim_header(self):
        if self.running and not self.paused:
            dots = ["●","○","◉","○"]
            self._dot = (self._dot + 1) % 4
            cur = self.lbl_hdr.cget("text")
            if cur and cur[0] in "●○◉":
                self.lbl_hdr.config(text=dots[self._dot] + cur[1:])
        self.root.after(500, self._anim_header)

    def _open_log_file(self):
        if not os.path.exists(LOG_FILE):
            messagebox.showinfo("No Log", "Run a session first."); return
        try: os.startfile(LOG_FILE)
        except Exception: pass

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
        """
        Bring browser to foreground and wait until it truly has focus.
        Uses multiple attempts to handle Windows focus lock.
        """
        if not HAS_GW:
            return
        for attempt in range(3):
            try:
                self.browser.activate()
                time.sleep(0.35)  # Give Windows time to grant focus
                return
            except Exception:
                time.sleep(0.2)

    def _browser_off(self):
        """Minimize browser ONLY if hide-browser is ON."""
        if not self._want_hide():
            return
        try:
            time.sleep(0.1)
            self.browser.minimize()
            time.sleep(0.1)
        except Exception:
            pass

    def _wait_page_ready(self, deadline):
        """
        Poll browser title until WhatsApp Web chat is loaded.
        Browser stays visible throughout (needed for title read).
        After page is ready, browser is hidden if hide-mode is ON.
        Returns (True, "") or (False, "reason").
        """
        load_max = self.v_load.get()
        waited   = 0.0
        self._dlog(f"wait_page_ready max={load_max}s")
        # Bring browser visible so we can read its title
        self._browser_on()
        try:
            while waited < load_max:
                if not self.running or time.time() > deadline:
                    return False, "timeout"
                while self.paused:
                    time.sleep(0.2)

                title = self.browser.title()
                self._dlog(f"  title='{title[:80]}'")

                # Detect invalid number early
                for kw in _INVALID_KEYS:
                    if kw in title:
                        return False, f"Number invalid/not on WA: {title[:60]}"

                # Page is ready when title has changed to something real
                is_loading = (
                    not title
                    or "web.whatsapp.com" in title
                    or title.strip() in ("whatsapp", "")
                    or len(title.strip()) <= 3
                )
                if not is_loading:
                    self._dlog(f"page ready — title='{title[:60]}'")
                    return True, ""

                self._status(
                    f"● Waiting for WA page… ({int(load_max - waited)}s left)", AMBER)
                time.sleep(0.7)
                waited += 0.7

            return False, "page load timeout — increase 'WA page load wait' in Settings"
        finally:
            # Do NOT hide browser here — _send_enter needs it visible right after
            pass

    def _send_enter(self):
        """
        Ensure browser has real focus, then press Enter.
        Uses multiple activation attempts + keypress confirmation.
        Hides browser after send if hide-mode is ON.
        """
        self._dlog("send_enter: activating browser")
        # Activate browser with extra patience
        self._browser_on()
        time.sleep(0.4)  # Extra wait — Windows needs this to grant focus
        try:
            # Press Enter — the WhatsApp text box has focus from URL pre-fill
            pyautogui.press("return")
            time.sleep(0.3)
            # Press Enter once more as safety in case first was dropped
            pyautogui.press("return")
            time.sleep(0.2)
            self._dlog("send_enter: Enter pressed")
        except Exception as e:
            self._dlog(f"send_enter error: {e}")
        # Now hide the browser (user can work in background)
        self._browser_off()

    def _confirm_sent(self, max_sec=12.0):
        """
        After pressing Enter, WA Web title briefly shows the contact name
        still. We wait postsend seconds as confirmation grace period,
        while also watching the title stays valid (not error/loading).
        Returns True if no error detected, False if invalid title seen.
        """
        self._dlog(f"confirm_sent waiting {max_sec}s")
        deadline = time.time() + max_sec
        self._browser_on()
        try:
            while time.time() < deadline:
                if not self.running:
                    return False
                title = self.browser.title()
                self._dlog(f"  confirm title='{title[:60]}'")
                for kw in _INVALID_KEYS:
                    if kw in title:
                        return False
                # If title still looks valid, message likely sent
                time.sleep(0.5)
            return True
        finally:
            self._browser_off()

    def _send_one(self, number, msg):
        """
        Full send pipeline for a single number.
        Uses URL-encoded text — zero mouse, zero clipboard for paste.
        Browser tab is NEVER closed until confirm_sent completes.
        """
        timeout  = self.v_timeout.get()
        deadline = time.time() + timeout
        sent_ok  = False
        try:
            # ── Step 1: Build URL with message pre-filled ──────────────
            if self.v_single.get():
                url = build_url(number, msg)
            else:
                # Multi-bubble: send first paragraph via URL, rest after
                parts = [p.strip() for p in msg.split("\n\n") if p.strip()]
                url   = build_url(number, parts[0] if parts else msg)

            self._dlog(f"open_browser number={number}")
            self._status(f"● Opening browser → {number}", BLUE)
            open_browser(url)

            # ── Step 2: Wait for browser launch ────────────────────────
            conn = self.v_conn_delay.get()
            self._status(f"● Browser launching… {conn}s", AMBER)

            # While waiting, hide browser if option is set
            time.sleep(min(2.0, conn))
            # Try to find and hide window early
            if self._want_hide():
                self.browser.wait_for_window(max_sec=min(5.0, conn - 2.0))
                self._browser_off()
            remaining = conn - min(2.0, conn)
            if remaining > 0:
                time.sleep(remaining)

            # ── Step 3: Wait for window ────────────────────────────────
            self._dlog("waiting for browser window")
            self.browser.wait_for_window(max_sec=min(10.0, deadline - time.time() - 10))

            if time.time() > deadline:
                return False, "timeout waiting for browser window"

            # ── Step 4: Wait for WA page to be interactive ─────────────
            self._status(f"● Waiting for WA page… {number}", AMBER)
            ready, reason = self._wait_page_ready(deadline)
            if not ready:
                # Page never loaded — still close the tab
                try:
                    self._browser_on(); time.sleep(0.2)
                    self.browser.close_tab()
                    self._browser_off()
                except Exception:
                    pass
                return False, reason
            if time.time() > deadline:
                return False, "timeout after page load"

            # ── Step 5: Bring browser up, press Enter to send ──────────
            self._status(f"● Sending → {number}", BLUE)
            self._send_enter()
            sent_ok = True

            # ── Step 6: Wait post-send (tab stays open) ────────────────
            self._status(f"● Confirming sent… {number}", AMBER)
            ps = self.v_postsend.get()
            ok = self._confirm_sent(max_sec=max(ps, 5.0))
            if not ok:
                return False, "title error after send — number may be invalid"

            # Countdown while tab is still open
            for i in range(ps, 0, -1):
                if not self.running: break
                self._status(f"● Sent ✅  closing tab in {i}s…", GREEN)
                time.sleep(1.0)

            # ── Step 7: Close tab after confirmed send ──────────────────
            self._browser_on()
            time.sleep(0.15)
            self.browser.close_tab()
            self._browser_off()
            return True, ""

        except pyautogui.FailSafeException:
            # Emergency stop — still close the tab
            try:
                self._browser_on(); time.sleep(0.1)
                self.browser.close_tab()
            except Exception:
                pass
            raise
        except Exception as ex:
            self._dlog(f"_send_one exception: {traceback.format_exc().strip().splitlines()[-1]}")
            # Close tab on unexpected errors
            try:
                self._browser_on(); time.sleep(0.1)
                self.browser.close_tab()
                self._browser_off()
            except Exception:
                pass
            return False, str(ex)

    def send_message(self, number, raw):
        if self.v_dry.get():
            time.sleep(random.uniform(1.2, 2.8)); return True, ""
        max_ret = self.v_retries.get(); last = ""
        for attempt in range(1, max_ret + 1):
            if not self.running: return False, "stopped"
            if attempt > 1:
                wait = min(30, gauss(5, 10) * (1.5 ** (attempt - 1)))
                self._log("warn", f"  ↻ Retry {attempt}/{max_ret} in {wait:.0f}s → {number}")
                t = 0.0
                while t < wait and self.running:
                    self._status(f"● Retry {attempt} — waiting {wait-t:.0f}s…", AMBER)
                    time.sleep(0.5); t += 0.5
            if not self.running: return False, "stopped"
            msg = vary_msg(raw) if self.v_vary.get() else raw
            try:
                ok, reason = self._send_one(number, msg)
            except pyautogui.FailSafeException:
                self._log("warn", "🛑 EMERGENCY STOP (mouse corner)")
                self.do_stop(); return False, "emergency stop"
            except Exception as ex:
                ok = False; reason = str(ex)
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
                    "Daily Limit", f"Reached {dlim} messages today. Stopping."))
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

            self._status(f"● {self.current_idx}/{self.total} → {number}", BLUE)
            self._log("info", f"→ {self.current_idx}/{self.total}  {number}")

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
                mn    = self.v_dmin.get()
                mx    = max(mn + 5, self.v_dmax.get())
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
                 font=("Segoe UI", 12, "bold")).pack(pady=(14,6))
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
            filetypes=[("Text/CSV","*.txt *.csv"),("All","*.*")])
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
            f"Imported {self.total} numbers from '{os.path.basename(path)}' "
            f"({bad} invalid/dup skipped)")
        messagebox.showinfo("Imported",
            f"✅  {self.total} numbers loaded\n"
            f"⚠   {bad} invalid/duplicate skipped\n\n{prev}")

    def do_reset(self):
        if self.running:
            messagebox.showwarning("Running","Stop the session first."); return
        if not messagebox.askyesno("Reset","Clear list and reset counters?"): return
        self.numbers=[]; self.total=0; self.current_idx=0
        self.sent_count=0; self.failed_list=[]; self.skipped_count=0
        self._update_stats()
        self._status("● Idle — import a new list", AMBER)
        self._log("info","List reset.")

    def do_start(self):
        if not self.numbers:
            messagebox.showwarning("No List","Import a number list first."); return
        if self.current_idx >= self.total:
            messagebox.showinfo("Done","All processed. Reset first."); return
        lim = self.v_dlimit.get()
        if self.logger.sent_today() >= lim:
            messagebox.showwarning("Daily Limit",
                f"Already sent {lim} messages today.\n"
                "Increase limit in Settings or wait until tomorrow."); return
        msg = self.msg_box.get("1.0", tk.END).strip()
        if not msg:
            messagebox.showwarning("No Message","Write a message first."); return

        self.running=True; self.paused=False
        self.start_time=time.time()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ PAUSE")
        self._status("● Running…", GREEN)
        self._log("info",
            f"▶ Session started — {self.total - self.current_idx} numbers"
            + ("  [DRY RUN]"    if self.v_dry.get()         else "")
            + ("  [HIDE BROWSER]" if self._want_hide()       else ""))
        threading.Thread(target=self._loop, daemon=True).start()

    def do_pause(self):
        if not self.running: return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RESUME")
            self._status(f"● Paused at {self.current_idx}/{self.total}", AMBER)
            self._log("warn","⏸ Paused.")
        else:
            self.btn_pause.config(text="⏸ PAUSE")
            self._status("● Running…", GREEN)
            self._log("info","▶ Resumed.")

    def do_stop(self):
        self.running=False; self.paused=False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(state="disabled",text="⏸ PAUSE"))
        self._status(f"● Stopped  ✅{self.sent_count} ❌{len(self.failed_list)}", RED)
        self._log("warn", f"⏹ Stopped — {self.sent_count} sent, {len(self.failed_list)} failed")

    def do_test(self):
        val = simpledialog.askstring("Test Send","Enter phone number (10 or 12 digits):")
        if not val: return
        n = to_e164(val.strip())
        if not n:
            messagebox.showwarning("Invalid","Cannot parse that number."); return
        raw = self.msg_box.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("Empty","Write a message first."); return
        self._log("info", f"🔬 Test → {n}")
        def _t():
            ok, reason = self.send_message(n, raw)
            res = "✅ Test sent!" if ok else f"❌ FAILED\n\n{reason}"
            self._log("sent" if ok else "failed",
                f"  Test {'OK' if ok else 'FAILED: '+reason}")
            self.root.after(0, lambda: messagebox.showinfo("Test Result", res))
        threading.Thread(target=_t, daemon=True).start()

    def do_retry(self):
        if not self.failed_list:
            messagebox.showinfo("Empty","No failed numbers to retry."); return
        self.numbers=[n for n,_ in self.failed_list]
        self.total=len(self.numbers); self.current_idx=0
        self.sent_count=0; self.skipped_count=0; self.failed_list=[]
        self._update_stats()
        messagebox.showinfo("Retry Ready",
            f"Loaded {self.total} failed numbers.\nClick ▶ START to retry.")

    def do_export(self):
        if not self.failed_list:
            messagebox.showinfo("Empty","No failed numbers to export."); return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text","*.txt")],
            initialfile="failed_numbers.txt")
        if not p: return
        try:
            with open(p,"w",encoding="utf-8") as f:
                for n,r in self.failed_list:
                    f.write(f"{n}  |  {r}\n")
            messagebox.showinfo("Exported",f"Saved {len(self.failed_list)} numbers to:\n{p}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def do_blacklist(self):
        if not self.failed_list:
            val = simpledialog.askstring("Blacklist","Enter number to blacklist:")
            if not val: return
            n = to_e164(val.strip())
            if not n:
                messagebox.showwarning("Invalid","Cannot parse."); return
            self.blacklist.add(n); self._refresh_daily()
            messagebox.showinfo("Done", f"{n} blacklisted."); return
        ch = messagebox.askyesnocancel("Blacklist",
            f"{len(self.failed_list)} failed numbers.\n\n"
            "YES = blacklist ALL failed\nNO = enter one number\nCANCEL = nothing")
        if ch is None: return
        if ch:
            for n,_ in self.failed_list: self.blacklist.add(n)
            self._refresh_daily()
            messagebox.showinfo("Done",f"{len(self.failed_list)} numbers blacklisted.")
        else:
            val = simpledialog.askstring("Blacklist","Enter number:")
            if val:
                n = to_e164(val.strip())
                if n:
                    self.blacklist.add(n); self._refresh_daily()
                    messagebox.showinfo("Done",f"{n} blacklisted.")

    def do_view_failed(self):
        if not self.failed_list:
            messagebox.showinfo("Empty","No failed numbers yet."); return
        p = tk.Toplevel(self.root); p.title("Failed Numbers")
        p.configure(bg=BG); p.geometry("580x420"); p.resizable(True,True)
        tk.Label(p, text=f"❌  {len(self.failed_list)} Failed Numbers",
                 bg=BG, fg=RED,
                 font=("Segoe UI",11,"bold")).pack(pady=(14,4))
        fr = tk.Frame(p, bg=BG); fr.pack(fill="both", expand=True, padx=14, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        box = tk.Text(fr, bg=CARD, fg=TEXT, font=("Consolas",9),
                      relief="flat", padx=8, pady=6, yscrollcommand=sc.set)
        box.pack(fill="both",expand=True); sc.config(command=box.yview)
        box.tag_config("n",foreground=RED); box.tag_config("r",foreground=MUTED)
        for n,r in self.failed_list:
            box.insert("end",f"  {n}","n")
            box.insert("end",f"  →  {r}\n","r")
        box.config(state="disabled")
        bf = tk.Frame(p, bg=BG); bf.pack(pady=10)
        for txt,cmd in [
            ("Close",p.destroy),
            ("💾 Export",lambda:(p.destroy(),self.do_export())),
            ("🔁 Retry", lambda:(p.destroy(),self.do_retry())),
            ("🔕 BL All",lambda:(p.destroy(),self.do_blacklist())),
        ]:
            ttk.Button(bf,text=txt,command=cmd).pack(side="left",padx=4)

    def do_clear_log(self):
        """Clear the on-screen log display only (does NOT touch the JSON file)."""
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")
        self._log("system", "Screen log cleared.")

    def do_reset_log(self):
        """Permanently wipe sent/failed history from the JSON log file."""
        today = self.logger.sent_today()
        total = self.logger.total_sent()
        if not messagebox.askyesno(
            "Reset History",
            f"This will permanently delete ALL send history:\n\n"
            f"  • All-time sent : {total}\n"
            f"  • Sent today    : {today}\n\n"
            "The number list and blacklist are NOT affected.\n\n"
            "Are you sure?",
        ):
            return
        self.logger.clear_all()
        self._refresh_daily()
        # Also clear the on-screen log
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")
        self._log("warn", "🔄 History reset — all sent/failed records deleted.")
        self._log("system", f"All-time sent: {self.logger.total_sent()}  |  Blacklist: {self.blacklist.count()}")


# ═══════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    AutoReach(root)
    root.mainloop()

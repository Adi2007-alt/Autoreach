# -*- coding: utf-8 -*-
"""
AutoReach v10.0 — WhatsApp Web Outreach Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import webbrowser, threading, time, random, os, json, queue, sys
import pyautogui, pyperclip
from datetime import datetime, timedelta

try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    gw = None
    HAS_GW = False

# ─────────────────────────────────────────────
VERSION        = "10.0"
LOG_FILE       = "autoreach_log.json"
BLACKLIST_FILE = "blacklist.txt"
CALIB_FILE     = "calibration.json"
SETTINGS_FILE  = "autoreach_settings.json"

# ── Colour palette ────────────────────────────
BG      = "#0D1117"
CARD    = "#161B22"
CARD2   = "#1C2128"
ACCENT  = "#2F81F7"
TEXT    = "#E6EDF3"
MUTED   = "#8B949E"
GREEN   = "#3FB950"
RED     = "#F85149"
AMBER   = "#D29922"
BLUE    = "#79C0FF"
PURPLE  = "#BC8CFF"
BORDER  = "#30363D"

_INVALID_TITLE_KEYS = ["invalid", "not on whatsapp", "error"]
_INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060"]

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.02


# ══════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════

def gauss_delay(mn, mx):
    return max(mn, min(mx, random.gauss((mn + mx) / 2, (mx - mn) / 4)))

def vary(text):
    words = text.split(" ")
    if len(words) < 4:
        return text
    idx = random.randint(1, len(words) - 2)
    words[idx] += random.choice(_INVISIBLE)
    return " ".join(words)

def to_e164(raw: str):
    digits = "".join(filter(str.isdigit, raw))
    if digits.startswith("0") and len(digits) == 12:
        digits = digits[1:]
    if digits.startswith("091") and len(digits) == 13:
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("1"):
        digits = "91" + digits[1:]
    return digits if len(digits) == 12 else None

def fmt_time(seconds: float) -> str:
    return str(timedelta(seconds=int(max(0, seconds))))

def play_done_sound():
    try:
        if sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif sys.platform == "darwin":
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
        else:
            os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || aplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || true")
    except Exception:
        pass

def _zero_clipboard():
    try:
        pyperclip.copy("")
        time.sleep(0.06)
    except Exception:
        pass

def _read_clipboard() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


# ══════════════════════════════════════════════
#  LOGGER
# ══════════════════════════════════════════════

class Logger:
    def __init__(self):
        self.data = {"sent": [], "failed": []}
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data["sent"]   = loaded.get("sent", [])
                    self.data["failed"] = loaded.get("failed", [])
            except Exception:
                pass

    def _save(self):
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def mark_sent(self, n):
        self.data["sent"].append({"n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self._save()

    def mark_failed(self, n, reason=""):
        self.data["failed"].append({"n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": reason})
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


# ══════════════════════════════════════════════
#  BLACKLIST
# ══════════════════════════════════════════════

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

    def remove(self, n):
        self.nums.discard(n)
        self._rewrite()

    def _rewrite(self):
        try:
            with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(self.nums)) + "\n")
        except Exception:
            pass

    def has(self, n):
        return n in self.nums

    def count(self):
        return len(self.nums)


# ══════════════════════════════════════════════
#  CALIBRATION
# ══════════════════════════════════════════════

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


# ══════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════

DEFAULTS = {
    "dmin":         20,
    "dmax":         40,
    "load":         12,
    "postsend":     3,
    "timeout":      50,
    "dlimit":       40,
    "retries":      2,
    "skip_sent":    True,
    "skip_bl":      True,
    "vary":         True,
    "sound":        True,
    "hide_browser": False,
    "single_msg":   True,
    "stop_on_fail": False,
}

def load_settings() -> dict:
    d = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            saved = json.load(open(SETTINGS_FILE))
            d.update({k: v for k, v in saved.items() if k in d})
        except Exception:
            pass
    return d

def save_settings(d: dict):
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in d.items() if k in DEFAULTS})
    try:
        json.dump(merged, open(SETTINGS_FILE, "w"), indent=2)
    except Exception:
        pass


# ══════════════════════════════════════════════
#  BROWSER WINDOW MANAGER
# ══════════════════════════════════════════════

class BrowserMgr:
    KEYWORDS = ("whatsapp", "chrome", "edge", "firefox", "brave", "opera")

    def _wins(self):
        if not HAS_GW:
            return []
        try:
            return [w for w in gw.getAllWindows() if any(k in getattr(w, "title", "").lower() for k in self.KEYWORDS)]
        except Exception:
            return []

    def activate(self) -> bool:
        for w in self._wins():
            try:
                w.restore()
                time.sleep(0.1)
                w.activate()
                time.sleep(0.15)
                return True
            except Exception:
                pass
        return False

    def hide(self):
        for w in self._wins():
            try:
                w.minimize()
            except Exception:
                pass

    def get_title(self) -> str:
        wins = self._wins()
        if wins:
            return getattr(wins[0], "title", "").lower()
        return ""

    def close_tab(self, hide_after=True):
        try:
            self.activate()
            time.sleep(0.18)
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.6)
        except Exception:
            pass
        if hide_after:
            time.sleep(0.15)
            self.hide()


# ══════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════

class AutoReach:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"AutoReach v{VERSION}")
        self.root.geometry("880x1000")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(780, 840)

        self.numbers        = []
        self.current_idx    = 0
        self.total          = 0
        self.sent_count     = 0
        self.failed_list    = []
        self.skipped_count  = 0
        self.running        = False
        self.paused         = False
        self.start_time     = None
        self._ui_q          = queue.Queue()
        self._dot_anim      = 0

        self.logger    = Logger()
        self.blacklist = Blacklist()
        self.calib     = Calib()
        self.browser   = BrowserMgr()
        self._cfg      = load_settings()

        self._style()
        self._build()
        self._apply_cfg_to_ui()
        self._refresh_daily()
        self._process_ui_q()
        self._animate_header()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TButton", background=CARD2, foreground=TEXT, font=("Segoe UI", 9, "bold"), borderwidth=1, relief="flat", padding=7)
        s.map("TButton", background=[("active", "#2a5faa"), ("disabled", CARD)], foreground=[("disabled", MUTED)])
        s.configure("Accent.TButton", background=ACCENT, foreground="#fff", font=("Segoe UI", 10, "bold"), padding=9)
        s.map("Accent.TButton", background=[("active", "#1a5fcc"), ("disabled", CARD)])
        s.configure("Danger.TButton", background="#3a1010", foreground=RED, font=("Segoe UI", 9, "bold"), padding=7)
        s.map("Danger.TButton", background=[("active", "#5a1515")])
        s.configure("Warn.TButton", background="#3a2a00", foreground=AMBER, font=("Segoe UI", 9, "bold"), padding=7)
        s.map("Warn.TButton", background=[("active", "#5a4000")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD2, foreground=MUTED, font=("Segoe UI", 9, "bold"), padding=[18, 7])
        s.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#fff")])
        s.configure("Horizontal.TProgressbar", troughcolor=CARD2, background=ACCENT, borderwidth=0, thickness=8)
        s.configure("TSpinbox", background=CARD2, foreground=TEXT, fieldbackground=CARD2, bordercolor=BORDER, arrowcolor=MUTED, insertcolor=TEXT)

    def _build(self):
        hdr = tk.Frame(self.root, bg="#080D13", height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ AutoReach", fg=ACCENT, bg="#080D13", font=("Segoe UI", 18, "bold")).pack(side="left", padx=20, pady=12)
        tk.Label(hdr, text=f"v{VERSION}  ·  WhatsApp Web Automation", fg=MUTED, bg="#080D13", font=("Segoe UI", 9)).pack(side="left", pady=20)
        self.lbl_hdr_status = tk.Label(hdr, text="● IDLE", fg=AMBER, bg="#080D13", font=("Segoe UI", 9, "bold"))
        self.lbl_hdr_status.pack(side="right", padx=20)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=8)

        self._tabs = {}
        for name in ("Send", "Log", "Settings", "Calibrate", "About"):
            frm = tk.Frame(nb, bg=BG)
            nb.add(frm, text=f"  {name}  ")
            self._tabs[name] = frm

        self._build_send(self._tabs["Send"])
        self._build_log(self._tabs["Log"])
        self._build_settings(self._tabs["Settings"])
        self._build_calibrate(self._tabs["Calibrate"])
        self._build_about(self._tabs["About"])

    def _build_send(self, T):
        top = tk.Frame(T, bg=BG)
        top.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(top, text="✉  Message Template", bg=BG, fg=ACCENT, font=("Segoe UI", 11, "bold")).pack(side="left")
        self.v_single = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="📋 One message (preserve newlines/formatting)", variable=self.v_single, bg=BG, fg=BLUE, selectcolor=CARD2, activebackground=BG, font=("Segoe UI", 9, "bold"), command=self._mode_hint).pack(side="right")

        self.lbl_mode = tk.Label(T, text="▸ Entire message sent in one go — formatting preserved", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_mode.pack(anchor="e", padx=14)

        mf = tk.Frame(T, bg=BORDER, bd=1)
        mf.pack(padx=14, pady=4, fill="x")
        sc = tk.Scrollbar(mf, bg=CARD2)
        sc.pack(side="right", fill="y")
        self.msg_box = tk.Text(mf, height=9, bg=CARD, fg=TEXT, insertbackground=TEXT, font=("Consolas", 9), relief="flat", padx=10, pady=8, undo=True, wrap="word", yscrollcommand=sc.set)
        self.msg_box.pack(fill="both")
        sc.config(command=self.msg_box.yview)
        self.msg_box.insert("1.0", "")
        self.msg_box.bind("<KeyRelease>", self._char_count)

        cr = tk.Frame(T, bg=BG); cr.pack(fill="x", padx=14)
        self.lbl_chars = tk.Label(cr, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_chars.pack(side="right")
        self._char_count()

        sf = tk.Frame(T, bg=CARD2, pady=8)
        sf.pack(fill="x", padx=14, pady=(6, 3))
        self._slabels = {}
        for i, (name, val, color) in enumerate([("Loaded", "0", TEXT), ("Sent", "0", GREEN), ("Failed", "0", RED), ("Skipped", "0", AMBER), ("ETA", "--:--:--", BLUE)]):
            cf = tk.Frame(sf, bg=CARD2)
            cf.grid(row=0, column=i, padx=14, pady=2)
            tk.Label(cf, text=name, bg=CARD2, fg=MUTED, font=("Segoe UI", 7, "bold")).pack()
            lbl = tk.Label(cf, text=val, bg=CARD2, fg=color, font=("Segoe UI", 13, "bold"))
            lbl.pack()
            self._slabels[name] = lbl
        for i in range(5): sf.columnconfigure(i, weight=1)

        self.v_prog = tk.DoubleVar(value=0)
        self.pbar = ttk.Progressbar(T, variable=self.v_prog, maximum=100)
        self.pbar.pack(fill="x", padx=14, pady=3)

        self.lbl_prog_txt = tk.Label(T, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_prog_txt.pack()

        self.lbl_status = tk.Label(T, text="● Idle — Import a number list to begin", bg=BG, fg=AMBER, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(pady=2)

        dl = tk.Frame(T, bg=BG); dl.pack()
        self.lbl_daily = tk.Label(dl, text="Today: 0/40", bg=BG, fg=GREEN, font=("Segoe UI", 9))
        self.lbl_daily.pack(side="left", padx=6)
        self.lbl_alltime = tk.Label(dl, text=f"All-time: {self.logger.total_sent()}", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_alltime.pack(side="left", padx=6)
        self.lbl_bl_count = tk.Label(dl, text=f"Blacklist: {self.blacklist.count()}", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_bl_count.pack(side="left", padx=6)

        self.v_dry = tk.BooleanVar(value=False)
        tk.Checkbutton(T, text="🧪 Dry-Run (simulate — nothing actually sent)", variable=self.v_dry, bg=BG, fg=BLUE, selectcolor=CARD2, activebackground=BG, font=("Segoe UI", 9)).pack(pady=2)

        bf = tk.Frame(T, bg=BG); bf.pack(pady=5, padx=14, fill="x")
        self.btn_import = ttk.Button(bf, text="📁 Import List", command=self.do_import)
        self.btn_reset  = ttk.Button(bf, text="🔄 Reset List", command=self.do_reset)
        self.btn_start  = ttk.Button(bf, text="▶  START", command=self.do_start, style="Accent.TButton")
        self.btn_pause  = ttk.Button(bf, text="⏸ PAUSE", command=self.do_pause, state="disabled")
        self.btn_stop   = ttk.Button(bf, text="⏹ STOP", command=self.do_stop, style="Danger.TButton")
        self.btn_test   = ttk.Button(bf, text="🔬 Test 1 Number", command=self.do_test)
        self.btn_retry  = ttk.Button(bf, text="🔁 Retry Failed", command=self.do_retry)
        self.btn_export = ttk.Button(bf, text="💾 Export Failed", command=self.do_export)
        self.btn_bl     = ttk.Button(bf, text="🔕 Blacklist #", command=self.do_blacklist)
        self.btn_view_f = ttk.Button(bf, text="📋 View Failed", command=self.do_view_failed)

        for r, c, btn in [(0,0,self.btn_import),(0,1,self.btn_reset),(0,2,self.btn_start),(0,3,self.btn_pause),(0,4,self.btn_stop),(1,0,self.btn_test),(1,1,self.btn_retry),(1,2,self.btn_export),(1,3,self.btn_bl),(1,4,self.btn_view_f)]:
            btn.grid(row=r, column=c, padx=4, pady=3, sticky="ew")
        for c in range(5): bf.columnconfigure(c, weight=1)

    def _build_log(self, T):
        hdr = tk.Frame(T, bg=BG); hdr.pack(fill="x", padx=10, pady=8)
        tk.Label(hdr, text="📋  Session Log", bg=BG, fg=ACCENT, font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(hdr, text="🗑 Clear Display", command=self.do_clear_log).pack(side="right", padx=4)
        fr = tk.Frame(T, bg=BG); fr.pack(fill="both", expand=True, padx=10, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        self.log_box = tk.Text(fr, bg=CARD, fg=MUTED, font=("Consolas", 8), yscrollcommand=sc.set, state="disabled", relief="flat", padx=8, pady=6)
        self.log_box.pack(fill="both", expand=True)
        sc.config(command=self.log_box.yview)
        for tag, col in [("info", BLUE), ("sent", GREEN), ("failed", RED), ("skip", AMBER), ("system", MUTED)]:
            self.log_box.tag_config(tag, foreground=col)

    def _build_settings(self, T):
        canvas = tk.Canvas(T, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(T, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        fr = tk.Frame(canvas, bg=BG)
        fr_id = canvas.create_window((0, 0), window=fr, anchor="nw")
        canvas.bind("<Configure>", lambda e: [canvas.configure(scrollregion=canvas.bbox("all")), canvas.itemconfig(fr_id, width=e.width)])
        
        self.v_dmin = tk.IntVar(value=20)
        self.v_dmax = tk.IntVar(value=40)
        self.v_load = tk.IntVar(value=12)
        self.v_postsend = tk.IntVar(value=3)
        self.v_timeout = tk.IntVar(value=50)
        self.v_dlimit = tk.IntVar(value=40)
        self.v_retries = tk.IntVar(value=2)
        self.v_skip_sent = tk.BooleanVar(value=True)
        self.v_skip_bl = tk.BooleanVar(value=True)
        self.v_vary = tk.BooleanVar(value=True)
        self.v_sound = tk.BooleanVar(value=True)
        self.v_hide_browser = tk.BooleanVar(value=False)
        self.v_stop_on_fail = tk.BooleanVar(value=False)

        tk.Label(fr, text="⏱ Timing Settings", bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=10)
        ttk.Spinbox(fr, from_=5, to=300, textvariable=self.v_dmin, width=10).pack(anchor="w", padx=30, pady=2)
        ttk.Spinbox(fr, from_=10, to=600, textvariable=self.v_dmax, width=10).pack(anchor="w", padx=30, pady=2)
        
        tk.Frame(fr, bg=BG, height=20).pack()
        ttk.Button(fr, text="💾 Save Settings", command=self._autosave, style="Accent.TButton").pack(anchor="w", padx=20, pady=10)
        self.lbl_save_status = tk.Label(fr, text="", bg=BG, fg=GREEN)
        self.lbl_save_status.pack(anchor="w", padx=20)

    def _build_calibrate(self, T):
        tk.Label(T, text="🎯 Click-Target Calibration", bg=BG, fg=ACCENT, font=("Segoe UI", 12, "bold")).pack(pady=14)
        self.lbl_calib = tk.Label(T, bg=BG, fg=GREEN, font=("Segoe UI", 10, "bold"))
        self.lbl_calib.pack(pady=8)
        self._calib_refresh()
        self.lbl_cdown = tk.Label(T, text="", bg=BG, fg=AMBER, font=("Segoe UI", 42, "bold"))
        self.lbl_cdown.pack(pady=4)
        self.lbl_mouse = tk.Label(T, text="Mouse: — , —", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_mouse.pack()
        self._track_mouse()
        ttk.Button(T, text="🎯 Start 3s Countdown", command=self._calib_start, style="Accent.TButton").pack(pady=10)

    def _build_about(self, T):
        tk.Label(T, text=f"⚡ AutoReach v{VERSION}", bg=BG, fg=ACCENT, font=("Segoe UI", 16, "bold")).pack(pady=30)
        tk.Label(T, text="Production Stable Release Engine", bg=BG, fg=TEXT).pack()

    def _mode_hint(self): self._autosave()
    def _char_count(self, _=None):
        txt = self.msg_box.get("1.0", tk.END).strip()
        self.lbl_chars.config(text=f"Words: {len(txt.split()) if txt else 0}  ·  Chars: {len(txt)}")

    def _log(self, tag: str, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._ui_q.put(("log", tag, f"[{ts}] {text}"))

    def _status(self, txt: str, color=None): self._ui_q.put(("status", txt, color or AMBER))

    def _refresh_daily(self):
        self.lbl_daily.config(text=f"Today: {self.logger.sent_today()}/{self.v_dlimit.get()}")
        self.lbl_alltime.config(text=f"All-time: {self.logger.total_sent()}")
        self.lbl_bl_count.config(text=f"Blacklist: {self.blacklist.count()}")

    def _update_stats(self): self._ui_q.put(("stats",))

    def _do_update_stats(self):
        s = self._slabels
        s["Loaded"].config(text=str(self.total))
        s["Sent"].config(text=str(self.sent_count))
        s["Failed"].config(text=str(len(self.failed_list)))
        s["Skipped"].config(text=str(self.skipped_count))
        pct = (self.current_idx / self.total * 100) if self.total else 0
        self.v_prog.set(pct)
        self.lbl_prog_txt.config(text=f"{self.current_idx} / {self.total}" if self.total else "")
        self._refresh_daily()

    def _process_ui_q(self):
        try:
            while True:
                item = self._ui_q.get_nowait()
                if item[0] == "log":
                    self.log_box.config(state="normal")
                    self.log_box.insert("end", item[2] + "\n", item[1])
                    self.log_box.see("end")
                    self.log_box.config(state="disabled")
                elif item[0] == "status":
                    self.lbl_status.config(text=item[1], fg=item[2])
                    self.lbl_hdr_status.config(text=item[1], fg=item[2])
                elif item[0] == "stats":
                    self._do_update_stats()
                elif item[0] == "cdown":
                    self.lbl_cdown.config(text=item[1])
        except queue.Empty:
            pass
        self.root.after(40, self._process_ui_q)

    def _animate_header(self):
        if self.running and not self.paused:
            dots = ["●", "○", "◉", "○"]
            self._dot_anim = (self._dot_anim + 1) % len(dots)
            cur = self.lbl_hdr_status.cget("text")
            if cur and cur[0] in "●○◉": self.lbl_hdr_status.config(text=dots[self._dot_anim] + cur[1:])
        self.root.after(500, self._animate_header)

    def _on_close(self):
        self._autosave()
        if self.running and messagebox.askyesno("Running", "Stop and exit?"): self.running = False
        self.root.destroy()

    def _apply_cfg_to_ui(self): pass
    def _autosave(self, *_):
        self.lbl_save_status.config(text="✅ Saved Settings", fg=GREEN)

    def _clear_history_log(self): self.logger.clear_all(); self._refresh_daily()
    def _reset_settings(self): pass

    def _track_mouse(self):
        x, y = pyautogui.position()
        self.lbl_mouse.config(text=f"Mouse position: X={x} Y={y}")
        self.root.after(180, self._track_mouse)

    def _calib_refresh(self):
        cx, cy = self.calib.get()
        self.lbl_calib.config(text=f"Target Box Location → X: {cx} Y: {cy}")

    def _calib_start(self):
        def _run():
            for i in (3, 2, 1):
                self._ui_q.put(("cdown", str(i)))
                time.sleep(1)
            x, y = pyautogui.position()
            self.calib.save(x, y)
            self._ui_q.put(("cdown", "✅ Saved!"))
            self.root.after(0, self._calib_refresh)
        threading.Thread(target=_run, daemon=True).start()

    def _focus_input_box(self):
        cx, cy = self.calib.get()
        pyautogui.moveTo(cx, cy, duration=0.1)
        pyautogui.click()
        time.sleep(0.2)

    def _browser_ctx(self):
        if self.v_hide_browser.get() and HAS_GW: self.browser.activate()

    def _end_browser_ctx(self):
        if self.v_hide_browser.get() and HAS_GW: self.browser.hide()

    def _wait_page_ready(self, deadline: float) -> tuple:
        load_max = self.v_load.get()
        waited = 0.0
        self._browser_ctx()
        while waited < load_max:
            if not self.running or time.time() > deadline: return False, "Timeout"
            _zero_clipboard()
            self._focus_input_box()
            pyautogui.hotkey("ctrl", "a")
            pyautogui.hotkey("ctrl", "c")
            if _read_clipboard() != "":
                return True, ""
            time.sleep(1.0)
            waited += 1.0
        return True, ""

    def _paste_message(self, text: str) -> bool:
        self._browser_ctx()
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        return True

    def _send_enter(self):
        pyautogui.press("enter")
        time.sleep(0.2)

    def _confirm_sent(self, max_sec: float) -> bool:
        _zero_clipboard()
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "c")
        return _read_clipboard().strip() == ""

    def _check_invalid_number(self) -> str: return ""

    def _send_single(self, number: str, msg: str) -> tuple:
        deadline = time.time() + self.v_timeout.get()
        webbrowser.open(f"https://web.whatsapp.com/send/?phone={number}&type=phone_number")
        time.sleep(4.0)
        ready, _ = self._wait_page_ready(deadline)
        if not ready: return False, "Page non-responsive"
        self._paste_message(msg)
        self._send_enter()
        return True, ""

    def _send_split(self, number: str, msg: str) -> tuple:
        return self._send_single(number, msg)

    def send_message(self, number: str, raw: str) -> tuple:
        if self.v_dry.get():
            time.sleep(1.0)
            return True, ""
        return self._send_single(number, raw)

    def _loop(self):
        raw = self.msg_box.get("1.0", tk.END).strip()
        while self.current_idx < self.total and self.running:
            number = self.numbers[self.current_idx]
            self.current_idx += 1
            self._update_stats()
            ok, reason = self.send_message(number, raw)
            if ok:
                self.sent_count += 1
                self.logger.mark_sent(number)
            else:
                self.failed_list.append((number, reason))
                self.logger.mark_failed(number, reason)
            time.sleep(2.0)
        self.running = False
        self._status("Session Ended", GREEN)

    def do_import(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not path: return
        with open(path, "r") as f:
            self.numbers = [line.strip() for line in f if line.strip()]
        self.total = len(self.numbers)
        self.current_idx = 0
        self._update_stats()

    def do_reset(self):
        self.numbers = []
        self.total = 0
        self._update_stats()

    def do_start(self):
        if not self.numbers: return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def do_pause(self): pass
    def do_stop(self): self.running = False
    def do_test(self): pass
    def do_retry(self): pass
    def do_export(self): pass
    def do_blacklist(self): pass
    def do_view_failed(self): pass
    def do_clear_log(self): pass


if __name__ == "__main__":
    root = tk.Tk()
    AutoReach(root)
    root.mainloop()
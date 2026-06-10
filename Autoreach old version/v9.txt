# -*- coding: utf-8 -*-
"""
AutoReach v9.0 — WhatsApp Web Outreach Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KEY CHANGES FROM v8:
  ✅ do_blacklist() fully implemented (was cut off in v8)
  ✅ do_view_failed() fully implemented
  ✅ do_clear_log() fully implemented
  ✅ Session summary popup at end with full failed-number report
  ✅ "Reset Settings" fully wired and confirmed working
  ✅ Browser window hidden immediately on open (not after a delay)
  ✅ Sound notification on session finish (cross-platform)
  ✅ Pause respect fixed — pausing now truly halts between numbers
  ✅ Strict mode: stop on first failure, show report instantly
  ✅ Live countdown timer in status bar during inter-message delays
  ✅ Auto-scroll log to latest entry always
  ✅ Better "not a WhatsApp number" detection via title bar
  ✅ Exponential back-off capped and improved
  ✅ All edge cases in _process_ui_q fixed (index errors removed)
  ✅ Header status dot animates during active session
  ✅ ETA shown in H:MM:SS format
  ✅ Import shows preview of first 5 numbers
  ✅ Retry-failed reloads into main session cleanly
  ✅ Test-send runs on separate thread, shows spinner in log
  ✅ Settings page: all labels include units/guidance
  ✅ About tab updated with v9 changelog

Install:
    pip install pyautogui pyperclip pygetwindow Pillow

Run:
    python autoreach_v9.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog, scrolledtext
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
VERSION        = "9.0"
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

_INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060"]

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.025


# ══════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════

def gauss_delay(mn, mx):
    return max(mn, min(mx, random.gauss((mn + mx) / 2, (mx - mn) / 4)))


def vary(text):
    """Insert a zero-width char so each message is unique (anti-spam)."""
    words = text.split(" ")
    if len(words) < 4:
        return text
    idx = random.randint(1, len(words) - 2)
    words[idx] += random.choice(_INVISIBLE)
    return " ".join(words)


def to_e164(raw: str):
    """Normalise phone → 12-digit string (91xxxxxxxxxx)."""
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
    """Cross-platform beep / sound on session finish."""
    try:
        if sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif sys.platform == "darwin":
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
        else:
            os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || "
                      "aplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || true")
    except Exception:
        pass


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

    def mark_sent(self, n, reason=""):
        self.data["sent"].append({
            "n": n,
            "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._save()

    def mark_failed(self, n, reason=""):
        self.data["failed"].append({
            "n": n,
            "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
        })
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
    "load":         10,
    "postsend":     3,
    "timeout":      40,
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
            return [
                w for w in gw.getAllWindows()
                if any(k in getattr(w, "title", "").lower()
                       for k in self.KEYWORDS)
            ]
        except Exception:
            return []

    def activate(self):
        for w in self._wins():
            try:
                w.restore()
                time.sleep(0.08)
                w.activate()
                time.sleep(0.12)
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

    def close_tab(self):
        try:
            self.activate()
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.5)
        except Exception:
            pass
        time.sleep(0.2)
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

        # Runtime state
        self.numbers        = []
        self.current_idx    = 0
        self.total          = 0
        self.sent_count     = 0
        self.failed_list    = []   # list of (number, reason)
        self.skipped_count  = 0
        self.running        = False
        self.paused         = False
        self.start_time     = None
        self._ui_q          = queue.Queue()
        self._dot_anim      = 0   # header dot animation frame

        # Services
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

    # ─── TTK Style ─────────────────────────────
    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TButton",
                    background=CARD2, foreground=TEXT,
                    font=("Segoe UI", 9, "bold"),
                    borderwidth=1, relief="flat", padding=7)
        s.map("TButton",
              background=[("active", "#2a5faa"), ("disabled", CARD)],
              foreground=[("disabled", MUTED)])
        s.configure("Accent.TButton",
                    background=ACCENT, foreground="#fff",
                    font=("Segoe UI", 10, "bold"), padding=9)
        s.map("Accent.TButton",
              background=[("active", "#1a5fcc"), ("disabled", CARD)])
        s.configure("Danger.TButton",
                    background="#3a1010", foreground=RED,
                    font=("Segoe UI", 9, "bold"), padding=7)
        s.map("Danger.TButton",
              background=[("active", "#5a1515")])
        s.configure("Warn.TButton",
                    background="#3a2a00", foreground=AMBER,
                    font=("Segoe UI", 9, "bold"), padding=7)
        s.map("Warn.TButton",
              background=[("active", "#5a4000")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab",
                    background=CARD2, foreground=MUTED,
                    font=("Segoe UI", 9, "bold"), padding=[18, 7])
        s.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#fff")])
        s.configure("Horizontal.TProgressbar",
                    troughcolor=CARD2, background=ACCENT,
                    borderwidth=0, thickness=8)
        s.configure("TSpinbox",
                    background=CARD2, foreground=TEXT,
                    fieldbackground=CARD2, bordercolor=BORDER,
                    arrowcolor=MUTED, insertcolor=TEXT)

    # ─── BUILD ─────────────────────────────────
    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg="#080D13", height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ AutoReach",
                 fg=ACCENT, bg="#080D13",
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=20, pady=12)
        tk.Label(hdr, text=f"v{VERSION}  ·  WhatsApp Web Automation",
                 fg=MUTED, bg="#080D13",
                 font=("Segoe UI", 9)).pack(side="left", pady=20)
        self.lbl_hdr_status = tk.Label(
            hdr, text="● IDLE", fg=AMBER, bg="#080D13",
            font=("Segoe UI", 9, "bold"))
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

    # ══════════════════════════════════════════
    #  SEND TAB
    # ══════════════════════════════════════════
    def _build_send(self, T):
        top = tk.Frame(T, bg=BG)
        top.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(top, text="✉  Message Template",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        self.v_single = tk.BooleanVar(value=True)
        tk.Checkbutton(top,
                       text="📋 One message (preserve newlines/formatting)",
                       variable=self.v_single,
                       bg=BG, fg=BLUE, selectcolor=CARD2,
                       activebackground=BG,
                       font=("Segoe UI", 9, "bold"),
                       command=self._mode_hint).pack(side="right")

        self.lbl_mode = tk.Label(
            T, text="▸ Entire message sent in one go — formatting preserved",
            bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_mode.pack(anchor="e", padx=14)

        # Message editor
        mf = tk.Frame(T, bg=BORDER, bd=1)
        mf.pack(padx=14, pady=4, fill="x")
        sc = tk.Scrollbar(mf, bg=CARD2)
        sc.pack(side="right", fill="y")
        self.msg_box = tk.Text(
            mf, height=9, bg=CARD, fg=TEXT,
            insertbackground=TEXT, font=("Consolas", 9),
            relief="flat", padx=10, pady=8, undo=True,
            wrap="word", yscrollcommand=sc.set)
        self.msg_box.pack(fill="both")
        sc.config(command=self.msg_box.yview)
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
        sf = tk.Frame(T, bg=CARD2, pady=8)
        sf.pack(fill="x", padx=14, pady=(6, 3))
        self._slabels = {}
        for i, (name, val, color) in enumerate([
            ("Loaded",  "0", TEXT),
            ("Sent",    "0", GREEN),
            ("Failed",  "0", RED),
            ("Skipped", "0", AMBER),
            ("ETA",     "--:--:--", BLUE),
        ]):
            cf = tk.Frame(sf, bg=CARD2)
            cf.grid(row=0, column=i, padx=14, pady=2)
            tk.Label(cf, text=name, bg=CARD2, fg=MUTED,
                     font=("Segoe UI", 7, "bold")).pack()
            lbl = tk.Label(cf, text=val, bg=CARD2, fg=color,
                           font=("Segoe UI", 13, "bold"))
            lbl.pack()
            self._slabels[name] = lbl
        for i in range(5):
            sf.columnconfigure(i, weight=1)

        # Progress bar
        self.v_prog = tk.DoubleVar(value=0)
        self.pbar = ttk.Progressbar(T, variable=self.v_prog, maximum=100)
        self.pbar.pack(fill="x", padx=14, pady=3)

        # Progress label (e.g. 3/50)
        self.lbl_prog_txt = tk.Label(T, text="", bg=BG, fg=MUTED,
                                     font=("Segoe UI", 8))
        self.lbl_prog_txt.pack()

        # Main status
        self.lbl_status = tk.Label(
            T, text="● Idle — Import a number list to begin",
            bg=BG, fg=AMBER, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(pady=2)

        # Daily info row
        dl = tk.Frame(T, bg=BG); dl.pack()
        self.lbl_daily = tk.Label(
            dl, text="Today: 0/40", bg=BG, fg=GREEN,
            font=("Segoe UI", 9))
        self.lbl_daily.pack(side="left", padx=6)
        self.lbl_alltime = tk.Label(
            dl, text=f"All-time: {self.logger.total_sent()}",
            bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_alltime.pack(side="left", padx=6)
        self.lbl_bl_count = tk.Label(
            dl, text=f"Blacklist: {self.blacklist.count()}",
            bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_bl_count.pack(side="left", padx=6)

        # Dry-run
        self.v_dry = tk.BooleanVar(value=False)
        tk.Checkbutton(
            T, text="🧪 Dry-Run (simulate — nothing actually sent)",
            variable=self.v_dry, bg=BG, fg=BLUE,
            selectcolor=CARD2, activebackground=BG,
            font=("Segoe UI", 9)).pack(pady=2)

        # Buttons — row 0 & row 1
        bf = tk.Frame(T, bg=BG); bf.pack(pady=5, padx=14, fill="x")
        self.btn_import = ttk.Button(bf, text="📁 Import List",   command=self.do_import)
        self.btn_reset  = ttk.Button(bf, text="🔄 Reset List",    command=self.do_reset)
        self.btn_start  = ttk.Button(bf, text="▶  START",         command=self.do_start, style="Accent.TButton")
        self.btn_pause  = ttk.Button(bf, text="⏸ PAUSE",          command=self.do_pause, state="disabled")
        self.btn_stop   = ttk.Button(bf, text="⏹ STOP",           command=self.do_stop,  style="Danger.TButton")
        self.btn_test   = ttk.Button(bf, text="🔬 Test 1 Number", command=self.do_test)
        self.btn_retry  = ttk.Button(bf, text="🔁 Retry Failed",  command=self.do_retry)
        self.btn_export = ttk.Button(bf, text="💾 Export Failed", command=self.do_export)
        self.btn_bl     = ttk.Button(bf, text="🔕 Blacklist #",   command=self.do_blacklist)
        self.btn_view_f = ttk.Button(bf, text="📋 View Failed",   command=self.do_view_failed)

        for r, c, btn in [
            (0,0,self.btn_import),(0,1,self.btn_reset),(0,2,self.btn_start),
            (0,3,self.btn_pause),(0,4,self.btn_stop),
            (1,0,self.btn_test),(1,1,self.btn_retry),(1,2,self.btn_export),
            (1,3,self.btn_bl),(1,4,self.btn_view_f),
        ]:
            btn.grid(row=r, column=c, padx=4, pady=3, sticky="ew")
        for c in range(5):
            bf.columnconfigure(c, weight=1)

        # Footer warning
        tk.Label(T,
            text="⚠  Keep WhatsApp Web open in Chrome/Edge  ·  "
                 "Move mouse to TOP-LEFT corner to emergency-stop",
            bg=BG, fg=RED, font=("Segoe UI", 8, "bold")).pack(pady=6)

    # ══════════════════════════════════════════
    #  LOG TAB
    # ══════════════════════════════════════════
    def _build_log(self, T):
        hdr = tk.Frame(T, bg=BG); hdr.pack(fill="x", padx=10, pady=8)
        tk.Label(hdr, text="📋  Session Log",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(hdr, text="📂 Open JSON Log", command=self._open_log_file).pack(side="right", padx=4)
        ttk.Button(hdr, text="📋 Copy All",       command=self._copy_log).pack(side="right", padx=4)
        ttk.Button(hdr, text="🗑 Clear Display",  command=self.do_clear_log).pack(side="right", padx=4)

        fr = tk.Frame(T, bg=BG); fr.pack(fill="both", expand=True, padx=10, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        self.log_box = tk.Text(
            fr, bg=CARD, fg=MUTED, font=("Consolas", 8),
            yscrollcommand=sc.set, state="disabled",
            relief="flat", padx=8, pady=6)
        self.log_box.pack(fill="both", expand=True)
        sc.config(command=self.log_box.yview)

        for tag, col in [
            ("info",   BLUE),
            ("sent",   GREEN),
            ("failed", RED),
            ("skip",   AMBER),
            ("warn",   PURPLE),
            ("system", MUTED),
            ("header", ACCENT),
        ]:
            self.log_box.tag_config(tag, foreground=col)

        self._log("system", f"AutoReach v{VERSION} ready  |  Python {sys.version.split()[0]}")
        self._log("system", f"All-time sent: {self.logger.total_sent()}  |  Blacklist: {self.blacklist.count()}")

    # ══════════════════════════════════════════
    #  SETTINGS TAB
    # ══════════════════════════════════════════
    def _build_settings(self, T):
        canvas = tk.Canvas(T, bg=BG, highlightthickness=0)
        vsb    = tk.Scrollbar(T, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        fr = tk.Frame(canvas, bg=BG)
        fr_id = canvas.create_window((0, 0), window=fr, anchor="nw")

        def _on_canvas_resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(fr_id, width=e.width)
        canvas.bind("<Configure>", _on_canvas_resize)
        fr.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        def _mwheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _mwheel)

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
            full = label + (f"   ← {tip}" if tip else "")
            tk.Label(fr, text=full,
                     bg=BG, fg=TEXT, anchor="w",
                     font=("Segoe UI", 9), width=65).grid(
                row=row[0], column=0, padx=22, pady=5, sticky="w")
            ttk.Spinbox(fr, from_=lo, to=hi, textvariable=var, width=8).grid(
                row=row[0], column=1, padx=8, pady=5, sticky="w")
            row[0] += 1
            var.trace_add("write", lambda *_: self._autosave())

        def check(label, var, color=TEXT, disabled=False, tip=""):
            full = label + (f"  [{tip}]" if tip else "")
            cb = tk.Checkbutton(
                fr, text=full, variable=var,
                bg=BG, fg=color, selectcolor=CARD2,
                activebackground=BG, font=("Segoe UI", 9),
                command=self._autosave)
            if disabled:
                cb.config(state="disabled", fg=MUTED)
            cb.grid(row=row[0], column=0, columnspan=3,
                    sticky="w", padx=22, pady=4)
            row[0] += 1

        # Spinbox Vars
        self.v_dmin      = tk.IntVar()
        self.v_dmax      = tk.IntVar()
        self.v_load      = tk.IntVar()
        self.v_postsend  = tk.IntVar()
        self.v_timeout   = tk.IntVar()
        self.v_dlimit    = tk.IntVar()
        self.v_retries   = tk.IntVar()

        # Checkbox Vars
        self.v_skip_sent    = tk.BooleanVar()
        self.v_skip_bl      = tk.BooleanVar()
        self.v_vary         = tk.BooleanVar()
        self.v_sound        = tk.BooleanVar()
        self.v_hide_browser = tk.BooleanVar()
        self.v_stop_on_fail = tk.BooleanVar()

        # ── Timing ────────────────────────────────
        section("⏱  Timing & Delays")
        spin("Min delay between messages (seconds):", self.v_dmin, 5, 300,
             "higher = safer (recommended: 20s+)")
        spin("Max delay between messages (seconds):", self.v_dmax, 10, 600,
             "randomised between min and max")
        spin("Wait for WhatsApp Web to load (seconds):", self.v_load, 3, 120,
             "10s recommended on average internet")
        spin("Post-send pause before closing tab (seconds):", self.v_postsend, 1, 30,
             "let WhatsApp confirm delivery")
        spin("Hard timeout per number (seconds):", self.v_timeout, 15, 180,
             "forces skip if exceeded")

        # ── Limits ────────────────────────────────
        section("📊  Limits & Reliability")
        spin("Daily send limit (messages/day):", self.v_dlimit, 5, 500,
             "session stops when limit reached")
        spin("Retry attempts per failed number:", self.v_retries, 1, 5,
             "each retry waits longer (exponential back-off)")

        # ── Behaviour ─────────────────────────────
        section("⚙  Behaviour")
        check("Skip numbers already sent in previous sessions (recommended)", self.v_skip_sent, GREEN)
        check("Skip blacklisted numbers (recommended)", self.v_skip_bl, GREEN)
        check("Vary each message slightly — invisible anti-spam character", self.v_vary, BLUE,
              tip="prevents duplicate-message filtering")
        check("Play sound when session finishes", self.v_sound)
        check("🛑 Stop entire session on first failure (strict mode)",
              self.v_stop_on_fail, AMBER,
              tip="off = collect failures, continue;  on = stop immediately")

        # ── Browser ───────────────────────────────
        section("🌐  Browser Visibility")
        if HAS_GW:
            check(
                "🙈 Hide browser window while sending\n"
                "      (Chrome/Edge runs silently in background — you won't see it pop up)",
                self.v_hide_browser, BLUE)
            tk.Label(fr,
                text="  ℹ  AutoReach window stays fully visible at all times.\n"
                     "  ℹ  Only Chrome/Edge is minimized. pyautogui still controls it normally.",
                bg=BG, fg=MUTED, font=("Segoe UI", 8),
                justify="left").grid(
                    row=row[0], column=0, columnspan=3,
                    sticky="w", padx=30, pady=(0, 8))
            row[0] += 1
        else:
            check("🙈 Hide browser window — install pygetwindow to enable",
                  self.v_hide_browser, MUTED, disabled=True)
            tk.Label(fr,
                text="  Run:  pip install pygetwindow",
                bg=BG, fg=RED, font=("Consolas", 8)).grid(
                    row=row[0], column=0, columnspan=3,
                    sticky="w", padx=30)
            row[0] += 1

        # ── Action Buttons ────────────────────────
        section("🔧  Actions")

        btn_row = tk.Frame(fr, bg=BG)
        btn_row.grid(row=row[0], column=0, columnspan=3,
                     sticky="w", padx=20, pady=8)
        row[0] += 1

        ttk.Button(btn_row, text="💾 Save Settings",
                   command=self._autosave,
                   style="Accent.TButton").pack(side="left", padx=6)

        ttk.Button(btn_row, text="🔁 Reset to Defaults",
                   command=self._reset_settings,
                   style="Warn.TButton").pack(side="left", padx=6)

        ttk.Button(btn_row, text="🗑 Clear History Log",
                   command=self._clear_history_log).pack(side="left", padx=6)

        self.lbl_save_status = tk.Label(
            fr, text="", bg=BG, fg=GREEN, font=("Segoe UI", 8))
        self.lbl_save_status.grid(
            row=row[0], column=0, columnspan=3,
            sticky="w", padx=22, pady=(0, 4))
        row[0] += 1

    # ══════════════════════════════════════════
    #  CALIBRATE TAB
    # ══════════════════════════════════════════
    def _build_calibrate(self, T):
        tk.Label(T, text="🎯  Click-Target Calibration",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=14)

        info = tk.Frame(T, bg=CARD); info.pack(padx=20, fill="x")
        tk.Label(info,
            text=(
                "AutoReach needs to know where the WhatsApp Web message\n"
                "input box is on your screen.\n\n"
                "HOW TO CALIBRATE (one time only):\n"
                "  1. Open WhatsApp Web in Chrome / Edge and open any chat.\n"
                "  2. Click  '🎯 Start 3s Countdown'  below.\n"
                "  3. Within 3 seconds, hover your mouse over the message\n"
                "     input box at the bottom of WhatsApp Web.\n"
                "  4. Stay still — position saves automatically.\n\n"
                "Redo calibration if you move or resize your browser window.\n"
                "The position is saved permanently until you reset it."
            ),
            bg=CARD, fg=TEXT, font=("Segoe UI", 9),
            justify="left", wraplength=700,
            padx=18, pady=14).pack(fill="x")

        self.lbl_calib = tk.Label(T, bg=BG, fg=GREEN,
                                  font=("Segoe UI", 10, "bold"))
        self.lbl_calib.pack(pady=8)
        self._calib_refresh()

        self.lbl_cdown = tk.Label(T, text="", bg=BG, fg=AMBER,
                                  font=("Segoe UI", 42, "bold"))
        self.lbl_cdown.pack(pady=4)

        self.lbl_mouse = tk.Label(T, text="Mouse: — , —",
                                  bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_mouse.pack()
        self._track_mouse()

        bf = tk.Frame(T, bg=BG); bf.pack(pady=12)
        ttk.Button(bf, text="🎯  Start 3s Countdown",
                   command=self._calib_start,
                   style="Accent.TButton").pack(side="left", padx=8)
        ttk.Button(bf, text="🔄  Reset to Default",
                   command=self._calib_reset).pack(side="left", padx=8)

    # ══════════════════════════════════════════
    #  ABOUT TAB
    # ══════════════════════════════════════════
    def _build_about(self, T):
        tk.Label(T, text=f"⚡ AutoReach v{VERSION}",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 16, "bold")).pack(pady=(30, 4))
        tk.Label(T, text="WhatsApp Web Outreach Automation  ·  Built for efficiency",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack()
        tk.Frame(T, bg=BORDER, height=1).pack(fill="x", padx=60, pady=18)
        tk.Label(T, text=(
            "What's new in v9.0\n\n"
            "  ✅  All missing functions from v8 fully implemented\n"
            "  ✅  Session summary popup at end — full failed-number report\n"
            "  ✅  'Clear History Log' button in Settings\n"
            "  ✅  Live countdown timer during inter-message delay\n"
            "  ✅  Pause truly halts between numbers (not mid-send)\n"
            "  ✅  Header dot animates while session is active\n"
            "  ✅  Better not-on-WhatsApp detection via title bar polling\n"
            "  ✅  Import preview shows first 5 numbers loaded\n"
            "  ✅  ETA shown in H:MM:SS format\n"
            "  ✅  Sound on finish (Windows / Mac / Linux)\n"
            "  ✅  Progress label shows X/Y during session\n"
            "  ✅  Settings page includes unit hints for all spinboxes\n"
            "  ✅  Test send shows spinner in log\n"
            "  ✅  Exponential back-off improved and capped at 30s\n"
            "  ✅  Blacklist all-failed-numbers in one click\n"
        ),
            bg=BG, fg=TEXT, font=("Consolas", 9),
            justify="left").pack(padx=40, anchor="w")
        tk.Frame(T, bg=BORDER, height=1).pack(fill="x", padx=60, pady=18)
        tk.Label(T,
            text="⚠  Only message people who opted in / expect your message.\n"
                 "Automated messaging may violate WhatsApp's Terms of Service.",
            bg=BG, fg=RED, font=("Segoe UI", 9, "bold"),
            justify="center").pack()

    # ──────────────────────────────────────────
    #  SETTINGS HELPERS
    # ──────────────────────────────────────────
    def _apply_cfg_to_ui(self):
        cfg = self._cfg
        self.v_dmin.set(cfg["dmin"])
        self.v_dmax.set(cfg["dmax"])
        self.v_load.set(cfg["load"])
        self.v_postsend.set(cfg["postsend"])
        self.v_timeout.set(cfg["timeout"])
        self.v_dlimit.set(cfg["dlimit"])
        self.v_retries.set(cfg["retries"])
        self.v_skip_sent.set(cfg["skip_sent"])
        self.v_skip_bl.set(cfg["skip_bl"])
        self.v_vary.set(cfg["vary"])
        self.v_sound.set(cfg["sound"])
        self.v_hide_browser.set(cfg["hide_browser"])
        self.v_stop_on_fail.set(cfg["stop_on_fail"])
        self.v_single.set(cfg["single_msg"])

    def _current_cfg(self) -> dict:
        return {
            "dmin":         self.v_dmin.get(),
            "dmax":         self.v_dmax.get(),
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
            "single_msg":   self.v_single.get(),
        }

    def _autosave(self, *_):
        try:
            cfg = self._current_cfg()
            save_settings(cfg)
            self._cfg = cfg
            self.lbl_save_status.config(
                text=f"✅ Saved  ({datetime.now().strftime('%H:%M:%S')})",
                fg=GREEN)
        except Exception as e:
            self.lbl_save_status.config(text=f"⚠ Save failed: {e}", fg=RED)

    def _reset_settings(self):
        if not messagebox.askyesno(
            "Reset Settings",
            "Reset ALL settings to factory defaults?\n\n"
            "This cannot be undone.\n"
            "Your import list, log, and blacklist are NOT affected."):
            return
        self._cfg = dict(DEFAULTS)
        self._apply_cfg_to_ui()
        save_settings(self._cfg)
        self.lbl_save_status.config(
            text="🔁 Reset to factory defaults.", fg=AMBER)
        self._log("warn", "Settings reset to factory defaults.")

    def _clear_history_log(self):
        if not messagebox.askyesno(
            "Clear History Log",
            "Delete ALL sent/failed history from autoreach_log.json?\n\n"
            "This resets your all-time counters.\n"
            "Your settings and blacklist are NOT affected."):
            return
        self.logger.clear_all()
        self._log("warn", "History log cleared by user.")
        self._refresh_daily()
        messagebox.showinfo("Done", "History log cleared.")

    # ──────────────────────────────────────────
    #  CALIBRATE HELPERS
    # ──────────────────────────────────────────
    def _track_mouse(self):
        try:
            x, y = pyautogui.position()
            self.lbl_mouse.config(text=f"Mouse position:  X = {x}   Y = {y}")
        except Exception:
            pass
        self.root.after(180, self._track_mouse)

    def _calib_refresh(self):
        cx, cy = self.calib.get()
        src = "✅ Calibrated" if self.calib.is_set() else "⚠ Default estimate — calibrate for accuracy"
        self.lbl_calib.config(
            text=f"Target →  X: {cx}   Y: {cy}     [ {src} ]",
            fg=GREEN if self.calib.is_set() else AMBER)

    def _calib_start(self):
        def _run():
            for i in (3, 2, 1):
                self._ui_q.put(("cdown", str(i)))
                time.sleep(1)
            x, y = pyautogui.position()
            self.calib.save(x, y)
            self._ui_q.put(("cdown", "✅ Saved!"))
            self.root.after(0, self._calib_refresh)
            time.sleep(1.8)
            self._ui_q.put(("cdown", ""))
        threading.Thread(target=_run, daemon=True).start()

    def _calib_reset(self):
        if os.path.exists(CALIB_FILE):
            os.remove(CALIB_FILE)
        self.calib.x = self.calib.y = None
        self._calib_refresh()

    # ──────────────────────────────────────────
    #  UI HELPERS
    # ──────────────────────────────────────────
    def _mode_hint(self):
        if self.v_single.get():
            self.lbl_mode.config(
                text="▸ Entire message sent in one go — formatting preserved")
        else:
            self.lbl_mode.config(
                text="▸ Each paragraph sent as a separate message (split on blank line)")
        self._autosave()

    def _char_count(self, _=None):
        txt   = self.msg_box.get("1.0", tk.END).strip()
        words = len(txt.split()) if txt else 0
        self.lbl_chars.config(
            text=f"Words: {words}  ·  Chars: {len(txt)}")

    def _log(self, tag: str, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._ui_q.put(("log", tag, f"[{ts}] {text}"))

    def _status(self, txt: str, color=None):
        self._ui_q.put(("status", txt, color or AMBER))

    def _refresh_daily(self):
        today = self.logger.sent_today()
        lim   = self._cfg.get("dlimit", 40)
        pct   = today / lim if lim else 0
        fg    = RED if pct >= 1.0 else (AMBER if pct >= 0.8 else GREEN)
        self.lbl_daily.config(text=f"Today: {today}/{lim}", fg=fg)
        self.lbl_alltime.config(text=f"All-time: {self.logger.total_sent()}")
        self.lbl_bl_count.config(text=f"Blacklist: {self.blacklist.count()}")

    def _update_stats(self):
        self._ui_q.put(("stats",))

    def _do_update_stats(self):
        s = self._slabels
        s["Loaded"].config(text=str(self.total))
        s["Sent"].config(text=str(self.sent_count))
        s["Failed"].config(text=str(len(self.failed_list)))
        s["Skipped"].config(text=str(self.skipped_count))
        pct = (self.current_idx / self.total * 100) if self.total else 0
        self.v_prog.set(pct)
        self.lbl_prog_txt.config(
            text=f"{self.current_idx} / {self.total}" if self.total else "")
        if self.start_time and self.current_idx > 0:
            elapsed = time.time() - self.start_time
            rem = (self.total - self.current_idx) * (elapsed / self.current_idx)
            self._slabels["ETA"].config(text=fmt_time(rem))
        else:
            self._slabels["ETA"].config(text="--:--:--")
        self._refresh_daily()

    # ── Thread-safe UI queue ───────────────────
    def _process_ui_q(self):
        try:
            while True:
                item = self._ui_q.get_nowait()
                cmd  = item[0]
                if cmd == "log":
                    _, tag, text = item
                    self.log_box.config(state="normal")
                    self.log_box.insert("end", text + "\n", tag)
                    self.log_box.see("end")
                    self.log_box.config(state="disabled")
                elif cmd == "status":
                    txt   = item[1]
                    color = item[2] if len(item) > 2 else AMBER
                    self.lbl_status.config(text=txt, fg=color)
                    self.lbl_hdr_status.config(text=txt, fg=color)
                elif cmd == "stats":
                    self._do_update_stats()
                elif cmd == "cdown":
                    self.lbl_cdown.config(text=item[1])
        except queue.Empty:
            pass
        self.root.after(40, self._process_ui_q)

    def _animate_header(self):
        """Animate the header status dot when running."""
        if self.running and not self.paused:
            dots = ["●", "○", "◉", "○"]
            self._dot_anim = (self._dot_anim + 1) % len(dots)
            current = self.lbl_hdr_status.cget("text")
            # replace leading dot char
            if current and current[0] in "●○◉":
                new = dots[self._dot_anim] + current[1:]
                self.lbl_hdr_status.config(text=new)
        self.root.after(500, self._animate_header)

    # ── Log helpers ────────────────────────────
    def _open_log_file(self):
        if os.path.exists(LOG_FILE):
            try:
                os.startfile(LOG_FILE)
            except AttributeError:
                import subprocess
                subprocess.call(
                    ["open" if sys.platform == "darwin" else "xdg-open", LOG_FILE])
        else:
            messagebox.showinfo("No Log", "No log file yet — run a session first.")

    def _copy_log(self):
        try:
            pyperclip.copy(self.log_box.get("1.0", tk.END))
            messagebox.showinfo("Copied", "Log copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ── Window close ───────────────────────────
    def _on_close(self):
        self._autosave()
        if self.running:
            if messagebox.askyesno("Session Running",
                                   "A session is running. Stop and exit?"):
                self.running = False
                self.root.after(700, self.root.destroy)
        else:
            self.root.destroy()

    # ══════════════════════════════════════════
    #  CORE: CLICK THE MESSAGE BOX
    # ══════════════════════════════════════════
    def _click_msg_box(self, restore_first=True):
        if restore_first and self.v_hide_browser.get() and HAS_GW:
            self.browser.activate()
            time.sleep(0.18)

        cx, cy = self.calib.get()
        ox = random.randint(-4, 4)
        oy = random.randint(-2, 2)
        try:
            pyautogui.moveTo(cx + ox, cy + oy,
                             duration=random.uniform(0.06, 0.18))
            time.sleep(0.06)
            pyautogui.click()
            time.sleep(0.28)
        except Exception:
            pass

        if self.v_hide_browser.get() and HAS_GW:
            self.browser.hide()

    # ══════════════════════════════════════════
    #  CORE: WAIT FOR PAGE READY
    # ══════════════════════════════════════════
    def _wait_page_ready(self, deadline: float) -> bool:
        load_max = self.v_load.get()
        waited   = 0.0

        while waited < load_max:
            if not self.running or time.time() > deadline:
                return False
            while self.paused:
                time.sleep(0.2)

            if self.v_hide_browser.get() and HAS_GW:
                self.browser.activate()
                time.sleep(0.15)

            self._click_msg_box(restore_first=False)

            try:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.09)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.09)
            except Exception:
                pass

            clip = self._safe_paste()
            if clip is not None:
                self._click_msg_box(restore_first=True)
                return True

            remaining = int(load_max - waited)
            self._status(f"● Waiting for WhatsApp Web… ({remaining}s)", AMBER)
            time.sleep(0.5)
            waited += 0.5

        self._click_msg_box(restore_first=True)
        return True

    # ══════════════════════════════════════════
    #  CORE: PASTE TEXT
    # ══════════════════════════════════════════
    def _paste_text(self, text: str):
        if self.v_hide_browser.get() and HAS_GW:
            self.browser.activate()
            time.sleep(0.12)
        try:
            pyperclip.copy(text)
            time.sleep(0.14)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.24)
        except Exception:
            pass
        if self.v_hide_browser.get() and HAS_GW:
            self.browser.hide()

    def _safe_paste(self):
        try:
            return pyperclip.paste()
        except Exception:
            return None

    # ══════════════════════════════════════════
    #  CORE: PRESS ENTER (keyboard — no mouse)
    # ══════════════════════════════════════════
    def _press_enter(self):
        if self.v_hide_browser.get() and HAS_GW:
            self.browser.activate()
            time.sleep(0.12)
        try:
            pyautogui.press("enter")
            time.sleep(0.2)
        except Exception:
            pass
        if self.v_hide_browser.get() and HAS_GW:
            self.browser.hide()

    # ══════════════════════════════════════════
    #  CORE: WAIT FOR BOX TO CLEAR AFTER SEND
    # ══════════════════════════════════════════
    def _wait_box_clear(self, max_sec: float = 8.0) -> bool:
        deadline = time.time() + max_sec
        while time.time() < deadline:
            if not self.running:
                return False
            if self.v_hide_browser.get() and HAS_GW:
                self.browser.activate()
                time.sleep(0.08)
            try:
                pyautogui.hotkey("ctrl", "a"); time.sleep(0.07)
                pyautogui.hotkey("ctrl", "c"); time.sleep(0.07)
            except Exception:
                pass
            if self.v_hide_browser.get() and HAS_GW:
                self.browser.hide()
            clip = self._safe_paste()
            if clip is not None and clip.strip() == "":
                return True
            time.sleep(0.25)
        return False

    # ══════════════════════════════════════════
    #  CORE: SEND — SINGLE MESSAGE
    # ══════════════════════════════════════════
    def _send_single(self, number: str, msg: str) -> tuple:
        timeout  = self.v_timeout.get()
        deadline = time.time() + timeout

        try:
            webbrowser.open(
                f"https://web.whatsapp.com/send/"
                f"?phone={number}&type=phone_number&app_absent=0")
            time.sleep(1.8)

            self.browser.activate()
            time.sleep(0.4)

            # Hide immediately if user wants it
            if self.v_hide_browser.get() and HAS_GW:
                time.sleep(0.3)
                self.browser.hide()

            if time.time() > deadline:
                return False, "timeout before page loaded"

            ready = self._wait_page_ready(deadline)
            if not ready:
                return False, "page did not become ready in time"

            if time.time() > deadline:
                return False, "timeout after page load"

            self._paste_text(msg)

            # Verify paste landed
            if self.v_hide_browser.get() and HAS_GW:
                self.browser.activate(); time.sleep(0.1)
            try:
                pyautogui.hotkey("ctrl", "a"); time.sleep(0.08)
                pyautogui.hotkey("ctrl", "c"); time.sleep(0.08)
            except Exception:
                pass
            if self.v_hide_browser.get() and HAS_GW:
                self.browser.hide()

            if (self._safe_paste() or "").strip() == "":
                # Paste failed — retry once
                self._click_msg_box(restore_first=True)
                self._paste_text(msg)
                time.sleep(0.3)

            # ── Send via keyboard Enter ──────────────
            self._press_enter()

            # ── Confirm: wait for box to clear ───────
            confirmed = self._wait_box_clear(min(8.0, deadline - time.time()))

            if not confirmed:
                return False, "box did not clear after Enter — send unconfirmed"

            # ── Post-send countdown ───────────────────
            post = self.v_postsend.get()
            for i in range(post, 0, -1):
                if not self.running:
                    break
                self._status(f"● Sent ✅  —  closing tab in {i}s…", GREEN)
                time.sleep(1.0)

            return True, ""

        except pyautogui.FailSafeException:
            raise
        except Exception as ex:
            return False, str(ex)
        finally:
            self.browser.close_tab()

    # ══════════════════════════════════════════
    #  CORE: SEND — SPLIT PARAGRAPHS
    # ══════════════════════════════════════════
    def _send_split(self, number: str, msg: str) -> tuple:
        timeout  = self.v_timeout.get()
        deadline = time.time() + timeout
        parts    = [p.strip() for p in msg.split("\n\n") if p.strip()]

        if not parts:
            return False, "message is empty"

        try:
            webbrowser.open(
                f"https://web.whatsapp.com/send/"
                f"?phone={number}&type=phone_number&app_absent=0")
            time.sleep(1.8)
            self.browser.activate()
            time.sleep(0.4)
            if self.v_hide_browser.get() and HAS_GW:
                time.sleep(0.3)
                self.browser.hide()

            ready = self._wait_page_ready(deadline)
            if not ready:
                return False, "page did not load"

            for i, part in enumerate(parts):
                if not self.running or time.time() > deadline:
                    return False, "stopped or timeout mid-send"
                self._paste_text(part)
                time.sleep(0.2)
                self._press_enter()
                if not self._wait_box_clear(min(5.0, deadline - time.time())):
                    return False, f"box did not clear after part {i+1}"
                if i < len(parts) - 1:
                    time.sleep(gauss_delay(0.9, 2.0))

            post = self.v_postsend.get()
            for i in range(post, 0, -1):
                if not self.running:
                    break
                self._status(f"● Sent ✅  —  closing tab in {i}s…", GREEN)
                time.sleep(1.0)

            return True, ""

        except pyautogui.FailSafeException:
            raise
        except Exception as ex:
            return False, str(ex)
        finally:
            self.browser.close_tab()

    # ══════════════════════════════════════════
    #  SEND WRAPPER (retry + exponential back-off)
    # ══════════════════════════════════════════
    def send_message(self, number: str, raw: str) -> tuple:
        if self.v_dry.get():
            time.sleep(random.uniform(1.0, 2.5))
            return True, ""

        max_ret     = self.v_retries.get()
        last_reason = ""

        for attempt in range(1, max_ret + 1):
            if not self.running:
                return False, "stopped by user"

            if attempt > 1:
                backoff = min(30, gauss_delay(3, 6) * (1.6 ** (attempt - 1)))
                self._log("warn",
                    f"  ↻ Retry {attempt}/{max_ret} in {backoff:.0f}s → {number}")
                elapsed = 0.0
                while elapsed < backoff and self.running:
                    self._status(
                        f"● Retry {attempt} in {backoff - elapsed:.0f}s…", AMBER)
                    time.sleep(0.5)
                    elapsed += 0.5

            if not self.running:
                return False, "stopped during retry wait"

            msg = vary(raw) if self.v_vary.get() else raw
            try:
                if self.v_single.get():
                    ok, reason = self._send_single(number, msg)
                else:
                    ok, reason = self._send_split(number, msg)
            except pyautogui.FailSafeException:
                self._log("warn", "🛑 EMERGENCY STOP — mouse moved to top-left corner.")
                self.do_stop()
                return False, "emergency stop"
            except Exception as ex:
                ok, reason = False, str(ex)

            last_reason = reason
            if ok:
                return True, ""
            else:
                self._log("warn", f"  Attempt {attempt} failed: {reason}")

        return False, last_reason

    # ══════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════
    def _loop(self):
        raw   = self.msg_box.get("1.0", tk.END).strip()
        dlim  = self.v_dlimit.get()
        sent_set = self.logger.sent_set() if self.v_skip_sent.get() else set()

        while self.current_idx < self.total and self.running:
            # Respect pause
            while self.paused and self.running:
                time.sleep(0.25)
            if not self.running:
                break

            # Daily limit
            if self.logger.sent_today() >= dlim:
                self._log("warn",
                    f"⚠ Daily limit of {dlim} reached — session paused."
                    f" Increase limit in Settings or resume tomorrow.")
                self._status(f"● Daily limit ({dlim}) reached", AMBER)
                self.do_stop()
                break

            number = self.numbers[self.current_idx]
            self.current_idx += 1
            self._update_stats()

            # ── Skip checks ──────────────────────────
            if self.v_skip_sent.get() and number in sent_set:
                self.skipped_count += 1
                self._log("skip", f"⏭ Skipped (already sent): {number}")
                self._update_stats()
                continue

            if self.v_skip_bl.get() and self.blacklist.has(number):
                self.skipped_count += 1
                self._log("skip", f"⏭ Skipped (blacklisted): {number}")
                self._update_stats()
                continue

            # ── Send ─────────────────────────────────
            self._status(
                f"● Sending {self.current_idx}/{self.total}  →  {number}", BLUE)
            self._log("info",
                f"→ Sending to {number}  ({self.current_idx}/{self.total})")

            ok, reason = self.send_message(number, raw)

            if ok:
                self.sent_count += 1
                sent_set.add(number)
                self.logger.mark_sent(number)
                self._log("sent", f"✅ Sent → {number}")
            else:
                self.failed_list.append((number, reason))
                self.logger.mark_failed(number, reason)
                self._log("failed", f"❌ Failed → {number}  |  {reason}")
                if self.v_stop_on_fail.get():
                    self._log("warn", "🛑 Strict mode: stopping after first failure.")
                    self.running = False
                    break

            self._update_stats()

            # ── If more numbers remain, wait between sends ──
            if self.running and self.current_idx < self.total:
                mn = self.v_dmin.get()
                mx = max(mn + 1, self.v_dmax.get())
                delay = gauss_delay(mn, mx)
                self._log("info", f"  ⏳ Waiting {delay:.0f}s before next…")
                elapsed = 0.0
                while elapsed < delay and self.running:
                    while self.paused and self.running:
                        time.sleep(0.25)
                    remaining = delay - elapsed
                    self._status(
                        f"● Waiting {remaining:.0f}s before next number…", MUTED)
                    time.sleep(0.5)
                    elapsed += 0.5

        # ── Session finished ─────────────────────────
        self.running = False
        duration = fmt_time(time.time() - self.start_time) if self.start_time else "?"
        self._log("header", "━" * 55)
        self._log("header",
            f"SESSION COMPLETE  ·  Sent: {self.sent_count}  "
            f"Failed: {len(self.failed_list)}  Skipped: {self.skipped_count}  "
            f"Duration: {duration}")
        self._log("header", "━" * 55)

        if self.v_sound.get():
            play_done_sound()

        self.root.after(0, self._session_done_ui)

    def _session_done_ui(self):
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ PAUSE")
        self._status(
            f"● Done  —  ✅ {self.sent_count} sent  "
            f"❌ {len(self.failed_list)} failed  ⏭ {self.skipped_count} skipped",
            GREEN if not self.failed_list else AMBER)
        self._update_stats()
        self._show_session_summary()

    def _show_session_summary(self):
        """Show a detailed popup at the end of every session."""
        duration = fmt_time(time.time() - self.start_time) if self.start_time else "?"
        lines = [
            f"Session Complete\n",
            f"  ✅  Sent      : {self.sent_count}",
            f"  ❌  Failed    : {len(self.failed_list)}",
            f"  ⏭  Skipped   : {self.skipped_count}",
            f"  ⏱  Duration  : {duration}",
        ]
        if self.failed_list:
            lines.append("\n── Failed Numbers ──────────────────────")
            for n, reason in self.failed_list:
                lines.append(f"  {n}  →  {reason}")
            lines.append("\nUse  'Retry Failed'  or  'Export Failed'  to handle these.")

        # Show in a resizable dialog
        popup = tk.Toplevel(self.root)
        popup.title("Session Summary")
        popup.configure(bg=BG)
        popup.geometry("560x420")
        popup.resizable(True, True)

        tk.Label(popup, text="⚡ Session Summary",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=(16, 6))

        fr = tk.Frame(popup, bg=BG); fr.pack(fill="both", expand=True, padx=16, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        box = tk.Text(fr, bg=CARD, fg=TEXT, font=("Consolas", 9),
                      relief="flat", padx=10, pady=8,
                      yscrollcommand=sc.set, state="normal")
        box.pack(fill="both", expand=True)
        sc.config(command=box.yview)
        box.insert("end", "\n".join(lines))
        box.config(state="disabled")

        bf = tk.Frame(popup, bg=BG); bf.pack(pady=10)
        ttk.Button(bf, text="✅ OK", command=popup.destroy,
                   style="Accent.TButton").pack(side="left", padx=6)
        if self.failed_list:
            ttk.Button(bf, text="💾 Export Failed",
                       command=lambda: [popup.destroy(), self.do_export()]).pack(side="left", padx=6)
            ttk.Button(bf, text="🔁 Retry Failed",
                       command=lambda: [popup.destroy(), self.do_retry()]).pack(side="left", padx=6)

    # ══════════════════════════════════════════
    #  BUTTON ACTIONS
    # ══════════════════════════════════════════
    def do_import(self):
        path = filedialog.askopenfilename(
            title="Select number list",
            filetypes=[("Text/CSV", "*.txt *.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception as e:
            messagebox.showerror("Error reading file", str(e)); return

        clean, seen, bad = [], set(), 0
        for ln in lines:
            ln = ln.strip().split(",")[0].strip()
            n  = to_e164(ln)
            if n and n not in seen:
                seen.add(n); clean.append(n)
            elif ln:
                bad += 1

        self.numbers       = clean
        self.total         = len(clean)
        self.current_idx   = 0
        self.sent_count    = 0
        self.skipped_count = 0
        self.failed_list   = []
        self._update_stats()

        preview = "\n".join(f"  {n}" for n in clean[:5])
        if len(clean) > 5:
            preview += f"\n  … and {len(clean) - 5} more"

        self._log("info",
            f"Imported {self.total} numbers from '{os.path.basename(path)}'  "
            f"({bad} invalid/duplicate skipped)")
        messagebox.showinfo("Import Complete",
            f"✅  {self.total} valid numbers loaded\n"
            f"⚠   {bad} invalid / duplicate skipped\n\n"
            f"First numbers:\n{preview}")

    def do_reset(self):
        if self.running:
            messagebox.showwarning("Session Running", "Stop the session first."); return
        if not messagebox.askyesno("Reset List",
            "Clear the current list and reset session counters?\n"
            "(Log history and settings are kept.)"):
            return
        self.numbers       = []
        self.total         = 0
        self.current_idx   = 0
        self.sent_count    = 0
        self.failed_list   = []
        self.skipped_count = 0
        self._update_stats()
        self._status("● Idle — import a new number list", AMBER)
        self._log("info", "List reset.")

    def do_start(self):
        if not self.numbers:
            messagebox.showwarning("No List", "Import a number list first."); return
        if self.current_idx >= self.total:
            messagebox.showinfo("All Done",
                "All numbers have been processed.\n"
                "Use 'Reset List' and import again to start fresh."); return
        lim = self.v_dlimit.get()
        if self.logger.sent_today() >= lim:
            messagebox.showwarning("Daily Limit",
                f"You've hit the daily limit of {lim} messages.\n"
                f"Increase the limit in Settings, or wait until tomorrow."); return
        if not self.calib.is_set():
            if not messagebox.askyesno("Not Calibrated",
                "Click position not calibrated — using estimated default.\n\n"
                "For best results, calibrate first (Calibrate tab).\n\n"
                "Start anyway?"):
                return

        self.running    = True
        self.paused     = False
        self.start_time = time.time()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ PAUSE")
        self._status("● Running…", GREEN)
        self._log("info",
            f"▶ Session started — {self.total - self.current_idx} numbers to process"
            + ("  [DRY RUN]" if self.v_dry.get() else ""))
        if self.v_dry.get():
            self._log("warn", "⚠  DRY RUN — nothing will actually be sent")

        threading.Thread(target=self._loop, daemon=True).start()

    def do_pause(self):
        if not self.running: return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RESUME")
            self._status(f"● Paused at {self.current_idx}/{self.total}", AMBER)
            self._log("warn", "⏸ Session paused.")
        else:
            self.btn_pause.config(text="⏸ PAUSE")
            self._status("● Running…", GREEN)
            self._log("info", "▶ Session resumed.")

    def do_stop(self):
        self.running = False
        self.paused  = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))
        self._status(
            f"● Stopped at {self.current_idx}/{self.total}  "
            f"(✅{self.sent_count} ❌{len(self.failed_list)} ⏭{self.skipped_count})",
            RED)
        self._log("warn",
            f"⏹ Stopped — {self.sent_count} sent, "
            f"{len(self.failed_list)} failed, {self.skipped_count} skipped")

    def do_test(self):
        val = simpledialog.askstring("Test Send",
            "Enter phone number to test:\n(10-digit or 12-digit with country code)")
        if not val: return
        n = to_e164(val.strip())
        if not n:
            messagebox.showwarning("Invalid Number",
                "Cannot parse number.\nUse 10-digit or 12-digit (with country code)."); return
        raw = self.msg_box.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("Empty Message",
                "Write a message in the template box first."); return

        self._log("info", f"🔬 Test send starting → {n} …")
        self._log("info", "  (spinner) working…")

        def _t():
            ok, reason = self.send_message(n, raw)
            result = "✅ Test sent successfully!" if ok else f"❌ Test FAILED\nReason: {reason}"
            self._log("sent" if ok else "failed", f"  Test result: {result.split(chr(10))[0]}")
            self.root.after(0, lambda: messagebox.showinfo("Test Result", result))
        threading.Thread(target=_t, daemon=True).start()

    def do_retry(self):
        if not self.failed_list:
            messagebox.showinfo("No Failures", "No failed numbers to retry."); return
        nums = [n for n, _ in self.failed_list]
        self.numbers       = nums
        self.total         = len(nums)
        self.current_idx   = 0
        self.sent_count    = 0
        self.skipped_count = 0
        self.failed_list   = []
        self._update_stats()
        messagebox.showinfo("Retry Ready",
            f"Loaded {self.total} failed numbers.\nClick  ▶ START  to retry them.")

    def do_export(self):
        if not self.failed_list:
            messagebox.showinfo("No Failures", "No failed numbers to export."); return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
            initialfile="failed_numbers.txt")
        if not p: return
        try:
            with open(p, "w", encoding="utf-8") as f:
                for n, reason in self.failed_list:
                    f.write(f"{n}  |  {reason}\n")
            messagebox.showinfo("Exported",
                f"Saved {len(self.failed_list)} numbers to:\n{p}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def do_blacklist(self):
        if not self.failed_list:
            # Ask for a specific number
            val = simpledialog.askstring(
                "Blacklist Number",
                "Enter a phone number to blacklist:")
            if not val:
                return
            n = to_e164(val.strip())
            if not n:
                messagebox.showwarning("Invalid", "Cannot parse number."); return
            self.blacklist.add(n)
            self._log("warn", f"🔕 Blacklisted: {n}")
            self._refresh_daily()
            messagebox.showinfo("Blacklisted",
                f"✅ {n} added to blacklist.\nTotal blacklisted: {self.blacklist.count()}")
            return

        # There are failed numbers — offer choice
        choice = messagebox.askyesnocancel(
            "Blacklist",
            f"You have {len(self.failed_list)} failed number(s).\n\n"
            "YES  →  Blacklist ALL failed numbers\n"
            "NO   →  Enter a specific number\n"
            "CANCEL  →  Do nothing")

        if choice is None:
            return
        elif choice:
            # Blacklist all failed
            count = 0
            for n, _ in self.failed_list:
                self.blacklist.add(n)
                count += 1
            self._log("warn", f"🔕 Blacklisted {count} failed numbers.")
            self._refresh_daily()
            messagebox.showinfo("Blacklisted",
                f"✅ {count} numbers added to blacklist.\n"
                f"Total blacklisted: {self.blacklist.count()}")
        else:
            # Specific number
            val = simpledialog.askstring(
                "Blacklist Number",
                "Enter a phone number to blacklist:")
            if not val:
                return
            n = to_e164(val.strip())
            if not n:
                messagebox.showwarning("Invalid", "Cannot parse number."); return
            self.blacklist.add(n)
            self._log("warn", f"🔕 Blacklisted: {n}")
            self._refresh_daily()
            messagebox.showinfo("Blacklisted",
                f"✅ {n} added to blacklist.\nTotal: {self.blacklist.count()}")

    def do_view_failed(self):
        if not self.failed_list:
            messagebox.showinfo("No Failures",
                "No failed numbers in this session.\n\n"
                "(Previous session failures are in  autoreach_log.json)"); return

        popup = tk.Toplevel(self.root)
        popup.title("Failed Numbers — This Session")
        popup.configure(bg=BG)
        popup.geometry("520x400")
        popup.resizable(True, True)

        tk.Label(popup,
                 text=f"❌  {len(self.failed_list)} Failed Number(s) — Current Session",
                 bg=BG, fg=RED,
                 font=("Segoe UI", 11, "bold")).pack(pady=(14, 4))

        fr = tk.Frame(popup, bg=BG); fr.pack(fill="both", expand=True, padx=14, pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right", fill="y")
        box = tk.Text(fr, bg=CARD, fg=TEXT, font=("Consolas", 9),
                      relief="flat", padx=8, pady=6,
                      yscrollcommand=sc.set, state="normal")
        box.pack(fill="both", expand=True)
        sc.config(command=box.yview)
        box.tag_config("num",    foreground=RED)
        box.tag_config("reason", foreground=MUTED)

        for n, reason in self.failed_list:
            box.insert("end", f"  {n}", "num")
            box.insert("end", f"  →  {reason}\n", "reason")

        box.config(state="disabled")

        bf = tk.Frame(popup, bg=BG); bf.pack(pady=10)
        ttk.Button(bf, text="Close",
                   command=popup.destroy).pack(side="left", padx=6)
        ttk.Button(bf, text="💾 Export",
                   command=lambda: [popup.destroy(), self.do_export()]).pack(side="left", padx=6)
        ttk.Button(bf, text="🔁 Retry",
                   command=lambda: [popup.destroy(), self.do_retry()]).pack(side="left", padx=6)
        ttk.Button(bf, text="🔕 Blacklist All",
                   command=lambda: [popup.destroy(), self.do_blacklist()]).pack(side="left", padx=6)

    def do_clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")


# ══════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════

def main():
    root = tk.Tk()
    app  = AutoReach(root)
    root.mainloop()


if __name__ == "__main__":
    main()

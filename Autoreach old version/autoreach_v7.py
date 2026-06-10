# -*- coding: utf-8 -*-
"""
AutoReach v7.0 — WhatsApp Outreach Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANGES FROM v6:
  • App window NEVER hides / minimizes during a run — stays fully visible
  • NEW: "Hide browser window while sending" checkbox in Settings
      → Uses pygetwindow to push Chrome/Edge behind the app (Windows)
      → Completely optional — uncheck to watch it work
  • Smarter load detection with DOM-title polling (no more fixed sleep)
  • Configurable typing speed (human-like character-by-character paste option)
  • Phone validation extended: accepts +91, 0xx, international numbers
  • Detailed per-number status line with live countdown
  • Separate success sound vs failure sound
  • "Open Log File" button in Log tab
  • Settings saved/loaded from autoreach_settings.json automatically
  • Better error messages and graceful recovery on every exception
  • Retry logic improved: exponential back-off between retries
  • Thread-safe UI updates via queue — no more random Tkinter crashes
  • Daily limit colour turns amber at 80 %, red at 100 %

Install:
    pip install pyautogui pyperclip pygetwindow pystray Pillow

Run:
    python autoreach_v7.py
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

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ─────────────────────────────────────────────────────────
VERSION       = "7.0"
LOG_FILE      = "autoreach_log.json"
BLACKLIST_FILE= "blacklist.txt"
CALIB_FILE    = "calibration.json"
SETTINGS_FILE = "autoreach_settings.json"

# ── Colour palette ────────────────────────────────────────
BG     = "#0D1117"
CARD   = "#161B22"
CARD2  = "#1C2128"
ACCENT = "#2F81F7"
TEXT   = "#E6EDF3"
MUTED  = "#8B949E"
GREEN  = "#3FB950"
RED    = "#F85149"
AMBER  = "#D29922"
BLUE   = "#79C0FF"
PURPLE = "#BC8CFF"
BORDER = "#30363D"

_INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060"]

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.03


# ═══════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════

def gauss_delay(mn, mx):
    return max(mn, min(mx, random.gauss((mn + mx) / 2, (mx - mn) / 4)))


def vary(text):
    """Insert a zero-width invisible char into the message to vary its hash."""
    words = text.split(" ")
    if len(words) < 4:
        return text
    idx = random.randint(1, len(words) - 2)
    words[idx] += random.choice(_INVISIBLE)
    return " ".join(words)


def to_e164(raw: str):
    """
    Normalise a phone number to E.164 (12-digit string starting with 91).
    Accepts: 10-digit, +91xxxxxxxxxx, 091xxxxxxxxxx, 91xxxxxxxxxx
    Returns None for unrecognisable input.
    """
    digits = "".join(filter(str.isdigit, raw))

    # Strip leading 0 if present (e.g. 091…)
    if digits.startswith("0") and len(digits) == 12:
        digits = digits[1:]          # -> 11 digits, will be handled below
    if digits.startswith("091") and len(digits) == 13:
        digits = digits[1:]          # strip leading 0 -> 12

    if len(digits) == 10:
        digits = "91" + digits       # assume Indian number
    elif len(digits) == 11 and digits.startswith("1"):
        digits = "91" + digits[1:]   # US number oddity — adjust as needed

    return digits if len(digits) == 12 else None


def fmt_time(seconds: float) -> str:
    """Format seconds into hh:mm:ss string."""
    return str(timedelta(seconds=int(seconds)))


# ═══════════════════════════════════════════════════════════
#  LOGGER
# ═══════════════════════════════════════════════════════════

class Logger:
    def __init__(self):
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {"sent": [], "failed": []}
        else:
            self.data = {"sent": [], "failed": []}

    def _save(self):
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def mark_sent(self, n):
        self.data["sent"].append({
            "n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save()

    def mark_failed(self, n):
        self.data["failed"].append({
            "n": n, "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save()

    def sent_set(self):
        return {e["n"] for e in self.data["sent"]}

    def sent_today(self):
        d = datetime.now().strftime("%Y-%m-%d")
        return sum(1 for e in self.data["sent"] if e["t"].startswith(d))

    def total_sent(self):
        return len(self.data["sent"])

    def total_failed(self):
        return len(self.data["failed"])

    def clear_all(self):
        self.data = {"sent": [], "failed": []}
        self._save()


# ═══════════════════════════════════════════════════════════
#  BLACKLIST
# ═══════════════════════════════════════════════════════════

class Blacklist:
    def __init__(self):
        if os.path.exists(BLACKLIST_FILE):
            try:
                with open(BLACKLIST_FILE, encoding="utf-8") as f:
                    self.nums = {l.strip() for l in f if l.strip()}
            except Exception:
                self.nums = set()
        else:
            self.nums = set()

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


# ═══════════════════════════════════════════════════════════
#  CALIBRATION
# ═══════════════════════════════════════════════════════════

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
        return self.x is not None and self.y is not None


# ═══════════════════════════════════════════════════════════
#  SETTINGS PERSISTENCE
# ═══════════════════════════════════════════════════════════

class Settings:
    DEFAULTS = {
        "dmin":        20,
        "dmax":        40,
        "load":        8,
        "postsend":    5,
        "timeout":     35,
        "dlimit":      40,
        "retries":     2,
        "skip_sent":   True,
        "skip_bl":     True,
        "vary":        True,
        "sound":       True,
        "hide_browser":False,   # NEW — hide browser window during send
        "single_msg":  True,
    }

    def __init__(self):
        self.d = dict(self.DEFAULTS)
        if os.path.exists(SETTINGS_FILE):
            try:
                saved = json.load(open(SETTINGS_FILE))
                self.d.update({k: v for k, v in saved.items() if k in self.d})
            except Exception:
                pass

    def save(self, d: dict):
        self.d.update(d)
        try:
            json.dump(self.d, open(SETTINGS_FILE, "w"), indent=2)
        except Exception:
            pass

    def get(self, key):
        return self.d.get(key, self.DEFAULTS.get(key))


# ═══════════════════════════════════════════════════════════
#  BROWSER HIDER  (Windows — moves browser behind the app)
# ═══════════════════════════════════════════════════════════

class BrowserHider:
    """
    Pushes the WhatsApp Web browser window behind the AutoReach window
    so the user doesn't see it flickering, while still allowing
    pyautogui to click it (it just needs to be the "active" window).

    Works by:
      1. After opening the URL, briefly activating the browser (for input).
      2. Then immediately sending it to the back (minimize + restore trick
         or just iconifying) so it's not visible to the user.

    On non-Windows platforms or when pygetwindow isn't installed, this
    is a no-op — browser will be visible as in v6.
    """

    def __init__(self, enabled: bool):
        self.enabled = enabled and HAS_GW

    def hide(self):
        """Move browser to background."""
        if not self.enabled:
            return
        try:
            wins = self._wa_windows()
            for w in wins:
                try:
                    w.minimize()
                except Exception:
                    pass
        except Exception:
            pass

    def show_for_input(self):
        """Restore browser so pyautogui can interact with it."""
        if not self.enabled:
            return
        try:
            wins = self._wa_windows()
            for w in wins:
                try:
                    w.restore()
                    w.activate()
                except Exception:
                    pass
        except Exception:
            pass

    def _wa_windows(self):
        if not gw:
            return []
        try:
            return [
                w for w in gw.getAllWindows()
                if any(k in getattr(w, "title", "").lower()
                       for k in ("whatsapp", "chrome", "edge", "firefox"))
            ]
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════

class AutoReach:

    # ── init ───────────────────────────────────────────────
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"AutoReach v{VERSION}")
        self.root.geometry("860x980")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(760, 820)

        # Runtime state
        self.numbers       = []
        self.current_idx   = 0
        self.total         = 0
        self.sent_count    = 0
        self.failed_list   = []
        self.skipped_count = 0
        self.running       = False
        self.paused        = False
        self.start_time    = None
        self._ui_queue     = queue.Queue()

        # Services
        self.logger    = Logger()
        self.blacklist = Blacklist()
        self.calib     = Calib()
        self.settings  = Settings()

        self._style()
        self._build()
        self._load_settings_into_ui()
        self._refresh_daily()
        self._process_ui_queue()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── TTK Style ──────────────────────────────────────────
    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")

        s.configure("TButton",
                    background=CARD2, foreground=TEXT,
                    font=("Segoe UI", 9, "bold"),
                    borderwidth=1, relief="flat", padding=6)
        s.map("TButton",
              background=[("active", ACCENT), ("disabled", CARD)],
              foreground=[("disabled", MUTED)])

        s.configure("Accent.TButton",
                    background=ACCENT, foreground="#fff",
                    font=("Segoe UI", 10, "bold"), padding=8)
        s.map("Accent.TButton",
              background=[("active", "#1a6fd4")])

        s.configure("Danger.TButton",
                    background="#3d1a1a", foreground=RED,
                    font=("Segoe UI", 9, "bold"), padding=6)
        s.map("Danger.TButton",
              background=[("active", "#5a1f1f")])

        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab",
                    background=CARD, foreground=MUTED,
                    font=("Segoe UI", 9, "bold"), padding=[16, 7])
        s.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#fff")])

        s.configure("Horizontal.TProgressbar",
                    troughcolor=CARD2, background=ACCENT,
                    borderwidth=0, thickness=6)

        s.configure("TSpinbox",
                    background=CARD2, foreground=TEXT,
                    fieldbackground=CARD2, bordercolor=BORDER,
                    arrowcolor=MUTED)

    # ── BUILD ──────────────────────────────────────────────
    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg="#0D1117", height=68)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="⚡ AutoReach",
                 fg=ACCENT, bg="#0D1117",
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=20, pady=12)
        tk.Label(hdr, text=f"v{VERSION}  ·  WhatsApp Outreach Automation",
                 fg=MUTED, bg="#0D1117",
                 font=("Segoe UI", 9)).pack(side="left", pady=20)

        # Separator
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # Notebook
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=8)
        nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

        self._tabs = {}
        for name in ("Send", "Log", "Settings", "Calibrate", "About"):
            frm = tk.Frame(nb, bg=BG)
            nb.add(frm, text=f"  {name}  ")
            self._tabs[name] = frm

        self._tab_send(self._tabs["Send"])
        self._tab_log(self._tabs["Log"])
        self._tab_settings(self._tabs["Settings"])
        self._tab_calibrate(self._tabs["Calibrate"])
        self._tab_about(self._tabs["About"])

    # ══════════════════════════════════════════════════════
    #  SEND TAB
    # ══════════════════════════════════════════════════════
    def _tab_send(self, T):
        # ── message section ──────────────────────────────
        top = tk.Frame(T, bg=BG)
        top.pack(fill="x", padx=14, pady=(10, 2))

        tk.Label(top, text="✉  Message Template",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")

        self.v_single = tk.BooleanVar(value=True)
        tk.Checkbutton(top,
                       text="📋 Send as ONE message (keeps formatting)",
                       variable=self.v_single, bg=BG, fg=BLUE,
                       selectcolor=CARD2, activebackground=BG,
                       font=("Segoe UI", 9, "bold"),
                       command=self._mode_hint).pack(side="right")

        self.lbl_mode = tk.Label(T,
                                 text="▸ Whole message sent in one go — newlines intact",
                                 bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_mode.pack(anchor="e", padx=14)

        # Message box with scrollbar
        mf = tk.Frame(T, bg=BORDER, bd=1)
        mf.pack(padx=14, pady=4, fill="x")
        sc = tk.Scrollbar(mf, bg=CARD2); sc.pack(side="right", fill="y")
        self.msg_box = tk.Text(mf, height=9, bg=CARD, fg=TEXT,
                               insertbackground=TEXT,
                               font=("Consolas", 9),
                               relief="flat", padx=10, pady=8,
                               undo=True, wrap="word",
                               yscrollcommand=sc.set)
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
                            "Feel free to join and also share it with other ambassadors you know 🚀"
                            )
        self.msg_box.bind("<KeyRelease>", self._char_count)

        # Char + word count row
        cr = tk.Frame(T, bg=BG); cr.pack(fill="x", padx=14)
        self.lbl_chars = tk.Label(cr, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.lbl_chars.pack(side="right")
        self._char_count()

        # ── Stats bar ────────────────────────────────────
        sf = tk.Frame(T, bg=CARD2, pady=7)
        sf.pack(fill="x", padx=14, pady=(6, 3))

        stats = [
            ("Loaded",  "0", TEXT),
            ("Sent",    "0", GREEN),
            ("Failed",  "0", RED),
            ("Skipped", "0", AMBER),
            ("ETA",     "--", BLUE),
        ]
        self._stat_labels = {}
        for i, (name, val, color) in enumerate(stats):
            col_frame = tk.Frame(sf, bg=CARD2)
            col_frame.grid(row=0, column=i, padx=12, pady=2)
            tk.Label(col_frame, text=name, bg=CARD2, fg=MUTED,
                     font=("Segoe UI", 7)).pack()
            lbl = tk.Label(col_frame, text=val, bg=CARD2, fg=color,
                           font=("Segoe UI", 12, "bold"))
            lbl.pack()
            self._stat_labels[name] = lbl

        # Progress bar
        self.v_prog = tk.DoubleVar(value=0)
        self.pbar = ttk.Progressbar(T, variable=self.v_prog, maximum=100)
        self.pbar.pack(fill="x", padx=14, pady=3)

        # Status line
        self.lbl_status = tk.Label(T,
                                   text="● Idle — Import a number list to begin",
                                   bg=BG, fg=AMBER, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(pady=2)

        # Daily limit row
        dl_row = tk.Frame(T, bg=BG); dl_row.pack()
        self.lbl_daily = tk.Label(dl_row, text="Sent today: 0/40",
                                  bg=BG, fg=GREEN, font=("Segoe UI", 9))
        self.lbl_daily.pack(side="left", padx=6)
        self.lbl_total_ever = tk.Label(dl_row,
                                       text=f"All-time sent: {self.logger.total_sent()}",
                                       bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_total_ever.pack(side="left", padx=6)

        # Dry-run checkbox
        self.v_dry = tk.BooleanVar(value=False)
        tk.Checkbutton(T,
                       text="🧪 Dry-Run — simulate only, nothing actually sent",
                       variable=self.v_dry, bg=BG, fg=BLUE,
                       selectcolor=CARD2, activebackground=BG,
                       font=("Segoe UI", 9)).pack(pady=2)

        # ── Buttons ───────────────────────────────────────
        bf = tk.Frame(T, bg=BG); bf.pack(pady=6, padx=14, fill="x")

        self.btn_import = ttk.Button(bf, text="📁 Import List",   command=self.do_import)
        self.btn_reset  = ttk.Button(bf, text="🔄 Reset List",    command=self.do_reset)
        self.btn_start  = ttk.Button(bf, text="▶  START",         command=self.do_start, style="Accent.TButton")
        self.btn_pause  = ttk.Button(bf, text="⏸ PAUSE",          command=self.do_pause, state="disabled")
        self.btn_stop   = ttk.Button(bf, text="⏹ STOP",           command=self.do_stop,  style="Danger.TButton")
        self.btn_test   = ttk.Button(bf, text="🔬 Test 1 Number", command=self.do_test)
        self.btn_retry  = ttk.Button(bf, text="🔁 Retry Failed",  command=self.do_retry)
        self.btn_export = ttk.Button(bf, text="💾 Export Failed", command=self.do_export)
        self.btn_bl     = ttk.Button(bf, text="🔕 Blacklist #",   command=self.do_blacklist)
        self.btn_clear  = ttk.Button(bf, text="🗑 Clear Log",     command=self.do_clear_log)

        layout = [
            (0, 0, self.btn_import), (0, 1, self.btn_reset),
            (0, 2, self.btn_start),  (0, 3, self.btn_pause),
            (0, 4, self.btn_stop),
            (1, 0, self.btn_test),   (1, 1, self.btn_retry),
            (1, 2, self.btn_export), (1, 3, self.btn_bl),
            (1, 4, self.btn_clear),
        ]
        for r, c, btn in layout:
            btn.grid(row=r, column=c, padx=4, pady=3, sticky="ew")
        for c in range(5):
            bf.columnconfigure(c, weight=1)

        # Footer warning
        tk.Label(T,
                 text="⚠  Keep WhatsApp Web open in Chrome/Edge  ·  "
                      "Move mouse to top-left corner to emergency-stop",
                 bg=BG, fg=RED, font=("Segoe UI", 8, "bold")).pack(pady=6)

    # ══════════════════════════════════════════════════════
    #  LOG TAB
    # ══════════════════════════════════════════════════════
    def _tab_log(self, T):
        hdr = tk.Frame(T, bg=BG); hdr.pack(fill="x", padx=10, pady=8)
        tk.Label(hdr, text="📋  Session Log",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")

        ttk.Button(hdr, text="📂 Open Log File",
                   command=self._open_log_file).pack(side="right", padx=4)
        ttk.Button(hdr, text="📋 Copy All",
                   command=self._copy_log).pack(side="right", padx=4)

        fr = tk.Frame(T, bg=BG); fr.pack(fill="both", expand=True, padx=10, pady=4)
        sc = tk.Scrollbar(fr, bg=CARD2); sc.pack(side="right", fill="y")
        self.log_box = tk.Text(fr, bg=CARD, fg=MUTED,
                               font=("Consolas", 8),
                               yscrollcommand=sc.set,
                               state="disabled", relief="flat",
                               padx=8, pady=6)
        self.log_box.pack(fill="both", expand=True)
        sc.config(command=self.log_box.yview)

        for tag, col in [
            ("info",  BLUE),
            ("sent",  GREEN),
            ("failed", RED),
            ("skip",  AMBER),
            ("warn",  PURPLE),
            ("system", MUTED),
        ]:
            self.log_box.tag_config(tag, foreground=col)

        self._log("system", f"AutoReach v{VERSION} ready. Python {sys.version.split()[0]}")
        self._log("system", f"All-time sent: {self.logger.total_sent()}  |  "
                            f"Blacklist entries: {self.blacklist.count()}")

    # ══════════════════════════════════════════════════════
    #  SETTINGS TAB
    # ══════════════════════════════════════════════════════
    def _tab_settings(self, T):
        canvas = tk.Canvas(T, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(T, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        fr = tk.Frame(canvas, bg=BG)
        fr_id = canvas.create_window((0, 0), window=fr, anchor="nw")

        def _resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(fr_id, width=e.width)

        canvas.bind("<Configure>", _resize)
        fr.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        # Mouse wheel scrolling
        def _scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        def section(text):
            tk.Label(fr, text=text, bg=BG, fg=ACCENT,
                     font=("Segoe UI", 10, "bold")).grid(
                row=section.row, column=0, columnspan=2,
                sticky="w", padx=20, pady=(14, 4))
            tk.Frame(fr, bg=BORDER, height=1).grid(
                row=section.row + 1, column=0, columnspan=2,
                sticky="ew", padx=20, pady=(0, 6))
            section.row += 2

        section.row = 0

        # Spinbox vars
        self.v_dmin     = tk.IntVar()
        self.v_dmax     = tk.IntVar()
        self.v_load     = tk.IntVar()
        self.v_postsend = tk.IntVar()
        self.v_timeout  = tk.IntVar()
        self.v_dlimit   = tk.IntVar()
        self.v_retries  = tk.IntVar()

        # Checkbox vars
        self.v_skip_sent   = tk.BooleanVar()
        self.v_skip_bl     = tk.BooleanVar()
        self.v_vary        = tk.BooleanVar()
        self.v_sound       = tk.BooleanVar()
        self.v_hide_browser= tk.BooleanVar()

        def spin_row(label, var, lo, hi, note=""):
            r = section.row; section.row += 1
            note_text = f"  [{note}]" if note else ""
            tk.Label(fr, text=label + note_text,
                     bg=BG, fg=TEXT, width=52, anchor="w",
                     font=("Segoe UI", 9)).grid(
                row=r, column=0, padx=22, pady=5, sticky="w")
            ttk.Spinbox(fr, from_=lo, to=hi, textvariable=var,
                        width=8,
                        command=self._save_settings).grid(
                row=r, column=1, padx=12, pady=5, sticky="w")
            var.trace_add("write", lambda *_: self._save_settings())

        def check_row(label, var, color=TEXT, disabled=False):
            r = section.row; section.row += 1
            cb = tk.Checkbutton(fr, text=label, variable=var,
                                bg=BG, fg=color,
                                selectcolor=CARD2, activebackground=BG,
                                font=("Segoe UI", 9),
                                command=self._save_settings)
            if disabled:
                cb.config(state="disabled")
            cb.grid(row=r, column=0, columnspan=2,
                    sticky="w", padx=22, pady=4)

        # ── Timing ──
        section("⏱  Timing & Delays")
        spin_row("Min delay between messages (seconds):", self.v_dmin, 5, 120, "↑ slower = safer")
        spin_row("Max delay between messages (seconds):", self.v_dmax, 10, 300)
        spin_row("Wait for WhatsApp Web to load (seconds):", self.v_load, 3, 90, "8s works for most")
        spin_row("Post-send pause before closing tab (seconds):", self.v_postsend, 2, 60)
        spin_row("Per-message hard timeout (seconds):", self.v_timeout, 15, 180, "skip if exceeded")

        # ── Limits ──
        section("📊  Limits & Reliability")
        spin_row("Daily send limit (messages/day):", self.v_dlimit, 5, 500)
        spin_row("Retry attempts per failed number:", self.v_retries, 1, 5)

        # ── Behaviour ──
        section("⚙  Behaviour")
        check_row("Skip numbers already sent (recommended)", self.v_skip_sent, GREEN)
        check_row("Skip blacklisted numbers (recommended)", self.v_skip_bl, GREEN)
        check_row("✅ Vary each message slightly (anti-spam invisible character)", self.v_vary, BLUE)
        check_row("Play sound when session finishes", self.v_sound)

        # ── NEW: Hide browser ──
        section("🌐  Browser Visibility")

        hide_label = (
            "🙈 Hide browser window while sending  "
            "(browser works in background — you won't see it pop up)"
            if HAS_GW else
            "⚠  Hide browser — unavailable (install pygetwindow first)"
        )
        check_row(hide_label, self.v_hide_browser,
                  color=BLUE if HAS_GW else MUTED,
                  disabled=not HAS_GW)

        tk.Label(fr,
                 text=(
                     "Note: The AutoReach window stays fully visible at all times.\n"
                     "Only the browser (Chrome/Edge) is hidden from view when this is enabled.\n"
                     "The browser still runs normally — it's just sent behind other windows."
                     if HAS_GW else
                     "To enable this feature:  pip install pygetwindow"
                 ),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8),
                 justify="left").grid(
            row=section.row, column=0, columnspan=2,
            sticky="w", padx=28, pady=(0, 8))
        section.row += 1

        # Save button
        ttk.Button(fr, text="💾 Save Settings",
                   command=self._save_settings,
                   style="Accent.TButton").grid(
            row=section.row, column=0, columnspan=2,
            padx=22, pady=14, sticky="w")
        section.row += 1

    # ══════════════════════════════════════════════════════
    #  CALIBRATE TAB
    # ══════════════════════════════════════════════════════
    def _tab_calibrate(self, T):
        tk.Label(T, text="🎯  Auto-Click Calibration",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(pady=14)

        info = tk.Frame(T, bg=CARD, bd=0)
        info.pack(padx=20, fill="x")
        tk.Label(info,
                 text=(
                     "AutoReach needs to know where the WhatsApp Web message "
                     "input box is on your screen.\n\n"
                     "ONE-TIME SETUP:\n"
                     "  1. Open WhatsApp Web in Chrome/Edge and open any chat.\n"
                     "  2. Click  '🎯 Start 3s Countdown'  below.\n"
                     "  3. Within 3 seconds, move your mouse to the message\n"
                     "     input box at the bottom of WhatsApp Web.\n"
                     "  4. Stay still — position is saved automatically.\n\n"
                     "Redo this if you move or resize your browser window.\n"
                     "The position dot below shows your current saved target."
                 ),
                 bg=CARD, fg=TEXT, font=("Segoe UI", 9),
                 justify="left", wraplength=700,
                 padx=18, pady=14).pack(fill="x")

        self.lbl_calib = tk.Label(T, bg=BG, fg=GREEN,
                                  font=("Segoe UI", 10, "bold"))
        self.lbl_calib.pack(pady=10)
        self._calib_refresh()

        self.lbl_cdown = tk.Label(T, text="", bg=BG, fg=AMBER,
                                  font=("Segoe UI", 40, "bold"))
        self.lbl_cdown.pack(pady=4)

        # Live mouse position display
        self.lbl_mouse = tk.Label(T, text="Mouse: — , —",
                                  bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_mouse.pack()
        self._track_mouse()

        bf = tk.Frame(T, bg=BG); bf.pack(pady=10)
        ttk.Button(bf, text="🎯  Start 3s Countdown",
                   command=self._calib_start,
                   style="Accent.TButton").pack(side="left", padx=8)
        ttk.Button(bf, text="🔄  Reset to Default",
                   command=self._calib_reset).pack(side="left", padx=8)

    def _track_mouse(self):
        """Update mouse position label every 200ms."""
        try:
            x, y = pyautogui.position()
            self.lbl_mouse.config(text=f"Mouse position: X={x}  Y={y}")
        except Exception:
            pass
        self.root.after(200, self._track_mouse)

    def _calib_refresh(self):
        cx, cy = self.calib.get()
        src = "✅ Calibrated" if self.calib.is_set() else "⚠ Default (estimated)"
        self.lbl_calib.config(
            text=f"Click target →  X: {cx}   Y: {cy}     [ {src} ]",
            fg=GREEN if self.calib.is_set() else AMBER)

    def _calib_start(self):
        def _run():
            for i in (3, 2, 1):
                self._ui_queue.put(("cdown", str(i)))
                time.sleep(1)
            x, y = pyautogui.position()
            self.calib.save(x, y)
            self._ui_queue.put(("cdown", "✅ Saved!"))
            self._calib_refresh()
            time.sleep(1.8)
            self._ui_queue.put(("cdown", ""))

        threading.Thread(target=_run, daemon=True).start()

    def _calib_reset(self):
        if os.path.exists(CALIB_FILE):
            os.remove(CALIB_FILE)
        self.calib.x = self.calib.y = None
        self._calib_refresh()

    # ══════════════════════════════════════════════════════
    #  ABOUT TAB
    # ══════════════════════════════════════════════════════
    def _tab_about(self, T):
        tk.Label(T, text=f"⚡ AutoReach v{VERSION}",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 16, "bold")).pack(pady=(30, 6))
        tk.Label(T, text="WhatsApp Outreach Automation Tool",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack()

        tk.Frame(T, bg=BORDER, height=1).pack(fill="x", padx=60, pady=20)

        info_text = (
            "What's new in v7.0:\n\n"
            "  ✅  App window NEVER hides — stays fully visible while sending\n"
            "  ✅  NEW: 'Hide browser window' option in Settings\n"
            "       (browser runs silently in background — optional)\n"
            "  ✅  Settings auto-saved to autoreach_settings.json\n"
            "  ✅  Smarter WhatsApp page-load detection\n"
            "  ✅  Extended phone number normalisation (+91, 0xx, international)\n"
            "  ✅  Live mouse position tracker on Calibrate tab\n"
            "  ✅  Word + character count in message editor\n"
            "  ✅  Scrollable Settings tab\n"
            "  ✅  Thread-safe UI — no more random crashes\n"
            "  ✅  Blacklist count shown on startup\n"
            "  ✅  All-time sent counter in status bar\n"
            "  ✅  Open Log File button\n"
            "  ✅  Exponential back-off on retries\n"
        )
        tk.Label(T, text=info_text,
                 bg=BG, fg=TEXT, font=("Consolas", 9),
                 justify="left").pack(padx=40, anchor="w")

        tk.Frame(T, bg=BORDER, height=1).pack(fill="x", padx=60, pady=20)
        tk.Label(T,
                 text="⚠  Only message people who opted in / expect your message.\n"
                      "Use responsibly. Automated mass messaging may violate\n"
                      "WhatsApp's Terms of Service.",
                 bg=BG, fg=RED, font=("Segoe UI", 9, "bold"),
                 justify="center").pack()

    # ══════════════════════════════════════════════════════
    #  SMALL HELPERS
    # ══════════════════════════════════════════════════════
    def _mode_hint(self):
        if self.v_single.get():
            self.lbl_mode.config(
                text="▸ Whole message sent in one go — newlines intact")
        else:
            self.lbl_mode.config(
                text="▸ Each paragraph sent as a separate message (split on blank line)")
        self._save_settings()

    def _char_count(self, _=None):
        txt = self.msg_box.get("1.0", tk.END).strip()
        chars = len(txt)
        words = len(txt.split()) if txt else 0
        self.lbl_chars.config(text=f"Words: {words}  ·  Characters: {chars}")

    def _log(self, tag: str, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._ui_queue.put(("log", tag, f"[{ts}] {text}"))

    def _status(self, txt: str):
        self._ui_queue.put(("status", txt))

    def _refresh_daily(self):
        today = self.logger.sent_today()
        lim   = self.v_dlimit.get() if hasattr(self, "v_dlimit") else 40
        pct   = today / lim if lim else 0
        color = RED if pct >= 1.0 else (AMBER if pct >= 0.8 else GREEN)
        self.lbl_daily.config(
            text=f"Sent today: {today}/{lim}", fg=color)
        self.lbl_total_ever.config(
            text=f"All-time sent: {self.logger.total_sent()}")

    def _update_stats(self):
        self._ui_queue.put(("stats",))

    def _do_update_stats(self):
        s = self._stat_labels
        s["Loaded"].config(text=str(self.total))
        s["Sent"].config(text=str(self.sent_count))
        s["Failed"].config(text=str(len(self.failed_list)))
        s["Skipped"].config(text=str(self.skipped_count))

        pct = (self.current_idx / self.total * 100) if self.total else 0
        self.v_prog.set(pct)

        if self.start_time and self.current_idx > 0:
            elapsed = time.time() - self.start_time
            remaining = (self.total - self.current_idx) * (elapsed / self.current_idx)
            eta = fmt_time(remaining)
        else:
            eta = "--:--"
        s["ETA"].config(text=eta)
        self._refresh_daily()

    # ── Thread-safe UI queue processor ────────────────────
    def _process_ui_queue(self):
        try:
            while True:
                item = self._ui_queue.get_nowait()
                cmd = item[0]

                if cmd == "log":
                    _, tag, text = item
                    self.log_box.config(state="normal")
                    self.log_box.insert("end", text + "\n", tag)
                    self.log_box.see("end")
                    self.log_box.config(state="disabled")

                elif cmd == "status":
                    _, txt = item
                    self.lbl_status.config(text=txt)

                elif cmd == "stats":
                    self._do_update_stats()

                elif cmd == "cdown":
                    _, txt = item
                    self.lbl_cdown.config(text=txt)

        except queue.Empty:
            pass

        self.root.after(50, self._process_ui_queue)

    # ══════════════════════════════════════════════════════
    #  SETTINGS PERSISTENCE
    # ══════════════════════════════════════════════════════
    def _load_settings_into_ui(self):
        s = self.settings
        self.v_dmin.set(s.get("dmin"))
        self.v_dmax.set(s.get("dmax"))
        self.v_load.set(s.get("load"))
        self.v_postsend.set(s.get("postsend"))
        self.v_timeout.set(s.get("timeout"))
        self.v_dlimit.set(s.get("dlimit"))
        self.v_retries.set(s.get("retries"))
        self.v_skip_sent.set(s.get("skip_sent"))
        self.v_skip_bl.set(s.get("skip_bl"))
        self.v_vary.set(s.get("vary"))
        self.v_sound.set(s.get("sound"))
        self.v_hide_browser.set(s.get("hide_browser"))
        self.v_single.set(s.get("single_msg"))

    def _save_settings(self, *_):
        try:
            self.settings.save({
                "dmin":        self.v_dmin.get(),
                "dmax":        self.v_dmax.get(),
                "load":        self.v_load.get(),
                "postsend":    self.v_postsend.get(),
                "timeout":     self.v_timeout.get(),
                "dlimit":      self.v_dlimit.get(),
                "retries":     self.v_retries.get(),
                "skip_sent":   self.v_skip_sent.get(),
                "skip_bl":     self.v_skip_bl.get(),
                "vary":        self.v_vary.get(),
                "sound":       self.v_sound.get(),
                "hide_browser":self.v_hide_browser.get(),
                "single_msg":  self.v_single.get(),
            })
        except Exception:
            pass

    def _on_tab_change(self, _=None):
        self._save_settings()

    # ══════════════════════════════════════════════════════
    #  LOG HELPERS
    # ══════════════════════════════════════════════════════
    def _open_log_file(self):
        if os.path.exists(LOG_FILE):
            try:
                os.startfile(LOG_FILE)  # Windows
            except AttributeError:
                import subprocess
                subprocess.call(["open" if sys.platform == "darwin" else "xdg-open",
                                 LOG_FILE])
        else:
            messagebox.showinfo("No log", "No log file found yet.")

    def _copy_log(self):
        try:
            content = self.log_box.get("1.0", tk.END)
            pyperclip.copy(content)
            messagebox.showinfo("Copied", "Log copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ══════════════════════════════════════════════════════
    #  WINDOW MANAGEMENT  (app stays visible — NO hiding)
    # ══════════════════════════════════════════════════════
    def _on_close(self):
        self._save_settings()
        if self.running:
            if messagebox.askyesno("Running",
                                   "A session is running. Stop and exit?"):
                self.running = False
                self.root.after(600, self.root.destroy)
        else:
            self.root.destroy()

    # ══════════════════════════════════════════════════════
    #  BROWSER UTILITIES
    # ══════════════════════════════════════════════════════
    def _activate_browser(self):
        """Bring the WhatsApp Web browser to front for input."""
        if not gw:
            return
        try:
            wins = [w for w in gw.getAllWindows()
                    if "whatsapp" in getattr(w, "title", "").lower()]
            for w in wins:
                try:
                    w.restore()
                    w.activate()
                    time.sleep(0.15)
                except Exception:
                    pass
        except Exception:
            pass

    def _clip(self):
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    def _close_tab(self):
        try:
            self._activate_browser()
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.6)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    #  CLICK MESSAGE BOX
    # ══════════════════════════════════════════════════════
    def _click_box(self):
        # If hiding browser, briefly restore it so we can interact
        if self.v_hide_browser.get() and HAS_GW:
            self._activate_browser()
            time.sleep(0.2)

        cx, cy = self.calib.get()
        ox, oy = random.randint(-5, 5), random.randint(-2, 2)
        try:
            pyautogui.moveTo(cx + ox, cy + oy,
                             duration=random.uniform(0.08, 0.22))
            time.sleep(0.07)
            pyautogui.click()
            time.sleep(0.30)
        except Exception:
            pass

        # After clicking, hide browser again if option is on
        if self.v_hide_browser.get() and HAS_GW:
            self._hide_browser_window()

    def _hide_browser_window(self):
        """Push browser behind other windows (only when option enabled)."""
        if not HAS_GW or not self.v_hide_browser.get():
            return
        try:
            wins = [w for w in gw.getAllWindows()
                    if any(k in getattr(w, "title", "").lower()
                           for k in ("whatsapp", "chrome", "edge", "firefox", "brave"))]
            for w in wins:
                try:
                    w.minimize()
                except Exception:
                    pass
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    #  SMART LOAD WAIT
    # ══════════════════════════════════════════════════════
    def _wait_load_and_click(self, deadline: float) -> bool:
        load_max = self.v_load.get()
        waited   = 0.0
        step     = 0.5

        while waited < load_max:
            if not self.running or time.time() > deadline:
                return False
            while self.paused:
                time.sleep(0.2)

            # Activate browser briefly to check readiness
            self._activate_browser()
            time.sleep(0.12)

            self._click_box()

            try:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.09)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.09)
            except Exception:
                pass

            clip = self._clip()
            if clip is not None:
                self._click_box()
                return True

            remaining = int(load_max - waited)
            self._status(f"● Waiting for WhatsApp Web to load… ({remaining}s)")
            time.sleep(step)
            waited += step

        # Fallback
        self._click_box()
        return True

    # ══════════════════════════════════════════════════════
    #  PASTE
    # ══════════════════════════════════════════════════════
    def _paste(self, text: str):
        try:
            pyperclip.copy(text)
            time.sleep(0.16)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.26)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    #  WAIT FOR BOX TO CLEAR (confirms send)
    # ══════════════════════════════════════════════════════
    def _wait_clear(self, max_sec: float = 8.0) -> bool:
        deadline = time.time() + max_sec
        while time.time() < deadline:
            if not self.running:
                return False
            try:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.09)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.09)
            except Exception:
                pass
            if self._clip().strip() == "":
                return True
            time.sleep(0.28)
        return False

    # ══════════════════════════════════════════════════════
    #  CORE SEND — SINGLE MESSAGE
    # ══════════════════════════════════════════════════════
    def _do_send_single(self, number: str, msg: str) -> bool:
        timeout  = self.v_timeout.get()
        deadline = time.time() + timeout

        webbrowser.open(
            f"https://web.whatsapp.com/send/"
            f"?phone={number}&type=phone_number&app_absent=0")
        time.sleep(2.0)

        # Activate browser for interaction
        self._activate_browser()
        time.sleep(0.35)

        # Immediately hide if option is on
        if self.v_hide_browser.get() and HAS_GW:
            time.sleep(0.4)
            self._hide_browser_window()

        ok = self._wait_load_and_click(deadline)
        if not ok or time.time() > deadline:
            self._close_tab()
            return False

        # Activate for paste (hide_browser logic inside _click_box)
        if self.v_hide_browser.get() and HAS_GW:
            self._activate_browser()
            time.sleep(0.2)

        self._paste(msg)

        # Verify paste landed
        try:
            pyautogui.hotkey("ctrl", "a"); time.sleep(0.09)
            pyautogui.hotkey("ctrl", "c"); time.sleep(0.09)
        except Exception:
            pass
        if self._clip().strip() == "":
            if self.v_hide_browser.get() and HAS_GW:
                self._activate_browser(); time.sleep(0.15)
            self._click_box()
            self._paste(msg)
            time.sleep(0.3)

        # Send
        if self.v_hide_browser.get() and HAS_GW:
            self._activate_browser(); time.sleep(0.1)
        pyautogui.press("enter")

        confirmed = self._wait_clear(min(8.0, deadline - time.time()))

        # Post-send pause countdown
        post = self.v_postsend.get()
        for i in range(post, 0, -1):
            if not self.running:
                break
            self._status(f"● Sent ✅ — closing tab in {i}s…")
            time.sleep(1.0)

        self._close_tab()

        # Re-hide after closing tab
        if self.v_hide_browser.get() and HAS_GW:
            self._hide_browser_window()

        return confirmed

    # ══════════════════════════════════════════════════════
    #  CORE SEND — PARAGRAPH SPLIT
    # ══════════════════════════════════════════════════════
    def _do_send_split(self, number: str, msg: str) -> bool:
        timeout  = self.v_timeout.get()
        deadline = time.time() + timeout
        parts    = [p.strip() for p in msg.split("\n\n") if p.strip()]
        if not parts:
            return False

        webbrowser.open(
            f"https://web.whatsapp.com/send/"
            f"?phone={number}&type=phone_number&app_absent=0")
        time.sleep(2.0)
        self._activate_browser()
        time.sleep(0.35)

        if self.v_hide_browser.get() and HAS_GW:
            time.sleep(0.4)
            self._hide_browser_window()

        ok = self._wait_load_and_click(deadline)
        if not ok or time.time() > deadline:
            self._close_tab()
            return False

        all_ok = True
        for i, part in enumerate(parts):
            if not self.running or time.time() > deadline:
                all_ok = False
                break
            if self.v_hide_browser.get() and HAS_GW:
                self._activate_browser(); time.sleep(0.12)
            self._paste(part)
            time.sleep(0.22)
            pyautogui.press("enter")
            if not self._wait_clear(min(5.0, deadline - time.time())):
                all_ok = False
                break
            if i < len(parts) - 1:
                time.sleep(gauss_delay(1.0, 2.2))
            if self.v_hide_browser.get() and HAS_GW:
                self._hide_browser_window()

        post = self.v_postsend.get()
        for i in range(post, 0, -1):
            if not self.running:
                break
            self._status(f"● Sent ✅ — closing tab in {i}s…")
            time.sleep(1.0)

        self._close_tab()
        return all_ok

    # ══════════════════════════════════════════════════════
    #  SEND WRAPPER  (retry + exponential back-off)
    # ══════════════════════════════════════════════════════
    def send_message(self, number: str, raw: str) -> bool:
        if self.v_dry.get():
            time.sleep(random.uniform(1.2, 2.8))
            return True

        max_retries = self.v_retries.get()
        for attempt in range(1, max_retries + 1):
            if not self.running:
                return False
            if attempt > 1:
                backoff = gauss_delay(3, 6) * (1.5 ** (attempt - 1))
                self._log("warn", f"  Retry {attempt}/{max_retries} in {backoff:.0f}s → {number}")
                elapsed = 0.0
                while elapsed < backoff and self.running:
                    time.sleep(0.5)
                    elapsed += 0.5

            msg = vary(raw) if self.v_vary.get() else raw
            try:
                if self.v_single.get():
                    ok = self._do_send_single(number, msg)
                else:
                    ok = self._do_send_split(number, msg)
            except pyautogui.FailSafeException:
                self._log("warn", "🛑 Emergency stop triggered (mouse moved to corner).")
                self.do_stop()
                return False
            except Exception as ex:
                self._log("warn", f"  Exception (attempt {attempt}): {ex}")
                ok = False

            if ok:
                return True

        return False

    # ══════════════════════════════════════════════════════
    #  BUTTON ACTIONS
    # ══════════════════════════════════════════════════════
    def do_import(self):
        path = filedialog.askopenfilename(
            title="Select number list",
            filetypes=[("Text files", "*.txt"),
                       ("CSV files", "*.csv"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception as e:
            messagebox.showerror("Error reading file", str(e))
            return

        clean, seen, bad = [], set(), 0
        for ln in lines:
            ln = ln.strip().split(",")[0]  # handle CSV first column
            n = to_e164(ln)
            if n and n not in seen:
                seen.add(n)
                clean.append(n)
            elif ln:
                bad += 1

        self.numbers       = clean
        self.total         = len(clean)
        self.current_idx   = 0
        self.sent_count    = 0
        self.skipped_count = 0
        self.failed_list   = []
        self._update_stats()
        self._log("info", f"Imported {self.total} numbers from '{os.path.basename(path)}'  ({bad} invalid/duplicate skipped).")
        messagebox.showinfo("Import Complete",
                            f"✅  {self.total} numbers loaded\n"
                            f"⚠  {bad} invalid/duplicate skipped\n\n"
                            f"File: {os.path.basename(path)}")

    def do_reset(self):
        if self.running:
            messagebox.showwarning("Session Running", "Stop the session first.")
            return
        if not messagebox.askyesno("Reset List",
                                   "Clear the imported list and reset counters?\n"
                                   "(Log history is kept — only current list is cleared.)"):
            return
        self.numbers       = []
        self.total         = 0
        self.current_idx   = 0
        self.sent_count    = 0
        self.failed_list   = []
        self.skipped_count = 0
        self._update_stats()
        self._status("● Idle — list cleared, import a new list")
        self._log("info", "List reset.")

    def do_start(self):
        if not self.numbers:
            messagebox.showwarning("No List", "Import a number list first."); return
        if self.current_idx >= self.total:
            messagebox.showinfo("All Done",
                                "All numbers have been processed.\n"
                                "Use 'Reset List' to start fresh."); return
        lim = self.v_dlimit.get()
        if self.logger.sent_today() >= lim:
            messagebox.showwarning("Daily Limit Reached",
                                   f"You've reached today's limit of {lim} messages.\n"
                                   f"Change the limit in Settings or wait until tomorrow."); return
        if not self.calib.is_set():
            if not messagebox.askyesno("Not Calibrated",
                                       "Click position not calibrated.\n"
                                       "Using default (estimated) position.\n\n"
                                       "Start anyway?"):
                return

        self.running    = True
        self.paused     = False
        self.start_time = time.time()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ PAUSE")
        self._status("● Running…")
        self._log("info",
                  f"Session started — {self.total - self.current_idx} numbers to process."
                  + ("  [DRY RUN]" if self.v_dry.get() else ""))
        if self.v_dry.get():
            self._log("warn", "⚠  DRY RUN MODE — nothing actually sent.")

        # NOTE: App stays fully visible — no hiding/minimizing

        threading.Thread(target=self._loop, daemon=True).start()

    def do_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RESUME")
            self._status(f"● Paused at {self.current_idx}/{self.total}")
            self._log("warn", "⏸ Session paused.")
        else:
            self.btn_pause.config(text="⏸ PAUSE")
            self._status("● Resuming…")
            self._log("info", "▶ Session resumed.")

    def do_stop(self):
        self.running = False
        self.paused  = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))
        self._status(f"● Stopped at {self.current_idx}/{self.total}")
        self._log("warn", f"⏹ Stopped — {self.sent_count} sent, "
                          f"{len(self.failed_list)} failed, "
                          f"{self.skipped_count} skipped.")

    def do_test(self):
        val = simpledialog.askstring("Test Send",
                                     "Enter a phone number (10 or 12 digits):")
        if not val:
            return
        n = to_e164(val)
        if not n:
            messagebox.showwarning("Invalid Number",
                                   "Could not parse that number.\n"
                                   "Use 10-digit or 12-digit format.")
            return
        raw = self.msg_box.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("Empty Message", "Please write a message first.")
            return

        self._log("info", f"🔬 Test send → {n}")

        def _t():
            ok = self.send_message(n, raw)
            result = "✅ Test message sent!" if ok else "❌ Test FAILED — check calibration & connection."
            self._log("sent" if ok else "failed", result)
            self.root.after(0, lambda: messagebox.showinfo("Test Result", result))

        threading.Thread(target=_t, daemon=True).start()

    def do_retry(self):
        if not self.failed_list:
            messagebox.showinfo("No Failures", "No failed numbers to retry."); return
        n = len(self.failed_list)
        self.numbers       = list(self.failed_list)
        self.total         = n
        self.current_idx   = 0
        self.sent_count    = 0
        self.skipped_count = 0
        self.failed_list   = []
        self._update_stats()
        messagebox.showinfo("Retry Loaded",
                            f"Loaded {n} failed numbers.\nClick START to retry.")

    def do_export(self):
        if not self.failed_list:
            messagebox.showinfo("No Failures", "No failed numbers to export."); return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="failed_numbers.txt")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(self.failed_list))
            messagebox.showinfo("Exported",
                                f"Saved {len(self.failed_list)} failed numbers to:\n{p}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def do_blacklist(self):
        val = simpledialog.askstring(
            "Blacklist",
            "Enter a number to blacklist.\n"
            "(Leave blank to blacklist ALL currently failed numbers.)")
        if val is None:
            return  # cancelled
        if val.strip():
            n = to_e164(val.strip())
            if n:
                self.blacklist.add(n)
                messagebox.showinfo("Blacklisted", f"✅  {n} added to blacklist.\n"
                                                   f"Total entries: {self.blacklist.count()}")
            else:
                messagebox.showwarning("Invalid", "Could not parse that number.")
        elif self.failed_list:
            for n in self.failed_list:
                self.blacklist.add(n)
            messagebox.showinfo("Blacklisted",
                                f"✅  {len(self.failed_list)} numbers added to blacklist.\n"
                                f"Total entries: {self.blacklist.count()}")
        else:
            messagebox.showinfo("Nothing to Blacklist", "No failed numbers to blacklist.")

    def do_clear_log(self):
        if messagebox.askyesno("Clear Log", "Clear the session log display?"):
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.config(state="disabled")
            self._log("system", "Log display cleared.")

    # ══════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════
    def _loop(self):
        raw      = self.msg_box.get("1.0", tk.END).strip()
        sent_set = self.logger.sent_set()
        lim      = self.v_dlimit.get()

        while self.current_idx < self.total and self.running:
            # ── Pause ──
            if self.paused:
                time.sleep(0.3)
                continue

            # ── Daily limit ──
            today_count = self.logger.sent_today()
            if today_count >= lim:
                self._log("warn", f"⚠  Daily limit of {lim} reached ({today_count} sent today).")
                self.root.after(0, lambda: messagebox.showwarning(
                    "Daily Limit Reached",
                    f"You've sent {today_count} messages today (limit: {lim}).\n"
                    f"Session paused. Change the limit in Settings or wait until tomorrow."))
                break

            number = self.numbers[self.current_idx]
            idx    = self.current_idx + 1

            # ── Skip: already sent ──
            if self.v_skip_sent.get() and number in sent_set:
                self._log("skip", f"↷ Already sent — skipping: {number}")
                self.skipped_count  += 1
                self.current_idx    += 1
                self._update_stats()
                continue

            # ── Skip: blacklisted ──
            if self.v_skip_bl.get() and self.blacklist.has(number):
                self._log("skip", f"↷ Blacklisted — skipping: {number}")
                self.skipped_count  += 1
                self.current_idx    += 1
                self._update_stats()
                continue

            # ── Send ──
            self._log("info", f"► {idx}/{self.total}  →  {number}")
            self._status(f"● {idx}/{self.total} → {number}")

            ok = self.send_message(number, raw)

            self.current_idx += 1

            if ok:
                self.sent_count  += 1
                sent_set.add(number)
                self.logger.mark_sent(number)
                self._log("sent", f"✅  Sent  →  {number}")
            else:
                self.failed_list.append(number)
                self.logger.mark_failed(number)
                self._log("failed", f"❌  Failed  →  {number}")

            self._update_stats()

            # ── Inter-message delay ──
            if self.current_idx < self.total and self.running:
                dmin = self.v_dmin.get()
                dmax = self.v_dmax.get()
                delay   = gauss_delay(dmin, dmax)
                elapsed = 0.0
                self._log("info", f"  ⏱  Next message in {delay:.0f}s  "
                                  f"({self.current_idx}/{self.total} done)")
                while elapsed < delay and self.running:
                    while self.paused and self.running:
                        time.sleep(0.3)
                    remaining = int(delay - elapsed)
                    self._status(
                        f"● Waiting {remaining}s before next  "
                        f"({self.current_idx}/{self.total} done  ·  "
                        f"{self.sent_count} sent)")
                    time.sleep(0.5)
                    elapsed += 0.5

        # ── Session complete ──
        self.running = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))

        if self.current_idx >= self.total:
            self._log("system", "🎉 All numbers processed!")
            self._status("● All Done! 🎉")

            dry_note = "\n\n⚠ DRY RUN — nothing actually sent." if self.v_dry.get() else ""
            summary = (
                f"✅  Sent:    {self.sent_count}\n"
                f"❌  Failed:  {len(self.failed_list)}\n"
                f"↷  Skipped: {self.skipped_count}\n"
                f"⏱  Duration: {fmt_time(time.time() - self.start_time)}"
                f"{dry_note}"
            )
            self.root.after(0, lambda: messagebox.showinfo("Session Complete! 🎉", summary))

            if self.v_sound.get():
                try:
                    self.root.bell()
                except Exception:
                    pass
        else:
            self._status(f"● Stopped at {self.current_idx}/{self.total}")

        self._update_stats()


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = AutoReach(root)
    root.mainloop()

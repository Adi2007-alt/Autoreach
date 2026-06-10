# -*- coding: utf-8 -*-
"""
AutoReach v6.0 — WhatsApp Outreach Automation
Only message people who opted in / expect your message.

Install:  pip install pyautogui pyperclip pygetwindow pystray Pillow
Run:      python autoreach_v6.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import webbrowser, threading, time, random, os, json
import pyautogui, pyperclip
from datetime import datetime, timedelta

try:
    import pygetwindow as gw
except ImportError:
    gw = None

# pystray = true system-tray (hidden from taskbar)
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ─────────────────────────────────────────────────────────
VERSION        = "6.0"
LOG_FILE       = "autoreach_log.json"
BLACKLIST_FILE = "blacklist.txt"
CALIB_FILE     = "calibration.json"

BG     = "#0F1115"; CARD  = "#161A1F"; ACCENT = "#4F8CFF"
TEXT   = "#E6E6E6"; MUTED = "#9AA0A6"; GREEN  = "#22C55E"
RED    = "#EF4444"; AMBER = "#F59E0B"; BLUE   = "#60A5FA"

_INVISIBLE = ["\u200b","\u200c","\u200d","\u2060"]
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.04


# ═══════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════
def gauss_delay(mn, mx):
    return max(mn, min(mx, random.gauss((mn+mx)/2, (mx-mn)/4)))

def vary(text):
    w = text.split(" ")
    if len(w) < 4: return text
    w[random.randint(1,len(w)-2)] += random.choice(_INVISIBLE)
    return " ".join(w)

def to_e164(s):
    d = "".join(filter(str.isdigit, s))
    if len(d) == 10: d = "91" + d
    return d if len(d) == 12 else None


# ═══════════════════════════════════════════════════════════
#  LOGGER
# ═══════════════════════════════════════════════════════════
class Logger:
    def __init__(self):
        self.data = json.load(open(LOG_FILE, encoding="utf-8")) \
                    if os.path.exists(LOG_FILE) else {"sent":[],"failed":[]}

    def _save(self):
        json.dump(self.data, open(LOG_FILE,"w",encoding="utf-8"), indent=2)

    def mark_sent(self, n):
        self.data["sent"].append({"n":n,"t":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self._save()

    def mark_failed(self, n):
        self.data["failed"].append({"n":n,"t":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self._save()

    def sent_set(self):   return {e["n"] for e in self.data["sent"]}
    def sent_today(self):
        d = datetime.now().strftime("%Y-%m-%d")
        return sum(1 for e in self.data["sent"] if e["t"].startswith(d))


# ═══════════════════════════════════════════════════════════
#  BLACKLIST
# ═══════════════════════════════════════════════════════════
class Blacklist:
    def __init__(self):
        self.nums = {l.strip() for l in open(BLACKLIST_FILE,encoding="utf-8")} \
                    if os.path.exists(BLACKLIST_FILE) else set()

    def add(self, n):
        if n not in self.nums:
            self.nums.add(n)
            open(BLACKLIST_FILE,"a",encoding="utf-8").write(n+"\n")

    def has(self, n): return n in self.nums


# ═══════════════════════════════════════════════════════════
#  CALIBRATION  — where to click the WA input box
# ═══════════════════════════════════════════════════════════
class Calib:
    def __init__(self):
        self.x = self.y = None
        if os.path.exists(CALIB_FILE):
            try:
                d = json.load(open(CALIB_FILE))
                self.x, self.y = d.get("x"), d.get("y")
            except Exception: pass

    def save(self, x, y):
        self.x, self.y = x, y
        json.dump({"x":x,"y":y}, open(CALIB_FILE,"w"))

    def get(self):
        if self.x and self.y: return self.x, self.y
        sw, sh = pyautogui.size()
        return int(sw*0.50), int(sh*0.935)   # WA Web input default position


# ═══════════════════════════════════════════════════════════
#  TRAY ICON  (only if pystray + Pillow installed)
# ═══════════════════════════════════════════════════════════
def _make_tray_image(color="#4F8CFF"):
    img = Image.new("RGBA", (64,64), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    d.ellipse([4,4,60,60], fill=color)
    d.text((14,18), "AR", fill="white")
    return img


# ═══════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════
class AutoReach:
    def __init__(self, root):
        self.root = root
        self.root.title(f"AutoReach v{VERSION}")
        self.root.geometry("830x960")
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
        self._tray_icon    = None

        self.logger    = Logger()
        self.blacklist = Blacklist()
        self.calib     = Calib()

        self._style()
        self._build()
        self._refresh_daily()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── TTK style ──────────────────────────────────────────
    def _style(self):
        s = ttk.Style(); s.theme_use("clam")
        s.configure("TButton", background=CARD, foreground=TEXT,
                    font=("Segoe UI",9,"bold"), borderwidth=0)
        s.map("TButton", background=[("active", ACCENT)])
        s.configure("TNotebook",     background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=MUTED,
                    font=("Segoe UI",9), padding=[14,6])
        s.map("TNotebook.Tab",
              background=[("selected",ACCENT)], foreground=[("selected","#fff")])
        s.configure("Horizontal.TProgressbar",
                    troughcolor=CARD, background=ACCENT, borderwidth=0)

    # ── BUILD ──────────────────────────────────────────────
    def _build(self):
        hdr = tk.Frame(self.root, bg="#111827", height=62)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text=f"🚀 AutoReach v{VERSION}",
                 fg=ACCENT, bg="#111827",
                 font=("Segoe UI",17,"bold")).pack(side="left",padx=18,pady=10)
        tk.Label(hdr, text="WhatsApp Outreach · Fully Automated",
                 fg=MUTED, bg="#111827",
                 font=("Segoe UI",9)).pack(side="left",pady=18)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=8)
        tabs = {n: tk.Frame(nb, bg=BG)
                for n in ("Send","Log","Settings","Calibrate")}
        for name, frm in tabs.items():
            nb.add(frm, text=f"  {name}  ")

        self._tab_send(tabs["Send"])
        self._tab_log(tabs["Log"])
        self._tab_settings(tabs["Settings"])
        self._tab_calibrate(tabs["Calibrate"])

    # ══════════════════════════════════════════════════════
    #  SEND TAB
    # ══════════════════════════════════════════════════════
    def _tab_send(self, T):
        # ── label row  +  single-send toggle ──
        top = tk.Frame(T, bg=BG)
        top.pack(fill="x", padx=15, pady=(10,2))
        tk.Label(top, text="Message Template",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI",11,"bold")).pack(side="left")
        self.v_single = tk.BooleanVar(value=True)
        tk.Checkbutton(top,
                       text="📋 Send as ONE message (preserve formatting)",
                       variable=self.v_single, bg=BG, fg=BLUE,
                       selectcolor=CARD, font=("Segoe UI",9,"bold"),
                       command=self._mode_hint).pack(side="right")

        # mode hint
        self.lbl_mode = tk.Label(T,
            text="▸ Whole message sent in one go — newlines kept intact",
            bg=BG, fg=MUTED, font=("Segoe UI",8))
        self.lbl_mode.pack(anchor="e", padx=15)

        # ── message box ──
        mf = tk.Frame(T, bg=CARD)
        mf.pack(padx=15, pady=3, fill="x")
        self.msg_box = tk.Text(mf, height=10, bg=CARD, fg=TEXT,
                               insertbackground=TEXT, font=("Consolas",9),
                               relief="flat", padx=10, pady=8, undo=True)
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
        self.msg_box.bind("<KeyRelease>", self._char_count)
        self.lbl_chars = tk.Label(T, text="", bg=BG, fg=MUTED,
                                  font=("Segoe UI",8))
        self.lbl_chars.pack(anchor="e", padx=15)
        self._char_count()

        # ── stats bar ──
        sf = tk.Frame(T, bg="#111827", pady=7)
        sf.pack(fill="x", padx=15, pady=5)
        self.lbl_loaded  = tk.Label(sf, text="Loaded: 0",  bg="#111827",fg=TEXT,  font=("Segoe UI",9,"bold"))
        self.lbl_sent    = tk.Label(sf, text="Sent: 0",    bg="#111827",fg=GREEN, font=("Segoe UI",9,"bold"))
        self.lbl_failed  = tk.Label(sf, text="Failed: 0",  bg="#111827",fg=RED,   font=("Segoe UI",9,"bold"))
        self.lbl_skipped = tk.Label(sf, text="Skipped: 0", bg="#111827",fg=AMBER, font=("Segoe UI",9,"bold"))
        self.lbl_eta     = tk.Label(sf, text="ETA: --",    bg="#111827",fg=BLUE,  font=("Segoe UI",9,"bold"))
        for i,l in enumerate([self.lbl_loaded,self.lbl_sent,self.lbl_failed,
                               self.lbl_skipped,self.lbl_eta]):
            l.grid(row=0,column=i,padx=11)

        # ── progress ──
        self.v_prog = tk.DoubleVar(value=0)
        ttk.Progressbar(T, variable=self.v_prog, maximum=100,
                        length=760).pack(padx=15, pady=3)

        # ── status / daily ──
        self.lbl_status = tk.Label(T,
            text="● Idle — Import your list to begin",
            bg=BG, fg=AMBER, font=("Segoe UI",10,"bold"))
        self.lbl_status.pack(pady=2)
        self.lbl_daily = tk.Label(T, text="Sent today: 0/40",
                                  bg=BG, fg=GREEN, font=("Segoe UI",9))
        self.lbl_daily.pack()

        # ── dry-run ──
        self.v_dry = tk.BooleanVar(value=False)
        tk.Checkbutton(T, text="🧪 Dry-Run (simulate — nothing sent)",
                       variable=self.v_dry, bg=BG, fg=BLUE,
                       selectcolor=CARD, font=("Segoe UI",9)).pack(pady=2)

        # ── BUTTONS ──────────────────────────────────────
        bf = tk.Frame(T, bg=BG); bf.pack(pady=6)

        self.btn_import = ttk.Button(bf, text="📁 Import List",   command=self.do_import)
        self.btn_reset  = ttk.Button(bf, text="🔄 Reset List",    command=self.do_reset)
        self.btn_start  = ttk.Button(bf, text="▶  START",         command=self.do_start)
        self.btn_pause  = ttk.Button(bf, text="⏸ PAUSE",          command=self.do_pause,state="disabled")
        self.btn_stop   = ttk.Button(bf, text="⏹ STOP",           command=self.do_stop)
        self.btn_test   = ttk.Button(bf, text="🔬 Test 1 Number", command=self.do_test)
        self.btn_retry  = ttk.Button(bf, text="🔁 Retry Failed",  command=self.do_retry)
        self.btn_export = ttk.Button(bf, text="💾 Export Failed", command=self.do_export)
        self.btn_bl     = ttk.Button(bf, text="🔕 Blacklist",     command=self.do_blacklist)
        self.btn_clear  = ttk.Button(bf, text="🗑 Clear Log",     command=self.do_clear_log)

        for r,c,b in [
            (0,0,self.btn_import),(0,1,self.btn_reset),(0,2,self.btn_start),
            (0,3,self.btn_pause), (0,4,self.btn_stop),
            (1,0,self.btn_test),  (1,1,self.btn_retry),(1,2,self.btn_export),
            (1,3,self.btn_bl),    (1,4,self.btn_clear),
        ]:
            b.grid(row=r,column=c,padx=5,pady=4,sticky="ew")

        # ── footer warning ──
        tk.Label(T,
            text="⚠  Keep WhatsApp Web open in Chrome/Edge  ·  "
                 "Move mouse to TOP-LEFT corner to emergency-stop",
            bg=BG, fg=RED, font=("Segoe UI",8,"bold")).pack(pady=5)

    # ══════════════════════════════════════════════════════
    #  LOG TAB
    # ══════════════════════════════════════════════════════
    def _tab_log(self, T):
        tk.Label(T, text="Session Log", bg=BG, fg=ACCENT,
                 font=("Segoe UI",11,"bold")).pack(pady=8)
        fr = tk.Frame(T, bg=BG)
        fr.pack(fill="both",expand=True,padx=10,pady=4)
        sc = tk.Scrollbar(fr); sc.pack(side="right",fill="y")
        self.log_box = tk.Text(fr, bg=CARD, fg=MUTED,
                               font=("Consolas",9),
                               yscrollcommand=sc.set,
                               state="disabled", relief="flat")
        self.log_box.pack(fill="both",expand=True)
        sc.config(command=self.log_box.yview)
        for tag,col in [("info",BLUE),("sent",GREEN),("failed",RED),
                        ("skip",AMBER),("warn","#FBBF24")]:
            self.log_box.tag_config(tag, foreground=col)
        self._log("info", f"AutoReach v{VERSION} ready.")

    # ══════════════════════════════════════════════════════
    #  SETTINGS TAB
    # ══════════════════════════════════════════════════════
    def _tab_settings(self, T):
        tk.Label(T, text="Settings", bg=BG, fg=ACCENT,
                 font=("Segoe UI",11,"bold")).pack(pady=10)
        fr = tk.Frame(T, bg=BG); fr.pack(padx=30, fill="x")

        # spinbox vars
        self.v_dmin     = tk.IntVar(value=20)   # min inter-message delay
        self.v_dmax     = tk.IntVar(value=40)   # max inter-message delay
        self.v_load     = tk.IntVar(value=8)    # wait after URL opens (was 15)
        self.v_postsend = tk.IntVar(value=5)    # delay AFTER send before closing tab
        self.v_timeout  = tk.IntVar(value=35)   # per-message hard timeout
        self.v_dlimit   = tk.IntVar(value=40)   # daily limit
        self.v_retries  = tk.IntVar(value=2)    # retries

        # checkbox vars
        self.v_skip_sent = tk.BooleanVar(value=True)
        self.v_skip_bl   = tk.BooleanVar(value=True)
        self.v_vary      = tk.BooleanVar(value=True)
        self.v_tray      = tk.BooleanVar(value=True)   # hide to system tray
        self.v_sound     = tk.BooleanVar(value=True)

        def row(label, var, lo, hi, r, note=""):
            full = label + (f"  ({note})" if note else "")
            tk.Label(fr, text=full, bg=BG, fg=MUTED,
                     width=54, anchor="w").grid(row=r,column=0,pady=5,sticky="w")
            ttk.Spinbox(fr, from_=lo, to=hi, textvariable=var,
                        width=8).grid(row=r,column=1,pady=5)

        row("Min delay between messages (s):",       self.v_dmin,     5, 120, 0, "↑ safer")
        row("Max delay between messages (s):",       self.v_dmax,    10, 240, 1)
        row("Wait after WhatsApp Web opens (s):",    self.v_load,     3,  60, 2, "8 works for most connections")
        row("Post-send pause before closing tab (s):",self.v_postsend,2,  30, 3, "default 5")
        row("Per-message hard timeout (s):",         self.v_timeout, 15, 120, 4, "closes tab & skips if exceeded")
        row("Daily send limit:",                     self.v_dlimit,   5, 200, 5)
        row("Retry attempts per number:",            self.v_retries,  1,   5, 6)

        tray_label = (
            "✅ Hide to system tray while running (recommended)"
            if HAS_TRAY else
            "⚠  System tray unavailable — run:  pip install pystray Pillow"
        )
        for r,var,txt in [
            (7,  self.v_skip_sent, "Skip already-sent numbers"),
            (8,  self.v_skip_bl,   "Skip blacklisted numbers"),
            (9,  self.v_vary,      "✅ Vary each message (anti-spam invisible char)"),
            (10, self.v_tray,      tray_label),
            (11, self.v_sound,     "Play sound when session finishes"),
        ]:
            cb = tk.Checkbutton(fr, text=txt, variable=var,
                                bg=BG, fg=TEXT, selectcolor=CARD)
            cb.grid(row=r, column=0, columnspan=2, sticky="w", pady=3)
            if not HAS_TRAY and var is self.v_tray:
                cb.config(state="disabled")

    # ══════════════════════════════════════════════════════
    #  CALIBRATE TAB
    # ══════════════════════════════════════════════════════
    def _tab_calibrate(self, T):
        tk.Label(T, text="Auto-Click Calibration",
                 bg=BG, fg=ACCENT, font=("Segoe UI",12,"bold")).pack(pady=14)

        tk.Label(T,
            text=(
                "AutoReach clicks the WhatsApp Web message box automatically.\n\n"
                "ONE-TIME SETUP:\n"
                "  1. Open WhatsApp Web in Chrome/Edge and open any chat.\n"
                "  2. Come back here and click  'Start 3s Countdown'.\n"
                "  3. Within 3 seconds move your mouse to the message\n"
                "     input box at the bottom of WhatsApp Web.\n"
                "  4. Stay still — position is saved automatically.\n\n"
                "Redo this if your browser window moves or resizes."
            ),
            bg=CARD, fg=TEXT, font=("Segoe UI",9),
            justify="left", wraplength=680, padx=18, pady=14
        ).pack(padx=20, fill="x")

        self.lbl_calib = tk.Label(T, bg=BG, fg=GREEN,
                                  font=("Segoe UI",10,"bold"))
        self.lbl_calib.pack(pady=10)
        self._calib_refresh()

        self.lbl_cdown = tk.Label(T, text="", bg=BG, fg=AMBER,
                                  font=("Segoe UI",32,"bold"))
        self.lbl_cdown.pack(pady=4)

        bf = tk.Frame(T, bg=BG); bf.pack()
        ttk.Button(bf, text="🎯  Start 3s Countdown",
                   command=self._calib_start).pack(side="left",padx=8,pady=6)
        ttk.Button(bf, text="🔄  Reset to Default",
                   command=self._calib_reset).pack(side="left",padx=8,pady=6)

    def _calib_refresh(self):
        cx, cy = self.calib.get()
        src = "Calibrated ✅" if self.calib.x else "Default (estimated)"
        self.lbl_calib.config(
            text=f"Click target → X: {cx}   Y: {cy}     [{src}]")

    def _calib_start(self):
        def _run():
            for i in (3,2,1):
                self.lbl_cdown.config(text=str(i)); time.sleep(1)
            x, y = pyautogui.position()
            self.calib.save(x, y)
            self.lbl_cdown.config(text="✅ Saved!")
            self._calib_refresh()
            time.sleep(1.5)
            self.lbl_cdown.config(text="")
        threading.Thread(target=_run, daemon=True).start()

    def _calib_reset(self):
        if os.path.exists(CALIB_FILE): os.remove(CALIB_FILE)
        self.calib.x = self.calib.y = None
        self._calib_refresh()

    # ══════════════════════════════════════════════════════
    #  SMALL HELPERS
    # ══════════════════════════════════════════════════════
    def _mode_hint(self):
        if self.v_single.get():
            self.lbl_mode.config(
                text="▸ Whole message sent in one go — newlines kept intact")
        else:
            self.lbl_mode.config(
                text="▸ Each paragraph sent as a separate message")

    def _char_count(self, _=None):
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

    def _status(self, txt):
        self.root.after(0, lambda: self.lbl_status.config(text=txt))
        if self._tray_icon:
            try: self._tray_icon.title = f"AutoReach · {txt}"
            except Exception: pass

    def _refresh_daily(self):
        today = self.logger.sent_today()
        lim   = self.v_dlimit.get() if hasattr(self,"v_dlimit") else 40
        self.lbl_daily.config(
            text=f"Sent today: {today}/{lim}",
            fg=RED if today>=lim else GREEN)

    def _update_stats(self):
        def _up():
            self.lbl_loaded.config(text=f"Loaded: {self.total}")
            self.lbl_sent.config(text=f"Sent: {self.sent_count}")
            self.lbl_failed.config(text=f"Failed: {len(self.failed_list)}")
            self.lbl_skipped.config(text=f"Skipped: {self.skipped_count}")
            pct = (self.current_idx/self.total*100) if self.total else 0
            self.v_prog.set(pct)
            if self.start_time and self.current_idx > 0:
                e = time.time()-self.start_time
                r = (self.total-self.current_idx)*(e/self.current_idx)
                eta = str(timedelta(seconds=int(r)))
            else: eta="--:--"
            self.lbl_eta.config(text=f"ETA: {eta}")
            self._refresh_daily()
        self.root.after(0, _up)

    # ══════════════════════════════════════════════════════
    #  WINDOW / TRAY
    # ══════════════════════════════════════════════════════
    def _go_background(self):
        """Hide window completely + show system tray icon if available."""
        if HAS_TRAY and self.v_tray.get():
            self.root.after(0, lambda: self.root.withdraw())
            menu = pystray.Menu(
                pystray.MenuItem("📊 Show App",      self._tray_show),
                pystray.MenuItem("⏸ Pause/Resume",   lambda _,__: self.do_pause()),
                pystray.MenuItem("⏹ Stop Session",   lambda _,__: self.do_stop()),
                pystray.MenuItem("✖  Exit",           lambda _,__: self._quit()),
            )
            icon = pystray.Icon(
                "AutoReach",
                _make_tray_image("#4F8CFF"),
                "AutoReach — Running",
                menu
            )
            self._tray_icon = icon
            threading.Thread(target=icon.run, daemon=True).start()
        else:
            # fallback: just minimize
            self.root.after(0, lambda: self.root.iconify())

    def _tray_show(self, icon=None, item=None):
        if self._tray_icon:
            try: self._tray_icon.stop()
            except Exception: pass
            self._tray_icon = None
        self.root.after(0, lambda: (
            self.root.deiconify(),
            self.root.lift(),
            self.root.focus_force()
        ))

    def _restore(self):
        if self._tray_icon:
            try: self._tray_icon.stop()
            except Exception: pass
            self._tray_icon = None
        self.root.after(0, lambda: (
            self.root.deiconify(),
            self.root.lift()
        ))

    def _quit(self):
        self.running = False
        self._restore()
        self.root.after(200, self.root.destroy)

    def _on_close(self):
        if self.running:
            if messagebox.askyesno("Running",
               "A session is running. Stop and exit?"):
                self.running = False
                self.root.after(500, self.root.destroy)
        else:
            self.root.destroy()

    # ══════════════════════════════════════════════════════
    #  BROWSER / CLIPBOARD
    # ══════════════════════════════════════════════════════
    def _activate_browser(self):
        if not gw: return
        try:
            wins = [w for w in gw.getAllWindows()
                    if "whatsapp" in getattr(w,"title","").lower()]
            if wins:
                try: wins[0].activate()
                except Exception: pass
        except Exception: pass

    def _clip(self):
        try: return pyperclip.paste()
        except Exception: return ""

    def _close_tab(self):
        try: pyautogui.hotkey("ctrl","w"); time.sleep(0.6)
        except Exception: pass

    # ══════════════════════════════════════════════════════
    #  CLICK MESSAGE BOX
    # ══════════════════════════════════════════════════════
    def _click_box(self):
        cx, cy = self.calib.get()
        ox, oy = random.randint(-6,6), random.randint(-3,3)
        try:
            pyautogui.moveTo(cx+ox, cy+oy, duration=random.uniform(0.1,0.25))
            time.sleep(0.08)
            pyautogui.click()
            time.sleep(0.35)
        except Exception: pass

    # ══════════════════════════════════════════════════════
    #  SMART LOAD WAIT
    #  Polls every 0.5s instead of sleeping a fixed block.
    #  Tries clicking + pasting early — as soon as the page
    #  seems ready — instead of waiting the full v_load time.
    # ══════════════════════════════════════════════════════
    def _wait_load_and_click(self, deadline):
        """
        Wait until WA Web appears ready (tab title contains a phone number
        or the box becomes clickable), then click the message input.
        Falls back to sleeping v_load seconds if detection fails.
        """
        load_max = self.v_load.get()
        waited   = 0.0

        while waited < load_max:
            if not self.running or time.time() > deadline:
                return False
            while self.paused: time.sleep(0.2)

            # Try clicking every 0.5 s — paste will succeed when page is ready
            self._click_box()

            # Quick probe: copy box contents
            try:
                pyautogui.hotkey("ctrl","a"); time.sleep(0.1)
                pyautogui.hotkey("ctrl","c"); time.sleep(0.1)
            except Exception: pass

            # If we can interact (anything or empty is fine), break early
            # The box is ready when ctrl+a/c doesn't raise and clipboard responds
            clip = self._clip()
            if clip is not None:   # page responded
                # One extra click to make sure focus is in the right place
                self._click_box()
                return True

            self._status(f"● Waiting for WhatsApp… ({load_max-int(waited)}s)")
            time.sleep(0.5)
            waited += 0.5

        # fallback: click once at end of wait
        self._click_box()
        return True

    # ══════════════════════════════════════════════════════
    #  PASTE
    # ══════════════════════════════════════════════════════
    def _paste(self, text):
        try:
            pyperclip.copy(text)
            time.sleep(0.18)
            pyautogui.hotkey("ctrl","v")
            time.sleep(0.28)
        except Exception: pass

    # ══════════════════════════════════════════════════════
    #  WAIT FOR BOX TO CLEAR  (confirms send)
    # ══════════════════════════════════════════════════════
    def _wait_clear(self, max_sec=8.0):
        deadline = time.time() + max_sec
        while time.time() < deadline:
            if not self.running: return False
            try:
                pyautogui.hotkey("ctrl","a"); time.sleep(0.1)
                pyautogui.hotkey("ctrl","c"); time.sleep(0.1)
            except Exception: pass
            if self._clip().strip() == "": return True
            time.sleep(0.3)
        return False

    # ══════════════════════════════════════════════════════
    #  CORE SEND — SINGLE MESSAGE
    # ══════════════════════════════════════════════════════
    def _do_send_single(self, number, msg):
        timeout  = self.v_timeout.get()
        deadline = time.time() + timeout

        # Open WhatsApp Web (no pre-filled text — we paste it ourselves)
        webbrowser.open(
            f"https://web.whatsapp.com/send/"
            f"?phone={number}&type=phone_number&app_absent=0")
        time.sleep(2.2)
        self._activate_browser()
        time.sleep(0.4)

        # Smart load + click
        ok = self._wait_load_and_click(deadline)
        if not ok or time.time() > deadline:
            self._close_tab(); return False

        # Paste message
        self._paste(msg)

        # Verify paste landed; retry once if box still empty
        try:
            pyautogui.hotkey("ctrl","a"); time.sleep(0.1)
            pyautogui.hotkey("ctrl","c"); time.sleep(0.1)
        except Exception: pass
        if self._clip().strip() == "":
            self._click_box()
            self._paste(msg)
            time.sleep(0.3)

        # ── SEND ──
        pyautogui.press("enter")

        # Confirm send (box clears)
        confirmed = self._wait_clear(min(8.0, deadline - time.time()))

        # ── POST-SEND PAUSE ──  (user-configurable, default 5s)
        post = self.v_postsend.get()
        for i in range(post, 0, -1):
            if not self.running: break
            self._status(f"● Sent ✅ — closing tab in {i}s…")
            time.sleep(1.0)

        self._close_tab()
        return confirmed

    # ══════════════════════════════════════════════════════
    #  CORE SEND — PARAGRAPH SPLIT
    # ══════════════════════════════════════════════════════
    def _do_send_split(self, number, msg):
        timeout  = self.v_timeout.get()
        deadline = time.time() + timeout
        parts    = [p.strip() for p in msg.split("\n\n") if p.strip()]
        if not parts: return False

        webbrowser.open(
            f"https://web.whatsapp.com/send/"
            f"?phone={number}&type=phone_number&app_absent=0")
        time.sleep(2.2)
        self._activate_browser()
        time.sleep(0.4)

        ok = self._wait_load_and_click(deadline)
        if not ok or time.time() > deadline:
            self._close_tab(); return False

        all_ok = True
        for i, part in enumerate(parts):
            if not self.running or time.time() > deadline:
                all_ok = False; break
            self._paste(part)
            time.sleep(0.25)
            pyautogui.press("enter")
            if not self._wait_clear(min(5.0, deadline-time.time())):
                all_ok = False; break
            if i < len(parts)-1:
                time.sleep(gauss_delay(1.2, 2.5))

        post = self.v_postsend.get()
        for i in range(post, 0, -1):
            if not self.running: break
            self._status(f"● Sent ✅ — closing tab in {i}s…")
            time.sleep(1.0)

        self._close_tab()
        return all_ok

    # ══════════════════════════════════════════════════════
    #  SEND WRAPPER  (retry + variation)
    # ══════════════════════════════════════════════════════
    def send_message(self, number, raw):
        if self.v_dry.get():
            time.sleep(random.uniform(1.5, 3.0)); return True

        for attempt in range(1, self.v_retries.get()+1):
            if not self.running: return False
            if attempt > 1:
                self._log("warn", f"  Retry {attempt} → {number}")
                time.sleep(gauss_delay(3,6))
            msg = vary(raw) if self.v_vary.get() else raw
            try:
                ok = (self._do_send_single(number, msg)
                      if self.v_single.get()
                      else self._do_send_split(number, msg))
            except pyautogui.FailSafeException:
                self._log("warn","🛑 Emergency stop (mouse corner).")
                self.do_stop(); return False
            except Exception as ex:
                self._log("warn", f"  Error: {ex}"); ok = False
            if ok: return True
        return False

    # ══════════════════════════════════════════════════════
    #  BUTTON ACTIONS
    # ══════════════════════════════════════════════════════
    def do_import(self):
        path = filedialog.askopenfilename(
            title="Select number list",
            filetypes=[("Text","*.txt"),("All","*.*")])
        if not path: return
        try: lines = open(path, encoding="utf-8").read().splitlines()
        except Exception as e: messagebox.showerror("Error", str(e)); return

        clean, seen, bad = [], set(), 0
        for ln in lines:
            n = to_e164(ln)
            if n and n not in seen: seen.add(n); clean.append(n)
            else: bad += 1

        self.numbers = clean; self.total = len(clean)
        self.current_idx = self.sent_count = self.skipped_count = 0
        self.failed_list = []
        self._update_stats()
        self._log("info",f"Imported {self.total} numbers  ({bad} skipped).")
        messagebox.showinfo("Imported",
            f"✅  {self.total} numbers loaded\n⚠  {bad} invalid/duplicate skipped")

    def do_reset(self):
        """Reset imported list back to zero — fresh start."""
        if self.running:
            messagebox.showwarning("Running","Stop the session first."); return
        if not messagebox.askyesno("Reset List",
            "Clear the imported list and reset all counters?\n"
            "(Log history is kept — only the current list is cleared.)"):
            return
        self.numbers       = []
        self.total         = 0
        self.current_idx   = 0
        self.sent_count    = 0
        self.failed_list   = []
        self.skipped_count = 0
        self._update_stats()
        self._status("● Idle — list cleared, import a new one")
        self._log("info","List reset.")

    def do_start(self):
        if not self.numbers:
            messagebox.showwarning("No list","Import a number list first."); return
        if self.current_idx >= self.total:
            messagebox.showinfo("Done","All processed. Reset or re-import to restart."); return
        lim = self.v_dlimit.get()
        if self.logger.sent_today() >= lim:
            messagebox.showwarning("Limit",
                f"Daily limit of {lim} reached.\nChange in Settings or wait until tomorrow.")
            return

        self.running = True; self.paused = False
        self.start_time = time.time()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ PAUSE")
        self._status("● Running…")
        self._log("info",
            f"Session started — {self.total-self.current_idx} numbers to process.")
        if self.v_dry.get():
            self._log("warn","⚠  DRY RUN — nothing actually sent.")

        if self.v_tray.get():
            self._go_background()

        threading.Thread(target=self._loop, daemon=True).start()

    def do_pause(self):
        if not self.running: return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RESUME")
            self._status(f"● Paused at {self.current_idx}/{self.total}")
            self._log("warn","Paused.")
        else:
            self.btn_pause.config(text="⏸ PAUSE")
            self._status("● Running…")
            self._log("info","Resumed.")

    def do_stop(self):
        self.running = False; self.paused = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))
        self._status(f"● Stopped at {self.current_idx}/{self.total}")
        self._log("warn","Stopped.")
        self._restore()

    def do_test(self):
        val = simpledialog.askstring("Test","Enter number (10 or 12 digits):")
        if not val: return
        n = to_e164(val)
        if not n: messagebox.showwarning("Invalid","Enter a valid number."); return
        raw = self.msg_box.get("1.0", tk.END).strip()
        self._log("info", f"Test → {n}")
        def _t():
            ok = self.send_message(n, raw)
            res = "✅ Test sent!" if ok else "❌ Test FAILED"
            self._log("sent" if ok else "failed", res)
            self.root.after(0, lambda: messagebox.showinfo("Test", res))
        threading.Thread(target=_t, daemon=True).start()

    def do_retry(self):
        if not self.failed_list:
            messagebox.showinfo("Empty","No failed numbers."); return
        self.numbers = list(self.failed_list)
        self.total = len(self.numbers)
        self.current_idx = self.sent_count = self.skipped_count = 0
        self.failed_list = []
        self._update_stats()
        messagebox.showinfo("Retry", f"Loaded {self.total} failed numbers.")

    def do_export(self):
        if not self.failed_list:
            messagebox.showinfo("Empty","No failed numbers."); return
        p = filedialog.asksaveasfilename(defaultextension=".txt",
            filetypes=[("Text","*.txt")], initialfile="failed.txt")
        if not p: return
        open(p,"w",encoding="utf-8").write("\n".join(self.failed_list))
        messagebox.showinfo("Exported", f"Saved {len(self.failed_list)} numbers.")

    def do_blacklist(self):
        val = simpledialog.askstring("Blacklist",
            "Enter number (leave blank to blacklist all failed):")
        if val:
            n = to_e164(val)
            if n: self.blacklist.add(n); messagebox.showinfo("Done",f"{n} blacklisted.")
            else: messagebox.showwarning("Invalid","Not a valid number.")
        elif self.failed_list:
            for n in self.failed_list: self.blacklist.add(n)
            messagebox.showinfo("Done",f"{len(self.failed_list)} blacklisted.")

    def do_clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0","end")
        self.log_box.config(state="disabled")
        self._log("info","Log cleared.")

    # ══════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════
    def _loop(self):
        raw      = self.msg_box.get("1.0", tk.END).strip()
        sent_set = self.logger.sent_set()
        lim      = self.v_dlimit.get()

        while self.current_idx < self.total and self.running:
            if self.paused: time.sleep(0.3); continue

            if self.logger.sent_today() >= lim:
                self._log("warn", f"Daily limit {lim} reached.")
                self.root.after(0, lambda: messagebox.showwarning(
                    "Limit", f"Daily limit of {lim} reached."))
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
            self._status(f"● {idx}/{self.total} → {number}")

            ok = self.send_message(number, raw)

            self.current_idx += 1
            if ok:
                self.sent_count += 1; sent_set.add(number)
                self.logger.mark_sent(number)
                self._log("sent", f"✅  {number}")
            else:
                self.failed_list.append(number)
                self.logger.mark_failed(number)
                self._log("failed", f"❌  {number}")

            self._update_stats()

            # ── inter-message delay ──
            if self.current_idx < self.total and self.running:
                delay   = gauss_delay(self.v_dmin.get(), self.v_dmax.get())
                elapsed = 0.0
                self._log("info", f"  Next in {delay:.0f}s…")
                while elapsed < delay and self.running:
                    while self.paused: time.sleep(0.3)
                    self._status(
                        f"● Next message in {int(delay-elapsed)}s "
                        f"({self.current_idx}/{self.total} done)")
                    time.sleep(0.5); elapsed += 0.5

        # ── DONE ──
        self.running = False
        self.root.after(0, lambda: self.btn_start.config(state="normal"))
        self.root.after(0, lambda: self.btn_pause.config(
            state="disabled", text="⏸ PAUSE"))
        self._restore()

        if self.current_idx >= self.total:
            self._log("info","🎉 All done!")
            self._status("● All Done! 🎉")
            dry = "\n(DRY RUN — nothing actually sent)" if self.v_dry.get() else ""
            summary = (f"✅ Sent:    {self.sent_count}\n"
                       f"❌ Failed:  {len(self.failed_list)}\n"
                       f"↷ Skipped: {self.skipped_count}{dry}")
            self.root.after(0, lambda: messagebox.showinfo("Session Done!", summary))
            if self.v_sound.get():
                try: self.root.bell()
                except Exception: pass
        else:
            self._status(f"● Stopped at {self.current_idx}/{self.total}")


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    AutoReach(root)
    root.mainloop()

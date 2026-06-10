# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.parse
import subprocess
import threading
import time
import pyautogui
import random
import os
import json

# ══════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════
LOAD_WAIT      = 16    # seconds to wait for WhatsApp Web
AFTER_SEND     = 2     # seconds after pressing Enter
BATCH_SIZE     = 50    # messages before auto-break
BATCH_BREAK    = 300   # 5 min break between batches
DEFAULT_DELAY  = 20    # seconds between each message
SAVE_FILE      = "progress.json"  # saves your progress

# Edge browser path
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
EDGE_PATH = next((p for p in EDGE_PATHS if os.path.exists(p)), None)

# ══════════════════════════════════════════
#  COLORS
# ══════════════════════════════════════════
BG      = "#0d0d0d"
CARD    = "#1c1c1c"
GREEN   = "#25D366"
BLUE    = "#4285F4"
RED     = "#FF5252"
ORANGE  = "#FF9800"
MUTED   = "#777777"
WHITE   = "#ffffff"

# ══════════════════════════════════════════════════════
class OutreachTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Ambassador Outreach Tool")
        self.root.geometry("760x900")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.numbers     = []
        self.current_idx = 0
        self.sent_count  = 0
        self.total       = 0
        self.running     = False
        self.paused      = False

        # Load saved progress if exists
        self._load_progress()
        self._build_ui()

    # ══════════════════════════════════════
    #  SAVE / LOAD PROGRESS
    # ══════════════════════════════════════
    def _save_progress(self):
        data = {
            "current_idx": self.current_idx,
            "sent_count":  self.sent_count,
            "numbers":     self.numbers
        }
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f)

    def _load_progress(self):
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, "r") as f:
                    data = json.load(f)
                self.numbers     = data.get("numbers", [])
                self.current_idx = data.get("current_idx", 0)
                self.sent_count  = data.get("sent_count", 0)
                self.total       = len(self.numbers)
            except:
                pass

    def _clear_progress(self):
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)

    # ══════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════
    def _build_ui(self):

        # ── Top accent stripe ──
        tk.Frame(self.root, bg=BLUE, height=6).pack(fill="x")

        # ── Main scrollable canvas ──
        canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        v_scroll = ttk.Scrollbar(self.root, orient="vertical",   command=canvas.yview)
        v_scroll.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=v_scroll.set)

        # Inner frame inside canvas
        inner = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        inner.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse wheel scroll
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ─────────────────────────────────────
        # Now build all widgets inside `inner`
        # ─────────────────────────────────────

        # Title
        tk.Label(inner, text="🚀 Google Ambassador Outreach",
                 bg=BG, fg=BLUE, font=("Segoe UI", 22, "bold")).pack(pady=(20, 2))
        tk.Label(inner, text="WhatsApp Bulk Messaging Tool  •  Safe Mode  •  Edge Browser",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack()

        # ── BAN WARNING ──
        warn = tk.Frame(inner, bg="#1e0505", padx=16, pady=12)
        warn.pack(fill="x", padx=25, pady=15)
        tk.Label(warn, text="⚠️  WhatsApp Ban Warning",
                 bg="#1e0505", fg=RED, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(warn,
                 text="• Sending bulk DMs to people who haven't saved your number can result in a ban.\n"
                      "• This tool adds smart delays and batch breaks to keep your account safe.\n"
                      "• Use on a SECONDARY number only. Do NOT touch mouse while running.\n"
                      "• Tool auto-pauses every 50 messages for 5 minutes for safety.",
                 bg="#1e0505", fg="#ffcccc",
                 font=("Segoe UI", 9), justify="left").pack(anchor="w")

        # ── MESSAGE BOX with scrollbar ──
        msg_outer = tk.Frame(inner, bg=CARD, padx=15, pady=12)
        msg_outer.pack(fill="x", padx=25, pady=8)

        tk.Label(msg_outer, text="📝  Message Template  (editable)",
                 bg=CARD, fg=WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        msg_container = tk.Frame(msg_outer, bg="#0a0a0a")
        msg_container.pack(fill="x", pady=(6, 0))

        # Vertical scrollbar for message box
        msg_vscroll = ttk.Scrollbar(msg_container, orient="vertical")
        msg_vscroll.pack(side="right", fill="y")

        self.msg_box = tk.Text(
            msg_container,
            height=12,
            bg="#0a0a0a", fg=WHITE,
            insertbackground=WHITE,
            font=("Segoe UI", 10),
            wrap="word",
            relief="flat",
            padx=10, pady=8,
            yscrollcommand=msg_vscroll.set
        )
        self.msg_box.pack(side="left", fill="both", expand=True)
        msg_vscroll.config(command=self.msg_box.yview)

        # Insert message with proper WhatsApp link
        self.msg_box.insert("1.0",
            "Hello 👋\n\n"
            "A separate student-led support community has been created "
            "for Google Gemini Student Ambassadors to help members with "
            "tasks, updates, resources, networking, collaboration, and "
            "doubt solving throughout the program.\n\n"
            "You're welcome to join the group here:\n"
            "https://chat.whatsapp.com/HBF8OYOOvfm7ihIutciSaw\n\n"
            "This group is independently organized by students and is "
            "only meant for helping and supporting fellow ambassadors.\n\n"
            "Feel free to join and also share it with other ambassadors "
            "you know 🚀"
        )

        # ── STATS ROW ──
        stats_row = tk.Frame(inner, bg=BG)
        stats_row.pack(fill="x", padx=25, pady=10)
        stats_row.columnconfigure((0,1,2,3), weight=1)

        self.lbl_loaded = self._stat(stats_row, "📥 Loaded",    "0",  BLUE,   0)
        self.lbl_sent   = self._stat(stats_row, "✅ Sent",      "0",  GREEN,  1)
        self.lbl_left   = self._stat(stats_row, "⏳ Remaining", "0",  ORANGE, 2)
        self.lbl_batch  = self._stat(stats_row, "📦 Batch",     "0",  MUTED,  3)

        # ── PROGRESS BAR ──
        self.progress = ttk.Progressbar(inner, length=700, mode="determinate")
        self.progress.pack(padx=25, pady=6)

        # ── STATUS LABEL ──
        self.lbl_status = tk.Label(inner,
            text="● Idle — Import your number list to begin",
            bg=BG, fg=MUTED, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(pady=6)

        # ── DELAY SELECTOR ──
        delay_frame = tk.Frame(inner, bg=CARD, padx=15, pady=10)
        delay_frame.pack(fill="x", padx=25, pady=6)

        tk.Label(delay_frame, text="⏱  Delay Between Messages:",
                 bg=CARD, fg=WHITE, font=("Segoe UI", 10)).pack(side="left", padx=(0,15))

        self.delay_var = tk.IntVar(value=DEFAULT_DELAY)
        for label, val, color in [("🐢 Safe 30s", 30, GREEN), ("🚗 Normal 20s", 20, ORANGE), ("⚡ Fast 15s", 15, RED)]:
            tk.Radiobutton(delay_frame, text=label,
                           variable=self.delay_var, value=val,
                           bg=CARD, fg=WHITE, selectcolor=BG,
                           activebackground=CARD,
                           font=("Segoe UI", 9)).pack(side="left", padx=12)

        # ── BUTTONS ──
        btn_frame = tk.Frame(inner, bg=BG)
        btn_frame.pack(pady=15)

        self.btn_import = self._btn(btn_frame, "📁  Import List",   BLUE,   self.import_list,  0)
        self.btn_start  = self._btn(btn_frame, "▶  START",          GREEN,  self.start,        1)
        self.btn_pause  = self._btn(btn_frame, "⏸  PAUSE",         ORANGE, self.toggle_pause, 2, "disabled")
        self.btn_stop   = self._btn(btn_frame, "⏹  STOP",          RED,    self.stop,         3, "disabled")
        self.btn_reset  = self._btn(btn_frame, "🔄  RESET",         MUTED,  self.reset,        4)

        # ── RESUME NOTICE ──
        if self.total > 0 and self.current_idx > 0:
            resume_card = tk.Frame(inner, bg="#0a1a0a", padx=14, pady=10)
            resume_card.pack(fill="x", padx=25, pady=6)
            tk.Label(resume_card,
                     text=f"💾  Saved progress found!  Previously sent: {self.sent_count} | "
                          f"Resuming from number {self.current_idx + 1} of {self.total}",
                     bg="#0a1a0a", fg=GREEN,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(resume_card,
                     text="Click START to continue from where you left off, or RESET to start fresh.",
                     bg="#0a1a0a", fg="#aaffaa",
                     font=("Segoe UI", 9)).pack(anchor="w")

        # ── HOW TO USE ──
        guide = tk.Frame(inner, bg=CARD, padx=15, pady=12)
        guide.pack(fill="x", padx=25, pady=10)
        tk.Label(guide, text="📋  How To Use",
                 bg=CARD, fg=WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        steps = [
            "1. Open WhatsApp Web (web.whatsapp.com) in Edge and log in FIRST.",
            "2. Click 📁 Import List and select your .txt file (one number per line).",
            "3. Edit the message template above if needed.",
            "4. Choose your delay speed — Safe 30s is recommended.",
            "5. Click ▶ START and do NOT move your mouse or type anything.",
            "6. Tool auto-sends to each number. Pauses every 50 for 5 minutes.",
            "7. Use ⏸ PAUSE anytime. Progress is auto-saved — click START to resume.",
        ]
        for s in steps:
            tk.Label(guide, text=s, bg=CARD, fg="#bbbbbb",
                     font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=1)

        # ── FOOTER ──
        tk.Label(inner,
                 text="Built for Google Gemini Student Ambassador Program 🌟",
                 bg=BG, fg="#333333", font=("Segoe UI", 9)).pack(pady=(5, 2))
        tk.Label(inner,
                 text="Use responsibly • Secondary number only • No liability",
                 bg=BG, fg="#222222", font=("Segoe UI", 8)).pack(pady=(0, 15))

        # Bottom accent stripe
        tk.Frame(inner, bg=GREEN, height=5).pack(fill="x", side="bottom")

        # Refresh stats if resuming
        self._refresh_stats()

    # ══════════════════════════════════════
    #  STAT BOX HELPER
    # ══════════════════════════════════════
    def _stat(self, parent, title, value, color, col):
        box = tk.Frame(parent, bg=CARD, padx=15, pady=10)
        box.grid(row=0, column=col, padx=5, sticky="ew")
        tk.Label(box, text=title, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack()
        lbl = tk.Label(box, text=value, bg=CARD, fg=color,
                       font=("Segoe UI", 20, "bold"))
        lbl.pack()
        return lbl

    # ══════════════════════════════════════
    #  BUTTON HELPER
    # ══════════════════════════════════════
    def _btn(self, parent, text, color, cmd, col, state="normal"):
        b = tk.Button(parent, text=text,
                      bg=color, fg=WHITE,
                      font=("Segoe UI", 10, "bold"),
                      relief="flat", padx=14, pady=9,
                      cursor="hand2", state=state,
                      activebackground=color, activeforeground=WHITE,
                      command=cmd)
        b.grid(row=0, column=col, padx=5)
        return b

    # ══════════════════════════════════════
    #  IMPORT NUMBERS
    # ══════════════════════════════════════
    def import_list(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not path:
            return

        with open(path, "r", encoding="utf-8") as f:
            raw = [line.strip() for line in f if line.strip()]

        seen, clean = set(), []
        for num in raw:
            digits = "".join(filter(str.isdigit, num))
            if len(digits) == 10:
                digits = "91" + digits
            if len(digits) == 12 and digits not in seen:
                seen.add(digits)
                clean.append(digits)

        if not clean:
            return messagebox.showerror("Error", "No valid numbers found in the file.\nMake sure each line has a 10 or 12 digit number.")

        self.numbers     = clean
        self.total       = len(clean)
        self.current_idx = 0
        self.sent_count  = 0

        self._clear_progress()
        self._refresh_stats()
        self._set_status(f"✅  {self.total} numbers loaded — ready to start", GREEN)
        messagebox.showinfo("Imported ✅",
                            f"{self.total} valid numbers loaded.\n"
                            f"Duplicates removed automatically.")

    # ══════════════════════════════════════
    #  START
    # ══════════════════════════════════════
    def start(self):
        if not self.numbers:
            return messagebox.showwarning("No List", "Please import your number list first.")
        if self.current_idx >= self.total:
            return messagebox.showinfo("Done",
                "All numbers have been processed.\n"
                "Click RESET and re-import to start again.")

        self.running = True
        self.paused  = False

        self.btn_import.config(state="disabled")
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸  PAUSE")
        self.btn_stop.config(state="normal")
        self.btn_reset.config(state="disabled")

        self._set_status("🚀  Running — Do NOT touch mouse or keyboard!", GREEN)
        threading.Thread(target=self._run_loop, daemon=True).start()

    # ══════════════════════════════════════
    #  PAUSE / RESUME
    # ══════════════════════════════════════
    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶  RESUME")
            self._set_status(f"⏸  Paused at {self.current_idx}/{self.total} — Click RESUME to continue", ORANGE)
        else:
            self.btn_pause.config(text="⏸  PAUSE")
            self._set_status("🚀  Running — Do NOT touch mouse or keyboard!", GREEN)

    # ══════════════════════════════════════
    #  STOP
    # ══════════════════════════════════════
    def stop(self):
        self.running = False
        self.paused  = False
        self._save_progress()
        self._reset_buttons()
        self._set_status(f"⏹  Stopped at {self.current_idx}/{self.total} — Progress saved. Click START to resume.", RED)

    # ══════════════════════════════════════
    #  RESET
    # ══════════════════════════════════════
    def reset(self):
        if messagebox.askyesno("Reset", "This will clear all saved progress.\nAre you sure?"):
            self.numbers     = []
            self.current_idx = 0
            self.sent_count  = 0
            self.total       = 0
            self.running     = False
            self.paused      = False
            self._clear_progress()
            self._refresh_stats()
            self._set_status("● Reset complete — Import a new list to begin", MUTED)

    # ══════════════════════════════════════
    #  RESET BUTTONS
    # ══════════════════════════════════════
    def _reset_buttons(self):
        self.btn_import.config(state="normal")
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸  PAUSE")
        self.btn_stop.config(state="disabled")
        self.btn_reset.config(state="normal")

    # ══════════════════════════════════════
    #  MAIN AUTOMATION LOOP
    # ══════════════════════════════════════
    def _run_loop(self):
        msg   = urllib.parse.quote(self.msg_box.get("1.0", tk.END).strip())
        delay = self.delay_var.get()

        while self.current_idx < self.total and self.running:

            # ── Pause ──
            if self.paused:
                time.sleep(0.5)
                continue

            # ── Batch Break ──
            if self.sent_count > 0 and self.sent_count % BATCH_SIZE == 0:
                for remaining in range(BATCH_BREAK, 0, -1):
                    if not self.running: break
                    self._set_status(
                        f"🛡️  Safety break — resuming in {remaining}s  "
                        f"(Batch {self.sent_count // BATCH_SIZE} complete)", ORANGE)
                    time.sleep(1)

            if not self.running:
                break

            number = self.numbers[self.current_idx]

            # ── Build URL ──
            # The group link inside the message will be recognised by WhatsApp
            url = (f"https://web.whatsapp.com/send"
                   f"?phone={number}"
                   f"&text={msg}"
                   f"&type=phone_number"
                   f"&app_absent=1")

            self._set_status(
                f"📤  Opening chat {self.current_idx + 1}/{self.total}  →  +{number}", BLUE)

            # ── Open in Edge ──
            try:
                if EDGE_PATH:
                    subprocess.Popen([EDGE_PATH, "--new-tab", url])
                else:
                    import webbrowser
                    webbrowser.open(url)
            except Exception as e:
                import webbrowser
                webbrowser.open(url)

            # ── Wait for WhatsApp Web to fully load ──
            time.sleep(LOAD_WAIT)

            # ── Auto Click + Send ──
            try:
                sw, sh = pyautogui.size()

                # Click the message input box area (bottom portion of screen)
                pyautogui.click(sw // 2, int(sh * 0.92))
                time.sleep(0.8 + random.uniform(0.2, 0.5))

                # Small human-like pause before sending
                time.sleep(0.5 + random.uniform(0.1, 0.4))

                # Press Enter to send
                pyautogui.press("enter")
                time.sleep(AFTER_SEND)

                self.sent_count  += 1
                self.current_idx += 1

                # Save progress after each successful send
                self._save_progress()

                self._set_status(
                    f"✅  Sent {self.sent_count}  |  Waiting {delay}s before next...", GREEN)

            except Exception as e:
                # If send fails, skip this number and move on
                self.current_idx += 1
                self._set_status(f"⚠️  Error on number {self.current_idx} — skipped", ORANGE)

            # ── Update UI ──
            self.root.after(0, self._refresh_stats)

            # ── Delay before next number ──
            for i in range(delay, 0, -1):
                if not self.running or self.paused:
                    break
                self._set_status(
                    f"⏱  Next message in {i}s  |  Sent: {self.sent_count}/{self.total}", GREEN)
                time.sleep(1)

        # ── Done ──
        self.running = False
        self.root.after(0, self._reset_buttons)
        self.root.after(0, self._refresh_stats)

        if self.current_idx >= self.total:
            self._clear_progress()
            self.root.after(0, lambda: self._set_status(
                f"🎉  All done! {self.sent_count} messages sent successfully.", GREEN))
            self.root.after(0, lambda: messagebox.showinfo(
                "All Done 🎉",
                f"✅  {self.sent_count} messages sent!\n\n"
                f"Skipped: {self.total - self.sent_count}\n\n"
                "Remember to check WhatsApp for any issues."))
        else:
            self.root.after(0, lambda: self._set_status(
                f"⏹  Stopped at {self.current_idx}/{self.total} — Progress saved.", RED))

    # ══════════════════════════════════════
    #  REFRESH STATS
    # ══════════════════════════════════════
    def _refresh_stats(self):
        self.lbl_loaded.config(text=str(self.total))
        self.lbl_sent.config(text=str(self.sent_count))
        self.lbl_left.config(text=str(max(0, self.total - self.current_idx)))
        self.lbl_batch.config(text=str(self.sent_count // BATCH_SIZE + 1 if self.total > 0 else 0))

        if self.total > 0:
            self.progress["maximum"] = self.total
            self.progress["value"]   = self.current_idx

    # ══════════════════════════════════════
    #  SET STATUS (thread-safe)
    # ══════════════════════════════════════
    def _set_status(self, text, color=MUTED):
        self.root.after(0, lambda t=text, c=color:
                        self.lbl_status.config(text=t, fg=c))


# ══════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = OutreachTool(root)
    root.mainloop()
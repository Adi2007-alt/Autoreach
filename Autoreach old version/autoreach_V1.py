# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox
import urllib.parse
import subprocess
import threading
import time
import pyautogui
import json
import os

# ===== CONFIG (SAFE FOR SECONDARY NUMBER) =====
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE_PATH):
    EDGE_PATH = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

PROGRESS_FILE = "progress.json"   # saves your progress
LOAD_WAIT = 18                     # wait for WhatsApp Web to fully load (seconds)
SEND_DELAY = 25                    # delay between messages (safer)
BATCH_SIZE = 50                    # auto-pause every 50
BATCH_BREAK = 300                  # 5 min break

# ===== YOUR MESSAGE (with clickable group link) =====
MESSAGE = """Hello 👋

A separate student-led support community has been created for Google Gemini Student Ambassadors to help members with tasks, updates, resources, networking, collaboration, and doubt solving throughout the program.

You’re welcome to join the group here:
https://chat.whatsapp.com/HBF8OYOOvfm7ihIutciSaw

This group is independently organized by students and is only meant for helping and supporting fellow ambassadors.

Feel free to join and also share it with other ambassadors you know 🚀"""

class WhatsAppOutreach:
    def __init__(self, root):
        self.root = root
        self.root.title("WhatsApp Outreach (Simple & Safe)")
        self.root.geometry("600x620")
        self.root.configure(bg="#0f0f0f")

        # State
        self.numbers = []
        self.current_idx = 0
        self.sent_count = 0
        self.running = False
        self.paused = False

        self.load_progress()
        self.build_ui()

    def load_progress(self):
        if os.path.exists(PROGRESS_FILE):
            try:
                with open(PROGRESS_FILE, "r") as f:
                    data = json.load(f)
                self.numbers = data.get("numbers", [])
                self.current_idx = data.get("current_idx", 0)
                self.sent_count = data.get("sent_count", 0)
            except:
                pass

    def save_progress(self):
        with open(PROGRESS_FILE, "w") as f:
            json.dump({
                "numbers": self.numbers,
                "current_idx": self.current_idx,
                "sent_count": self.sent_count
            }, f)

    def clear_progress(self):
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)

    def build_ui(self):
        # Title
        tk.Label(self.root, text="🚀 Google Ambassador WhatsApp Outreach",
                 bg="#0f0f0f", fg="#4285F4", font=("Arial", 16, "bold")).pack(pady=15)

        # Warning
        warn = tk.Label(self.root,
            text="⚠️ USE A SECONDARY NUMBER ONLY!\nAutomated sending can lead to ban. Safe delays applied.",
            bg="#2a0000", fg="#ff5555", font=("Arial", 10, "bold"), padx=10, pady=6)
        warn.pack(pady=5)

        # Stats
        self.stats_label = tk.Label(self.root, text=self.get_stats_text(),
                                    bg="#0f0f0f", fg="#25D366", font=("Arial", 12, "bold"))
        self.stats_label.pack(pady=8)

        # Status
        self.status_label = tk.Label(self.root, text="Idle — Import your list to begin",
                                     bg="#0f0f0f", fg="#888888", font=("Arial", 10))
        self.status_label.pack(pady=4)

        # Buttons
        btn_frame = tk.Frame(self.root, bg="#0f0f0f")
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="📁 Import List", bg="#4285F4", fg="white",
                  command=self.import_list, padx=10, pady=6).grid(row=0, column=0, padx=5)

        self.start_btn = tk.Button(btn_frame, text="▶ START", bg="#25D366", fg="white",
                                   command=self.start, padx=10, pady=6)
        self.start_btn.grid(row=0, column=1, padx=5)

        self.pause_btn = tk.Button(btn_frame, text="⏸ PAUSE", bg="#FF9800", fg="white",
                                   command=self.toggle_pause, padx=10, pady=6, state="disabled")
        self.pause_btn.grid(row=0, column=2, padx=5)

        self.stop_btn = tk.Button(btn_frame, text="⏹ STOP", bg="#FF5252", fg="white",
                                  command=self.stop, padx=10, pady=6, state="disabled")
        self.stop_btn.grid(row=0, column=3, padx=5)

        tk.Button(btn_frame, text="🔄 RESET", bg="#666", fg="white",
                  command=self.reset, padx=10, pady=6).grid(row=0, column=4, padx=5)

        # Resume info
        if self.numbers and self.current_idx > 0:
            tk.Label(self.root, text=f"💾 Progress saved: Resuming from {self.current_idx+1}/{len(self.numbers)}",
                     bg="#0f0f0f", fg="#25D366", font=("Arial", 9, "bold")).pack()

        # Instructions
        tk.Label(self.root, text="Instructions:\n1. Login to WhatsApp Web in Edge first.\n2. Import .txt list (one number per line).\n3. Click START. Do NOT move your mouse while running.",
                 bg="#0f0f0f", fg="#aaaaaa", font=("Arial", 9), justify="left").pack(pady=10)

    def get_stats_text(self):
        total = len(self.numbers)
        remaining = max(0, total - self.current_idx)
        return f"Loaded: {total} | Sent: {self.sent_count} | Remaining: {remaining}"

    def update_stats(self):
        self.stats_label.config(text=self.get_stats_text())

    def set_status(self, text, color="#888888"):
        self.status_label.config(text=text, fg=color)

    def import_list(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = [line.strip() for line in f if line.strip()]
        except:
            messagebox.showerror("Error", "Could not read file.")
            return

        clean, seen = [], set()
        for num in raw:
            digits = "".join(filter(str.isdigit, num))
            if len(digits) == 10:
                digits = "91" + digits
            if len(digits) == 12 and digits not in seen:
                seen.add(digits)
                clean.append(digits)

        if not clean:
            messagebox.showerror("Error", "No valid Indian numbers found (10 or 12 digits).")
            return

        self.numbers = clean
        self.current_idx = 0
        self.sent_count = 0
        self.clear_progress()
        self.update_stats()
        self.set_status(f"✅ Loaded {len(clean)} numbers. Ready to start.", "#25D366")

    def start(self):
        if not self.numbers:
            messagebox.showwarning("No List", "Please import a number list first.")
            return
        if self.current_idx >= len(self.numbers):
            messagebox.showinfo("Done", "All numbers already sent. Click RESET to start over.")
            return

        if not os.path.exists(EDGE_PATH):
            messagebox.showerror("Error", "Microsoft Edge not found at expected location.")
            return

        try:
            pyautogui.size()  # test pyautogui
        except:
            messagebox.showerror("Error", "pyautogui is not working. Run: pip install pyautogui")
            return

        self.running = True
        self.paused = False
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        self.set_status("🚀 Running... DO NOT TOUCH MOUSE OR KEYBOARD!", "#25D366")

        threading.Thread(target=self.run_loop, daemon=True).start()

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.config(text="▶ RESUME")
            self.set_status("⏸ Paused. Click RESUME to continue.", "#FF9800")
        else:
            self.pause_btn.config(text="⏸ PAUSE")
            self.set_status("🚀 Running...", "#25D366")

    def stop(self):
        self.running = False
        self.save_progress()
        self.reset_buttons()
        self.set_status(f"⏹ Stopped at {self.current_idx}/{len(self.numbers)}. Progress saved.", "#FF5252")

    def reset(self):
        if messagebox.askyesno("Reset", "Clear all progress and start fresh?"):
            self.clear_progress()
            self.numbers = []
            self.current_idx = 0
            self.sent_count = 0
            self.update_stats()
            self.set_status("🔄 Reset. Import a new list.", "#888888")

    def reset_buttons(self):
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="⏸ PAUSE")
        self.stop_btn.config(state="disabled")

    def run_loop(self):
        msg_encoded = urllib.parse.quote(MESSAGE)

        while self.current_idx < len(self.numbers) and self.running:
            if self.paused:
                time.sleep(0.5)
                continue

            # Batch break every 50 messages
            if self.sent_count > 0 and self.sent_count % BATCH_SIZE == 0:
                self.set_status("🛡️ Taking 5-minute safety break...", "#FF9800")
                for _ in range(BATCH_BREAK):
                    if not self.running:
                        break
                    time.sleep(1)

            number = self.numbers[self.current_idx]
            url = f"https://web.whatsapp.com/send?phone={number}&text={msg_encoded}&type=phone_number&app_absent=1"

            self.set_status(f"📤 Opening chat {self.current_idx+1}/{len(self.numbers)} (+{number})", "#4285F4")

            try:
                subprocess.Popen([EDGE_PATH, url])
            except:
                self.set_status("Error opening Edge.", "#FF5252")
                time.sleep(2)
                self.current_idx += 1
                continue

            # Wait for WhatsApp Web to load
            time.sleep(LOAD_WAIT)

            # --- ROBUST AUTO-SEND ---
            if self.running and not self.paused:
                try:
                    screen_w, screen_h = pyautogui.size()

                    # Move to bottom-center (message input area) and click
                    pyautogui.moveTo(screen_w // 2, int(screen_h * 0.88))
                    time.sleep(0.2)
                    pyautogui.click()
                    time.sleep(1.2)

                    # Press Enter to send
                    pyautogui.press("enter")
                    time.sleep(2.5)

                    self.sent_count += 1
                    self.current_idx += 1
                    self.save_progress()
                    self.root.after(0, self.update_stats)
                    self.set_status(f"✅ Sent {self.sent_count}. Waiting {SEND_DELAY}s...", "#25D366")

                except Exception:
                    # Skip on failure
                    self.current_idx += 1
                    self.save_progress()
                    self.set_status("⚠️ Failed to send (skipped).", "#FF9800")

            # Wait between messages
            for _ in range(SEND_DELAY):
                if not self.running or self.paused:
                    break
                time.sleep(1)

        # Finished
        self.running = False
        self.clear_progress()
        self.root.after(0, self.reset_buttons)
        self.root.after(0, lambda: self.set_status(f"🎉 Done! Sent {self.sent_count} messages.", "#25D366"))
        self.root.after(0, lambda: messagebox.showinfo("Finished", f"All done! Sent {self.sent_count} messages."))

if __name__ == "__main__":
    root = tk.Tk()
    app = WhatsAppOutreach(root)
    root.mainloop()
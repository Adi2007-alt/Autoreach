# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.parse
import webbrowser
import threading
import time
import random
import os
import json
import pyautogui
import pyperclip

try:
    import pygetwindow as gw
except ImportError:
    gw = None

# Files for tracking
SENT_FILE = "sent_numbers.json"
FAILED_FILE = "failed_numbers.txt"

class SimpleAutoReach:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoReach - Simple")
        self.root.geometry("650x600")
        self.root.configure(bg="#1e1e1e")
        
        # State
        self.numbers = []
        self.current_index = 0
        self.total_count = 0
        self.sent_count = 0
        self.failed_list = []
        self.skipped_count = 0
        self.is_running = False
        self.is_paused = False
        
        # Load sent numbers
        self.sent_numbers = self.load_sent()
        
        # Build UI
        self.build_ui()
        
    def load_sent(self):
        if os.path.exists(SENT_FILE):
            try:
                with open(SENT_FILE, 'r') as f:
                    data = json.load(f)
                    return set(data)
            except:
                return set()
        return set()
    
    def save_sent(self):
        try:
            with open(SENT_FILE, 'w') as f:
                json.dump(list(self.sent_numbers), f)
        except:
            pass
    
    def build_ui(self):
        # Title
        title = tk.Label(self.root, text="AutoReach",
                         fg="#4F8CFF", bg="#1e1e1e",
                         font=("Arial", 18, "bold"))
        title.pack(pady=10)
        
        # Message box
        msg_label = tk.Label(self.root, text="Message:",
                             fg="white", bg="#1e1e1e")
        msg_label.pack(anchor="w", padx=20)
        
        self.message_text = tk.Text(self.root, height=8, width=70,
                                    bg="#2d2d2d", fg="white",
                                    insertbackground="white")
        self.message_text.pack(padx=20, pady=5)
        
        # Default message
        default_msg = (
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
        self.message_text.insert("1.0", default_msg)
        
        # Stats
        self.stats_label = tk.Label(
            self.root,
            text="Loaded: 0 | Sent: 0 | Failed: 0 | Skipped: 0",
            fg="#4CAF50", bg="#1e1e1e", font=("Arial", 10))
        self.stats_label.pack(pady=5)
        
        # Status
        self.status_label = tk.Label(
            self.root,
            text="Ready - Import numbers list",
            fg="#FF9800", bg="#1e1e1e", font=("Arial", 10))
        self.status_label.pack(pady=5)
        
        # Buttons
        btn_frame = tk.Frame(self.root, bg="#1e1e1e")
        btn_frame.pack(pady=10)
        
        self.import_btn = tk.Button(
            btn_frame, text="Import List",
            command=self.import_list,
            bg="#4F8CFF", fg="white", width=12)
        self.import_btn.grid(row=0, column=0, padx=5)
        
        self.start_btn = tk.Button(
            btn_frame, text="Start",
            command=self.start,
            bg="#4CAF50", fg="white", width=12)
        self.start_btn.grid(row=0, column=1, padx=5)
        
        self.pause_btn = tk.Button(
            btn_frame, text="Pause",
            command=self.pause,
            bg="#FF9800", fg="white", width=12,
            state="disabled")
        self.pause_btn.grid(row=0, column=2, padx=5)
        
        self.stop_btn = tk.Button(
            btn_frame, text="Stop",
            command=self.stop,
            bg="#F44336", fg="white", width=12)
        self.stop_btn.grid(row=0, column=3, padx=5)
        
        self.export_btn = tk.Button(
            btn_frame, text="Export Failed",
            command=self.export_failed,
            bg="#9C27B0", fg="white", width=12)
        self.export_btn.grid(row=1, column=0, padx=5, pady=5)
        
        # Warning
        warning = tk.Label(
            self.root,
            text="Keep WhatsApp Web open and logged in.\n"
                 "Do not touch mouse/keyboard while running.",
            fg="#F44336", bg="#1e1e1e", font=("Arial", 9))
        warning.pack(pady=10)
        
    # ── Import ────────────────────────────────────────────
    def import_list(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt")])
        if not path:
            return
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            numbers = []
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                digits = ''.join(filter(str.isdigit, s))
                if len(digits) == 10:
                    digits = '91' + digits
                if len(digits) == 12:
                    if digits not in numbers:
                        numbers.append(digits)
            self.numbers = numbers
            self.total_count = len(numbers)
            self.current_index = 0
            self.sent_count = 0
            self.failed_list = []
            self.skipped_count = 0
            self.update_stats()
            self.status_label.config(
                text=f"Loaded {self.total_count} numbers",
                fg="#4CAF50")
            messagebox.showinfo(
                "Success",
                f"Imported {self.total_count} numbers")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import: {e}")
    
    # ── Stats ─────────────────────────────────────────────
    def update_stats(self):
        self.stats_label.config(
            text=f"Loaded: {self.total_count} | "
                 f"Sent: {self.sent_count} | "
                 f"Failed: {len(self.failed_list)} | "
                 f"Skipped: {self.skipped_count}")
    
    # ── Start ─────────────────────────────────────────────
    def start(self):
        if not self.numbers:
            messagebox.showwarning(
                "Warning", "Please import numbers first")
            return
        if self.is_running:
            return
        self.is_running = True
        self.is_paused = False
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.status_label.config(text="Running...", fg="#4CAF50")
        thread = threading.Thread(
            target=self.run_process, daemon=True)
        thread.start()
    
    # ── Pause ─────────────────────────────────────────────
    def pause(self):
        if not self.is_running:
            return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.config(text="Resume")
            self.status_label.config(text="Paused", fg="#FF9800")
        else:
            self.pause_btn.config(text="Pause")
            self.status_label.config(
                text="Running...", fg="#4CAF50")
    
    # ── Stop ──────────────────────────────────────────────
    def stop(self):
        self.is_running = False
        self.is_paused = False
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="Pause")
        self.status_label.config(text="Stopped", fg="#F44336")
    
    # ── Export failed ─────────────────────────────────────
    def export_failed(self):
        if not self.failed_list:
            messagebox.showinfo(
                "Info", "No failed numbers to export")
            return
        try:
            with open(FAILED_FILE, 'w') as f:
                for num in self.failed_list:
                    f.write(num + "\n")
            messagebox.showinfo(
                "Success",
                f"Failed numbers saved to {FAILED_FILE}")
        except:
            messagebox.showerror("Error", "Failed to export")
    
    # ── Activate WhatsApp window ──────────────────────────
    def activate_whatsapp(self):
        if gw is None:
            return True
        try:
            windows = gw.getWindowsWithTitle("WhatsApp")
            if not windows:
                for w in gw.getAllWindows():
                    if "whatsapp" in w.title.lower():
                        windows.append(w)
            if windows:
                w = windows[0]
                try:
                    w.activate()
                except:
                    pass
                return True
        except:
            pass
        return True
    
    # ── Wait for message in text box ─────────────────────
    def wait_for_message(self, expected_msg, max_sec):
        elapsed = 0
        while elapsed < max_sec:
            if not self.is_running:
                return False
            while self.is_paused:
                time.sleep(0.2)
            try:
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.15)
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.15)
            except:
                pass
            clip = pyperclip.paste().strip()
            if clip == expected_msg.strip():
                return True
            elapsed += 0.5
            time.sleep(0.5)
        return False
    
    # ── Wait for text box to be empty (send confirmed) ────
    def wait_for_sent(self, max_sec):
        elapsed = 0
        while elapsed < max_sec:
            if not self.is_running:
                return False
            while self.is_paused:
                time.sleep(0.2)
            try:
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.15)
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.15)
            except:
                pass
            clip = pyperclip.paste().strip()
            if clip == "":
                return True
            elapsed += 0.3
            time.sleep(0.3)
        return False
    
    # ── Send single message ───────────────────────────────
    def send_single(self, number, message):
        msg_encoded = urllib.parse.quote(message)
        retries = 2

        for attempt in range(1, retries + 1):
            if not self.is_running:
                return False

            if attempt > 1:
                time.sleep(3)

            # Open WhatsApp Web URL
            url = (
                f"https://web.whatsapp.com/send/"
                f"?phone={number}"
                f"&text={msg_encoded}"
                f"&type=phone_number"
                f"&app_absent=1"
            )
            webbrowser.open(url)
            time.sleep(2)

            # Bring WhatsApp window to front
            self.activate_whatsapp()
            time.sleep(1)

            # Wait until message is loaded in text box
            self.set_status(
                f"● Waiting for chat to load... ({number})")
            loaded = self.wait_for_message(message, 15)

            if not loaded:
                # Message never loaded — close and retry
                self.set_status(
                    f"● Load failed attempt {attempt} for {number}")
                try:
                    pyautogui.hotkey('ctrl', 'w')
                    time.sleep(1)
                except:
                    pass
                if attempt == retries:
                    return False
                continue

            # ── Message is loaded — press Enter to send ───
            self.set_status(f"● Sending to {number}...")
            try:
                pyautogui.press('enter')
            except:
                pass

            # ✅ Wait 2 seconds so message is fully sent
            # before we close the tab
            time.sleep(2)

            # Confirm send by checking text box is empty
            sent_ok = self.wait_for_sent(5)

            # Close the tab
            try:
                pyautogui.hotkey('ctrl', 'w')
                time.sleep(1)
            except:
                pass

            if sent_ok:
                return True
            else:
                self.set_status(
                    f"● Send not confirmed attempt {attempt}")
                if attempt == retries:
                    return False

        return False
    
    # ── Helper: set status from thread ───────────────────
    def set_status(self, text):
        self.root.after(
            0, lambda: self.status_label.config(text=text))
    
    # ── Main run loop ─────────────────────────────────────
    def run_process(self):
        message = self.message_text.get("1.0", tk.END).strip()

        while self.current_index < self.total_count \
                and self.is_running:

            if self.is_paused:
                time.sleep(0.3)
                continue

            number = self.numbers[self.current_index]

            # Skip already sent numbers
            if number in self.sent_numbers:
                self.skipped_count += 1
                self.current_index += 1
                self.root.after(0, self.update_stats)
                continue

            # Send
            self.set_status(
                f"● Processing {self.current_index + 1}"
                f"/{self.total_count}: {number}")

            success = self.send_single(number, message)

            if success:
                self.sent_count += 1
                self.sent_numbers.add(number)
                self.save_sent()
                self.set_status(
                    f"✅ Sent to {number} "
                    f"({self.sent_count} sent so far)")
            else:
                self.failed_list.append(number)
                self.set_status(f"❌ Failed: {number}")

            self.current_index += 1
            self.root.after(0, self.update_stats)

            # Delay before next number
            if self.current_index < self.total_count \
                    and self.is_running:
                delay = random.uniform(8, 15)
                elapsed_d = 0
                while elapsed_d < delay:
                    if not self.is_running:
                        break
                    while self.is_paused:
                        time.sleep(0.2)
                    rem = int(delay - elapsed_d)
                    self.set_status(f"● Next message in {rem}s...")
                    time.sleep(0.5)
                    elapsed_d += 0.5

        # ── All done ──────────────────────────────────────
        self.is_running = False
        self.root.after(
            0, lambda: self.start_btn.config(state="normal"))
        self.root.after(
            0, lambda: self.pause_btn.config(
                state="disabled", text="Pause"))

        if self.current_index >= self.total_count:
            self.set_status("● All Done! 🎉")
            self.root.after(
                0, lambda: messagebox.showinfo(
                    "Finished",
                    f"✅ Sent:    {self.sent_count}\n"
                    f"❌ Failed:  {len(self.failed_list)}\n"
                    f"⏭️ Skipped: {self.skipped_count}"))
        else:
            self.set_status(
                f"● Stopped at "
                f"{self.current_index}/{self.total_count}")


# ── Run ───────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleAutoReach(root)
    root.mainloop()
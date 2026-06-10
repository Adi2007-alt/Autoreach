# -*- coding: utf-8 -*-
"""
ui/tab_send.py — AutoReach v15
Main send tab.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading

class TabSend(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, start_cb, stop_cb, dry_run_cb):
        super().__init__(parent)
        self.start_cb = start_cb
        self.stop_cb = stop_cb
        self.dry_run_cb = dry_run_cb
        self.numbers: list[str] = []
        self._build_ui()

    def _build_ui(self):
        container = ttk.Frame(self, padding=10)
        container.pack(fill="both", expand=True)

        # Numbers Top Row
        f_top = ttk.Frame(container)
        f_top.pack(fill="x", pady=5)
        ttk.Button(f_top, text="Import Numbers", command=self._import_numbers).pack(side="left", padx=(0, 10))
        ttk.Button(f_top, text="Reset List", command=self._reset_list).pack(side="left")
        
        self.lbl_loaded = ttk.Label(container, text="Numbers loaded: 0", font=("Segoe UI", 10, "bold"))
        self.lbl_loaded.pack(fill="x", pady=5)

        # Message Row
        f_msg = ttk.Frame(container)
        f_msg.pack(fill="x", pady=(10, 0))
        ttk.Label(f_msg, text="Message:").pack(side="left")
        self.var_one_send = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_msg, text="📋 One send", variable=self.var_one_send).pack(side="right")

        # Text Box
        self.txt_message = tk.Text(container, height=8, width=50)
        self.txt_message.pack(fill="x", pady=5)
        self.txt_message.bind("<KeyRelease>", self._update_char_count)

        self.lbl_chars = ttk.Label(container, text="Characters: 0")
        self.lbl_chars.pack(anchor="e")

        # Action Buttons
        f_actions = ttk.Frame(container)
        f_actions.pack(fill="x", pady=15)
        self.btn_start = ttk.Button(f_actions, text="Start", command=self._start)
        self.btn_start.pack(side="left", padx=(0, 10))
        self.btn_stop = ttk.Button(f_actions, text="Stop", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 10))
        self.btn_dry_run = ttk.Button(f_actions, text="Dry Run", command=self._dry_run)
        self.btn_dry_run.pack(side="left")

        # Progress
        self.lbl_progress = ttk.Label(container, text="Progress: 0 / 0", font=("Segoe UI", 10, "bold"))
        self.lbl_progress.pack(fill="x", pady=5)

        # Log
        self.txt_log = scrolledtext.ScrolledText(container, height=10, state="disabled")
        self.txt_log.pack(fill="both", expand=True, pady=5)

    def _import_numbers(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt"), ("CSV Files", "*.csv")])
        if not file_path:
            return
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Clean and filter numbers
            new_numbers = []
            for line in lines:
                cleaned = "".join(c for c in line if c.isdigit() or c == "+")
                if cleaned:
                    new_numbers.append(cleaned)
                    
            if not new_numbers:
                messagebox.showwarning("Warning", "No valid numbers found in file.")
                return
                
            self.numbers.extend(new_numbers)
            self.lbl_loaded.config(text=f"Numbers loaded: {len(self.numbers)}")
            self._update_progress(0, len(self.numbers))
            self.log(f"Imported {len(new_numbers)} numbers from {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import numbers:\n{e}")

    def _reset_list(self):
        self.numbers.clear()
        self.lbl_loaded.config(text="Numbers loaded: 0")
        self._update_progress(0, 0)
        self.txt_log.config(state="normal")
        self.txt_log.delete(1.0, tk.END)
        self.txt_log.config(state="disabled")

    def _update_char_count(self, event=None):
        count = len(self.txt_message.get(1.0, tk.END)) - 1
        self.lbl_chars.config(text=f"Characters: {max(0, count)}")

    def _set_running_state(self, is_running: bool):
        state = "disabled" if is_running else "normal"
        self.btn_start.config(state=state)
        self.btn_dry_run.config(state=state)
        self.btn_stop.config(state="normal" if is_running else "disabled")

    def _start(self):
        if not self.numbers:
            messagebox.showwarning("Warning", "No numbers loaded!")
            return
        msg = self.txt_message.get(1.0, tk.END).strip()
        if not msg:
            messagebox.showwarning("Warning", "Message is empty!")
            return
            
        self._set_running_state(True)
        threading.Thread(target=self.start_cb, args=(self.numbers, msg), daemon=True).start()

    def _dry_run(self):
        if not self.numbers:
            messagebox.showwarning("Warning", "No numbers loaded!")
            return
        msg = self.txt_message.get(1.0, tk.END).strip()
        if not msg:
            messagebox.showwarning("Warning", "Message is empty!")
            return
            
        self._set_running_state(True)
        threading.Thread(target=self.dry_run_cb, args=(self.numbers, msg), daemon=True).start()

    def _stop(self):
        self.stop_cb()
        self._set_running_state(False)

    def on_campaign_finished(self):
        self.after(0, lambda: self._set_running_state(False))

    def _update_progress(self, current: int, total: int):
        self.lbl_progress.config(text=f"Progress: {current} / {total}")

    def update_progress_safe(self, current: int, total: int):
        self.after(0, lambda: self._update_progress(current, total))

    def log(self, text: str):
        self.after(0, lambda: self._log_safe(text))

    def _log_safe(self, text: str):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

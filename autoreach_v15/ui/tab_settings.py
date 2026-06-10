# -*- coding: utf-8 -*-
"""
ui/tab_settings.py — AutoReach v15
Settings configuration tab.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from core.settings import Settings, save_settings

class TabSettings(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, settings: Settings):
        super().__init__(parent)
        self.settings = settings
        self.vars = {}
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)

        row = 0
        def add_field(label: str, attr_name: str, type_cast: type):
            nonlocal row
            ttk.Label(container, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=5)
            var = tk.StringVar()
            self.vars[attr_name] = (var, type_cast)
            ttk.Entry(container, textvariable=var, width=15).grid(row=row, column=1, sticky="w", pady=5, padx=5)
            row += 1

        add_field("Min delay (seconds):", "delay_min", float)
        add_field("Max delay (seconds):", "delay_max", float)
        add_field("Daily limit (0 = unlimited):", "daily_limit", int)
        add_field("Timeout per number (seconds):", "timeout", int)
        add_field("Post-send delay (seconds):", "post_send_delay", float)
        add_field("Page load wait (seconds):", "page_load_wait", float)

        # Boolean toggles
        self.var_dark_mode = tk.BooleanVar()
        ttk.Checkbutton(container, text="WhatsApp Web Dark Mode", variable=self.var_dark_mode).grid(row=row, column=0, columnspan=2, sticky="w", pady=5, padx=5)
        row += 1

        self.var_bg_mode = tk.BooleanVar()
        ttk.Checkbutton(container, text="Background Mode (System Tray)", variable=self.var_bg_mode).grid(row=row, column=0, columnspan=2, sticky="w", pady=5, padx=5)
        row += 1

        # Send mode radios
        ttk.Label(container, text="Send Mode:").grid(row=row, column=0, sticky="w", pady=5, padx=5)
        self.var_send_mode = tk.StringVar()
        f_radios = ttk.Frame(container)
        f_radios.grid(row=row, column=1, sticky="w", pady=5, padx=5)
        ttk.Radiobutton(f_radios, text="One message", variable=self.var_send_mode, value="one").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(f_radios, text="Split paragraphs", variable=self.var_send_mode, value="split").pack(side="left")
        row += 1

        ttk.Button(container, text="Save Settings", command=self._save).grid(row=row, column=0, columnspan=2, pady=20)

    def _load_values(self):
        for attr, (var, type_cast) in self.vars.items():
            var.set(str(getattr(self.settings, attr)))
        self.var_dark_mode.set(self.settings.dark_mode)
        self.var_bg_mode.set(self.settings.background_mode)
        self.var_send_mode.set(self.settings.send_mode)

    def _save(self):
        try:
            for attr, (var, type_cast) in self.vars.items():
                val = type_cast(var.get())
                setattr(self.settings, attr, val)
                
            self.settings.dark_mode = self.var_dark_mode.get()
            self.settings.background_mode = self.var_bg_mode.get()
            self.settings.send_mode = self.var_send_mode.get()

            if save_settings(self.settings):
                messagebox.showinfo("Success", "Settings saved successfully.")
            else:
                messagebox.showerror("Error", "Failed to save settings to file.")
        except ValueError as e:
            messagebox.showerror("Validation Error", f"Invalid input format: {e}")

# -*- coding: utf-8 -*-
"""
ui/tab_tips.py — AutoReach v15
Anti-ban tips and guidance.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class TabTips(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        lbl_title = ttk.Label(self, text="Anti-Ban Best Practices", font=("Segoe UI", 16, "bold"))
        lbl_title.pack(pady=(20, 10))

        tips = [
            "• Use only for people who opted in to receive messages.",
            "• Keep daily limit under 40.",
            "• Use realistic delays (10–25 sec).",
            "• Don't run 24/7; pause overnight.",
            "• Warm up new accounts: start with 10/day, increase slowly.",
            "• Enable WhatsApp Web dark mode for better pixel detection."
        ]

        for tip in tips:
            lbl = ttk.Label(self, text=tip, font=("Segoe UI", 11), justify="left")
            lbl.pack(anchor="w", padx=40, pady=5)

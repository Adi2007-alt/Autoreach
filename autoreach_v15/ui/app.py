# -*- coding: utf-8 -*-
"""
ui/app.py — AutoReach v15
Root Tk window, tab container.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from ui.tab_send import TabSend
from ui.tab_settings import TabSettings
from ui.tab_tips import TabTips
from core.settings import Settings

class AutoReachApp(tk.Tk):
    def __init__(self, settings: Settings, start_cb, stop_cb, dry_run_cb):
        super().__init__()
        self.settings = settings
        self.title("AutoReach v15 - WhatsApp Bulk Sender")
        self.geometry("600x600")
        
        # Make it look a bit more modern
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
            
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_send = TabSend(self.notebook, start_cb, stop_cb, dry_run_cb)
        self.tab_settings = TabSettings(self.notebook, settings)
        self.tab_tips = TabTips(self.notebook)
        
        self.notebook.add(self.tab_send, text="Send")
        self.notebook.add(self.tab_settings, text="Settings")
        self.notebook.add(self.tab_tips, text="Anti-Ban Tips")

    def log(self, text: str):
        self.tab_send.log(text)

    def update_progress(self, current: int, total: int):
        self.tab_send.update_progress_safe(current, total)
        
    def on_campaign_finished(self):
        self.tab_send.on_campaign_finished()

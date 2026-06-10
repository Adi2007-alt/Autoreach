# -*- coding: utf-8 -*-
"""
main.py — AutoReach v15
Entry point, launches GUI, manages background tray icon.
"""
import logging
import os
import sys
import threading
import tkinter as tk

import pystray
from PIL import Image, ImageDraw

from core.settings import load_settings
from core.scheduler import Scheduler
from ui.app import AutoReachApp

# Set working directory to the directory of main.py
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class AutoReachMain:
    def __init__(self):
        self.settings = load_settings()
        self.scheduler = Scheduler(self.settings)
        self.tray_icon = None
        
        self.app = AutoReachApp(
            settings=self.settings,
            start_cb=self._start_campaign,
            stop_cb=self._stop_campaign,
            dry_run_cb=self._start_dry_run
        )
        
        # Handle window close gracefully
        self.app.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_tray_icon(self):
        """Create and run the system tray icon."""
        if self.tray_icon is not None:
            return
            
        def create_image():
            image = Image.new('RGB', (64, 64), color=(255, 255, 255))
            dc = ImageDraw.Draw(image)
            dc.ellipse((0, 0, 64, 64), fill=(0, 168, 132))
            return image
            
        def show_window(icon, item):
            self.app.after(0, self.app.deiconify)
            
        def stop_action(icon, item):
            self._stop_campaign()
            
        def quit_action(icon, item):
            icon.stop()
            self._stop_campaign()
            self.app.after(0, self.app.destroy)

        menu = pystray.Menu(
            pystray.MenuItem("Show AutoReach", show_window, default=True),
            pystray.MenuItem("Stop", stop_action),
            pystray.MenuItem("Quit", quit_action)
        )
        
        self.tray_icon = pystray.Icon("AutoReach", create_image(), "AutoReach v15", menu=menu)
        # run_detached runs the tray icon in a separate thread
        self.tray_icon.run_detached()

    def _start_campaign(self, numbers, message):
        self.settings.dry_run = False
        self._run_scheduler(numbers, message)

    def _start_dry_run(self, numbers, message):
        self.settings.dry_run = True
        self._run_scheduler(numbers, message)

    def _run_scheduler(self, numbers, message):
        if self.settings.background_mode:
            self.app.after(0, self.app.withdraw)
            self._create_tray_icon()
            
        # The scheduler blocks, so this is called from a thread spawned by tab_send
        try:
            self.scheduler.run_campaign(
                numbers, 
                message, 
                progress_cb=self.app.update_progress,
                log_cb=self.app.log
            )
        finally:
            # Campaign finished or stopped
            self.app.on_campaign_finished()
            if self.settings.background_mode:
                self.app.after(0, self.app.deiconify)
                self.app.after(0, self.app.bell)

    def _stop_campaign(self):
        self.scheduler.stop()

    def _on_close(self):
        """Clean up on app close."""
        self._stop_campaign()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.app.destroy()

    def run(self):
        self.app.mainloop()

if __name__ == "__main__":
    app_main = AutoReachMain()
    app_main.run()

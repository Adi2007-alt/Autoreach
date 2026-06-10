# -*- coding: utf-8 -*-
import logging
import pyautogui
import ctypes
import sys

logger = logging.getLogger("autoreach.screen_analyser")

class ScreenAnalyser:
    def __init__(self, tolerance: int = 55):
        self.tolerance = tolerance
        self.wa_green = (0, 168, 132)  # #00A884 Brand Color
        self.scale_factor = self._detect_scaling()
        
    def _detect_scaling(self) -> float:
        """Detect OS-level UI scaling for coordinate normalization."""
        if sys.platform != "win32":
            return 1.0
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88) # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return dpi / 96.0
        except Exception as e:
            logger.debug(f"Failed to detect display scaling: {e}")
            return 1.0

    def get_region_box(self, win, pct_x, pct_y, pct_w, pct_h):
        """Calculates dynamic absolute coordinates based on percentage geometry."""
        try:
            rx = int((win.left + (win.width * pct_x)) / self.scale_factor)
            ry = int((win.top + (win.height * pct_y)) / self.scale_factor)
            rw = int((win.width * pct_w) / self.scale_factor)
            rh = int((win.height * pct_h) / self.scale_factor)
            return rx, ry, rw, rh
        except Exception as e:
            logger.error(f"Error building region boundaries: {e}")
            return None

    def is_wa_page_ready(self, win) -> bool:
        """Confirms UI rendering by looking for the green header bar pixels."""
        if not win:
            return False
        coords = self.get_region_box(win, 0.0, 0.0, 1.0, 0.18)
        if not coords:
            return False
        rx, ry, rw, rh = coords
        try:
            screenshot = pyautogui.screenshot(region=(rx, ry, rw, rh))
            for x in range(0, rw, 5):
                for y in range(0, rh, 5):
                    r, g, b = screenshot.getpixel((x, y))[:3]
                    if (abs(r - self.wa_green[0]) <= self.tolerance and 
                        abs(g - self.wa_green[1]) <= self.tolerance and 
                        abs(b - self.wa_green[2]) <= self.tolerance):
                        return True
        except Exception as e:
            logger.error(f"Error during pixel scanning: {e}")
        return False

    def find_input_box(self, win):
        """Calculates precise input box target coordinates to avoid text clipping."""
        if not win:
            return None
        cx = int((win.left + (win.width * 0.5)) / self.scale_factor)
        cy = int((win.top + (win.height * 0.965)) / self.scale_factor)  # Bottom chat field placement
        return cx, cy

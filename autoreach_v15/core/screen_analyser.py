# -*- coding: utf-8 -*-
"""
core/screen_analyser.py — AutoReach v15
Pixel-based page-ready and send detection using Pillow.
"""
from __future__ import annotations

import pyautogui
from PIL import Image

# WhatsApp Colors
WA_GREEN = (0, 168, 132)      # #00A884
DARK_STRIP = (32, 44, 51)     # #202C33
LIGHT_STRIP = (240, 242, 245) # #F0F2F5
ERROR_RED = (244, 67, 54)     # #F44336

def _color_match(pixel: tuple[int, int, int], target: tuple[int, int, int], tolerance: int) -> bool:
    """Check if a pixel matches a target color within a tolerance."""
    if len(pixel) >= 3:
        r, g, b = pixel[:3]
        tr, tg, tb = target[:3]
        return abs(r - tr) <= tolerance and abs(g - tg) <= tolerance and abs(b - tb) <= tolerance
    return False

def is_wa_page_ready(win) -> bool:
    """
    Check if WhatsApp Web is fully loaded.
    Returns True if WA green header AND input strip are visible.
    """
    try:
        # 1. Screenshot top 8% for WA green header
        header_region = (win.left, win.top, win.width, max(1, int(win.height * 0.08)))
        header_img = pyautogui.screenshot(region=header_region)
        header_found = False
        
        # Scan header with 10px density for speed
        for x in range(0, header_img.width, 10):
            for y in range(0, header_img.height, 10):
                if _color_match(header_img.getpixel((x, y)), WA_GREEN, 30):
                    header_found = True
                    break
            if header_found:
                break
                
        # 2. Screenshot bottom 10% for input strip
        strip_height = max(1, int(win.height * 0.10))
        strip_region = (win.left, win.bottom - strip_height, win.width, strip_height)
        strip_img = pyautogui.screenshot(region=strip_region)
        strip_found = False
        
        # Scan strip with 10px density
        for x in range(0, strip_img.width, 10):
            for y in range(0, strip_img.height, 10):
                px = strip_img.getpixel((x, y))
                if _color_match(px, DARK_STRIP, 20) or _color_match(px, LIGHT_STRIP, 20):
                    strip_found = True
                    break
            if strip_found:
                break

        return header_found and strip_found
    except Exception:
        return False

def find_send_button(win) -> tuple[int, int] | None:
    """
    Scan bottom-right 40%x25% region for WA green (#00A884).
    Returns center (x, y) of the green cluster, or None.
    """
    try:
        scan_width = max(1, int(win.width * 0.40))
        scan_height = max(1, int(win.height * 0.25))
        region = (win.right - scan_width, win.bottom - scan_height, scan_width, scan_height)
        img = pyautogui.screenshot(region=region)
        
        points = []
        # Scan at 4px grid density
        for x in range(0, img.width, 4):
            for y in range(0, img.height, 4):
                if _color_match(img.getpixel((x, y)), WA_GREEN, 55):
                    points.append((x, y))
                    
        if not points:
            return None
            
        # Center of the green cluster
        avg_x = sum(p[0] for p in points) // len(points)
        avg_y = sum(p[1] for p in points) // len(points)
        return (region[0] + avg_x, region[1] + avg_y)
    except Exception:
        return None

def find_input_box(win) -> tuple[int, int] | None:
    """
    Scan bottom 15% of window for input strip.
    Returns center (x, y).
    """
    try:
        scan_height = max(1, int(win.height * 0.15))
        region = (win.left, win.bottom - scan_height, win.width, scan_height)
        img = pyautogui.screenshot(region=region)
        
        points = []
        for x in range(0, img.width, 10):
            for y in range(0, img.height, 10):
                px = img.getpixel((x, y))
                if _color_match(px, DARK_STRIP, 20) or _color_match(px, LIGHT_STRIP, 20):
                    points.append((x, y))
                    
        if not points:
            return None
            
        avg_x = sum(p[0] for p in points) // len(points)
        avg_y = sum(p[1] for p in points) // len(points)
        return (region[0] + avg_x, region[1] + avg_y)
    except Exception:
        return None

def detect_invalid_number(win) -> bool:
    """
    Look for WA error red (#F44336 ±30) in center 60% of window.
    Returns True if found (invalid number dialog shown).
    """
    try:
        scan_width = max(1, int(win.width * 0.60))
        scan_height = max(1, int(win.height * 0.60))
        left = win.left + int(win.width * 0.20)
        top = win.top + int(win.height * 0.20)
        region = (left, top, scan_width, scan_height)
        img = pyautogui.screenshot(region=region)
        
        for x in range(0, img.width, 10):
            for y in range(0, img.height, 10):
                if _color_match(img.getpixel((x, y)), ERROR_RED, 30):
                    return True
        return False
    except Exception:
        return False

def diagnose(win) -> str:
    """
    Returns human-readable string of what is visible.
    """
    try:
        ready = is_wa_page_ready(win)
        send_btn = find_send_button(win)
        input_box = find_input_box(win)
        invalid = detect_invalid_number(win)
        
        status = []
        status.append("✅ WA header/strip found" if ready else "❌ WA header/strip not found")
        status.append("✅ Send button found" if send_btn else "❌ Send button not found")
        status.append("✅ Input box found" if input_box else "❌ Input box not found")
        status.append("⚠️ Invalid number dialog shown" if invalid else "✅ No error dialog")
        
        return " | ".join(status)
    except Exception as e:
        return f"❌ Diagnosis failed: {str(e)}"

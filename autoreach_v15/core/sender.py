# -*- coding: utf-8 -*-
"""
core/sender.py — AutoReach v15
Opens WhatsApp Web, pastes msg, sends.
"""
from __future__ import annotations

import logging
import random
import re
import time
import urllib.parse
import webbrowser
import pyautogui
import pyperclip
import pygetwindow

from core.settings import Settings
from core.screen_analyser import is_wa_page_ready

logger = logging.getLogger(__name__)

# Fail-safe feature of pyautogui
pyautogui.FAILSAFE = True

# Invisible unicode characters for anti-ban message variation
INVISIBLE_CHARS = ["\u200b", "\u200c", "\u200d", "\u2060"]

def _add_invisible_variation(message: str) -> str:
    """Insert one invisible Unicode character at a random word boundary."""
    char = random.choice(INVISIBLE_CHARS)
    words = message.split()
    if not words:
        return message + char
    insert_idx = random.randint(0, len(words))
    words.insert(insert_idx, char)
    # Join using original whitespace could be tricky, but basic space join is fine
    # A safer way: regex replace to insert at a random space
    spaces = [m.start() for m in re.finditer(r'\s+', message)]
    if spaces:
        idx = random.choice(spaces)
        return message[:idx] + char + message[idx:]
    else:
        return message + char

def _clear_input_box() -> bool:
    """Clear the input box via keyboard shortcuts. Return True if confirmed empty."""
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.1)
    pyperclip.copy("")
    
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)
    
    # Verify empty
    pyperclip.copy("___EMPTY___")
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.1)
    
    if pyperclip.paste() == "___EMPTY___" or pyperclip.paste().strip() == "":
        return True
    return False

def _paste_and_verify(text: str) -> bool:
    """Paste text and verify it landed. Retry up to 3 times."""
    for attempt in range(3):
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.4)
        
        # Verify paste landed
        pyperclip.copy("___CHECK___")
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.1)
        
        pasted = pyperclip.paste().strip()
        
        if pasted == text.strip():
            # Deselect the text so Enter sends it instead of deleting it!
            pyautogui.press("right")
            time.sleep(0.1)
            return True
            
        logger.warning(f"Paste verification failed (attempt {attempt+1}/3). Retrying...")
        _clear_input_box()
        
    return False

def send_message(number: str, message: str, settings: Settings, dry_run: bool = False) -> bool:
    """
    Core send logic.
    Returns True if sent successfully, False otherwise.
    """
    if dry_run or settings.dry_run:
        logger.info(f"DRY RUN: Would send to {number}")
        return True
        
    if settings.vary_message:
        message = _add_invisible_variation(message)

    # 1. Build URL & Open
    url = f"https://web.whatsapp.com/send?phone={number}&text="
    webbrowser.open(url)
    
    # 2. Wait for page load
    time.sleep(settings.page_load_wait)
    
    start_time = time.time()
    win = None
    wa_ready = False
    
    while time.time() - start_time < settings.timeout:
        windows = pygetwindow.getWindowsWithTitle("WhatsApp")
        if windows:
            win = windows[0]
            if is_wa_page_ready(win):
                wa_ready = True
                break
        time.sleep(1)
        
    if not wa_ready or not win:
        logger.error(f"Failed to load WhatsApp for {number} within {settings.timeout}s.")
        # Close tab anyway to prevent pileup
        pyautogui.hotkey("ctrl", "w")
        return False
        
    # 3. Focus Window
    try:
        win.activate()
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"Window activation issue: {e}")
        
    # 4. Tab 3 times
    pyautogui.press("tab", presses=3, interval=0.2)
    time.sleep(0.5)
    
    # 5. Clear pre-filled text
    if not _clear_input_box():
        logger.warning("Could not definitively clear input box, but proceeding.")
        
    # 6. Paste & Send
    try:
        if settings.send_mode == "split":
            paragraphs = re.split(r'\n\s*\n', message)
            for i, p in enumerate(paragraphs):
                # Within paragraph, replace single newlines with Shift+Enter
                lines = p.split('\n')
                for j, line in enumerate(lines):
                    if not _paste_and_verify(line):
                        raise RuntimeError("Paste verification failed persistently.")
                    if j < len(lines) - 1:
                        pyautogui.hotkey("shift", "enter")
                        time.sleep(0.2)
                
                # After paragraph, press Enter to send, UNLESS we want to send it all at once?
                # Spec says: "Enter to send final paragraph" but wait, "For each paragraph: paste -> Shift+Enter after each line within paragraph -> Enter to send final paragraph."
                # Does it mean we send each paragraph separately? Yes, "Enter to send"
                pyautogui.press("enter")
                time.sleep(0.5)
        else:
            # send_mode == "one"
            if not _paste_and_verify(message):
                raise RuntimeError("Paste verification failed persistently.")
            pyautogui.press("enter")
            
        # 9. Wait post-send delay
        time.sleep(settings.post_send_delay)
        
        # 10. Close tab
        pyautogui.hotkey("ctrl", "w")
        return True
        
    except Exception as e:
        logger.error(f"Error during send interaction: {e}")
        pyautogui.hotkey("ctrl", "w")
        return False

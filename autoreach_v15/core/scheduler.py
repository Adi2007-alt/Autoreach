# -*- coding: utf-8 -*-
"""
core/scheduler.py — AutoReach v15
Loops through number list, enforces delays/limits.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable

import pyautogui

from core.settings import Settings
from core.sender import send_message

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.is_running = False
        self.is_paused = False
        self.sent_count = 0
        
    def _gaussian_delay(self):
        """Calculate and wait gaussian delay with mouse jitter."""
        if self.settings.delay_min >= self.settings.delay_max:
            target_delay = self.settings.delay_max
        else:
            mid = (self.settings.delay_min + self.settings.delay_max) / 2
            spread = (self.settings.delay_max - self.settings.delay_min) / 4
            target_delay = random.gauss(mid, spread)
            target_delay = max(self.settings.delay_min, min(self.settings.delay_max, target_delay))
            
        logger.info(f"Waiting {target_delay:.1f}s before next message...")
        
        start = time.time()
        while time.time() - start < target_delay:
            if not self.is_running:
                break
                
            # Mouse jitter (anti-ban): every 3s (roughly handled by waking up often)
            # We'll sleep 3 seconds at a time
            sleep_time = min(3.0, target_delay - (time.time() - start))
            time.sleep(sleep_time)
            
            if self.is_running and not self.settings.dry_run:
                try:
                    # Move mouse ±3 pixels
                    mx, my = pyautogui.position()
                    dx = random.randint(-3, 3)
                    dy = random.randint(-3, 3)
                    pyautogui.moveTo(mx + dx, my + dy, duration=0.2)
                except pyautogui.FailSafeException:
                    logger.warning("Failsafe triggered! Stopping campaign.")
                    self.is_running = False
                    break
                except Exception as e:
                    logger.debug(f"Jitter failed: {e}")

    def run_campaign(self, numbers: list[str], message: str, 
                     progress_cb: Callable[[int, int], None],
                     log_cb: Callable[[str], None]) -> None:
        """
        Run the campaign for a list of numbers.
        """
        self.is_running = True
        self.is_paused = False
        self.sent_count = 0
        total = len(numbers)
        
        progress_cb(0, total)
        log_cb("Campaign started.")
        
        for i, number in enumerate(numbers):
            if not self.is_running:
                log_cb("Campaign stopped by user.")
                break
                
            # Check daily limit
            if self.settings.daily_limit > 0 and self.sent_count >= self.settings.daily_limit:
                log_cb(f"Daily limit ({self.settings.daily_limit}) reached. Pausing campaign.")
                self.is_paused = True
                self.is_running = False
                break
                
            log_cb(f"Sending to {number}...")
            
            success = send_message(number, message, self.settings, self.settings.dry_run)
            
            if success:
                self.sent_count += 1
                log_cb(f"Successfully sent to {number}")
            else:
                log_cb(f"Failed to send to {number}")
                
            progress_cb(i + 1, total)
            
            # Delay before next (unless it's the last one or we stopped)
            if self.is_running and i < total - 1:
                self._gaussian_delay()
                
        if self.settings.dry_run:
            log_cb("Dry run complete")
        else:
            log_cb("Campaign complete")
            
        self.is_running = False
        
    def stop(self):
        self.is_running = False

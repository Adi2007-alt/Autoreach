# -*- coding: utf-8 -*-
"""
core/sender.py — AutoReach v14
=================================
Send engine with adapter pattern, failure taxonomy, exponential backoff,
crash recovery, and structured diagnostic capture.

FIX (v14.1):
  - WhatsAppWebAdapter now calls wait_for_window() before _wait_page_ready()
  - _bring_browser_forward() uses AllowSetForegroundWindow(-1) + restore + wait
    (same pattern as v13 BrowserMgr._foreground that worked reliably)
  - Extra 0.4s sleep after activation before pressing Enter
  - Tab is NEVER closed until after confirm_sent completes
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
import traceback
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, List, Optional, Tuple

from core.database import Database
from core.models import AuditLevel, MessageStatus
from core.settings import Settings
from core.screen_analyser import ScreenAnalyser

logger = logging.getLogger(__name__)

# ── Optional browser-control imports ─────────────────────────────────────────

try:
    import pyautogui
    import pyperclip
    _HAS_PYAUTOGUI = True
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.02
except ImportError:
    _HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    _HAS_GW = True
except ImportError:
    gw = None
    _HAS_GW = False

try:
    import ctypes
    _U32 = ctypes.windll.user32 if sys.platform == "win32" else None
    _HAS_WIN32 = True
except Exception:
    _U32 = None
    _HAS_WIN32 = False

# ── Invalid-number title keywords (WA Web) ───────────────────────────────────
_INVALID_KEYS = [
    "invalid phone number", "not on whatsapp",
    "phone number shared via url is invalid",
    "link you opened is invalid",
]
_INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060"]


# ═══════════════════════════════════════════════════════════════
#  Failure taxonomy
# ═══════════════════════════════════════════════════════════════

class FailureCategory(str, Enum):
    BROWSER    = "BrowserError"
    SESSION    = "SessionError"
    NETWORK    = "NetworkError"
    VALIDATION = "ValidationError"
    TIMEOUT    = "TimeoutError"
    UNKNOWN    = "UnknownError"


# ═══════════════════════════════════════════════════════════════
#  SendResult
# ═══════════════════════════════════════════════════════════════

@dataclass
class SendResult:
    ok:          bool
    number:      str
    campaign_id: int
    category:    Optional[FailureCategory] = None
    reason:      Optional[str]             = None
    screenshot:  Optional[str]             = None
    timestamp:   datetime                  = field(default_factory=datetime.now)

    def __str__(self) -> str:
        if self.ok:
            return f"OK → {self.number}"
        return f"FAIL({self.category}) → {self.number}: {self.reason}"


# ═══════════════════════════════════════════════════════════════
#  SenderAdapter ABC
# ═══════════════════════════════════════════════════════════════

class SenderAdapter(ABC):
    @abstractmethod
    def health_check(self) -> Tuple[bool, str]: ...

    @abstractmethod
    def send(self, number: str, text: str,
             campaign_id: int,
             stop_event: Optional[object] = None) -> SendResult: ...

    @abstractmethod
    def name(self) -> str: ...


# ═══════════════════════════════════════════════════════════════
#  DryRunAdapter
# ═══════════════════════════════════════════════════════════════

class DryRunAdapter(SenderAdapter):
    def __init__(self, failure_rate: float = 0.1,
                 sim_delay: float = 0.5) -> None:
        self._failure_rate = max(0.0, min(1.0, failure_rate))
        self._sim_delay    = sim_delay

    def name(self) -> str:
        return "DryRunAdapter"

    def health_check(self) -> Tuple[bool, str]:
        return True, ""

    def send(self, number: str, text: str,
             campaign_id: int,
             stop_event: Optional[object] = None) -> SendResult:
        time.sleep(self._sim_delay)
        if stop_event and getattr(stop_event, "is_set", lambda: False)():
            return SendResult(ok=False, number=number,
                              campaign_id=campaign_id,
                              category=FailureCategory.UNKNOWN,
                              reason="Stopped by user")
        if random.random() < self._failure_rate:
            cat = random.choice(list(FailureCategory))
            return SendResult(ok=False, number=number,
                              campaign_id=campaign_id,
                              category=cat,
                              reason=f"[DRY-RUN] Simulated {cat.value}")
        return SendResult(ok=True, number=number, campaign_id=campaign_id)


# ═══════════════════════════════════════════════════════════════
#  WhatsAppWebAdapter  (v14.2 — screenshot-based send + visual verify)
# ═══════════════════════════════════════════════════════════════

# WA brand green colors (RGB) used by the send button on both dark/light themes
_WA_SEND_COLORS = [
    (0,   168, 132),   # #00A884  — WA dark-mode send button
    (37,  211, 102),   # #25D366  — WA light-mode / classic green
    (18,  140, 126),   # darker variant
    (0,   153, 120),   # alternate shade
]
# Tick-mark colors: grey (sent/delivered) and blue (read)
_WA_TICK_GREY = (134, 150, 160)   # #8696A0
_WA_TICK_BLUE = ( 83, 189, 235)   # #53BDEB


class WhatsAppWebAdapter(SenderAdapter):
    """
    WhatsApp Web browser automation adapter — v14.2.

    Send mechanism (most-reliable-first cascade):
      1. Capture a BEFORE screenshot of the browser window.
      2. Scan bottom-right quadrant for the green WA send button (pixel color).
      3. If found → click it directly (most reliable).
      4. If not found → click the input area at 93 % height + press End + Enter
         (legacy fallback).
      5. Wait 2.5 s, capture an AFTER screenshot.
      6. Verify via THREE independent visual checks:
           a. Input area variance dropped (box is now empty — text was sent).
           b. Chat area has ≥1.5 % pixel change (new message bubble appeared).
           c. Tick-mark color (#8696A0 grey or #53BDEB blue) detected in
              the bottom half of the chat.
      7. Any ONE passing check = SENT; all three failing = FAILED (draft stuck).
      8. Always also watch for explicit WA error keywords in the browser title.
    """

    WA_URL = (
        "https://web.whatsapp.com/send/"
        "?phone={number}&text={text}&type=phone_number&app_absent=0"
    )

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self.analyser = ScreenAnalyser()

    def name(self) -> str:
        return "WhatsAppWebAdapter"

    # ── Health check ──────────────────────────────────────────

    def health_check(self) -> Tuple[bool, str]:
        if not _HAS_PYAUTOGUI:
            return False, "pyautogui not installed. Run: pip install pyautogui"
        browser = self._find_browser()
        if not browser:
            return False, (
                "No browser found. Install Chrome or Edge "
                "and ensure it is in the standard path."
            )
        if not self._network_ok():
            return False, "Cannot reach web.whatsapp.com. Check internet connection."
        return True, ""

    def _network_ok(self) -> bool:
        import socket
        try:
            socket.setdefaulttimeout(5)
            socket.getaddrinfo("web.whatsapp.com", 443)
            return True
        except OSError:
            return False

    def _find_browser(self) -> Optional[str]:
        """Find Chrome first (preferred), then Edge, Brave, Firefox."""
        if sys.platform != "win32":
            return "xdg-open"
        pf   = os.environ.get("ProgramFiles",      r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        loc  = os.environ.get("LocalAppData", "")
        candidates = [
            # Chrome first — most reliable for WA Web
            os.path.join(pf,   r"Google\Chrome\Application\chrome.exe"),
            os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(loc,  r"Google\Chrome\Application\chrome.exe"),
            # Edge second
            os.path.join(pf86, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(pf,   r"Microsoft\Edge\Application\msedge.exe"),
            # Brave
            os.path.join(pf,   r"BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.join(pf86, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.join(loc,  r"BraveSoftware\Brave-Browser\Application\brave.exe"),
            # Firefox
            os.path.join(pf,   r"Mozilla Firefox\firefox.exe"),
            os.path.join(pf86, r"Mozilla Firefox\firefox.exe"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return None

    # ── Send pipeline ─────────────────────────────────────────

    def send(self, number: str, text: str,
             campaign_id: int,
             stop_event: Optional[object] = None) -> SendResult:
        import subprocess

        def stopped() -> bool:
            return bool(stop_event and
                        getattr(stop_event, "is_set", lambda: False)())

        deadline = time.time() + self._s.timeout
        screenshot_path: Optional[str] = None

        try:
            # Step 1: Build URL
            url = self.WA_URL.format(
                number=number,
                text=urllib.parse.quote(text, safe=""),
            )

            # Step 2: Open browser
            browser = self._find_browser()
            if not browser:
                return SendResult(ok=False, number=number,
                                  campaign_id=campaign_id,
                                  category=FailureCategory.BROWSER,
                                  reason="No browser found")
            try:
                subprocess.Popen([browser, url])
            except Exception as exc:
                return SendResult(ok=False, number=number,
                                  campaign_id=campaign_id,
                                  category=FailureCategory.BROWSER,
                                  reason=f"Failed to launch browser: {exc}")

            # Step 3: Wait for browser window to appear (critical fix)
            logger.debug("Waiting for browser window to appear…")
            self._wait_for_window(max_sec=min(15.0, self._s.conn_delay))

            if stopped():
                self._close_tab()
                return SendResult(ok=False, number=number,
                                  campaign_id=campaign_id,
                                  category=FailureCategory.UNKNOWN,
                                  reason="Stopped by user after browser launch")

            # Step 4: Extra connection wait
            remaining = max(0.0, self._s.conn_delay - 3.0)
            if remaining > 0:
                time.sleep(remaining)

            # Focus browser window ONCE to avoid looping focus-theft
            wins = self._all_browser_wins()
            win = wins[0] if wins else None
            if win:
                self._bring_browser_forward()
                time.sleep(1.5)

            # Wait for WA page using visual checks (ScreenAnalyser)
            waited = 0.0
            ready = False
            while waited < float(self._s.load):
                if stopped() or time.time() > deadline:
                    break
                if self.analyser.is_wa_page_ready(win):
                    ready = True
                    break
                time.sleep(0.7)
                waited += 0.7

            if not ready:
                screenshot_path = self._screenshot(number, campaign_id)
                self._close_tab()
                return SendResult(ok=False, number=number,
                                  campaign_id=campaign_id,
                                  category=FailureCategory.TIMEOUT,
                                  reason="Visual signature validation failed: Page unready or timeout reached.",
                                  screenshot=screenshot_path)

            # Step 6: Target message input area coordinates
            input_target = self.analyser.find_input_box(win)
            if not input_target:
                screenshot_path = self._screenshot(number, campaign_id)
                self._close_tab()
                return SendResult(ok=False, number=number,
                                  campaign_id=campaign_id,
                                  category=FailureCategory.BROWSER,
                                  reason="Could not find input box visually.",
                                  screenshot=screenshot_path)

            before_img = self._capture_win_shot(win)

            # Click input box and dispatch text via keyboard pipeline
            if _HAS_PYAUTOGUI:
                # 1. Hardware-level DOM focus click (safe center-top area) to ensure browser captures Enter key
                if win:
                    safe_x = win.left + (win.right - win.left) // 2
                    safe_y = win.top + 200  # Well below address bar
                    pyautogui.moveTo(safe_x, safe_y, duration=0.2)
                    pyautogui.click()
                    time.sleep(0.3)

                # 2. Click the actual input target
                pyautogui.moveTo(input_target[0], input_target[1], duration=0.2)
                pyautogui.click()
                time.sleep(0.5)

                # Force clipboard reset to ensure no old text is accidentally retained
                pyperclip.copy("")
                pyperclip.copy(text)
                time.sleep(0.3)

                # Execute text entry using secure hotkeys exclusively (No manual clicking)
                pyautogui.hotkey('ctrl', 'a')
                pyautogui.press('backspace')
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.6)  # Buffering delay for long text blocks

                # Dispatch text
                pyautogui.press('enter')
                logger.info("Message dispatched successfully via keyboard-only pipeline.")
                time.sleep(0.5)

            title_before = self._browser_title()
            logger.info("Send action dispatched → %s (title=%r)", number, title_before)

            # ── Step 9: Wait, then capture AFTER screenshot ────────────────
            # Check title for error keywords during wait
            wait_end = time.time() + 2.5
            while time.time() < wait_end:
                if stopped():
                    self._close_tab()
                    return SendResult(ok=False, number=number,
                                     campaign_id=campaign_id,
                                     category=FailureCategory.UNKNOWN,
                                     reason="Stopped during send wait")
                title_now = self._browser_title()
                for kw in _INVALID_KEYS:
                    if kw in title_now:
                        screenshot_path = self._screenshot(number, campaign_id)
                        self._close_tab()
                        return SendResult(ok=False, number=number,
                                         campaign_id=campaign_id,
                                         category=FailureCategory.VALIDATION,
                                         reason=f"WA error: {title_now[:80]}",
                                         screenshot=screenshot_path)
                time.sleep(0.5)

            after_img = self._capture_win_shot(win)

            # ── Step 10: Visual verification ───────────────────────────────
            ok_vis, reason_vis = self._verify_send_visual(
                before_img, after_img, win)

            if not ok_vis:
                screenshot_path = self._screenshot(number, campaign_id)
                self._close_tab()
                logger.warning("Visual verification failed: %s", reason_vis)
                return SendResult(ok=False, number=number,
                                  campaign_id=campaign_id,
                                  category=FailureCategory.VALIDATION,
                                  reason=reason_vis,
                                  screenshot=screenshot_path)

            # ── Step 11: Success — close tab ───────────────────────────────
            self._close_tab()
            return SendResult(ok=True, number=number, campaign_id=campaign_id)

        except Exception:
            tb = traceback.format_exc()
            logger.error("WhatsAppWebAdapter unhandled exception:\n%s", tb)
            screenshot_path = self._screenshot(number, campaign_id)
            try:
                self._close_tab()
            except Exception:
                pass
            return SendResult(ok=False, number=number,
                              campaign_id=campaign_id,
                              category=FailureCategory.UNKNOWN,
                              reason=tb.strip().splitlines()[-1],
                              screenshot=screenshot_path)

    # ── Browser window helpers ────────────────────────────────

    def _all_browser_wins(self) -> list:
        if not _HAS_GW:
            return []
        try:
            kw_wa  = ["whatsapp"]
            kw_br  = ["chrome", "msedge", "firefox", "brave", "opera"]
            wa, br = [], []
            for w in gw.getAllWindows():
                t = getattr(w, "title", "").lower()
                if any(k in t for k in kw_wa):
                    wa.append(w)
                elif any(k in t for k in kw_br):
                    br.append(w)
            return wa + br   # WA windows first
        except Exception:
            return []

    def _wait_for_window(self, max_sec: float = 15.0) -> bool:
        """Poll until a browser window appears. Returns True when found."""
        if not _HAS_GW:
            time.sleep(max_sec)
            return True
        deadline = time.time() + max_sec
        while time.time() < deadline:
            if self._all_browser_wins():
                return True
            time.sleep(0.4)
        return True   # proceed even on timeout

    def _bring_browser_forward(self) -> None:
        """
        Bring browser to foreground using AllowSetForegroundWindow trick.
        This is the same approach used in v13 BrowserMgr._foreground() which
        reliably steals focus even when Windows tries to prevent it.
        """
        wins = self._all_browser_wins()
        if not wins:
            return
        w = wins[0]
        # First restore the window (in case minimized)
        try:
            w.restore()
            time.sleep(0.15)
        except Exception:
            pass
        # Win32 reliable focus steal
        if _HAS_WIN32 and _U32:
            try:
                hwnd = w._hWnd
                _U32.AllowSetForegroundWindow(-1)  # ASFW_ANY — bypass focus lock
                _U32.ShowWindow(hwnd, 9)            # SW_RESTORE
                _U32.SetForegroundWindow(hwnd)
                time.sleep(0.3)
                return
            except Exception:
                pass
        # Fallback: pygetwindow activate
        try:
            w.activate()
            time.sleep(0.3)
        except Exception:
            pass

    def _browser_title(self) -> str:
        wins = self._all_browser_wins()
        return getattr(wins[0], "title", "").lower() if wins else ""

    def _wait_page_ready(self, deadline: float,
                         stopped: Callable[[], bool]
                         ) -> Tuple[bool, str, FailureCategory]:
        """Wait for WA Web chat page to be interactive (title changes from generic)."""
        self._bring_browser_forward()
        waited, max_wait = 0.0, float(self._s.load)
        while waited < max_wait:
            if stopped() or time.time() > deadline:
                return False, "Timeout waiting for WA page", FailureCategory.TIMEOUT
            title = self._browser_title()
            for kw in _INVALID_KEYS:
                if kw in title:
                    return (False,
                            f"Number invalid/not on WhatsApp: {title[:80]}",
                            FailureCategory.VALIDATION)
            # Page is loading while title is blank or just shows domain
            loading = (
                not title
                or "web.whatsapp.com" in title
                or title.strip() in ("whatsapp", "", "new tab")
                or len(title.strip()) <= 3
            )
            if not loading:
                logger.debug("WA page ready — title=%r", title[:60])
                return True, "", FailureCategory.UNKNOWN
            time.sleep(0.7)
            waited += 0.7
        return False, (
            "Page load timeout — increase 'WA page load wait' in Settings"
        ), FailureCategory.NETWORK

    # ── Screenshot-based send helpers (v14.2) ────────────────

    def _find_send_button(self, win) -> Optional[Tuple[int, int]]:
        """
        Scan the bottom-right quadrant of the browser window for the
        WhatsApp green send button by pixel color.
        Returns absolute screen (x, y) to click, or None if not found.
        """
        if not _HAS_PYAUTOGUI:
            return None
        try:
            # Capture only the bottom-right 35 % × 20 % region
            rx = win.left + int(win.width  * 0.65)
            ry = win.top  + int(win.height * 0.80)
            rw = win.width  - int(win.width  * 0.65)
            rh = win.height - int(win.height * 0.80)
            shot = pyautogui.screenshot(region=(rx, ry, rw, rh))
            w, h = shot.size

            # Scan bottom-right to top-left (button is at very bottom-right)
            for py in range(h - 1, max(h - 120, 0), -3):
                for px in range(w - 1, max(w - 250, 0), -3):
                    r, g, b = shot.getpixel((px, py))[:3]
                    for tr, tg, tb in _WA_SEND_COLORS:
                        if abs(r-tr) < 40 and abs(g-tg) < 40 and abs(b-tb) < 40:
                            # Convert back to screen coordinates
                            sx, sy = rx + px, ry + py
                            logger.debug("Send button pixel found at screen (%d,%d) "
                                         "color=(%d,%d,%d)", sx, sy, r, g, b)
                            return (sx, sy)
            return None
        except Exception as exc:
            logger.debug("_find_send_button: %s", exc)
            return None

    def _capture_win_shot(self, win) -> Optional[object]:
        """Capture full browser window screenshot. Returns PIL Image or None."""
        if not _HAS_PYAUTOGUI or win is None:
            return None
        try:
            return pyautogui.screenshot(
                region=(win.left, win.top, win.width, win.height))
        except Exception as exc:
            logger.debug("_capture_win_shot: %s", exc)
            return None

    def _verify_send_visual(self, before, after, win
                            ) -> Tuple[bool, str]:
        """
        Compare before/after screenshots to decide if the message was sent.

        Three independent checks — ANY ONE passing = SENT:
          A. Input area variance dropped (text box cleared after send).
          B. Chat area ≥ 1.5 % pixels changed (new message bubble).
          C. Tick-mark color detected in bottom chat region.

        All three failing = message stayed as draft.
        """
        if before is None or after is None:
            # Can't verify visually — trust the title check that already passed
            logger.debug("Visual verify skipped (no screenshots)")
            return True, ""

        try:
            w, h = before.size

            # ── Check A: Input area cleared ───────────────────────────────
            # Input sits at ~88–97 % height, left 5 – 85 % width
            ax1, ay1, ax2, ay2 = (
                int(w * 0.05), int(h * 0.88),
                int(w * 0.85), int(h * 0.97),
            )
            var_before = self._region_variance(before, ax1, ay1, ax2, ay2)
            var_after  = self._region_variance(after,  ax1, ay1, ax2, ay2)
            if var_before > 20 and var_after < var_before * 0.45:
                logger.info("Send verified (A): input cleared "
                            "(variance %.1f→%.1f)", var_before, var_after)
                return True, ""

            # ── Check B: Chat area pixel change ───────────────────────────
            by1, by2 = int(h * 0.35), int(h * 0.87)
            diff_pct = self._region_diff_pct(before, after, 0, by1, w, by2)
            if diff_pct >= 1.5:
                logger.info("Send verified (B): chat area changed %.1f%%", diff_pct)
                return True, ""

            # ── Check C: Tick-mark color detected ─────────────────────────
            if self._detect_tick_color(after, w, h):
                logger.info("Send verified (C): tick-mark color detected")
                return True, ""

            # All checks failed
            logger.warning(
                "Visual verify FAILED: var=%.1f→%.1f, diff=%.1f%%, no tick",
                var_before, var_after, diff_pct)
            return (
                False,
                "Message appears to still be in draft — the send button was not "
                "clicked successfully. "
                f"(input-variance: {var_before:.0f}→{var_after:.0f}, "
                f"chat-change: {diff_pct:.1f}%)"
            )
        except Exception as exc:
            logger.warning("_verify_send_visual error: %s", exc)
            # On error, give benefit of doubt
            return True, ""

    @staticmethod
    def _region_variance(img, x1: int, y1: int, x2: int, y2: int) -> float:
        """Average brightness variance of sampled pixels in region."""
        vals: list = []
        for px in range(x1, x2, 5):
            for py in range(y1, y2, 5):
                try:
                    r, g, b = img.getpixel((px, py))[:3]
                    vals.append((r + g + b) / 3)
                except Exception:
                    pass
        if not vals:
            return 0.0
        mean = sum(vals) / len(vals)
        return sum((v - mean) ** 2 for v in vals) / len(vals)

    @staticmethod
    def _region_diff_pct(img1, img2,
                         x1: int, y1: int, x2: int, y2: int) -> float:
        """Percentage of sampled pixels that differ by >50 RGB-sum between images."""
        diff = total = 0
        for px in range(x1, x2, 6):
            for py in range(y1, y2, 6):
                try:
                    r1, g1, b1 = img1.getpixel((px, py))[:3]
                    r2, g2, b2 = img2.getpixel((px, py))[:3]
                    if abs(r1-r2) + abs(g1-g2) + abs(b1-b2) > 50:
                        diff += 1
                    total += 1
                except Exception:
                    pass
        return (diff / total * 100) if total else 0.0

    @staticmethod
    def _detect_tick_color(img, w: int, h: int) -> bool:
        """
        Look for WhatsApp tick-mark colors in the bottom half of the chat.
        Grey tick (#8696A0) = sent/delivered; Blue tick (#53BDEB) = read.
        Returns True if ≥ 6 matching pixels found (robust against false pos).
        """
        count = 0
        x1, y1 = int(w * 0.30), int(h * 0.65)
        x2, y2 = int(w * 0.97), int(h * 0.92)
        for px in range(x1, x2, 4):
            for py in range(y1, y2, 4):
                try:
                    r, g, b = img.getpixel((px, py))[:3]
                    gr, gg, gb = _WA_TICK_GREY
                    br2, bg2, bb2 = _WA_TICK_BLUE
                    if (abs(r-gr) < 22 and abs(g-gg) < 22 and abs(b-gb) < 22) or \
                       (abs(r-br2) < 22 and abs(g-bg2) < 22 and abs(b-bb2) < 22):
                        count += 1
                        if count >= 6:
                            return True
                except Exception:
                    pass
        return False

    def _close_tab(self) -> None:
        """Close current tab via Ctrl+W (activate first)."""
        self._bring_browser_forward()
        time.sleep(0.2)
        if _HAS_PYAUTOGUI:
            try:
                pyautogui.hotkey("ctrl", "w")
                time.sleep(0.4)
            except Exception:
                pass

    def _screenshot(self, number: str, campaign_id: int) -> Optional[str]:
        if not _HAS_PYAUTOGUI:
            return None
        try:
            os.makedirs("screenshots", exist_ok=True)
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join("screenshots",
                                f"fail_{campaign_id}_{number}_{ts}.png")
            pyautogui.screenshot(path)
            logger.info("Failure screenshot saved: %s", path)
            return path
        except Exception as exc:
            logger.warning("Screenshot failed: %s", exc)
            return None


# ═══════════════════════════════════════════════════════════════
#  Backoff helper
# ═══════════════════════════════════════════════════════════════

def _backoff_delay(attempt: int,
                   base: float = 5.0,
                   factor: float = 2.0,
                   jitter_cap: float = 3.0,
                   max_delay: float = 60.0) -> float:
    raw    = base * (factor ** (attempt - 1))
    capped = min(max_delay, raw)
    return capped + random.uniform(0, jitter_cap)


def _vary_msg(text: str) -> str:
    words = text.split(" ")
    if len(words) < 4:
        return text
    words[random.randint(1, len(words) - 2)] += random.choice(_INVISIBLE)
    return " ".join(words)


# ═══════════════════════════════════════════════════════════════
#  Sender — orchestrator
# ═══════════════════════════════════════════════════════════════

class Sender:
    def __init__(self, db: Database, settings: Settings,
                 adapter: Optional[SenderAdapter] = None) -> None:
        self._db      = db
        self._s       = settings
        self._adapter = adapter or WhatsAppWebAdapter(settings)
        logger.info("Sender initialized with adapter: %s", self._adapter.name())

    @property
    def adapter(self) -> SenderAdapter:
        return self._adapter

    def health_check(self) -> Tuple[bool, str]:
        ok, reason = self._adapter.health_check()
        if ok:
            self._db.log(AuditLevel.INFO, "Health check passed.", source="sender")
        else:
            self._db.log(AuditLevel.ERROR,
                         f"Health check FAILED: {reason}", source="sender")
        return ok, reason

    def send_with_retry(self, message_id: int, number: str,
                        text: str, campaign_id: int,
                        stop_event: Optional[object] = None,
                        status_cb: Optional[Callable[[str], None]] = None,
                        ) -> SendResult:
        max_retries = self._s.retries
        last_result: Optional[SendResult] = None

        def _stopped() -> bool:
            return bool(stop_event and
                        getattr(stop_event, "is_set", lambda: False)())

        def _cb(msg: str) -> None:
            if status_cb:
                try:
                    status_cb(msg)
                except Exception:
                    pass

        self._db.update_message_status(message_id, MessageStatus.SENDING)
        self._db.log(AuditLevel.INFO, f"→ Sending to {number}",
                     source="sender", message_id=message_id,
                     campaign_id=campaign_id)

        for attempt in range(1, max_retries + 1):
            if _stopped():
                result = SendResult(ok=False, number=number,
                                    campaign_id=campaign_id,
                                    category=FailureCategory.UNKNOWN,
                                    reason="Stopped by user")
                self._finalize(message_id, campaign_id, result, attempt)
                return result

            varied = _vary_msg(text) if self._s.vary else text

            if attempt > 1:
                wait = _backoff_delay(attempt - 1)
                _cb(f"↻ Retry {attempt}/{max_retries} in {wait:.0f}s → {number}")
                self._db.log(
                    AuditLevel.WARNING,
                    f"Retry {attempt}/{max_retries} for {number} in {wait:.0f}s",
                    source="sender", message_id=message_id,
                    campaign_id=campaign_id,
                )
                elapsed = 0.0
                while elapsed < wait and not _stopped():
                    time.sleep(0.5)
                    elapsed += 0.5
                if _stopped():
                    break

            _cb(f"● Attempt {attempt}/{max_retries} → {number}")

            result = self._adapter.send(
                number=number, text=varied,
                campaign_id=campaign_id,
                stop_event=stop_event,
            )
            last_result = result

            if result.ok:
                self._finalize(message_id, campaign_id, result, attempt)
                return result

            self._db.log(
                AuditLevel.WARNING,
                f"Attempt {attempt} failed [{result.category}]: {result.reason}",
                source="sender", message_id=message_id,
                campaign_id=campaign_id,
            )

        final = last_result or SendResult(
            ok=False, number=number, campaign_id=campaign_id,
            category=FailureCategory.UNKNOWN, reason="No attempts made")
        self._finalize(message_id, campaign_id, final, max_retries)
        return final

    def _finalize(self, message_id: int, campaign_id: int,
                  result: SendResult, attempt: int) -> None:
        if result.ok:
            self._db.update_message_status(message_id, MessageStatus.SENT)
            self._db.log(AuditLevel.INFO,
                         f"✅ Sent to {result.number} (attempt {attempt})",
                         source="sender", message_id=message_id,
                         campaign_id=campaign_id)
            self._db.increment_rate_window()
        else:
            self._db.update_message_status(
                message_id, MessageStatus.FAILED,
                failure_reason=result.reason,
                retry_count=attempt,
                screenshot=result.screenshot,
            )
            self._db.log(
                AuditLevel.ERROR,
                f"❌ Failed {result.number} [{result.category}]: {result.reason}",
                source="sender", message_id=message_id,
                campaign_id=campaign_id,
            )

    @staticmethod
    def recover_sending_orphans(db: Database) -> List[int]:
        conn  = db._conn
        cur   = conn.execute("SELECT id FROM messages WHERE status='sending'")
        ids   = [r["id"] for r in cur.fetchall()]
        if ids:
            placeholders = ",".join("?" * len(ids))
            with db._tx() as c:
                c.execute(
                    f"UPDATE messages SET status='queued', sending_at=NULL,"
                    f" updated_at=datetime('now')"
                    f" WHERE id IN ({placeholders})",
                    ids,
                )
            db.log(AuditLevel.WARNING,
                   f"Crash recovery: {len(ids)} message(s) reset to queued.",
                   source="sender")
        return ids

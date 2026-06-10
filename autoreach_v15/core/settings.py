# -*- coding: utf-8 -*-
"""
core/settings.py — AutoReach v15
Settings dataclass + JSON persistence.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Resolved at runtime by main.py via os.chdir — always relative to project root
SETTINGS_FILE = "autoreach_settings.json"


@dataclass
class Settings:
    """All application settings with typed fields and safe defaults."""

    # ── Timing ────────────────────────────────────────────────
    delay_min:      float = 10.0   # min seconds between messages
    delay_max:      float = 20.0   # max seconds between messages
    timeout:        int   = 90     # seconds to wait for page load per number
    post_send_delay: float = 5.0   # seconds after send before closing tab
    page_load_wait: float = 10.0   # seconds to wait after opening URL

    # ── Limits ────────────────────────────────────────────────
    daily_limit:    int   = 40     # 0 = unlimited

    # ── Behaviour ─────────────────────────────────────────────
    dark_mode:       bool = True   # WhatsApp Web dark mode (affects pixel detection)
    background_mode: bool = True   # hide app to system tray while running
    send_mode:       str  = "one"  # "one" = single paste+enter | "split" = paragraph
    dry_run:         bool = False  # simulate without opening browser

    # ── Internal (not shown in UI) ────────────────────────────
    vary_message:    bool = True   # insert invisible char for message variation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        valid = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in valid})

    def validate(self) -> list[str]:
        warnings: list[str] = []
        if self.delay_min < 5:
            warnings.append("Min delay < 5s — very high ban risk.")
        if self.delay_max < self.delay_min:
            warnings.append("Max delay < min delay — clamped.")
            self.delay_max = self.delay_min + 10.0
        if self.daily_limit > 80:
            warnings.append("Daily limit > 80 — high ban risk.")
        if self.timeout < 20:
            warnings.append("Timeout < 20s — may cause premature failures.")
        return warnings


def load_settings() -> Settings:
    """Load settings from JSON. Returns defaults if file missing or corrupt."""
    if not os.path.exists(SETTINGS_FILE):
        logger.info("No settings file — using defaults.")
        s = Settings()
        save_settings(s)   # create file on first run
        return s
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        s = Settings.from_dict(data)
        for w in s.validate():
            logger.warning("Settings: %s", w)
        return s
    except Exception as exc:
        logger.error("Failed to load settings (%s) — using defaults.", exc)
        return Settings()


def save_settings(s: Settings) -> bool:
    """Persist settings to JSON. Returns True on success."""
    try:
        for w in s.validate():
            logger.warning("Settings: %s", w)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s.to_dict(), f, indent=2)
        return True
    except OSError as exc:
        logger.error("Cannot save settings: %s", exc)
        return False

# -*- coding: utf-8 -*-
"""
core/settings.py — AutoReach v14
==================================
Manages all application configuration:
  - JSON-backed user settings (compatible with v13 format)
  - Optional PIN lock stored as salted SHA-256 hash in a separate file
  - Runtime defaults with typed accessors
  - Auto-save on change with validation

Design:
  - Settings class is the single source of truth for all configuration.
  - v13 autoreach_settings.json keys are preserved for backward compatibility.
  - New v14 keys use defaults if the file predates them.
  - PIN hash is stored in auth.dat (never in the main settings JSON).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  File paths (relative to working directory)
# ─────────────────────────────────────────────
SETTINGS_FILE = "autoreach_settings.json"
AUTH_FILE     = "auth.dat"          # PIN salt + hash (never the plain PIN)


# ─────────────────────────────────────────────
#  Settings dataclass
# ─────────────────────────────────────────────

@dataclass
class Settings:
    """
    All application settings with typed fields and defaults.

    Fields that existed in v13 keep the same names so the existing
    JSON file is loaded without conversion.
    """
    # ── Timing & Delays ───────────────────────
    dmin:        int   = 45     # Min delay between messages (seconds)
    dmax:        int   = 90     # Max delay between messages (seconds)
    conn_delay:  int   = 7      # Wait after opening browser (seconds)
    load:        int   = 25     # WhatsApp page load wait (seconds)
    postsend:    int   = 5      # Post-send wait before closing tab (seconds)
    timeout:     int   = 90     # Hard timeout per number (seconds)

    # ── Limits & Reliability ──────────────────
    dlimit:      int   = 30     # Daily send limit
    retries:     int   = 2      # Max retry attempts per failure

    # ── Behaviour ─────────────────────────────
    skip_sent:   bool  = True   # Skip already-sent numbers
    skip_bl:     bool  = True   # Skip blacklisted numbers
    vary:        bool  = True   # Add invisible chars to vary message (anti-spam)
    sound:       bool  = True   # Play sound on session complete
    hide_browser: bool = False  # Minimize browser while sending
    stop_on_fail: bool = False  # Stop entire session on first failure
    diagnostic:  bool  = False  # Log every sub-step
    single_msg:  bool  = True   # Send as single bubble vs multi-paragraph

    # ── v14 New Settings ──────────────────────
    dry_run:          bool  = False  # Simulate sends without opening WA
    pin_lock_enabled: bool  = False  # Require PIN on launch
    backup_on_start:  bool  = True   # Auto-backup DB before every campaign
    backup_on_end:    bool  = True   # Auto-backup DB after every campaign
    human_delays:     bool  = True   # Use Gaussian delay distribution
    health_check:     bool  = True   # Verify WA Web reachable before campaign
    screenshot_on_fail: bool = True  # Capture screenshot on send failure
    max_backup_count: int   = 10     # Maximum number of backup files to keep
    campaign_recovery: bool = True   # Auto-resume crashed campaigns on start

    # ── Rate Limiting ─────────────────────────
    rate_limit_per_hour: int = 0    # 0 = disabled; >0 = cap per hour
    rate_limit_per_day:  int = 0    # 0 = uses dlimit; >0 = explicit cap

    def validate(self) -> list[str]:
        """
        Validate settings and return a list of warning strings.
        Empty list means all settings are within safe ranges.
        """
        warnings: list[str] = []
        if self.dmin < 30:
            warnings.append("Min delay < 30s — high ban risk.")
        if self.dmax < self.dmin:
            warnings.append("Max delay is less than min delay — resetting max.")
            self.dmax = self.dmin + 30
        if self.dlimit > 100:
            warnings.append("Daily limit > 100 — very high ban risk.")
        if self.retries > 5:
            warnings.append("Retry attempts > 5 — may cause long delays.")
        if self.timeout < 30:
            warnings.append("Timeout < 30s — may cause premature failures.")
        return warnings

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """
        Create a Settings instance from a dictionary.
        Unknown keys are ignored; missing keys use defaults.
        This ensures forward/backward compatibility.
        """
        valid_keys = cls.__dataclass_fields__.keys()
        filtered   = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


# ─────────────────────────────────────────────
#  Settings Manager
# ─────────────────────────────────────────────

class SettingsManager:
    """
    Loads, saves, and manages application settings.

    Usage:
        mgr = SettingsManager()
        s   = mgr.settings          # typed Settings object
        s.dmin = 60
        mgr.save()

    PIN management:
        mgr.set_pin("1234")         # Store hashed PIN
        mgr.verify_pin("1234")      # True/False
        mgr.remove_pin()            # Disable PIN lock
    """

    def __init__(self, settings_path: str = SETTINGS_FILE,
                 auth_path: str = AUTH_FILE) -> None:
        self._path      = settings_path
        self._auth_path = auth_path
        self.settings   = self._load()

    # ── Load / Save ───────────────────────────

    def _load(self) -> Settings:
        """Load settings from JSON, falling back to defaults on any error."""
        if not os.path.exists(self._path):
            logger.info("No settings file found — using defaults.")
            return Settings()
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            s = Settings.from_dict(data)
            warnings = s.validate()
            for w in warnings:
                logger.warning("Settings validation: %s", w)
            logger.info("Settings loaded from '%s'.", self._path)
            return s
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("Failed to load settings (%s) — using defaults.", exc)
            return Settings()

    def save(self) -> bool:
        """
        Persist current settings to JSON.

        Returns True on success, False on failure (never raises).
        """
        try:
            warnings = self.settings.validate()
            for w in warnings:
                logger.warning("Settings validation on save: %s", w)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self.settings.to_dict(), f, indent=2)
            logger.debug("Settings saved to '%s'.", self._path)
            return True
        except OSError as exc:
            logger.error("Could not save settings: %s", exc)
            return False

    def reset_to_defaults(self) -> None:
        """Reset all settings to factory defaults and save."""
        self.settings = Settings()
        self.save()
        logger.info("Settings reset to defaults.")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key string (for dynamic access)."""
        return getattr(self.settings, key, default)

    def set(self, key: str, value: Any) -> bool:
        """
        Set a setting value by key string and save.

        Returns True if the key exists and was set, False otherwise.
        """
        if not hasattr(self.settings, key):
            logger.warning("Unknown setting key: '%s'", key)
            return False
        setattr(self.settings, key, value)
        return self.save()

    # ── PIN Management ────────────────────────

    @staticmethod
    def _hash_pin(pin: str, salt: str) -> str:
        """Return a salted SHA-256 hex digest of the PIN."""
        return hashlib.sha256(f"{salt}{pin}".encode("utf-8")).hexdigest()

    def set_pin(self, pin: str) -> bool:
        """
        Store a new PIN as a salted hash in auth.dat.
        The plain-text PIN is never written to disk.

        Returns True on success.
        """
        if not pin or not pin.isdigit() or len(pin) < 4:
            raise ValueError("PIN must be at least 4 digits.")
        salt    = secrets.token_hex(16)
        hashed  = self._hash_pin(pin, salt)
        payload = {"salt": salt, "hash": hashed}
        try:
            with open(self._auth_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            self.settings.pin_lock_enabled = True
            self.save()
            logger.info("PIN set successfully.")
            return True
        except OSError as exc:
            logger.error("Could not write auth file: %s", exc)
            return False

    def verify_pin(self, pin: str) -> bool:
        """
        Verify a PIN against the stored hash.

        Returns True if the PIN matches, False otherwise.
        Never raises — returns False on any error.
        """
        if not os.path.exists(self._auth_path):
            return True   # No PIN set — always passes
        try:
            with open(self._auth_path, encoding="utf-8") as f:
                payload = json.load(f)
            salt   = payload.get("salt", "")
            stored = payload.get("hash", "")
            return secrets.compare_digest(self._hash_pin(pin, salt), stored)
        except Exception as exc:
            logger.error("PIN verification error: %s", exc)
            return False

    def remove_pin(self) -> bool:
        """
        Remove the PIN lock (delete auth.dat and update settings).

        Returns True on success.
        """
        try:
            if os.path.exists(self._auth_path):
                os.remove(self._auth_path)
            self.settings.pin_lock_enabled = False
            self.save()
            logger.info("PIN lock removed.")
            return True
        except OSError as exc:
            logger.error("Could not remove auth file: %s", exc)
            return False

    def has_pin(self) -> bool:
        """Return True if a PIN file exists and PIN lock is enabled."""
        return (self.settings.pin_lock_enabled
                and os.path.exists(self._auth_path))

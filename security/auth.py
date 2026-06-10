# -*- coding: utf-8 -*-
"""
security/auth.py — AutoReach v14
Optional PIN lock + token-bucket rate limiter.
"""
from __future__ import annotations
import time
import threading
import logging
from core.settings import SettingsManager

logger = logging.getLogger(__name__)


class PINLock:
    """
    Optional startup PIN guard. Wraps SettingsManager PIN methods.
    Usage: PINLock(mgr).prompt_and_verify(root) → bool
    """
    def __init__(self, mgr: SettingsManager) -> None:
        self._mgr = mgr

    def is_enabled(self) -> bool:
        return self._mgr.has_pin()

    def verify(self, pin: str) -> bool:
        return self._mgr.verify_pin(pin)

    def set_pin(self, pin: str) -> bool:
        return self._mgr.set_pin(pin)

    def remove(self) -> bool:
        return self._mgr.remove_pin()


class TokenBucketRateLimiter:
    """
    Thread-safe token-bucket rate limiter.

    Args:
        rate:     Tokens added per second.
        capacity: Maximum bucket size (burst limit).

    Usage:
        limiter = TokenBucketRateLimiter(rate=1/45, capacity=1)
        if limiter.consume():
            send_message()
        else:
            wait...
    """
    def __init__(self, rate: float, capacity: float) -> None:
        self._rate     = rate
        self._capacity = capacity
        self._tokens   = capacity
        self._last     = time.monotonic()
        self._lock     = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        with self._lock:
            now    = time.monotonic()
            delta  = now - self._last
            self._last   = now
            self._tokens = min(self._capacity,
                               self._tokens + delta * self._rate)
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_and_consume(self, tokens: float = 1.0, timeout: float = 300.0) -> bool:
        """Block until a token is available or timeout is reached."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.consume(tokens):
                return True
            time.sleep(0.5)
        return False

    @property
    def available(self) -> float:
        with self._lock:
            now = time.monotonic()
            return min(self._capacity,
                       self._tokens + (now - self._last) * self._rate)

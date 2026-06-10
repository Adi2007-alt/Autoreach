# -*- coding: utf-8 -*-
"""
core/phone.py — AutoReach v14
================================
Phone number normalization, validation, and batch processing.

Rules (applied in order):
  1. Strip all non-digit characters.
  2. 12 digits, valid country prefix  → use as-is (E.164 without '+').
  3. 11 digits starting with '0'      → drop leading 0, prepend default CC.
  4. 10 digits                        → prepend default country code.
  5. Anything else                    → INVALID.
  6. Post-normalization deduplication (same E.164 = duplicate).

Design:
  - PhoneNormalizer is configurable (default_country_code, min/max length).
  - ValidationResult carries enough detail for the UI to show per-number status.
  - batch_validate() is the primary public API; single-number helpers wrap it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# ─── Known country code lengths (digits after CC) ────────────────────────────
# A non-exhaustive set used to loosely validate 12-digit inputs.
_VALID_CC_PREFIXES: Set[str] = {
    "1",                               # US / Canada
    "7",                               # Russia / Kazakhstan
    "20", "27",                        # Egypt, South Africa
    "30", "31", "32", "33", "34",      # Greece, NL, BE, FR, ES
    "36", "39",                        # Hungary, Italy
    "40", "41", "43", "44", "45",      # Romania, CH, AT, UK, DK
    "46", "47", "48", "49",            # SE, NO, PL, DE
    "51", "52", "53", "54", "55",      # PE, MX, CU, AR, BR
    "56", "57", "58",                  # CL, CO, VE
    "60", "61", "62", "63", "64",      # MY, AU, ID, PH, NZ
    "65", "66",                        # SG, TH
    "81", "82", "84", "86",            # JP, KR, VN, CN
    "90", "91", "92", "93", "94",      # TR, IN, PK, AF, LK
    "95", "98",                        # MM, IR
    "212", "213", "216", "218",        # MA, DZ, TN, LY
    "220", "221", "222", "223",        # GM, SN, MR, ML
    "234", "233", "254", "255",        # NG, GH, KE, TZ
    "256", "260", "263", "264",        # UG, ZM, ZW, NA
    "380", "381", "385", "386",        # UA, RS, HR, SI
    "420", "421",                      # CZ, SK
    "880", "886",                      # BD, TW
    "960", "961", "962", "963",        # MV, LB, JO, SY
    "966", "971", "972",               # SA, UAE, IL
    "977", "992", "994", "995", "998", # NP, TJ, AZ, GE, UZ
}


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    Outcome of validating a single raw phone number input.

    Attributes:
        raw:        The original input string exactly as provided.
        normalized: E.164-style string (digits only) if valid, else None.
        is_valid:   True if the number passed all validation rules.
        is_duplicate: True if another entry in the same batch normalized
                      to the same E.164 value.
        reason:     Human-readable explanation when is_valid is False.
    """
    raw:          str
    normalized:   Optional[str] = None
    is_valid:     bool          = True
    is_duplicate: bool          = False
    reason:       Optional[str] = None

    def __str__(self) -> str:
        if self.is_duplicate:
            return f"{self.raw!r} → duplicate of {self.normalized}"
        if self.is_valid:
            return f"{self.raw!r} → {self.normalized}"
        return f"{self.raw!r} → INVALID ({self.reason})"


@dataclass
class BatchValidationReport:
    """Summary of a batch_validate() call."""
    results:        List[ValidationResult]
    valid_count:    int = 0
    invalid_count:  int = 0
    duplicate_count: int = 0

    @property
    def valid_numbers(self) -> List[str]:
        """Return only the normalized valid, non-duplicate numbers."""
        return [r.normalized for r in self.results
                if r.is_valid and not r.is_duplicate and r.normalized]

    @property
    def invalid_numbers(self) -> List[ValidationResult]:
        return [r for r in self.results if not r.is_valid]

    @property
    def duplicate_numbers(self) -> List[ValidationResult]:
        return [r for r in self.results if r.is_duplicate]


# ─── Normalizer ───────────────────────────────────────────────────────────────

class PhoneNormalizer:
    """
    Normalizes phone number strings to E.164-style digit-only format.

    Args:
        default_country_code: Digits to prepend for 10-digit numbers.
                              Default is '91' (India).
        strict_cc_check:      If True, reject 12-digit numbers whose
                              first 1-3 digits don't match a known CC.
    """

    def __init__(self, default_country_code: str = "91",
                 strict_cc_check: bool = False) -> None:
        self._default_cc   = default_country_code.lstrip("+")
        self._strict       = strict_cc_check

    # ── Public API ────────────────────────────────────────────

    def normalize(self, raw: str) -> ValidationResult:
        """
        Normalize a single phone number.

        Returns a ValidationResult — never raises.
        """
        if not raw or not raw.strip():
            return ValidationResult(raw=raw, is_valid=False,
                                    reason="Empty input")

        digits = re.sub(r"\D", "", raw)

        if not digits:
            return ValidationResult(raw=raw, is_valid=False,
                                    reason="No digits found")

        # 12-digit: treat as fully-qualified (with or without country code)
        if len(digits) == 12:
            if self._strict and not self._known_cc(digits):
                return ValidationResult(raw=raw, is_valid=False,
                                        reason="Unknown country code prefix")
            return ValidationResult(raw=raw, normalized=digits, is_valid=True)

        # 13-digit starting with '+' country code (already captured as digits)
        if len(digits) == 13 and digits.startswith("0"):
            # e.g. '+0091...' edge case — strip leading 0
            digits = digits[1:]
            if len(digits) == 12:
                return ValidationResult(raw=raw, normalized=digits, is_valid=True)

        # 11-digit starting with 0: strip 0, prepend default CC
        if len(digits) == 11 and digits.startswith("0"):
            normalized = self._default_cc + digits[1:]
            if len(normalized) == 12:
                return ValidationResult(raw=raw, normalized=normalized,
                                        is_valid=True)

        # 10-digit: prepend default country code
        if len(digits) == 10:
            normalized = self._default_cc + digits
            return ValidationResult(raw=raw, normalized=normalized,
                                    is_valid=True)

        # All other lengths
        return ValidationResult(
            raw=raw, is_valid=False,
            reason=f"Unexpected digit count: {len(digits)} "
                   f"(expected 10 or 12)",
        )

    def batch_validate(self, raw_numbers: List[str]) -> BatchValidationReport:
        """
        Validate a list of raw phone number strings.

        Deduplication is applied post-normalization: the first occurrence
        of each E.164 value is kept, subsequent ones are marked duplicate.

        Args:
            raw_numbers: List of raw strings from a contact file.

        Returns:
            BatchValidationReport with full per-number detail.
        """
        seen:    Set[str]              = set()
        results: List[ValidationResult] = []
        valid   = invalid = dupes = 0

        for raw in raw_numbers:
            r = self.normalize(raw)
            if not r.is_valid:
                invalid += 1
            elif r.normalized in seen:
                r.is_duplicate = True
                r.reason       = f"Duplicate of earlier entry {r.normalized!r}"
                dupes          += 1
            else:
                seen.add(r.normalized)
                valid += 1
            results.append(r)

        logger.info(
            "batch_validate: %d total → %d valid, %d invalid, %d duplicates",
            len(raw_numbers), valid, invalid, dupes,
        )
        return BatchValidationReport(
            results=results,
            valid_count=valid,
            invalid_count=invalid,
            duplicate_count=dupes,
        )

    # ── Helpers ───────────────────────────────────────────────

    def _known_cc(self, digits: str) -> bool:
        """Check if digits starts with a known country code (1, 2 or 3 digits)."""
        for length in (1, 2, 3):
            if digits[:length] in _VALID_CC_PREFIXES:
                return True
        return False


# ─── Module-level convenience functions ──────────────────────────────────────

_DEFAULT_NORMALIZER = PhoneNormalizer(default_country_code="91")


def normalize(raw: str,
              default_cc: str = "91") -> Optional[str]:
    """
    Convenience: normalize a single number, return E.164 string or None.

    Args:
        raw:        Raw phone number string.
        default_cc: Country code digits to prepend for 10-digit numbers.

    Returns:
        Normalized digit string (e.g. '919876543210') or None if invalid.
    """
    normalizer = (PhoneNormalizer(default_cc)
                  if default_cc != "91" else _DEFAULT_NORMALIZER)
    result = normalizer.normalize(raw)
    return result.normalized if result.is_valid else None


def batch_validate(raw_numbers: List[str],
                   default_cc: str = "91") -> BatchValidationReport:
    """
    Convenience: validate a list of numbers, return a full report.

    Args:
        raw_numbers: List of raw strings.
        default_cc:  Country code digits for 10-digit numbers.

    Returns:
        BatchValidationReport with per-number detail and summary counts.
    """
    return PhoneNormalizer(default_cc).batch_validate(raw_numbers)

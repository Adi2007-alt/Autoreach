# -*- coding: utf-8 -*-
"""
core/models.py — AutoReach v14
================================
Pure dataclasses and enums for all domain entities.
No database calls. No business logic. Only data shapes.

State machine (honest — no false delivery receipts):
    queued → sending → sent
                    → failed  (retry_count < max_retries → back to sending)
                    → skipped
    delivered / read: NOT set automatically — require WhatsApp Business API.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────
#  Enumerations
# ─────────────────────────────────────────────

class MessageStatus(str, Enum):
    """
    Lifecycle states for a single outbound message.

    IMPORTANT: DELIVERED and READ are intentionally omitted from the
    automation flow. WhatsApp Web browser automation cannot reliably
    verify delivery or read receipts. Setting those states without a
    verifiable source would generate false data.

    If a WhatsApp Business API integration is added in the future,
    those states can be updated via an external webhook — this enum
    is designed to accommodate them safely.
    """
    QUEUED   = "queued"    # Imported, waiting in queue
    SENDING  = "sending"   # Browser opened, WA page loading / Enter pressed
    SENT     = "sent"      # Enter pressed, no error title detected
    FAILED   = "failed"    # All retry attempts exhausted
    SKIPPED  = "skipped"   # Duplicate, blacklisted, or invalid — never attempted
    # Future states (not set by automation):
    DELIVERED = "delivered"  # External confirmation only
    READ       = "read"      # External confirmation only


class CampaignStatus(str, Enum):
    """Lifecycle states for a campaign (batch of messages)."""
    DRAFT      = "draft"       # Created but not started
    SCHEDULED  = "scheduled"   # Waiting for scheduled_at time
    RUNNING    = "running"     # Actively sending
    PAUSED     = "paused"      # Mid-run pause by user or daily limit
    COMPLETED  = "completed"   # All messages processed
    CANCELLED  = "cancelled"   # Aborted by user
    CRASHED    = "crashed"     # Interrupted by unexpected shutdown (recoverable)


class AuditLevel(str, Enum):
    """Severity levels for audit log entries."""
    DEBUG   = "DEBUG"
    INFO    = "INFO"
    WARNING = "WARNING"
    ERROR   = "ERROR"
    SYSTEM  = "SYSTEM"


# ─────────────────────────────────────────────
#  Domain Dataclasses
# ─────────────────────────────────────────────

@dataclass
class ContactGroup:
    """A named grouping of contacts (e.g. 'Leads Jan 2026')."""
    id:         Optional[int]
    name:       str
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("ContactGroup name cannot be empty.")


@dataclass
class Contact:
    """
    A single phone number with metadata.

    is_valid reflects whether the number passed format validation.
    It does NOT indicate WhatsApp registration — that cannot be
    confirmed without attempting to open WhatsApp Web for the number.
    """
    id:            Optional[int]
    number:        str                   # E.164 normalized (e.g. "919876543210")
    display_name:  Optional[str]  = None
    group_id:      Optional[int]  = None
    is_valid:      bool           = True  # Format-valid (not WA-verified)
    is_blacklisted: bool          = False
    verified_at:   Optional[datetime.datetime] = None
    notes:         Optional[str]  = None
    created_at:    datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class Campaign:
    """
    A named batch send session.

    Campaigns are the top-level grouping unit. All messages belong
    to a campaign. Recovery uses campaign status to detect crashes.
    """
    id:              Optional[int]
    name:            str
    message:         str
    status:          CampaignStatus = CampaignStatus.DRAFT
    scheduled_at:    Optional[datetime.datetime] = None
    started_at:      Optional[datetime.datetime] = None
    completed_at:    Optional[datetime.datetime] = None
    total_contacts:  int = 0
    sent_count:      int = 0
    failed_count:    int = 0
    skipped_count:   int = 0
    daily_limit:     int = 30
    dry_run:         bool = False         # Simulate without opening WA
    created_at:      datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at:      datetime.datetime = field(default_factory=datetime.datetime.now)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.message = self.message.strip()
        if not self.name:
            raise ValueError("Campaign name cannot be empty.")
        if not self.message:
            raise ValueError("Campaign message cannot be empty.")

    @property
    def pending_count(self) -> int:
        """Messages not yet processed."""
        return max(0, self.total_contacts - self.sent_count
                   - self.failed_count - self.skipped_count)

    @property
    def success_rate(self) -> float:
        """Percentage of attempts that succeeded (0.0–100.0)."""
        attempted = self.sent_count + self.failed_count
        return (self.sent_count / attempted * 100.0) if attempted else 0.0

    @property
    def is_recoverable(self) -> bool:
        """True if this campaign can be resumed after a crash."""
        return self.status in (CampaignStatus.CRASHED, CampaignStatus.PAUSED,
                               CampaignStatus.RUNNING)


@dataclass
class Message:
    """
    A single outbound WhatsApp message with full state history.

    Timestamps are set only when the corresponding state is entered —
    they are never backfilled or estimated.
    """
    id:             Optional[int]
    campaign_id:    int
    number:         str              # E.164 (e.g. "919876543210")
    message_text:   str              # Actual text sent (after vary_msg transformation)
    status:         MessageStatus = MessageStatus.QUEUED
    contact_id:     Optional[int] = None
    failure_reason: Optional[str] = None
    retry_count:    int = 0
    max_retries:    int = 2
    # State timestamps — None until that state is entered
    queued_at:      Optional[datetime.datetime] = field(default_factory=datetime.datetime.now)
    sending_at:     Optional[datetime.datetime] = None
    sent_at:        Optional[datetime.datetime] = None
    failed_at:      Optional[datetime.datetime] = None
    skipped_at:     Optional[datetime.datetime] = None
    updated_at:     datetime.datetime = field(default_factory=datetime.datetime.now)
    # Screenshot path captured on failure (optional)
    failure_screenshot: Optional[str] = None

    @property
    def can_retry(self) -> bool:
        """True if this failed message has retries remaining."""
        return (self.status == MessageStatus.FAILED
                and self.retry_count < self.max_retries)

    @property
    def is_terminal(self) -> bool:
        """True if this message has reached a final state."""
        return self.status in (
            MessageStatus.SENT,
            MessageStatus.SKIPPED,
            MessageStatus.DELIVERED,
            MessageStatus.READ,
        ) or (self.status == MessageStatus.FAILED
              and self.retry_count >= self.max_retries)


@dataclass
class AuditLog:
    """
    A single structured log entry stored in the database.

    Provides a searchable audit trail separate from the on-screen log.
    """
    id:          Optional[int]
    level:       AuditLevel
    text:        str
    source:      Optional[str]  = None   # Module name (e.g. "sender")
    message_id:  Optional[int]  = None   # Linked message (if applicable)
    campaign_id: Optional[int]  = None   # Linked campaign (if applicable)
    created_at:  datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class RateWindow:
    """Tracks messages sent per date+hour for rate limiting."""
    id:         Optional[int]
    date:       str   # YYYY-MM-DD
    hour:       int   # 0–23
    sent_count: int = 0


@dataclass
class Insight:
    """
    A single analytics finding returned by the Analyzer.

    Designed to be renderer-agnostic — the UI displays whatever
    title/description/severity the analytics module produces.
    This is also the interface that a future GPT/Gemini integration
    would populate.
    """
    title:       str
    description: str
    severity:    str   # "info" | "warning" | "critical"
    data:        dict  = field(default_factory=dict)  # Optional chart data

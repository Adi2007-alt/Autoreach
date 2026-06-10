# -*- coding: utf-8 -*-
"""
core/scheduler.py — AutoReach v14
====================================
Campaign scheduler: queue management, pause/resume/cancel,
daily/hourly rate limiting, ETA calculation, and graceful shutdown.

State machine:
    PENDING → RUNNING → COMPLETED
                     → PAUSED   (user, daily/hourly limit)
                     → CANCELLED

The scheduler runs the send loop in a background daemon thread.
All UI interaction goes through thread-safe callbacks and a threading.Event.
"""

from __future__ import annotations

import heapq
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from core.database import Database
from core.models import AuditLevel, CampaignStatus, Message, MessageStatus
from core.sender import DryRunAdapter, SendResult, Sender, SenderAdapter, _backoff_delay
from core.settings import Settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  Queue item
# ═══════════════════════════════════════════════════════════════

@dataclass
class QueueItem:
    """
    Priority-queue entry for a campaign.

    Lower priority value = processed first (min-heap).
    Same priority → FIFO via sequence counter.
    """
    priority:    int
    seq:         int
    campaign_id: int

    def __lt__(self, other: "QueueItem") -> bool:
        return (self.priority, self.seq) < (other.priority, other.seq)

    def __le__(self, other: "QueueItem") -> bool:
        return (self.priority, self.seq) <= (other.priority, other.seq)

    def __gt__(self, other: "QueueItem") -> bool:
        return (self.priority, self.seq) > (other.priority, other.seq)

    def __ge__(self, other: "QueueItem") -> bool:
        return (self.priority, self.seq) >= (other.priority, other.seq)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QueueItem):
            return NotImplemented
        return (self.priority, self.seq) == (other.priority, other.seq)


# ═══════════════════════════════════════════════════════════════
#  Scheduler callbacks (all optional)
# ═══════════════════════════════════════════════════════════════

@dataclass
class SchedulerCallbacks:
    """
    UI callback hooks.  All are optional (default = no-op).

    on_status:    Called with a status string for the status bar.
    on_log:       Called with (level: str, text: str) for the log panel.
    on_stats:     Called after every message completes (for stat refresh).
    on_done:      Called when a campaign finishes (any terminal state).
    on_progress:  Called with (current, total, eta_seconds) for the queue monitor.
    """
    on_status:   Optional[Callable[[str], None]]          = None
    on_log:      Optional[Callable[[str, str], None]]     = None
    on_stats:    Optional[Callable[[], None]]             = None
    on_done:     Optional[Callable[[int, str], None]]     = None
    on_progress: Optional[Callable[[int, int, float], None]] = None

    def status(self, msg: str) -> None:
        if self.on_status:
            try: self.on_status(msg)
            except Exception: pass

    def log(self, level: str, msg: str) -> None:
        if self.on_log:
            try: self.on_log(level, msg)
            except Exception: pass

    def stats(self) -> None:
        if self.on_stats:
            try: self.on_stats()
            except Exception: pass

    def done(self, campaign_id: int, status: str) -> None:
        if self.on_done:
            try: self.on_done(campaign_id, status)
            except Exception: pass

    def progress(self, current: int, total: int, eta: float) -> None:
        if self.on_progress:
            try: self.on_progress(current, total, eta)
            except Exception: pass


# ═══════════════════════════════════════════════════════════════
#  ETA Tracker
# ═══════════════════════════════════════════════════════════════

class ETATracker:
    """
    Computes a rolling average send time to estimate remaining duration.

    Uses an exponential moving average (EMA) with alpha=0.3 so recent
    samples are weighted more heavily than old ones.
    """

    def __init__(self, alpha: float = 0.3) -> None:
        self._alpha  = alpha
        self._ema:   Optional[float] = None   # seconds per message
        self._count  = 0

    def record(self, elapsed_seconds: float) -> None:
        """Record time taken for one completed message."""
        if self._ema is None:
            self._ema = elapsed_seconds
        else:
            self._ema = self._alpha * elapsed_seconds + (1 - self._alpha) * self._ema
        self._count += 1

    def eta(self, remaining: int) -> float:
        """Estimated seconds to complete `remaining` messages."""
        if self._ema is None or remaining <= 0:
            return 0.0
        return self._ema * remaining

    def eta_str(self, remaining: int) -> str:
        secs = self.eta(remaining)
        return str(timedelta(seconds=int(max(0, secs))))

    @property
    def avg_seconds(self) -> Optional[float]:
        return self._ema


# ═══════════════════════════════════════════════════════════════
#  CampaignScheduler
# ═══════════════════════════════════════════════════════════════

class CampaignScheduler:
    """
    Manages the lifecycle of one campaign at a time.

    Features:
      - Priority queue for multiple campaigns (lower int = higher priority)
      - Pause / resume / cancel via threading events
      - Daily and hourly rate-limit enforcement
      - Human-like random delays (Gaussian distribution)
      - ETA calculation (rolling EMA)
      - Graceful shutdown (drains current message, saves state)
      - Crash recovery (restores sending-orphan messages on startup)

    Thread safety:
      - The send loop runs in a single background daemon thread.
      - pause_event, stop_event are threading.Event objects.
      - All DB writes are transactional (see core/database.py).
    """

    def __init__(self, db: Database, settings: Settings,
                 callbacks: Optional[SchedulerCallbacks] = None,
                 adapter: Optional[SenderAdapter] = None) -> None:
        self._db        = db
        self._s         = settings
        self._cb        = callbacks or SchedulerCallbacks()
        # Adapter resolution: explicit > dry_run default > WhatsAppWebAdapter
        if adapter is not None:
            resolved_adapter = adapter
        elif settings.dry_run:
            resolved_adapter = DryRunAdapter()
        else:
            from core.sender import WhatsAppWebAdapter
            resolved_adapter = WhatsAppWebAdapter(settings)
        self._sender = Sender(db, settings, resolved_adapter)

        self._heap:     List[QueueItem] = []
        self._seq:      int = 0
        self._lock      = threading.Lock()

        # Outer loop stop (stops the thread entirely — shutdown/cancel active)
        self._loop_stop   = threading.Event()
        # Per-campaign stop (replaced each run — cancel() sets this)
        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()  # set = paused
        self._thread: Optional[threading.Thread] = None

        # Runtime state
        self._active_campaign_id: Optional[int] = None
        self._eta_tracker         = ETATracker()
        self._current_msg: Optional[Message]    = None

    # ── Campaign queue ────────────────────────────────────────

    def enqueue(self, campaign_id: int, priority: int = 10) -> None:
        """
        Add a campaign to the priority queue.

        Lower priority value = runs sooner.
        Same priority → FIFO (insertion order).
        """
        with self._lock:
            self._seq += 1
            heapq.heappush(self._heap,
                           QueueItem(priority, self._seq, campaign_id))
        logger.info("Campaign %d enqueued (priority=%d).", campaign_id, priority)
        self._db.log(AuditLevel.INFO,
                     f"Campaign {campaign_id} enqueued (priority={priority}).",
                     source="scheduler", campaign_id=campaign_id)

    def queue_depth(self) -> int:
        with self._lock:
            return len(self._heap)

    # ── Start / Pause / Resume / Cancel ──────────────────────

    def start(self) -> bool:
        """
        Start processing the queue in a background thread.

        Returns True if started, False if already running.
        """
        if self._thread and self._thread.is_alive():
            logger.warning("Scheduler already running.")
            return False
        self._loop_stop.clear()
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="SchedulerThread",
        )
        self._thread.start()
        logger.info("Scheduler started.")
        return True

    def pause(self) -> None:
        """Signal the send loop to pause after the current message."""
        self._pause_event.set()
        self._cb.status("⏸ Pausing after current message…")
        logger.info("Scheduler pause requested.")

    def resume(self) -> None:
        """Resume a paused scheduler."""
        self._pause_event.clear()
        self._cb.status("▶ Resumed.")
        logger.info("Scheduler resumed.")

    def cancel(self, campaign_id: Optional[int] = None) -> None:
        """
        Cancel the active campaign (or a specific queued one).

        If campaign_id is None, cancels whatever is currently running.
        """
        if campaign_id is None or campaign_id == self._active_campaign_id:
            # Set only the per-campaign stop — the outer loop continues
            # to the next queued campaign (or idles).
            self._stop_event.set()
            cid = self._active_campaign_id
            if cid:
                self._db.update_campaign_status(cid, CampaignStatus.CANCELLED)
                self._db.log(AuditLevel.WARNING,
                             "Campaign cancelled by user.",
                             source="scheduler", campaign_id=cid)
            self._cb.status("⏹ Campaign cancelled.")
        else:
            # Remove from queue only — do NOT touch stop events
            with self._lock:
                self._heap = [item for item in self._heap
                              if item.campaign_id != campaign_id]
                heapq.heapify(self._heap)
            logger.info("Campaign %d removed from queue.", campaign_id)

    def shutdown(self, timeout: float = 10.0) -> None:
        """Graceful shutdown: signal both stop events, wait for thread."""
        self._loop_stop.set()
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        logger.info("Scheduler shut down.")

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive()
                    and not self._pause_event.is_set())

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    @property
    def active_campaign_id(self) -> Optional[int]:
        return self._active_campaign_id

    @property
    def current_message(self) -> Optional[Message]:
        return self._current_msg

    # ── Crash recovery ────────────────────────────────────────

    def recover_on_startup(self) -> List[int]:
        """
        Recover from a previous crash:
          1. Reset 'sending' orphan messages → 'queued'.
          2. Re-enqueue campaigns that were RUNNING or CRASHED.

        Returns list of recovered campaign IDs.
        """
        if not self._s.campaign_recovery:
            return []

        orphan_ids = Sender.recover_sending_orphans(self._db)

        recoverable = self._db.get_recoverable_campaigns()
        recovered   = []
        for camp in recoverable:
            self._db.update_campaign_status(camp.id, CampaignStatus.PAUSED)
            recovered.append(camp.id)
            logger.info("Recovered campaign %d ('%s') — status → paused.",
                        camp.id, camp.name)
            self._db.log(AuditLevel.WARNING,
                         f"Campaign '{camp.name}' recovered after crash "
                         f"({len(orphan_ids)} message(s) reset to queued).",
                         source="scheduler", campaign_id=camp.id)

        if recovered:
            self._cb.log("WARNING",
                         f"🔄 {len(recovered)} campaign(s) recovered. "
                         "Check Campaigns tab to resume.")
        return recovered

    # ── Internal run loop ─────────────────────────────────────

    def _run_loop(self) -> None:
        """Background thread: dequeue campaigns and process them."""
        logger.info("Scheduler run loop started.")
        while not self._loop_stop.is_set():
            with self._lock:
                item = heapq.heappop(self._heap) if self._heap else None
            if item is None:
                time.sleep(0.5)
                continue
            # Fresh per-campaign stop event — isolated from outer loop
            self._stop_event = threading.Event()
            self._process_campaign(item.campaign_id)
            if self._loop_stop.is_set():
                break
        logger.info("Scheduler run loop exited.")

    def _process_campaign(self, campaign_id: int) -> None:
        """Run a single campaign: health check → send loop → finalize."""
        self._active_campaign_id = campaign_id
        # _stop_event is already a fresh Event (created in _run_loop)
        self._eta_tracker = ETATracker()

        campaign = self._db.get_campaign(campaign_id)
        if not campaign:
            logger.error("Campaign %d not found.", campaign_id)
            return

        self._cb.log("INFO", f"▶ Campaign '{campaign.name}' starting…")
        self._db.log(AuditLevel.INFO,
                     f"Campaign '{campaign.name}' processing started.",
                     source="scheduler", campaign_id=campaign_id)

        # ── Health check ─────────────────────────────────────
        if self._s.health_check and not campaign.dry_run:
            ok, reason = self._sender.health_check()
            if not ok:
                self._cb.log("ERROR", f"❌ Health check failed: {reason}")
                self._db.update_campaign_status(
                    campaign_id, CampaignStatus.PAUSED)
                self._cb.done(campaign_id, "paused")
                self._active_campaign_id = None
                return

        # ── Backup before campaign ────────────────────────────
        if self._s.backup_on_start:
            self._db.backup(label=f"pre_c{campaign_id}",
                            max_keep=self._s.max_backup_count)

        # ── Mark campaign running ────────────────────────────
        self._db.update_campaign_status(
            campaign_id, CampaignStatus.RUNNING,
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # ── Send loop ─────────────────────────────────────────
        messages   = self._db.get_queued_messages(campaign_id)
        total      = len(messages)
        processed  = 0

        for msg in messages:
            # Check stop
            if self._stop_event.is_set():
                break

            # Check daily limit
            if not self._check_limits(campaign, campaign_id):
                break

            # Wait while paused
            while self._pause_event.is_set() and not self._stop_event.is_set():
                self._cb.status("⏸ Paused — click Resume to continue")
                time.sleep(0.5)
            if self._stop_event.is_set():
                break

            self._current_msg = msg
            remaining  = total - processed
            eta        = self._eta_tracker.eta(remaining)
            self._cb.progress(processed, total, eta)
            self._cb.status(
                f"● {processed+1}/{total} → {msg.number}  "
                f"ETA {self._eta_tracker.eta_str(remaining - 1)}")

            t_start = time.time()

            # Use DryRunAdapter if campaign flag is set
            if campaign.dry_run:
                from core.sender import DryRunAdapter
                sender = Sender(self._db, self._s, DryRunAdapter())
            else:
                sender = self._sender

            result: SendResult = sender.send_with_retry(
                message_id=msg.id,
                number=msg.number,
                text=campaign.message,
                campaign_id=campaign_id,
                stop_event=self._stop_event,
                status_cb=self._cb.status,
            )

            elapsed = time.time() - t_start
            self._eta_tracker.record(elapsed)
            processed += 1
            self._db.update_campaign_counts(campaign_id)
            self._cb.stats()

            if result.ok:
                self._cb.log("INFO", f"✅ {msg.number}")
            else:
                self._cb.log("ERROR",
                             f"❌ {msg.number} — {result.reason}")

            # Delay between messages (not after last one)
            if processed < total and not self._stop_event.is_set():
                self._inter_message_delay(campaign)

        # ── Finalize ──────────────────────────────────────────
        self._current_msg = None
        if self._stop_event.is_set():
            # Distinguish: pause_event set = user paused; otherwise = cancelled
            if self._pause_event.is_set():
                self._db.update_campaign_status(campaign_id, CampaignStatus.PAUSED)
                final_status = "paused"
            else:
                self._db.update_campaign_status(campaign_id, CampaignStatus.CANCELLED)
                final_status = "cancelled"
        else:
            self._db.update_campaign_status(
                campaign_id, CampaignStatus.COMPLETED,
                completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            final_status = "completed"

        if self._s.backup_on_end:
            self._db.backup(label=f"post_c{campaign_id}",
                            max_keep=self._s.max_backup_count)

        stats = self._db.get_campaign_stats(campaign_id)
        self._cb.log(
            "INFO",
            f"━━ Campaign '{campaign.name}' {final_status} ━━  "
            f"✅{stats.get('sent',0)}  ❌{stats.get('failed',0)}  "
            f"⏭{stats.get('skipped',0)}"
        )
        self._db.log(
            AuditLevel.INFO,
            f"Campaign '{campaign.name}' {final_status}. "
            f"Sent={stats.get('sent',0)}, "
            f"Failed={stats.get('failed',0)}.",
            source="scheduler", campaign_id=campaign_id,
        )
        self._cb.done(campaign_id, final_status)
        self._active_campaign_id = None

    # ── Rate limit enforcement ────────────────────────────────

    def _check_limits(self, campaign, campaign_id: int) -> bool:
        """
        Check daily and hourly limits.

        Daily limit: uses the campaign's own sent_count (from DB messages),
        not the global rate_window, so campaigns are isolated.
        Hourly limit: uses rate_windows (global, opt-in via settings).

        Returns False if a limit is exceeded (caller should break the loop).
        """
        # Daily limit — count from this campaign's own messages
        c = self._db.get_campaign(campaign_id)
        campaign_sent = c.sent_count if c else 0
        if campaign.daily_limit > 0 and campaign_sent >= campaign.daily_limit:
            self._cb.log(
                "WARNING",
                f"⚠ Daily limit {campaign.daily_limit} reached "
                f"({campaign_sent} sent in this campaign). Campaign paused.",
            )
            self._db.update_campaign_status(campaign_id, CampaignStatus.PAUSED)
            self._pause_event.set()
            return False

        # Hourly limit (settings-level)
        hr_limit = self._s.rate_limit_per_hour
        if hr_limit > 0:
            this_hour = self._db.sent_this_hour()
            if this_hour >= hr_limit:
                wait = 60 - datetime.now().minute
                self._cb.log(
                    "WARNING",
                    f"⚠ Hourly limit {hr_limit} reached. "
                    f"Waiting ~{wait}min for next hour.",
                )
                # Wait until next hour, checking stop/pause
                end = time.time() + wait * 60
                while time.time() < end:
                    if self._stop_event.is_set():
                        return False
                    time.sleep(10)
        return True

    # ── Inter-message delay ───────────────────────────────────

    def _inter_message_delay(self, campaign) -> None:
        """
        Sleep between messages using a Gaussian (human-like) distribution.

        Falls back to uniform random if human_delays is disabled.
        """
        mn = self._s.dmin
        mx = max(mn + 5, self._s.dmax)

        if self._s.human_delays:
            mu    = (mn + mx) / 2
            sigma = (mx - mn) / 4
            delay = max(mn, min(mx, random.gauss(mu, sigma)))
        else:
            delay = random.uniform(mn, mx)

        self._cb.status(
            f"⏳ Next message in {delay:.0f}s…  "
            f"(daily: {self._db.sent_today()}/{campaign.daily_limit})")

        elapsed = 0.0
        while elapsed < delay:
            if self._stop_event.is_set() or self._pause_event.is_set():
                break
            time.sleep(0.5)
            elapsed += 0.5

    # ── Queue monitor data ────────────────────────────────────

    def queue_monitor_data(self, campaign_id: int) -> dict:
        """
        Return current queue monitor state for the UI.

        Returns a dict with:
            total:      Total messages in campaign.
            sent:       Sent so far.
            failed:     Failed so far.
            queued:     Still waiting.
            current:    Number currently being processed (or None).
            eta_str:    Human-readable ETA string.
            eta_seconds: Float ETA.
        """
        stats    = self._db.get_campaign_stats(campaign_id)
        remaining = stats.get("queued", 0) + stats.get("sending", 0)
        eta      = self._eta_tracker.eta(remaining)
        return {
            "total":       stats.get("total", 0),
            "sent":        stats.get("sent", 0),
            "failed":      stats.get("failed", 0),
            "queued":      remaining,
            "skipped":     stats.get("skipped", 0),
            "current":     self._current_msg.number if self._current_msg else None,
            "eta_seconds": eta,
            "eta_str":     self._eta_tracker.eta_str(remaining),
            "avg_seconds": self._eta_tracker.avg_seconds,
        }

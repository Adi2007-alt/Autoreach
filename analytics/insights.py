# -*- coding: utf-8 -*-
"""
analytics/insights.py — AutoReach v14
Rule-based analytics with a GPT-ready abstract interface.
To add AI: subclass Analyzer and override get_insights().
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
from core.database import Database
from core.models import Insight


class AnalyzerBase(ABC):
    """Abstract interface — swap implementation without changing callers."""
    @abstractmethod
    def get_insights(self, db: Database) -> List[Insight]:
        """Return list of Insight objects for the dashboard."""


class RuleBasedAnalyzer(AnalyzerBase):
    """
    Statistical / rule-based analytics.
    No external API calls. GPT integration: subclass and override.
    """

    def get_insights(self, db: Database) -> List[Insight]:
        insights: List[Insight] = []
        stats = db.global_stats()
        total    = stats.get("total", 0)
        failed   = stats.get("failed", 0)
        sent     = stats.get("sent", 0)
        rate     = stats.get("success_rate", 0.0)

        if total == 0:
            insights.append(Insight(
                title="No data yet",
                description="Send your first campaign to see analytics.",
                severity="info"))
            return insights

        # Success rate
        if rate >= 90:
            insights.append(Insight(
                title="✅ Excellent delivery rate",
                description=f"{rate:.1f}% success rate across {total} messages.",
                severity="info", data={"rate": rate}))
        elif rate >= 70:
            insights.append(Insight(
                title="⚠ Moderate delivery rate",
                description=f"{rate:.1f}% — consider reviewing failed numbers.",
                severity="warning", data={"rate": rate}))
        else:
            insights.append(Insight(
                title="❌ Low delivery rate",
                description=f"Only {rate:.1f}% delivered. Check session / number validity.",
                severity="critical", data={"rate": rate}))

        # High failure volume
        if failed > 10:
            insights.append(Insight(
                title="High failure count",
                description=f"{failed} messages failed. Export and review failure reasons.",
                severity="warning", data={"failed": failed}))

        # Hourly activity pattern
        activity = db.hourly_activity(days=7)
        if activity:
            by_hour: dict[int, int] = {}
            for row in activity:
                h = row["hour"]
                by_hour[h] = by_hour.get(h, 0) + row["sent_count"]
            best_hour = max(by_hour, key=by_hour.get)
            insights.append(Insight(
                title="🕐 Best sending hour",
                description=f"Most messages sent successfully at {best_hour:02d}:00. "
                            f"Schedule future campaigns around this time.",
                severity="info",
                data={"best_hour": best_hour, "by_hour": by_hour}))

        # Campaigns with zero sent
        campaigns = db.list_campaigns()
        dead = [c for c in campaigns
                if c.total_contacts > 0 and c.sent_count == 0
                and c.status.value not in ("draft","scheduled")]
        if dead:
            insights.append(Insight(
                title="⚠ Campaigns with 0 sent",
                description=f"{len(dead)} campaign(s) processed with zero successful sends.",
                severity="warning",
                data={"campaigns": [c.name for c in dead]}))

        return insights


# Module-level convenience
_analyzer = RuleBasedAnalyzer()

def get_insights(db: Database) -> List[Insight]:
    """Convenience wrapper — returns insights from the default analyzer."""
    return _analyzer.get_insights(db)

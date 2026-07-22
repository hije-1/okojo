"""Profile Aggregator — unified, anomaly-flagged subject timeline (Component 1)."""

from __future__ import annotations

from .anomalies import Anomaly, detect_all
from .profile import ProfileTimeline, TimelineEvent, build_profile

__all__ = ["ProfileTimeline", "TimelineEvent", "Anomaly", "build_profile", "detect_all"]

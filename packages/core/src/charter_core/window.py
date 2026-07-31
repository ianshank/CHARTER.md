"""The rolling density window: a closed trailing interval on UTC instants.

``[at - window_days, at]``, using exact ``timedelta`` arithmetic rather than
calendar-day truncation, which would reintroduce a timezone-of-record
ambiguity and an off-by-one at midnight. Boundary inclusivity is itself a
resolved setting (``window_boundary``), not a hard-coded choice: an event at
exactly ``at - window_days`` counts under the default ``inclusive`` policy and
does not under ``exclusive``, with both configurations exercised by the
conformance suite.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from charter_core.settings import WindowBoundary


def in_window(ts: datetime, *, at: datetime, days: int, boundary: WindowBoundary) -> bool:
    """Whether ``ts`` falls inside the trailing window ending at ``at``."""
    start = at - timedelta(days=days)
    if boundary == "inclusive":
        return start <= ts <= at
    return start < ts <= at

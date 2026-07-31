"""A total order over ledger events.

Two ratifications landing in the same second make "the (budget+1)th proposal"
order-dependent unless the order is pinned. The order key is
``(committed_at, commit_sha, path)``: the instant first, the commit second
(distinct commits at the same instant are vanishingly rare but must still
resolve deterministically), and the path last as a pure tie-breaker that can
never itself collide, since two ledger files cannot share a path.

This is a total order, not merely a sort key that happens to work: no two
distinct events produce equal keys (the path is unique), so every pair is
strictly ordered one way or the other.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from charter_core.models.state import ResolvedEvent

OrderKey = tuple[datetime, str, str]


def order_key(resolved: ResolvedEvent) -> OrderKey:
    """The sort key for one resolved event."""
    return (resolved.provenance.committed_at, resolved.provenance.commit_sha, resolved.path)


def total_order(events: Iterable[ResolvedEvent]) -> tuple[ResolvedEvent, ...]:
    """Sort events into the canonical total order.

    Deterministic regardless of the order ``events`` arrives in -- callers must
    never depend on ledger read order, since directory listing order is not
    itself guaranteed.
    """
    return tuple(sorted(events, key=order_key))

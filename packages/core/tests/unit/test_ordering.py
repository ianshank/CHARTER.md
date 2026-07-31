"""The total order over ledger events.

Correctness here is what makes "the (budget+1)th proposal" well-defined when
two ratifications land in the same second.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter

from charter_core.ids import LedgerPath
from charter_core.models.events import LedgerEvent
from charter_core.models.state import ResolvedEvent
from charter_core.ordering import order_key, total_order
from charter_core.ports import Provenance

AT = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _retired(co_id: str, path: str, *, at: datetime, sha: str) -> ResolvedEvent:
    event = TypeAdapter(LedgerEvent).validate_python(
        {
            "event_type": "carveout.retired",
            "id": co_id,
            "reason": "Superseded by the v3 design.",
            "actor": {"identity": "maintainer", "role": "maintainer"},
        }
    )
    return ResolvedEvent(
        path=LedgerPath(path),
        event=event,
        provenance=Provenance(
            commit_sha=sha, committed_at=at, first_parent=True, provisional=False
        ),
    )


class TestOrderKey:
    def test_instant_dominates(self) -> None:
        earlier = _retired("CO-1", "ledger/CO-1.retired.yaml", at=AT, sha="zzz")
        later = _retired("CO-2", "ledger/CO-2.retired.yaml", at=LATER, sha="aaa")
        assert order_key(earlier) < order_key(later)

    def test_commit_sha_breaks_a_same_instant_tie(self) -> None:
        a = _retired("CO-1", "ledger/CO-1.retired.yaml", at=AT, sha="aaa")
        b = _retired("CO-2", "ledger/CO-2.retired.yaml", at=AT, sha="bbb")
        assert order_key(a) < order_key(b)

    def test_path_breaks_a_same_instant_same_commit_tie(self) -> None:
        """Two events introduced by one commit -- the common case for adoption."""
        a = _retired("CO-1", "ledger/CO-1.retired.yaml", at=AT, sha="same")
        b = _retired("CO-2", "ledger/CO-2.retired.yaml", at=AT, sha="same")
        assert order_key(a) < order_key(b)


class TestTotalOrder:
    def test_sorts_by_instant(self) -> None:
        early = _retired("CO-1", "ledger/CO-1.retired.yaml", at=AT, sha="a")
        late = _retired("CO-2", "ledger/CO-2.retired.yaml", at=LATER, sha="b")
        assert total_order([late, early]) == (early, late)

    def test_result_is_independent_of_input_order(self) -> None:
        """Ledger read order (directory listing) must never affect the result."""
        events = [
            _retired("CO-3", "ledger/CO-3.retired.yaml", at=AT, sha="c"),
            _retired("CO-1", "ledger/CO-1.retired.yaml", at=AT, sha="a"),
            _retired("CO-2", "ledger/CO-2.retired.yaml", at=AT, sha="b"),
        ]
        forward = total_order(events)
        reversed_input = total_order(list(reversed(events)))
        assert forward == reversed_input

    def test_no_two_distinct_events_tie(self) -> None:
        """A total order has no unresolved ties; the path is always distinct."""
        events = [
            _retired(f"CO-{i}", f"ledger/CO-{i}.retired.yaml", at=AT, sha="same")
            for i in range(1, 6)
        ]
        ordered = total_order(events)
        keys = [order_key(e) for e in ordered]
        assert keys == sorted(keys)
        assert len(set(keys)) == len(keys)

    def test_empty_and_singleton(self) -> None:
        assert total_order([]) == ()
        one = _retired("CO-1", "ledger/CO-1.retired.yaml", at=AT, sha="a")
        assert total_order([one]) == (one,)


@pytest.mark.req("REQ-ORDER-001")
def test_order_is_strictly_increasing_on_a_shuffled_set() -> None:
    """Every consecutive pair in the output must satisfy strict '<'.

    All twenty events here have distinct keys, so a correct total order has no
    equal or out-of-order neighbours anywhere in the result -- not just "the
    list happens to be non-decreasing," which duplicate-tolerant sorts would
    also satisfy.
    """
    import random

    events = [
        _retired(f"CO-{i}", f"ledger/CO-{i}.retired.yaml", at=AT, sha=f"sha{i:03d}")
        for i in range(1, 21)
    ]
    shuffled = list(events)
    random.Random(42).shuffle(shuffled)
    ordered = total_order(shuffled)
    keys = [order_key(e) for e in ordered]
    for earlier, later in itertools.pairwise(keys):
        assert earlier < later

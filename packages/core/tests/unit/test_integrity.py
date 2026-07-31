"""Referential integrity over the resolved event stream."""

from __future__ import annotations

import pytest

from charter_core.integrity import check_integrity
from charter_core.ordering import total_order

from ..builders import (
    T,
    charter,
    correction,
    expired,
    ratified,
    retired,
    review_closed,
    review_opened,
)


def check(*events, non_goals=None):
    c = charter(non_goals=non_goals) if non_goals else charter()
    return check_integrity(c, total_order(events))


class TestCleanLedgersProduceNoDiagnostics:
    def test_a_single_valid_ratification(self) -> None:
        assert list(check(ratified())) == []

    def test_ratify_then_retire(self) -> None:
        assert list(check(ratified(), retired())) == []

    def test_a_full_review_lifecycle(self) -> None:
        events = [review_opened(at=T(0)), review_closed(at=T(1))]
        assert list(check(*events)) == []

    def test_a_correction_targeting_a_real_event(self) -> None:
        events = [ratified(at=T(0)), correction(target="CO-1.ratified", at=T(1))]
        assert list(check(*events)) == []


class TestUnknownNonGoalReference:
    @pytest.mark.req("REQ-INTEG-001")
    def test_carveout_against_an_undeclared_non_goal(self) -> None:
        bag = check(ratified(non_goal_id="NG-99"))
        assert [d.code for d in bag] == ["CK-E0501"]
        assert bag.items()[0].location.event_key == "CO-1.ratified"


class TestOrphanLifecycleEvents:
    @pytest.mark.req("REQ-INTEG-002")
    def test_retirement_with_no_ratification(self) -> None:
        bag = check(retired())
        assert [d.code for d in bag] == ["CK-E0502"]

    @pytest.mark.req("REQ-INTEG-002")
    def test_expiry_with_no_ratification(self) -> None:
        bag = check(expired())
        assert [d.code for d in bag] == ["CK-E0502"]

    @pytest.mark.req("REQ-INTEG-002")
    def test_closure_with_no_matching_opening(self) -> None:
        bag = check(review_closed())
        assert [d.code for d in bag] == ["CK-E0502"]


class TestDuplicateLifecycleEvents:
    @pytest.mark.req("REQ-INTEG-003")
    def test_retired_twice(self) -> None:
        """A second retirement can only reuse the first one's exact path.

        The filename grammar derives the path deterministically from
        (id, kind), so there is no second valid filename for it to occupy.
        That makes this simultaneously a duplicate lifecycle event AND a path
        collision (CK-E0504); both diagnostics are correct here.
        """
        bag = check(ratified(at=T(0)), retired(sha="a", at=T(1)), retired(sha="b", at=T(2)))
        assert {d.code for d in bag} == {"CK-E0503", "CK-E0504"}

    @pytest.mark.req("REQ-INTEG-003")
    def test_retired_then_expired_is_also_a_duplicate_terminal_event(self) -> None:
        """Unlike same-kind duplicates, retired and expired are different files.

        So this is the realistic way E0503 alone can occur: a carve-out has
        exactly one lifecycle end, whichever kind fires first.
        """
        bag = check(ratified(at=T(0)), retired(sha="a", at=T(1)), expired(sha="b", at=T(2)))
        assert [d.code for d in bag] == ["CK-E0503"]

    @pytest.mark.req("REQ-INTEG-003")
    def test_review_closed_twice(self) -> None:
        """Same reasoning as test_retired_twice: 'RV-1.closed' has one valid path."""
        bag = check(
            review_opened(at=T(0)),
            review_closed(sha="a", at=T(1)),
            review_closed(sha="b", at=T(2)),
        )
        assert {d.code for d in bag} == {"CK-E0503", "CK-E0504"}

    def test_the_first_terminal_event_is_not_flagged(self) -> None:
        """Only the duplicate is a violation; the original retirement is fine."""
        bag = check(ratified(at=T(0)), retired(sha="a", at=T(1)))
        assert list(bag) == []


class TestCorrections:
    @pytest.mark.req("REQ-INTEG-005")
    def test_correction_targeting_a_nonexistent_event(self) -> None:
        bag = check(correction(target="CO-99.ratified"))
        assert [d.code for d in bag] == ["CK-E0505"]

    @pytest.mark.req("REQ-INTEG-005")
    def test_correction_targeting_a_not_yet_occurred_event_is_unknown(self) -> None:
        """A correction can only annotate the past.

        The target-existence check walks the total order and only ever knows
        about events at or before the correction's own position in it -- a
        correction whose target sorts *later* is indistinguishable from one
        whose target does not exist at all, and reports the same CK-E0505.
        That is intentional: an append-only ledger has no notion of
        correcting something that has not happened yet, so treating "exists,
        but in the future" as "unknown" is the correct outcome even though the
        referenced event key is technically present elsewhere in the ledger.
        """
        events = [
            correction(target="CO-1.ratified", at=T(0)),
            ratified(at=T(1)),
        ]
        bag = check(*events)
        assert [d.code for d in bag] == ["CK-E0505"]

    @pytest.mark.req("REQ-LEDGER-009")
    def test_correction_targeting_another_correction_is_a_chain(self) -> None:
        bag = check(
            ratified(at=T(0)),
            correction(cr_id="CR-1", target="CO-1.ratified", sha="cr1", at=T(1)),
            correction(cr_id="CR-2", target="CR-1.correction", sha="cr2", at=T(2)),
        )
        assert [d.code for d in bag] == ["CK-E0307"]


class TestDuplicateEventIdentity:
    @pytest.mark.req("REQ-INTEG-004")
    def test_two_files_claiming_the_same_event_key(self) -> None:
        """Structurally rare (paths are unique) but defensively checked."""
        from charter_core.ids import LedgerPath
        from charter_core.models.state import ResolvedEvent

        a = ratified(sha="a")
        b = ResolvedEvent(
            path=LedgerPath("ledger/CO-1.ratified.duplicate.yaml"),
            event=a.event,
            provenance=a.provenance,
        )
        bag = check_integrity(charter(), total_order([a, b]))
        assert [d.code for d in bag] == ["CK-E0504"]


def test_multiple_independent_problems_are_all_reported() -> None:
    """One evaluation surfaces everything wrong, not just the first problem."""
    bag = check(
        ratified(co_id="CO-1", non_goal_id="NG-99"),
        retired(co_id="CO-2"),
        correction(cr_id="CR-1", target="CO-99.ratified"),
    )
    assert {d.code for d in bag} == {"CK-E0501", "CK-E0502", "CK-E0505"}

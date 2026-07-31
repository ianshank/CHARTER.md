"""Deriving LedgerState: statuses, the moot cascade, genesis, ratchet baselines.

The ratchet cluster here is the highest-value test in the suite: it is the
direct evidence for R3-1, the defect round 2's watermark design introduced and
round 3 caught -- a review closing must not reset a level trigger's baseline
to zero (that would turn a budget into a rate limit) and must not let it
refire immediately either (that is the original deadlock F3 existed to fix).
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from charter_core.models.state import CarveOutStatus, ReviewStatus
from charter_core.projection import project

from ..builders import (
    T,
    charter,
    expired,
    non_goal,
    ratified,
    retired,
    review_closed,
    review_opened,
)


class TestCarveOutStatusDerivation:
    def test_a_ratified_carveout_is_active(self) -> None:
        state = project(charter(), [ratified(at=T(0))], at=T(1))
        assert state.carveouts["CO-1"].status is CarveOutStatus.ACTIVE

    def test_a_retired_carveout_is_retired(self) -> None:
        events = [ratified(at=T(0)), retired(at=T(1))]
        state = project(charter(), events, at=T(2))
        assert state.carveouts["CO-1"].status is CarveOutStatus.RETIRED

    def test_an_attested_expiry_is_expired(self) -> None:
        events = [ratified(at=T(0)), expired(at=T(1))]
        state = project(charter(), events, at=T(2))
        assert state.carveouts["CO-1"].status is CarveOutStatus.EXPIRED

    @pytest.mark.req("REQ-TRIGGER-009")
    def test_a_declared_expiry_takes_effect_without_an_event(self) -> None:
        """A8: expires_at is a legal stored declaration, not derived provenance."""
        event = ratified(at=T(0), expires_at=T(10))
        before = project(charter(), [event], at=T(5))
        after = project(charter(), [event], at=T(10))
        assert before.carveouts["CO-1"].status is CarveOutStatus.ACTIVE
        assert after.carveouts["CO-1"].status is CarveOutStatus.EXPIRED

    @pytest.mark.req("REQ-TRIGGER-009")
    def test_effective_expiry_is_the_earlier_of_declared_and_attested(self) -> None:
        """A8: min(declared, attested)."""
        events = [ratified(at=T(0), expires_at=T(20)), expired(at=T(5))]
        state = project(charter(), events, at=T(5))
        assert state.carveouts["CO-1"].expires_at == T(5)


class TestMootCascade:
    @pytest.mark.req("REQ-TRIGGER-007")
    def test_retiring_the_non_goal_makes_its_carveouts_moot(self) -> None:
        """A12: excluded from every count, not merely from the active status."""
        c = charter(non_goals=[non_goal("NG-1", status="retired")])
        state = project(c, [ratified(at=T(0))], at=T(1))
        carveout = state.carveouts["CO-1"]
        assert carveout.status is CarveOutStatus.MOOT
        assert carveout.counts_toward_level is False
        assert carveout.counts_toward_velocity is False

    def test_moot_overrides_an_otherwise_active_carveout(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", status="retired")])
        state = project(c, [ratified(at=T(0))], at=T(1))
        assert state.carveouts["CO-1"].status is CarveOutStatus.MOOT

    def test_active_carveouts_on_other_non_goals_are_unaffected(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", status="retired"), non_goal("NG-2")])
        events = [ratified("CO-1", "NG-1", at=T(0)), ratified("CO-2", "NG-2", at=T(0))]
        state = project(c, events, at=T(1))
        assert state.carveouts["CO-1"].status is CarveOutStatus.MOOT
        assert state.carveouts["CO-2"].status is CarveOutStatus.ACTIVE


class TestGenesisExemption:
    @pytest.mark.req("REQ-TRIGGER-006")
    def test_events_at_or_before_adopted_at_are_historical(self) -> None:
        """A11: exempt from velocity, still counted by level."""
        c = charter(adopted_at=T(0))
        state = project(c, [ratified(at=T(0))], at=T(1))
        carveout = state.carveouts["CO-1"]
        assert carveout.historical is True
        assert carveout.counts_toward_velocity is False
        assert carveout.counts_toward_level is True

    def test_events_after_adopted_at_are_not_historical(self) -> None:
        c = charter(adopted_at=T(0))
        state = project(c, [ratified(at=T(1))], at=T(2))
        assert state.carveouts["CO-1"].historical is False

    def test_no_adopted_at_means_nothing_is_historical(self) -> None:
        state = project(charter(), [ratified(at=T(0))], at=T(1))
        assert state.carveouts["CO-1"].historical is False


class TestReviewStatusDerivation:
    def test_opened_with_no_closure_is_open(self) -> None:
        state = project(charter(), [review_opened(at=T(0))], at=T(1))
        assert state.reviews["RV-1"].status is ReviewStatus.OPEN
        assert state.open_reviews == (state.reviews["RV-1"],)

    def test_opened_and_closed_is_closed(self) -> None:
        events = [review_opened(at=T(0)), review_closed(at=T(1))]
        state = project(charter(), events, at=T(2))
        assert state.reviews["RV-1"].status is ReviewStatus.CLOSED
        assert state.open_reviews == ()


class TestEventVisibilityRespectsAt:
    """Evaluating 'as of at' must not see events that have not happened yet."""

    def test_an_event_after_at_is_invisible(self) -> None:
        state = project(charter(), [ratified(at=T(10))], at=T(5))
        assert state.carveouts == {}

    def test_an_event_exactly_at_at_is_visible(self) -> None:
        state = project(charter(), [ratified(at=T(5))], at=T(5))
        assert "CO-1" in state.carveouts


class TestRatchetBaseline:
    """A2: level triggers ratchet; they never reset.

    baseline = level observed at the most recent covering closure, then
    tracking downward as the minimum observed since. This is the corrected
    design from R3-1.
    """

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_no_covering_review_means_no_baseline(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        state = project(c, events, at=T(3))
        assert state.baselines.for_non_goal("NG-1") is None

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_baseline_is_the_level_observed_at_closure(self) -> None:
        """Three active carve-outs, review closes -> baseline is 3."""
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            review_opened(at=T(3), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(4)),
        ]
        state = project(charter(), events, at=T(5))
        assert state.baselines.for_non_goal("NG-1") == 3

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_ratchet_no_refire_when_level_is_unchanged(self) -> None:
        """The deadlock test: standing still after a review must not re-fire.

        Level stays at 3 after closure -> baseline stays 3 -> a fresh
        evaluation at the same level is not above its own baseline.
        """
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            review_opened(at=T(3), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(4)),
        ]
        state = project(charter(), events, at=T(10))
        baseline = state.baselines.for_non_goal("NG-1")
        assert baseline is not None
        assert baseline == 3
        active_now = len(state.active_carveouts_for("NG-1"))
        assert active_now == 3
        assert not (active_now > baseline)

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_ratchet_further_erosion_still_refires(self) -> None:
        """The ceiling must survive review; this is what round 2's design got wrong.

        A fourth carve-out after closure exceeds the baseline.
        """
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            review_opened(at=T(3), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(4)),
            ratified("CO-4", at=T(5)),
        ]
        state = project(charter(), events, at=T(6))
        baseline = state.baselines.for_non_goal("NG-1")
        assert baseline is not None
        assert baseline == 3
        active_now = len(state.active_carveouts_for("NG-1"))
        assert active_now == 4
        assert active_now > baseline

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_ratchet_improvement_locks_in_a_lower_baseline(self) -> None:
        """Retiring one after closure permanently drops the floor to 2.

        Per A2's 'tracks downward'. Returning to 3 must fire again.
        """
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            review_opened(at=T(3), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(4)),
            retired("CO-3", at=T(5)),
        ]
        state = project(charter(), events, at=T(6))
        assert state.baselines.for_non_goal("NG-1") == 2

        # A carve-out returning the level to 3 is now above the lowered floor.
        with_new = [*events, ratified("CO-4", at=T(7))]
        later = project(charter(), with_new, at=T(8))
        later_baseline = later.baselines.for_non_goal("NG-1")
        assert later_baseline is not None
        assert len(later.active_carveouts_for("NG-1")) == 3
        assert later_baseline < 3

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_a_later_closure_overrides_an_earlier_ones_baseline(self) -> None:
        """The *most recent* covering closure sets the baseline."""
        events = [
            ratified("CO-1", at=T(0)),
            review_opened("RV-1", at=T(1), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed("RV-1", at=T(2)),
            ratified("CO-2", at=T(3)),
            ratified("CO-3", at=T(4)),
            review_opened("RV-2", at=T(5), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed("RV-2", at=T(6)),
        ]
        state = project(charter(), events, at=T(7))
        assert state.baselines.for_non_goal("NG-1") == 3

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_a_global_review_covers_every_non_goal(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2), non_goal("NG-2", budget=2)])
        events = [
            ratified("CO-1", "NG-1", at=T(0)),
            ratified("CO-2", "NG-2", at=T(1)),
            review_opened(at=T(2), scope_global=True),
            review_closed(at=T(3)),
        ]
        state = project(c, events, at=T(4))
        assert state.baselines.for_non_goal("NG-1") == 1
        assert state.baselines.for_non_goal("NG-2") == 1

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_a_non_goal_scoped_review_does_not_cover_a_different_non_goal(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2), non_goal("NG-2", budget=2)])
        events = [
            ratified("CO-1", "NG-1", at=T(0)),
            review_opened(at=T(1), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(2)),
        ]
        state = project(c, events, at=T(3))
        assert state.baselines.for_non_goal("NG-1") == 1
        assert state.baselines.for_non_goal("NG-2") is None

    def test_baseline_is_not_computed_for_a_retired_non_goal(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", status="retired")])
        events = [
            review_opened(at=T(0), scope_global=True),
            review_closed(at=T(1)),
        ]
        state = project(c, events, at=T(2))
        assert state.baselines.for_non_goal("NG-1") is None


class TestCumulativeBaseline:
    @pytest.mark.req("REQ-TRIGGER-005")
    def test_no_global_closure_means_no_cumulative_baseline(self) -> None:
        state = project(charter(), [ratified(at=T(0))], at=T(1))
        assert state.baselines.cumulative is None

    @pytest.mark.req("REQ-TRIGGER-005")
    def test_baseline_is_the_ratio_observed_at_global_closure(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=5), non_goal("NG-2", budget=5)])
        events = [
            ratified("CO-1", "NG-1", at=T(0)),
            review_opened(at=T(1), scope_global=True),
            review_closed(at=T(2)),
        ]
        state = project(c, events, at=T(3))
        assert state.baselines.cumulative == Fraction(1, 2)

    @pytest.mark.req("REQ-TRIGGER-005")
    def test_a_non_goal_scoped_closure_does_not_set_the_cumulative_baseline(self) -> None:
        """Cumulative is inherently repo-wide; only a global closure re-baselines it."""
        events = [
            ratified(at=T(0)),
            review_opened(at=T(1), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(2)),
        ]
        state = project(charter(), events, at=T(3))
        assert state.baselines.cumulative is None

    def test_retiring_a_carveout_after_closure_lowers_the_cumulative_floor(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=5), non_goal("NG-2", budget=5)])
        events = [
            ratified("CO-1", "NG-1", at=T(0)),
            ratified("CO-2", "NG-2", at=T(1)),
            review_opened(at=T(2), scope_global=True),
            review_closed(at=T(3)),
            retired("CO-2", at=T(4)),
        ]
        state = project(c, events, at=T(5))
        assert state.baselines.cumulative == Fraction(1, 2)

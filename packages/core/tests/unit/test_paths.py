"""Computing amendment-path state from trigger results and open reviews."""

from __future__ import annotations

from fractions import Fraction

import pytest

from charter_core.models.state import Closure
from charter_core.paths import compute_path_state
from charter_core.projection import project
from charter_core.triggers.base import GLOBAL_SCOPE, TriggerResult

from ..builders import T, charter, review_opened


def result(trigger_id, scope, *, fired):
    return TriggerResult(
        trigger_id=trigger_id,
        kind="level" if trigger_id != "density" else "velocity",
        fired=fired,
        scope=scope,
        observed=Fraction(0),
        threshold=Fraction(0),
        baseline=None,
        margin=Fraction(0),
    )


class TestNothingFired:
    def test_everything_stays_open(self) -> None:
        state = project(charter(), [], at=T(0))
        path = compute_path_state(state, [])
        assert path.global_state is Closure.OPEN
        assert path.for_non_goal("NG-1") is Closure.OPEN


class TestPerIdClosure:
    @pytest.mark.req("REQ-TRIGGER-001")
    def test_closes_only_the_scoped_non_goal(self) -> None:
        state = project(charter(), [], at=T(0))
        results = [result("per_id", "NG-1", fired=True), result("per_id", "NG-2", fired=False)]
        path = compute_path_state(state, results)
        assert path.for_non_goal("NG-1") is Closure.CLOSED
        assert path.for_non_goal("NG-2") is Closure.OPEN
        assert path.global_state is Closure.OPEN
        assert path.causes["NG-1"] == ("per_id",)


class TestGlobalClosure:
    @pytest.mark.req("REQ-TRIGGER-002")
    def test_density_closes_the_path_for_every_non_goal(self) -> None:
        state = project(charter(), [], at=T(0))
        results = [result("density", GLOBAL_SCOPE, fired=True)]
        path = compute_path_state(state, results)
        assert path.global_state is Closure.CLOSED
        assert path.for_non_goal("NG-1") is Closure.CLOSED
        assert path.for_non_goal("NG-anything-untouched") is Closure.CLOSED
        assert path.causes[GLOBAL_SCOPE] == ("density",)

    @pytest.mark.req("REQ-TRIGGER-008")
    def test_cumulative_also_closes_globally(self) -> None:
        state = project(charter(), [], at=T(0))
        results = [result("cumulative", GLOBAL_SCOPE, fired=True)]
        path = compute_path_state(state, results)
        assert path.global_state is Closure.CLOSED

    def test_both_global_triggers_firing_records_both_causes(self) -> None:
        state = project(charter(), [], at=T(0))
        results = [
            result("density", GLOBAL_SCOPE, fired=True),
            result("cumulative", GLOBAL_SCOPE, fired=True),
        ]
        path = compute_path_state(state, results)
        assert path.causes[GLOBAL_SCOPE] == ("cumulative", "density")


class TestOpenReviewDominates:
    @pytest.mark.req("REQ-TRIGGER-002")
    def test_any_open_review_blocks_ratification_repo_wide(self) -> None:
        """Regardless of the review's own scope -- the open-review-blocks case."""
        c = charter()
        events = [review_opened(at=T(0), scope_global=False, scope_non_goals=("NG-1",))]
        state = project(c, events, at=T(1))
        path = compute_path_state(state, [])
        assert path.global_state is Closure.REVIEW_REQUIRED
        assert path.for_non_goal("NG-2") is Closure.REVIEW_REQUIRED
        assert path.causes[GLOBAL_SCOPE] == ("RV-1",)

    def test_open_review_dominates_a_fired_trigger(self) -> None:
        c = charter()
        events = [review_opened(at=T(0))]
        state = project(c, events, at=T(1))
        results = [result("per_id", "NG-1", fired=True)]
        path = compute_path_state(state, results)
        assert path.global_state is Closure.REVIEW_REQUIRED
        assert path.for_non_goal("NG-1") is Closure.REVIEW_REQUIRED

    def test_multiple_open_reviews_are_all_named_in_causes(self) -> None:
        c = charter()
        events = [
            review_opened("RV-1", at=T(0), scope_non_goals=("NG-1",), scope_global=False),
            review_opened("RV-2", at=T(1), scope_non_goals=("NG-1",), scope_global=False),
        ]
        state = project(c, events, at=T(2))
        path = compute_path_state(state, [])
        assert path.causes[GLOBAL_SCOPE] == ("RV-1", "RV-2")

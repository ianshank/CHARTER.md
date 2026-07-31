"""The guardian contract: PASS, VIOLATION(NG-x), or REVIEW_REQUIRED."""

from __future__ import annotations

import pytest

from charter_core.models.state import Closure, PathState, VerdictKind
from charter_core.verdict import compute_verdict


def path(*, global_state=Closure.OPEN, per_non_goal=None, causes=None):
    return PathState(
        global_state=global_state, per_non_goal=per_non_goal or {}, causes=causes or {}
    )


class TestPass:
    def test_nothing_touched(self) -> None:
        verdict = compute_verdict(path(), touched_non_goals=())
        assert verdict.kind is VerdictKind.PASS
        assert verdict.render() == "PASS"

    def test_touched_but_open(self) -> None:
        verdict = compute_verdict(path(), touched_non_goals=["NG-1"])
        assert verdict.kind is VerdictKind.PASS

    @pytest.mark.req("REQ-VERDICT-003")
    def test_a_closed_non_goal_that_is_not_touched_is_ignored(self) -> None:
        """guardian-untouched-ng-ignored."""
        p = path(per_non_goal={"NG-2": Closure.CLOSED}, causes={"NG-2": ("per_id",)})
        verdict = compute_verdict(p, touched_non_goals=["NG-1"])
        assert verdict.kind is VerdictKind.PASS


class TestViolation:
    @pytest.mark.req("REQ-VERDICT-001")
    def test_a_touched_closed_non_goal_violates(self) -> None:
        p = path(per_non_goal={"NG-1": Closure.CLOSED}, causes={"NG-1": ("per_id",)})
        verdict = compute_verdict(p, touched_non_goals=["NG-1"])
        assert verdict.kind is VerdictKind.VIOLATION
        assert verdict.non_goals == ("NG-1",)
        assert verdict.render() == "VIOLATION(NG-1)"

    @pytest.mark.req("REQ-VERDICT-002")
    def test_multiple_violated_non_goals_render_sorted(self) -> None:
        """guardian-multi-ng-precedence: deterministic ordering."""
        p = path(
            per_non_goal={"NG-2": Closure.CLOSED, "NG-1": Closure.CLOSED},
            causes={"NG-1": ("per_id",), "NG-2": ("per_id",)},
        )
        verdict = compute_verdict(p, touched_non_goals=["NG-2", "NG-1"])
        assert verdict.non_goals == ("NG-1", "NG-2")
        assert verdict.render() == "VIOLATION(NG-1,NG-2)"

    def test_only_touched_non_goals_that_are_closed_are_named(self) -> None:
        p = path(
            per_non_goal={"NG-1": Closure.CLOSED, "NG-2": Closure.CLOSED},
            causes={"NG-1": ("per_id",), "NG-2": ("per_id",)},
        )
        verdict = compute_verdict(p, touched_non_goals=["NG-1", "NG-3"])
        assert verdict.non_goals == ("NG-1",)

    def test_global_closure_violates_every_touched_non_goal(self) -> None:
        p = path(global_state=Closure.CLOSED, causes={"global": ("density",)})
        verdict = compute_verdict(p, touched_non_goals=["NG-1", "NG-2"])
        assert verdict.kind is VerdictKind.VIOLATION
        assert verdict.non_goals == ("NG-1", "NG-2")
        assert verdict.reasons == ("density",)

    def test_reasons_are_deduplicated_across_non_goals(self) -> None:
        p = path(
            per_non_goal={"NG-1": Closure.CLOSED, "NG-2": Closure.CLOSED},
            causes={"NG-1": ("per_id",), "NG-2": ("per_id",)},
        )
        verdict = compute_verdict(p, touched_non_goals=["NG-1", "NG-2"])
        assert verdict.reasons == ("per_id",)


class TestReviewRequired:
    @pytest.mark.req("REQ-VERDICT-004")
    def test_dominates_a_violation(self) -> None:
        """guardian-review-required: dominates VIOLATION."""
        p = path(
            global_state=Closure.REVIEW_REQUIRED,
            per_non_goal={"NG-1": Closure.CLOSED},
            causes={"global": ("RV-1",), "NG-1": ("per_id",)},
        )
        verdict = compute_verdict(p, touched_non_goals=["NG-1"])
        assert verdict.kind is VerdictKind.REVIEW_REQUIRED
        assert verdict.non_goals == ()
        assert verdict.reasons == ("RV-1",)

    def test_review_required_even_with_nothing_touched(self) -> None:
        p = path(global_state=Closure.REVIEW_REQUIRED, causes={"global": ("RV-1",)})
        verdict = compute_verdict(p, touched_non_goals=())
        assert verdict.kind is VerdictKind.REVIEW_REQUIRED

    def test_renders_bare(self) -> None:
        p = path(global_state=Closure.REVIEW_REQUIRED, causes={"global": ("RV-1",)})
        verdict = compute_verdict(p, touched_non_goals=[])
        assert verdict.render() == "REVIEW_REQUIRED"

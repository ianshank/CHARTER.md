"""Frozen dataclasses must stay frozen through their dict-typed fields too.

``frozen=True`` on a dataclass only blocks reassigning an attribute
(``state.carveouts = {}``); it does nothing to stop in-place mutation of a
mutable value already held by that attribute (``state.carveouts["CO-1"] =
...``). Every one of these types is documented as "never stored, always
recomputed" -- a caller silently corrupting a shared reference would violate
that promise for every other holder of the same snapshot. Each field is
wrapped in a :class:`~types.MappingProxyType` at construction to make the
in-place path raise too.
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from types import MappingProxyType

import pytest

from charter_core.models.state import Baselines, Closure, LedgerState, PathState
from charter_core.settings import ApprovalPolicy, ResolvedSettings

AT = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


class TestBaselinesIsReadOnly:
    def test_wraps_a_plain_dict_at_construction(self) -> None:
        baselines = Baselines(per_non_goal={"NG-1": 2})
        assert isinstance(baselines.per_non_goal, MappingProxyType)

    def test_in_place_mutation_raises(self) -> None:
        baselines = Baselines(per_non_goal={"NG-1": 2})
        with pytest.raises(TypeError):
            baselines.per_non_goal["NG-1"] = 99  # type: ignore[index]

    def test_mutating_the_source_dict_after_construction_does_not_leak_in(self) -> None:
        source = {"NG-1": 2}
        baselines = Baselines(per_non_goal=source)
        source["NG-1"] = 99
        assert baselines.per_non_goal["NG-1"] == 2


class TestLedgerStateIsReadOnly:
    def test_carveouts_and_reviews_are_wrapped(self) -> None:
        state = LedgerState(
            ordered=(),
            carveouts={},
            reviews={},
            baselines=Baselines(),
            evaluated_at=AT,
        )
        assert isinstance(state.carveouts, MappingProxyType)
        assert isinstance(state.reviews, MappingProxyType)

    def test_in_place_mutation_of_carveouts_raises(self) -> None:
        state = LedgerState(
            ordered=(), carveouts={}, reviews={}, baselines=Baselines(), evaluated_at=AT
        )
        with pytest.raises(TypeError):
            state.carveouts["CO-1"] = None  # type: ignore[index]


class TestPathStateIsReadOnly:
    def test_per_non_goal_and_causes_are_wrapped(self) -> None:
        path = PathState(global_state=Closure.OPEN, per_non_goal={}, causes={})
        assert isinstance(path.per_non_goal, MappingProxyType)
        assert isinstance(path.causes, MappingProxyType)

    def test_in_place_mutation_of_causes_raises(self) -> None:
        path = PathState(global_state=Closure.OPEN, per_non_goal={}, causes={})
        with pytest.raises(TypeError):
            path.causes["NG-1"] = ("per_id",)  # type: ignore[index]


class TestResolvedSettingsIsReadOnly:
    def test_provenance_is_wrapped(self) -> None:
        settings = ResolvedSettings(
            density_window_days=90,
            density_threshold=3,
            cumulative_ratio=Fraction(1, 2),
            default_carveout_budget=2,
            window_boundary="inclusive",
            require_review_artifact=True,
            ledger_pr_isolation=True,
            approval_policy=ApprovalPolicy(
                min_approvals=1,
                require_code_owner=True,
                distinct_from_author=True,
                self_ratification_allowed=False,
            ),
            provenance={},
        )
        assert isinstance(settings.provenance, MappingProxyType)
        with pytest.raises(TypeError):
            settings.provenance["density_threshold"] = None  # type: ignore[index]

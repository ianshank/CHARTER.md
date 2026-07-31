"""The rolling density window: a closed trailing interval on exact instants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from charter_core.window import in_window

AT = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


class TestBoundaryInclusivity:
    def test_exactly_at_the_start_is_inside_under_inclusive(self) -> None:
        """A3: the default boundary policy, and the density-exact-90 case."""
        start = AT - timedelta(days=90)
        assert in_window(start, at=AT, days=90, boundary="inclusive")

    def test_exactly_at_the_start_is_outside_under_exclusive(self) -> None:
        start = AT - timedelta(days=90)
        assert not in_window(start, at=AT, days=90, boundary="exclusive")

    def test_one_microsecond_before_the_start_is_always_outside(self) -> None:
        just_before = AT - timedelta(days=90) - timedelta(microseconds=1)
        assert not in_window(just_before, at=AT, days=90, boundary="inclusive")
        assert not in_window(just_before, at=AT, days=90, boundary="exclusive")

    def test_exactly_at_at_is_inside_under_both_policies(self) -> None:
        assert in_window(AT, at=AT, days=90, boundary="inclusive")
        assert in_window(AT, at=AT, days=90, boundary="exclusive")

    def test_one_microsecond_after_at_is_always_outside(self) -> None:
        just_after = AT + timedelta(microseconds=1)
        assert not in_window(just_after, at=AT, days=90, boundary="inclusive")
        assert not in_window(just_after, at=AT, days=90, boundary="exclusive")

    def test_well_inside_is_inside_under_both_policies(self) -> None:
        middle = AT - timedelta(days=45)
        assert in_window(middle, at=AT, days=90, boundary="inclusive")
        assert in_window(middle, at=AT, days=90, boundary="exclusive")

    def test_well_outside_is_outside_under_both_policies(self) -> None:
        outside = AT - timedelta(days=91)
        assert not in_window(outside, at=AT, days=90, boundary="inclusive")
        assert not in_window(outside, at=AT, days=90, boundary="exclusive")


@pytest.mark.req("REQ-TRIGGER-003")
@given(
    offset_days=st.floats(min_value=0, max_value=365, allow_nan=False),
    window_days=st.integers(min_value=1, max_value=365),
    advance_seconds=st.integers(min_value=0, max_value=3600 * 24 * 30),
    boundary=st.sampled_from(["inclusive", "exclusive"]),
)
def test_window_membership_is_monotonically_non_increasing_as_at_advances(
    offset_days: float, window_days: int, advance_seconds: int, boundary
) -> None:
    """Sliding ``at`` forward can only drop events from the window, never re-admit one.

    This is the half of "time only relaxes; only events tighten" that the
    density trigger owns outright: it depends solely on ``in_window``, with no
    event-count logic involved, so the property is provable here directly.
    """
    ts = AT - timedelta(days=offset_days)
    later = AT + timedelta(seconds=advance_seconds)

    was_in = in_window(ts, at=AT, days=window_days, boundary=boundary)
    still_in = in_window(ts, at=later, days=window_days, boundary=boundary)

    # If it was already outside (too old), advancing `at` cannot bring it back
    # in -- the window only ever slides in one direction. It CAN newly exclude
    # something that was in range, if `at` advances far enough to leave it
    # behind -- that direction is fine and expected.
    if not was_in and ts <= AT:
        assert not still_in


@pytest.mark.req("REQ-TRIGGER-003")
def test_inclusive_admits_a_superset_of_exclusive() -> None:
    """At any boundary, inclusive can only accept what exclusive already does."""
    start = AT - timedelta(days=90)
    for delta_days in (-1, 0, 1, 45, 89, 90, 91):
        ts = start + timedelta(days=delta_days)
        exclusive = in_window(ts, at=AT, days=90, boundary="exclusive")
        inclusive = in_window(ts, at=AT, days=90, boundary="inclusive")
        if exclusive:
            assert inclusive, f"exclusive admitted {ts} but inclusive did not"

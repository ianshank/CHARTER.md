"""ReviewScope: exactly one of global or non-empty non_goals, never both, never neither."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from charter_core.models.events import ReviewScope

SCOPE = TypeAdapter(ReviewScope)


class TestExactlyOneScope:
    def test_global_alone_is_valid(self) -> None:
        scope = SCOPE.validate_python({"global": True})
        assert scope.global_ is True
        assert scope.non_goals == ()

    def test_non_goals_alone_is_valid(self) -> None:
        scope = SCOPE.validate_python({"global": False, "non_goals": ["NG-1"]})
        assert scope.global_ is False
        assert scope.non_goals == ("NG-1",)

    def test_neither_is_rejected(self) -> None:
        """An empty scope used to parse silently.

        The docstring said "exactly one", but nothing enforced it.
        """
        with pytest.raises(ValidationError, match=r"global.*non-goal"):
            SCOPE.validate_python({"global": False})

    def test_both_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="not both"):
            SCOPE.validate_python({"global": True, "non_goals": ["NG-1"]})


class TestRoundTrip:
    def test_dump_by_alias_then_revalidate(self) -> None:
        scope = SCOPE.validate_python({"global": True})
        assert SCOPE.validate_python(scope.model_dump(by_alias=True)) == scope

    def test_dump_by_field_name_then_revalidate(self) -> None:
        """Confirms the round-trip populate_by_name exists to fix.

        Without it, this raised: the field-name key ``global_`` was not the
        ``global`` alias the model accepted on input.
        """
        scope = SCOPE.validate_python({"global": False, "non_goals": ["NG-1"]})
        assert SCOPE.validate_python(scope.model_dump()) == scope

    def test_field_name_kwarg_still_works_at_construction(self) -> None:
        scope = ReviewScope(global_=True)
        assert scope.global_ is True

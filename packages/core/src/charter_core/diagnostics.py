"""Diagnostics: the values the engine returns instead of raising.

Policy problems are data, not exceptions. ``evaluate`` is total over
well-formed input and reports everything it found, so a single run surfaces
every problem rather than the first one.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Self

from charter_core.errors import CK, Severity


@dataclass(frozen=True, slots=True)
class Location:
    """Where a diagnostic applies, as precisely as the engine can say."""

    path: str | None = None
    event_key: str | None = None
    entity_id: str | None = None
    pointer: str | None = None
    """RFC 6901 JSON pointer into the offending document, when applicable."""


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single finding, always traceable to a registry code."""

    code: str
    severity: Severity
    message: str
    spec_ref: str
    remediation: str
    location: Location | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        ck: CK,
        *,
        message: str | None = None,
        location: Location | None = None,
        **context: Any,
    ) -> Self:
        """Build a diagnostic from a registry entry.

        ``message`` defaults to the registry title; pass one to add the
        specifics that make a failure actionable in CI output.
        """
        definition = ck.value
        return cls(
            code=definition.code,
            severity=definition.severity,
            message=message or definition.title,
            spec_ref=definition.spec_ref,
            remediation=definition.remediation,
            location=location,
            context=context,
        )


class DiagnosticBag:
    """A mutable accumulator that yields an immutable, ordered result.

    Ordering is insertion order, which keeps evaluation reports stable and
    therefore diffable as golden fixtures.
    """

    __slots__ = ("_items",)

    def __init__(self, items: Iterable[Diagnostic] = ()) -> None:
        self._items: list[Diagnostic] = list(items)

    def add(
        self,
        ck: CK,
        *,
        message: str | None = None,
        location: Location | None = None,
        **context: Any,
    ) -> None:
        """Record a finding."""
        self._items.append(Diagnostic.of(ck, message=message, location=location, **context))

    def extend(self, items: Iterable[Diagnostic]) -> None:
        """Record findings produced elsewhere."""
        self._items.extend(items)

    def items(self) -> tuple[Diagnostic, ...]:
        """Every diagnostic recorded so far, in insertion order."""
        return tuple(self._items)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        """Only the error-severity diagnostics."""
        return tuple(d for d in self._items if d.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        """Only the warning-severity diagnostics."""
        return tuple(d for d in self._items if d.severity is Severity.WARNING)

    def has_errors(self) -> bool:
        """Whether any error-severity diagnostic was recorded."""
        return any(d.severity is Severity.ERROR for d in self._items)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


#: Exit-code precedence, most severe first.
#:
#: Declared explicitly rather than derived by ``max()`` over the numeric codes.
#: Numeric ordering happens to rank these correctly today, but only by accident
#: of how the values were assigned -- ``INTERNAL`` (70) and ``INTERRUPTED``
#: (130) outrank everything by number alone, and any future code would silently
#: take a precedence nobody chose. The rule this encodes: a failure that stopped
#: the engine from reaching a conclusion outranks a conclusion it did reach.
_EXIT_CODE_PRECEDENCE: Final[tuple[int, ...]] = (
    70,  # INTERNAL          -- the engine broke; nothing else can be trusted
    5,  # SPEC_UNSUPPORTED   -- semantics unknown, so no verdict is meaningful
    4,  # ENVIRONMENT        -- could not read the repository
    3,  # INPUT_INVALID      -- could not read the documents
    2,  # USAGE              -- could not read the invocation
    1,  # VIOLATION          -- read everything, and it violates the charter
)


def worst_exit_code(diagnostics: Sequence[Diagnostic], *, fail_on_warning: bool = False) -> int:
    """Resolve a set of diagnostics to a single process exit code.

    The most severe finding wins, by the precedence in
    :data:`_EXIT_CODE_PRECEDENCE` rather than by numeric comparison. An
    unrecognised code sorts last, so an unmapped diagnostic degrades to
    "something failed" instead of silently outranking a real blocker.
    """
    from charter_core.errors import REGISTRY

    codes = [
        REGISTRY[d.code].exit_code
        for d in diagnostics
        if d.severity is Severity.ERROR or (fail_on_warning and d.severity is Severity.WARNING)
    ]
    failing = [code for code in codes if code != 0]
    if not failing:
        # Warnings map to exit 0 individually; --fail-on warning turns the
        # presence of any of them into a violation.
        return 1 if (fail_on_warning and codes) else 0

    def rank(code: int) -> int:
        try:
            return _EXIT_CODE_PRECEDENCE.index(code)
        except ValueError:
            return len(_EXIT_CODE_PRECEDENCE)

    return min(failing, key=rank)

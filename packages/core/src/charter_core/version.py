"""Engine and specification versions, and the negotiation between them.

A charter declares which SPEC version it targets. The engine refuses to guess
at semantics it does not know: an unknown major is fatal, a newer minor is a
warning and evaluation continues. Both outcomes carry a stable diagnostic code
so CI output and documentation can reference them precisely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from charter_core.errors import CK

CORE_VERSION: Final[str] = "0.1.0"
SPEC_VERSION: Final[str] = "0.1.0"
SCHEMA_VERSION: Final[str] = "0.1"
SUPPORTED_SPEC_MAJORS: Final[frozenset[int]] = frozenset({0})

SEMVER_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


class Compatibility(StrEnum):
    """The outcome of comparing a declared spec version against this engine."""

    OK = "ok"
    NEWER_MINOR = "newer_minor"
    UNSUPPORTED_MAJOR = "unsupported_major"
    MALFORMED = "malformed"


@dataclass(frozen=True, slots=True)
class SemVer:
    """A parsed semantic version."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> SemVer | None:
        """Parse ``raw``, returning ``None`` when it is not valid semver."""
        match = SEMVER_RE.match(raw)
        if match is None:
            return None
        return cls(
            major=int(match["major"]),
            minor=int(match["minor"]),
            patch=int(match["patch"]),
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class NegotiationResult:
    """What the engine decided about a declared spec version."""

    compatibility: Compatibility
    declared: SemVer | None
    code: CK | None

    @property
    def can_evaluate(self) -> bool:
        """Whether evaluation may proceed under this result."""
        return self.compatibility in (Compatibility.OK, Compatibility.NEWER_MINOR)


def negotiate(declared: str) -> NegotiationResult:
    """Compare a declared ``spec_version`` against what this engine implements."""
    parsed = SemVer.parse(declared)
    if parsed is None:
        return NegotiationResult(Compatibility.MALFORMED, None, CK.E0101_SPEC_MAJOR_UNSUPPORTED)

    if parsed.major not in SUPPORTED_SPEC_MAJORS:
        return NegotiationResult(
            Compatibility.UNSUPPORTED_MAJOR, parsed, CK.E0101_SPEC_MAJOR_UNSUPPORTED
        )

    engine = SemVer.parse(SPEC_VERSION)
    assert engine is not None  # noqa: S101 -- module constant, validated by test
    if parsed.minor > engine.minor:
        return NegotiationResult(Compatibility.NEWER_MINOR, parsed, CK.W0102_SPEC_MINOR_NEWER)

    return NegotiationResult(Compatibility.OK, parsed, None)

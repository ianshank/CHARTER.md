"""Profile registry.

Profiles are presets, not code paths. Adding one is a dictionary entry, which
is what keeps the trigger and approval logic free of per-profile branching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class Profile:
    """A named preset over the settings layer."""

    name: str
    description: str
    max_conformance_level: int
    preset: dict[str, Any]


LITE: Final = Profile(
    name="lite",
    description="Solo maintainer. Single ratifier; self-ratification permitted and stamped.",
    max_conformance_level=2,
    preset={
        "approval_policy": {
            "min_approvals": 0,
            "require_code_owner": False,
            "distinct_from_author": False,
            "self_ratification_allowed": True,
        }
    },
)

STANDARD: Final = Profile(
    name="standard",
    description="Team. One distinct ratifier, code-owner routed.",
    max_conformance_level=3,
    preset={
        "approval_policy": {
            "min_approvals": 1,
            "require_code_owner": True,
            "distinct_from_author": True,
            "self_ratification_allowed": False,
        }
    },
)

ENTERPRISE: Final = Profile(
    name="enterprise",
    description="Regulated. Dual ratification, code-owner routed, no self-ratification.",
    max_conformance_level=4,
    preset={
        "approval_policy": {
            "min_approvals": 2,
            "require_code_owner": True,
            "distinct_from_author": True,
            "self_ratification_allowed": False,
        }
    },
)

PROFILES: Final[dict[str, Profile]] = {p.name: p for p in (LITE, STANDARD, ENTERPRISE)}
DEFAULT_PROFILE: Final[str] = STANDARD.name


def get_profile(name: str | None) -> Profile:
    """Look up a profile by name, falling back to the default."""
    return PROFILES[name or DEFAULT_PROFILE]

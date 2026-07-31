"""Threshold resolution, with per-key provenance.

Every tunable in the system -- window length, density threshold, cumulative
ratio, default budget, approval policy -- resolves through this module and
nowhere else. Each resolved value carries where it came from, which is what
turns "no hard-coded values" from a claim into something ``charter explain
settings`` can print and a reviewer can audit.

Precedence, highest first:
    1. the ``config`` block in charter.yaml
    2. the active profile preset
    3. the schema default
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Any, Final, Literal

WindowBoundary = Literal["inclusive", "exclusive"]


class SettingSource(StrEnum):
    """Which layer supplied a resolved value."""

    EXPLICIT_CONFIG = "config"
    PROFILE = "profile"
    SCHEMA_DEFAULT = "schema_default"


@dataclass(frozen=True, slots=True)
class SettingProvenance:
    """A resolved value and the layer it came from."""

    value: Any
    source: SettingSource
    detail: str


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    """How many, and whose, approvals a ratification requires."""

    min_approvals: int
    require_code_owner: bool
    distinct_from_author: bool
    self_ratification_allowed: bool


#: Schema defaults. These are the *only* literals for these values in the
#: codebase; the JSON Schema is generated from the same numbers, so schema and
#: engine cannot disagree.
SCHEMA_DEFAULTS: Final[dict[str, Any]] = {
    "density_window_days": 90,
    "density_threshold": 3,
    "cumulative_ratio": "0.5",
    "default_carveout_budget": 2,
    "window_boundary": "inclusive",
    "require_review_artifact": True,
    "ledger_pr_isolation": True,
    "min_approvals": 1,
    "require_code_owner": True,
    "distinct_from_author": True,
    "self_ratification_allowed": False,
}


@dataclass(frozen=True, slots=True)
class ResolvedSettings:
    """Fully resolved thresholds for one evaluation."""

    density_window_days: int
    density_threshold: int
    cumulative_ratio: Fraction
    default_carveout_budget: int
    window_boundary: WindowBoundary
    require_review_artifact: bool
    ledger_pr_isolation: bool
    approval_policy: ApprovalPolicy
    provenance: dict[str, SettingProvenance]

    def explain(self, key: str) -> SettingProvenance:
        """Return where ``key`` got its value."""
        return self.provenance[key]


def parse_ratio(raw: str | float | int) -> Fraction:
    """Parse a ratio exactly.

    ``Fraction(str(value))`` reads the decimal literal the author wrote rather
    than the nearest binary float. Comparisons downstream cross-multiply, so a
    configured 0.1 or 0.3 behaves at its boundary exactly as 0.5 does.
    """
    return Fraction(str(raw))


def schema_defaults() -> dict[str, Any]:
    """A copy of the schema-default layer."""
    return dict(SCHEMA_DEFAULTS)


def _resolve(
    key: str,
    *,
    config: dict[str, Any] | None,
    profile_preset: dict[str, Any],
    profile_name: str,
    provenance: dict[str, SettingProvenance],
) -> Any:
    """Resolve one key through the precedence chain, recording its source."""
    if config is not None and key in config and config[key] is not None:
        value = config[key]
        provenance[key] = SettingProvenance(
            value=value,
            source=SettingSource.EXPLICIT_CONFIG,
            detail=f"charter.yaml#/config/{key}",
        )
        return value

    if key in profile_preset:
        value = profile_preset[key]
        provenance[key] = SettingProvenance(
            value=value,
            source=SettingSource.PROFILE,
            detail=f"profile:{profile_name}",
        )
        return value

    value = SCHEMA_DEFAULTS[key]
    provenance[key] = SettingProvenance(
        value=value,
        source=SettingSource.SCHEMA_DEFAULT,
        detail=f"schema:{key}",
    )
    return value


def resolve_settings(
    *,
    config: dict[str, Any] | None,
    profile_name: str,
    profile_preset: dict[str, Any],
) -> ResolvedSettings:
    """Resolve every threshold, recording where each value came from."""
    prov: dict[str, SettingProvenance] = {}

    def get(key: str) -> Any:
        return _resolve(
            key,
            config=config,
            profile_preset=profile_preset,
            profile_name=profile_name,
            provenance=prov,
        )

    approval_config = (config or {}).get("approval_policy") or {}
    approval_preset = profile_preset.get("approval_policy") or {}

    def get_approval(key: str) -> Any:
        return _resolve(
            key,
            config=approval_config,
            profile_preset=approval_preset,
            profile_name=profile_name,
            provenance=prov,
        )

    policy = ApprovalPolicy(
        min_approvals=int(get_approval("min_approvals")),
        require_code_owner=bool(get_approval("require_code_owner")),
        distinct_from_author=bool(get_approval("distinct_from_author")),
        self_ratification_allowed=bool(get_approval("self_ratification_allowed")),
    )

    return ResolvedSettings(
        density_window_days=int(get("density_window_days")),
        density_threshold=int(get("density_threshold")),
        cumulative_ratio=parse_ratio(get("cumulative_ratio")),
        default_carveout_budget=int(get("default_carveout_budget")),
        window_boundary=str(get("window_boundary")),  # type: ignore[arg-type]
        require_review_artifact=bool(get("require_review_artifact")),
        ledger_pr_isolation=bool(get("ledger_pr_isolation")),
        approval_policy=policy,
        provenance=prov,
    )

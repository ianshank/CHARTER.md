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

:data:`SETTING_SPECS` is the single declarative table every consumer derives
from: the raw default, the value published in the generated JSON Schema, and
which ``charter.yaml`` block (``config`` or ``config.approval_policy``) the key
belongs to. Before this table existed, adding one threshold meant editing four
places by hand -- the default, the resolver, the pydantic field, and the schema
stamper -- with nothing to notice a miss. Now three of those four read this
table directly; the fourth (the pydantic field declarations in
``models/charter.py``, which need real type annotations for validation) is
cross-checked against it by a test asserting the key sets are identical, so a
drift between "what this table declares" and "what the model accepts" fails
CI rather than shipping silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Any, Final, Literal

WindowBoundary = Literal["inclusive", "exclusive"]
SettingGroup = Literal["config", "approval_policy"]


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


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """One tunable's identity: its default, and where it is declared."""

    key: str
    default: Any
    """The literal used as the schema default and the resolution floor."""
    group: SettingGroup
    """Which ``ConfigBlock`` sub-object this key is declared on."""
    schema_default: Any = None
    """The JSON-safe value to publish in the schema, if it differs from
    ``default`` (``cumulative_ratio`` is stored as a decimal string for exact
    parsing but published as the JSON number an adopter would actually
    write)."""

    def __post_init__(self) -> None:
        if self.schema_default is None:
            object.__setattr__(self, "schema_default", self.default)


#: The single declarative source of every threshold. Add a tunable here first;
#: everything downstream is either derived from this table or cross-checked
#: against it by a test.
SETTING_SPECS: Final[tuple[SettingSpec, ...]] = (
    SettingSpec("density_window_days", 90, "config"),
    SettingSpec("density_threshold", 3, "config"),
    SettingSpec("cumulative_ratio", "0.5", "config", schema_default=0.5),
    SettingSpec("default_carveout_budget", 2, "config"),
    SettingSpec("window_boundary", "inclusive", "config"),
    SettingSpec("require_review_artifact", True, "config"),
    SettingSpec("ledger_pr_isolation", True, "config"),
    SettingSpec("min_approvals", 1, "approval_policy"),
    SettingSpec("require_code_owner", True, "approval_policy"),
    SettingSpec("distinct_from_author", True, "approval_policy"),
    SettingSpec("self_ratification_allowed", False, "approval_policy"),
)

#: Derived from :data:`SETTING_SPECS`. These are the *only* literals for these
#: values in the codebase; the JSON Schema is generated from the same numbers,
#: so schema and engine cannot disagree.
SCHEMA_DEFAULTS: Final[dict[str, Any]] = {spec.key: spec.default for spec in SETTING_SPECS}

#: Keys declared directly on ``ConfigBlock``, excluding the nested
#: ``approval_policy`` object. Cross-checked in tests against
#: ``ConfigBlock.model_fields``.
CONFIG_KEYS: Final[frozenset[str]] = frozenset(
    spec.key for spec in SETTING_SPECS if spec.group == "config"
)

#: Keys declared on ``ApprovalPolicyConfig``. Cross-checked in tests against
#: ``ApprovalPolicyConfig.model_fields``.
APPROVAL_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    spec.key for spec in SETTING_SPECS if spec.group == "approval_policy"
)


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
    """Resolve every threshold, recording where each value came from.

    Iterates :data:`SETTING_SPECS` rather than naming keys individually, so a
    tunable added to the table is resolved (and its provenance recorded)
    without a second edit here.
    """
    prov: dict[str, SettingProvenance] = {}
    approval_config = (config or {}).get("approval_policy") or {}
    approval_preset = profile_preset.get("approval_policy") or {}

    raw: dict[str, Any] = {}
    for spec in SETTING_SPECS:
        if spec.group == "config":
            raw[spec.key] = _resolve(
                spec.key,
                config=config,
                profile_preset=profile_preset,
                profile_name=profile_name,
                provenance=prov,
            )
        else:
            raw[spec.key] = _resolve(
                spec.key,
                config=approval_config,
                profile_preset=approval_preset,
                profile_name=profile_name,
                provenance=prov,
            )

    policy = ApprovalPolicy(
        min_approvals=int(raw["min_approvals"]),
        require_code_owner=bool(raw["require_code_owner"]),
        distinct_from_author=bool(raw["distinct_from_author"]),
        self_ratification_allowed=bool(raw["self_ratification_allowed"]),
    )

    return ResolvedSettings(
        density_window_days=int(raw["density_window_days"]),
        density_threshold=int(raw["density_threshold"]),
        cumulative_ratio=parse_ratio(raw["cumulative_ratio"]),
        default_carveout_budget=int(raw["default_carveout_budget"]),
        window_boundary=raw["window_boundary"],
        require_review_artifact=bool(raw["require_review_artifact"]),
        ledger_pr_isolation=bool(raw["ledger_pr_isolation"]),
        approval_policy=policy,
        provenance=prov,
    )

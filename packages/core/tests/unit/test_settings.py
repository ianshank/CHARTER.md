"""Settings resolution: the "no hard-coded values" guarantee, made auditable.

Every threshold must resolve through one path with recorded provenance. These
tests pin the precedence chain and prove the provenance map is complete, which
is what `charter explain settings` prints for a reviewer.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest

from charter_core.profiles import PROFILES, get_profile
from charter_core.settings import (
    APPROVAL_POLICY_KEYS,
    CONFIG_KEYS,
    SCHEMA_DEFAULTS,
    SETTING_SPECS,
    SettingSource,
    parse_ratio,
    resolve_settings,
)

TUNABLES = (
    "density_window_days",
    "density_threshold",
    "cumulative_ratio",
    "default_carveout_budget",
    "window_boundary",
    "require_review_artifact",
    "ledger_pr_isolation",
)


def resolve(config: dict[str, Any] | None = None, profile: str = "standard"):
    p = get_profile(profile)
    return resolve_settings(config=config, profile_name=p.name, profile_preset=p.preset)


class TestPrecedence:
    def test_schema_default_applies_when_nothing_overrides(self) -> None:
        settings = resolve()
        assert settings.density_window_days == 90
        assert settings.density_threshold == 3
        assert settings.cumulative_ratio == Fraction(1, 2)
        assert settings.explain("density_window_days").source is SettingSource.SCHEMA_DEFAULT

    def test_explicit_config_beats_schema_default(self) -> None:
        settings = resolve({"density_window_days": 30})
        assert settings.density_window_days == 30
        provenance = settings.explain("density_window_days")
        assert provenance.source is SettingSource.EXPLICIT_CONFIG
        assert provenance.detail == "charter.yaml#/config/density_window_days"

    def test_profile_beats_schema_default(self) -> None:
        settings = resolve(profile="enterprise")
        assert settings.approval_policy.min_approvals == 2
        assert settings.explain("min_approvals").source is SettingSource.PROFILE

    def test_explicit_config_beats_profile(self) -> None:
        """The full chain: config > profile > schema default."""
        settings = resolve({"approval_policy": {"min_approvals": 5}}, profile="enterprise")
        assert settings.approval_policy.min_approvals == 5
        assert settings.explain("min_approvals").source is SettingSource.EXPLICIT_CONFIG

    def test_approval_policy_pointer_resolves_to_the_nested_field(self) -> None:
        """The pointer must name where the field actually lives.

        ``min_approvals`` sits under ``config.approval_policy``, not
        ``config`` directly -- a reader following ``.../config/min_approvals``
        would find nothing there.
        """
        settings = resolve({"approval_policy": {"min_approvals": 5}})
        assert (
            settings.explain("min_approvals").detail
            == "charter.yaml#/config/approval_policy/min_approvals"
        )

    def test_top_level_config_pointer_has_no_approval_policy_segment(self) -> None:
        settings = resolve({"density_window_days": 30})
        assert (
            settings.explain("density_window_days").detail
            == "charter.yaml#/config/density_window_days"
        )

    def test_null_config_value_falls_through(self) -> None:
        """An omitted key and an explicit null must behave identically."""
        settings = resolve({"density_window_days": None})
        assert settings.density_window_days == 90
        assert settings.explain("density_window_days").source is SettingSource.SCHEMA_DEFAULT


class TestProvenanceCompleteness:
    def test_every_tunable_records_provenance(self) -> None:
        """A value with no recorded source is a hard-coded value in disguise."""
        settings = resolve()
        for key in TUNABLES:
            assert key in settings.provenance, f"{key} resolved without provenance"

    def test_approval_policy_keys_record_provenance(self) -> None:
        settings = resolve()
        for key in (
            "min_approvals",
            "require_code_owner",
            "distinct_from_author",
            "self_ratification_allowed",
        ):
            assert key in settings.provenance, f"{key} resolved without provenance"

    def test_provenance_value_matches_resolved_value(self) -> None:
        settings = resolve({"density_threshold": 7})
        assert settings.explain("density_threshold").value == 7
        assert settings.density_threshold == 7


class TestExactRatioArithmetic:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.5", Fraction(1, 2)),
            (0.5, Fraction(1, 2)),
            ("0.1", Fraction(1, 10)),
            (0.1, Fraction(1, 10)),
            ("0.3", Fraction(3, 10)),
            ("1", Fraction(1)),
        ],
    )
    def test_ratio_parses_the_decimal_the_author_wrote(self, raw, expected) -> None:
        """Not the nearest binary float.

        0.1 as a float is 0.1000000000000000055511151231257827, which would
        make a boundary comparison at exactly 1/10 unpredictable.
        """
        assert parse_ratio(raw) == expected

    def test_boundary_comparison_is_exact(self) -> None:
        """2 of 20 must equal a 0.1 threshold, which float arithmetic misses."""
        ratio = parse_ratio("0.1")
        numerator, denominator = 2, 20
        assert numerator * ratio.denominator == ratio.numerator * denominator


class TestProfiles:
    def test_all_profiles_resolve(self) -> None:
        for name in PROFILES:
            assert resolve(profile=name) is not None

    def test_lite_permits_self_ratification_and_caps_conformance(self) -> None:
        """Self-ratification is visible, not hidden -- and it limits the claim."""
        settings = resolve(profile="lite")
        assert settings.approval_policy.self_ratification_allowed is True
        assert get_profile("lite").max_conformance_level == 2

    def test_standard_and_enterprise_forbid_self_ratification(self) -> None:
        for name in ("standard", "enterprise"):
            assert resolve(profile=name).approval_policy.self_ratification_allowed is False

    def test_enterprise_requires_dual_ratification(self) -> None:
        assert resolve(profile="enterprise").approval_policy.min_approvals == 2

    def test_unknown_profile_name_is_an_error(self) -> None:
        with pytest.raises(KeyError):
            get_profile("does-not-exist")


def test_schema_defaults_cover_every_tunable() -> None:
    """The schema-default layer is the floor; a gap would be a KeyError at runtime."""
    for key in TUNABLES:
        assert key in SCHEMA_DEFAULTS


class TestSettingSpecsAreTheSingleSourceOfTruth:
    """The table SCHEMA_DEFAULTS, resolve_settings, and the schema stamper derive from.

    The one place that cannot derive from it automatically -- the pydantic
    field declarations, which need real type annotations -- is cross-checked
    here instead, so a key added to one side and not the other fails a test
    rather than drifting silently.
    """

    def test_no_duplicate_keys(self) -> None:
        keys = [spec.key for spec in SETTING_SPECS]
        assert len(keys) == len(set(keys))

    def test_group_partition_is_exhaustive_and_disjoint(self) -> None:
        assert set() == CONFIG_KEYS & APPROVAL_POLICY_KEYS
        assert {spec.key for spec in SETTING_SPECS} == CONFIG_KEYS | APPROVAL_POLICY_KEYS

    def test_config_block_declares_exactly_the_config_group(self) -> None:
        from charter_core.models.charter import ConfigBlock

        declared = set(ConfigBlock.model_fields) - {"approval_policy"}
        assert declared == CONFIG_KEYS, (
            f"ConfigBlock and SETTING_SPECS disagree: "
            f"only in model={declared - CONFIG_KEYS} only in table={CONFIG_KEYS - declared}"
        )

    def test_approval_policy_config_declares_exactly_the_approval_group(self) -> None:
        from charter_core.models.charter import ApprovalPolicyConfig

        declared = set(ApprovalPolicyConfig.model_fields)
        assert declared == APPROVAL_POLICY_KEYS, (
            f"ApprovalPolicyConfig and SETTING_SPECS disagree: "
            f"only in model={declared - APPROVAL_POLICY_KEYS} "
            f"only in table={APPROVAL_POLICY_KEYS - declared}"
        )

    def test_schema_default_is_json_safe(self) -> None:
        """The published schema must never leak the internal string encoding."""
        for spec in SETTING_SPECS:
            assert not (spec.key == "cumulative_ratio" and isinstance(spec.schema_default, str)), (
                "cumulative_ratio's schema_default must be a JSON number, not the decimal string"
            )

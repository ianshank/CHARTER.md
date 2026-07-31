"""The diagnostic registry is the hub SPEC, exit codes, and fixtures key off.

If these tests pass, a code cannot exist without a SPEC reference, two codes
cannot collide, and the registry cannot disagree with the CLI's exit-code enum.
"""

from __future__ import annotations

import re

import pytest

from charter_cli.exit_codes import ExitCode
from charter_core.diagnostics import Diagnostic, DiagnosticBag, Location, worst_exit_code
from charter_core.errors import CK, REGISTRY, Severity

CODE_RE = re.compile(r"^CK-(?:E0[1-9]\d{2}|W1\d{3}|I2\d{3}|W0\d{3})$")
SPEC_REF_RE = re.compile(r"^REQ-[A-Z]+-\d{3}$")


def test_every_code_is_well_formed() -> None:
    for member in CK:
        assert CODE_RE.match(member.code), f"{member.name} has malformed code {member.code}"


def test_codes_are_unique() -> None:
    codes = [m.code for m in CK]
    assert len(codes) == len(set(codes)), "duplicate diagnostic code"
    assert len(REGISTRY) == len(codes)


def test_every_code_cites_a_spec_requirement() -> None:
    """A code with no SPEC reference is enforcement without a rule."""
    for member in CK:
        assert SPEC_REF_RE.match(member.spec_ref), (
            f"{member.name} has malformed spec_ref {member.spec_ref!r}"
        )


def test_every_code_has_actionable_remediation() -> None:
    """CI output must tell the reader what to do, not just what broke."""
    for member in CK:
        remediation = member.value.remediation
        assert len(remediation) > 20, f"{member.name} remediation is too thin"
        assert remediation.endswith("."), f"{member.name} remediation is not a sentence"


def test_exit_codes_are_drawn_from_the_cli_contract() -> None:
    """Core duplicates exit codes as ints to stay pure; they must still agree."""
    valid = {int(code) for code in ExitCode}
    for member in CK:
        assert member.exit_code in valid, f"{member.name} uses an unknown exit code"


def test_error_severity_never_maps_to_success() -> None:
    for member in CK:
        if member.severity is Severity.ERROR:
            assert member.exit_code != ExitCode.OK, f"{member.name} is an error but exits 0"


def test_warning_severity_maps_to_success() -> None:
    """Warnings must not fail a run unless the caller opts in."""
    for member in CK:
        if member.severity is Severity.WARNING:
            assert member.exit_code == ExitCode.OK, f"{member.name} is a warning but fails"


class TestDiagnosticBag:
    def test_preserves_insertion_order(self) -> None:
        """Report stability depends on this; golden fixtures would churn otherwise."""
        bag = DiagnosticBag()
        bag.add(CK.E0701_PATH_CLOSED)
        bag.add(CK.W1003_NO_ACTIVE_NON_GOALS)
        bag.add(CK.E0501_UNKNOWN_NON_GOAL_REF)
        assert [d.code for d in bag] == ["CK-E0701", "CK-W1003", "CK-E0501"]

    def test_partitions_by_severity(self) -> None:
        bag = DiagnosticBag()
        bag.add(CK.E0701_PATH_CLOSED)
        bag.add(CK.W1003_NO_ACTIVE_NON_GOALS)
        assert [d.code for d in bag.errors] == ["CK-E0701"]
        assert [d.code for d in bag.warnings] == ["CK-W1003"]
        assert bag.has_errors()

    def test_empty_bag_has_no_errors(self) -> None:
        assert not DiagnosticBag().has_errors()
        assert len(DiagnosticBag()) == 0

    def test_carries_location_and_context(self) -> None:
        bag = DiagnosticBag()
        bag.add(
            CK.E0501_UNKNOWN_NON_GOAL_REF,
            message="CO-9 references NG-99, which is not declared.",
            location=Location(path="ledger/CO-9.ratified.yaml", event_key="CO-9.ratified"),
            referenced="NG-99",
        )
        (found,) = bag.items()
        assert found.location is not None
        assert found.location.path == "ledger/CO-9.ratified.yaml"
        assert found.context == {"referenced": "NG-99"}

    def test_default_message_falls_back_to_registry_title(self) -> None:
        bag = DiagnosticBag()
        bag.add(CK.E0401_SHALLOW_CLONE)
        assert bag.items()[0].message == CK.E0401_SHALLOW_CLONE.value.title


class TestWorstExitCode:
    def test_no_diagnostics_is_success(self) -> None:
        assert worst_exit_code([]) == ExitCode.OK

    def test_warnings_alone_are_success(self) -> None:
        bag = DiagnosticBag()
        bag.add(CK.W1003_NO_ACTIVE_NON_GOALS)
        assert worst_exit_code(bag.items()) == ExitCode.OK

    def test_warnings_fail_when_the_caller_opts_in(self) -> None:
        bag = DiagnosticBag()
        bag.add(CK.W1003_NO_ACTIVE_NON_GOALS)
        assert worst_exit_code(bag.items(), fail_on_warning=True) == ExitCode.VIOLATION

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            (CK.E0701_PATH_CLOSED, ExitCode.VIOLATION),
            (CK.E0201_DERIVED_VALUE_STORED, ExitCode.INPUT_INVALID),
            (CK.E0401_SHALLOW_CLONE, ExitCode.ENVIRONMENT),
            (CK.E0101_SPEC_MAJOR_UNSUPPORTED, ExitCode.SPEC_UNSUPPORTED),
        ],
    )
    def test_single_error_maps_to_its_code(self, code: CK, expected: ExitCode) -> None:
        bag = DiagnosticBag()
        bag.add(code)
        assert worst_exit_code(bag.items()) == expected

    def test_most_severe_wins(self) -> None:
        """A shallow clone means nothing else could be judged; it must dominate."""
        bag = DiagnosticBag()
        bag.add(CK.E0701_PATH_CLOSED)
        bag.add(CK.E0401_SHALLOW_CLONE)
        assert worst_exit_code(bag.items()) == ExitCode.ENVIRONMENT

    def test_precedence_is_declared_not_derived_from_the_numbers(self) -> None:
        """Order must come from the precedence table, not numeric comparison.

        These two happen to rank the same either way; the point is that the
        rule is stated. The next case is the one that proves it.
        """
        bag = DiagnosticBag()
        bag.add(CK.E0201_DERIVED_VALUE_STORED)  # 3, could not read the documents
        bag.add(CK.E0701_PATH_CLOSED)  # 1, read them and found a violation
        assert worst_exit_code(bag.items()) == ExitCode.INPUT_INVALID

    def test_could_not_conclude_outranks_concluded(self) -> None:
        """The rule: a failure that stopped the engine outranks one it reached."""
        bag = DiagnosticBag()
        bag.add(CK.E0701_PATH_CLOSED)  # a real verdict
        bag.add(CK.E0101_SPEC_MAJOR_UNSUPPORTED)  # no verdict was possible
        assert worst_exit_code(bag.items()) == ExitCode.SPEC_UNSUPPORTED

    def test_order_of_diagnostics_does_not_change_the_exit_code(self) -> None:
        """Aggregation is over a set, not a sequence; CI must be reproducible."""
        first = DiagnosticBag()
        first.add(CK.E0401_SHALLOW_CLONE)
        first.add(CK.E0701_PATH_CLOSED)
        second = DiagnosticBag()
        second.add(CK.E0701_PATH_CLOSED)
        second.add(CK.E0401_SHALLOW_CLONE)
        assert worst_exit_code(first.items()) == worst_exit_code(second.items())

    def test_every_failing_registry_code_has_a_declared_precedence(self) -> None:
        """An unranked code would sort last and could mask a real blocker."""
        from charter_core.diagnostics import _EXIT_CODE_PRECEDENCE

        for member in CK:
            if member.exit_code != ExitCode.OK:
                assert member.exit_code in _EXIT_CODE_PRECEDENCE, (
                    f"{member.name} exits {member.exit_code} with no declared precedence"
                )


def test_diagnostic_of_is_frozen() -> None:
    diagnostic = Diagnostic.of(CK.E0701_PATH_CLOSED)
    with pytest.raises((AttributeError, TypeError)):
        diagnostic.code = "CK-E9999"  # type: ignore[misc]

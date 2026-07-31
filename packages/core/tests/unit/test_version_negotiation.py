"""Version negotiation: refuse to guess at semantics this engine does not know.

An unknown major is fatal because the meaning of the ledger may have changed.
A newer minor is a warning because minors are additive by policy, so evaluation
under the older engine is still sound -- just possibly incomplete.
"""

from __future__ import annotations

import pytest

from charter_core.errors import CK
from charter_core.version import (
    SPEC_VERSION,
    SUPPORTED_SPEC_MAJORS,
    Compatibility,
    SemVer,
    negotiate,
)


class TestSemVerParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.1.0", (0, 1, 0)),
            ("1.0.0", (1, 0, 0)),
            ("10.20.30", (10, 20, 30)),
            ("1.0.0-rc.1", (1, 0, 0)),
            ("1.0.0+build.5", (1, 0, 0)),
        ],
    )
    def test_valid_versions_parse(self, raw: str, expected: tuple[int, int, int]) -> None:
        parsed = SemVer.parse(raw)
        assert parsed is not None
        assert (parsed.major, parsed.minor, parsed.patch) == expected

    @pytest.mark.parametrize(
        "raw", ["1", "1.0", "1.0.0.0", "01.0.0", "v1.0.0", "", "latest", "1.0.x"]
    )
    def test_invalid_versions_are_rejected(self, raw: str) -> None:
        assert SemVer.parse(raw) is None


class TestNegotiation:
    @pytest.mark.req("REQ-VERSION-003")
    def test_exact_match_is_ok(self) -> None:
        result = negotiate(SPEC_VERSION)
        assert result.compatibility is Compatibility.OK
        assert result.code is None
        assert result.can_evaluate

    @pytest.mark.req("REQ-VERSION-003")
    def test_older_minor_is_ok(self) -> None:
        """This engine implements everything an older minor can declare."""
        result = negotiate("0.0.1")
        assert result.compatibility is Compatibility.OK
        assert result.can_evaluate

    @pytest.mark.req("REQ-VERSION-002")
    def test_newer_minor_warns_but_proceeds(self) -> None:
        result = negotiate("0.99.0")
        assert result.compatibility is Compatibility.NEWER_MINOR
        assert result.code is CK.W0102_SPEC_MINOR_NEWER
        assert result.can_evaluate

    @pytest.mark.req("REQ-VERSION-001")
    def test_unknown_major_is_fatal(self) -> None:
        """Semantics may have changed; guessing would be worse than refusing."""
        result = negotiate("9.0.0")
        assert result.compatibility is Compatibility.UNSUPPORTED_MAJOR
        assert result.code is CK.E0101_SPEC_MAJOR_UNSUPPORTED
        assert not result.can_evaluate

    @pytest.mark.req("REQ-VERSION-001")
    def test_malformed_version_is_fatal(self) -> None:
        result = negotiate("not-a-version")
        assert result.compatibility is Compatibility.MALFORMED
        assert not result.can_evaluate
        assert result.declared is None

    def test_unsupported_major_exits_with_its_own_code(self) -> None:
        """A stable exit code lets CI distinguish 'too old' from 'violated'."""
        from charter_cli.exit_codes import ExitCode

        assert CK.E0101_SPEC_MAJOR_UNSUPPORTED.exit_code == ExitCode.SPEC_UNSUPPORTED


def test_engine_declares_a_supported_major() -> None:
    """Guards against a release that cannot evaluate its own spec version."""
    parsed = SemVer.parse(SPEC_VERSION)
    assert parsed is not None
    assert parsed.major in SUPPORTED_SPEC_MAJORS

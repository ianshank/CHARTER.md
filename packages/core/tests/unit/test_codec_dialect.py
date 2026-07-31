"""Behavioural contract for the YAML dialect.

These tests pin *behaviour*, not the library that provides it. Each case is a
hazard that the default YAML 1.1 dialect exhibits and that would be exploitable
in a governance format, so the guarantees must survive a dependency swap.
"""

from __future__ import annotations

import pytest

from charter_core.codec import CodecError, decode, normalize_newlines


@pytest.mark.req("REQ-LEDGER-010")
def test_yaml_11_booleans_stay_strings() -> None:
    """`no`/`yes`/`on`/`off` must not become booleans.

    Under YAML 1.1 a non-goal reading "no" would silently become False.
    """
    decoded = decode("a: no\nb: yes\nc: on\nd: off\n")
    assert decoded == {"a": "no", "b": "yes", "c": "on", "d": "off"}


@pytest.mark.req("REQ-LEDGER-010")
def test_timestamps_stay_strings() -> None:
    """Date-times stay text so pydantic parses them under a declared type.

    JSON has no timestamp type; a decoded datetime would make this engine
    disagree with the JSON Schema it publishes.
    """
    decoded = decode("expires_at: 2027-01-01T00:00:00Z\n")
    assert decoded == {"expires_at": "2027-01-01T00:00:00Z"}
    assert isinstance(decoded["expires_at"], str)


@pytest.mark.req("REQ-LEDGER-010")
def test_json_native_types_are_preserved() -> None:
    """Types JSON does have keep them, so schema validation agrees."""
    decoded = decode("n: 90\nr: 0.5\nt: true\nf: false\nz: null\ns: hello\n")
    assert decoded == {"n": 90, "r": 0.5, "t": True, "f": False, "z": None, "s": "hello"}


@pytest.mark.req("REQ-LEDGER-010")
def test_duplicate_keys_are_rejected() -> None:
    """Last-wins duplicate keys are a tampering vector, not a typo."""
    with pytest.raises(CodecError) as exc:
        decode("budget: 2\nbudget: 99\n")
    assert exc.value.hazard == "duplicate_key"


@pytest.mark.req("REQ-LEDGER-010")
@pytest.mark.parametrize(
    ("document", "hazard"),
    [
        ("a: &anchor 1\nb: *anchor\n", "anchor_alias"),
        ("base:\n  x: 1\nd:\n  <<: *base\n", "merge_key"),
        ("a: 1\n---\nb: 2\n", "multi_document"),
    ],
)
def test_unreviewable_constructs_are_rejected(document: str, hazard: str) -> None:
    """Constructs that make a diff unreviewable are refused outright."""
    with pytest.raises(CodecError) as exc:
        decode(document)
    assert exc.value.hazard == hazard


@pytest.mark.req("REQ-LEDGER-010")
def test_oversize_document_is_rejected() -> None:
    with pytest.raises(CodecError) as exc:
        decode("k: " + ("x" * (256 * 1024 + 1)) + "\n")
    assert exc.value.hazard == "oversize"


@pytest.mark.req("REQ-LEDGER-010")
def test_non_mapping_root_is_rejected() -> None:
    with pytest.raises(CodecError) as exc:
        decode("- one\n- two\n")
    assert exc.value.hazard == "not_a_mapping"


def test_empty_document_decodes_to_empty_mapping() -> None:
    assert decode("") == {}
    assert decode("# only a comment\n") == {}


@pytest.mark.req("REQ-RENDER-001")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("a\nb", "a\nb"),
        ("a\r\n\r\nb", "a\n\nb"),
    ],
)
def test_newline_normalisation_only_touches_line_endings(raw: str, expected: str) -> None:
    """Normalisation collapses CR/CRLF and nothing else.

    Trimming whitespace here would let real drift pass as equal.
    """
    assert normalize_newlines(raw) == expected


def test_newline_normalisation_preserves_significant_whitespace() -> None:
    assert normalize_newlines("  indented  \n") == "  indented  \n"

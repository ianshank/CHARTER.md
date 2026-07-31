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
        ("a: &anchor 1\n", "anchor_alias"),
        ("a: &anchor 1\nb: [*anchor]\n", "anchor_alias"),
        ("seq: &s\n  - 1\nother: *s\n", "anchor_alias"),
        # A merge key is expressed as an alias, so the alias guard catches it.
        ("base: &b\n  x: 1\nd:\n  <<: *b\n", "anchor_alias"),
        ("a: 1\n---\nb: 2\n", "multi_document"),
    ],
)
def test_unreviewable_constructs_are_rejected(document: str, hazard: str) -> None:
    """Constructs that make a diff unreviewable are refused outright."""
    with pytest.raises(CodecError) as exc:
        decode(document)
    assert exc.value.hazard == hazard


@pytest.mark.req("REQ-LEDGER-010")
@pytest.mark.parametrize(
    "document",
    [
        'note: "this is *important* context"',
        'rationale: "R&D workloads are out of scope"',
        'bounding: "applies to src/*.py only"',
        'reason: "the a * b product path is excluded"',
        'note: "see AT&T for the reference implementation"',
        "# owner: R&D team\nid: CO-1\n",
    ],
)
def test_ordinary_prose_containing_yaml_sigils_is_accepted(document: str) -> None:
    """Regression: the guard used to be a lexical scan and rejected these.

    Markdown emphasis and ampersands are entirely ordinary in a rationale or a
    note, and this codec validates contributor-authored governance prose. The
    guard now asks the parser what is really an anchor instead of guessing.
    """
    assert decode(document)


@pytest.mark.req("REQ-LEDGER-010")
@pytest.mark.parametrize(
    "document",
    [
        "reason: |\n  first line\n  ---\n  after a rule\n",
        'reason: "a --- b"\n',
        "---\na: 1\n",
        "reason: |\n  ---\n",
    ],
)
def test_document_separators_inside_content_are_not_stream_boundaries(document: str) -> None:
    """Only a real DocumentStartEvent begins a document, not a '---' in text."""
    assert decode(document)


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


@pytest.mark.req("REQ-LEDGER-010")
def test_parse_errors_report_where_the_problem_is() -> None:
    """A ledger author needs the position, not ruamel's advice to Python users."""
    with pytest.raises(CodecError) as exc:
        decode("a: 1\nb: [unclosed\n")
    message = str(exc.value)
    assert exc.value.hazard == "malformed"
    assert "line 3" in message, f"position missing from {message!r}"
    assert "column" in message


@pytest.mark.req("REQ-LEDGER-010")
@pytest.mark.parametrize(
    "document",
    [
        'a: !!python/object/apply:os.system ["echo pwned"]',
        "a: !!python/name:os.system",
        "a: !!custom value",
    ],
)
def test_arbitrary_tags_cannot_construct_objects(document: str) -> None:
    """Ledger files are untrusted input from contributor pull requests.

    Tag handling happens at construction, after the structural guard's parse
    pass, so this exercises a genuinely different code path from the anchor and
    document guards.
    """
    with pytest.raises(CodecError) as exc:
        decode(document)
    assert exc.value.hazard == "malformed"


@pytest.mark.req("REQ-LEDGER-010")
def test_byte_order_mark_is_rejected() -> None:
    """A BOM would otherwise become part of the first key's name."""
    with pytest.raises(CodecError) as exc:
        decode("﻿id: CO-1\n")
    assert exc.value.hazard == "bom"


@pytest.mark.req("REQ-LEDGER-010")
def test_alias_without_a_defined_anchor_is_still_rejected() -> None:
    """Covers the alias branch directly, with no anchor event preceding it."""
    with pytest.raises(CodecError) as exc:
        decode("b: *undefined\n")
    assert exc.value.hazard == "anchor_alias"


@pytest.mark.req("REQ-LEDGER-010")
def test_control_characters_are_reported_not_raised() -> None:
    """Ruamel's ReaderError must not escape as a stack trace.

    A ledger file with a stray control byte is bad input, which the caller can
    diagnose -- not an engine failure.
    """
    with pytest.raises(CodecError) as exc:
        decode("id: CO-1\x00\n")
    assert exc.value.hazard == "encoding"


@pytest.mark.req("REQ-LEDGER-010")
def test_error_without_a_position_still_produces_a_message() -> None:
    """Not every parser error carries a mark; the message must survive anyway."""
    from ruamel.yaml.error import MarkedYAMLError

    from charter_core.codec import _format_yaml_error

    assert _format_yaml_error(MarkedYAMLError(problem="something went wrong"))


@pytest.mark.req("REQ-LEDGER-010")
def test_duplicate_key_error_carries_a_position() -> None:
    """The most tampering-relevant hazard should say where it is."""
    with pytest.raises(CodecError) as exc:
        decode("budget: 2\nother: x\nbudget: 99\n")
    assert exc.value.hazard == "duplicate_key"
    assert "line" in str(exc.value)


@pytest.mark.req("REQ-LEDGER-010")
def test_size_guard_runs_before_the_parser() -> None:
    """Oversized input must be refused without parsing it.

    Guarding first is what bounds the cost of the two parse passes.
    """
    with pytest.raises(CodecError) as exc:
        decode("k: " + ("x" * (256 * 1024 + 1)) + "\n")
    assert exc.value.hazard == "oversize"


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

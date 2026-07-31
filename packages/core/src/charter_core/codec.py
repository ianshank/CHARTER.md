"""Decoding charter and ledger documents, safely.

This is the one place YAML enters the system, and it is deliberately strict.
The default YAML 1.1 dialect coerces ``no`` to ``False``, turns ISO timestamps
into ``datetime`` objects before pydantic ever sees them, and drops duplicate
keys silently, last-wins. In a governance format all three are exploitable: a
duplicate ``budget:`` key that quietly changes policy is a tampering vector,
not a typo.

So: YAML 1.2 core schema, duplicate keys rejected, anchors and aliases
rejected, one document per file, and timestamps left as strings.

That last point is deliberate and narrow. Decoding produces exactly the JSON
data model -- null, bool, number, string, array, object -- because the
published JSON Schema is the normative artifact and an adopter may validate
their charter with any JSON Schema validator. YAML's timestamp resolver has no
JSON counterpart, so a decoded ``datetime`` would make this engine disagree
with the schema it publishes. Booleans and numbers keep their native types,
which JSON has; date-times stay strings carrying ``format: date-time``, and
pydantic parses them under a declared ``AwareDatetime``.

The behaviour is pinned by contract tests rather than by trusting the library,
so it survives a dependency swap.

This module is pure: it decodes text that a caller has already read.
"""

from __future__ import annotations

from io import StringIO
from typing import Any, Final

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError, SafeConstructor
from ruamel.yaml.error import MarkedYAMLError
from ruamel.yaml.events import (
    AliasEvent,
    DocumentStartEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceStartEvent,
)
from ruamel.yaml.nodes import ScalarNode
from ruamel.yaml.reader import ReaderError

MAX_DOCUMENT_BYTES: Final[int] = 256 * 1024

#: Events that can carry an anchor definition (``&name``).
_ANCHORABLE_EVENTS: Final = (ScalarEvent, MappingStartEvent, SequenceStartEvent)


class CodecError(ValueError):
    """A document could not be decoded under the safe dialect.

    ``hazard`` names the guard that fired, so callers can map the failure to a
    stable diagnostic code rather than matching on message text.
    """

    def __init__(
        self,
        message: str,
        *,
        hazard: str,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.hazard = hazard
        self.line = line
        self.column = column


def _format_yaml_error(exc: MarkedYAMLError) -> str:
    """Render a parser error with its position, dropping ruamel's own advice.

    ruamel appends suggestions aimed at Python authors ("could not find expected
    ':'"), which are unhelpful to someone editing a ledger file. What they need
    is the problem and where it is.
    """
    mark = exc.problem_mark
    problem = (exc.problem or str(exc)).strip()
    if mark is None:
        return problem
    # ruamel marks are zero-based; editors are one-based.
    return f"{problem} (line {mark.line + 1}, column {mark.column + 1})"


class _JsonModelConstructor(SafeConstructor):
    """A constructor whose output stays inside the JSON data model."""


def _construct_timestamp_as_string(constructor: SafeConstructor, node: ScalarNode) -> str:
    """Keep date-times as written, for pydantic to parse under a declared type."""
    del constructor
    return str(node.value)


_JsonModelConstructor.add_constructor("tag:yaml.org,2002:timestamp", _construct_timestamp_as_string)


def _reader() -> YAML:
    """Build a reader pinned to the safe dialect."""
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    yaml.Constructor = _JsonModelConstructor
    return yaml


def _guard_size_and_encoding(text: str) -> None:
    """Cheap guards that must run before the parser sees the document."""
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise CodecError(
            f"Document exceeds {MAX_DOCUMENT_BYTES} bytes.",
            hazard="oversize",
        )
    if text.startswith("﻿"):
        raise CodecError(
            "Document starts with a byte order mark; use plain UTF-8.",
            hazard="bom",
        )


def _guard_structure(text: str) -> None:
    """Reject constructs that are unsafe or unreviewable in a governance file.

    This inspects the YAML **event stream** rather than the raw text. A lexical
    scan cannot do this job: it is unsound in both directions, rejecting
    ordinary prose (``note: "this is *important* context"`` reads as an alias)
    while missing constructs that do not match its shape. The parser already
    knows exactly what is an anchor, an alias, and a document boundary, so ask
    it instead of guessing.

    Merge keys (``<<:``) are caught here too: a merge key is expressed as an
    alias, so rejecting aliases rejects merges by construction.

    Cost is one extra parse pass, which is bounded because
    :func:`_guard_size_and_encoding` runs first.
    """
    documents = 0
    try:
        for event in _reader().parse(StringIO(text)):
            if isinstance(event, DocumentStartEvent):
                documents += 1
                if documents > 1:
                    raise CodecError(
                        "Multi-document streams are not permitted; use one document per file.",
                        hazard="multi_document",
                    )
            elif isinstance(event, AliasEvent):
                raise CodecError(
                    "Aliases and merge keys are not permitted; write the value out in full.",
                    hazard="anchor_alias",
                )
            elif isinstance(event, _ANCHORABLE_EVENTS) and event.anchor:
                raise CodecError(
                    f"Anchors are not permitted (found '&{event.anchor}'); "
                    "they make review unreliable.",
                    hazard="anchor_alias",
                )
    except MarkedYAMLError as exc:
        raise CodecError(_format_yaml_error(exc), hazard="malformed") from exc
    except ReaderError as exc:
        # Undecodable bytes or disallowed control characters. This guard reads
        # the whole document, so it is where such input surfaces -- without
        # this the exception escapes as a stack trace instead of a diagnosis.
        raise CodecError(f"Document is not readable UTF-8 text: {exc}", hazard="encoding") from exc


def decode(text: str) -> dict[str, Any]:
    """Decode a charter or ledger document into a plain mapping.

    Scalars are returned as written -- strings stay strings, ``no`` stays
    ``"no"``, timestamps stay text -- so that pydantic performs every coercion
    under a declared type rather than the YAML resolver guessing.
    """
    _guard_size_and_encoding(text)
    _guard_structure(text)
    try:
        loaded = _reader().load(StringIO(text))
    except DuplicateKeyError as exc:
        raise CodecError(
            f"Duplicate key in document: {_format_yaml_error(exc)}",
            hazard="duplicate_key",
        ) from exc
    except MarkedYAMLError as exc:
        raise CodecError(_format_yaml_error(exc), hazard="malformed") from exc

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise CodecError(
            f"Expected a mapping at the document root, found {type(loaded).__name__}.",
            hazard="not_a_mapping",
        )
    return loaded


def normalize_newlines(text: str) -> str:
    """Collapse CRLF and CR to LF.

    The only normalisation applied before generated-block comparison. Anything
    more -- whitespace trimming, Unicode normalisation -- would let real drift
    pass as equal.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")

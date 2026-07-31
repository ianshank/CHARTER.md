"""Identifier grammars for charter entities and ledger paths.

Ids are the framework's stability promise: they are never reused, never
renumbered, and -- for ledger files -- never moved, because ratification
provenance is derived from the commit that first introduced the path.
"""

from __future__ import annotations

import re
from typing import Final, NewType

from charter_core.models.common import END
from charter_core.models.events import KIND_SUFFIX

NonGoalId = NewType("NonGoalId", str)
CarveOutId = NewType("CarveOutId", str)
ReviewId = NewType("ReviewId", str)
CorrectionId = NewType("CorrectionId", str)
LedgerPath = NewType("LedgerPath", str)

NON_GOAL_RE: Final[re.Pattern[str]] = re.compile(rf"^NG-[1-9][0-9]*{END}")
CARVE_OUT_RE: Final[re.Pattern[str]] = re.compile(rf"^CO-[1-9][0-9]*{END}")
REVIEW_RE: Final[re.Pattern[str]] = re.compile(rf"^RV-[1-9][0-9]*{END}")
CORRECTION_RE: Final[re.Pattern[str]] = re.compile(rf"^CR-[1-9][0-9]*{END}")

LEDGER_DIR: Final[str] = "ledger"
REVIEWS_DIR: Final[str] = "reviews"

#: The filename suffixes, derived from the event union rather than restated.
#:
#: Writing them out again here would let the filename grammar drift away from
#: the events it names -- add a variant to ``EventKind`` and the grammar would
#: silently keep rejecting it.
_KIND_ALTERNATION: Final[str] = "|".join(sorted(set(KIND_SUFFIX.values())))

#: Ledger filenames are restricted to a conservative character set so that
#: case-insensitive and Unicode-normalising filesystems cannot introduce two
#: paths the engine would consider distinct.
LEDGER_PATH_RE: Final[re.Pattern[str]] = re.compile(
    rf"^{LEDGER_DIR}/(?P<id>(?:CO|RV|CR)-[1-9][0-9]*)"
    rf"\.(?P<kind>{_KIND_ALTERNATION})\.yaml{END}"
)


def ordinal(entity_id: str) -> int:
    """Return the numeric part of an id, e.g. ``NG-12`` -> ``12``."""
    return int(entity_id.rsplit("-", 1)[1])


def event_key(entity_id: str, kind: str) -> str:
    """Build the canonical event key, which must equal the ledger file stem."""
    return f"{entity_id}.{kind}"


def parse_ledger_path(path: str) -> tuple[str, str] | None:
    """Split a ledger path into ``(id, kind)``, or ``None`` if it is malformed."""
    match = LEDGER_PATH_RE.match(path)
    if match is None:
        return None
    return match["id"], match["kind"]

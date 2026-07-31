"""Identifier grammars for charter entities and ledger paths.

Ids are the framework's stability promise: they are never reused, never
renumbered, and -- for ledger files -- never moved, because ratification
provenance is derived from the commit that first introduced the path.
"""

from __future__ import annotations

import re
from typing import Final, NewType

NonGoalId = NewType("NonGoalId", str)
CarveOutId = NewType("CarveOutId", str)
ReviewId = NewType("ReviewId", str)
CorrectionId = NewType("CorrectionId", str)
LedgerPath = NewType("LedgerPath", str)

NON_GOAL_RE: Final[re.Pattern[str]] = re.compile(r"^NG-[1-9][0-9]*$")
CARVE_OUT_RE: Final[re.Pattern[str]] = re.compile(r"^CO-[1-9][0-9]*$")
REVIEW_RE: Final[re.Pattern[str]] = re.compile(r"^RV-[1-9][0-9]*$")
CORRECTION_RE: Final[re.Pattern[str]] = re.compile(r"^CR-[1-9][0-9]*$")

LEDGER_DIR: Final[str] = "ledger"
REVIEWS_DIR: Final[str] = "reviews"

#: Ledger filenames are restricted to a conservative character set so that
#: case-insensitive and Unicode-normalising filesystems cannot introduce two
#: paths the engine would consider distinct.
LEDGER_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"^ledger/(?P<id>(?:CO|RV|CR)-[1-9][0-9]*)"
    r"\.(?P<kind>ratified|retired|expired|opened|closed|correction)\.yaml$"
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

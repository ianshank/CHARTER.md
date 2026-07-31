"""The interfaces charter-core depends on, and never implements.

Everything the engine needs from the outside world -- git history, the
filesystem, the review platform, the clock -- arrives through these Protocols.
The CLI supplies real implementations, tests supply fakes, and the engine
cannot tell the difference. That is what keeps ``evaluate`` deterministic and
lets one engine back the CLI, the Action, the MCP server, and the conformance
suite without duplication.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from charter_core.ids import LedgerPath


@dataclass(frozen=True, slots=True)
class Provenance:
    """When and where a ledger event entered the default branch.

    Derived, never stored. ``committed_at`` is the *committer* timestamp -- not
    the author timestamp, which survives rebases and is trivially forgeable --
    of the first commit that introduced the path, walking first-parent from the
    default ref.
    """

    commit_sha: str
    committed_at: datetime
    first_parent: bool
    provisional: bool
    """True when derived off the default branch, making the result advisory."""


class ChangeStatus(StrEnum):
    """How a path changed between two refs."""

    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"


@dataclass(frozen=True, slots=True)
class PathChange:
    """A single path's change between a base and a head ref."""

    path: str
    status: ChangeStatus
    previous_path: str | None = None
    """Populated for renames, which the ledger forbids."""


@dataclass(frozen=True, slots=True)
class Actor:
    """Who did something, recorded as both identity and role.

    A role alone cannot support an audit trail and a bare identity cannot
    express policy, so both are required.
    """

    identity: str
    role: str


@dataclass(frozen=True, slots=True)
class ApprovalFacts:
    """What a review platform reports about a ratifying pull request."""

    pr_number: int
    merged: bool
    author: str
    approvers: tuple[Actor, ...]
    code_owner_approved: bool


@runtime_checkable
class ProvenanceProvider(Protocol):
    """Derives ledger provenance from repository history."""

    def provenance_for(self, paths: Sequence[LedgerPath]) -> Mapping[LedgerPath, Provenance | None]:
        """Return provenance for each path, or ``None`` when it has no commit.

        Implementations should resolve every path in a single history pass;
        per-file invocation does not scale to a mature ledger.
        """
        ...

    def is_shallow(self) -> bool:
        """Whether history is truncated, which makes derivation unsound."""
        ...

    def default_ref(self) -> str:
        """The ref provenance is derived against."""
        ...


@runtime_checkable
class LedgerSource(Protocol):
    """Yields raw ledger documents without interpreting them."""

    def documents(self) -> Iterator[tuple[LedgerPath, Mapping[str, Any]]]:
        """Yield ``(path, decoded mapping)`` for every ledger file."""
        ...


@runtime_checkable
class DiffSource(Protocol):
    """Reports how paths changed between two refs."""

    def changed_paths(self, base: str, head: str) -> Sequence[PathChange]:
        """Return the changes between ``base`` and ``head``, rename-aware."""
        ...


@runtime_checkable
class ApprovalSource(Protocol):
    """Reports approval facts for a pull request."""

    def approvals_for(self, pr_number: int) -> ApprovalFacts:
        """Return the approval facts for ``pr_number``."""
        ...


@runtime_checkable
class PullRequestResolver(Protocol):
    """Maps a commit back to the pull request that introduced it."""

    def pr_for_commit(self, sha: str) -> int | None:
        """Return the pull request number for ``sha``, or ``None`` if direct."""
        ...


@runtime_checkable
class Clock(Protocol):
    """The only source of the current time in the system.

    charter-core never calls this. It exists so the CLI has one auditable
    place where wall-clock time enters, and so tests can pin it.
    """

    def now(self) -> datetime:
        """Return the current time, timezone-aware and in UTC."""
        ...

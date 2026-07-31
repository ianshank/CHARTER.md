"""Referential integrity over the ledger event stream.

Checks that hold *within* the ledger and against the current charter
declarations: every carve-out references a real non-goal, every lifecycle
event (retire, expire, close) refers to something that actually exists, no
entity is retired or closed twice, and corrections target real prior events
rather than each other.

What this module does **not** check: whether a non-goal id was reused after
retirement, or whether `charter.yaml` was edited without a covering review.
Both compare the current declarations against a *previous* revision, which
requires git history -- a `DiffSource` the CLI supplies, not something this
pure module has access to. Those checks live with the git adapter.
"""

from __future__ import annotations

from collections import defaultdict

from charter_core.diagnostics import DiagnosticBag, Location
from charter_core.errors import CK
from charter_core.models.charter import Charter
from charter_core.models.events import Correction, EventKind
from charter_core.models.state import ResolvedEvent

#: Event kinds that terminate a carve-out's or review's lifecycle. Each may
#: occur at most once per id, and each requires the entity it terminates to
#: have been opened first.
_CARVEOUT_TERMINAL_KINDS = (EventKind.CARVEOUT_RETIRED, EventKind.CARVEOUT_EXPIRED)


def check_integrity(charter: Charter, events: tuple[ResolvedEvent, ...]) -> DiagnosticBag:
    """Validate referential integrity across the resolved event stream.

    ``events`` should already be in the engine's total order, so that when two
    problems could both be reported, the diagnostics come out in a stable,
    reproducible sequence.
    """
    bag = DiagnosticBag()
    non_goal_ids = {ng.id for ng in charter.non_goals}

    ratified_ids: set[str] = set()
    carveout_terminal_seen: dict[str, str] = {}  # id -> first terminal event_key
    review_opened_ids: set[str] = set()
    review_closed_seen: dict[str, str] = {}  # id -> first closing event_key
    event_keys_seen: dict[str, list[str]] = defaultdict(list)  # event_key -> paths
    all_event_keys: set[str] = set()

    for resolved in events:
        event = resolved.event
        location = Location(path=resolved.path, event_key=resolved.event_key)
        event_keys_seen[resolved.event_key].append(resolved.path)
        all_event_keys.add(resolved.event_key)

        if event.event_type == EventKind.CARVEOUT_RATIFIED:
            ratified_ids.add(event.id)
            if event.non_goal not in non_goal_ids:
                bag.add(
                    CK.E0501_UNKNOWN_NON_GOAL_REF,
                    message=f"{event.id} references {event.non_goal}, which is not declared.",
                    location=location,
                    referenced=event.non_goal,
                )

        elif event.event_type in _CARVEOUT_TERMINAL_KINDS:
            if event.id not in ratified_ids:
                bag.add(
                    CK.E0502_ORPHAN_LIFECYCLE_EVENT,
                    message=(
                        f"{resolved.event_key} has no matching carveout.ratified for {event.id}."
                    ),
                    location=location,
                )
            elif event.id in carveout_terminal_seen:
                bag.add(
                    CK.E0503_DUPLICATE_LIFECYCLE_EVENT,
                    message=(
                        f"{event.id} already has a terminal event "
                        f"({carveout_terminal_seen[event.id]}); "
                        f"{resolved.event_key} is a duplicate."
                    ),
                    location=location,
                )
            else:
                carveout_terminal_seen[event.id] = resolved.event_key

        elif event.event_type == EventKind.REVIEW_OPENED:
            review_opened_ids.add(event.id)

        elif event.event_type == EventKind.REVIEW_CLOSED:
            if event.id not in review_opened_ids:
                bag.add(
                    CK.E0502_ORPHAN_LIFECYCLE_EVENT,
                    message=f"{resolved.event_key} has no matching review.opened for {event.id}.",
                    location=location,
                )
            elif event.id in review_closed_seen:
                bag.add(
                    CK.E0503_DUPLICATE_LIFECYCLE_EVENT,
                    message=(
                        f"{event.id} was already closed by {review_closed_seen[event.id]}; "
                        f"{resolved.event_key} is a duplicate."
                    ),
                    location=location,
                )
            else:
                review_closed_seen[event.id] = resolved.event_key

        elif event.event_type == EventKind.CORRECTION:
            _check_correction(event, resolved, all_event_keys, bag)

    for event_key, paths in event_keys_seen.items():
        if len(paths) > 1:
            bag.add(
                CK.E0504_DUPLICATE_EVENT_ID,
                message=(
                    f"{event_key} is claimed by {len(paths)} files: {', '.join(sorted(paths))}."
                ),
                location=Location(event_key=event_key),
            )

    return bag


def _check_correction(
    event: Correction,
    resolved: ResolvedEvent,
    all_event_keys: set[str],
    bag: DiagnosticBag,
) -> None:
    location = Location(path=resolved.path, event_key=resolved.event_key)
    target = event.corrects.event_key

    if target not in all_event_keys:
        bag.add(
            CK.E0505_UNKNOWN_CORRECTION_TARGET,
            message=f"{resolved.event_key} corrects {target!r}, which does not exist.",
            location=location,
            referenced=target,
        )
        return

    if target.endswith(".correction"):
        bag.add(
            CK.E0307_CORRECTION_CHAIN,
            message=f"{resolved.event_key} corrects {target}, which is itself a correction.",
            location=location,
            referenced=target,
        )


__all__ = ["check_integrity"]

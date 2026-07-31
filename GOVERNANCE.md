# Governance

## Current model

Single maintainer (`@ianshank`). Decisions are made directly — there is no
steering committee, no voting process, and no formal RFC track, because
inventing one for a project with one regular contributor would be
governance theater. This document describes what actually happens today,
not an aspirational structure for a team that doesn't exist yet.

## How decisions get made today

Informally. Changes get proposed (by the maintainer, or via an AI-assisted
review session), evaluated against the project's own stated non-goals and
design invariants (see `CLAUDE.md`, `docs/architecture.md`), and either
land or don't. AI-assisted sessions (Claude Code) feed findings and
proposals into [`NEXTSTEPS.md`](NEXTSTEPS.md) and
[`CHANGELOG.md`](CHANGELOG.md) the same way a human contributor's proposal
would — triaged by the maintainer, not auto-merged.

## Scope governance

The project governs its *own* scope the same way it asks adopters to govern
theirs: [`charter.yaml`](charter.yaml) and [`CHARTER.md`](CHARTER.md)
declare this repository's own non-goals (currently NG-1: GitHub-only in
v1; NG-2: no MCP server/adapters/expanded enterprise profile until an
external adopter exists), with budgets on how many exceptions are
tolerated before a review is required. That's the canonical mechanism —
this document doesn't restate it.

## How this changes

Revisited once there's a second regular contributor. At that point this
document should describe real things — who has merge rights on which
paths (see [`CODEOWNERS`](CODEOWNERS)), how disagreements get resolved,
whether a review threshold above zero becomes practical (see the
single-maintainer caveat in [`BRANCHING.md`](BRANCHING.md)) — rather than
being pre-designed now for a structure that doesn't exist.

## Release process

No releases have been cut yet. `NEXTSTEPS.md`'s verification checklist
("Verification, once S4 lands") is the closest thing to a release
readiness gate that exists today; this document will point at a real
release process once one exists.

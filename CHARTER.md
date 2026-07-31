# charter-kit's charter

This is the human-readable companion to [`charter.yaml`](charter.yaml) — the
machine-readable declarations charter-kit itself validates against. That
file is the canonical state; this one exists so the reasoning behind it
doesn't only live in a `rationale:` field a validator ignores.

**Status: draft.** There's no ratification process to have run this
through yet — that's the CLI's job (`charter init`, `charter check`), and
the CLI doesn't exist yet (see [`NEXTSTEPS.md`](NEXTSTEPS.md)). Draft status
caps what this project can claim about itself at conformance level 2 and
relaxes trigger-based blocking, but every structural check still applies —
`charter.yaml` is validated against the real `Charter` model in
`packages/core/tests/unit/test_own_charter.py`, the same model every
adopter's document is checked against. Nothing here is decorative.

Once `charter render` exists (S4), the block between the markers below will
be machine-generated from `charter.yaml` and this file will fail CI drift
checks if the two disagree. Until then, it's hand-maintained, and matching
`charter.yaml` is a discipline rather than an enforced invariant.

<!-- charter-kit:begin:non-goals -->
## Non-goals

### NG-1 — GitHub only in v1

The system does not target platforms other than GitHub — no GitLab,
Bitbucket, or generic git-forge support.

Provenance derivation is built around GitHub's specific commit and
pull-request model (`--first-parent` history, PR-to-commit resolution via
the GitHub API). Generalizing that abstraction correctly requires a second
real integration to design against, not speculation about what a second
forge might need.

*Budget: 1 concurrent carve-out.*

### NG-2 — No MCP server, adapters, or expanded enterprise profile yet

The system does not build the MCP server, OpenSpec or Copilot adapters, or
an enterprise profile beyond what `packages/core/src/charter_core/profiles.py`
already defines.

Each of those is a real surface with its own design questions, and building
them before the core gate has a single external adopter risks polishing
infrastructure nobody has validated needs polishing. **The scope gate:**
these stay unbuilt until at least one repository other than this one runs
the gate as a required check.

*Budget: 1 concurrent carve-out.*
<!-- charter-kit:end:non-goals -->

## Why this exists at all

The honest test of a governance framework is whether its own authors are
willing to be governed by it. A `charter.yaml` that only ever validates
against synthetic test fixtures is a schema exercise, not a boundary. This
one is real: it names actual scope decisions this project has already made
(GitHub-only, no premature platform expansion) and puts a number on how many
exceptions to each are tolerated before a review is required — one, for
both, for now.

It's also, deliberately, an incomplete demonstration. Nothing can yet
*enforce* these boundaries the way the design intends — that needs
`charter check` running in CI against real ledger events, which needs the
CLI, which is blocked on a repository setting (see `NEXTSTEPS.md`). Until
then, this document and `charter.yaml` prove the schema and the model are
usable against a real charter, not that the gate works. That's the next
milestone, not this one.

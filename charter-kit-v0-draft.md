# charter-kit — Enterprise Repository Framework (v0 draft)

> Document under review. Reproduced verbatim from the review request of 2026-07-31 so that
> `charter-kit-v0-peer-review.md` is self-contained. Finding references (F1–F11) in the
> review point at sections of this document.

Working name: **charter-kit** (rename freely). A pluggable standard + toolchain that makes
project-charter governance (non-goal IDs, budgeted carve-outs, review triggers)
**computable and CI-enforced**, and exposes charter state to AI agents as first-class
context in spec-driven development (SDD) workflows.

Positioning delta: Spec Kit's `constitution.md` gives principles + semver + amendment
dates; AGENTS.md gives agent instructions. Neither has budgeted amendments, stable
non-goal IDs, carve-out ledgers, density triggers, or a machine-readable
"amendment path closed" state. That delta is the entire product.

---

## 1. Design invariants (the framework's own non-negotiables)

1. **Git is the source of truth.** All charter state lives in the repo. Ratification
   *is* a merged PR through the gate; there is no out-of-band ratification.
2. **State/prose split.** `charter.yaml` is canonical machine state. `CHARTER.md` is
   human prose; every count, date, and budget figure in it is inside generated blocks
   rendered from the yaml. Hand-editing a generated block fails CI.
3. **CI is the control plane; agents are advisory.** Sub-agents improve compliance and
   ergonomics. Only the required status check + branch protection is an actual control.
4. **Append-only ledger.** Ledger entries and review records are never edited or
   deleted; corrections are new entries referencing the old ID.
5. **Agents read and draft; they never write ratified state.** MCP tools and sub-agents
   may read state and open draft PRs. No agent-reachable code path commits to the
   protected branch or mutates `charter.yaml` directly.
6. **Derived values are never stored.** Per-non-goal counts, 90-day density, cumulative
   ratio, and path state are computed from the ledger at check time.

## 2. Repository layout

```
charter-kit/
├── SPEC.md                      # Normative standard (RFC 2119 keywords), versioned
├── CHARTER.md                   # Dogfood: this repo's own charter (DRAFT until v1.0)
├── charter.yaml                 # Dogfood state file
├── schema/
│   ├── charter.schema.json      # JSON Schema for charter.yaml (semver'd with SPEC)
│   └── ledger-event.schema.json # Event/attestation record schema
├── packages/
│   ├── core/                    # Pure library: state model, budget math, window calc
│   ├── cli/                     # charter lint | check | amend | review | render | init
│   ├── renderer/                # charter.yaml -> CHARTER.md generated blocks
│   └── mcp-server/              # charter-mcp: read + draft-PR tools for agents
├── actions/
│   └── charter-gate/            # GitHub Action + reusable workflow (the control)
├── adapters/
│   ├── spec-kit/                # constitution bridge; /specify + /plan phase gates
│   ├── openspec/                # change-package gate mapping
│   ├── claude-code/             # materializes agents/ into .claude/agents + hooks
│   └── copilot/                 # instructions-file templates (best-effort tier)
├── agents/                      # Portable, tool-agnostic sub-agent role definitions
│   ├── charter-guardian.md
│   ├── amendment-drafter.md
│   └── review-facilitator.md
├── conformance/                 # Fixture repos + golden files; adapters must pass
├── examples/
│   ├── lite/                    # Solo-maintainer profile
│   ├── standard/                # Team profile
│   └── enterprise/              # Regulated profile
├── governance/
│   ├── rfcs/                    # Changes to SPEC.md go through RFCs post-1.0
│   ├── CODEOWNERS-policy.md
│   └── release-policy.md
├── docs/                        # Integration guides, ADRs, precedence chain
└── .github/
    ├── workflows/               # gate, release (signed tags, provenance), conformance
    ├── PULL_REQUEST_TEMPLATE/
    │   └── carveout.md          # §7.1-complete carve-out template
    └── CODEOWNERS               # charter.yaml, CHARTER.md, governance/ -> ratifiers
```

## 3. State model

```yaml
# charter.yaml (canonical; all counts derived, never stored)
spec_version: "0.1.0"          # version of the charter-kit SPEC this file targets
charter_version: "1.0.0"       # semver of THIS charter's content
status: draft | ratified
amendment_path: open | closed  # closed is set only by core when a trigger fires
last_full_review: 2026-07-31 | null

non_goals:
  - id: NG-1
    text: "The system does not X"
    rationale: "Why this boundary exists"
    status: active | retired
    budget: 2                  # per-ID carve-out budget

carveouts:
  - id: CO-1
    non_goal: NG-1
    title: "Short title"
    constraints: [bounding, mechanism, safety, sequencing]   # §7.1 completeness
    ratified_by: "role:maintainer"
    ratified_at: "2026-07-31T14:02:11Z"   # UTC merge-commit timestamp of ratifying PR
    pr: 42
    commit: "abc123"
    status: active | retired | expired

reviews:
  - id: RV-1
    opened: "2026-07-30T09:00:00Z"
    closed: null                # while any review is open, ratification is blocked
    trigger: per_id | density | cumulative | voluntary
    artifact: "reviews/2026-07-30.md"
```

**Clock semantics (normative):** `ratified_at` is the UTC merge-commit timestamp of the
ratifying PR. The 90-day density window is computed over `ratified_at` values in
calendar days, UTC. This removes the ambiguity that makes the prose version
uncomputable.

**Trigger evaluation (in `core`, exhaustively unit-tested):**
- Per-ID: active carve-outs on NG-x ≥ budget → third proposal sets `amendment_path: closed` for NG-x.
- Density: ≥3 ratifications across all NGs in any rolling 90-day window → global close.
- Cumulative: active carve-outs ≥ 50% of active non-goals → next proposal forces review.
- Any open review with `closed: null` → all ratification blocked repo-wide.

## 4. Enforcement pipeline (defense in depth)

1. **Local:** pre-commit hook runs `charter lint` (schema + §7.1 completeness).
2. **PR — `charter-gate` (required status check):**
   - Schema validation of `charter.yaml` and ledger events.
   - Append-only diff check on carve-outs/reviews (no edits, no deletions).
   - Budget math: per-ID, density window, cumulative ratio recomputed from scratch.
   - Path state: reject ratification PRs while `amendment_path: closed` or a review is open.
   - Render freshness: `charter render --check` must produce a zero diff against
     `CHARTER.md` generated blocks.
   - Non-goal edits without a corresponding review artifact → fail.
3. **Repo settings:** branch protection requires the gate; CODEOWNERS routes
   `charter.yaml`, `CHARTER.md`, `governance/` to ratification authority.
4. **Release:** signed tags, pinned-by-SHA action dependencies, minimal token
   permissions (`contents: read`, `checks: write`), SLSA provenance + SBOM on releases
   (enterprise profile).

## 5. Agent & sub-agent architecture

**charter-mcp (MCP server) — read + draft only:**

| Tool / resource | Behavior |
|---|---|
| `charter://state` (resource) | Full parsed state incl. derived counts, path state |
| `check_budget(non_goal_id)` | Remaining budget, density status, blocking reviews |
| `validate_carveout(draft)` | §7.1 completeness + trigger simulation ("would this close the path?") |
| `draft_amendment(payload)` | Opens a **draft PR** via API using the carve-out template; never commits to default branch |
| `request_review(reason)` | Opens a review record as a draft PR + `reviews/` artifact stub |

**Portable sub-agent roles** (defined once in `agents/`, materialized per-tool by
adapters — e.g., into `.claude/agents/` for Claude Code):

- **charter-guardian** — read-only. Invoked before any plan/spec generation; consumes
  `charter://state`; emits exactly one verdict: `PASS`, `VIOLATION(NG-x)`, or
  `REVIEW_REQUIRED`. Collaboration default: the planning agent consumes the verdict
  automatically; a `VIOLATION` or `REVIEW_REQUIRED` verdict halts implementation and
  routes to amendment-drafter or review-facilitator respectively.
- **amendment-drafter** — drafts §7.1-complete carve-outs via `draft_amendment`. Hard
  rule in its definition: refuses to draft when `check_budget` reports the path closed;
  its only valid output in that state is a charter-review request.
- **review-facilitator** — active only when a review is open. Compiles the evidence
  pack (ledger stats, diffs since last review, trigger that fired) into the `reviews/`
  artifact. Cannot close the review; a human does.

**Orchestration contract (normative in SPEC.md):** agents collaborate by default on
*reads* (guardian verdicts flow to planners without being asked); all *writes* funnel
through draft PRs and the gate. Tools without sub-agent support (baseline Copilot)
get the instructions-file adapter and rely on the CI gate as backstop — degraded
ergonomics, identical enforcement.

## 6. SDD integration & precedence

- **Precedence chain (normative):** Charter > constitution (Spec Kit) > spec > plan >
  tasks/NEXTSTEPS. More-specific documents refine, never contradict, higher levels.
- **Spec Kit adapter:** injects a Charter Check into the constitution-check step; a
  spec or plan touching an `active` non-goal without a ratified CO fails `/specify` /
  `/plan`. Charter fields can seed `constitution.md` governance metadata (one-way sync).
- **OpenSpec adapter:** change packages declare touched NG IDs; gate validates against
  state before the package is accepted.

## 7. Conformance levels & profiles

| Level | Meaning |
|---|---|
| CL-1 Documented | `CHARTER.md` + schema-valid `charter.yaml` present |
| CL-2 Validated | `lint`/`check` green (local or advisory CI) |
| CL-3 Enforced | Gate is a required check + branch protection + CODEOWNERS |
| CL-4 Integrated | SDD phase gates + agent adapters active |

Profiles: **lite** (solo; single ratifier; CL-2 minimum), **standard** (team; CL-3),
**enterprise** (dual ratification, JSONL audit export with retention policy, signed
tags, SLSA/SBOM; CL-4). Self-ratification is permitted only in lite and is stamped
`self_ratified: true` in the ledger — visible, not hidden.

## 8. Governance of the standard itself

- Pre-1.0: this repo's own charter runs with `status: draft` — triggers are computed
  and reported but do not block. This is explicit policy, not a quiet exemption, and it
  exists because early-stage scope churn would otherwise trip triggers constantly.
- At 1.0: charter is ratified; SPEC changes require an RFC in `governance/rfcs/` with
  two approvals; schema majors follow SPEC majors.

## 9. Delivery roadmap (MVP cut is the recommendation, the rest is ceiling)

- **M0 — ship first:** `schema/` + `packages/core` + `cli` (`lint`, `check`) +
  `actions/charter-gate` + one `examples/lite`. Nothing else.
- **M1:** renderer, `amend`/`review` commands, PR templates, CODEOWNERS policy.
- **M2:** spec-kit adapter + claude-code sub-agent materialization.
- **M3:** mcp-server (read/draft), openspec + copilot adapters, conformance suite.
- **M4:** enterprise profile (audit export, dual ratification, SLSA/SBOM).

Gate for building M2+: at least one repo other than charter-kit itself running CL-3.

## 10. Risk register (condensed)

| Risk | Exposure | Mitigation |
|---|---|---|
| Platform-before-adopters | Months of build, zero demand signal | M0 cut; M2+ gated on external CL-3 adoption |
| MCP write-path bypasses ratification | Governance integrity | Invariant 5: read/draft-PR only; no agent path to protected branch |
| Agents skip guardian invocation | Compliance gap | CI gate is the control; agent roles are ergonomics (stated in SPEC) |
| Dogfooding paradox pre-1.0 | Credibility ("they exempt themselves") | Explicit `draft` status with computed-but-non-blocking triggers |
| CL badge-hunting (protection quietly off) | Trust in conformance claims | `charter attest` (repo-settings verification via API) — deferred; needs GitHub App scopes |
| Action supply chain | Enterprise security review | SHA-pinned deps, minimal permissions, signed releases |
| Custom budget engine vs. existing policy engines | Build cost / NIH | Evaluate OPA/conftest as check engine before writing `core` (see review note) |

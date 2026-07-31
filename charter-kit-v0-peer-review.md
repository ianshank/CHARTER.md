# Peer Review — charter-kit Enterprise Repository Framework (v0 draft)

Reviewer: Claude Code (objective technical review, requested as part of project inception)
Date: 2026-07-31
Artifact reviewed: charter-kit v0 draft (design invariants, state model, enforcement pipeline, agent architecture, roadmap) — reproduced verbatim in `charter-kit-v0-draft.md`.

---

## Verdict

The architecture is sound and the strategic instincts are unusually good — in particular the
decision to treat CI as the only real control and label everything agentic as advisory. The
positioning delta (budgeted amendments, stable non-goal IDs, append-only carve-out ledgers,
computed triggers) is real: neither Spec Kit's `constitution.md` nor AGENTS.md has it.

However, **the state model as drafted is internally inconsistent in three places**, and all
three trace to the same root cause: current-state records that mutate in place, in a system
whose invariants promise append-only history and derived-only values. These are spec-level
defects, cheap to fix now and expensive to fix after anyone adopts the schema. They should be
resolved before M0, because the schema is the one thing that cannot be quietly changed later.

**Recommendation: proceed to M0 after resolving F1–F4.** One structural change — an
event-sourced, file-per-event ledger with all state derived at check time — resolves F1, F2,
and F3 simultaneously and simplifies the gate implementation.

---

## Major findings

### F1 — The append-only invariant contradicts the state model (blocker)

Invariant 4 states ledger entries and review records are *never edited or deleted*; corrections
are new entries. But the state model requires in-place mutation:

- carve-outs transition `status: active → retired | expired` (an edit to an existing entry);
- reviews transition `closed: null → <timestamp>` (an edit — and closing a review is the
  single most important state transition in the system, since an open review blocks all
  ratification repo-wide);
- non-goals transition `active → retired`.

As written, the gate's append-only diff check would reject every legitimate lifecycle
transition. The alternative — whitelisting status-field edits — reopens the tampering surface
the invariant exists to close (flipping a carve-out to `retired` to free per-ID budget is
byte-for-byte identical to a legitimate retirement).

**Recommendation:** event-source the ledger. The layout already hints at this
(`ledger-event.schema.json` exists, but the state model ignores it). The strongest variant is
one file per event (`ledger/2026/CO-1.ratified.yaml`, `ledger/2026/CO-1.retired.yaml`,
`ledger/2026/RV-1.closed.yaml`):

- Append-only enforcement reduces to "PRs may only *add* files under `ledger/`, never modify
  or delete" — a trivial, unambiguous diff check.
- All statuses become derived (satisfying Invariant 6 for real).
- YAML merge conflicts on a single hot `charter.yaml` disappear (the changesets/ADR pattern).
- `charter.yaml` shrinks to slow-moving declarations: non-goals, budgets, versions.

### F2 — Provenance chicken-and-egg: `ratified_at` / `commit` cannot exist pre-merge (blocker)

`ratified_at` is defined as the UTC merge-commit timestamp of the ratifying PR, and `commit`
as the merge SHA — but both are written *inside the commit being merged*, and the merge
commit's SHA and timestamp do not exist until after the merge. Every resolution of this is
currently off the table:

- fill them optimistically pre-merge → wrong the moment a PR sits for a day, corrupting the
  90-day density math the clock-semantics paragraph exists to protect;
- stamp them post-merge with a bot commit → violates Invariant 5 (no automated writes to the
  protected branch) and produces unreviewed commits on the ratified branch;
- compute them at check time from git history → correct, but then storing them violates
  Invariant 6 (derived values are never stored).

**Recommendation:** take the third option and stop storing the fields. Define the normative
fact as: *the committer timestamp (UTC) of the commit that first introduces the ledger entry
to the default branch*. This is well-defined under merge, squash, and rebase strategies
(GitHub is the committer in all three), forgery-resistant, and fully derivable. Note the
implementation consequence: the gate needs `fetch-depth: 0`; document it and its cost on
large repos. This also dissolves most of F6 — `pr` and `commit` stop being self-asserted
claims and become computed facts.

### F3 — `amendment_path` storage, per-NG closure, and missing reopen semantics (blocker)

Three defects in one field:

1. **A global scalar cannot represent per-NG closure.** The per-ID trigger "sets
   `amendment_path: closed` for NG-x," but the field is a single top-level value. The schema
   cannot express "closed for NG-1, open for NG-2."
2. **Storing it violates Invariant 6** and creates a stored-vs-computed disagreement with no
   defined winner. §4 says budget math is recomputed from scratch at the gate — so the stored
   field is redundant when it agrees and misleading when it doesn't. Note also §3 says
   "closed is set only by core" — but core is specified as a *pure library*; pure libraries
   don't commit. Nobody in the design is actually authorized to write this field.
3. **Nothing defines how a closed path reopens.** The review-facilitator cannot close reviews;
   humans close them — but closing a review record is an edit forbidden by Invariant 4 (see
   F1). And density closure is defined over "any rolling 90-day window," which read literally
   is *any historical window*: one busy quarter closes the path forever. As drafted, the first
   trigger fire is a permanent deadlock.

**Recommendation:** never store path state; compute per-NG and global state at check time
from the event ledger. Define reopen transitions explicitly: a `review.closed` event
(ratifier-authored, through the gate — trivially expressible in the F1 event model) reopens
the paths its scope covers; state whether density closure auto-reopens as the window slides
or persists until a review closes. Either is defensible; silence is not.

### F4 — TOCTOU between gate check and merge (major)

Required status checks evaluate at PR head, not at merge time. With a sliding density window
and trigger state that depends on *other* merges, "passed the gate" ≠ "valid at merge":

- Two carve-out PRs are open; each sees 2 of 3 density slots used; both pass; both merge;
  the window now holds 4 ratifications and no closure fired on either.
- A PR passes on Monday, merges Friday after a third unrelated ratification landed Wednesday.

**Recommendation:** at CL-3, require strict up-to-date branches or a merge queue for
ledger-touching PRs (spec this as a MUST in the CL-3 definition alongside branch protection).
Add a post-merge verification workflow that recomputes state on every push to the default
branch and raises a visible red flag (issue + failing status) on violation — it cannot
unmerge, but it converts a silent breach into a loud one within minutes. Spec the evaluation
instant normatively: merge-time state is authoritative; PR-time checks are advisory previews.

### F5 — §7.1 completeness as drafted is checkable in name only (major)

`constraints: [bounding, mechanism, safety, sequencing]` is a list of labels. The gate can
verify the four words are present — checkbox theater, not completeness. Make it an object
with four required, non-empty content fields:

```yaml
constraints:
  bounding:   "Applies only to read paths under /export"
  mechanism:  "Feature-flagged; flag owned by platform team"
  safety:     "No PII leaves the region; verified by test X"
  sequencing: "Expires when NG-3 review RV-2 closes"
```

And state honestly in SPEC.md that CI validates *structure*; substance is reviewed by
ratifiers (and pre-screened by agents). Claiming more invites the first "the gate passed a
garbage carve-out" incident.

### F6 — Ledger fields are self-asserted (major)

`ratified_by`, `pr`, and `commit` are YAML claims the gate never verifies. Enterprise dual
ratification is then a policy on paper: nothing checks the PR actually had two ratifier
approvals. The gate should cross-check the referenced PR against the GitHub API — merged into
the default branch, approvals satisfy the active profile's policy, approver identities
recorded. This requires `pull-requests: read`, so update §4's minimal-token spec
(`contents: read, checks: write` is not sufficient). If F2's compute-from-history
recommendation is adopted, most of the self-assertion surface disappears; what remains is
approval verification, which is the part enterprise buyers will audit first. Related:
`ratified_by: "role:maintainer"` records a role, not an identity — audit trails need both,
and dual ratification needs a list.

---

## Moderate findings

**F7 — Trigger math needs the precision it claims to have.** The clock-semantics paragraph
says the ambiguity is removed; several remain:

- "Third proposal" assumes budget = 2; the rule should be budget-relative ("the (budget+1)th").
- Window boundaries: inclusive or exclusive at exactly 90 days? Timestamps or calendar-day
  truncation? The draft says both "calendar days, UTC" and gives full UTC timestamps — pick one.
- "Any rolling 90-day window" over all history vs. the trailing window at evaluation time
  (see F3.3) — presumably trailing; say so.
- Cumulative trigger with zero active non-goals: division by zero; define the behavior.
- Active-only counting is gameable: retiring/expiring a carve-out frees per-ID budget;
  adding trivial non-goals dilutes the cumulative ratio. Decide lifetime vs. concurrent
  counting per trigger and justify it in SPEC; consider making NG *additions* (not just
  edits) review-gated, and define whether "non-goal edits" in the §4 gate includes additions
  and retirements.

**F8 — Roadmap sequencing bug.** The M0 gate includes the render-freshness check (§4.2), but
the renderer ships in M1. Either ship the gate with that check config-disabled at M0 (and say
so), or pull a minimal renderer into M0. As written, M0 is not internally buildable.

**F9 — CL-3 "Enforced" overpromises.** What CI enforces is ledger and process integrity. No
check detects that a feature PR semantically violates NG-2 — that is guardian/human territory
and inherently advisory, as the draft itself says (Invariant 3). SPEC.md should state in one
bold sentence: *the gate enforces the amendment process, not the boundary itself*. Consider
renaming CL-3 to "Gated," or define "Enforced" precisely. Otherwise the first
bypass-by-semantics incident reads as a broken product promise rather than a documented limit.

**F10 — Platform coupling is undeclared scope.** Branch protection, CODEOWNERS, draft PRs,
Actions, merge queues — the entire control plane is GitHub. That's a fine v1 scoping decision,
but SPEC.md (an RFC 2119 document) should abstract the roles (gate, protected ref, ratifier
routing) from their GitHub bindings, and the project should declare GitHub-only-v1 as an
actual non-goal *in its own charter, with a budget*. This is a free dogfooding win: the
project's first NG-1 writes itself.

**F11 — "Ratification PR" is undefined.** The gate must distinguish ratification PRs (blocked
while path closed) from ordinary code PRs (never blocked by path state). Define detection —
presumably "touches the ledger" — and decide whether mixed PRs (code + ledger changes) are
legal. Recommended: ledger-touching PRs MUST touch only ledger files and rendered blocks.
This isolation rule simplifies the gate, CODEOWNERS routing, and review scoping in one move.

---

## Minor findings

- `reviews/` is referenced by the state model (`artifact: "reviews/2026-07-30.md"`) but
  absent from the §2 repository layout.
- `self_ratified: true` (§7) is absent from the state-model sketch and schema.
- `last_full_review` is stored but derivable from the last closed review — Invariant 6 again.
- `expired` status exists with no `expires_at` field or expiry rule anywhere. Who expires a
  carve-out, and when? (In the F1 event model: an `expires_at` on the ratified event plus
  derivation at check time — no mutation needed.)
- CLI list has no `migrate` command, but `spec_version` implies schema evolution. Define the
  gate's version-negotiation policy now (MUST fail on unknown major, SHOULD warn on newer
  minor) — it costs a paragraph today and a migration crisis later.
- CL-3's definition should enumerate the required branch-protection settings (enforce for
  admins, require code-owner review, dismiss stale approvals, block force pushes) rather than
  saying "branch protection." Until `charter attest` exists, the written checklist is the
  only defense against badge-hunting.

## Security notes

- **MCP token scope:** `draft_amendment` needs push rights to create branches for draft PRs.
  Prefer a GitHub App with per-repo installation scoping, or push to forks; never mount a
  ratifier's PAT into the MCP server. An agent that can push any branch can also push
  ordinary code branches — acceptable, but say so in the threat model.
- **Prompt injection:** non-goal rationale and carve-out prose are attacker-influenceable
  inputs (any contributor PR can propose text) that flow into guardian and drafter context.
  Impact is bounded because agents are advisory, but add it to the risk register and have
  the guardian's definition treat charter prose as data, never as instructions.
- **Gate needs history:** the append-only diff check and (per F2) history-derived facts
  require `fetch-depth: 0`. Undocumented, this will be the #1 adopter bug report, and a
  shallow clone silently weakens the append-only check.

---

## Strengths worth keeping

1. **Invariant 3 is the best decision in the document.** Naming the required status check as
   the only control and demoting agents to ergonomics is honest in a way most agent-adjacent
   governance designs are not, and it's restated consistently (§5 orchestration contract,
   risk register). Guard this framing in every future edit.
2. **The state/prose split with render-freshness checking** is the proven pattern
   (`terraform fmt -check`, codegen drift gates) applied correctly.
3. **M0 minimality plus the external-adoption gate for M2+** directly attacks the dominant
   risk (platform-before-adopters), and the risk register names NIH explicitly. Endorsed
   strongly: run the OPA/conftest spike *before* writing `core`. Likely outcome: Rego covers
   the pure budget math, but not the git-history-derived facts — which F2 shows must exist
   anyway. Expect a hybrid (small git-fact extractor + either Rego or a few hundred lines of
   library code); a timeboxed spike settles it cheaply.
4. **The clock-semantics paragraph** is the right instinct — F2/F7 finish what it started.
5. **Dogfooding with disclosure** (§8) and **self-ratification stamping** (§7) handle the
   credibility problems most standards bodies fumble.
6. **Conformance levels** map to real adoption maturity and give the sales conversation a
   vocabulary. (See F9 for the one naming hazard.)

## Positioning assessment

The delta claim is accurate: Spec Kit's constitution has versioned principles and amendment
dates but no budgets, ledgers, density triggers, or machine-readable path state; AGENTS.md is
instructions, not state. The honest open question is not whether the delta exists but whether
it alone clears the adoption bar — a disciplined team could approximate 60% of it with
conventions plus conftest. The durable moat is more likely the integration surface (renderer,
SDD phase gates, MCP state exposure) than the budget math itself. The M0/M2 adoption gate
answers this question empirically before real money is spent, which is exactly right.

## Summary of requested changes before M0

| # | Change | Severity |
|---|--------|----------|
| F1 | Event-sourced, file-per-event ledger; drop in-place status mutation | Blocker |
| F2 | Derive `ratified_at`/`commit` from git history at check time; stop storing them | Blocker |
| F3 | Never store path state; define per-NG closure and explicit reopen transitions | Blocker |
| F4 | Merge queue / strict up-to-date at CL-3 + post-merge verification workflow | Major |
| F5 | §7.1 constraints as keyed content object, not label list | Major |
| F6 | Gate verifies PR approvals vs. profile policy; add `pull-requests: read` | Major |
| F7–F11 | Trigger precision, M0 sequencing, CL-3 naming, platform scope as NG, ratification-PR definition | Moderate |

None of these threaten the architecture; all of them get harder after the first external
adopter pins the schema.

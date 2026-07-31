# Branching model

The exact mechanics: branch roles, required-check tables, and branch
protection settings. For the contributor-facing why and how (naming,
commit convention, PR checklist), see [`CONTRIBUTING.md`](CONTRIBUTING.md).
This file is separate because required-check names churn with
`.github/workflows/ci.yml`'s job list, and that churn shouldn't force edits
to contributor-facing prose every time.

## Branch roles

```
feature/*, fix/*, claude/*  --PR-->  dev  --promote-->  qa  --promote-->  main
```

- **`dev`** — integration branch. Every feature/fix PR targets this, never
  `main` directly.
- **`qa`** — pre-release verification branch, promoted from `dev` via PR
  when `dev` is in a state worth verifying before release.
- **`main`** — the protected release branch. Promoted from `qa` via PR.
  Always releasable.

Do not skip a stage (`dev` → `main` directly). GitHub's "Create pull
request" UI defaults the base branch to the repository's *default* branch
— when opening a PR, check the base is actually `dev` before submitting;
it will not default there automatically.

**This does not change the existing default-branch requirement.** S4 (see
`NEXTSTEPS.md`) is still blocked on the repository's *default branch*
becoming `main` — `--first-parent` provenance derivation walks history from
whatever ref GitHub considers default, and that must be `main`, never
`dev`, since `main` is the release branch in this model.

## Applying this: no tool did it for you

Nothing in this repository's tooling can configure GitHub branch protection
rules automatically — there's no available API/CLI access from within a
Claude Code session for repository admin settings. The tables below need to
be applied by hand, once, via **Settings → Branches → Add branch protection
rule** for each of `main`, `qa`, `dev`.

**Ordering constraint**: a status check only appears in the "required
checks" search box after it has run at least once *against that specific
branch*. Push to each branch (or merge a PR into it) under the current
`ci.yml` first, confirm the Actions tab shows a green run for that branch,
then configure protection. Applying protection before any check has run
against a branch means you won't find it in the dropdown.

## Required status checks

Exact check names, copied from `ci.yml`'s job `name:` fields — must match
verbatim in the GitHub UI's required-checks search box.

| Check | main | qa | dev |
|---|:---:|:---:|:---:|
| `Lint, types, and architecture` | ✅ | ✅ | ✅ |
| `Tests (py3.11 / ubuntu-latest)` | ✅ | ✅ | ✅ |
| `Tests (py3.12 / ubuntu-latest)` | ✅ | ✅ | ✅ |
| `Tests (py3.13 / ubuntu-latest)` | ✅ | ✅ | ✅ |
| `Tests (py3.12 / windows-latest)` | ✅ | ✅ | ✅ |
| `Tests (py3.12 / macos-latest)` | ✅ | ✅ | ✅ |
| `Schema drift` | ✅ | ✅ | ✅ |
| `Coverage floors` | ✅ | ✅ | — |
| `Dependency and dead-code hygiene` | ✅ | ✅ | — |
| `Dependency vulnerabilities and secrets` | ✅ | ✅ | — |
| `Wheels install without the workspace` | ✅ | ✅ | — |

All 11 checks *run* on every push to every branch regardless of this table
(see `ci.yml`'s trigger) — this table is only which ones block a merge.
`dev` gets a fast build/test/schema-integrity smoke gate; `qa` and `main`
get full rigor. That's incremental strictness up the promotion chain, not
an oversight — if CI cost ever becomes a real constraint, revisit by adding
rows here rather than by conditionally skipping jobs in `ci.yml` (keeps one
source of truth for "required" instead of two that can drift).

## Branch protection settings

| Setting | main | qa | dev |
|---|:---:|:---:|:---:|
| Require a pull request before merging | yes | yes | yes |
| Required approving reviews | **1** ⚠️ | 0 | 0 |
| Dismiss stale reviews on new commits | yes | — | — |
| Require linear history | **yes** | no | no |
| Require branches to be up to date before merging | yes | no | no |
| Block force pushes | yes | yes | yes |
| Block branch deletion | yes | yes | yes |
| Enforce rules for administrators | **yes** | no | no |
| Allowed merge methods | Squash / Rebase only | any | any |

### ⚠️ Single-maintainer caveat — read before applying to `main`

GitHub does not count a pull request author's own approval toward a
required-review threshold. With one collaborator on this repository,
setting "required approvals: 1" on `main` will **block the maintainer from
merging their own PR** the moment it's applied, until either a second
collaborator exists to approve, or the maintainer temporarily adds
themselves to the rule's bypass list for that merge. This is a real,
immediate consequence — not a hypothetical edge case — so apply it knowing
that's the tradeoff, or set required approvals to 0 on `main` until a
second regular contributor exists and raise it then.

### Linear history is a change from current practice

PRs #1–#3 all merged into `main` via a regular merge commit ("Merge pull
request #N from ..."). Once "Require linear history" is enabled, **"Create
a merge commit" disappears from the merge button** on PRs targeting `main`
— use Squash or Rebase (see `CONTRIBUTING.md`'s merge-method section).

## Verifying it's actually applied

After configuring all three branches:

1. Attempt a direct push to `main` (`git push origin HEAD:main` from a
   local commit not going through a PR) — must be rejected.
2. Open a throwaway PR into each of `dev`, `qa`, and `main` — the merge
   button must stay disabled until the checks listed as required in the
   table above report success, and must show the required review count
   where applicable.
3. Settings → Branches should list three rules whose configuration matches
   the tables above exactly — check this after any future edit to this
   file, since the file and the live GitHub settings have no automated
   sync and can drift.

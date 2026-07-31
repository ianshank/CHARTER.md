# Contributing

This is pre-release software with a single maintainer today. AI-assisted
sessions (Claude Code, working on branches named `claude/<slug>`) are a
normal contribution path here, not a special case — they follow the same
branching, review, and commit conventions as anyone else.

## Before you start

Check [README.md](README.md)'s "What exists today" table for what's
actually built versus scaffolded, and [`NEXTSTEPS.md`](NEXTSTEPS.md) for
what's blocked and what's next. Don't infer scope from the design docs in
`docs/` — they describe the full end state, not what's in scope right now.

## Development environment

See [`CLAUDE.md`](CLAUDE.md)'s "Build and test commands" section, or the
README's "Development" section — `uv sync`, `make all`, `make help`. Not
repeated here to avoid a third copy drifting out of sync with the other two.

## Branching strategy

```
feature/<slug>, fix/<slug>, claude/<slug>
        |
        | PR, always
        v
       dev  --(maintainer promotes via PR)-->  qa  --(maintainer promotes via PR)-->  main
```

- **Target `dev`, not `main`, for all feature/fix work.** GitHub's "Create
  pull request" UI defaults the base branch to the repository's *default*
  branch — check the base is actually `dev` before submitting; it will not
  pick `dev` automatically.
- **Never skip a stage.** `dev → main` directly is not a valid path; `dev`
  promotes to `qa`, `qa` promotes to `main`.
- Feature branch naming: `feature/<short-slug>` for new capability,
  `fix/<short-slug>` for a bug fix, `claude/<session-slug>` for AI-assisted
  session branches (the existing convention from PRs #1–#3).
- See [`BRANCHING.md`](BRANCHING.md) for the exact required-checks and
  branch-protection configuration on each branch.

## Commit message convention

Follow the pattern already established across this repository's history
rather than a generic convention invented for this document. A real
example (`git log --oneline`):

```
S6: five defects in merged code -- one invariant gap, one mutability gap,
one naming mismatch, one broken pointer, one unchecked test suite
```

- **Subject**: `<scope-or-work-package>: <summary>`. The scope prefix is
  whatever groups the change meaningfully (a work-package id like `S6`, a
  package name, a component) — not a rigid taxonomy to look up, just a
  short label a reader recognizes at a glance in `git log --oneline`.
- **Body**: explains *why*, not what — the diff already shows what changed.
  State the problem being fixed, the constraint that shaped the approach,
  or the tradeoff being made. Skip the body only for genuinely
  self-explanatory changes.
- **Trailers**: AI-assisted commits carry `Co-Authored-By:` and
  `Claude-Session:` trailers. Keep them if you're continuing AI-assisted
  work; they're provenance, not decoration.

## Merge method by branch

- **`dev`, `qa`**: whatever GitHub's default merge button offers (currently
  a regular merge commit — see PR #1–#3's history). No linear-history
  requirement on these branches.
- **`main`**: **Squash and merge** or **Rebase and merge** only, once
  `BRANCHING.md`'s linear-history rule is applied. Hand-edit the resulting
  commit message to follow the convention above — don't accept GitHub's
  auto-generated list of every commit-in-the-PR as the message.

## Before opening a PR

- `make all` green locally (or at minimum `uv run pre-commit run
  --all-files`, which covers everything except the full coverage run).
- `CHANGELOG.md`'s `[Unreleased]` section updated if the change is
  user-visible.
- `NEXTSTEPS.md` updated if the change resolves a blocker, closes an item,
  or changes what's next.
- No new files in a category `NEXTSTEPS.md`'s "Explicitly out of scope"
  section marks as deliberately deferred (Dockerfile, `.claude/`
  agents/skills, `examples/`, NumPy or similar) without raising it first —
  those exclusions were deliberate, not oversights.

## Review

See [`CODEOWNERS`](CODEOWNERS) for who's expected to review which paths.
Note the practical caveat in `BRANCHING.md`: GitHub does not count a PR
author's own approval toward a required-review count, which matters for a
single-maintainer repository — read that section before assuming a required
review will work the way you expect.

## Other policies

- [`SECURITY.md`](SECURITY.md) — how to report a vulnerability.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — expected behavior.
- [`GOVERNANCE.md`](GOVERNANCE.md) — how decisions get made today.

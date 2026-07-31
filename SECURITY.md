# Security policy

## Supported versions

Nothing has been released yet — see [`README.md`](README.md)'s "What
exists today" table and [`CHANGELOG.md`](CHANGELOG.md). Until a first
version is published, only the tips of `main` and `dev` receive fixes;
there's no version-support matrix to publish because there's no version
yet.

## Reporting a vulnerability

Use GitHub's **private vulnerability reporting** — the "Report a
vulnerability" button under this repository's Security tab
(`github.com/ianshank/CHARTER.md/security/advisories/new`). It requires no
published email address and keeps the report private to maintainers until
a fix is ready, which is the right default for anything that isn't already
public.

Please include: what you found, the affected file(s) or behavior, and — if
you have one — a minimal reproduction. For this codebase specifically,
findings in `packages/core/src/charter_core/codec.py` (the YAML decode
path, deliberately hardened against anchors/aliases/duplicate keys) or in
provenance/integrity logic are the highest-value reports, since those are
exactly the surfaces a governance tool needs to be honest about.

## Response expectations

Single maintainer, best-effort, no SLA. This will be updated once that
changes.

## What's already checked mechanically

Some classes of issue are caught in CI before a human ever needs to look:
`gitleaks` (committed secrets) and `pip-audit` (known dependency
vulnerabilities) run on every push and pull request — see the `security`
job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml). A report
that reproduces something CI should have caught is still welcome; it means
the gate has a gap worth knowing about.

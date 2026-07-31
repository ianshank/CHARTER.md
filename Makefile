# Thin aliases over uv. CI runs the same commands, so a green `make all`
# locally means a green pipeline.
.PHONY: help sync lint types imports test cov schema drift deptry vulture audit secrets all

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'

sync:  ## Install the workspace and dev dependencies
	uv sync

lint:  ## Lint and format-check
	uv run ruff check .
	uv run ruff format --check .

types:  ## Type-check under mypy --strict
	uv run mypy

imports:  ## Enforce the core purity and layering contracts
	uv run lint-imports

test:  ## Run the test suite
	uv run pytest

cov:  ## Run the test suite with branch coverage (floor: pyproject.toml [tool.coverage.report])
	uv run pytest --cov=charter_core --cov=charter_cli --cov-report=term-missing

schema:  ## Regenerate the published JSON Schemas
	uv run python -c "from charter_core.schema_export import generate_all, serialise; \
	from pathlib import Path; \
	[Path(f'schema/{n}.schema.json').write_text(serialise(s), encoding='utf-8') for n, s in generate_all().items()]"

drift: schema  ## Fail if the committed schemas are stale
	git diff --exit-code -- schema/

deptry:  ## Unused/missing/transitive dependency check, per package
	cd packages/core && uv run --project ../.. deptry .
	cd packages/cli && uv run --project ../.. deptry .

vulture:  ## Dead-code check
	uv run vulture

audit:  ## Check the dependency tree for known vulnerabilities
	uv run pip-audit

secrets:  ## Scan for committed secrets (requires the gitleaks binary; not part of `all`)
	@command -v gitleaks >/dev/null 2>&1 || { \
		echo "gitleaks not found -- see https://github.com/gitleaks/gitleaks#installing"; exit 1; \
	}
	gitleaks detect --source . --no-git --redact -v

all: lint types imports cov drift deptry vulture audit  ## Everything CI runs

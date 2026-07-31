# Thin aliases over uv. CI runs the same commands, so a green `make all`
# locally means a green pipeline.
.PHONY: help sync lint types imports test cov schema drift all

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

cov:  ## Run the test suite with branch coverage
	uv run pytest --cov=charter_core --cov=charter_cli --cov-report=term-missing

schema:  ## Regenerate the published JSON Schemas
	uv run python -c "from charter_core.schema_export import generate_all, serialise; \
	from pathlib import Path; \
	[Path(f'schema/{n}.schema.json').write_text(serialise(s), encoding='utf-8') for n, s in generate_all().items()]"

drift: schema  ## Fail if the committed schemas are stale
	git diff --exit-code -- schema/

all: lint types imports cov drift  ## Everything CI runs

# Every target is a one-line wrapper around the `aipb` CLI, so on a machine without
# make you can run the same thing as `uv run aipb <command>`.
# Later phases add: filter extract dedupe verify explain publish site eval findings
# newsletter-preview newsletter-send
# Pick a company list with U=pilot (default) or U=sp100, e.g. `make ingest U=pilot`.

U ?= pilot

.PHONY: setup restore budget cost-report doctor smoke test lint fmt check-keys 	ingest parse prefilter stats packets import-labels

setup:
	uv sync
	uv run pre-commit install

restore:
	uv run aipb restore

budget:
	uv run aipb budget

cost-report:
	uv run aipb cost-report

doctor:
	uv run aipb doctor

smoke:
	uv run aipb smoke

ingest:
	uv run aipb ingest --universe $(U)

parse:
	uv run aipb parse --universe $(U)

prefilter:
	uv run aipb prefilter --universe $(U)

stats:
	uv run aipb stats --universe $(U)

packets:
	uv run aipb packets --universe $(U)

import-labels:
	uv run aipb import-labels

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

check-keys:
	git ls-files -z | xargs -0 uv run python scripts/check_secrets.py

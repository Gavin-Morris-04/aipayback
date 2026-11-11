# Every target is a one-line wrapper around the `aipb` CLI, so on a machine without
# make you can run the same thing as `uv run aipb <command>`.
# Pick a company list with U=pilot (default) or U=sp100, e.g. `make ingest U=pilot`.

U ?= pilot

.PHONY: setup restore budget cost-report doctor smoke test lint fmt check-keys 	ingest parse prefilter stats packets import-labels filter extract dedupe split eval 	compare verify explain gate status publish site status-packets import-statuses 	eval-status newsletter-preview newsletter-send findings

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

# Paid stages print a worst-case estimate first; anything over $0.50 needs CONFIRM=--confirm.
filter:
	uv run aipb filter --universe $(U) $(CONFIRM)

extract:
	uv run aipb extract --universe $(U) $(CONFIRM)

dedupe:
	uv run aipb dedupe

split:
	uv run aipb split --universe $(U)

eval:
	uv run aipb eval --universe $(U)

compare:
	uv run aipb compare

verify:
	uv run aipb verify --universe $(U) $(CONFIRM)

explain:
	uv run aipb explain --universe $(U) $(CONFIRM)

gate:
	uv run aipb gate

status:
	uv run aipb status

publish:
	uv run aipb publish

site:
	uv run aipb site

status-packets:
	uv run aipb status-packets

import-statuses:
	uv run aipb import-statuses

eval-status:
	uv run aipb eval-status

newsletter-preview:
	uv run aipb newsletter-preview

newsletter-send:
	uv run aipb newsletter-send

findings:
	uv run aipb findings

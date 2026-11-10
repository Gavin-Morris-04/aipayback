# Every target is a one-line wrapper around the `aipb` CLI, so on a machine without
# make you can run the same thing as `uv run aipb <command>`.
# Later phases add: ingest parse prefilter filter extract dedupe verify explain publish
# site eval findings packets import-labels newsletter-preview newsletter-send

.PHONY: setup restore budget cost-report doctor smoke test lint fmt check-keys

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

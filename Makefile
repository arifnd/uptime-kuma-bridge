.PHONY: install run lint format typecheck test cov check openapi

install:
	uv sync --extra dev

run:
	uv run uptime-kuma-bridge

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test:
	uv run pytest

cov:
	uv run pytest --cov=uptime_kuma_bridge --cov-report=term-missing

check: lint typecheck test

openapi:
	uv run python scripts/export_openapi.py

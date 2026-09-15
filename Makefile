.PHONY: install run test lint format typecheck check

install:
	cd backend && uv sync

run:
	cd backend && uv run uvicorn relaymaid.main:app --reload

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .

format:
	cd backend && uv run ruff format .

typecheck:
	cd backend && uv run mypy

check: lint typecheck test


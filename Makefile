.PHONY: spec4 install run dev test lint serve build

# One-command setup and launch for new users
spec4: install run

# Create .venv and install all dependencies into it
install:
	uv sync

run:
	@echo "Starting Flask..."
	@uv run python src/spec4/app.py

dev:
	DASH_DEBUG=true uv run python src/spec4/app.py

test:
	uv run pytest

lint:
	uv run ruff check src/ tests/

# Production: gunicorn must be installed separately (uv add gunicorn)
serve:
	uv run gunicorn 'spec4.app:server' --bind 0.0.0.0:8050 --workers 2 --threads 4

build:
	uv build

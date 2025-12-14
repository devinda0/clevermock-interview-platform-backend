# Makefile for Interview Assistant Backend

.PHONY: help install dev run agent test lint format clean freeze

# Default target
help:
	@echo "Available targets:"
	@echo "  install    - Install dependencies from requirements.txt"
	@echo "  dev        - Run FastAPI development server with hot reload"
	@echo "  run        - Run FastAPI server (production mode)"
	@echo "  agent      - Run LiveKit agent in dev mode"
	@echo "  test       - Run pytest tests"
	@echo "  lint       - Run linting checks"
	@echo "  format     - Format code with black and isort"
	@echo "  clean      - Remove cache and temporary files"
	@echo "  freeze     - Freeze current dependencies to requirements.txt"
	@echo "  venv       - Create virtual environment"

# Variables
PYTHON := python
PIP := pip
UVICORN := uvicorn
PORT := 3001

# Create virtual environment
venv:
	$(PYTHON) -m venv .venv
	@echo "Virtual environment created. Activate with: source .venv/bin/activate"

# Install dependencies
install:
	$(PIP) install -r requirements.txt

# Run development server with hot reload
dev:
	$(UVICORN) app.main:app --reload --port=$(PORT)

# Run production server
run:
	$(UVICORN) app.main:app --port=$(PORT)

# Run LiveKit agent in dev mode
agent:
	$(PYTHON) app/livekit/agent.py dev

# Download LiveKit model files
download-files:
	$(PYTHON) app/livekit/agent.py download-files

# Run tests
test:
	$(PYTHON) -m pytest -v

# Run specific test file
test-file:
	$(PYTHON) -m pytest -v $(FILE)

# Lint code
lint:
	$(PYTHON) -m flake8 app/
	$(PYTHON) -m mypy app/

# Format code
format:
	$(PYTHON) -m black app/
	$(PYTHON) -m isort app/

# Clean cache and temporary files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Freeze dependencies
freeze:
	$(PIP) freeze > requirements.txt

# Run with custom port
dev-port:
	$(UVICORN) app.main:app --reload --port=$(PORT)

# Run both server and agent (requires tmux or separate terminals)
all:
	@echo "Run 'make dev' in one terminal and 'make agent' in another"

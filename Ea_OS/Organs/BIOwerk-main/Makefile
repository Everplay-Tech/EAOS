.PHONY: help install install-dev clean lint format type-check test test-cov test-unit test-integration test-e2e security pre-commit check-all run docker-up docker-down

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
BLACK := $(PYTHON) -m black
ISORT := $(PYTHON) -m isort
FLAKE8 := $(PYTHON) -m flake8
PYLINT := $(PYTHON) -m pylint
MYPY := $(PYTHON) -m mypy
BANDIT := $(PYTHON) -m bandit
SAFETY := $(PYTHON) -m safety
PRE_COMMIT := pre-commit

# Directories
SRC_DIRS := matrix services mesh
TEST_DIR := tests

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt

install-dev: ## Install development dependencies
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements-dev.txt
	$(PRE_COMMIT) install
	@echo "Development environment setup complete!"

clean: ## Clean build artifacts and cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ .coverage htmlcov/ .tox/
	@echo "Cleaned build artifacts and cache files"

format: ## Format code with black and isort
	@echo "Formatting code with black..."
	$(BLACK) $(SRC_DIRS) $(TEST_DIR)
	@echo "Sorting imports with isort..."
	$(ISORT) $(SRC_DIRS) $(TEST_DIR)
	@echo "Code formatting complete!"

lint: ## Run linters (flake8 and pylint)
	@echo "Running flake8..."
	$(FLAKE8) $(SRC_DIRS)
	@echo "Running pylint..."
	$(PYLINT) $(SRC_DIRS)
	@echo "Linting complete!"

type-check: ## Run type checking with mypy
	@echo "Running mypy type checker..."
	$(MYPY) $(SRC_DIRS)
	@echo "Type checking complete!"

security: ## Run security checks (bandit and safety)
	@echo "Running bandit security linter..."
	$(BANDIT) -r $(SRC_DIRS) -ll --skip B101
	@echo "Running safety dependency checker..."
	$(SAFETY) check --json || true
	@echo "Security checks complete!"

test: ## Run all tests
	$(PYTEST) $(TEST_DIR) -v

test-cov: ## Run tests with coverage report
	$(PYTEST) $(TEST_DIR) -v --cov=matrix --cov=services --cov-report=term-missing --cov-report=html

test-unit: ## Run unit tests only
	$(PYTEST) $(TEST_DIR) -v -m "not integration and not e2e"

test-integration: ## Run integration tests only
	$(PYTEST) $(TEST_DIR) -v -m "integration"

test-e2e: ## Run end-to-end tests only
	$(PYTEST) tests/e2e -v

test-fast: ## Run tests in parallel (fast)
	$(PYTEST) $(TEST_DIR) -v -n auto

pre-commit: ## Run pre-commit hooks on all files
	$(PRE_COMMIT) run --all-files

pre-commit-update: ## Update pre-commit hooks
	$(PRE_COMMIT) autoupdate

check-all: format lint type-check security test-cov ## Run all checks (format, lint, type-check, security, tests)
	@echo ""
	@echo "=========================================="
	@echo "All checks passed successfully!"
	@echo "=========================================="

docker-up: ## Start all services with docker-compose
	docker-compose up -d

docker-down: ## Stop all services with docker-compose
	docker-compose down

docker-logs: ## Show logs from all docker containers
	docker-compose logs -f

docker-rebuild: ## Rebuild and restart all docker containers
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d

run-mesh: ## Run the mesh service
	cd mesh && uvicorn main:app --reload --host 0.0.0.0 --port 8000

run-service: ## Run a specific service (usage: make run-service SERVICE=synapse)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make run-service SERVICE=synapse"; \
		exit 1; \
	fi
	cd services/$(SERVICE) && uvicorn main:app --reload --host 0.0.0.0 --port 8000

migrations-create: ## Create a new migration (usage: make migrations-create MSG="description")
	@if [ -z "$(MSG)" ]; then \
		echo "Error: MSG parameter is required. Usage: make migrations-create MSG='add users table'"; \
		exit 1; \
	fi
	alembic revision --autogenerate -m "$(MSG)"

migrations-upgrade: ## Apply all pending migrations
	alembic upgrade head

migrations-downgrade: ## Rollback one migration
	alembic downgrade -1

migrations-history: ## Show migration history
	alembic history

dev-setup: install-dev ## Complete development environment setup
	@echo ""
	@echo "=========================================="
	@echo "Development environment ready!"
	@echo "=========================================="
	@echo "Next steps:"
	@echo "  1. Copy .env.example to .env and configure"
	@echo "  2. Run 'make docker-up' to start services"
	@echo "  3. Run 'make test' to verify setup"
	@echo "=========================================="

ci-check: ## Run CI checks (format check, lint, type-check, security, tests)
	@echo "Checking code formatting..."
	$(BLACK) --check $(SRC_DIRS) $(TEST_DIR)
	$(ISORT) --check-only $(SRC_DIRS) $(TEST_DIR)
	@echo "Running linters..."
	$(FLAKE8) $(SRC_DIRS)
	$(PYLINT) $(SRC_DIRS)
	@echo "Running type checker..."
	$(MYPY) $(SRC_DIRS)
	@echo "Running security checks..."
	$(BANDIT) -r $(SRC_DIRS) -ll --skip B101
	@echo "Running tests with coverage..."
	$(PYTEST) $(TEST_DIR) -v --cov=matrix --cov=services --cov-report=xml
	@echo "CI checks complete!"

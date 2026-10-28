.PHONY: help bootstrap install install-dev lock test test-cov test-unit lint lint-fix format typecheck pre-commit audit-deps smoke clean build audit audit-debug ci all docker-build docker-run docker-shell docker-compose-up docker-compose-down docker-clean

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

bootstrap:  ## One-time setup: venv with all extras, Playwright Chromium, git hooks
	uv sync --extra dev --extra saas --extra undetected
	uv run playwright install chromium
	uv run pre-commit install

install:  ## Runtime dependencies only
	uv sync

install-dev:  ## Dev and saas extras
	uv sync --extra dev --extra saas

lock:  ## Re-resolve uv.lock after editing pyproject.toml
	uv lock

test:  ## Run tests
	uv run pytest tests/

test-cov:  ## Run tests with coverage report (terminal and htmlcov/)
	uv run pytest tests/ --cov --cov-report=term-missing --cov-report=html

test-unit:  ## Run only tests marked @pytest.mark.unit
	uv run pytest tests/ -m unit

lint:  ## Run linters
	uv run ruff check src/ tests/
	uv run black --check src/ tests/

lint-fix:  ## Run linters and fix issues
	uv run ruff check --fix src/ tests/
	uv run black src/ tests/

format:  ## Format code
	uv run black src/ tests/

typecheck:  ## Run type checker
	uv run mypy src/

pre-commit:  ## Run pre-commit hooks
	uv run pre-commit run --all-files

audit-deps:  ## pip-audit against the locked dependency set (same as CI)
	uv export --format requirements-txt --all-extras --no-emit-project --no-hashes -o .requirements-audit.txt
	uvx --python 3.12 pip-audit --no-deps --strict --desc on -r .requirements-audit.txt; status=$$?; rm -f .requirements-audit.txt; exit $$status

smoke:  ## Three-query live run against nike (needs OPENROUTER_API_KEY or OPENAI_API_KEY)
	uv run search-audit --site nike --max-queries 3 --output runs/smoke

clean:  ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf .coverage htmlcov/ .requirements-audit.txt
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:  ## Build package
	uv build

audit:  ## Run audit on Nike.com (example)
	uv run search-audit --site nike --log-level INFO

audit-debug:  ## Run audit with debug logging
	uv run search-audit --site nike --log-level DEBUG --no-headless

ci:  ## Run CI checks locally
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test-cov
	$(MAKE) audit-deps

all: clean install-dev lint typecheck test-cov  ## Run all checks

# Docker targets
DOCKER_IMAGE = agentic-search-audit
DOCKER_TAG = latest

docker-build:  ## Build Docker image
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

docker-run:  ## Run audit in Docker (use ARGS="--url https://example.com --queries queries.json")
	docker run --rm -it \
		--shm-size=2g \
		-v $(PWD)/runs:/app/runs \
		-v $(PWD)/configs:/app/configs:ro \
		-v $(PWD)/data/queries:/app/data/queries:ro \
		-e OPENROUTER_API_KEY=$(OPENROUTER_API_KEY) \
		-e OPENAI_API_KEY=$(OPENAI_API_KEY) \
		-e ANTHROPIC_API_KEY=$(ANTHROPIC_API_KEY) \
		$(DOCKER_IMAGE):$(DOCKER_TAG) $(ARGS)

docker-shell:  ## Open shell in Docker container
	docker run --rm -it \
		--shm-size=2g \
		-v $(PWD)/runs:/app/runs \
		-v $(PWD)/configs:/app/configs:ro \
		-v $(PWD)/data/queries:/app/data/queries:ro \
		--entrypoint /bin/bash \
		$(DOCKER_IMAGE):$(DOCKER_TAG)

docker-compose-up:  ## Start services with docker-compose
	docker-compose up -d

docker-compose-down:  ## Stop services with docker-compose
	docker-compose down

docker-clean:  ## Remove Docker images and containers
	docker-compose down --rmi local -v
	docker rmi $(DOCKER_IMAGE):$(DOCKER_TAG) || true

.PHONY: help install install-dev test test-cov lint format clean build docker-build docker-run docker-shell

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install package
	pip install -e .

install-dev:  ## Install package with dev dependencies
	pip install -e ".[dev]"

test:  ## Run tests
	pytest tests/ -v

test-cov:  ## Run tests with coverage report
	pytest tests/ --cov=agentic_search_audit --cov-report=term --cov-report=html -v

test-unit:  ## Run only unit tests
	pytest tests/ -v -m unit

test-watch:  ## Run tests in watch mode
	pytest-watch tests/ -v

lint:  ## Run linters
	ruff check src/ tests/
	black --check src/ tests/

lint-fix:  ## Run linters and fix issues
	ruff check --fix src/ tests/
	black src/ tests/

format:  ## Format code
	black src/ tests/

typecheck:  ## Run type checker
	mypy src/

pre-commit:  ## Run pre-commit hooks
	pre-commit run --all-files

clean:  ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:  ## Build package
	python -m build

audit:  ## Run audit on Nike.com (example)
	search-audit --site nike --log-level INFO

audit-debug:  ## Run audit with debug logging
	search-audit --site nike --log-level DEBUG --no-headless

smoke-test:  ## Run smoke test
	./scripts/smoke.sh

ci:  ## Run CI checks locally
	make lint
	make typecheck
	make test-cov

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

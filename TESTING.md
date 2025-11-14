# Testing Guide

This document describes how to run tests and the testing strategy for the Agentic Search Audit project.

## Quick Start

```bash
# Install with dev dependencies
make install-dev

# Run all tests
make test

# Run tests with coverage
make test-cov

# Run only unit tests
make test-unit

# Run linters
make lint

# Run type checker
make typecheck

# Run all CI checks locally
make ci
```

## Test Organization

Tests are organized by module:

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_types.py            # Core type definitions
├── test_config.py           # Configuration loading
├── test_judge.py            # LLM judge and rubric
├── test_extractors.py       # DOM extractors
├── test_report.py           # Report generation
└── test_cli.py              # CLI interface
```

## Test Markers

We use pytest markers to categorize tests:

- `@pytest.mark.unit` - Fast unit tests (no external dependencies)
- `@pytest.mark.integration` - Integration tests (may require external services)
- `@pytest.mark.slow` - Slow tests that take significant time

### Running Specific Test Categories

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

## Coverage

Current test coverage: **46%**

High coverage modules:
- `core/types.py` - 100%
- `report/generator.py` - 97%
- `judge/rubric.py` - 100%

Lower coverage modules (require integration testing):
- `mcp/client.py` - 26% (browser automation)
- `extractors/*` - 17-21% (DOM extraction)
- `core/orchestrator.py` - 22% (end-to-end flow)

### Viewing Coverage Report

```bash
# Generate HTML coverage report
make test-cov

# Open in browser
open htmlcov/index.html
```

## Writing Tests

### Unit Test Example

```python
import pytest
from agentic_search_audit.core.types import Query, QueryOrigin

@pytest.mark.unit
def test_query_creation():
    """Test Query model."""
    query = Query(
        id="q001",
        text="running shoes",
        lang="en",
        origin=QueryOrigin.PREDEFINED,
    )

    assert query.id == "q001"
    assert query.text == "running shoes"
```

### Using Fixtures

```python
import pytest

@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "site": {"url": "https://example.com"},
        "run": {"top_k": 10},
    }

@pytest.mark.unit
def test_with_fixture(sample_config):
    """Test using a fixture."""
    assert sample_config["run"]["top_k"] == 10
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await some_async_function()
    assert result is not None
```

## Continuous Integration

We use GitHub Actions for CI/CD:

- **Lint**: Black formatting + Ruff linting + mypy type checking
- **Test**: Run on Python 3.10, 3.11, 3.12, 3.13
- **Package**: Build and verify package installation
- **Security**: Safety + Bandit checks

### CI Configuration

See `.github/workflows/ci.yml` for the complete CI pipeline.

### Running CI Locally

```bash
# Run all CI checks
make ci

# Or run individual checks
make lint
make typecheck
make test-cov
```

## Pre-commit Hooks

We use pre-commit to run checks before commits:

```bash
# Install hooks
pre-commit install

# Run manually
make pre-commit
```

Hooks include:
- Trailing whitespace removal
- End of file fixer
- YAML/JSON/TOML validation
- Black formatting
- Ruff linting
- mypy type checking

## Test Configuration

Test configuration is in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = ["-v", "--strict-markers", "--strict-config", "--tb=short"]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "slow: Slow tests that may take a while",
]
```

## Debugging Tests

### Run Single Test

```bash
# Run specific test file
pytest tests/test_types.py -v

# Run specific test function
pytest tests/test_types.py::test_query_creation -v

# Run with debug output
pytest tests/test_types.py -vv -s
```

### Show Print Statements

```bash
# Disable output capture
pytest tests/ -s

# Show local variables on failure
pytest tests/ -l
```

### Drop into Debugger on Failure

```bash
# Use pdb
pytest tests/ --pdb

# Use ipdb (if installed)
pytest tests/ --pdb --pdbcls=IPython.terminal.debugger:Pdb
```

## Testing Best Practices

1. **Keep tests fast**: Unit tests should run in milliseconds
2. **Use fixtures**: Share common setup with pytest fixtures
3. **Test edge cases**: Don't just test the happy path
4. **Descriptive names**: Test names should describe what they test
5. **One assertion per test**: Keep tests focused
6. **Mock external services**: Don't depend on external APIs in unit tests
7. **Use markers**: Tag tests appropriately (unit, integration, slow)

## Common Issues

### Import Errors

If you get import errors, make sure the package is installed:

```bash
pip install -e ".[dev]"
```

### Environment Variables

Tests mock the `OPENAI_API_KEY` automatically via `conftest.py`. For integration tests that actually call the API, set it in `.env`:

```bash
echo "OPENAI_API_KEY=your-key" > .env
```

### Cache Issues

If tests behave unexpectedly, clear the cache:

```bash
pytest --cache-clear
```

## Future Test Improvements

- [ ] Add integration tests for browser automation
- [ ] Add end-to-end tests with mocked LLM responses
- [ ] Increase coverage to 80%+
- [ ] Add property-based testing with Hypothesis
- [ ] Add performance benchmarks
- [ ] Add mutation testing

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)

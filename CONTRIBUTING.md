# Contributing to Agentic Search Audit

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/MysterionRise/agentic-search-audit.git
cd agentic-search-audit
```

2. Install everything with uv (dev, saas and undetected extras, Playwright Chromium, git hooks):
```bash
make bootstrap
```
   Without uv: `pip install -e ".[dev]"` and `playwright install chromium`.

3. Dependencies and tool versions live in `pyproject.toml` only. After editing them run
   `uv lock` and commit `uv.lock`; the pre-commit hooks, the Makefile and CI run the pinned
   black, ruff and mypy through `uv run`.

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your API keys
```

## Code Style

This project uses:
- **Black** for code formatting (100 char line length)
- **Ruff** for linting
- **Mypy** for type checking

Run all checks:
```bash
make format       # black
make lint         # ruff and black --check
make typecheck    # mypy src/
```

## Running Tests

```bash
make test                                  # uv run pytest tests/
make test-cov                              # with coverage
uv run pytest tests/test_config.py         # one file
uv run pytest tests/integration -m browser # needs Playwright Chromium
```

## Making Changes

1. Create a new branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and add tests

3. Run tests and linters:
```bash
make ci
```

4. Commit your changes:
```bash
git add .
git commit -m "feat: add your feature description"
```

We follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test changes
- `refactor:` - Code refactoring
- `chore:` - Build/tooling changes

5. Push and create a pull request:
```bash
git push origin feature/your-feature-name
```

## Pull Request Process

1. Ensure all tests pass and code is formatted
2. Update documentation if needed
3. Add tests for new functionality
4. Describe your changes in the PR description
5. Link any related issues

## Project Structure

```
agentic-search-audit/
├── src/agentic_search_audit/    # Main package
│   ├── core/                     # Core types and orchestration
│   ├── browser/                  # backends, bridge/, session, stealth
│   ├── analysis/                 # maturity, benchmarks, findings
│   ├── generators/               # LLM-generated queries
│   ├── extractors/               # DOM extraction logic
│   ├── judge/                    # LLM judge implementation
│   ├── report/                   # Report generation
│   └── cli/                      # CLI interface
├── configs/                      # Configuration files
├── data/queries/                # Predefined query sets
├── tests/                       # Unit tests
└── scripts/                     # Helper scripts
```

## Adding New Features

### Adding a New Site Configuration

1. Create a new config file in `configs/sites/{site}.yaml`
2. Add site-specific selectors and overrides
3. Create a query set in `data/queries/{site}.json`
4. Test with: `search-audit --site {site}`

### Adding a New LLM Provider

1. Add provider to `LLMConfig.provider` enum in `core/types.py`
2. Implement provider in `judge/judge.py`
3. Add environment variable for API key
4. Update documentation

### Adding New Report Formats

1. Add format to `ReportConfig.formats` in `core/types.py`
2. Implement generation method in `report/generator.py`
3. Add tests
4. Update documentation

## Code Review Checklist

- [ ] Tests added and passing
- [ ] Code formatted with Black
- [ ] No linting errors (Ruff)
- [ ] Type hints added (Mypy passes)
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (for significant changes)
- [ ] Commit messages follow conventions

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

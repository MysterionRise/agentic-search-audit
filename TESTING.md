# Testing

## Commands

```bash
make test                     # uv run pytest tests/
make test-cov                 # with coverage (terminal and htmlcov/)
uv run pytest tests/test_config.py
uv run pytest tests/ -m unit
uv run pytest tests/ -m "not browser and not integration"   # exactly what CI runs
uv run pytest tests/integration -m browser                  # needs Playwright Chromium
ASA_BRIDGE_INTEGRATION=1 ASA_BRIDGE_MODE=launch ASA_BRIDGE_HEADLESS=1 \
  uv run pytest -m integration tests/integration/test_bridge_real_browser.py
make lint && make typecheck   # ruff, black --check, mypy src/
make ci                       # lint, typecheck, test-cov, pip-audit
```

## Layout and markers

`tests/` holds one module per source module (`test_<module>.py`), `tests/api/` the SaaS
tests, `tests/integration/` the ones that need a browser, `tests/fakes/` shared fakes
(`FakeTransport` for the bridge client). `asyncio_mode = "auto"` and `filterwarnings =
error` are set in `pyproject.toml`.

| Marker | Meaning | In CI |
|---|---|---|
| `unit` | fast, no I/O; most tests carry it | yes |
| `browser` | launches Playwright's Chromium (`test_evaluate_chromium.py`, `test_extractors_snapshot.py`); skips when the binary is missing | no (deselected) |
| `integration` | opt-in runs against external systems, gated by environment variables | no |

SaaS tests (`tests/api/`, `test_repositories.py`, `test_api_deps.py`, `test_alembic_heads.py`)
use `pytest.importorskip` and skip unless the `saas` extra is installed; CI installs it on
Python 3.12 only.

## Conventions

- Mock the browser at the `BrowserClient` boundary with `AsyncMock`, and return the values
  JavaScript would produce (`True`, `7`, `{"found": True}`), never strings like `"true"`.
  `tests/test_evaluate_contract.py` enforces the contract on every backend.
- Inject the client into the orchestrator (`SearchAuditOrchestrator(..., client=fake)`)
  instead of patching `create_browser_client`.
- Bridge transports are tested against fakes: a `FakeMcpSession` for chrome-devtools-mcp
  and an in-process aiohttp daemon for Kimi WebBridge. Real browsers are reached only
  through the `browser` and `integration` markers.
- Keep tests deterministic: patch `asyncio.sleep` where the code waits, and set
  `throttle_rps=0` on test configs.

## CI

`.github/workflows/ci.yml`, all jobs through uv with `UV_LOCKED=1`:

| Job | Does |
|---|---|
| Lint and Format Check | black, ruff, mypy on Python 3.12 |
| Test Python 3.10 / 3.11 / 3.12 / 3.13 | `pytest tests/ -m "not browser and not integration"` with coverage; the `saas` extra only on 3.12 |
| Test Package Installation | builds the wheel, installs it into a clean venv, runs `search-audit --help`, checks `search-audit-api` fails without the extra |
| Security Checks | `pip-audit` against the exported lock, bandit on `src/` |

The job names are required checks on `main`. Dependabot keeps uv, GitHub Actions,
pre-commit and Docker dependencies current (`.github/dependabot.yml`).

## Pre-commit

`make bootstrap` installs the hooks; `uv run pre-commit run --all-files` runs them. The
Python hooks are local and run the versions pinned in `pyproject.toml`.

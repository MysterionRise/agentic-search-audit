"""Tests for the orchestrator's per-query retry loop, recovery and failure records."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from agentic_search_audit.browser.challenge_detector import (
    ChallengeDetectedError,
    ChallengeDetection,
)
from agentic_search_audit.browser.errors import BrowserErrorKind
from agentic_search_audit.core.errors import QuerySubmitError
from agentic_search_audit.core.orchestrator import CapturedQuery, SearchAuditOrchestrator
from agentic_search_audit.core.types import (
    AuditConfig,
    AuditRecord,
    PageArtifacts,
    ProxyRotationStrategy,
    Query,
    QueryOrigin,
    RunConfig,
    SearchConfig,
    SiteConfig,
)
from tests.helpers import make_fqi_judge_score

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(search_url_template: str | None = None, **run_overrides: Any) -> AuditConfig:
    """Create a minimal AuditConfig for testing."""
    run_kwargs: dict[str, Any] = {
        "headless": True,
        "throttle_rps": 0,  # disable rate limiting for fast tests
        "retry_backoff_base": 0.01,
    }
    run_kwargs.update(run_overrides)
    return AuditConfig(
        site=SiteConfig(
            url="https://example.com",  # type: ignore[arg-type]
            search=SearchConfig(search_url_template=search_url_template),
        ),
        run=RunConfig(**run_kwargs),
    )


def _make_query(text: str = "test query", qid: str = "q001") -> Query:
    return Query(id=qid, text=text, lang="en", origin=QueryOrigin.PREDEFINED)


def _artifacts() -> PageArtifacts:
    return PageArtifacts(
        url="https://example.com",
        final_url="https://example.com/search",
        html_path="test.html",
        screenshot_path="test.png",
        ts=datetime.now(),
    )


def _captured(query: Query) -> CapturedQuery:
    return CapturedQuery(
        query=query, items=[], page=_artifacts(), html="<html/>", url="https://example.com/s"
    )


def _record(query: Query) -> AuditRecord:
    return AuditRecord(
        site="https://example.com",
        query=query,
        items=[],
        page=_artifacts(),
        judge=make_fqi_judge_score(),
    )


def _challenge() -> ChallengeDetectedError:
    return ChallengeDetectedError(
        ChallengeDetection(detected=True, challenge_type="cloudflare", message="Just a moment")
    )


class MockBrowserClient:
    """Mock BrowserClient with call counters (no ``capabilities``: treated as all-capable)."""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.recover_page_calls = 0
        self.reconnect_calls = 0
        self.navigate_calls = 0
        self.set_user_agent_calls = 0
        self.set_proxy_calls = 0
        self.clear_cookies_calls = 0
        self._page_alive = True
        self._browser_alive = True

    async def connect(self) -> None:
        self.connect_calls += 1

    async def disconnect(self) -> None:
        self.disconnect_calls += 1

    async def __aenter__(self) -> "MockBrowserClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    async def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        self.navigate_calls += 1
        return url

    async def query_selector(self, selector: str) -> dict[str, Any] | None:
        return {"exists": True}

    async def query_selector_all(self, selector: str) -> list[dict[str, Any]]:
        return []

    async def evaluate(self, expression: str) -> Any:
        return "https://example.com/search?q=test"

    async def click(self, selector: str) -> None:
        pass

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        pass

    async def press_key(self, key: str) -> None:
        pass

    async def screenshot(self, output_path: Path, full_page: bool = True) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake png")
        return output_path

    async def get_html(self) -> str:
        return "<html><body>results</body></html>"

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, visible: bool = True
    ) -> bool:
        return True

    async def wait_for_network_idle(self, timeout: int = 2000) -> None:
        pass

    async def get_element_text(self, selector: str) -> str | None:
        return None

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        return None

    def is_page_alive(self) -> bool:
        return self._page_alive

    async def recover_page(self) -> None:
        self.recover_page_calls += 1
        self._page_alive = True

    def is_browser_alive(self) -> bool:
        return self._browser_alive

    async def reconnect(self) -> None:
        self.reconnect_calls += 1
        self._page_alive = True
        self._browser_alive = True

    async def set_user_agent(self, ua: str) -> None:
        self.set_user_agent_calls += 1

    async def set_proxy(self, proxy_url: str) -> None:
        self.set_proxy_calls += 1

    async def clear_cookies(self) -> None:
        self.clear_cookies_calls += 1


def _make_orchestrator(
    config: AuditConfig,
    queries: list[Query],
    tmp_path: Path,
    mock_client: MockBrowserClient,
) -> SearchAuditOrchestrator:
    """Orchestrator with the mock client injected and components built (judge mocked)."""
    orch = SearchAuditOrchestrator(config, queries, tmp_path, client=mock_client)  # type: ignore[arg-type]
    with patch("agentic_search_audit.core.orchestrator.SearchQualityJudge"):
        orch._init_components()
    return orch


def _stub_query_pipeline(
    orch: SearchAuditOrchestrator,
    query: Query,
    capture_effects: list[Any],
    judge_effects: list[Any] | None = None,
    navigate_effects: list[Any] | None = None,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Replace capture, judge and navigation with scripted fakes."""
    capture = AsyncMock(side_effect=capture_effects)
    judge = AsyncMock(side_effect=judge_effects or [_record(query)] * 5)
    navigate = AsyncMock(side_effect=navigate_effects or [None] * 10)
    orch._capture_query = capture  # type: ignore[method-assign]
    orch._judge_query = judge  # type: ignore[method-assign]
    orch._navigate_to_site = navigate  # type: ignore[method-assign]
    return capture, judge, navigate


# ---------------------------------------------------------------------------
# Construction and injection
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_client_and_factory_are_exclusive(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            SearchAuditOrchestrator(
                _make_config(), [], tmp_path, client=MockBrowserClient(), client_factory=MagicMock()  # type: ignore[arg-type]
            )

    def test_factory_builds_the_client(self, tmp_path: Path) -> None:
        mock_client = MockBrowserClient()
        factory = MagicMock(return_value=mock_client)
        config = _make_config()
        orch = SearchAuditOrchestrator(config, [], tmp_path, client_factory=factory)
        with patch("agentic_search_audit.core.orchestrator.SearchQualityJudge"):
            orch._init_components()
        factory.assert_called_once_with(config.run, "en-US")
        assert orch.client is mock_client

    def test_default_factory_is_create_browser_client(self, tmp_path: Path) -> None:
        mock_client = MockBrowserClient()
        orch = SearchAuditOrchestrator(_make_config(), [], tmp_path)
        with (
            patch(
                "agentic_search_audit.core.orchestrator.create_browser_client",
                return_value=mock_client,
            ) as factory,
            patch("agentic_search_audit.core.orchestrator.SearchQualityJudge"),
        ):
            orch._init_components()
        factory.assert_called_once()
        assert orch.client is mock_client

    def test_injected_client_is_kept(self, tmp_path: Path) -> None:
        mock_client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(), [], tmp_path, mock_client)
        assert orch.client is mock_client
        assert orch.session.client is mock_client


# ---------------------------------------------------------------------------
# Retry loop
# ---------------------------------------------------------------------------


class TestRetryLoop:
    async def test_success_on_first_attempt(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(), [query], tmp_path, client)
        capture, judge, navigate = _stub_query_pipeline(orch, query, [_captured(query)])

        record = await orch._run_query_with_retries(query, 1)

        assert record is not None and record.query.id == query.id
        assert capture.await_count == 1 and judge.await_count == 1
        assert navigate.await_count == 1
        assert orch.failures == []

    async def test_challenge_on_navigation_is_retried(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(max_retries=2), [query], tmp_path, client)
        capture, _, navigate = _stub_query_pipeline(
            orch, query, [_captured(query)], navigate_effects=[_challenge(), None]
        )

        record = await orch._run_query_with_retries(query, 1)

        assert record is not None
        assert navigate.await_count == 2
        assert capture.await_count == 1
        assert client.clear_cookies_calls == 1  # challenge recovery on a disposable profile
        assert orch.failures == []

    async def test_recovery_errors_do_not_escape(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(max_retries=1), [query], tmp_path, client)
        _stub_query_pipeline(
            orch, query, [PlaywrightTimeoutError("Timeout 30000ms exceeded"), _captured(query)]
        )
        orch.session.recover = AsyncMock(side_effect=RuntimeError("recovery exploded"))  # type: ignore[method-assign]

        record = await orch._run_query_with_retries(query, 1)

        assert record is not None
        assert orch.failures == []

    async def test_submit_error_is_retried(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(max_retries=1), [query], tmp_path, client)
        capture, _, navigate = _stub_query_pipeline(
            orch, query, [QuerySubmitError("no search box"), _captured(query)]
        )

        record = await orch._run_query_with_retries(query, 1)

        assert record is not None
        assert capture.await_count == 2
        assert navigate.await_count == 2

    async def test_timeout_budget_is_retried_with_page_recovery(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(
            _make_config(max_retries=1, query_timeout_s=0.05), [query], tmp_path, client
        )

        calls = 0

        async def slow_then_ok(q: Query) -> CapturedQuery:
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(1)
            return _captured(q)

        orch._capture_query = slow_then_ok  # type: ignore[method-assign]
        orch._judge_query = AsyncMock(return_value=_record(query))  # type: ignore[method-assign]
        orch._navigate_to_site = AsyncMock()  # type: ignore[method-assign]

        record = await orch._run_query_with_retries(query, 1)

        assert record is not None
        assert calls == 2
        assert client.recover_page_calls >= 1

    async def test_exhausted_retries_record_a_failure(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(max_retries=1), [query], tmp_path, client)
        capture, _, _ = _stub_query_pipeline(orch, query, [PlaywrightTimeoutError("Timeout")] * 2)

        record = await orch._run_query_with_retries(query, 1)

        assert record is None
        assert capture.await_count == 2
        assert [f.error_kind for f in orch.failures] == ["timeout"]
        assert orch.failures[0].attempts == 2
        lines = (tmp_path / "failures.jsonl").read_text().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["error_kind"] == "timeout"
        assert not (tmp_path / "audit.jsonl").exists()
        assert orch._load_checkpoint() == set()  # a failed query is retried on resume

    async def test_judge_failure_is_not_retried(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(max_retries=2), [query], tmp_path, client)
        capture, _, _ = _stub_query_pipeline(
            orch, query, [_captured(query)] * 3, judge_effects=[RuntimeError("LLM down")]
        )

        record = await orch._run_query_with_retries(query, 1)

        assert record is None
        assert capture.await_count == 1
        assert [f.error_kind for f in orch.failures] == ["judge"]

    async def test_permanent_error_is_not_retried(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(max_retries=2), [query], tmp_path, client)
        capture, _, _ = _stub_query_pipeline(
            orch, query, [PlaywrightError("Element is not an input")] * 3
        )

        record = await orch._run_query_with_retries(query, 1)

        assert record is None
        assert capture.await_count == 1
        assert client.recover_page_calls == 0 and client.reconnect_calls == 0
        assert orch.failures[0].error_kind == "permanent"

    async def test_rate_limit_applies_on_retry(self, tmp_path: Path) -> None:
        query = _make_query()
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(max_retries=1), [query], tmp_path, client)
        _stub_query_pipeline(orch, query, [PlaywrightTimeoutError("Timeout"), _captured(query)])
        rate_limit = AsyncMock()
        orch._rate_limit = rate_limit  # type: ignore[method-assign]

        await orch._run_query_with_retries(query, 1)

        assert rate_limit.await_count == 1  # first query, second attempt only

    async def test_template_site_loads_the_homepage_once(self, tmp_path: Path) -> None:
        queries = [_make_query("a", "q1"), _make_query("b", "q2")]
        client = MockBrowserClient()
        config = _make_config(search_url_template="https://example.com/s?q={query}")
        orch = _make_orchestrator(config, queries, tmp_path, client)
        _, _, navigate = _stub_query_pipeline(orch, queries[0], [_captured(q) for q in queries])

        for index, query in enumerate(queries, 1):
            assert await orch._run_query_with_retries(query, index) is not None

        assert navigate.await_count == 1

    async def test_search_box_site_loads_the_homepage_per_query(self, tmp_path: Path) -> None:
        queries = [_make_query("a", "q1"), _make_query("b", "q2")]
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(), queries, tmp_path, client)
        _, _, navigate = _stub_query_pipeline(orch, queries[0], [_captured(q) for q in queries])

        for index, query in enumerate(queries, 1):
            await orch._run_query_with_retries(query, index)

        assert navigate.await_count == 2

    async def test_per_query_ua_rotation_rotates_and_reloads(self, tmp_path: Path) -> None:
        queries = [_make_query("a", "q1"), _make_query("b", "q2")]
        client = MockBrowserClient()
        config = _make_config(
            search_url_template="https://example.com/s?q={query}",
            ua_rotation_strategy=ProxyRotationStrategy.PER_QUERY,
        )
        orch = _make_orchestrator(config, queries, tmp_path, client)
        _, _, navigate = _stub_query_pipeline(orch, queries[0], [_captured(q) for q in queries])

        for index, query in enumerate(queries, 1):
            await orch._run_query_with_retries(query, index)

        assert client.set_user_agent_calls == 2
        assert navigate.await_count == 2


# ---------------------------------------------------------------------------
# Recovery through the session
# ---------------------------------------------------------------------------


class TestSessionRecovery:
    async def test_reconnects_on_browser_dead(self, tmp_path: Path) -> None:
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(), [], tmp_path, client)
        await orch.session.recover(BrowserErrorKind.BROWSER_DEAD)
        assert client.reconnect_calls == 1

    async def test_reconnects_when_browser_not_alive_on_page_closed(self, tmp_path: Path) -> None:
        client = MockBrowserClient()
        client._browser_alive = False
        orch = _make_orchestrator(_make_config(), [], tmp_path, client)
        await orch.session.recover(BrowserErrorKind.PAGE_CLOSED)
        assert client.reconnect_calls == 1
        assert client.recover_page_calls == 0

    async def test_recovers_page_when_browser_alive_on_page_closed(self, tmp_path: Path) -> None:
        client = MockBrowserClient()
        orch = _make_orchestrator(_make_config(), [], tmp_path, client)
        await orch.session.recover(BrowserErrorKind.PAGE_CLOSED)
        assert client.recover_page_calls == 1
        assert client.reconnect_calls == 0


# ---------------------------------------------------------------------------
# Artifact safety
# ---------------------------------------------------------------------------


class TestOrchestratorArtifactSafety:
    """Artifact capture failures must not fail the query."""

    async def test_screenshot_failure_returns_artifacts(self, tmp_path: Path) -> None:
        mock_client = MockBrowserClient()

        async def failing_screenshot(output_path: Path, full_page: bool = True) -> Path:
            raise PlaywrightError("Page has been closed")

        mock_client.screenshot = failing_screenshot  # type: ignore[method-assign]
        orch = _make_orchestrator(_make_config(), [], tmp_path, mock_client)

        artifacts = await orch._capture_artifacts(_make_query())

        assert artifacts.url == "https://example.com/"
        assert artifacts.html_path

    async def test_html_failure_returns_artifacts(self, tmp_path: Path) -> None:
        mock_client = MockBrowserClient()

        async def failing_html() -> str:
            raise PlaywrightError("Page has been closed")

        mock_client.get_html = failing_html  # type: ignore[method-assign]
        orch = _make_orchestrator(_make_config(), [], tmp_path, mock_client)

        artifacts = await orch._capture_artifacts(_make_query())

        assert artifacts.url == "https://example.com/"

    async def test_evaluate_failure_uses_fallback_url(self, tmp_path: Path) -> None:
        mock_client = MockBrowserClient()

        async def failing_evaluate(expr: str) -> Any:
            raise PlaywrightError("Page has been closed")

        mock_client.evaluate = failing_evaluate  # type: ignore[method-assign]
        orch = _make_orchestrator(_make_config(), [], tmp_path, mock_client)

        artifacts = await orch._capture_artifacts(_make_query())

        assert artifacts.final_url == "https://example.com/"


class TestOrchestratorBackoff:
    """Exponential backoff computation."""

    def test_backoff_increases_exponentially(self, tmp_path: Path) -> None:
        orch = SearchAuditOrchestrator(_make_config(retry_backoff_base=2.0), [], tmp_path)

        # With base=2.0, attempt=0 gives ~2.0, attempt=1 ~4.0, attempt=2 ~8.0 (jitter 0.7-1.3)
        assert 1.4 <= orch._compute_backoff(0) <= 2.6
        assert 2.8 <= orch._compute_backoff(1) <= 5.2
        assert 5.6 <= orch._compute_backoff(2) <= 10.4

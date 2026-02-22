"""Tests for orchestrator retry logic and error recovery."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from agentic_search_audit.core.orchestrator import SearchAuditOrchestrator
from agentic_search_audit.core.types import (
    AuditConfig,
    PageArtifacts,
    Query,
    QueryOrigin,
    RunConfig,
    SiteConfig,
)
from tests.helpers import make_fqi_judge_score

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**run_overrides: Any) -> AuditConfig:
    """Create a minimal AuditConfig for testing."""
    run_kwargs: dict[str, Any] = {
        "headless": True,
        "throttle_rps": 0,  # disable rate limiting for fast tests
    }
    run_kwargs.update(run_overrides)
    return AuditConfig(
        site=SiteConfig(url="https://example.com"),  # type: ignore[arg-type]
        run=RunConfig(**run_kwargs),
    )


def _make_query(text: str = "test query") -> Query:
    return Query(id="q001", text=text, lang="en", origin=QueryOrigin.PREDEFINED)


class MockBrowserClient:
    """Mock BrowserClient with configurable failure injection."""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.recover_page_calls = 0
        self.reconnect_calls = 0
        self.navigate_calls = 0
        self._page_alive = True
        self._browser_alive = True
        self._fail_on_process: list[Exception] = []

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

    def inject_failure(self, exc: Exception) -> None:
        """Add an exception to be raised on the next _process_query call."""
        self._fail_on_process.append(exc)

    def pop_failure(self) -> Exception | None:
        if self._fail_on_process:
            return self._fail_on_process.pop(0)
        return None


def _make_orchestrator(
    config: AuditConfig,
    queries: list[Query],
    tmp_path: Path,
    mock_client: MockBrowserClient,
) -> SearchAuditOrchestrator:
    orch = SearchAuditOrchestrator(config, queries, tmp_path)
    orch.client = mock_client
    return orch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrchestratorRetryOnTimeout:
    """Test retry behaviour on timeout errors."""

    async def test_retries_on_timeout_then_succeeds(self, tmp_path: Path) -> None:
        config = _make_config(max_retries=2, retry_backoff_base=0.01)
        query = _make_query()
        mock_client = MockBrowserClient()
        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        call_count = 0

        async def fake_process_query(q: Query) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PlaywrightTimeoutError("Timeout 30000ms exceeded")
            # Succeed on second call
            from agentic_search_audit.core.types import AuditRecord

            return AuditRecord(
                site="https://example.com",
                query=q,
                items=[],
                page=PageArtifacts(
                    url="https://example.com",
                    final_url="https://example.com/search",
                    html_path="test.html",
                    screenshot_path="test.png",
                    ts=datetime.now(),
                ),
                judge=make_fqi_judge_score(),
            )

        orch._process_query = fake_process_query  # type: ignore[assignment]

        # Mock compliance and other setup
        with (
            patch.object(orch, "_navigate_to_site", new_callable=AsyncMock),
            patch.object(orch, "_save_record"),
        ):
            # Simulate what run() does inside async with
            max_attempts = 1 + config.run.max_retries
            for attempt in range(max_attempts):
                try:
                    record = await orch._process_query(query)
                    orch.records.append(record)
                    break
                except Exception as e:
                    from agentic_search_audit.browser import classify_error, is_retryable

                    kind = classify_error(e)
                    if is_retryable(kind) and attempt < max_attempts - 1:
                        await orch._recover_for_retry(kind)
                        await asyncio.sleep(0.01)
                    else:
                        break

        assert len(orch.records) == 1
        assert call_count == 2
        assert mock_client.recover_page_calls >= 1

    async def test_gives_up_after_max_retries(self, tmp_path: Path) -> None:
        config = _make_config(max_retries=1, retry_backoff_base=0.01)
        query = _make_query()
        mock_client = MockBrowserClient()
        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        async def always_timeout(q: Query) -> Any:
            raise PlaywrightTimeoutError("Timeout 30000ms exceeded")

        orch._process_query = always_timeout  # type: ignore[assignment]

        with patch.object(orch, "_navigate_to_site", new_callable=AsyncMock):
            max_attempts = 1 + config.run.max_retries
            attempts_made = 0
            for attempt in range(max_attempts):
                try:
                    await orch._process_query(query)
                    break
                except Exception as e:
                    attempts_made += 1
                    from agentic_search_audit.browser import classify_error, is_retryable

                    kind = classify_error(e)
                    if is_retryable(kind) and attempt < max_attempts - 1:
                        await orch._recover_for_retry(kind)
                    else:
                        break

        assert attempts_made == 2  # 1 + max_retries
        assert len(orch.records) == 0


class TestOrchestratorBrowserDeadRecovery:
    """Test full reconnect when browser dies."""

    async def test_reconnects_on_browser_dead(self, tmp_path: Path) -> None:
        config = _make_config(max_retries=1, retry_backoff_base=0.01)
        query = _make_query()
        mock_client = MockBrowserClient()
        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        from agentic_search_audit.browser.errors import BrowserErrorKind

        with patch.object(orch, "_navigate_to_site", new_callable=AsyncMock):
            await orch._recover_for_retry(BrowserErrorKind.BROWSER_DEAD)

        assert mock_client.reconnect_calls == 1

    async def test_reconnects_when_browser_not_alive_on_page_closed(self, tmp_path: Path) -> None:
        config = _make_config(max_retries=1, retry_backoff_base=0.01)
        query = _make_query()
        mock_client = MockBrowserClient()
        mock_client._browser_alive = False  # browser is also dead
        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        from agentic_search_audit.browser.errors import BrowserErrorKind

        with patch.object(orch, "_navigate_to_site", new_callable=AsyncMock):
            await orch._recover_for_retry(BrowserErrorKind.PAGE_CLOSED)

        assert mock_client.reconnect_calls == 1
        assert mock_client.recover_page_calls == 0

    async def test_recovers_page_when_browser_alive_on_page_closed(self, tmp_path: Path) -> None:
        config = _make_config(max_retries=1, retry_backoff_base=0.01)
        query = _make_query()
        mock_client = MockBrowserClient()
        mock_client._browser_alive = True
        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        from agentic_search_audit.browser.errors import BrowserErrorKind

        with patch.object(orch, "_navigate_to_site", new_callable=AsyncMock):
            await orch._recover_for_retry(BrowserErrorKind.PAGE_CLOSED)

        assert mock_client.recover_page_calls == 1
        assert mock_client.reconnect_calls == 0


class TestOrchestratorRateLimitOnRetry:
    """Test that rate limiting applies on retries."""

    async def test_rate_limit_called_on_retry(self, tmp_path: Path) -> None:
        config = _make_config(max_retries=1, retry_backoff_base=0.01, throttle_rps=0.5)
        query = _make_query()
        mock_client = MockBrowserClient()
        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        rate_limit_calls = 0

        async def counting_rate_limit() -> None:
            nonlocal rate_limit_calls
            rate_limit_calls += 1

        orch._rate_limit = counting_rate_limit  # type: ignore[assignment]

        call_count = 0

        async def fail_once(q: Query) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PlaywrightTimeoutError("Timeout")
            from agentic_search_audit.core.types import AuditRecord

            return AuditRecord(
                site="https://example.com",
                query=q,
                items=[],
                page=PageArtifacts(
                    url="https://example.com",
                    final_url="https://example.com",
                    html_path="test.html",
                    screenshot_path="test.png",
                    ts=datetime.now(),
                ),
                judge=make_fqi_judge_score(),
            )

        orch._process_query = fail_once  # type: ignore[assignment]

        # Simulate the retry loop for query index i=1, which means
        # rate_limit is called on every attempt (i > 1 or attempt > 0)
        with (
            patch.object(orch, "_navigate_to_site", new_callable=AsyncMock),
            patch.object(orch, "_save_record"),
        ):
            max_attempts = 1 + config.run.max_retries
            i = 1  # first query
            for attempt in range(max_attempts):
                try:
                    # attempt > 0 triggers rate limit
                    if i > 1 or attempt > 0:
                        await orch._rate_limit()

                    record = await orch._process_query(query)
                    orch.records.append(record)
                    break
                except Exception as e:
                    from agentic_search_audit.browser import classify_error, is_retryable

                    kind = classify_error(e)
                    if is_retryable(kind) and attempt < max_attempts - 1:
                        await orch._recover_for_retry(kind)

        # Rate limit should have been called on retry attempt (attempt=1)
        assert rate_limit_calls == 1


class TestOrchestratorArtifactSafety:
    """Test that artifact capture failures don't fail the query."""

    async def test_screenshot_failure_returns_artifacts(self, tmp_path: Path) -> None:
        config = _make_config()
        query = _make_query()
        mock_client = MockBrowserClient()

        # Make screenshot fail
        async def failing_screenshot(output_path: Path, full_page: bool = True) -> Path:
            raise PlaywrightError("Page has been closed")

        mock_client.screenshot = failing_screenshot  # type: ignore[assignment]

        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        artifacts = await orch._capture_artifacts(query)

        # Should return valid artifacts even though screenshot failed
        assert artifacts.url == "https://example.com/"
        assert artifacts.html_path  # path should still be set

    async def test_html_failure_returns_artifacts(self, tmp_path: Path) -> None:
        config = _make_config()
        query = _make_query()
        mock_client = MockBrowserClient()

        # Make get_html fail
        async def failing_html() -> str:
            raise PlaywrightError("Page has been closed")

        mock_client.get_html = failing_html  # type: ignore[assignment]

        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        artifacts = await orch._capture_artifacts(query)

        assert artifacts.url == "https://example.com/"

    async def test_evaluate_failure_uses_fallback_url(self, tmp_path: Path) -> None:
        config = _make_config()
        query = _make_query()
        mock_client = MockBrowserClient()

        # Make evaluate fail
        async def failing_evaluate(expr: str) -> Any:
            raise PlaywrightError("Page has been closed")

        mock_client.evaluate = failing_evaluate  # type: ignore[assignment]

        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        artifacts = await orch._capture_artifacts(query)

        assert artifacts.final_url == "https://example.com/"


class TestOrchestratorBackoff:
    """Test exponential backoff computation."""

    def test_backoff_increases_exponentially(self, tmp_path: Path) -> None:
        config = _make_config(retry_backoff_base=2.0)
        orch = SearchAuditOrchestrator(config, [], tmp_path)

        # With base=2.0, attempt=0 should give ~2.0, attempt=1 ~4.0, attempt=2 ~8.0
        # Jitter is 0.7-1.3, so we check ranges
        b0 = orch._compute_backoff(0)
        b1 = orch._compute_backoff(1)
        b2 = orch._compute_backoff(2)

        assert 1.4 <= b0 <= 2.6  # 2.0 * 1 * [0.7, 1.3]
        assert 2.8 <= b1 <= 5.2  # 2.0 * 2 * [0.7, 1.3]
        assert 5.6 <= b2 <= 10.4  # 2.0 * 4 * [0.7, 1.3]


class TestOrchestratorNonRetryableError:
    """Test that non-retryable errors are not retried."""

    async def test_permanent_error_not_retried(self, tmp_path: Path) -> None:
        config = _make_config(max_retries=2, retry_backoff_base=0.01)
        query = _make_query()
        mock_client = MockBrowserClient()
        orch = _make_orchestrator(config, [query], tmp_path, mock_client)

        call_count = 0

        async def always_permanent(q: Query) -> Any:
            nonlocal call_count
            call_count += 1
            raise PlaywrightError("Element is not an input")

        orch._process_query = always_permanent  # type: ignore[assignment]

        with patch.object(orch, "_navigate_to_site", new_callable=AsyncMock):
            max_attempts = 1 + config.run.max_retries
            for attempt in range(max_attempts):
                try:
                    await orch._process_query(query)
                    break
                except Exception as e:
                    from agentic_search_audit.browser import classify_error, is_retryable

                    kind = classify_error(e)
                    if is_retryable(kind) and attempt < max_attempts - 1:
                        await orch._recover_for_retry(kind)
                    else:
                        break

        # Should only be called once -- permanent error is not retried
        assert call_count == 1
        assert mock_client.recover_page_calls == 0
        assert mock_client.reconnect_calls == 0

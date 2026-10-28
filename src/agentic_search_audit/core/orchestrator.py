"""Main orchestrator for search audit."""

import asyncio
import json
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from ..browser import classify_error, create_browser_client, is_retryable
from ..browser.challenge_detector import ChallengeDetectedError, detect_challenge
from ..browser.errors import BrowserErrorKind
from ..browser.session import BrowserSession
from ..browser.stealth import inject_human_behavior
from ..extractors import ModalHandler, ResultsExtractor, SearchBoxFinder
from ..extractors.pdp_analyzer import PdpAnalyzer
from ..extractors.vision_results import VisionResultsExtractor
from ..judge import SearchQualityJudge
from ..judge.experts import ExpertPanel
from ..judge.intent_classifier import IntentClassifier
from ..judge.rate_limiter import LLMRateLimiter
from ..report import ReportGenerator
from .compliance import ComplianceChecker, RobotsPolicy
from .config import get_run_dir
from .errors import QuerySubmitError
from .types import (
    AuditConfig,
    AuditRecord,
    BrowserClient,
    ExpertInsight,
    PageArtifacts,
    Query,
    QueryFailure,
    ResultItem,
    RunConfig,
    query_time_budget_s,
)

logger = logging.getLogger(__name__)

ClientFactory = Callable[[RunConfig, str], BrowserClient]

# Failure kinds beyond the BrowserErrorKind values.
FAILURE_QUERY_TIMEOUT = "query_timeout"
FAILURE_CHALLENGE = "challenge"
FAILURE_SUBMIT = "submit_failed"
FAILURE_JUDGE = "judge"
_BROWSER_ERROR_VALUES = {kind.value for kind in BrowserErrorKind}


@dataclass
class CapturedQuery:
    """Everything the browser produced for one query, before the judge sees it."""

    query: Query
    items: list[ResultItem]
    page: PageArtifacts
    html: str
    url: str


class SearchAuditOrchestrator:
    """Orchestrates the complete search audit process.

    The browser client is injected (``client=``) or built by ``client_factory``
    (default: ``create_browser_client``) when ``run()`` starts. Per-query identity
    rotation and recovery live in ``BrowserSession``; the retry loop in
    ``_run_query_with_retries`` keeps the browser work (``_capture_query``) under a
    time budget and runs the judge (``_judge_query``) outside it.
    """

    def __init__(
        self,
        config: AuditConfig,
        queries: list[Query],
        run_dir: Path,
        *,
        client: BrowserClient | None = None,
        client_factory: ClientFactory | None = None,
    ):
        """Initialize orchestrator.

        Args:
            config: Audit configuration
            queries: List of queries to evaluate
            run_dir: Output directory for this run
            client: A ready browser client to use instead of building one
            client_factory: Builds the client from ``(run_config, locale)``;
                defaults to ``create_browser_client``
        """
        if client is not None and client_factory is not None:
            raise ValueError("Pass either client or client_factory, not both")
        self.config = config
        self.queries = queries
        self.run_dir = run_dir
        self.records: list[AuditRecord] = []
        self.failures: list[QueryFailure] = []

        self.client: BrowserClient | None = client
        self._client_factory = client_factory
        self.judge: SearchQualityJudge | None = None
        self.reporter: ReportGenerator | None = None
        self.compliance_checker: ComplianceChecker | None = None

        self._session: BrowserSession | None = None
        self._modal_handler: ModalHandler | None = None
        self._search_finder: SearchBoxFinder | None = None
        self._results_extractor: ResultsExtractor | None = None
        self._vision_extractor: VisionResultsExtractor | None = None
        self._intent_classifier = IntentClassifier()
        self._llm_rate_limiter: LLMRateLimiter | None = None

        # Adaptive throttle multiplier (increases on resistance, decays on success)
        self._throttle_multiplier: float = 1.0
        self._query_timeout_s: float = query_time_budget_s(config)

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------

    def _require_client(self) -> BrowserClient:
        if self.client is None:
            raise RuntimeError("Browser client not initialized")
        return self.client

    @property
    def session(self) -> BrowserSession:
        """The per-run browser session (built on first use)."""
        if self._session is None:
            self._session = BrowserSession(self._require_client(), self.config.run)
        return self._session

    @property
    def modal_handler(self) -> ModalHandler:
        if self._modal_handler is None:
            self._modal_handler = ModalHandler(self._require_client(), self.config.site.modals)
        return self._modal_handler

    @property
    def search_finder(self) -> SearchBoxFinder:
        if self._search_finder is None:
            search = self.config.site.search
            self._search_finder = SearchBoxFinder(
                self._require_client(),
                search,
                llm_config=self.config.llm,
                use_intelligent_fallback=search.use_intelligent_fallback,
            )
        return self._search_finder

    @property
    def results_extractor(self) -> ResultsExtractor:
        if self._results_extractor is None:
            self._results_extractor = ResultsExtractor(
                self._require_client(), self.config.site.results, str(self.config.site.url)
            )
        return self._results_extractor

    @property
    def vision_extractor(self) -> VisionResultsExtractor:
        if self._vision_extractor is None:
            self._vision_extractor = VisionResultsExtractor(self._require_client(), self.config.llm)
        return self._vision_extractor

    def _init_components(self) -> None:
        """Build the client (unless injected), judge, reporter, compliance and extractors."""
        run, llm = self.config.run, self.config.llm
        if run.seed is not None:
            random.seed(run.seed)

        self._llm_rate_limiter = LLMRateLimiter(
            max_concurrent=llm.max_concurrent, min_interval_seconds=llm.min_request_interval_s
        )
        if self.client is None:
            factory = self._client_factory or create_browser_client
            self.client = factory(run, self.config.site.locale)
        self.judge = SearchQualityJudge(llm, rate_limiter=self._llm_rate_limiter, seed=run.seed)
        self.reporter = ReportGenerator(self.config, self.run_dir)
        robots_policy = RobotsPolicy(
            user_agent=self.config.compliance.user_agent,
            respect_robots=self.config.compliance.respect_robots_txt,
            timeout=self.config.compliance.robots_timeout,
        )
        self.compliance_checker = ComplianceChecker(robots_policy=robots_policy)

        # Extractors are created once per run and reused by every query.
        self._session = BrowserSession(self.client, run)
        self._modal_handler = None
        self._search_finder = None
        self._results_extractor = None
        self._vision_extractor = None

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self, generate_pdf: bool = False) -> list[AuditRecord]:
        """Run the complete audit.

        Returns:
            List of audit records
        """
        logger.info(f"Starting audit with {len(self.queries)} queries")
        logger.info(f"Output directory: {self.run_dir}")

        completed_ids = self._load_checkpoint()
        self._init_components()
        client = self._require_client()
        assert self.reporter is not None

        await self._check_compliance()
        self._log_time_budget()

        async with client:
            for index, query in enumerate(self.queries, 1):
                if query.id in completed_ids:
                    logger.info(
                        f"Skipping query {index}/{len(self.queries)} (already completed): {query.text}"
                    )
                    continue

                logger.info(f"Processing query {index}/{len(self.queries)}: {query.text}")
                record = await self._run_query_with_retries(query, index)
                if record is not None:
                    self.records.append(record)
                    self._save_record(record)
                    self._signal_success()

        expert_insights = await self._run_expert_panel()

        if self.records:
            self.reporter.generate_reports(
                self.records,
                expert_insights=expert_insights,
                generate_pdf=generate_pdf,
                failures=self.failures,
            )

        logger.info(
            f"Audit complete. Processed {len(self.records)}/{len(self.queries)} queries "
            f"({len(self.failures)} failed)"
        )
        return self.records

    async def _check_compliance(self) -> None:
        """Abort before touching the site if robots.txt disallows it."""
        assert self.compliance_checker is not None
        site_url = str(self.config.site.url)
        compliance_result = await self.compliance_checker.check_url(site_url)
        if not compliance_result["allowed"]:
            logger.error(f"Audit blocked by compliance policy: {compliance_result['warnings']}")
            raise PermissionError(
                f"Cannot audit {site_url}: blocked by robots.txt. "
                "Use --ignore-robots to override (not recommended)."
            )

    def _log_time_budget(self) -> None:
        run, llm = self.config.run, self.config.llm
        if run.query_timeout_s is not None:
            logger.info(
                f"Per-query browser budget {self._query_timeout_s:.0f}s (run.query_timeout_s)"
            )
            return
        pdp = run.pdp_top_k * run.pdp_timeout_ms / 1000 if run.enable_pdp_analysis else 0.0
        logger.info(
            f"Per-query browser budget {self._query_timeout_s:.0f}s = "
            f"browser {run.browser_budget_s:.0f} + vision {2 * llm.vision_timeout:.0f} + pdp {pdp:.0f}"
        )

    async def _run_expert_panel(self) -> list[ExpertInsight]:
        """Site-level expert commentary over the collected records (non-fatal)."""
        if not self.records:
            return []
        try:
            expert_panel = ExpertPanel(self.config.llm, rate_limiter=self._llm_rate_limiter)
            insights = await expert_panel.evaluate(self.records, str(self.config.site.url))
            logger.info(f"Expert panel complete: {len(insights)} insights generated")
            return list(insights)
        except Exception as e:
            logger.error(f"Expert panel failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Per-query retry loop
    # ------------------------------------------------------------------

    async def _prepare_browser_for_query(self, index: int, attempt: int) -> None:
        """Recover a dead page, rotate identity (first attempt only) and load the site.

        Raises:
            ChallengeDetectedError: when the site shows a bot challenge on load.
        """
        session = self.session
        await session.ensure_alive()
        if attempt == 0:
            await session.rotate_for_query(index)
        if session.needs_navigation or not self.config.site.search.search_url_template:
            await self._navigate_to_site()
            session.needs_navigation = False

    async def _run_query_with_retries(self, query: Query, index: int) -> AuditRecord | None:
        """Run one query with retries; returns None (and records a failure) when it gives up."""
        max_attempts = 1 + self.config.run.max_retries
        failure: QueryFailure | None = None

        for attempt in range(max_attempts):
            try:
                await self._prepare_browser_for_query(index, attempt)
                if index > 1 or attempt > 0:
                    await self._rate_limit()
                captured = await asyncio.wait_for(
                    self._capture_query(query), timeout=self._query_timeout_s
                )
            except asyncio.TimeoutError:
                kind, retryable, message = (
                    FAILURE_QUERY_TIMEOUT,
                    True,
                    f"exceeded the {self._query_timeout_s:.0f}s query budget",
                )
            except ChallengeDetectedError as e:
                kind, retryable, message = FAILURE_CHALLENGE, True, str(e)
            except QuerySubmitError as e:
                kind, retryable, message = FAILURE_SUBMIT, True, str(e)
            except Exception as e:
                error_kind = classify_error(e)
                kind, retryable, message = error_kind.value, is_retryable(error_kind), str(e)
                logger.debug(f"Query '{query.text}' raised {type(e).__name__}", exc_info=True)
            else:
                try:
                    return await self._judge_query(captured)
                except Exception as e:
                    # The judge has its own retries; never re-run the browser for it.
                    logger.error(f"Judge failed for '{query.text}': {e}")
                    self._record_failure(
                        QueryFailure(
                            site=str(self.config.site.url),
                            query=query,
                            error_kind=FAILURE_JUDGE,
                            message=str(e),
                            attempts=attempt + 1,
                        )
                    )
                    return None

            self._signal_resistance()
            failure = QueryFailure(
                site=str(self.config.site.url),
                query=query,
                error_kind=kind,
                message=message,
                attempts=attempt + 1,
            )
            if not retryable or attempt >= max_attempts - 1:
                logger.error(
                    f"Query '{query.text}' failed ({kind}) after {attempt + 1} attempt(s): {message}"
                )
                break
            logger.warning(
                f"Query '{query.text}' failed ({kind}, attempt {attempt + 1}/{max_attempts}): "
                f"{message} -- retrying"
            )
            await self._recover_after_failure(kind, attempt)

        if failure is not None:
            self._record_failure(failure)
        return None

    async def _recover_after_failure(self, kind: str, attempt: int) -> None:
        """Recover the browser for the next attempt and back off. Never raises."""
        session = self.session
        backoff = self._compute_backoff(attempt) * (3 if kind == FAILURE_CHALLENGE else 1)
        try:
            if kind == FAILURE_CHALLENGE:
                await session.clear_cookies_if_allowed("challenge")
                session.needs_navigation = True
            elif kind == FAILURE_QUERY_TIMEOUT:
                await session.recover(BrowserErrorKind.TIMEOUT)
            elif kind in _BROWSER_ERROR_VALUES:
                await session.recover(BrowserErrorKind(kind))
            else:
                session.needs_navigation = True
        except Exception as e:
            logger.warning(f"Recovery after {kind} failed: {e}")
            session.needs_navigation = True
        logger.debug(f"Backing off {backoff:.1f}s before retry")
        await asyncio.sleep(backoff)

    def _record_failure(self, failure: QueryFailure) -> None:
        """Keep the failure for the report and append it to failures.jsonl."""
        self.failures.append(failure)
        path = self.run_dir / "failures.jsonl"
        try:
            with open(path, "a", encoding="utf-8") as f:
                json.dump(failure.model_dump(mode="json"), f)
                f.write("\n")
        except OSError as e:
            logger.warning(f"Could not write {path}: {e}")

    # ------------------------------------------------------------------
    # One query: browser part, then judge
    # ------------------------------------------------------------------

    async def _process_query(self, query: Query) -> AuditRecord:
        """Capture and judge one query (no retries). Kept for callers of the old API."""
        return await self._judge_query(await self._capture_query(query))

    async def _capture_query(self, query: Query) -> CapturedQuery:
        """Run the search in the browser and capture results and artifacts.

        Raises:
            ChallengeDetectedError: If a bot-detection challenge is detected.
            QuerySubmitError: If the search could not be submitted.
        """
        client = self._require_client()

        # Auto-classify intent if not set
        if query.intent is None:
            query = query.model_copy(
                update={"intent": self._intent_classifier.classify(query.text)}
            )
            logger.debug(f"Auto-classified intent for '{query.text}': {query.intent}")

        # Use direct URL navigation if a search_url_template is configured
        template = self.config.site.search.search_url_template
        if template:
            search_url = template.replace("{query}", quote_plus(query.text))
            logger.info(f"Navigating directly to search URL: {search_url}")
            await client.navigate(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await self.modal_handler.dismiss_modals()
        else:
            await self.modal_handler.dismiss_modals()
            await inject_human_behavior(client)
            if not await self.search_finder.submit_search(query.text):
                raise QuerySubmitError(f"Failed to submit search for query: {query.text}")

        # Wait for results
        await asyncio.sleep(self.config.run.post_submit_ms / 1000)
        await client.wait_for_network_idle(timeout=self.config.run.network_idle_ms)

        # Challenge detection: check for bot-detection pages before extraction
        challenge = await detect_challenge(client)
        if challenge.detected:
            raise ChallengeDetectedError(challenge)

        no_results = await self.results_extractor.check_for_no_results()
        if no_results:
            logger.warning(f"No results found for query: {query.text}")
        else:
            await self._scroll_for_results(self.results_extractor, self.config.run.top_k)

        items = await self._extract_items(no_results)

        # Human-like behavior after extraction
        try:
            await inject_human_behavior(client)
        except Exception:
            pass  # Non-critical

        # Signal resistance if empty results on a non-empty query
        if not items and not no_results:
            self._signal_resistance()

        if self.config.run.enable_pdp_analysis and items:
            items = await self._analyze_pdps(query, items)

        page_artifacts = await self._capture_artifacts(query)
        html_content = await client.get_html()
        return CapturedQuery(
            query=query,
            items=items,
            page=page_artifacts,
            html=html_content,
            url=await self._current_url(),
        )

    async def _extract_items(self, no_results: bool) -> list[ResultItem]:
        """CSS extraction with a vision fallback, or vision-first when configured."""
        run = self.config.run
        if no_results:
            return []
        if run.use_vision_extraction:
            return await self.vision_extractor.extract_results(top_k=run.top_k)

        items = await self.results_extractor.extract_results(top_k=run.top_k)
        has_content = any(item.title or item.price for item in items)
        if items and has_content:
            return items
        reason = (
            "CSS extraction returned no items"
            if not items
            else "CSS extraction returned items with no content"
        )
        logger.warning(f"{reason} -- falling back to vision extraction")
        return await self.vision_extractor.extract_results(top_k=run.top_k)

    async def _analyze_pdps(self, query: Query, items: list[ResultItem]) -> list[ResultItem]:
        """Click into the top product pages; non-fatal except for bot challenges."""
        client = self._require_client()
        try:
            pdp_analyzer = PdpAnalyzer(
                client=client,
                llm_config=self.config.llm,
                modals_config=self.config.site.modals,
                run_dir=self.run_dir,
                query=query,
                timeout_ms=self.config.run.pdp_timeout_ms,
            )
            items = await pdp_analyzer.analyze_pdps(
                items=items,
                search_page_url=await self._current_url(),
                top_k=self.config.run.pdp_top_k,
            )
            analyzed_count = sum(
                1 for item in items if item.attributes.get("pdp_analyzed") == "true"
            )
            logger.info(
                f"PDP analysis complete: {analyzed_count}/"
                f"{min(len(items), self.config.run.pdp_top_k)} PDPs analyzed"
            )
            # Challenge detection after PDP navigation (may have triggered blocks)
            challenge = await detect_challenge(client)
            if challenge.detected:
                raise ChallengeDetectedError(challenge)
        except ChallengeDetectedError:
            raise
        except Exception as e:
            logger.warning(f"PDP analysis failed (non-fatal): {e}")
        return items

    async def _judge_query(self, captured: CapturedQuery) -> AuditRecord:
        """Score a captured query with the LLM judge."""
        if self.judge is None:
            raise RuntimeError("Judge not initialized")
        judge_score = await self.judge.evaluate(
            query=captured.query,
            results=captured.items,
            page_url=captured.url,
            html_content=captured.html,
            site_name=str(self.config.site.url),
            locale=self.config.site.locale,
        )
        return AuditRecord(
            site=str(self.config.site.url),
            query=captured.query,
            items=captured.items,
            page=captured.page,
            judge=judge_score,
        )

    # ------------------------------------------------------------------
    # Checkpoint, throttle, navigation
    # ------------------------------------------------------------------

    def _load_checkpoint(self) -> set[str]:
        """Load completed query IDs from existing JSONL checkpoint.

        Returns:
            Set of query IDs that have already been completed.
        """
        jsonl_path = self.run_dir / "audit.jsonl"
        if not jsonl_path.exists():
            return set()

        completed_ids: set[str] = set()
        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record_data = json.loads(line)
                        query_id = record_data.get("query", {}).get("id")
                        if query_id:
                            completed_ids.add(query_id)
                            # Reload the record into self.records
                            self.records.append(AuditRecord(**record_data))
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"Skipping malformed checkpoint line: {e}")
                        continue

            if completed_ids:
                logger.info(
                    f"Resuming: {len(completed_ids)} queries already completed, "
                    f"{len(self.queries) - len(completed_ids)} remaining"
                )
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")

        return completed_ids

    def _compute_backoff(self, attempt: int) -> float:
        """Compute exponential backoff with jitter.

        Args:
            attempt: Zero-based attempt index.

        Returns:
            Sleep duration in seconds.
        """
        base = self.config.run.retry_backoff_base
        jitter: float = random.uniform(0.7, 1.3)
        delay: float = base * (2**attempt) * jitter
        return delay

    def _signal_resistance(self) -> None:
        """Increase throttle multiplier when encountering resistance signals."""
        self._throttle_multiplier = min(self._throttle_multiplier * 1.5, 5.0)
        logger.debug(f"Throttle multiplier increased to {self._throttle_multiplier:.2f}")

    def _signal_success(self) -> None:
        """Decay throttle multiplier toward 1.0 after successful queries."""
        self._throttle_multiplier = max(self._throttle_multiplier * 0.9, 1.0)

    async def _current_url(self) -> str:
        """Return the page's current URL, falling back to the configured site URL."""
        if self.client is None:
            return str(self.config.site.url)
        try:
            url = await self.client.evaluate("window.location.href")
        except Exception as e:
            logger.debug(f"Could not read window.location.href: {e}")
            return str(self.config.site.url)
        return url if isinstance(url, str) and url else str(self.config.site.url)

    async def _navigate_to_site(self) -> None:
        """Navigate to the site and handle initial modals."""
        client = self._require_client()

        logger.info(f"Navigating to {self.config.site.url}")

        # Use "domcontentloaded" instead of "networkidle" for faster, more reliable loading
        # Some sites (especially heavy SPAs) never reach "networkidle"
        await client.navigate(str(self.config.site.url), wait_until="domcontentloaded")

        # Wait for JavaScript to render (important for SPAs and dynamic content)
        logger.debug("Waiting for page JavaScript to render...")
        await asyncio.sleep(3)  # Initial wait for JS frameworks to bootstrap
        await client.wait_for_network_idle(timeout=self.config.run.network_idle_ms)

        # Handle modals (cookie consent, popups, etc.)
        await self.modal_handler.dismiss_modals()

        # Wait again after dismissing modals for any animations/transitions
        await asyncio.sleep(1)
        await self.modal_handler.wait_for_page_stable()

        # Challenge detection on initial navigation (not just post-search)
        challenge = await detect_challenge(client)
        if challenge.detected:
            raise ChallengeDetectedError(challenge)

        logger.info("Site loaded and ready")

    async def _scroll_for_results(self, extractor: ResultsExtractor, top_k: int) -> None:
        """Scroll incrementally and click 'Load More' to gather enough results.

        Replaces the old single-scroll approach.  Keeps scrolling until either
        ``top_k`` results are visible, the page stops growing, or
        ``max_scroll_attempts`` is exhausted.

        Args:
            extractor: ResultsExtractor (used only for counting).
            top_k: Desired number of results.
        """
        if not self.client:
            return

        cfg = self.config.run
        max_attempts = cfg.max_scroll_attempts
        step_px = cfg.scroll_step_px
        pause_s = cfg.scroll_pause_ms / 1000

        # Initial quick scroll to trigger any lazy-loading above the fold
        await self.client.evaluate(f"window.scrollBy(0, {step_px})")
        await asyncio.sleep(pause_s)

        visible = await extractor.count_visible_results()
        logger.debug(f"Initial visible results: {visible}")

        prev_visible = visible
        for attempt in range(max_attempts):
            if visible >= top_k:
                logger.debug(f"Enough results visible ({visible} >= {top_k}), stopping scroll")
                break

            # Try clicking "Load More" first — more reliable than infinite scroll
            clicked = await self._click_load_more()
            if clicked:
                await asyncio.sleep(pause_s)
                await self.client.wait_for_network_idle(timeout=self.config.run.network_idle_ms)
                visible = await extractor.count_visible_results()
                logger.debug(f"After Load-More click (attempt {attempt + 1}): {visible} results")
                if visible > prev_visible:
                    prev_visible = visible
                    continue  # got new results, try again

            # Scroll down to trigger infinite-scroll / lazy loading
            await self.client.evaluate(f"window.scrollBy(0, {step_px})")
            await asyncio.sleep(pause_s)
            await self.client.wait_for_network_idle(timeout=self.config.run.network_idle_ms)

            visible = await extractor.count_visible_results()
            logger.debug(f"After scroll (attempt {attempt + 1}): {visible} results")

            if visible == prev_visible:
                # Page didn't grow — stop scrolling to avoid wasting time
                logger.debug("No new results after scroll, stopping")
                break
            prev_visible = visible

        # Scroll back to top so screenshot / extraction start from the beginning
        await self.client.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

    async def _click_load_more(self) -> bool:
        """Try to find and click a 'Load More' / 'Show More' button.

        Returns:
            True if a button was clicked.
        """
        if not self.client:
            return False

        cfg = self.config.run

        # 1. Try CSS selectors
        for selector in cfg.load_more_selectors:
            try:
                el = await self.client.query_selector(selector)
                if el:
                    await self.client.click(selector)
                    logger.debug(f"Clicked Load-More via selector: {selector}")
                    return True
            except Exception:
                continue

        # 2. Fallback: find buttons / links by textContent
        for pattern in cfg.load_more_text_patterns:
            js = f"""
            (function() {{
                var candidates = document.querySelectorAll('button, a, [role="button"]');
                for (var i = 0; i < candidates.length; i++) {{
                    var txt = (candidates[i].textContent || '').trim().toLowerCase();
                    if (txt.includes('{pattern}')) {{
                        candidates[i].click();
                        return true;
                    }}
                }}
                return false;
            }})()
            """
            try:
                result = await self.client.evaluate(js)
                if result is True:
                    logger.debug(f"Clicked Load-More via text pattern: '{pattern}'")
                    return True
            except Exception:
                continue

        return False

    async def _capture_artifacts(self, query: Query) -> PageArtifacts:
        """Capture page artifacts (screenshot, HTML).

        Wrapped in safety handling so that a failure here does not
        abort the query.

        Args:
            query: Current query

        Returns:
            PageArtifacts with paths to saved files
        """
        if not self.client:
            raise RuntimeError("Browser client not initialized")

        # Create safe filename from query
        safe_query = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in query.text)
        safe_query = safe_query.replace(" ", "_")[:50]

        screenshot_path = self.run_dir / "screenshots" / f"{query.id}_{safe_query}.png"
        html_path = self.run_dir / "html_snapshots" / f"{query.id}_{safe_query}.html"

        # Screenshot (safe)
        try:
            await self.client.screenshot(screenshot_path, full_page=True)
        except Exception as e:
            logger.warning(f"Failed to capture screenshot for '{query.text}': {e}")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        # HTML snapshot (safe)
        try:
            html_content = await self.client.get_html()
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html_content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to capture HTML for '{query.text}': {e}")

        return PageArtifacts(
            url=str(self.config.site.url),
            final_url=await self._current_url(),
            html_path=str(html_path),
            screenshot_path=str(screenshot_path),
            ts=datetime.now(),
        )

    def _save_record(self, record: AuditRecord) -> None:
        """Save audit record to JSONL file.

        Args:
            record: Audit record to save
        """
        jsonl_path = self.run_dir / "audit.jsonl"

        with open(jsonl_path, "a", encoding="utf-8") as f:
            json.dump(record.model_dump(mode="json"), f)
            f.write("\n")

    async def _rate_limit(self) -> None:
        """Apply adaptive rate limiting with ±30% jitter between requests.

        The throttle multiplier increases when encountering resistance signals
        (challenges, empty results, errors) and decays on successful queries.
        """
        if self.config.run.throttle_rps > 0:
            delay = 1.0 / self.config.run.throttle_rps
            jittered = delay * self._throttle_multiplier * random.uniform(0.7, 1.3)
            logger.debug(
                f"Rate limiting: waiting {jittered:.2f}s "
                f"(base {delay:.2f}s, multiplier {self._throttle_multiplier:.2f}x)"
            )
            await asyncio.sleep(jittered)


def _find_latest_run_dir(base_dir: Path, site_name: str) -> Path | None:
    """Find the most recent run directory for a site.

    Args:
        base_dir: Base output directory (e.g. ./runs)
        site_name: Site hostname

    Returns:
        Path to the latest run directory, or None if none exists.
    """
    site_dir = base_dir / site_name
    if not site_dir.exists():
        return None
    # Run dirs are named as timestamps (YYYYMMDD_HHMMSS), sorted alphabetically = chronologically
    dirs = sorted(
        [d for d in site_dir.iterdir() if d.is_dir() and (d / "audit.jsonl").exists()],
        key=lambda d: d.name,
    )
    return dirs[-1] if dirs else None


async def run_audit(
    config: AuditConfig,
    queries: list[Query],
    output_dir: str | None = None,
    resume: bool = False,
    generate_pdf: bool = False,
) -> list[AuditRecord]:
    """Run a complete search audit.

    Args:
        config: Audit configuration
        queries: List of queries to evaluate
        output_dir: Custom output directory (optional)
        resume: If True, reuse the most recent run directory for checkpoint resume

    Returns:
        List of audit records
    """
    # Create or find run directory
    if output_dir:
        run_dir = Path(output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "screenshots").mkdir(exist_ok=True)
        (run_dir / "html_snapshots").mkdir(exist_ok=True)
    elif resume:
        base_dir = Path(config.report.out_dir)
        site_name = config.site.url.host or "unknown"
        existing = _find_latest_run_dir(base_dir, site_name)
        if existing:
            run_dir = existing
            logger.info(f"Resuming from existing run directory: {run_dir}")
        else:
            logger.warning("No previous run found to resume — starting fresh")
            run_dir = get_run_dir(base_dir, site_name)
    else:
        base_dir = Path(config.report.out_dir)
        site_name = config.site.url.host or "unknown"
        run_dir = get_run_dir(base_dir, site_name)

    # Create orchestrator and run
    orchestrator = SearchAuditOrchestrator(config, queries, run_dir)
    records = await orchestrator.run(generate_pdf=generate_pdf)

    return records

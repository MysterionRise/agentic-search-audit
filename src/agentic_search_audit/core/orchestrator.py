"""Main orchestrator for search audit."""

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path

from ..browser import classify_error, create_browser_client, is_retryable
from ..browser.challenge_detector import ChallengeDetectedError, detect_challenge
from ..browser.errors import BrowserErrorKind
from ..browser.proxy import ProxyRotator
from ..browser.stealth import UserAgentRotator
from ..extractors import ModalHandler, ResultsExtractor, SearchBoxFinder
from ..judge import SearchQualityJudge
from ..judge.experts import ExpertPanel
from ..judge.rate_limiter import LLMRateLimiter
from ..report import ReportGenerator
from .compliance import ComplianceChecker, RobotsPolicy
from .config import get_run_dir
from .types import AuditConfig, AuditRecord, BrowserClient, PageArtifacts, Query, ResultItem

logger = logging.getLogger(__name__)


class SearchAuditOrchestrator:
    """Orchestrates the complete search audit process."""

    def __init__(self, config: AuditConfig, queries: list[Query], run_dir: Path):
        """Initialize orchestrator.

        Args:
            config: Audit configuration
            queries: List of queries to evaluate
            run_dir: Output directory for this run
        """
        self.config = config
        self.queries = queries
        self.run_dir = run_dir
        self.records: list[AuditRecord] = []

        # Initialize components (will be created in async context)
        self.client: BrowserClient | None = None
        self.judge: SearchQualityJudge | None = None
        self.reporter: ReportGenerator | None = None
        self.compliance_checker: ComplianceChecker | None = None

        # Adaptive throttle multiplier (increases on resistance, decays on success)
        self._throttle_multiplier: float = 1.0

    async def run(self) -> list[AuditRecord]:
        """Run the complete audit.

        Returns:
            List of audit records
        """
        logger.info(f"Starting audit with {len(self.queries)} queries")
        logger.info(f"Output directory: {self.run_dir}")

        # Load checkpoint if resuming
        completed_ids = self._load_checkpoint()

        # Initialize shared LLM rate limiter
        llm_rate_limiter = LLMRateLimiter(max_concurrent=3, min_interval_seconds=0.5)

        # Initialize browser client based on configured backend
        self.client = create_browser_client(self.config.run, locale=self.config.site.locale)
        self.judge = SearchQualityJudge(self.config.llm, rate_limiter=llm_rate_limiter)
        self.reporter = ReportGenerator(self.config, self.run_dir)

        # Initialize UA rotator and proxy rotator
        ua_rotator = UserAgentRotator()
        proxy_rotator = ProxyRotator(
            strategy=self.config.run.proxy_rotation_strategy,
            proxy_list=self.config.run.proxy_list,
        )

        # Initialize compliance checker
        robots_policy = RobotsPolicy(
            user_agent=self.config.compliance.user_agent,
            respect_robots=self.config.compliance.respect_robots_txt,
            timeout=self.config.compliance.robots_timeout,
        )
        self.compliance_checker = ComplianceChecker(robots_policy=robots_policy)

        # Check robots.txt compliance before starting
        site_url = str(self.config.site.url)
        compliance_result = await self.compliance_checker.check_url(site_url)
        if not compliance_result["allowed"]:
            logger.error(f"Audit blocked by compliance policy: {compliance_result['warnings']}")
            raise PermissionError(
                f"Cannot audit {site_url}: blocked by robots.txt. "
                "Use --ignore-robots to override (not recommended)."
            )

        # Connect to browser
        async with self.client:
            # Navigate to homepage
            await self._navigate_to_site()

            # Process each query with configurable retry
            max_attempts = 1 + self.config.run.max_retries
            cookie_interval = self.config.run.cookie_clear_interval
            queries_since_cookie_clear = 0

            for i, query in enumerate(self.queries, 1):
                # Skip already-completed queries (checkpoint resume)
                if query.id in completed_ids:
                    logger.info(
                        f"Skipping query {i}/{len(self.queries)} (already completed): {query.text}"
                    )
                    continue

                logger.info(f"Processing query {i}/{len(self.queries)}: {query.text}")

                # Rotate user-agent before each query
                new_ua = ua_rotator.next()
                try:
                    await self.client.set_user_agent(new_ua)
                    # Re-navigate to site after UA rotation (new context)
                    await self._navigate_to_site()
                except Exception as e:
                    logger.warning(f"UA rotation failed: {e}")

                # Rotate proxy if configured for per-query
                next_proxy = proxy_rotator.next_proxy()
                if next_proxy:
                    try:
                        await self.client.set_proxy(next_proxy)
                        await self._navigate_to_site()
                    except Exception as e:
                        logger.warning(f"Proxy rotation failed: {e}")

                # Clear cookies periodically
                if cookie_interval > 0:
                    queries_since_cookie_clear += 1
                    if queries_since_cookie_clear >= cookie_interval:
                        try:
                            await self.client.clear_cookies()
                            queries_since_cookie_clear = 0
                            logger.debug("Cookies cleared (periodic)")
                            await self._navigate_to_site()
                        except Exception as e:
                            logger.warning(f"Cookie clearing failed: {e}")

                for attempt in range(max_attempts):
                    try:
                        # Check page health and recover if needed
                        if not self.client.is_page_alive():
                            logger.warning("Page is dead before query -- recovering")
                            if self.client.is_browser_alive():
                                await self.client.recover_page()
                            else:
                                await self.client.reconnect()
                            await self._navigate_to_site()
                            await asyncio.sleep(random.uniform(1.0, 3.0))

                        # Rate limiting on non-first queries or retries
                        if i > 1 or attempt > 0:
                            await self._rate_limit()

                        # Execute query and evaluate
                        record = await asyncio.wait_for(
                            self._process_query(query),
                            timeout=90,
                        )
                        self.records.append(record)

                        # Save record to JSONL
                        self._save_record(record)

                        # Signal success for adaptive throttle
                        self._signal_success()
                        break  # success -- exit retry loop

                    except asyncio.TimeoutError:
                        logger.error(
                            f"Query '{query.text}' timed out after 90s "
                            f"(attempt {attempt + 1}/{max_attempts}) -- skipping"
                        )
                        self._signal_resistance()
                        break  # Don't retry timeouts -- move to next query

                    except ChallengeDetectedError as e:
                        self._signal_resistance()
                        is_last_attempt = attempt >= max_attempts - 1
                        if not is_last_attempt:
                            logger.warning(
                                f"Challenge detected for '{query.text}' "
                                f"(attempt {attempt + 1}/{max_attempts}): {e} -- "
                                "clearing cookies and retrying with increased backoff"
                            )
                            # Clear cookies before retry on challenge
                            try:
                                await self.client.clear_cookies()
                            except Exception:
                                pass
                            # Use 3x backoff multiplier for challenges
                            backoff = self._compute_backoff(attempt) * 3
                            await asyncio.sleep(backoff)
                            await self._navigate_to_site()
                        else:
                            logger.error(
                                f"Challenge persists for '{query.text}' after "
                                f"{max_attempts} attempts -- skipping"
                            )
                            break

                    except Exception as e:
                        error_kind = classify_error(e)
                        retryable = is_retryable(error_kind)
                        is_last_attempt = attempt >= max_attempts - 1

                        if retryable and not is_last_attempt:
                            self._signal_resistance()
                            logger.warning(
                                f"Query '{query.text}' failed (attempt {attempt + 1}/{max_attempts},"
                                f" {error_kind.value}): {e} -- retrying"
                            )
                            await self._recover_for_retry(error_kind)
                            backoff = self._compute_backoff(attempt)
                            await asyncio.sleep(backoff)
                        else:
                            logger.error(
                                f"Failed to process query '{query.text}' "
                                f"(attempt {attempt + 1}/{max_attempts}, "
                                f"{error_kind.value}): {e}",
                                exc_info=True,
                            )
                            break  # non-retryable or exhausted attempts

        # Run expert panel for site-level insights
        expert_insights = []
        if self.records:
            try:
                expert_panel = ExpertPanel(self.config.llm, rate_limiter=llm_rate_limiter)
                site_name = str(self.config.site.url)
                expert_insights = await expert_panel.evaluate(self.records, site_name)
                logger.info(f"Expert panel complete: {len(expert_insights)} insights generated")
            except Exception as e:
                logger.error(f"Expert panel failed: {e}")

        # Generate reports
        if self.records:
            self.reporter.generate_reports(self.records, expert_insights=expert_insights)

        logger.info(f"Audit complete. Processed {len(self.records)}/{len(self.queries)} queries")
        return self.records

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

    async def _recover_for_retry(self, error_kind: BrowserErrorKind) -> None:
        """Recover the browser/page based on error classification.

        Args:
            error_kind: The classified error kind.
        """
        if not self.client:
            return

        if error_kind == BrowserErrorKind.BROWSER_DEAD:
            await self.client.reconnect()
            await self._navigate_to_site()
        elif error_kind in (
            BrowserErrorKind.PAGE_CLOSED,
            BrowserErrorKind.TIMEOUT,
            BrowserErrorKind.TRANSIENT,
        ):
            if self.client.is_browser_alive():
                await self.client.recover_page()
                await self._navigate_to_site()
            else:
                await self.client.reconnect()
                await self._navigate_to_site()

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

    async def _navigate_to_site(self) -> None:
        """Navigate to the site and handle initial modals."""
        if not self.client:
            raise RuntimeError("Browser client not initialized")

        logger.info(f"Navigating to {self.config.site.url}")

        # Use "domcontentloaded" instead of "networkidle" for faster, more reliable loading
        # Some sites (especially heavy SPAs) never reach "networkidle"
        await self.client.navigate(str(self.config.site.url), wait_until="domcontentloaded")

        # Wait for JavaScript to render (important for SPAs and dynamic content)
        logger.debug("Waiting for page JavaScript to render...")
        await asyncio.sleep(3)  # Initial wait for JS frameworks to bootstrap
        await self.client.wait_for_network_idle(timeout=self.config.run.network_idle_ms)

        # Handle modals (cookie consent, popups, etc.)
        modal_handler = ModalHandler(self.client, self.config.site.modals)
        await modal_handler.dismiss_modals()

        # Wait again after dismissing modals for any animations/transitions
        await asyncio.sleep(1)
        await modal_handler.wait_for_page_stable()

        logger.info("Site loaded and ready")

    async def _process_query(self, query: Query) -> AuditRecord:
        """Process a single query.

        Args:
            query: Query to process

        Returns:
            AuditRecord with results and evaluation

        Raises:
            ChallengeDetectedError: If a bot-detection challenge is detected.
        """
        if not self.client:
            raise RuntimeError("Browser client not initialized")
        if not self.judge:
            raise RuntimeError("Judge not initialized")

        # Use direct URL navigation if a search_url_template is configured
        if self.config.site.search.search_url_template:
            from urllib.parse import quote_plus

            search_url = self.config.site.search.search_url_template.replace(
                "{query}", quote_plus(query.text)
            )
            logger.info(f"Navigating directly to search URL: {search_url}")
            await self.client.navigate(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            # Dismiss any modals on the search results page
            modal_handler = ModalHandler(self.client, self.config.site.modals)
            await modal_handler.dismiss_modals()
        else:
            # Dismiss any modals that might be blocking the search box
            modal_handler = ModalHandler(self.client, self.config.site.modals)
            await modal_handler.dismiss_modals()

            # Find and submit search
            search_finder = SearchBoxFinder(
                self.client,
                self.config.site.search,
                llm_config=self.config.llm,
                use_intelligent_fallback=self.config.site.search.use_intelligent_fallback,
            )
            success = await search_finder.submit_search(query.text)

            if not success:
                raise RuntimeError(f"Failed to submit search for query: {query.text}")

        # Wait for results
        await asyncio.sleep(self.config.run.post_submit_ms / 1000)
        await self.client.wait_for_network_idle(timeout=self.config.run.network_idle_ms)

        # Challenge detection: check for bot-detection pages before extraction
        challenge = await detect_challenge(self.client)
        if challenge.detected:
            raise ChallengeDetectedError(challenge)

        # Scroll to load all results before extraction (benefits both paths)
        results_extractor = ResultsExtractor(
            self.client,
            self.config.site.results,
            str(self.config.site.url),
        )
        no_results = await results_extractor.check_for_no_results()
        if no_results:
            logger.warning(f"No results found for query: {query.text}")

        if not no_results:
            await self._scroll_for_results(results_extractor, self.config.run.top_k)

        # Extract results -- vision-based or CSS-based with vision fallback
        items: list[ResultItem] = []
        if self.config.run.use_vision_extraction and not no_results:
            # Vision-first: use LLM to extract results from full-page screenshot
            from ..extractors.vision_results import VisionResultsExtractor

            vision_extractor = VisionResultsExtractor(self.client, self.config.llm)
            items = await vision_extractor.extract_results(top_k=self.config.run.top_k)
        elif not no_results:
            # CSS-first: use DOM selectors with vision fallback
            items = await results_extractor.extract_results(top_k=self.config.run.top_k)

            # Vision fallback: if CSS extracted no items or items with no content
            has_content = any(item.title or item.price for item in items)
            if not items or not has_content:
                reason = (
                    "CSS extraction returned no items"
                    if not items
                    else "CSS extraction returned items with no content"
                )
                logger.warning(f"{reason} -- falling back to vision extraction")
                from ..extractors.vision_results import VisionResultsExtractor

                vision_extractor = VisionResultsExtractor(self.client, self.config.llm)
                items = await vision_extractor.extract_results(top_k=self.config.run.top_k)

        # Signal resistance if empty results on a non-empty query
        if not items and not no_results:
            self._signal_resistance()

        # Capture artifacts (safely -- screenshot/HTML failure shouldn't kill the query)
        page_artifacts = await self._capture_artifacts(query)

        # Get HTML content
        html_content = await self.client.get_html()

        # Evaluate with LLM judge
        current_url = await self.client.evaluate("window.location.href")
        judge_score = await self.judge.evaluate(
            query=query,
            results=items,
            page_url=current_url or str(self.config.site.url),
            html_content=html_content,
            site_name=str(self.config.site.url),
            locale=self.config.site.locale,
        )

        # Create audit record
        record = AuditRecord(
            site=str(self.config.site.url),
            query=query,
            items=items,
            page=page_artifacts,
            judge=judge_score,
        )

        return record

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
                if result and str(result).lower() == "true":
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

        # Get current URL (safe)
        try:
            current_url = await self.client.evaluate("window.location.href")
        except Exception:
            current_url = None

        return PageArtifacts(
            url=str(self.config.site.url),
            final_url=current_url or str(self.config.site.url),
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
    records = await orchestrator.run()

    return records

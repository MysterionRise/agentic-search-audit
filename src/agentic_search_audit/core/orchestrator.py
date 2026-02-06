"""Main orchestrator for search audit."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from ..browser import PlaywrightBrowserClient
from ..extractors import ModalHandler, ResultsExtractor, SearchBoxFinder
from ..judge import SearchQualityJudge
from ..report import ReportGenerator
from .compliance import ComplianceChecker, RobotsPolicy
from .config import get_run_dir
from .types import AuditConfig, AuditRecord, BrowserClient, PageArtifacts, Query

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

    async def run(self) -> list[AuditRecord]:
        """Run the complete audit.

        Returns:
            List of audit records
        """
        logger.info(f"Starting audit with {len(self.queries)} queries")
        logger.info(f"Output directory: {self.run_dir}")

        # Initialize components - using Playwright for reliable browser automation
        self.client = PlaywrightBrowserClient(
            headless=self.config.run.headless,
            viewport_width=self.config.run.viewport_width,
            viewport_height=self.config.run.viewport_height,
        )
        self.judge = SearchQualityJudge(self.config.llm)
        self.reporter = ReportGenerator(self.config, self.run_dir)

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

            # Process each query
            for i, query in enumerate(self.queries, 1):
                logger.info(f"Processing query {i}/{len(self.queries)}: {query.text}")

                try:
                    # Rate limiting
                    if i > 1:
                        await self._rate_limit()

                    # Execute query and evaluate
                    record = await self._process_query(query)
                    self.records.append(record)

                    # Save record to JSONL
                    self._save_record(record)

                except Exception as e:
                    logger.error(f"Failed to process query '{query.text}': {e}", exc_info=True)
                    continue

        # Generate reports
        if self.records:
            self.reporter.generate_reports(self.records)

        logger.info(f"Audit complete. Processed {len(self.records)}/{len(self.queries)} queries")
        return self.records

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
        """
        if not self.client:
            raise RuntimeError("Browser client not initialized")
        if not self.judge:
            raise RuntimeError("Judge not initialized")

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

        # Scroll down to trigger lazy loading of product cards
        await self.client.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(1)
        await self.client.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

        # Extract results
        results_extractor = ResultsExtractor(
            self.client,
            self.config.site.results,
            str(self.config.site.url),
        )

        # Check for no results
        if await results_extractor.check_for_no_results():
            logger.warning(f"No results found for query: {query.text}")
            items = []
        else:
            items = await results_extractor.extract_results(top_k=self.config.run.top_k)

        # Capture artifacts
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

    async def _capture_artifacts(self, query: Query) -> PageArtifacts:
        """Capture page artifacts (screenshot, HTML).

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

        # Screenshot
        screenshot_path = self.run_dir / "screenshots" / f"{query.id}_{safe_query}.png"
        await self.client.screenshot(screenshot_path, full_page=True)

        # HTML snapshot
        html_path = self.run_dir / "html_snapshots" / f"{query.id}_{safe_query}.html"
        html_content = await self.client.get_html()
        html_path.write_text(html_content, encoding="utf-8")

        # Get current URL
        current_url = await self.client.evaluate("window.location.href")

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
        """Apply rate limiting between requests."""
        if self.config.run.throttle_rps > 0:
            delay = 1.0 / self.config.run.throttle_rps
            logger.debug(f"Rate limiting: waiting {delay:.2f}s")
            await asyncio.sleep(delay)


async def run_audit(
    config: AuditConfig,
    queries: list[Query],
    output_dir: str | None = None,
) -> list[AuditRecord]:
    """Run a complete search audit.

    Args:
        config: Audit configuration
        queries: List of queries to evaluate
        output_dir: Custom output directory (optional)

    Returns:
        List of audit records
    """
    # Create run directory
    if output_dir:
        run_dir = Path(output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "screenshots").mkdir(exist_ok=True)
        (run_dir / "html_snapshots").mkdir(exist_ok=True)
    else:
        base_dir = Path(config.report.out_dir)
        site_name = config.site.url.host or "unknown"
        run_dir = get_run_dir(base_dir, site_name)

    # Create orchestrator and run
    orchestrator = SearchAuditOrchestrator(config, queries, run_dir)
    records = await orchestrator.run()

    return records

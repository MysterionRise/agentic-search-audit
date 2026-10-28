#!/usr/bin/env python
"""Backend spike: measure every browser backend on the configured sites (issue #22).

For each site x backend x query it runs the audit's core steps one by one and records
works / partial / fails with timing, so docs/BROWSER_BACKENDS.md can be filled with
numbers instead of opinions. No LLM calls are made.

    uv run python scripts/backend_spike.py --sites nike,amazon,ebay \\
        --backends undetected,chrome_devtools_mcp,kimi_webbridge --queries 3 \\
        --bridge-mode autoconnect --out docs/spike/$(date +%Y%m%d)

Bridge backends need their one-time setup (see docs/BROWSER_BACKENDS.md). Use
``--bridge-mode launch`` to let chrome_devtools_mcp start its own Chrome.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import logging
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from agentic_search_audit.browser.challenge_detector import detect_challenge  # noqa: E402
from agentic_search_audit.browser.factory import create_browser_client  # noqa: E402
from agentic_search_audit.cli.main import load_queries  # noqa: E402
from agentic_search_audit.core.config import load_config  # noqa: E402
from agentic_search_audit.core.types import (  # noqa: E402
    AuditConfig,
    BrowserClient,
    Query,
    QueryOrigin,
    get_capabilities,
)
from agentic_search_audit.extractors import (  # noqa: E402
    ModalHandler,
    ResultsExtractor,
    SearchBoxFinder,
)

logger = logging.getLogger("backend_spike")

FALLBACK_QUERIES = ["running shoes", "laptop", "jeans"]
STEPS = [
    "navigate",
    "consent",
    "challenge",
    "search_box",
    "submit",
    "results_wait",
    "screenshot",
    "html",
    "extract_top10",
    "challenge_after",
    "snapshot_tokens",
]


@dataclass
class StepResult:
    step: str
    status: str  # works | partial | fails | skipped
    ms: int
    detail: str = ""


@dataclass
class QueryRun:
    site: str
    backend: str
    query: str
    steps: list[StepResult] = field(default_factory=list)
    challenge_before: str | None = None
    challenge_after: str | None = None
    results: int = 0
    html_chars: int | None = None
    screenshot_bytes: int | None = None
    snapshot_tokens: int | None = None
    total_ms: int = 0

    def status_of(self, step: str) -> str:
        for result in self.steps:
            if result.step == step:
                return result.status
        return "skipped"


class Ladder:
    """Runs the step ladder for one query and records every rung."""

    def __init__(self, config: AuditConfig, client: BrowserClient, out_dir: Path) -> None:
        self.config = config
        self.client = client
        self.out_dir = out_dir
        self.modals = ModalHandler(client, config.site.modals)
        self.results = ResultsExtractor(client, config.site.results, str(config.site.url))

    async def step(
        self, run: QueryRun, name: str, fn: Callable[[], Awaitable[tuple[str, str]]]
    ) -> str:
        started = time.monotonic()
        try:
            status, detail = await fn()
        except Exception as exc:  # the rung failed; the ladder decides whether to go on
            status, detail = "fails", f"{type(exc).__name__}: {str(exc)[:160]}"
        ms = int((time.monotonic() - started) * 1000)
        run.steps.append(StepResult(name, status, ms, detail))
        logger.info(f"  {name:<16} {status:<8} {ms:>6} ms  {detail}")
        return status

    async def run(self, query: Query, index: int) -> QueryRun:
        config, client = self.config, self.client
        run = QueryRun(
            site=config.site.url.host or "",
            backend=config.run.browser_backend.value,
            query=query.text,
        )
        started = time.monotonic()
        template = config.site.search.search_url_template

        async def navigate() -> tuple[str, str]:
            await client.navigate(str(config.site.url), wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await client.wait_for_network_idle(timeout=config.run.network_idle_ms)
            return "works", await client.evaluate("document.title") or ""  # type: ignore[return-value]

        if await self.step(run, "navigate", navigate) == "fails":
            run.total_ms = int((time.monotonic() - started) * 1000)
            return run

        async def consent() -> tuple[str, str]:
            dismissed = await self.modals.dismiss_modals()
            overlay = await self.modals._check_modal_overlay()
            if overlay:
                return "partial", f"dismissed={dismissed}, an overlay is still visible"
            return "works", f"dismissed={dismissed}"

        await self.step(run, "consent", consent)

        async def challenge() -> tuple[str, str]:
            detection = await detect_challenge(client)
            if detection.detected:
                run.challenge_before = detection.challenge_type
                return "fails", detection.message[:120]
            return "works", "no challenge"

        if await self.step(run, "challenge", challenge) == "fails":
            run.total_ms = int((time.monotonic() - started) * 1000)
            return run

        if template:
            run.steps.append(StepResult("search_box", "skipped", 0, "search_url_template"))
        else:
            finder = SearchBoxFinder(
                client, config.site.search, llm_config=config.llm, use_intelligent_fallback=False
            )

            async def search_box() -> tuple[str, str]:
                selector = await finder.find_search_box()
                return ("works", selector) if selector else ("fails", "no selector matched")

            if await self.step(run, "search_box", search_box) == "fails":
                run.total_ms = int((time.monotonic() - started) * 1000)
                return run

        async def submit() -> tuple[str, str]:
            if template:
                from urllib.parse import quote_plus

                url = template.replace("{query}", quote_plus(query.text))
                await client.navigate(url, wait_until="domcontentloaded")
                return "works", url
            finder = SearchBoxFinder(
                client, config.site.search, llm_config=config.llm, use_intelligent_fallback=False
            )
            ok = await finder.submit_search(query.text)
            return ("works", "submitted") if ok else ("fails", "submit_search returned False")

        if await self.step(run, "submit", submit) == "fails":
            run.total_ms = int((time.monotonic() - started) * 1000)
            return run

        async def results_wait() -> tuple[str, str]:
            await asyncio.sleep(config.run.post_submit_ms / 1000)
            await client.wait_for_network_idle(timeout=config.run.network_idle_ms)
            deadline = time.monotonic() + 15
            count = 0
            while time.monotonic() < deadline:
                count = await self.results.count_visible_results()
                if count > 0:
                    break
                await asyncio.sleep(1)
            if count == 0:
                return "fails", "no result items became visible within 15s"
            if count < config.run.top_k:
                return "partial", f"{count} items visible"
            return "works", f"{count} items visible"

        await self.step(run, "results_wait", results_wait)

        async def screenshot() -> tuple[str, str]:
            path = self.out_dir / "screenshots" / f"{run.site}_{run.backend}_{index}.png"
            await client.screenshot(path, full_page=True)
            run.screenshot_bytes = path.stat().st_size if path.exists() else 0
            if not run.screenshot_bytes:
                return "fails", "empty file"
            return "works", f"{run.screenshot_bytes} bytes"

        await self.step(run, "screenshot", screenshot)

        async def html() -> tuple[str, str]:
            content = await client.get_html()
            run.html_chars = len(content)
            return ("works" if run.html_chars > 1000 else "partial"), f"{run.html_chars} chars"

        await self.step(run, "html", html)

        async def extract() -> tuple[str, str]:
            items = await self.results.extract_results(top_k=config.run.top_k)
            run.results = len(items)
            with_content = sum(1 for item in items if item.title or item.price)
            if not items:
                return "fails", "0 items"
            if len(items) < config.run.top_k or with_content < len(items):
                return "partial", f"{len(items)} items, {with_content} with title or price"
            return "works", f"{len(items)} items"

        await self.step(run, "extract_top10", extract)

        async def challenge_after() -> tuple[str, str]:
            detection = await detect_challenge(client)
            if detection.detected:
                run.challenge_after = detection.challenge_type
                return "fails", detection.message[:120]
            return "works", "no challenge"

        await self.step(run, "challenge_after", challenge_after)

        async def snapshot_tokens() -> tuple[str, str]:
            caps = get_capabilities(client)
            transport = getattr(client, "transport", None)
            if not caps.snapshot or transport is None:
                return "skipped", "backend has no accessibility snapshot"
            text = await transport.snapshot()
            run.snapshot_tokens = len(text) // 4
            return "works", f"~{run.snapshot_tokens} tokens"

        await self.step(run, "snapshot_tokens", snapshot_tokens)

        run.total_ms = int((time.monotonic() - started) * 1000)
        return run


def site_queries(site: str, count: int) -> list[Query]:
    path = REPO / "data" / "queries" / f"{site}.json"
    queries = load_queries(path) if path.exists() else []
    if not queries:
        queries = [
            Query(id=f"q{i:03d}", text=text, origin=QueryOrigin.PREDEFINED)
            for i, text in enumerate(FALLBACK_QUERIES, 1)
        ]
    return queries[:count]


def site_config(site: str, backend: str, args: argparse.Namespace) -> AuditConfig:
    overrides: dict[str, Any] = {
        "run": {
            "browser_backend": backend,
            "headless": args.headless,
            "bridge": {"mode": args.bridge_mode},
        },
        "site": {"search": {"use_intelligent_fallback": False}},
    }
    return load_config(
        site_config_path=REPO / "configs" / "sites" / f"{site}.yaml", overrides=overrides
    )


async def run_backend(
    site: str, backend: str, args: argparse.Namespace, out_dir: Path
) -> list[QueryRun]:
    config = site_config(site, backend, args)
    queries = site_queries(site, args.queries)
    logger.info(f"== {site} x {backend}: {len(queries)} queries")
    runs: list[QueryRun] = []
    client = create_browser_client(config.run, locale=config.site.locale)
    try:
        async with client:
            ladder = Ladder(config, client, out_dir)
            for index, query in enumerate(queries, 1):
                logger.info(f"-- query {index}: {query.text}")
                try:
                    run = await asyncio.wait_for(
                        ladder.run(query, index), timeout=args.query_timeout
                    )
                except asyncio.TimeoutError:
                    run = QueryRun(
                        site=config.site.url.host or "", backend=backend, query=query.text
                    )
                    run.steps.append(
                        StepResult(
                            "timeout", "fails", args.query_timeout * 1000, "query budget exceeded"
                        )
                    )
                runs.append(run)
                _append(out_dir / "results.jsonl", run)
    except Exception as exc:
        run = QueryRun(site=site, backend=backend, query="(connect)")
        run.steps.append(
            StepResult("connect", "fails", 0, f"{type(exc).__name__}: {str(exc)[:300]}")
        )
        logger.error(f"  connect          fails   {run.steps[0].detail}")
        runs.append(run)
        _append(out_dir / "results.jsonl", run)
    return runs


def _append(path: Path, run: QueryRun) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(run)) + "\n")


def _cell(runs: list[QueryRun], step: str) -> str:
    statuses = [run.status_of(step) for run in runs]
    if all(s == "skipped" for s in statuses):
        return "–"
    if any(s == "fails" for s in statuses):
        return "F"
    if any(s == "partial" for s in statuses):
        return "P"
    return "W"


def summarize(runs: list[QueryRun], environment: dict[str, Any]) -> str:
    groups: dict[tuple[str, str], list[QueryRun]] = {}
    for run in runs:
        groups.setdefault((run.site, run.backend), []).append(run)
    lines = [
        f"# Backend spike {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "W = works, P = partial, F = fails, – = not applicable. One row per site and backend; "
        "Notes carry the first failing step's detail.",
        "",
        "| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | "
        "Top10 | p50 s/query | Snapshot tokens | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (site, backend), group in sorted(groups.items()):
        totals = [r.total_ms / 1000 for r in group if r.total_ms]
        p50 = f"{statistics.median(totals):.1f}" if totals else "–"
        challenge = sorted({c for r in group for c in (r.challenge_before, r.challenge_after) if c})
        tokens = [r.snapshot_tokens for r in group if r.snapshot_tokens]
        notes = ""
        for run in group:
            failing = next((s for s in run.steps if s.status == "fails"), None)
            if failing:
                notes = f"{failing.step}: {failing.detail}"
                break
        lines.append(
            f"| {site} | {backend} | {', '.join(challenge) or 'none'} | {_cell(group, 'navigate')} | "
            f"{_cell(group, 'consent')} | {_cell(group, 'search_box')} | {_cell(group, 'submit')} | "
            f"{_cell(group, 'results_wait')} | {_cell(group, 'screenshot')} | {_cell(group, 'html')} | "
            f"{_cell(group, 'extract_top10')} | {p50} | {int(statistics.median(tokens)) if tokens else '–'} | "
            f"{notes.replace('|', '/')} |"
        )
    lines += ["", "## Environment", ""]
    lines += [f"- {key}: {value}" for key, value in environment.items()]
    return "\n".join(lines) + "\n"


def environment() -> dict[str, Any]:
    info: dict[str, Any] = {"platform": platform.platform(), "python": platform.python_version()}
    try:
        from agentic_search_audit.browser.undetected_client import detect_chrome_version

        info["chrome"] = detect_chrome_version()
    except Exception:
        info["chrome"] = None
    for name in ("playwright", "playwright-stealth", "undetected-chromedriver", "mcp"):
        try:
            info[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            info[name] = None
    try:
        info["node"] = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        info["node"] = None
    pkgs = sorted(
        (Path.home() / ".npm" / "_npx").glob("*/node_modules/chrome-devtools-mcp/package.json")
    )
    info["chrome-devtools-mcp (npx cache)"] = (
        json.loads(pkgs[-1].read_text()).get("version") if pkgs else None
    )
    return info


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--sites", default="nike,amazon,ebay", help="comma-separated site config names"
    )
    parser.add_argument(
        "--backends", default="undetected,chrome_devtools_mcp", help="comma-separated backends"
    )
    parser.add_argument("--queries", type=int, default=3, help="queries per site")
    parser.add_argument(
        "--bridge-mode", default="autoconnect", choices=["autoconnect", "browser_url", "launch"]
    )
    parser.add_argument("--headless", dest="headless", action="store_true", default=False)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--query-timeout", type=int, default=180, help="seconds per query")
    parser.add_argument("--out", default=None, help="output directory (default docs/spike/<date>)")
    args = parser.parse_args()

    out_dir = (
        Path(args.out)
        if args.out
        else REPO / "docs" / "spike" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(out_dir / "spike.log")],
    )
    for noisy in ("agentic_search_audit.extractors", "agentic_search_audit.browser"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    env = environment()
    (out_dir / "environment.json").write_text(json.dumps(env, indent=2))
    runs: list[QueryRun] = []
    for site in args.sites.split(","):
        for backend in args.backends.split(","):
            runs += asyncio.run(run_backend(site.strip(), backend.strip(), args, out_dir))
    summary = summarize(runs, env)
    (out_dir / "summary.md").write_text(summary)
    print("\n" + summary)
    print(f"Written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI entrypoint for search audit."""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from ..core.config import load_config
from ..core.orchestrator import run_audit
from ..core.types import Query, QueryOrigin
from ..generators.query_gen import QueryGenerator

# Load environment variables
load_dotenv()

# Allowed URL schemes to prevent SSRF attacks
ALLOWED_URL_SCHEMES = {"http", "https"}


def validate_url(url: str) -> str:
    """Validate URL to prevent SSRF attacks.

    Args:
        url: URL to validate

    Returns:
        Validated URL

    Raises:
        ValueError: If URL scheme is not allowed or URL is malformed
    """
    try:
        parsed = urlparse(url)

        # Check for valid scheme
        if not parsed.scheme:
            raise ValueError(f"URL must include a scheme (http:// or https://): {url}")

        if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
            raise ValueError(
                f"URL scheme '{parsed.scheme}' is not allowed. "
                f"Only {', '.join(ALLOWED_URL_SCHEMES)} are permitted."
            )

        # Check for valid host
        if not parsed.netloc:
            raise ValueError(f"URL must include a host: {url}")

        # Block localhost/internal IPs in production-like scenarios
        # Note: For legitimate internal audits, this can be bypassed with a flag
        hostname = parsed.hostname or ""
        blocked_hosts = {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",  # nosec B104 - not binding, blocking this address
            "::1",
        }

        # Check for internal IP ranges (basic check)
        if hostname in blocked_hosts:
            raise ValueError(
                f"Cannot audit internal/localhost URLs for security reasons: {url}. "
                "Use --allow-internal flag if this is intentional."
            )

        # Check for internal IP ranges
        if hostname.startswith(
            (
                "10.",
                "192.168.",
                "172.16.",
                "172.17.",
                "172.18.",
                "172.19.",
                "172.20.",
                "172.21.",
                "172.22.",
                "172.23.",
                "172.24.",
                "172.25.",
                "172.26.",
                "172.27.",
                "172.28.",
                "172.29.",
                "172.30.",
                "172.31.",
                "169.254.",
            )
        ):
            raise ValueError(
                f"Cannot audit internal network URLs for security reasons: {url}. "
                "Use --allow-internal flag if this is intentional."
            )

        return url

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid URL '{url}': {e}") from e


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration.

    Args:
        level: Logging level
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_queries(queries_path: Path) -> list[Query]:
    """Load queries from JSON file.

    Args:
        queries_path: Path to queries JSON file

    Returns:
        List of Query objects
    """
    with open(queries_path, encoding="utf-8") as f:
        data = json.load(f)

    queries = []
    if isinstance(data, list):
        # List of query objects or strings
        for i, item in enumerate(data, 1):
            if isinstance(item, str):
                queries.append(
                    Query(
                        id=f"q{i:03d}",
                        text=item,
                        origin=QueryOrigin.PREDEFINED,
                    )
                )
            elif isinstance(item, dict):
                queries.append(Query(**item))
    elif isinstance(data, dict) and "queries" in data:
        # Object with queries array
        for i, item in enumerate(data["queries"], 1):
            if isinstance(item, str):
                queries.append(
                    Query(
                        id=f"q{i:03d}",
                        text=item,
                        origin=QueryOrigin.PREDEFINED,
                    )
                )
            elif isinstance(item, dict):
                queries.append(Query(**item))

    return queries


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Agentic Search Audit - Evaluate on-site search quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run audit on Nike.com with predefined queries
  search-audit --site nike

  # Run with custom config and queries
  search-audit --config configs/sites/custom.yaml --queries data/queries/custom.json

  # Run with specific URL
  search-audit --url https://www.example.com --queries queries.json

  # Run in headed mode (visible browser)
  search-audit --site nike --no-headless

  # Specify custom output directory
  search-audit --site nike --output ./my-audit-results
        """,
    )

    parser.add_argument(
        "--site",
        type=str,
        help="Site name (looks for configs/sites/{site}.yaml)",
    )

    parser.add_argument(
        "--url",
        type=str,
        help="Site URL (overrides config)",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file (default: configs/default.yaml)",
    )

    parser.add_argument(
        "--queries",
        type=Path,
        help="Path to queries JSON file (default: data/queries/{site}.json)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory for results (overrides config)",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run browser in headless mode (default: true)",
    )

    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in headed mode (visible)",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        help="Number of top results to extract (default: 10)",
    )

    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducible LLM outputs",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Ignore robots.txt restrictions (not recommended for production use)",
    )

    parser.add_argument(
        "--auto-generate",
        action="store_true",
        help="Auto-generate queries from homepage using LLM (requires --url)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate queries but don't run audit (useful with --auto-generate)",
    )

    parser.add_argument(
        "--allow-internal",
        action="store_true",
        help="Allow auditing internal/localhost URLs (security risk - use with caution)",
    )

    return parser.parse_args()


async def main_async() -> int:
    """Async main function.

    Returns:
        Exit code
    """
    args = parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        # Determine config path
        config_path = args.config
        site_config_path = None

        if args.site:
            # Look for site-specific config
            site_config_path = Path("configs") / "sites" / f"{args.site}.yaml"
            if not site_config_path.exists():
                logger.error(f"Site config not found: {site_config_path}")
                return 1

        # Build config overrides
        overrides = {}

        if args.url:
            # Validate URL to prevent SSRF
            try:
                if not args.allow_internal:
                    validate_url(args.url)
                else:
                    # Still validate scheme even with --allow-internal
                    parsed = urlparse(args.url)
                    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
                        logger.error(
                            f"URL scheme '{parsed.scheme}' is not allowed. "
                            f"Only {', '.join(ALLOWED_URL_SCHEMES)} are permitted."
                        )
                        return 1
            except ValueError as e:
                logger.error(str(e))
                return 1

            overrides["site"] = {"url": args.url}

        if args.no_headless:
            overrides["run"] = {"headless": False}
        elif args.headless:
            overrides["run"] = {"headless": True}

        if args.top_k:
            if "run" not in overrides:
                overrides["run"] = {}
            overrides["run"]["top_k"] = args.top_k

        if args.seed is not None:
            if "run" not in overrides:
                overrides["run"] = {}
            overrides["run"]["seed"] = args.seed

        if args.ignore_robots:
            overrides["compliance"] = {"respect_robots_txt": False}
            logger.warning("robots.txt compliance disabled by --ignore-robots flag")

        # Load config
        config = load_config(
            config_path=config_path,
            site_config_path=site_config_path,
            overrides=overrides,
        )

        # Handle query generation or loading
        queries: list[Query] = []

        if args.auto_generate:
            if not args.url:
                logger.error("--auto-generate requires --url to be specified")
                return 1

            logger.info("Auto-generating queries from homepage...")

            # Validate URL before fetching (double-check even if already validated above)
            site_url = str(config.site.url)
            if not args.allow_internal:
                try:
                    validate_url(site_url)
                except ValueError as e:
                    logger.error(str(e))
                    return 1

            # Fetch homepage HTML
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(site_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch homepage: HTTP {response.status}")
                        return 1
                    homepage_html = await response.text()

            # Generate queries
            generator = QueryGenerator(config.llm)
            queries = await generator.generate_from_html(homepage_html)

            if not queries:
                logger.error("Failed to generate queries")
                return 1

            logger.info(f"Generated {len(queries)} queries")

            # Save generated queries
            output_dir = args.output or Path(config.report.out_dir)
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            queries_output = output_dir / "generated_queries.json"
            generator.save_queries(queries, str(queries_output))
            logger.info(f"Saved generated queries to {queries_output}")

            # If dry-run, just print queries and exit
            if args.dry_run:
                logger.info("Dry run mode - queries generated but audit not run")
                print("\nGenerated Queries:")
                print("-" * 40)
                for q in queries:
                    print(f"  [{q.id}] {q.text}")
                return 0

        else:
            # Determine queries path
            queries_path = args.queries
            if not queries_path:
                if args.site:
                    queries_path = Path("data") / "queries" / f"{args.site}.json"
                else:
                    logger.error("--queries is required when --site is not specified")
                    return 1

            if not queries_path.exists():
                logger.error(f"Queries file not found: {queries_path}")
                return 1

            # Load queries
            queries = load_queries(queries_path)
            if not queries:
                logger.error("No queries found in file")
                return 1

            logger.info(f"Loaded {len(queries)} queries")

        # Run audit
        records = await run_audit(
            config=config,
            queries=queries,
            output_dir=str(args.output) if args.output else None,
        )

        # Print summary
        if records:
            avg_score = sum(r.judge.fqi for r in records) / len(records)
            logger.info("=" * 60)
            logger.info("AUDIT COMPLETE")
            logger.info("=" * 60)
            logger.info(f"Processed: {len(records)}/{len(queries)} queries")
            logger.info(f"Average FQI score: {avg_score:.2f}/5.00")
            logger.info(f"Results saved to: {config.report.out_dir}")
            logger.info("=" * 60)

            return 0
        else:
            logger.error("No queries were successfully processed")
            return 1

    except KeyboardInterrupt:
        logger.info("Audit interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Audit failed: {e}", exc_info=True)
        return 1


def main() -> None:
    """Main CLI entrypoint."""
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()

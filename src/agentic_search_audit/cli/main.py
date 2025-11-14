"""CLI entrypoint for search audit."""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from ..core.config import load_config
from ..core.orchestrator import run_audit
from ..core.types import Query, QueryOrigin

# Load environment variables
load_dotenv()


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


def load_queries(queries_path: Path) -> List[Query]:
    """Load queries from JSON file.

    Args:
        queries_path: Path to queries JSON file

    Returns:
        List of Query objects
    """
    with open(queries_path, "r", encoding="utf-8") as f:
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

        # Load config
        config = load_config(
            config_path=config_path,
            site_config_path=site_config_path,
            overrides=overrides,
        )

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
            avg_score = sum(r.judge.overall for r in records) / len(records)
            logger.info("=" * 60)
            logger.info("AUDIT COMPLETE")
            logger.info("=" * 60)
            logger.info(f"Processed: {len(records)}/{len(queries)} queries")
            logger.info(f"Average overall score: {avg_score:.2f}/5.00")
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

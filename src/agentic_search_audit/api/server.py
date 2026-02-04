"""Server entry point for running the API."""

import argparse
import logging
import os


def main() -> None:
    """Run the API server."""
    parser = argparse.ArgumentParser(description="Agentic Search Audit API Server")
    parser.add_argument(
        "--host",
        default=os.getenv("AUDIT_HOST", "0.0.0.0"),  # nosec B104 - intentional for container
        help="Host to bind to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("AUDIT_PORT", "8000")),
        help="Port to bind to",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("AUDIT_WORKERS", "1")),
        help="Number of worker processes",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("AUDIT_DEBUG", "false").lower() == "true",
        help="Enable auto-reload",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("AUDIT_LOG_LEVEL", "info"),
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run with uvicorn
    import uvicorn

    uvicorn.run(
        "agentic_search_audit.api.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers if not args.reload else 1,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

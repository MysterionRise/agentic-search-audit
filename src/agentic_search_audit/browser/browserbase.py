"""Browserbase cloud browser session management."""

import logging

logger = logging.getLogger(__name__)


def get_browserbase_endpoint(api_key: str, project_id: str | None = None) -> str:
    """Create a Browserbase session and return the CDP WebSocket URL.

    Args:
        api_key: Browserbase API key.
        project_id: Optional Browserbase project ID.

    Returns:
        CDP WebSocket endpoint URL.

    Raises:
        ImportError: If the browserbase SDK is not installed.
        RuntimeError: If session creation fails.
    """
    try:
        from browserbase import Browserbase  # type: ignore[import-untyped,import-not-found]
    except ImportError:
        raise ImportError(
            "Browserbase SDK not installed. "
            "Install with: pip install 'agentic-search-audit[browserbase]'"
        )

    try:
        bb = Browserbase(api_key=api_key)
        create_kwargs: dict[str, str] = {}
        if project_id:
            create_kwargs["project_id"] = project_id
        session = bb.sessions.create(**create_kwargs)
        ws_url: str = session.connect_url
        logger.info(f"Created Browserbase session: {session.id}")
        return ws_url
    except Exception as e:
        raise RuntimeError(f"Failed to create Browserbase session: {e}") from e

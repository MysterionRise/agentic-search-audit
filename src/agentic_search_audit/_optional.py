"""Checks for optional dependency groups."""

from importlib.util import find_spec

_SAAS_MODULES = ("fastapi", "sqlalchemy", "redis", "jwt", "bcrypt", "prometheus_client")


def missing_saas_modules() -> list[str]:
    """Names of the 'saas' extra's modules that are not importable."""
    return [name for name in _SAAS_MODULES if find_spec(name) is None]


def require_saas() -> None:
    """Raise a clear ImportError when the experimental 'saas' extra is not installed."""
    missing = missing_saas_modules()
    if missing:
        raise ImportError(
            "The API/worker/database layer is experimental and needs the 'saas' extra "
            f"(missing: {', '.join(missing)}). Install with `uv sync --extra saas` "
            "or `pip install 'agentic-search-audit[saas]'`."
        )

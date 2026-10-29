"""FastAPI-based REST API for Agentic Search Audit (experimental; needs the 'saas' extra)."""

from .._optional import require_saas

require_saas()

from .main import app, create_app  # noqa: E402

__all__ = ["app", "create_app"]

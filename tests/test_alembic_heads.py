"""The SaaS schema must have exactly one Alembic head."""

from pathlib import Path

import pytest

# "alembic.config", not "alembic": the repo's alembic/ migrations directory is importable as
# a namespace package even when the real library is absent.
pytest.importorskip(
    "alembic.config", reason="SaaS tests need the 'saas' extra (uv sync --extra saas)"
)

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

pytestmark = pytest.mark.unit


def test_single_alembic_head() -> None:
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["7d2e4f1a9c3b"], heads

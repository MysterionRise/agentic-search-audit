"""Every shipped site config must load under the strict (extra="forbid") models."""

from pathlib import Path

import pytest

from agentic_search_audit.core.config import load_config

SITES_DIR = Path(__file__).parent.parent / "configs" / "sites"
SITE_CONFIGS = sorted(SITES_DIR.glob("*.yaml"))

pytestmark = pytest.mark.unit


def test_site_configs_exist() -> None:
    assert len(SITE_CONFIGS) >= 40


@pytest.mark.parametrize("path", SITE_CONFIGS, ids=[p.stem for p in SITE_CONFIGS])
def test_site_config_loads(path: Path) -> None:
    config = load_config(site_config_path=path)
    assert config.site.url.host
    assert config.run.browser_backend is not None

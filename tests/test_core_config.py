"""Tests for core configuration module."""

import pytest


class TestRunConfig:
    """Test suite for RunConfig."""

    def test_run_config_defaults(self):
        """Test RunConfig has sensible defaults."""
        from agentic_search_audit.core.types import RunConfig

        config = RunConfig()
        assert config.headless is True
        assert config.top_k > 0
        assert config.network_idle_ms > 0

    def test_run_config_custom_values(self):
        """Test RunConfig accepts custom values."""
        from agentic_search_audit.core.types import RunConfig

        config = RunConfig(
            headless=False,
            top_k=5,
            network_idle_ms=2000,
        )
        assert config.headless is False
        assert config.top_k == 5
        assert config.network_idle_ms == 2000


class TestRunConfigProxy:
    """Test suite for RunConfig proxy fields."""

    def test_proxy_defaults_are_none(self):
        from agentic_search_audit.core.types import ProxyRotationStrategy, RunConfig

        config = RunConfig()
        assert config.proxy_url is None
        assert config.proxy_rotation_strategy == ProxyRotationStrategy.NONE
        assert config.proxy_list is None

    def test_proxy_url_accepted(self):
        from agentic_search_audit.core.types import RunConfig

        config = RunConfig(proxy_url="http://proxy:8080")
        assert config.proxy_url == "http://proxy:8080"

    def test_rotation_per_site_requires_proxy_list(self):
        from agentic_search_audit.core.types import RunConfig

        with pytest.raises(ValueError, match="proxy_list.*at least 2"):
            RunConfig(proxy_rotation_strategy="per-site")

    def test_rotation_per_query_requires_proxy_list(self):
        from agentic_search_audit.core.types import RunConfig

        with pytest.raises(ValueError, match="proxy_list.*at least 2"):
            RunConfig(proxy_rotation_strategy="per-query", proxy_list=["http://one:8080"])

    def test_rotation_per_site_with_valid_list(self):
        from agentic_search_audit.core.types import ProxyRotationStrategy, RunConfig

        config = RunConfig(
            proxy_rotation_strategy="per-site",
            proxy_list=["http://a:8080", "http://b:8080"],
        )
        assert config.proxy_rotation_strategy == ProxyRotationStrategy.PER_SITE
        assert len(config.proxy_list) == 2

    def test_rotation_none_allows_no_list(self):
        from agentic_search_audit.core.types import ProxyRotationStrategy, RunConfig

        config = RunConfig(proxy_rotation_strategy="none")
        assert config.proxy_rotation_strategy == ProxyRotationStrategy.NONE


class TestSiteConfig:
    """Test suite for SiteConfig."""

    def test_site_config_requires_url(self):
        """Test SiteConfig requires a URL."""
        from agentic_search_audit.core.types import SiteConfig

        config = SiteConfig(url="https://example.com")
        assert "example.com" in str(config.url)

    def test_site_config_with_locale(self):
        """Test SiteConfig can have locale."""
        from agentic_search_audit.core.types import SiteConfig

        config = SiteConfig(
            url="https://example.com",
            locale="de-DE",
        )
        assert config.locale == "de-DE"


class TestLLMConfig:
    """Test suite for LLMConfig."""

    def test_llm_config_defaults(self):
        """Test LLMConfig has defaults."""
        from agentic_search_audit.core.types import LLMConfig

        config = LLMConfig()
        assert config.provider is not None

    def test_llm_config_model(self):
        """Test LLMConfig can specify model."""
        from agentic_search_audit.core.types import LLMConfig

        config = LLMConfig(model="gpt-4")
        assert config.model == "gpt-4"


class TestReportConfig:
    """Test suite for ReportConfig."""

    def test_report_config_defaults(self):
        """Test ReportConfig has defaults."""
        from agentic_search_audit.core.types import ReportConfig

        config = ReportConfig()
        assert isinstance(config.formats, list)


class TestAuditConfig:
    """Test suite for AuditConfig."""

    def test_audit_config_requires_site(self):
        """Test AuditConfig requires site config."""
        from agentic_search_audit.core.types import AuditConfig, SiteConfig

        site = SiteConfig(url="https://example.com")
        config = AuditConfig(site=site)
        assert "example.com" in str(config.site.url)

    def test_audit_config_has_run_defaults(self):
        """Test AuditConfig has RunConfig defaults."""
        from agentic_search_audit.core.types import AuditConfig, SiteConfig

        site = SiteConfig(url="https://example.com")
        config = AuditConfig(site=site)
        assert config.run.headless is True

    def test_audit_config_serialization(self):
        """Test AuditConfig can be serialized."""
        from agentic_search_audit.core.types import AuditConfig, SiteConfig

        site = SiteConfig(url="https://example.com")
        config = AuditConfig(site=site)
        config_dict = config.model_dump()
        assert isinstance(config_dict, dict)
        assert "site" in config_dict


class TestSearchConfig:
    """Test suite for SearchConfig."""

    def test_search_config_defaults(self):
        """Test SearchConfig has default selectors."""
        from agentic_search_audit.core.types import SearchConfig

        config = SearchConfig()
        assert len(config.input_selectors) > 0

    def test_search_config_submit_strategy(self):
        """Test SearchConfig submit strategy."""
        from agentic_search_audit.core.types import SearchConfig

        config = SearchConfig()
        assert config.submit_strategy in ["enter", "clickSelector"]


class TestResultsConfig:
    """Test suite for ResultsConfig."""

    def test_results_config_defaults(self):
        """Test ResultsConfig has default selectors."""
        from agentic_search_audit.core.types import ResultsConfig

        config = ResultsConfig()
        assert len(config.item_selectors) > 0
        assert len(config.title_selectors) > 0


class TestEnvironmentConfig:
    """Test environment-based configuration."""

    def test_api_settings_defaults(self):
        """Test APISettings has defaults."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.environment in ["development", "staging", "production"]

    def test_database_url_has_value(self):
        """Test database URL is set."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.database_url is not None

    def test_redis_url_has_value(self):
        """Test Redis URL is set."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.redis_url is not None

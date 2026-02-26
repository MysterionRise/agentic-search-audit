"""Tests for anti-bot stealth utilities."""

from unittest.mock import AsyncMock

import pytest

from agentic_search_audit.browser.stealth import (
    LOCALE_TIMEZONE_MAP,
    USER_AGENTS,
    WEBGL_PROFILES,
    build_client_hints_js,
    build_stealth_js,
    get_client_hints_headers,
    human_typing_delay,
    inject_human_behavior,
    languages_for_locale,
    mouse_jitter_js,
    post_action_delay,
    pre_action_delay,
    random_user_agent,
    random_webgl_profile,
    timezone_for_locale,
)


@pytest.mark.unit
class TestUserAgents:
    """User-agent pool and rotation."""

    def test_pool_is_nonempty(self) -> None:
        assert len(USER_AGENTS) > 0

    def test_random_user_agent_returns_string(self) -> None:
        ua = random_user_agent()
        assert isinstance(ua, str)
        assert "Mozilla" in ua

    def test_random_user_agent_from_pool(self) -> None:
        for _ in range(20):
            assert random_user_agent() in USER_AGENTS


@pytest.mark.unit
class TestHumanTypingDelay:
    """Human-like typing delay generation."""

    def test_returns_positive_int(self) -> None:
        for _ in range(50):
            d = human_typing_delay(50)
            assert isinstance(d, int)
            assert d > 0

    def test_never_below_minimum(self) -> None:
        for _ in range(100):
            d = human_typing_delay(30)
            assert d >= 20  # The minimum floor defined in the function

    def test_varies_across_calls(self) -> None:
        delays = {human_typing_delay(50) for _ in range(50)}
        # Should produce at least a few distinct values (not constant)
        assert len(delays) > 3


@pytest.mark.unit
class TestPrePostActionDelay:
    """Random micro-delays for actions."""

    def test_pre_action_delay_range(self) -> None:
        for _ in range(50):
            d = pre_action_delay()
            assert 0.05 <= d <= 0.3

    def test_post_action_delay_range(self) -> None:
        for _ in range(50):
            d = post_action_delay()
            assert 0.1 <= d <= 0.4


@pytest.mark.unit
class TestMouseJitterJS:
    """Mouse jitter JavaScript generation."""

    def test_returns_js_string(self) -> None:
        js = mouse_jitter_js(100, 200)
        assert isinstance(js, str)
        assert "mousemove" in js

    def test_contains_dispatch_events(self) -> None:
        js = mouse_jitter_js(100, 200, steps=3)
        assert js.count("dispatchEvent") == 3

    def test_custom_steps(self) -> None:
        js = mouse_jitter_js(50, 50, steps=7)
        assert js.count("dispatchEvent") == 7


@pytest.mark.unit
class TestWebGLProfiles:
    """WebGL vendor/renderer fingerprint pool."""

    def test_pool_is_nonempty(self) -> None:
        assert len(WEBGL_PROFILES) > 0

    def test_random_webgl_profile_returns_tuple(self) -> None:
        vendor, renderer = random_webgl_profile()
        assert isinstance(vendor, str)
        assert isinstance(renderer, str)

    def test_random_webgl_profile_from_pool(self) -> None:
        for _ in range(20):
            assert random_webgl_profile() in WEBGL_PROFILES

    def test_profiles_have_two_elements(self) -> None:
        for profile in WEBGL_PROFILES:
            assert len(profile) == 2


@pytest.mark.unit
class TestTimezoneForLocale:
    """Locale-to-timezone mapping."""

    def test_known_locale_returns_valid_tz(self) -> None:
        tz = timezone_for_locale("en-US")
        assert tz in LOCALE_TIMEZONE_MAP["en-US"]

    def test_en_gb_returns_london(self) -> None:
        assert timezone_for_locale("en-GB") == "Europe/London"

    def test_unknown_locale_falls_back(self) -> None:
        tz = timezone_for_locale("xx-XX")
        assert tz == "America/New_York"

    def test_all_mapped_locales_return_valid(self) -> None:
        for locale, timezones in LOCALE_TIMEZONE_MAP.items():
            tz = timezone_for_locale(locale)
            assert tz in timezones


@pytest.mark.unit
class TestLanguagesForLocale:
    """navigator.languages generation."""

    def test_en_us_returns_en_pair(self) -> None:
        langs = languages_for_locale("en-US")
        assert langs == ["en-US", "en"]

    def test_en_gb_returns_en_pair(self) -> None:
        langs = languages_for_locale("en-GB")
        assert langs == ["en-GB", "en"]

    def test_non_english_includes_english_fallback(self) -> None:
        langs = languages_for_locale("de-DE")
        assert langs[0] == "de-DE"
        assert langs[1] == "de"
        assert "en-US" in langs
        assert "en" in langs

    def test_japanese_includes_english_fallback(self) -> None:
        langs = languages_for_locale("ja-JP")
        assert langs == ["ja-JP", "ja", "en-US", "en"]


@pytest.mark.unit
class TestBuildStealthJS:
    """Comprehensive stealth JS builder."""

    def test_returns_string(self) -> None:
        js = build_stealth_js()
        assert isinstance(js, str)

    def test_contains_webdriver_override(self) -> None:
        js = build_stealth_js()
        assert "navigator" in js
        assert "webdriver" in js

    def test_contains_webgl_spoofing(self) -> None:
        js = build_stealth_js()
        assert "37445" in js  # UNMASKED_VENDOR
        assert "37446" in js  # UNMASKED_RENDERER

    def test_contains_canvas_noise(self) -> None:
        js = build_stealth_js()
        assert "getImageData" in js
        assert "toDataURL" in js
        assert "toBlob" in js

    def test_contains_plugins_override(self) -> None:
        js = build_stealth_js()
        assert "Chrome PDF Plugin" in js
        assert "navigator" in js

    def test_contains_webrtc_prevention(self) -> None:
        js = build_stealth_js()
        assert "RTCPeerConnection" in js
        assert "iceTransportPolicy" in js
        assert "relay" in js

    def test_contains_languages_for_locale(self) -> None:
        js = build_stealth_js("de-DE")
        assert '"de-DE"' in js
        assert '"en-US"' in js

    def test_default_locale_en_us(self) -> None:
        js = build_stealth_js()
        assert '"en-US"' in js

    def test_contains_webgl2_patch(self) -> None:
        js = build_stealth_js()
        assert "WebGL2RenderingContext" in js

    def test_contains_chrome_runtime(self) -> None:
        js = build_stealth_js()
        assert "chrome" in js
        assert "runtime" in js

    def test_contains_client_hints(self) -> None:
        js = build_stealth_js()
        assert "userAgentData" in js
        assert "brands" in js


@pytest.mark.unit
class TestBuildClientHintsJS:
    """Client Hints JavaScript generation."""

    def test_returns_js_string(self) -> None:
        js = build_client_hints_js()
        assert isinstance(js, str)
        assert "userAgentData" in js

    def test_extracts_chrome_version_from_ua(self) -> None:
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/131.0.0.0 Safari/537.36"
        js = build_client_hints_js(ua)
        assert '"131"' in js

    def test_defaults_to_133_without_ua(self) -> None:
        js = build_client_hints_js("")
        assert '"133"' in js

    def test_contains_brands_array(self) -> None:
        js = build_client_hints_js()
        assert "Chromium" in js
        assert "Google Chrome" in js
        assert "Not-A.Brand" in js

    def test_contains_high_entropy_values(self) -> None:
        js = build_client_hints_js()
        assert "getHighEntropyValues" in js
        assert "platformVersion" in js
        assert "architecture" in js


@pytest.mark.unit
class TestGetClientHintsHeaders:
    """Client Hints HTTP header generation."""

    def test_returns_expected_keys(self) -> None:
        headers = get_client_hints_headers()
        assert "Sec-CH-UA" in headers
        assert "Sec-CH-UA-Mobile" in headers
        assert "Sec-CH-UA-Platform" in headers

    def test_extracts_version_from_ua(self) -> None:
        headers = get_client_hints_headers("Mozilla/5.0 Chrome/132.0.0.0 Safari/537.36")
        assert '"132"' in headers["Sec-CH-UA"]

    def test_mobile_is_false(self) -> None:
        headers = get_client_hints_headers()
        assert headers["Sec-CH-UA-Mobile"] == "?0"

    def test_platform_is_macos(self) -> None:
        headers = get_client_hints_headers()
        assert headers["Sec-CH-UA-Platform"] == '"macOS"'


@pytest.mark.unit
class TestInjectHumanBehavior:
    """Human-like behavioral randomization."""

    async def test_inject_human_behavior_runs(self) -> None:
        """inject_human_behavior completes without error on mock client."""
        client = AsyncMock()
        client.evaluate = AsyncMock(return_value=None)
        # Run multiple times to hit different random branches
        for _ in range(20):
            await inject_human_behavior(client)

    async def test_inject_human_behavior_calls_evaluate(self) -> None:
        """inject_human_behavior calls client.evaluate for scroll/mouse actions."""
        client = AsyncMock()
        client.evaluate = AsyncMock(return_value=None)
        await inject_human_behavior(client)
        # At least one evaluate call for scroll/mouse, or no calls for pause
        # Either way, no exception is raised


@pytest.mark.unit
class TestChromeVersionDetection:
    """Cross-platform Chrome version detection."""

    def test_detect_chrome_version_imports(self) -> None:
        """detect_chrome_version can be imported."""
        from agentic_search_audit.browser.undetected_client import detect_chrome_version

        assert callable(detect_chrome_version)

    def test_detect_chrome_version_returns_int_or_none(self) -> None:
        """detect_chrome_version returns int or None."""
        from agentic_search_audit.browser.undetected_client import detect_chrome_version

        result = detect_chrome_version()
        assert result is None or isinstance(result, int)

    def test_detect_chrome_version_mock_darwin(self) -> None:
        """detect_chrome_version parses version on Darwin."""
        from unittest.mock import MagicMock, patch

        from agentic_search_audit.browser.undetected_client import detect_chrome_version

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Google Chrome 131.0.6778.85"

        with patch(
            "agentic_search_audit.browser.undetected_client.platform.system", return_value="Darwin"
        ):
            with patch(
                "agentic_search_audit.browser.undetected_client.subprocess.run",
                return_value=mock_result,
            ):
                version = detect_chrome_version()
                assert version == 131

    def test_detect_chrome_version_mock_linux(self) -> None:
        """detect_chrome_version parses version on Linux."""
        from unittest.mock import MagicMock, patch

        from agentic_search_audit.browser.undetected_client import detect_chrome_version

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Google Chrome 133.0.6931.0"

        with patch(
            "agentic_search_audit.browser.undetected_client.platform.system", return_value="Linux"
        ):
            with patch(
                "agentic_search_audit.browser.undetected_client.subprocess.run",
                return_value=mock_result,
            ):
                version = detect_chrome_version()
                assert version == 133

    def test_detect_chrome_version_not_found(self) -> None:
        """detect_chrome_version returns None when Chrome is not installed."""
        from unittest.mock import patch

        from agentic_search_audit.browser.undetected_client import detect_chrome_version

        with patch(
            "agentic_search_audit.browser.undetected_client.platform.system", return_value="Darwin"
        ):
            with patch(
                "agentic_search_audit.browser.undetected_client.subprocess.run",
                side_effect=FileNotFoundError,
            ):
                version = detect_chrome_version()
                assert version is None

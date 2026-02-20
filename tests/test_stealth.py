"""Tests for anti-bot stealth utilities."""

import pytest

from agentic_search_audit.browser.stealth import (
    LOCALE_TIMEZONE_MAP,
    USER_AGENTS,
    WEBGL_PROFILES,
    build_stealth_js,
    human_typing_delay,
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

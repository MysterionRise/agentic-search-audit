"""Tests for the shared evaluate() wrapper and envelope decoder."""

import json

import pytest

from agentic_search_audit.browser._js import MAX_RESULT_CHARS, decode_result, wrap_expression
from agentic_search_audit.browser.errors import BrowserErrorKind, BrowserScriptError, classify_error

pytestmark = pytest.mark.unit


class TestWrapExpression:
    def test_strips_whitespace_and_trailing_semicolons(self) -> None:
        assert wrap_expression("  1 + 1 ;; \n") == wrap_expression("1 + 1")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            wrap_expression("   ;  ")

    def test_expression_sits_on_its_own_line(self) -> None:
        wrapped = wrap_expression("document.title // trailing comment")
        assert "\ndocument.title // trailing comment\n" in wrapped
        assert wrapped.startswith("(() => {")
        assert wrapped.endswith("})()")

    def test_max_chars_substituted(self) -> None:
        assert str(MAX_RESULT_CHARS) in wrap_expression("1")
        assert "12345" in wrap_expression("1", max_chars=12345)
        assert "__MAX__" not in wrap_expression("1")
        assert "__EXPR__" not in wrap_expression("1")

    def test_expression_text_is_not_rewritten(self) -> None:
        expr = "'__MAX__' + '%s' + '{x}'"
        assert ("\n" + expr + "\n") in wrap_expression(expr)


class TestDecodeResult:
    @pytest.mark.parametrize(
        "value",
        [True, False, 0, 1, 1.5, "x", "", [1, "a", None], {"k": "v", "n": [1, 2]}, None],
    )
    def test_ok_values_round_trip(self, value: object) -> None:
        raw = json.dumps({"ok": True, "v": value})
        assert decode_result(raw) == value

    def test_true_is_identity_not_string(self) -> None:
        assert decode_result('{"ok": true, "v": true}') is True
        assert decode_result('{"ok": true, "v": false}') is False
        assert decode_result('{"ok": true, "v": 0}') == 0

    def test_missing_v_is_none(self) -> None:
        assert decode_result('{"ok": true}') is None

    def test_dict_envelope_accepted(self) -> None:
        assert decode_result({"ok": True, "v": {"a": 1}}) == {"a": 1}

    def test_error_envelope_raises_with_details(self) -> None:
        raw = json.dumps(
            {"ok": False, "kind": "script", "name": "TypeError", "message": "boom", "stack": "s"}
        )
        with pytest.raises(BrowserScriptError) as info:
            decode_result(raw)
        err = info.value
        assert err.kind == "script"
        assert err.name == "TypeError"
        assert err.message == "boom"
        assert err.stack == "s"
        assert "TypeError: boom" in str(err)

    @pytest.mark.parametrize("raw", ["not json", "", None, 42, [1, 2], {"v": 1}, "[1, 2]"])
    def test_non_envelope_raises_decode(self, raw: object) -> None:
        with pytest.raises(BrowserScriptError) as info:
            decode_result(raw)
        assert info.value.kind == "decode"

    def test_error_envelope_defaults(self) -> None:
        with pytest.raises(BrowserScriptError) as info:
            decode_result('{"ok": false}')
        assert info.value.kind == "script"
        assert info.value.name == "Error"


class TestClassification:
    def test_script_error_is_permanent(self) -> None:
        assert classify_error(BrowserScriptError("script", "x")) is BrowserErrorKind.PERMANENT

    def test_script_error_mentioning_not_connected_is_still_permanent(self) -> None:
        err = BrowserScriptError("script", "driver not connected")
        assert classify_error(err) is BrowserErrorKind.PERMANENT

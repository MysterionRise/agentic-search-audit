"""Response parsing, error mapping and the Node preflight shared by MCP bridges."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from mcp import types

from agentic_search_audit.browser.bridge.mcp_base import (
    parse_json_block,
    parse_selected_page_id,
    result_is_error,
    result_text,
)
from agentic_search_audit.browser.bridge.node import check_node_version, parse_node_version
from agentic_search_audit.browser.bridge.transport import BridgeEnvironmentError, BridgeToolError

pytestmark = pytest.mark.unit


def _result(text: str, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], isError=is_error
    )


class TestParsing:
    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("42", 42),
            ('"s"', "s"),
            ("true", True),
            ("null", None),
            ('{"a": [1]}', {"a": [1]}),
            ("undefined", None),
            ("", None),
        ],
    )
    def test_parse_json_block(self, body: str, expected: Any) -> None:
        text = f"Script ran on page and returned:\n```json\n{body}\n```\n"
        assert parse_json_block(text) == expected

    def test_parse_json_block_without_block_raises(self) -> None:
        with pytest.raises(BridgeToolError):
            parse_json_block("Script ran on page. Output saved to x.json.")

    def test_parse_json_block_invalid_json_raises(self) -> None:
        with pytest.raises(BridgeToolError):
            parse_json_block("```json\n{oops\n```")

    def test_result_is_error_both_spellings(self) -> None:
        assert result_is_error(_result("x", is_error=True)) is True
        assert result_is_error(_result("x")) is False
        assert result_is_error(SimpleNamespace(is_error=True)) is True
        assert result_is_error(SimpleNamespace()) is False

    def test_result_text_joins_text_items(self) -> None:
        result = types.CallToolResult(
            content=[
                types.TextContent(type="text", text="a"),
                types.ImageContent(type="image", data="AA==", mimeType="image/png"),
                types.TextContent(type="text", text="b"),
            ]
        )
        assert result_text(result) == "a\nb"

    def test_parse_selected_page_id(self) -> None:
        text = (
            "Successfully navigated.\n## Pages\n"
            "1: Shop (https://shop.example/) \n"
            "2: about:blank (about:blank) [selected]\n"
        )
        assert parse_selected_page_id(text) == 2
        assert parse_selected_page_id("## Pages\n1: x (y)\n") is None


class TestNodeCheck:
    def test_parse_node_version(self) -> None:
        assert parse_node_version("v20.18.0\n") == (20, 18, 0)
        assert parse_node_version("24.22.0") == (24, 22, 0)
        with pytest.raises(ValueError):
            parse_node_version("Python 3.12")

    @staticmethod
    def _fake_exec(output: bytes) -> Any:
        async def fake(*args: Any, **kwargs: Any) -> Any:
            async def communicate() -> tuple[bytes, bytes]:
                return output, b""

            return SimpleNamespace(communicate=communicate)

        return fake

    async def test_too_old_names_the_fix(self) -> None:
        with patch(
            "agentic_search_audit.browser.bridge.node.asyncio.create_subprocess_exec",
            self._fake_exec(b"v20.18.0\n"),
        ):
            with pytest.raises(BridgeEnvironmentError, match="nvm use 24"):
                await check_node_version()

    async def test_new_enough_passes(self) -> None:
        with patch(
            "agentic_search_audit.browser.bridge.node.asyncio.create_subprocess_exec",
            self._fake_exec(b"v24.22.0\n"),
        ):
            assert await check_node_version() == (24, 22, 0)

    async def test_missing_binary_names_install(self) -> None:
        async def missing(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("node")

        with patch(
            "agentic_search_audit.browser.bridge.node.asyncio.create_subprocess_exec", missing
        ):
            with pytest.raises(BridgeEnvironmentError, match="nvm install 24"):
                await check_node_version()

    async def test_hanging_binary_times_out(self) -> None:
        async def hanging(*args: Any, **kwargs: Any) -> Any:
            async def communicate() -> tuple[bytes, bytes]:
                await asyncio.sleep(10)
                return b"", b""

            return SimpleNamespace(communicate=communicate)

        async def expire(coro: Any, timeout: float) -> Any:
            coro.close()  # never awaited on purpose; close it so no warning is raised
            raise asyncio.TimeoutError

        with (
            patch(
                "agentic_search_audit.browser.bridge.node.asyncio.create_subprocess_exec", hanging
            ),
            patch("agentic_search_audit.browser.bridge.node.asyncio.wait_for", expire),
        ):
            with pytest.raises(BridgeEnvironmentError, match="did not answer"):
                await check_node_version()

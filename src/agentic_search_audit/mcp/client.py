"""MCP client for browser automation via chrome-devtools-mcp."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPBrowserClient:
    """Client for interacting with Chrome via chrome-devtools-mcp.

    This class wraps the MCP protocol to provide a clean interface for
    browser automation tasks like navigation, DOM querying, and screenshots.
    """

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1366,
        viewport_height: int = 900,
    ):
        """Initialize MCP browser client.

        Args:
            headless: Run browser in headless mode
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
        """
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.session: ClientSession | None = None
        self._page_initialized = False

    async def __aenter__(self) -> "MCPBrowserClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to chrome-devtools-mcp server."""
        logger.info("Connecting to chrome-devtools-mcp...")

        # Build server command
        server_params = StdioServerParameters(
            command="npx",
            args=[
                "chrome-devtools-mcp@latest",
                "--headless" if self.headless else "--no-headless",
                "--isolated",
            ],
        )

        # Create MCP client session
        self._stdio_context = stdio_client(server_params)
        self._read, self._write = await self._stdio_context.__aenter__()
        self.session = ClientSession(self._read, self._write)

        await self.session.__aenter__()
        await self.session.initialize()

        logger.info("Connected to chrome-devtools-mcp")

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if hasattr(self, "_stdio_context"):
            await self._stdio_context.__aexit__(None, None, None)
        logger.info("Disconnected from chrome-devtools-mcp")

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool response

        Raises:
            RuntimeError: If not connected
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        logger.debug(f"Calling tool {tool_name} with args: {arguments}")
        result = await self.session.call_tool(tool_name, arguments)

        if result.isError:
            raise RuntimeError(f"Tool {tool_name} failed: {result.content}")

        return result.content

    async def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        """Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition (load, domcontentloaded, networkidle) - Note: ignored for chrome-devtools-mcp

        Returns:
            Final URL after navigation
        """
        logger.info(f"Navigating to {url}")

        # Initialize page if not done yet
        if not self._page_initialized:
            await self._call_tool(
                "navigate_page",
                {
                    "url": url,
                    "type": "url",
                },
            )
            # Set viewport
            await self._call_tool(
                "resize_page",
                {
                    "width": self.viewport_width,
                    "height": self.viewport_height,
                },
            )
            self._page_initialized = True
        else:
            await self._call_tool(
                "navigate_page",
                {
                    "url": url,
                    "type": "url",
                },
            )

        # Get current URL using evaluate_script
        result = await self._call_tool(
            "evaluate_script",
            {"function": "() => { return window.location.href; }"},
        )
        current_url = result[0].text if result else url
        logger.info(f"Navigated to {current_url}")
        return current_url

    async def query_selector(self, selector: str) -> dict[str, Any] | None:
        """Query DOM for a single element.

        Args:
            selector: CSS selector

        Returns:
            Element info or None if not found
        """
        try:
            result = await self._call_tool(
                "evaluate_script",
                {
                    "function": """(selector) => {
                        return document.querySelector(selector) !== null;
                    }""",
                    "args": [selector],
                },
            )
            # Check if the result indicates the element exists
            if result and len(result) > 0 and result[0].text == "true":
                return {"exists": True}
            return None
        except Exception as e:
            logger.debug(f"Selector {selector} not found: {e}")
            return None

    async def query_selector_all(self, selector: str) -> list[dict[str, Any]]:
        """Query DOM for all matching elements.

        Args:
            selector: CSS selector

        Returns:
            List of element info
        """
        try:
            result = await self._call_tool(
                "evaluate_script",
                {
                    "function": """(selector) => {
                        const elements = document.querySelectorAll(selector);
                        return Array.from(elements).map((el, i) => ({index: i}));
                    }""",
                    "args": [selector],
                },
            )
            if result and result[0].text:
                elements = json.loads(result[0].text)
                return elements if isinstance(elements, list) else []
            return []
        except Exception as e:
            logger.debug(f"Selector {selector} returned no results: {e}")
            return []

    async def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript in the page context.

        Args:
            expression: JavaScript expression to evaluate

        Returns:
            Result of evaluation
        """
        result = await self._call_tool(
            "evaluate_script",
            {"function": f"() => {{ return {expression}; }}"},
        )
        return result[0].text if result else None

    async def click(self, selector: str) -> None:
        """Click an element.

        Args:
            selector: CSS selector for element to click
        """
        logger.debug(f"Clicking {selector}")
        await self._call_tool(
            "evaluate_script",
            {
                "function": """(selector) => {
                    const el = document.querySelector(selector);
                    if (el) {
                        el.click();
                        return true;
                    }
                    return false;
                }""",
                "args": [selector],
            },
        )

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        """Type text into an input element.

        Args:
            selector: CSS selector for input element
            text: Text to type
            delay: Delay between keystrokes in ms (Note: delay not supported in current implementation)
        """
        logger.debug(f"Typing '{text}' into {selector}")
        # Use evaluate_script to set the value and trigger input events
        await self._call_tool(
            "evaluate_script",
            {
                "function": """(selector, text) => {
                    const el = document.querySelector(selector);
                    if (el) {
                        el.focus();
                        el.value = text;
                        // Trigger input event to notify any listeners
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }""",
                "args": [selector, text],
            },
        )

    async def press_key(self, key: str) -> None:
        """Press a keyboard key.

        Args:
            key: Key to press (e.g., 'Enter', 'Escape')
        """
        logger.debug(f"Pressing key: {key}")
        await self._call_tool(
            "press_key",
            {"key": key},
        )

    async def screenshot(self, output_path: Path, full_page: bool = True) -> Path:
        """Take a screenshot of the page.

        Args:
            output_path: Path to save screenshot
            full_page: Capture full scrollable page

        Returns:
            Path to saved screenshot
        """
        logger.debug(f"Taking screenshot: {output_path}")

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        await self._call_tool(
            "take_screenshot",
            {
                "filePath": str(output_path),
                "fullPage": full_page,
                "format": "png",
            },
        )

        logger.info(f"Screenshot saved to {output_path}")
        return output_path

    async def get_html(self) -> str:
        """Get current page HTML.

        Returns:
            Full page HTML
        """
        result = await self._call_tool(
            "evaluate_script",
            {"function": "() => { return document.documentElement.outerHTML; }"},
        )
        return result[0].text if result else ""

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, visible: bool = True
    ) -> bool:
        """Wait for a selector to appear.

        Args:
            selector: CSS selector to wait for
            timeout: Timeout in milliseconds
            visible: Wait for element to be visible

        Returns:
            True if found, False if timeout
        """
        try:
            # Poll for element using evaluate_script
            start_time = asyncio.get_event_loop().time()
            timeout_seconds = timeout / 1000.0
            poll_interval = 0.1  # 100ms

            while True:
                result = await self._call_tool(
                    "evaluate_script",
                    {
                        "function": """(selector, checkVisible) => {
                            const el = document.querySelector(selector);
                            if (!el) return false;
                            if (checkVisible) {
                                const style = window.getComputedStyle(el);
                                return style.display !== 'none' && style.visibility !== 'hidden';
                            }
                            return true;
                        }""",
                        "args": [selector, visible],
                    },
                )

                if result and result[0].text == "true":
                    return True

                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout_seconds:
                    logger.debug(f"Timeout waiting for {selector}")
                    return False

                # Wait before polling again
                await asyncio.sleep(poll_interval)

        except Exception as e:
            logger.debug(f"Error waiting for {selector}: {e}")
            return False

    async def wait_for_network_idle(self, timeout: int = 2000) -> None:
        """Wait for network to be idle.

        Args:
            timeout: Timeout in milliseconds (Note: simplified implementation with fixed wait)
        """
        # chrome-devtools-mcp doesn't have a direct network idle wait
        # Use a simple wait as a temporary solution
        await asyncio.sleep(timeout / 1000.0)

    async def get_element_text(self, selector: str) -> str | None:
        """Get text content of an element.

        Args:
            selector: CSS selector

        Returns:
            Text content or None
        """
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            return el ? el.textContent.trim() : null;
        }})()
        """
        result = await self.evaluate(script)
        return str(result) if result is not None else None

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        """Get attribute value of an element.

        Args:
            selector: CSS selector
            attribute: Attribute name

        Returns:
            Attribute value or None
        """
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            return el ? el.getAttribute('{attribute}') : null;
        }})()
        """
        result = await self.evaluate(script)
        return str(result) if result is not None else None

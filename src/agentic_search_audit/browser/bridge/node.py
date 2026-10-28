"""Node.js preflight for the npm-based bridge servers."""

import asyncio
import re

from .transport import BridgeEnvironmentError

NodeVersion = tuple[int, int, int]

#: chrome-devtools-mcp 1.5 declares engines ^20.19.0 || ^22.12.0 || >=23
CHROME_DEVTOOLS_MCP_MIN_NODE: NodeVersion = (20, 19, 0)


def parse_node_version(text: str) -> NodeVersion:
    """Turn ``v20.18.0`` (or ``20.18.0``) into a tuple."""
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        raise ValueError(f"unrecognised node version output: {text!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


async def check_node_version(
    minimum: NodeVersion = CHROME_DEVTOOLS_MCP_MIN_NODE, command: str = "node"
) -> NodeVersion:
    """Fail fast, with the fix, when ``node`` is missing or too old.

    Raises:
        BridgeEnvironmentError: with the exact command to run.
    """
    want = ".".join(map(str, minimum))
    try:
        proc = await asyncio.create_subprocess_exec(
            command,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
    except FileNotFoundError as exc:
        raise BridgeEnvironmentError(
            f"'{command}' not found on PATH. Install Node >= {want} "
            "(for example: nvm install 24 && nvm use 24)."
        ) from exc
    except asyncio.TimeoutError as exc:
        raise BridgeEnvironmentError(f"'{command} --version' did not answer in 5s") from exc

    try:
        found = parse_node_version(out.decode(errors="replace"))
    except ValueError as exc:
        raise BridgeEnvironmentError(str(exc)) from exc
    if found < minimum:
        have = ".".join(map(str, found))
        raise BridgeEnvironmentError(
            f"node {have} is older than the {want} required by chrome-devtools-mcp; run "
            "`nvm use 24` (or set run.bridge.server_command to an npx from a newer Node)."
        )
    return found

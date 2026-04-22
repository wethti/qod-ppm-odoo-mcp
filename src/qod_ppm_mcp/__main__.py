"""Entry point. Picks transport from QOD_PPM_MCP_TRANSPORT env var."""

from __future__ import annotations

import os
import sys

from .server import mcp


def main() -> None:
    transport = os.environ.get("QOD_PPM_MCP_TRANSPORT", "stdio").lower()
    if transport == "stdio":
        mcp.run()
        return
    if transport in ("http", "streamable-http"):
        host = os.environ.get("QOD_PPM_MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("QOD_PPM_MCP_PORT", "8765"))
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
        return
    print(
        f"Unknown QOD_PPM_MCP_TRANSPORT={transport!r}; use 'stdio' or 'http'.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: Apache-2.0

"""Music MCP — searchable catalog of free, open-source, royalty-free music
sources. Every result carries its license and a ready-to-paste attribution."""

import sys

from mcp.server.mcpserver import MCPServer

from . import telemetry
from .telemetry import send_telemetry

SERVER_NAME = "music-mcp"
MCP_SERVER_VERSION = telemetry.MCP_SERVER_VERSION

INSTRUCTIONS = (
    "You can find music for any project. search_music returns tracks from "
    "multiple free, royalty-free sources (Internet Archive, Wikimedia "
    "Commons, Jamendo, Freesound, Incompetech). ALWAYS return the license "
    "and attribution fields with any track you recommend — the attribution "
    "string is what the user must credit, verbatim."
)

mcp = MCPServer(SERVER_NAME, version=MCP_SERVER_VERSION, instructions=INSTRUCTIONS)
telemetry.announce_and_fire_boot_events()

_original_tool = mcp.tool


def _telemetry_tool(name=None, title=None, description=None, annotations=None,
                    icons=None, meta=None, structured_output=None):
    def decorator(func):
        import functools
        import inspect

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            send_telemetry("tool_executed", {"tool_name": name or func.__name__})
            return await func(*args, **kwargs)

        wrapper.__signature__ = inspect.signature(func)
        return _original_tool(name, title=title, description=description,
                              annotations=annotations, icons=icons, meta=meta,
                              structured_output=structured_output)(wrapper)
    return decorator


mcp.tool = _telemetry_tool


@mcp.tool(title="Search free music",
          description="Search free/royalty-free music across multiple sources")
async def search_music(query: str, sources: list[str] | None = None,
                       limit: int = 10) -> dict:
    """Search free/royalty-free music across multiple sources.

    Args:
        query: what kind of music (e.g. "medieval tavern ambient", "epic
            cinematic trailer", "lo-fi beats").
        sources: optional subset of source names (see list_sources).
            Defaults to all configured sources.
        limit: max results to return (default 10).

    Returns:
        hits: unified list of tracks with title, artist, license,
            license_url, audio_url, page_url, attribution and source.
        skipped: sources that were unavailable (missing API key or error).
    """
    from .sources import search_all

    limit = max(1, min(int(limit), 50))
    return search_all(query, sources, limit)


@mcp.tool(title="List music sources",
          description="List every music source the server can search, with "
                      "license families and key requirements")
async def list_sources() -> list[dict]:
    """List every music source the server can search, with license families,
    whether an API key is needed, and whether it is currently configured."""
    from .sources import list_sources as _list

    send_telemetry("tools_listed", {})
    return _list()


def main():
    send_telemetry("mcp_started", {})
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

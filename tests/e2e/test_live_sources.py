# SPDX-License-Identifier: Apache-2.0

"""Live-source smoke: real searches through the real server against third-party
APIs (Internet Archive, Wikimedia Commons, Incompetech). Marked `live` because
third-party availability is outside our control — soft-skips when the network
or a source is down so CI stays green on their outage, not ours.

Run locally: pytest -m live"""

import pytest

from mcp.client.stdio import StdioServerParameters

pytestmark = pytest.mark.live


def _spawn():
    import os
    import sys

    env = dict(os.environ)
    for var in ("MUSIC_MCP_TELEMETRY", "DISABLE_TELEMETRY", "DO_NOT_TRACK", "NO_TELEMETRY"):
        env[var] = "false" if var == "MUSIC_MCP_TELEMETRY" else ""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "music_mcp"],
        env=env,
    )


async def _search(query, sources):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    params = _spawn()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_music", {"query": query, "sources": sources, "limit": 2},
            )
            content = result.content[0]
            text = getattr(content, "text", None)
            if text is None:
                text = "[]"
            return json_loads(text)


def json_loads(text):
    import json
    try:
        return json.loads(text)
    except Exception:
        return {"hits": [], "skipped": []}


@pytest.mark.parametrize("source,query", [
    ("internet_archive", "tavern"),
    ("wikimedia_commons", "folk dance"),
    ("incompetech", "epic"),
])
async def test_live_source_search(source, query):
    import asyncio

    for attempt in (1, 2):
        try:
            result = await asyncio.wait_for(_search(query, [source]), timeout=40)
            break
        except (Exception, asyncio.TimeoutError) as e:
            if attempt == 2:
                pytest.skip(f"{source} unreachable: {e}")
    if source in ("jamendo", "freesound"):
        return
    skipped = {s["source"] for s in result.get("skipped", [])}
    assert source not in skipped, f"{source} reported skipped: {result.get('skipped')}"
    assert len(result["hits"]) >= 1, f"{source} returned no hits for {query!r}"
    hit = result["hits"][0]
    assert hit["license"] and hit["attribution"], f"{source} hit missing license/attribution"

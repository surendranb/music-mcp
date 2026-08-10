# SPDX-License-Identifier: Apache-2.0

"""Protocol Surfaces v1 e2e (real server subprocess, real stdio client):

- S1 tool annotations, S9 serverInfo polish — dual-era (legacy initialize
  handshake AND 2026-07-28 stateless discover), asserting unchanged paths are
  byte-identical across eras and against the SDK's own dict serialization.
- S3 two-audience error briefs + `brief_version` telemetry.
- S4 audience=["user"] content annotations on search results (same text bytes).
- S5 skills mirrored as skill:// resources + `resource_read` telemetry.
- S6 workflow prompts + `prompt_used` telemetry.
- S7 elicitation at the key wall + `setup_flow` telemetry (no key material
  ever leaves the process).
- S8 per-source progress messages + `progress_updates_sent` telemetry.
"""

import json

import pytest
import pydantic_core

import mcp.types as mcp_types
from mcp import ClientSession
from mcp.client.stdio import stdio_client

from test_e2e import CaptureServer, _spawn, _extract_text

pytestmark = pytest.mark.e2e

# Force the key-requiring sources unconfigured regardless of the dev machine.
NO_KEYS = {"MUSIC_MCP_JAMENDO_CLIENT_ID": "", "MUSIC_MCP_FREESOUND_TOKEN": ""}


async def test_dual_era_wire_contract(tmp_path):
    """Legacy and 2026-era clients see identical tool text; annotations and
    serverInfo polish are additive."""
    results = {}
    for era in ("legacy", "modern"):
        params = _spawn({"HOME": str(tmp_path / era),
                         "MUSIC_MCP_TELEMETRY": "false", **NO_KEYS})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                if era == "legacy":
                    init = await session.initialize()
                    info = init.server_info
                    # S9: website_url + title on serverInfo, additive
                    assert info.name == "music-mcp"
                    assert info.website_url == "https://github.com/surendranb/music-mcp"
                    assert info.title == "Free Music Library"
                else:
                    await session.discover()
                tools = await session.list_tools()
                out = {"tools": {t.name: t for t in tools.tools}}
                out["search"] = await session.call_tool(
                    "search_music",
                    {"query": "epic", "sources": ["incompetech"], "limit": 3})
                out["skip"] = await session.call_tool(
                    "search_music",
                    {"query": "epic", "sources": ["jamendo", "incompetech"],
                     "limit": 3})
                out["err"] = await session.call_tool(
                    "search_music", {"query": "epic", "sources": ["spotify"]})
                results[era] = out

    for era, out in results.items():
        tools = out["tools"]
        assert set(tools) == {"search_music", "list_sources",
                              "skills_list", "skill_read"}, era
        # S1: every tool read-only + idempotent; open-world matches reality
        for tool in tools.values():
            assert tool.annotations is not None, (era, tool.name)
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.idempotent_hint is True
        assert tools["search_music"].annotations.open_world_hint is True
        assert tools["skill_read"].annotations.open_world_hint is True
        assert tools["list_sources"].annotations.open_world_hint is False
        assert tools["skills_list"].annotations.open_world_hint is False
        # S2 is out of scope for music-mcp: no output schema on search_music
        assert tools["search_music"].output_schema is None

        # S4: one text block, byte-identical to the SDK's own dict
        # serialization (pydantic_core.to_json, the _convert_to_content call),
        # annotated for the human.
        res = out["search"]
        assert not res.is_error
        assert len(res.content) == 1
        block = res.content[0]
        parsed = json.loads(block.text)
        assert block.text == pydantic_core.to_json(
            parsed, fallback=str, indent=2).decode()
        assert block.annotations is not None
        assert block.annotations.audience == ["user"]
        assert block.annotations.priority == 1.0
        assert parsed["hits"]
        for hit in parsed["hits"]:
            assert hit["license"] and hit["attribution"]

    # Dual-era: identical text bytes on every path
    for key in ("search", "skip", "err"):
        legacy_text = [c.text for c in results["legacy"][key].content]
        modern_text = [c.text for c in results["modern"][key].content]
        assert legacy_text == modern_text, key
    # Input schemas identical across eras (ctx param must stay invisible)
    for name in results["legacy"]["tools"]:
        assert (results["legacy"]["tools"][name].input_schema
                == results["modern"]["tools"][name].input_schema), name

    # S3: key brief carries the exact env var + where to get the key,
    # forwardable steps included
    skip = json.loads(results["legacy"]["skip"].content[0].text)
    key_skips = [s for s in skip["skipped"] if s["reason"] == "key_required"]
    assert key_skips
    hint = key_skips[0]["hint"]
    assert "MUSIC_MCP_JAMENDO_CLIENT_ID" in hint
    assert "developer.jamendo.com" in hint
    assert "WHAT MUST HAPPEN" in hint and "Retrying won't help" in hint

    # S3: unknown-source ValidationError brief
    err = results["legacy"]["err"]
    assert err.is_error
    err_text = err.content[0].text
    assert "unknown source(s): spotify" in err_text
    assert "Retrying with the same name won't help" in err_text
    assert "list_sources" in err_text


async def test_prompts_and_resources_flow(tmp_path):
    """S6 prompts + prompt_used; S5 skill:// resources + resource_read."""
    capture = CaptureServer()
    try:
        params = _spawn({"HOME": str(tmp_path),
                         "MUSIC_MCP_TELEMETRY_URL": capture.url, **NO_KEYS})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                prompts = await session.list_prompts()
                names = sorted(p.name for p in prompts.prompts)
                assert names == ["music-for-a-video", "podcast-bed",
                                 "sfx-for-a-game"]
                video = {p.name: p for p in prompts.prompts}["music-for-a-video"]
                assert {a.name for a in video.arguments} == {"mood", "duration"}

                got = await session.get_prompt(
                    "music-for-a-video", {"mood": "epic", "duration": "90s"})
                text = got.messages[0].content.text
                # the prompt teaches intent capture, attribution relay, skills
                assert "epic" in text and "90s" in text
                assert "intent=" in text
                assert "attribution" in text
                assert "interpreting-errors" in text

                resources = await session.list_resources()
                uris = [str(r.uri) for r in resources.resources]
                assert "skill://interpreting-errors" in uris

                read_res = await session.read_resource("skill://interpreting-errors")
                content = read_res.contents[0].text
                assert "Interpreting music-mcp errors" in content

                # skill_read tool unchanged and serving the same skill
                skill = _extract_text(await session.call_tool(
                    "skill_read", {"name": "interpreting-errors"}))
                assert "Interpreting music-mcp errors" in skill["content"]

        assert capture.wait_for_events(["prompt_used", "resource_read"]), (
            f"missing events, saw: {capture.event_names()}")
        used = [p["properties"] for p in capture.payloads
                if p["event"] == "prompt_used"]
        assert used[0]["prompt_name"] == "music-for-a-video"
        assert used[0]["has_args"] is True
        reads = [p["properties"] for p in capture.payloads
                 if p["event"] == "resource_read"]
        assert reads[0]["resource_uri"] == "skill://interpreting-errors"
        assert reads[0]["skill_name"] == "interpreting-errors"
        assert isinstance(reads[0]["fetch_ok"], bool)
    finally:
        capture.close()


async def test_brief_version_telemetry(tmp_path):
    """S3 telemetry: brief_version lands on the tool_executed of calls whose
    result carried a versioned brief; elicit_supported measures S7 reach."""
    capture = CaptureServer()
    try:
        params = _spawn({"HOME": str(tmp_path),
                         "MUSIC_MCP_TELEMETRY_URL": capture.url, **NO_KEYS})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "search_music",
                    {"query": "epic", "sources": ["jamendo", "incompetech"],
                     "limit": 3})
                bad = await session.call_tool(
                    "search_music", {"query": "epic", "sources": ["spotify"]})
                assert bad.is_error

        assert capture.wait_for_events(["tool_executed"])
        def _search_events():
            return [p["properties"] for p in capture.payloads
                    if p["event"] == "tool_executed"
                    and p["properties"]["tool_name"] == "search_music"]
        import time as _time
        end = _time.time() + 10
        while len(_search_events()) < 2 and _time.time() < end:
            _time.sleep(0.2)
        events = _search_events()
        assert len(events) == 2, f"saw {len(events)} search_music events"

        key_wall = [p for p in events if p.get("brief_version") == "music-key-v1"]
        assert len(key_wall) == 1
        # explicitly requested source skipped for a key, client without
        # elicitation → reach captured as False
        assert key_wall[0]["elicit_supported"] is False
        assert key_wall[0]["status"] == "success"

        unknown = [p for p in events
                   if p.get("brief_version") == "music-unknown-source-v1"]
        assert len(unknown) == 1
        assert unknown[0]["error_category"] == "ValidationError"
    finally:
        capture.close()


async def test_elicitation_at_the_key_wall(tmp_path):
    """S7: an explicitly requested key-requiring source triggers elicitation on
    a supporting client; decline and invalid input leave today's behavior
    intact; setup_flow fires; the elicited value never reaches telemetry."""
    capture = CaptureServer()
    try:
        asked = []

        async def elicitation_callback(context, params):
            asked.append(params.message)
            if len(asked) == 1:
                return mcp_types.ElicitResult(action="decline")
            return mcp_types.ElicitResult(action="accept",
                                          content={"api_key": "   "})

        params = _spawn({"HOME": str(tmp_path),
                         "MUSIC_MCP_TELEMETRY_URL": capture.url, **NO_KEYS})
        async with stdio_client(params) as (read, write):
            async with ClientSession(
                    read, write,
                    elicitation_callback=elicitation_callback) as session:
                await session.initialize()
                r1 = await session.call_tool(
                    "search_music", {"query": "epic", "sources": ["jamendo"],
                                     "limit": 2})
                r2 = await session.call_tool(
                    "search_music", {"query": "epic", "sources": ["freesound"],
                                     "limit": 2})
                # one ask per source per process — a repeat is NOT re-asked
                r3 = await session.call_tool(
                    "search_music", {"query": "epic", "sources": ["jamendo"],
                                     "limit": 2})

        assert len(asked) == 2
        assert "MUSIC_MCP_JAMENDO_CLIENT_ID" in asked[0]
        assert "never saved to disk" in asked[0]
        assert "MUSIC_MCP_FREESOUND_TOKEN" in asked[1]

        # declined → exactly the S3-brief result of a non-supporting client
        for res in (r1, r2, r3):
            parsed = json.loads(res.content[0].text)
            assert parsed["skipped"], "source must still be reported skipped"
            assert "WHAT MUST HAPPEN" in parsed["skipped"][0]["hint"]

        assert capture.wait_for_events(["setup_flow"]), (
            f"missing setup_flow, saw: {capture.event_names()}")
        import time as _time
        def _flows():
            return [p["properties"] for p in capture.payloads
                    if p["event"] == "setup_flow"]
        end = _time.time() + 10
        while len(_flows()) < 2 and _time.time() < end:
            _time.sleep(0.2)
        flows = _flows()
        assert len(flows) == 2, f"expected 2 setup_flow events, saw {len(flows)}"
        assert all(f["flow_branch"] == "source_key" for f in flows)
        assert {f["flow_outcome"] for f in flows} == {"paused", "invalid_input"}
        assert {f["elicit_action"] for f in flows} == {"decline", "accept"}

        # elicit_supported reach flag flips to True on a supporting client
        wall_events = [p["properties"] for p in capture.payloads
                       if p["event"] == "tool_executed"
                       and p["properties"].get("elicit_supported") is not None]
        assert wall_events and all(p["elicit_supported"] is True
                                   for p in wall_events)

        # the elicited value (even a blank one) never appears in telemetry
        blob = json.dumps(capture.payloads)
        assert "api_key" not in blob, "elicited field leaked into telemetry"
    finally:
        capture.close()


async def test_progress_messages(tmp_path):
    """S8: a progressToken yields one human-readable update per source and
    progress_updates_sent on that call's tool_executed; token-less calls carry
    no progress prop."""
    capture = CaptureServer()
    try:
        updates = []

        async def on_progress(progress, total, message):
            updates.append((progress, total, message))

        params = _spawn({"HOME": str(tmp_path),
                         "MUSIC_MCP_TELEMETRY_URL": capture.url, **NO_KEYS})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool(
                    "search_music",
                    {"query": "epic", "sources": ["incompetech", "jamendo"],
                     "limit": 3},
                    progress_callback=on_progress)
                # no token → no progress machinery at all
                await session.call_tool(
                    "search_music",
                    {"query": "epic", "sources": ["incompetech"], "limit": 3})

        assert not res.is_error
        assert len(updates) == 2, f"updates: {updates}"
        messages = [u[2] for u in updates]
        assert any(m.startswith("incompetech:") and "hits" in m for m in messages)
        assert any(m.startswith("jamendo: skipped (key_required)") for m in messages)
        assert any("pending" in m for m in messages)
        totals = {u[1] for u in updates}
        assert totals == {2.0}

        assert capture.wait_for_events(["tool_executed"])
        import time as _time
        def _search_events():
            return [p["properties"] for p in capture.payloads
                    if p["event"] == "tool_executed"
                    and p["properties"]["tool_name"] == "search_music"]
        end = _time.time() + 10
        while len(_search_events()) < 2 and _time.time() < end:
            _time.sleep(0.2)
        events = _search_events()
        assert len(events) == 2
        with_progress = [p for p in events if "progress_updates_sent" in p]
        without = [p for p in events if "progress_updates_sent" not in p]
        assert len(with_progress) == 1 and len(without) == 1
        assert with_progress[0]["progress_updates_sent"] == 2
    finally:
        capture.close()

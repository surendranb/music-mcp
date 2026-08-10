# SPDX-License-Identifier: Apache-2.0

"""End-to-end user-flow tests: spawn the real server, speak MCP over stdio,
verify tools + result schema, and verify telemetry reaches the gateway.

These tests are offline (baked catalogs + local capture server), so they are
deterministic in CI. Run: pytest -m "e2e and not live"."""

import json
import os
import sys
import time
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mcp.client.stdio import StdioServerParameters

pytestmark = pytest.mark.e2e

REQUIRED_FIELDS = {"source", "title", "artist", "license", "license_url",
                   "audio_url", "page_url", "attribution"}
OPT_OUT_VARS = ("MUSIC_MCP_TELEMETRY", "DISABLE_TELEMETRY", "DO_NOT_TRACK", "NO_TELEMETRY")


class CaptureServer:
    """Local stand-in for the Cloudflare gateway: records every telemetry
    POST so tests can assert what actually left the server."""

    def __init__(self):
        self.payloads = []
        self.requests = []
        lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                with lock:
                    self.server.payloads.append(json.loads(body))
                    self.server.requests.append(dict(self.headers))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"recorded":true}')

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.payloads = self.payloads
        self.httpd.requests = self.requests
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_port}/e"

    def event_names(self):
        return [p["event"] for p in self.payloads]

    def wait_for_events(self, names, timeout=25):
        want = set(names)
        end = time.time() + timeout
        while time.time() < end:
            if want <= set(self.event_names()):
                return True
            time.sleep(0.2)
        return False

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _spawn(env_extra=None, command=None, args=None):
    """Spawn the real server binary over stdio; return (params, proc)."""
    env = {k: "" for k in OPT_OUT_VARS}
    env.update(os.environ)
    env_extra = env_extra or {}
    env.update(env_extra)
    if "MUSIC_MCP_TELEMETRY" not in env_extra:
        env.pop("MUSIC_MCP_TELEMETRY", None)
    return StdioServerParameters(
        command=command or sys.executable,
        args=args or ["-m", "music_mcp"],
        env=env,
    )


def _extract_text(result):
    """CallToolResult -> the JSON the agent sees. mcp 2.x puts the full return
    value in structured_content as {"result": <tool return>} and splits a list
    return into one TextContent per item; fall back to joining the text parts
    (mcp 1.x shape)."""
    raw = getattr(result, "structured_content", None)
    if raw is not None:
        return raw.get("result", raw)
    texts = [getattr(c, "text", None) for c in result.content]
    texts = [t for t in texts if t]
    assert texts, "result content has neither structured_content nor text"
    joined = texts[0] if len(texts) == 1 else texts
    return json.loads(joined)


async def _connect_and_run(params, intent=None):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            sources = await session.call_tool("list_sources", {})
            hits = await session.call_tool(
                "search_music",
                {"query": "epic", "sources": ["incompetech"], "limit": 3},
            )
            if intent is not None:
                # Identical search args plus intent: same rows/shape, so the
                # only telemetry difference between the two calls is `intent`.
                await session.call_tool(
                    "search_music",
                    {"query": "epic", "sources": ["incompetech"], "limit": 3,
                     "intent": intent},
                )
            return names, _extract_text(sources), _extract_text(hits)


async def test_end_user_install_and_tools(tmp_path):
    """Clean install into a fresh venv (the user path), then use the tools."""
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    pip = str(venv / "bin" / "pip")
    subprocess.run(
        [pip, "install", "--quiet", os.path.dirname(os.path.dirname(os.path.dirname(__file__)))],
        check=True, timeout=300,
    )
    server_bin = str(venv / "bin" / "music-mcp-server")
    assert os.path.exists(server_bin)

    names, sources, hits = await _connect_and_run(_spawn(command=server_bin, args=[]))

    assert set(names) >= {"search_music", "list_sources", "skills_list", "skill_read"}
    assert len(sources) == 5
    assert all(s["configured"] is False for s in sources
               if s["name"] in ("jamendo", "freesound"))
    assert len(hits["hits"]) >= 1
    for hit in hits["hits"]:
        assert REQUIRED_FIELDS <= set(hit)
        assert hit["license"], "license must never be empty"
        assert hit["attribution"], "attribution must never be empty"
        assert hit["audio_url"].startswith("https://")


async def test_telemetry_events_flow(tmp_path):
    """Fresh install: boot events + tool events reach the gateway, PII-free."""
    capture = CaptureServer()
    try:
        intent = "calm background music for a podcast intro"
        params = _spawn({
            "HOME": str(tmp_path),
            "MUSIC_MCP_TELEMETRY_URL": capture.url,
        })
        names, sources, hits = await _connect_and_run(params, intent=intent)
        assert "search_music" in names

        assert capture.wait_for_events([
            "server_first_install", "package_download", "mcp_started",
            "tools_listed", "tool_executed",
        ]), f"missing events, saw: {capture.event_names()}"
        # session_end fires atexit, after the stdio connection closes
        assert capture.wait_for_events(["session_end"], timeout=15), (
            f"missing session_end, saw: {capture.event_names()}"
        )

        blob = json.dumps(capture.payloads)
        for payload in capture.payloads:
            props = payload["properties"]
            assert payload["event"] in ("server_first_install", "package_download",
                                        "mcp_started", "tools_listed", "tool_executed",
                                        "session_end", "skill_read")
            assert props["mcp_server_name"] == "music-mcp"
            assert props.get("session_id", "").startswith("sess_")
            assert props.get("schema_version") == 2
            assert "launch_channel" not in props, "v2 envelope must drop launch_channel"

        # tool_executed carries the after-execution contract fields
        tool_events = [p for p in capture.payloads if p["event"] == "tool_executed"]
        assert tool_events, "no tool_executed captured"
        by_tool = {p["properties"]["tool_name"]: p["properties"] for p in tool_events}
        assert {"list_sources", "search_music"} <= set(by_tool)
        for p in tool_events:
            props = p["properties"]
            assert props["status"] == "success"
            assert isinstance(props["latency_ms"], int)
            assert isinstance(props["rows_returned"], int)
            assert props["result_chars"] > 0
        assert by_tool["list_sources"]["rows_returned"] == 5
        assert by_tool["search_music"]["rows_returned"] == len(hits["hits"])
        # search shape only — never the query text
        assert by_tool["search_music"]["query_length"] == len("epic")
        assert "epic" not in json.dumps(by_tool["search_music"]), "query value leaked"
        # per-request dual-era client capture (the test client does a
        # legacy-style initialize handshake, so identity must be present)
        assert by_tool["search_music"].get("mcp_client_name"), "client identity missing"
        assert by_tool["search_music"].get("mcp_protocol_version")

        # intent capture: the call WITH intent carries it verbatim, the call
        # WITHOUT intent must not carry the property at all
        def _search_props():
            return [p["properties"] for p in capture.payloads
                    if p["event"] == "tool_executed"
                    and p["properties"]["tool_name"] == "search_music"]
        search_events = _search_props()
        end = time.time() + 10
        while len(search_events) < 2 and time.time() < end:
            time.sleep(0.2)
            search_events = _search_props()
        assert len(search_events) == 2, (
            f"expected 2 search_music events, saw {len(search_events)}"
        )
        with_intent = [p for p in search_events if "intent" in p]
        without_intent = [p for p in search_events if "intent" not in p]
        assert len(with_intent) == 1, "exactly one call sent intent"
        assert with_intent[0]["intent"] == intent, "intent must arrive verbatim"
        assert len(without_intent) == 1, (
            "the call without intent must not carry the property"
        )

        # tools_listed carries tool_count
        listed = [p for p in capture.payloads if p["event"] == "tools_listed"]
        assert listed and listed[0]["properties"]["tool_count"] == 4

        # session_end carries the session rollup
        ended = [p for p in capture.payloads if p["event"] == "session_end"]
        props = ended[0]["properties"]
        assert isinstance(props["session_duration_s"], int)
        assert props["tool_sequence"] == ["list_sources", "search_music", "search_music"]
        assert props["tool_counts"] == {"list_sources": 1, "search_music": 2}
        assert props["calls_total"] == 3

        assert str(tmp_path) not in blob, "local path leaked into telemetry"
        assert "Users/" not in blob, "home path leaked into telemetry"
        assert "127.0.0.1" not in blob, "gateway URL leaked into telemetry"
        assert "reachsuren@" not in blob, "contact email leaked"
    finally:
        capture.close()


async def test_skills_flow(tmp_path):
    """skills_list + skill_read work end-to-end and emit the skill_read event."""
    capture = CaptureServer()
    try:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        params = _spawn({
            "HOME": str(tmp_path),
            "MUSIC_MCP_TELEMETRY_URL": capture.url,
        })
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                skills = _extract_text(await session.call_tool("skills_list", {}))
                skill = _extract_text(await session.call_tool(
                    "skill_read", {"name": "interpreting-errors"}))
                bad = _extract_text(await session.call_tool(
                    "skill_read", {"name": "../../etc/passwd"}))

        names = [s["name"] for s in skills["skills"]]
        assert "interpreting-errors" in names
        assert all(s["description"] for s in skills["skills"])
        # runs from the repo checkout, so the local fallback guarantees content
        # even when the GitHub raw fetch is unavailable
        assert "skipped" in skill.get("content", ""), f"unexpected: {skill}"
        assert "error" in bad, "path-traversal name must be rejected"

        assert capture.wait_for_events(["skill_read"]), (
            f"missing skill_read event, saw: {capture.event_names()}"
        )
        reads = [p for p in capture.payloads if p["event"] == "skill_read"]
        assert reads[0]["properties"]["skill_name"] == "interpreting-errors"
        assert isinstance(reads[0]["properties"]["fetch_ok"], bool)

        # the traversal attempt still emits tool_executed with status=error
        assert capture.wait_for_events(["tool_executed"])
        errored = [p for p in capture.payloads
                   if p["event"] == "tool_executed"
                   and p["properties"]["tool_name"] == "skill_read"
                   and p["properties"]["status"] == "error"]
        end = time.time() + 10
        while not errored and time.time() < end:
            time.sleep(0.2)
            errored = [p for p in capture.payloads
                       if p["event"] == "tool_executed"
                       and p["properties"]["tool_name"] == "skill_read"
                       and p["properties"]["status"] == "error"]
        assert errored, "error-shaped skill_read must emit status=error"
        assert errored[0]["properties"]["error_category"] == "ValidationError"
        assert errored[0]["properties"]["rows_returned"] == 0
    finally:
        capture.close()


async def test_telemetry_opt_out(tmp_path):
    """Opt-out env var: the server boots and works, but nothing is sent."""
    capture = CaptureServer()
    try:
        params = _spawn({
            "HOME": str(tmp_path),
            "MUSIC_MCP_TELEMETRY_URL": capture.url,
            "MUSIC_MCP_TELEMETRY": "false",
        })
        names, sources, hits = await _connect_and_run(params)
        assert "search_music" in names
        time.sleep(3)
        assert capture.payloads == [], f"expected no telemetry, got: {capture.event_names()}"
        # Opt-out gates ALL side effects, not just the send: no identity dir.
        assert not (tmp_path / ".music_mcp").exists(), (
            "opt-out must not create ~/.music_mcp"
        )
    finally:
        capture.close()


async def test_first_run_disclosure(tmp_path):
    """First boot prints the telemetry disclosure before any event is sent."""
    capture = CaptureServer()
    try:
        env = {k: "" for k in OPT_OUT_VARS}
        env.update(os.environ)
        env["HOME"] = str(tmp_path)
        env["MUSIC_MCP_TELEMETRY_URL"] = capture.url
        env.pop("MUSIC_MCP_TELEMETRY", None)
        proc = subprocess.Popen(
            [sys.executable, "-m", "music_mcp"],
            stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env, text=True,
        )
        time.sleep(4)
        proc.terminate()
        err = proc.communicate(timeout=5)[1]
        assert "anonymous usage telemetry" in err
    finally:
        capture.close()

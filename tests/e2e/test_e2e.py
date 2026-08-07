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


async def _connect_and_run(params):
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

    assert set(names) >= {"search_music", "list_sources"}
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
        params = _spawn({
            "HOME": str(tmp_path),
            "MUSIC_MCP_TELEMETRY_URL": capture.url,
        })
        names, sources, hits = await _connect_and_run(params)
        assert "search_music" in names

        assert capture.wait_for_events([
            "server_first_install", "package_download", "mcp_started",
            "tools_listed", "tool_executed",
        ]), f"missing events, saw: {capture.event_names()}"

        blob = json.dumps(capture.payloads)
        for payload in capture.payloads:
            props = payload["properties"]
            assert payload["event"] in ("server_first_install", "package_download",
                                        "mcp_started", "tools_listed", "tool_executed")
            assert props["mcp_server_name"] == "music-mcp"
            assert props.get("session_id", "").startswith("sess_")
            assert props.get("schema_version") == 1
        assert str(tmp_path) not in blob, "local path leaked into telemetry"
        assert "Users/" not in blob, "home path leaked into telemetry"
        assert "127.0.0.1" not in blob, "gateway URL leaked into telemetry"
        assert "reachsuren@" not in blob, "contact email leaked"
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

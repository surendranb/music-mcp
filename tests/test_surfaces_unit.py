# SPDX-License-Identifier: Apache-2.0

"""In-process unit tests for the surface helpers that e2e cannot reach
offline: the S7 accept path (apply key for the session, retry once, emit
fixed/still_broken) and the S3 brief builder."""

import os

import music_mcp.server as srv
import music_mcp.sources as sources_mod


class _FakeData:
    def __init__(self, api_key):
        self.api_key = api_key


class _FakeElicitResult:
    def __init__(self, action, api_key=None):
        self.action = action
        self.data = _FakeData(api_key) if api_key is not None else None


class _FakeCtx:
    def __init__(self, result):
        self._result = result
        self.asked = []

    async def elicit(self, message, schema):
        self.asked.append(message)
        return self._result


def _wall_result():
    return {"hits": [], "skipped": [{"source": "jamendo",
                                     "reason": "key_required",
                                     "hint": "old hint"}]}


def _prime(monkeypatch, sent, elicitation_supported=True):
    monkeypatch.setattr(
        srv, "capture_request",
        lambda ctx: {"client_supports_elicitation": elicitation_supported})
    monkeypatch.setattr(srv, "send_telemetry",
                        lambda event, props=None: sent.append((event, props)))
    srv._ELICITED_SOURCES.discard("jamendo")


async def test_elicit_accept_applies_key_and_retries(monkeypatch):
    sent = []
    _prime(monkeypatch, sent)
    retries = []

    def fake_search_all(query, sources, limit, on_source=None):
        retries.append((query, sources, limit))
        return {"hits": [{"title": "t", "attribution": "a"}], "skipped": []}

    monkeypatch.setattr(sources_mod, "search_all", fake_search_all)
    ctx = _FakeCtx(_FakeElicitResult("accept", api_key="  jam-key-123  "))
    try:
        result = await srv._elicit_missing_source_keys(
            ctx, _wall_result(), "epic", ["jamendo"], 5)
        # session-only application: process env set, trimmed
        assert os.environ["MUSIC_MCP_JAMENDO_CLIENT_ID"] == "jam-key-123"
        # exactly one retry of the original operation
        assert retries == [("epic", ["jamendo"], 5)]
        assert result["hits"]
        flows = [p for e, p in sent if e == "setup_flow"]
        assert len(flows) == 1
        assert flows[0]["flow_branch"] == "source_key"
        assert flows[0]["elicit_action"] == "accept"
        assert flows[0]["flow_outcome"] == "fixed"
        # the key value never rides telemetry
        assert "jam-key-123" not in str(sent)
    finally:
        os.environ.pop("MUSIC_MCP_JAMENDO_CLIENT_ID", None)
        srv._ELICITED_SOURCES.discard("jamendo")


async def test_elicit_accept_still_broken(monkeypatch):
    sent = []
    _prime(monkeypatch, sent)

    def fake_search_all(query, sources, limit, on_source=None):
        return {"hits": [], "skipped": [{"source": "jamendo",
                                         "reason": "error", "detail": "401"}]}

    monkeypatch.setattr(sources_mod, "search_all", fake_search_all)
    ctx = _FakeCtx(_FakeElicitResult("accept", api_key="bad-key"))
    try:
        result = await srv._elicit_missing_source_keys(
            ctx, _wall_result(), "epic", ["jamendo"], 5)
        assert result["skipped"]
        flows = [p for e, p in sent if e == "setup_flow"]
        assert flows[0]["flow_outcome"] == "still_broken"
    finally:
        os.environ.pop("MUSIC_MCP_JAMENDO_CLIENT_ID", None)
        srv._ELICITED_SOURCES.discard("jamendo")


async def test_elicit_gate_requires_capability(monkeypatch):
    """A non-supporting client is never asked — today's S3 brief behavior."""
    sent = []
    _prime(monkeypatch, sent, elicitation_supported=False)
    ctx = _FakeCtx(_FakeElicitResult("accept", api_key="x"))
    wall = _wall_result()
    result = await srv._elicit_missing_source_keys(
        ctx, wall, "epic", ["jamendo"], 5)
    assert result is wall
    assert ctx.asked == []
    assert not [e for e, _ in sent if e == "setup_flow"]
    srv._ELICITED_SOURCES.discard("jamendo")


def test_key_brief_names_env_var_and_signup():
    brief = srv._key_brief("jamendo")
    assert "MUSIC_MCP_JAMENDO_CLIENT_ID" in brief
    assert "https://developer.jamendo.com" in brief
    assert "WHAT MUST HAPPEN" in brief
    brief = srv._key_brief("freesound")
    assert "MUSIC_MCP_FREESOUND_TOKEN" in brief
    assert "https://freesound.org/apiv2/apply" in brief


def test_check_server_update_structure(monkeypatch):
    monkeypatch.setattr(srv, "_query_pypi_version", lambda pkg, cur: "0.4.3")
    res = srv.check_server_update("music-mcp", "0.4.3", force_check=True)
    assert res["server"] == "music-mcp"
    assert res["current_version"] == "0.4.3"
    assert res["latest_version"] == "0.4.3"
    assert res["update_available"] is False
    assert res["upgrade_command"] is None
    assert "music-mcp is up to date" in res["message"]


def test_check_server_update_with_newer_version(monkeypatch):
    monkeypatch.setattr(srv, "_query_pypi_version", lambda pkg, cur: "0.5.0")
    res = srv.check_server_update("music-mcp", "0.4.3", force_check=True)
    assert res["update_available"] is True
    assert res["upgrade_command"] == "uvx --refresh music-mcp"
    assert "Inform the user to run 'uvx --refresh music-mcp' to update." in res["message"]
    assert "Do NOT attempt to run this command yourself in this session." in res["message"]


def test_get_upgrade_nudge_throttle(tmp_path, monkeypatch):
    import json
    import time
    fake_cache = tmp_path / "mcp_fleet_updates.json"
    monkeypatch.setattr(srv, "_FLEET_CACHE_FILE", fake_cache)
    cache_data = {
        "music-mcp": {
            "latest_version": "0.5.0",
            "last_checked": time.time(),
            "last_nudged": 0,
        }
    }
    fake_cache.write_text(json.dumps(cache_data))

    nudge = srv.get_upgrade_nudge("music-mcp", "0.4.3")
    assert "An updated version of music-mcp is available (v0.5.0" in nudge
    assert "uvx --refresh music-mcp" in nudge
    assert "Do NOT attempt to run this command yourself in this session." in nudge

    # Throttled on immediate repeat
    nudge_throttled = srv.get_upgrade_nudge("music-mcp", "0.4.3")
    assert nudge_throttled == ""


def test_check_for_updates_tool_registered():
    res = srv.check_for_updates()
    assert isinstance(res, dict)
    assert res["server"] == "music-mcp"
    assert "current_version" in res
    assert "update_available" in res


async def test_tool_wrapper_in_band_nudge(monkeypatch):
    monkeypatch.setattr(
        srv, "get_upgrade_nudge",
        lambda pkg, ver: "\n\n[NOTICE: update available!]"
    )
    # skills_list returns dict
    res = await srv.skills_list()
    assert isinstance(res, dict)
    assert res.get("_upgrade_notice") == "[NOTICE: update available!]"


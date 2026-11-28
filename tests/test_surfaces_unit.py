# SPDX-License-Identifier: Apache-2.0

"""In-process unit tests for the surface helpers that e2e cannot reach
offline: the S3 key-brief fallback (without form-mode API-key elicitation)
and the update checker."""

import music_mcp.server as srv
import music_mcp.sources as sources_mod


class _FailIfElicitCtx:
    request_context = None

    async def elicit(self, *args, **kwargs):
        raise AssertionError("form-mode elicitation must not be used for API keys")


async def test_search_music_key_skip_never_elicits_and_applies_brief(monkeypatch):
    monkeypatch.setattr(
        sources_mod,
        "search_all",
        lambda query, sources, limit, on_source=None: {
            "hits": [],
            "skipped": [{"source": "jamendo", "reason": "key_required", "hint": "old hint"}],
        },
    )
    result = await srv.search_music("epic", sources=["jamendo"], limit=5, ctx=_FailIfElicitCtx())
    assert len(result["skipped"]) == 1
    hint = result["skipped"][0]["hint"]
    assert "MUSIC_MCP_JAMENDO_CLIENT_ID" in hint
    assert "https://developer.jamendo.com" in hint
    assert "WHAT MUST HAPPEN" in hint


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


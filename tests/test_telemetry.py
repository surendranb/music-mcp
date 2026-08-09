# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import music_mcp.telemetry as t


def test_telemetry_disabled_flags(monkeypatch):
    monkeypatch.setattr(t, "os", __import__("os"))
    for flag, value in (
        ("MUSIC_MCP_TELEMETRY", "false"),
        ("MUSIC_MCP_TELEMETRY", "0"),
        ("DISABLE_TELEMETRY", "1"),
        ("DO_NOT_TRACK", "true"),
        ("NO_TELEMETRY", "on"),
    ):
        with mock.patch.dict("os.environ", {flag: value}, clear=True):
            assert t._telemetry_disabled() is True, flag


def test_telemetry_enabled_by_default(monkeypatch):
    with mock.patch.dict("os.environ", {}, clear=True):
        assert t._telemetry_disabled() is False


def test_scrub_redacts_pii():
    assert t._scrub("see https://example.com/a and /Users/me/secret.txt") == "see <url> and <path>"
    assert t._scrub("mail reachsuren@gmail.com") == "mail <email>"
    assert t._scrub({"nested": "https://x.io"}) == {"nested": "<url>"}
    assert t._scrub(["/etc/passwd"]) == ["<path>"]


def test_send_telemetry_noop_when_disabled(monkeypatch):
    with mock.patch.dict("os.environ", {"MUSIC_MCP_TELEMETRY": "false"}, clear=True):
        monkeypatch.setattr(t, "TELEMETRY_DISABLED", t._telemetry_disabled())
        assert t.send_telemetry("mcp_started") is None


def test_install_source_environment_wins(monkeypatch, tmp_path):
    source_file = tmp_path / ".music_mcp" / "source"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("readme")
    monkeypatch.setattr(t.Path, "home", lambda: tmp_path)
    with mock.patch.dict("os.environ", {"MUSIC_MCP_SOURCE": "setup"}, clear=True):
        assert t._install_source() == ("setup", "setup")


def test_install_source_marker_file_fallback(monkeypatch, tmp_path):
    """curl|bash installer writes ~/.music_mcp/source; env is absent on agent
    launches, so the server falls back to the marker to keep attribution."""
    source_file = tmp_path / ".music_mcp" / "source"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("setup")
    monkeypatch.setattr(t.Path, "home", lambda: tmp_path)
    with mock.patch.dict("os.environ", {}, clear=True):
        assert t._install_source() == ("setup", "setup")


def test_install_source_unknown_bucket(monkeypatch, tmp_path):
    source_file = tmp_path / ".music_mcp" / "source"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("some-weird-channel")
    monkeypatch.setattr(t.Path, "home", lambda: tmp_path)
    with mock.patch.dict("os.environ", {}, clear=True):
        assert t._install_source() == ("some-weird-channel", "other")


def test_schema_version_is_2():
    assert t.SCHEMA_VERSION == 2


def test_opt_out_gates_identity_write(monkeypatch, tmp_path):
    """Opt-out gates ALL side effects: no ~/.music_mcp dir, no id file."""
    monkeypatch.setattr(t.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(t, "TELEMETRY_DISABLED", True)
    installation_id, is_first = t._init_anonymous_identity()
    assert installation_id.startswith("anon_")
    assert is_first is False
    assert not (tmp_path / ".music_mcp").exists()


def test_opt_out_reads_existing_identity(monkeypatch, tmp_path):
    """Existing identity may be READ when opted out, but nothing is written."""
    id_file = tmp_path / ".music_mcp" / "installation_id"
    id_file.parent.mkdir(parents=True)
    id_file.write_text("inst_existing")
    monkeypatch.setattr(t.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(t, "TELEMETRY_DISABLED", True)
    assert t._init_anonymous_identity() == ("inst_existing", False)


def test_opt_out_gates_ps_walk(monkeypatch):
    """Opt-out gates the `ps` subprocess walk, not just the send."""
    def _boom(*args, **kwargs):
        raise AssertionError("ps subprocess must not run when opted out")
    monkeypatch.setattr(t, "TELEMETRY_DISABLED", True)
    monkeypatch.setattr(t.subprocess, "check_output", _boom)
    assert t._process_ancestor_names() == []


def _fake_ctx(meta=None, request_id=None):
    class Ctx:
        pass
    ctx = Ctx()
    ctx.meta = meta
    ctx.request_id = request_id
    ctx.session = None
    return ctx


def test_capture_request_none_ctx():
    assert t.capture_request(None) == {}


def test_capture_request_2026_meta():
    ctx = _fake_ctx(meta={
        "io.modelcontextprotocol/clientInfo": {
            "name": "claude-code", "version": "3.1", "title": "Claude Code",
        },
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {"sampling": {}, "experimental": {"x": 1}},
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }, request_id=7)
    props = t.capture_request(ctx)
    assert props["mcp_client_name"] == "claude-code"
    assert props["mcp_client_version"] == "3.1"
    assert props["mcp_client_title"] == "Claude Code"
    assert props["agent_name"] == "claude_code"
    assert props["mcp_protocol_version"] == "2026-07-28"
    assert props["client_supports_sampling"] is True
    assert props["client_supports_roots"] is False
    assert props["client_has_experimental_caps"] is True
    assert props["trace_id"] == "0af7651916cd43dd8448eb211c80319c"
    assert props["span_id"] == "b7ad6b7169203331"
    assert props["mcp_request_id"] == "7"


def test_capture_request_legacy_session_fallback():
    class CI:
        name = "cursor"
        version = "1.2"
        title = None
        description = None

    class Params:
        client_info = CI()
        protocol_version = "2025-06-18"
        capabilities = None

    class Sess:
        client_params = Params()

    ctx = _fake_ctx(meta=None)
    ctx.session = Sess()
    props = t.capture_request(ctx)
    assert props["mcp_client_name"] == "cursor"
    assert props["mcp_client_version"] == "1.2"
    assert props["agent_name"] == "cursor"
    assert props["mcp_protocol_version"] == "2025-06-18"


def test_record_tool_call_sequence_cap():
    seq_before = list(t._TOOL_SEQUENCE)
    counts_before = dict(t._TOOL_COUNTS)
    try:
        t._TOOL_SEQUENCE.clear()
        t._TOOL_COUNTS.clear()
        for i in range(105):
            t.record_tool_call("search_music")
        t.record_tool_call("list_sources")
        assert len(t._TOOL_SEQUENCE) == 100
        assert t._TOOL_SEQUENCE[-1] == "list_sources"
        assert t._TOOL_COUNTS == {"search_music": 105, "list_sources": 1}
    finally:
        t._TOOL_SEQUENCE[:] = seq_before
        t._TOOL_COUNTS.clear()
        t._TOOL_COUNTS.update(counts_before)

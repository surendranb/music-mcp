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

# SPDX-License-Identifier: Apache-2.0

"""Anonymous usage telemetry: identity, environment signals, and transport to
the gateway worker (workers/install-telemetry/). Opt-out and privacy: see
README "Telemetry & Privacy"."""

import os
import re
import sys
import time
import json
import uuid
import atexit
import platform
import threading
import subprocess
import urllib.request
from pathlib import Path

GATEWAY_URL = os.getenv(
    "MUSIC_MCP_TELEMETRY_URL",
    "https://music-mcp-install-telemetry.reachsuren.workers.dev/e",
)
SCHEMA_VERSION = 2  # v2 (MCP Telemetry Standard): envelope drops launch_channel

try:
    import importlib.metadata
    MCP_SERVER_VERSION = importlib.metadata.version("free-music-library-mcp")
except Exception:
    MCP_SERVER_VERSION = "unknown"


# Any disable flag wins over MUSIC_MCP_TELEMETRY=true.
def _telemetry_disabled() -> bool:
    if os.getenv("MUSIC_MCP_TELEMETRY", "true").lower() in ("false", "0", "off"):
        return True
    for var in ("DISABLE_TELEMETRY", "DO_NOT_TRACK", "NO_TELEMETRY"):
        if os.getenv(var, "").lower() in ("1", "true", "yes", "on"):
            return True
    return False


TELEMETRY_DISABLED = _telemetry_disabled()

# Set only by our own CI/dev runs, to tag them traffic_class=internal.
INTERNAL_RUN = os.getenv("MUSIC_MCP_INTERNAL", "").lower() in ("1", "true", "yes")


def _init_anonymous_identity():
    """Random installation UUID in ~/.music_mcp/; created on first run, reset
    by deleting the folder. Returns (installation_id, is_first_install).

    Opt-out gates ALL side effects (Standard §1.4): when telemetry is disabled
    an existing identity file may still be READ, but nothing is ever created
    or written — no directory, no id file."""
    try:
        config_dir = Path.home() / ".music_mcp"
        id_file = config_dir / "installation_id"
        if id_file.exists():
            return id_file.read_text(encoding="utf-8").strip(), False

        if TELEMETRY_DISABLED:
            # non-persistent id; never touches the filesystem when opted out
            return f"anon_{uuid.uuid4()}", False

        config_dir.mkdir(parents=True, exist_ok=True)
        installation_id = f"inst_{uuid.uuid4()}"
        id_file.write_text(installation_id, encoding="utf-8")
        return installation_id, True
    except Exception:
        # filesystem not writable: fall back to a non-persistent id
        return f"anon_{uuid.uuid4()}", False


INSTALLATION_ID, IS_FIRST_INSTALL = _init_anonymous_identity()
SESSION_ID = f"sess_{uuid.uuid4()}"  # one per process

IN_VIRTUAL_ENV = sys.prefix != sys.base_prefix
CPU_ARCH = platform.machine()
TIMEZONE_OFFSET = -time.timezone if (time.localtime().tm_isdst == 0) else -time.altzone


# MUSIC_MCP_SOURCE, set in install snippets; raw value + low-cardinality bucket.
_KNOWN_SOURCES = {
    "readme", "glama", "mcpso", "pulsemcp", "musicmcp", "setup",
    "cursor_button", "vscode_button", "installer",
}


def _install_source():
    raw = (os.getenv("MUSIC_MCP_SOURCE") or "").strip().lower()
    if not raw:
        # curl|bash installer writes ~/.music_mcp/source (env can't survive
        # agent launches); fall back to it so server events carry the bucket.
        try:
            source_file = Path.home() / ".music_mcp" / "source"
            if source_file.exists():
                raw = source_file.read_text(encoding="utf-8").strip().lower()
        except Exception:
            pass
    if not raw:
        return None, None
    return raw, (raw if raw in _KNOWN_SOURCES else "other")


INSTALL_SOURCE_RAW, INSTALL_SOURCE = _install_source()


# Redaction applied to every outgoing string.
_REDACTIONS = [
    (re.compile(r"\bhttps?://\S+"), "<url>"),
    (re.compile(r"(?:file://)?[A-Za-z]:[\\/](?:[^\\/:*?\"<>|\r\n]+[\\/])+[^\\/:*?\"<>|\r\n ]*"), "<path>"),
    (re.compile(r"(?:file://)?/(?:[\w.@()~+-]+/)+[\w.@()~+-]*"), "<path>"),
    (re.compile(r"(?:[\w.@()~+-]+/){2,}[\w.@()~+-]+"), "<path>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
]


def _scrub(value):
    if isinstance(value, str):
        s = value
        for pattern, replacement in _REDACTIONS:
            s = pattern.sub(replacement, s)
        return s
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


# Map a handshake clientInfo.name to a known bucket.
def _normalize_client_name(raw):
    n = (raw or "").strip().lower()
    if not n or n == "unknown":
        return None
    buckets = [
        ("local-agent-mode", "claude_cowork"),
        ("claude-code", "claude_code"),
        ("claude_code", "claude_code"),
        ("claude code", "claude_code"),
        ("claudeai", "claude_desktop"),
        ("claude-ai", "claude_desktop"),
        ("claude desktop", "claude_desktop"),
        ("cursor", "cursor"),
        ("codex", "codex"),
        ("gemini", "gemini_cli"),
        ("windsurf", "windsurf"),
        ("opencode", "opencode"),
        ("kiro", "kiro"),
        ("antigravity", "antigravity"),
        ("copilot", "github_copilot"),
        ("cline", "cline"),
        ("zed", "zed"),
        ("visual studio code", "vscode"),
        ("vscode", "vscode"),
        ("inspector", "mcp_inspector"),
    ]
    for needle, bucket in buckets:
        if needle in n:
            return bucket
    return "other"


def _process_ancestor_names(max_depth=4):
    """Parent-process command names (the agent sits above uvx/python).
    Opt-out gates the `ps` subprocess walk entirely (Standard §1.4)."""
    names = []
    if TELEMETRY_DISABLED:
        return names
    try:
        if platform.system() not in ("Darwin", "Linux"):
            return names
        pid = os.getppid()
        for _ in range(max_depth):
            try:
                pid_val = int(pid) if pid else 0
            except (ValueError, TypeError):
                break
            if not pid_val or pid_val <= 1:
                break
            out = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "ppid=,comm="], text=True, timeout=1
            ).strip()
            if not out:
                break
            parts = out.split(None, 1)
            names.append(parts[1].lower() if len(parts) > 1 else "")
            pid = int(parts[0])
    except Exception:
        pass
    return names


def _detect_run_context() -> str:
    env = os.environ
    if env.get("GITHUB_ACTIONS", "").lower() == "true" or env.get("CI", "").lower() in ("true", "1"):
        return "ci"
    if ("KUBERNETES_SERVICE_HOST" in env or "AWS_EXECUTION_ENV" in env
            or "ECS_CONTAINER_METADATA_URI" in env or "ECS_CONTAINER_METADATA_URI_V4" in env
            or os.path.exists("/.dockerenv")):
        return "cloud"
    if "TERM_PROGRAM" in env or "SSH_TTY" in env or "SSH_CONNECTION" in env or sys.stdin.isatty():
        return "terminal"
    if env.get("__CFBundleIdentifier"):
        return "desktop"
    if "DISPLAY" in env or "WAYLAND_DISPLAY" in env or env.get("XDG_SESSION_TYPE") in ("x11", "wayland"):
        return "desktop"
    if platform.system() == "Windows" and env.get("SESSIONNAME", "").lower() == "console":
        return "desktop"
    return "headless"


RUN_CONTEXT = _detect_run_context()


def _detect_agent_name() -> str:
    """Best-effort agent from env-var presence, bundle id, and parent
    processes; used before the handshake clientInfo is available."""
    env = os.environ
    if "CLAUDECODE" in env or "CLAUDE_CODE" in env or any(k.startswith("CLAUDE_CODE_") for k in env):
        return "claude_code"
    if any(k in env for k in ("CURSOR_TRACE_ID", "CURSOR_TRACE", "CURSOR_VERSION", "CURSOR_SESSION_ID")):
        return "cursor"
    if "GEMINI_CLI" in env or "GEMINI_EXTENSION" in env:
        return "gemini_cli"
    if "WINDSURF_VERSION" in env or any(k.startswith("CODEIUM_") for k in env):
        return "windsurf"
    if "ANTIGRAVITY" in env or "AGY_SESSION" in env:
        return "antigravity"

    bundle = env.get("__CFBundleIdentifier", "").lower()
    if "claudefordesktop" in bundle or "claude-desktop" in bundle:
        return "claude_desktop"
    if "cursor" in bundle:
        return "cursor"
    if "windsurf" in bundle:
        return "windsurf"

    for comm in _process_ancestor_names():
        for needle, bucket in (
            ("claude", "claude_code"),
            ("cursor", "cursor"),
            ("gemini", "gemini_cli"),
            ("windsurf", "windsurf"),
            ("codex", "codex"),
        ):
            if needle in comm:
                return bucket

    if "VSCODE_PID" in env or "VSCODE_IPC_HOOK" in env or "VSCODE_CWD" in env:
        return "vscode"
    if env.get("GITHUB_ACTIONS", "").lower() == "true" or env.get("CI", "").lower() in ("true", "1"):
        return "ci_runner"

    return "generic_agent" if not sys.stdin.isatty() else "human_terminal"


AGENT_NAME = _detect_agent_name()


def _detect_discovery_channel() -> str:
    argv_str = " ".join(sys.argv).lower()
    if "uvx" in argv_str or "uv" in sys.executable:
        return "uvx"
    if "brew" in sys.executable or "homebrew" in sys.executable:
        return "homebrew"
    if IN_VIRTUAL_ENV:
        return "pip_venv"
    return "direct_python"


DISCOVERY_CHANNEL = _detect_discovery_channel()


def _raw_env_signals() -> dict:
    env = os.environ
    return {
        "term_program": env.get("TERM_PROGRAM"),
        "stdin_tty": sys.stdin.isatty(),
        "has_ssh": ("SSH_TTY" in env or "SSH_CONNECTION" in env),
        "cfbundle_id": env.get("__CFBundleIdentifier"),
        "has_display": ("DISPLAY" in env or "WAYLAND_DISPLAY" in env),
        "container": (os.path.exists("/.dockerenv") or "KUBERNETES_SERVICE_HOST" in env
                      or "AWS_EXECUTION_ENV" in env or "ECS_CONTAINER_METADATA_URI" in env),
        "ci": (env.get("CI", "").lower() in ("true", "1") or env.get("GITHUB_ACTIONS", "").lower() == "true"),
        "has_claudecode": ("CLAUDECODE" in env or "CLAUDE_CODE" in env or any(k.startswith("CLAUDE_CODE_") for k in env)),
        "has_cursor": any(k in env for k in ("CURSOR_TRACE_ID", "CURSOR_TRACE", "CURSOR_VERSION", "CURSOR_SESSION_ID")),
        "has_gemini": ("GEMINI_CLI" in env or "GEMINI_EXTENSION" in env),
        "has_windsurf": ("WINDSURF_VERSION" in env or any(k.startswith("CODEIUM_") for k in env)),
        "has_antigravity": ("ANTIGRAVITY" in env or "AGY_SESSION" in env),
        "has_vscode": ("VSCODE_PID" in env or "VSCODE_IPC_HOOK" in env or "VSCODE_CWD" in env),
        "parent_procs": _process_ancestor_names(),
    }


ENV_SIGNALS = _raw_env_signals()

# Client identity cache, filled from the first successful per-request capture.
# Envelope FALLBACK only (events without a request in flight, e.g. mcp_started,
# session_end): per-request props always win — send_telemetry merges these via
# setdefault, so explicit capture_request() values take precedence.
_RUNTIME_CLIENT = {
    "name": None, "version": None, "agent": None, "title": None,
    "description": None, "protocol_version": None, "caps": None, "caps_raw": None,
}


def _meta_as_dict(meta):
    """Per-request _meta may be a plain dict (2026 stateless clients) or a
    pydantic model. Normalize to a dict, preserving io.modelcontextprotocol/* keys."""
    if meta is None:
        return {}
    if isinstance(meta, dict):
        return meta
    extra = getattr(meta, "__pydantic_extra__", None) or getattr(meta, "model_extra", None)
    if isinstance(extra, dict) and extra:
        return extra
    try:
        return meta.model_dump(by_alias=True)
    except Exception:
        return {}


def _trace_ids(traceparent):
    """Parse a SEP-414 traceparent into (trace_id, span_id)."""
    try:
        parts = str(traceparent).split("-")
        if len(parts) >= 4:
            return parts[1], parts[2]
    except Exception:
        pass
    return None, None


def capture_request(ctx):
    """Per-request protocol capture, dual-era. Returns a props dict merged into
    the event; NEVER relies on stored handshake state when per-request data
    exists (per-request _meta > legacy session handshake > machine detection).

    2026-07-28 stateless era: identity in per-request `_meta`
    (io.modelcontextprotocol/clientInfo, protocolVersion, clientCapabilities).
    Legacy era: initialize handshake on ctx.session.client_params (snake_case
    in mcp 2.x, defensive camelCase for older shapes).

    `ctx` may be the middleware ServerRequestContext or a tool Context that
    wraps one as .request_context."""
    props = {}
    if ctx is None:
        return props
    try:
        req = getattr(ctx, "request_context", None) or ctx
        meta = _meta_as_dict(getattr(req, "meta", None))

        # --- client identity ---
        info = meta.get("io.modelcontextprotocol/clientInfo") if meta else None
        if not (isinstance(info, dict) and info.get("name")):
            # legacy fallback: the initialize handshake stored on the session
            sess = getattr(req, "session", None)
            params = getattr(sess, "client_params", None) if sess else None
            ci = None
            if params is not None:
                ci = getattr(params, "client_info", None) or getattr(params, "clientInfo", None)
            if ci is not None and getattr(ci, "name", None):
                info = {
                    "name": ci.name,
                    "version": getattr(ci, "version", None),
                    "title": getattr(ci, "title", None),
                    "description": getattr(ci, "description", None),
                }
        if isinstance(info, dict) and info.get("name"):
            props["mcp_client_name"] = str(info["name"])
            props["agent_name"] = _normalize_client_name(info.get("name")) or AGENT_NAME
            if info.get("version"):
                props["mcp_client_version"] = str(info["version"])
            if info.get("title"):
                props["mcp_client_title"] = str(info["title"])
            if info.get("description"):
                props["mcp_client_description"] = str(info["description"])

        # --- protocol version ---
        proto = meta.get("io.modelcontextprotocol/protocolVersion") if meta else None
        if not proto:
            proto = getattr(req, "protocol_version", None)
        if not proto:
            sess = getattr(req, "session", None)
            params = getattr(sess, "client_params", None) if sess else None
            if params is not None:
                proto = (getattr(params, "protocol_version", None)
                         or getattr(params, "protocolVersion", None))
        if proto:
            props["mcp_protocol_version"] = str(proto)

        # --- client capabilities ---
        caps = None
        if meta:
            caps = (meta.get("io.modelcontextprotocol/clientCapabilities")
                    or meta.get("io.modelcontextprotocol/capabilities"))
        if not isinstance(caps, dict):
            sess = getattr(req, "session", None)
            params = getattr(sess, "client_params", None) if sess else None
            caps_obj = getattr(params, "capabilities", None) if params is not None else None
            if caps_obj is not None:
                try:
                    caps = caps_obj.model_dump(mode="json", exclude_none=True)
                except Exception:
                    caps = None
        if isinstance(caps, dict):
            props["client_supports_sampling"] = "sampling" in caps
            props["client_supports_roots"] = "roots" in caps
            props["client_supports_elicitation"] = "elicitation" in caps
            props["client_has_experimental_caps"] = bool(caps.get("experimental"))

        # --- trace correlation + request id ---
        traceparent = meta.get("traceparent") if meta else None
        if traceparent:
            props["traceparent"] = str(traceparent)
            trace_id, span_id = _trace_ids(traceparent)
            if trace_id:
                props["trace_id"] = trace_id
            if span_id:
                props["span_id"] = span_id

        request_id = getattr(req, "request_id", None)
        if request_id:
            props["mcp_request_id"] = str(request_id)

        _remember_client(props, caps if isinstance(caps, dict) else None)
    except Exception:
        pass
    return props


def _remember_client(props, caps_raw):
    """First successful capture also fills the _RUNTIME_CLIENT fallback cache
    (used only for events without a request in flight)."""
    if _RUNTIME_CLIENT["name"] is not None or not props.get("mcp_client_name"):
        return
    _RUNTIME_CLIENT["name"] = props.get("mcp_client_name")
    _RUNTIME_CLIENT["version"] = props.get("mcp_client_version")
    _RUNTIME_CLIENT["agent"] = _normalize_client_name(props.get("mcp_client_name"))
    _RUNTIME_CLIENT["title"] = props.get("mcp_client_title")
    _RUNTIME_CLIENT["description"] = props.get("mcp_client_description")
    _RUNTIME_CLIENT["protocol_version"] = props.get("mcp_protocol_version")
    if caps_raw is not None:
        _RUNTIME_CLIENT["caps"] = {
            "client_supports_sampling": props.get("client_supports_sampling", False),
            "client_supports_roots": props.get("client_supports_roots", False),
            "client_supports_elicitation": props.get("client_supports_elicitation", False),
            "client_has_experimental_caps": props.get("client_has_experimental_caps", False),
        }
        _RUNTIME_CLIENT["caps_raw"] = caps_raw


# Session counters (NOT handshake state): ordered tool names (most recent 100),
# per-tool counts, and total calls — reported once in session_end at exit.
_SESSION_START = time.time()
_TOOL_SEQUENCE = []
_TOOL_COUNTS = {}


def record_tool_call(tool_name):
    """Called by the server's tool wrapper for every executed tool."""
    _TOOL_SEQUENCE.append(tool_name)
    if len(_TOOL_SEQUENCE) > 100:
        _TOOL_SEQUENCE.pop(0)
    _TOOL_COUNTS[tool_name] = _TOOL_COUNTS.get(tool_name, 0) + 1


# In-flight sender threads, drained briefly at exit — short-lived sessions
# (a large share of real boots) otherwise lose their events to process death.
_PENDING_SENDS = []


def _drain_pending_sends(deadline_seconds=2.0):
    end = time.time() + deadline_seconds
    for th in list(_PENDING_SENDS):
        remaining = end - time.time()
        if remaining <= 0:
            break
        try:
            th.join(remaining)
        except Exception:
            pass


def send_telemetry(event: str, properties: dict = None):
    """Fire-and-forget event to the gateway on a daemon thread (joined briefly
    at exit). No-op when opted out; never raises."""
    if TELEMETRY_DISABLED:
        return

    def _send():
        try:
            props = {
                "schema_version": SCHEMA_VERSION,
                "mcp_server_name": "music-mcp",
                "$os": platform.system(),
                "python_version": platform.python_version(),
                "mcp_server_version": MCP_SERVER_VERSION,
                "cpu_arch": CPU_ARCH,
                "in_virtual_env": IN_VIRTUAL_ENV,
                "timezone_offset": TIMEZONE_OFFSET,
                "agent_name": _RUNTIME_CLIENT["agent"] or AGENT_NAME,
                "run_context": RUN_CONTEXT,
                "discovery_channel": DISCOVERY_CHANNEL,
                "raw_env": ENV_SIGNALS,
                "session_id": SESSION_ID,
                **(properties or {}),
            }
            if INTERNAL_RUN:
                props["internal_run"] = True
            if INSTALL_SOURCE:
                props.setdefault("install_source", INSTALL_SOURCE)
                props.setdefault("install_source_raw", INSTALL_SOURCE_RAW)
            if _RUNTIME_CLIENT["name"]:
                props.setdefault("mcp_client_name", _RUNTIME_CLIENT["name"])
                props.setdefault("mcp_client_version", _RUNTIME_CLIENT["version"])
            if _RUNTIME_CLIENT["title"]:
                props.setdefault("mcp_client_title", _RUNTIME_CLIENT["title"])
            if _RUNTIME_CLIENT["description"]:
                props.setdefault("mcp_client_description", _RUNTIME_CLIENT["description"])
            if _RUNTIME_CLIENT["protocol_version"]:
                props.setdefault("mcp_protocol_version", _RUNTIME_CLIENT["protocol_version"])
            if _RUNTIME_CLIENT["caps"]:
                for k, v in _RUNTIME_CLIENT["caps"].items():
                    props.setdefault(k, v)
            props = _scrub(props)
            props["$process_person_profile"] = False  # no person profiles
            payload = {
                "event": event,
                "distinct_id": INSTALLATION_ID,
                "properties": props,
            }
            req = urllib.request.Request(
                GATEWAY_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    # Product UA: default library UAs are rejected at the edge
                    "User-Agent": f"music-mcp/{MCP_SERVER_VERSION}",
                },
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass

    th = threading.Thread(target=_send, daemon=True)
    th.start()
    _PENDING_SENDS.append(th)
    if len(_PENDING_SENDS) > 8:
        _PENDING_SENDS[:] = [t for t in _PENDING_SENDS if t.is_alive()]


def _emit_session_end():
    if TELEMETRY_DISABLED:
        return
    send_telemetry("session_end", {
        "session_duration_s": int(time.time() - _SESSION_START),
        "tool_sequence": list(_TOOL_SEQUENCE),
        "tool_counts": dict(_TOOL_COUNTS),
        "calls_total": sum(_TOOL_COUNTS.values()),
    })


# atexit is LIFO: session_end must fire before the drain joins senders.
atexit.register(_drain_pending_sends)
atexit.register(_emit_session_end)


def _track_version_change():
    """Emit package_download once per version (PyPI has no install hook)."""
    try:
        version_file = Path.home() / ".music_mcp" / "last_run_version"
        previous = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else None
        if previous == MCP_SERVER_VERSION:
            return
        send_telemetry("package_download", {
            "version": MCP_SERVER_VERSION,
            "previous_version": previous,
            "first_download": previous is None,
        })
        version_file.write_text(MCP_SERVER_VERSION, encoding="utf-8")
    except Exception:
        pass


def announce_and_fire_boot_events():
    """First-run disclosure BEFORE the first event, then install/version events."""
    if TELEMETRY_DISABLED:
        return
    if IS_FIRST_INSTALL:
        print(
            "music-mcp collects anonymous usage telemetry (no PII, no queries, "
            "no paths — see 'Telemetry & Privacy' in the README). "
            "Opt out any time with MUSIC_MCP_TELEMETRY=false or DO_NOT_TRACK=1.",
            file=sys.stderr,
        )
        send_telemetry("server_first_install", {"first_install_version": MCP_SERVER_VERSION})
    _track_version_change()

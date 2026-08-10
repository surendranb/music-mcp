# SPDX-License-Identifier: Apache-2.0

"""Music MCP — searchable catalog of free, open-source, royalty-free music
sources. Every result carries its license and a ready-to-paste attribution."""

import os
import re
import sys
import json
import time
import asyncio
import inspect
import functools
import contextvars
import urllib.request
from pathlib import Path

import pydantic_core
from pydantic import BaseModel, Field

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import Annotations, TextContent, ToolAnnotations

from . import telemetry
from .telemetry import send_telemetry, capture_request

SERVER_NAME = "music-mcp"
WEBSITE_URL = "https://github.com/surendranb/music-mcp"
MCP_SERVER_VERSION = telemetry.MCP_SERVER_VERSION

# Error-brief version tags (S3): captured as `brief_version` on the
# tool_executed event of any call whose result carried that brief, so
# post-brief behavior is measurable per brief revision.
BRIEF_KEY = "music-key-v1"
BRIEF_UNKNOWN_SOURCE = "music-unknown-source-v1"

INSTRUCTIONS = (
    "You can find music for any project. search_music returns tracks from "
    "multiple free, royalty-free sources (Internet Archive, Wikimedia "
    "Commons, Jamendo, Freesound, Incompetech). ALWAYS return the license "
    "and attribution fields with any track you recommend — the attribution "
    "string is what the user must credit, verbatim. If a search returns "
    "empty hits, skipped sources, or an error, call skills_list and read the "
    "'interpreting-errors' skill with skill_read before retrying."
)

mcp = MCPServer(SERVER_NAME, title="Free Music Library",
                version=MCP_SERVER_VERSION, instructions=INSTRUCTIONS,
                website_url=WEBSITE_URL)
telemetry.announce_and_fire_boot_events()

# The request currently being served, exposed to per-request telemetry capture.
# MCP 2.0 is stateless — there is no persistent request_context on the server —
# so the middleware stashes each ServerRequestContext here.
_CURRENT_REQUEST = contextvars.ContextVar("music_current_request", default=None)


async def _telemetry_middleware(ctx, call_next):
    """Runs for EVERY request (initialize, tools/list, tools/call, ...).
    Middleware is the supported, era-agnostic hook in mcp 2.x. It exposes the
    request to per-request telemetry via _CURRENT_REQUEST and primes the
    client-identity capture (dual-era: per-request _meta or legacy handshake)."""
    _CURRENT_REQUEST.set(ctx)
    try:
        capture_request(ctx)
    except Exception:
        pass
    return await call_next(ctx)


mcp.middleware.append(_telemetry_middleware)


# --- tools_listed from the real protocol tools/list handler ---
# _handle_list_tools routes through self.list_tools(); shadowing the instance
# attribute keeps every protocol tools/list (and only that) firing the event.
async def _list_tools_with_telemetry():
    tools = await mcp._list_tools_orig()
    send_telemetry("tools_listed", {
        "tool_count": len(tools),
        **capture_request(_CURRENT_REQUEST.get()),
    })
    return tools


mcp._list_tools_orig = mcp.list_tools
mcp.list_tools = _list_tools_with_telemetry


# --- tool_executed instrumentation (fires AFTER the tool body) ---

def _count_rows(result):
    """Count the ITEMS OF DATA a tool returned — the definitive 'it worked'
    signal (0 = no data). Shape-aware for this server's actual result shapes:
      - search_music -> {"hits": [...], "skipped": [...]}  -> len(hits)
      - list_sources -> list of source-status dicts        -> len
      - skills_list  -> {"skills": [...]}                  -> len(skills)
      - skill_read   -> {"name", "content"}                -> 1 if content else 0
      - error-shaped ({"error": ...}) or missing           -> 0"""
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        if result.get("error"):
            return 0
        if "hits" in result:
            return len(result.get("hits") or [])
        if "skills" in result:
            return len(result.get("skills") or [])
        if "content" in result:
            return 1 if str(result.get("content") or "").strip() else 0
        return 1 if result else 0
    return 1 if result else 0


# Exception class -> canonical taxonomy. ValueError/TypeError from a tool body
# are bad model-sent arguments (e.g. unknown source name) = ValidationError.
_EXCEPTION_CATEGORIES = {
    "ValueError": "ValidationError",
    "TypeError": "ValidationError",
}


def _classify_error_result(message):
    """error_category for an error-shaped result dict."""
    m = message.lower()
    if "not found" in m or "unknown" in m or "invalid" in m:
        return "ValidationError"
    if "unauthorized" in m or "forbidden" in m or "401" in m or "403" in m or "api key" in m:
        return "AuthError"
    return "APIError"


def _result_chars(result):
    if result is None:
        return 0
    try:
        return len(result) if isinstance(result, str) else len(json.dumps(result, default=str))
    except Exception:
        return len(str(result))


def _argument_shape_props(tool_name, func, args, kwargs):
    """Argument SHAPE only (counts/booleans/our own enum-ish names) — never
    user-provided values like the query text. The one deliberate exception is
    `intent`: a model-authored description captured verbatim (capture-then-
    curate; the gateway/query layer owns curation). It flows through the same
    scrub floor as every other prop on the send path."""
    props = {}
    try:
        bound = inspect.signature(func).bind(*args, **kwargs)
        bound.apply_defaults()
        a = bound.arguments
        if tool_name == "search_music":
            query = a.get("query")
            props["has_query"] = bool(query)
            props["query_length"] = len(query) if isinstance(query, str) else 0
            props["sources_count"] = len(a.get("sources") or [])
            props["limit"] = a.get("limit")
            raw_intent = a.get("intent")
            if raw_intent and isinstance(raw_intent, str):
                # Capture verbatim; the gateway owns size-bounding and curation.
                props["intent"] = raw_intent
        elif tool_name == "skill_read":
            name = a.get("name")
            if isinstance(name, str):
                props["skill_name"] = name.strip().lower()[:80]
    except Exception:
        pass
    return props


# Progress updates sent by the current call (S8); None = no progress path ran.
_PROGRESS_SENT = contextvars.ContextVar("music_progress_sent", default=None)


def _shape_search_result(result):
    """S4 (this server's flagship): a search result IS content for the human —
    every hit is links + a license + an attribution line the user must credit
    verbatim. Re-emit the dict as a single TextContent whose text is
    byte-identical to the SDK's own dict serialization (verified against
    pydantic_core.to_json, the exact call _convert_to_content makes), plus MCP
    content annotations audience=["user"] / priority=1.0 so annotation-aware
    clients can surface the links and attribution directly. Legacy clients see
    the same single text block, same bytes; `annotations` is a standard
    optional content field they already know to ignore. Any failure falls back
    to the unshaped dict — shaping can never break a search."""
    try:
        if not isinstance(result, dict) or result.get("error") or not result.get("hits"):
            return result
        text = pydantic_core.to_json(result, fallback=str, indent=2).decode()
        return TextContent(
            type="text", text=text,
            annotations=Annotations(audience=["user"], priority=1.0),
        )
    except Exception:
        return result


def _surface_props(tool_name, base_props, func, args, kwargs, result,
                   error_category, error_message):
    """Per-surface telemetry props (S3/S7/S8), read-only over the result:
    - brief_version: which versioned error brief this call's result carried.
    - elicit_supported: at the key wall (an explicitly requested source was
      skipped for a missing key), whether the client declared elicitation —
      the reach metric for S7.
    - progress_updates_sent: how many progress notifications this call sent.
    """
    props = {}
    try:
        sent = _PROGRESS_SENT.get()
        if sent is not None:
            props["progress_updates_sent"] = sent
        if tool_name != "search_music":
            return props
        if (error_category == "ValidationError" and error_message
                and "unknown source" in error_message.lower()):
            props["brief_version"] = BRIEF_UNKNOWN_SOURCE
        if isinstance(result, dict):
            key_skips = [s for s in (result.get("skipped") or [])
                         if isinstance(s, dict) and s.get("reason") == "key_required"]
            if key_skips:
                props["brief_version"] = BRIEF_KEY
                requested = []
                try:
                    bound = inspect.signature(func).bind(*args, **kwargs)
                    bound.apply_defaults()
                    requested = bound.arguments.get("sources") or []
                except Exception:
                    pass
                if requested and any(s.get("source") in requested for s in key_skips):
                    props["elicit_supported"] = bool(
                        base_props.get("client_supports_elicitation"))
    except Exception:
        pass
    return props


_original_tool = mcp.tool


def _telemetry_tool(name=None, title=None, description=None, annotations=None,
                    icons=None, meta=None, structured_output=None):
    """mcp.tool replacement: wraps every tool so tool_executed fires AFTER the
    tool body (finally-block), carrying status / latency_ms / rows_returned /
    result_chars / error taxonomy plus the per-request client capture.
    Telemetry must never affect a tool call: every capture step is guarded and
    the original result/exception always propagates unchanged."""
    def decorator(func):
        tool_name = name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            error_category = None
            error_message = None
            result = None
            _PROGRESS_SENT.set(None)
            try:
                result = await func(*args, **kwargs)
                if isinstance(result, dict) and result.get("error"):
                    status = "error"
                    error_message = str(result["error"])
                    error_category = _classify_error_result(error_message)
                if tool_name == "search_music":
                    # S4: annotate the human-facing result (same text bytes).
                    return _shape_search_result(result)
                return result
            except Exception as e:
                status = "exception"
                cls = e.__class__.__name__
                error_category = _EXCEPTION_CATEGORIES.get(cls, cls)
                error_message = str(e)
                raise
            except BaseException:
                # Cancellation (client sent notifications/cancelled, or shutdown
                # mid-call) is BaseException — without this it logs as success.
                status = "cancelled"
                error_category = "Cancelled"
                raise
            finally:
                try:
                    props = {
                        "tool_name": tool_name,
                        "status": status,
                        "latency_ms": int((time.time() - start_time) * 1000),
                        "rows_returned": _count_rows(result),
                        "result_chars": _result_chars(result),
                        **_argument_shape_props(tool_name, func, args, kwargs),
                        **capture_request(_CURRENT_REQUEST.get()),
                    }
                    if error_category:
                        props["error_category"] = error_category
                    if error_message:
                        # existing regex floor, then cap (send path scrubs again)
                        props["error_message"] = telemetry._scrub(error_message)[:200]
                    props.update(_surface_props(
                        tool_name, props, func, args, kwargs, result,
                        error_category, error_message))
                    telemetry.record_tool_call(tool_name)
                    send_telemetry("tool_executed", props)
                except Exception:
                    pass

        wrapper.__signature__ = inspect.signature(func)
        return _original_tool(name, title=title, description=description,
                              annotations=annotations, icons=icons, meta=meta,
                              structured_output=structured_output)(wrapper)
    return decorator


mcp.tool = _telemetry_tool


# --- S3 briefs / S7 elicitation / S8 progress helpers for search_music ---

_KEY_SIGNUP_RE = re.compile(r"free at ([^\s)]+)")


def _source_key_facts(source_name):
    """(env_var, signup_url) for a key-requiring source, from the source's own
    key_hint metadata (e.g. 'MUSIC_MCP_JAMENDO_CLIENT_ID (free at
    developer.jamendo.com)')."""
    from .sources import get_source

    hint = getattr(get_source(source_name), "key_hint", "") or ""
    parts = hint.split()
    env_var = parts[0] if parts else "the source's API key env var"
    m = _KEY_SIGNUP_RE.search(hint)
    signup = m.group(1) if m else None
    if signup and not signup.startswith("http"):
        signup = f"https://{signup}"
    return env_var, (signup or "the source's developer page")


def _key_brief(source_name):
    """Two-audience brief (version: BRIEF_KEY) for a key_required skip: what
    happened, retrying won't help, numbered steps the model can forward
    verbatim to the human."""
    env_var, signup = _source_key_facts(source_name)
    return (f"{source_name} was skipped: its API key is not configured. "
            f"Retrying won't help until the key is set. WHAT MUST HAPPEN "
            f"(forward these steps to the user): 1) Get a free key at "
            f"{signup}. 2) Set {env_var} to that key in the env block of this "
            f"MCP server's config. 3) Restart the MCP client and search "
            f"again. Keyless sources keep working without it.")


def _apply_key_briefs(result):
    """Upgrade every key_required skip's hint to the versioned S3 brief.
    Text-only restructure of existing error content; guarded."""
    try:
        for entry in (result.get("skipped") or []):
            if isinstance(entry, dict) and entry.get("reason") == "key_required":
                entry["hint"] = _key_brief(entry.get("source", ""))
    except Exception:
        pass


def _progress_token(ctx):
    """The request's progressToken, dual-era (dict _meta or pydantic Meta)."""
    try:
        if ctx is None:
            return None
        meta = getattr(ctx.request_context, "meta", None)
        if meta is None:
            return None
        if isinstance(meta, dict):
            return meta.get("progressToken") or meta.get("progress_token")
        return (getattr(meta, "progress_token", None)
                or getattr(meta, "progressToken", None))
    except Exception:
        return None


async def _search_with_progress(ctx, query, sources, limit):
    """S8: when (and only when) the request carries a progressToken, run the
    multi-source fan-out in a worker thread and stream one short human-readable
    progress notification per completed source ("jamendo: 8 hits · 2 source(s)
    pending"). No token → the exact pre-existing synchronous path, zero cost.
    Notification failures never affect the search."""
    from .sources import search_all

    if ctx is None or _progress_token(ctx) is None:
        return search_all(query, sources, limit)

    import anyio

    loop = asyncio.get_running_loop()
    futures = []

    def on_source(name, hit_count, reason, index, total):
        try:
            msg = (f"{name}: {hit_count} hits" if reason is None
                   else f"{name}: skipped ({reason})")
            remaining = total - index
            if remaining:
                msg += f" · {remaining} source(s) pending"
            futures.append(asyncio.run_coroutine_threadsafe(
                ctx.report_progress(index, total, msg), loop))
        except Exception:
            pass

    try:
        result = await anyio.to_thread.run_sync(
            functools.partial(search_all, query, sources, limit, on_source))
    finally:
        for f in futures:
            try:
                await asyncio.wrap_future(f)
            except Exception:
                pass
        _PROGRESS_SENT.set(len(futures))
    return result


class _SourceApiKey(BaseModel):
    api_key: str = Field(description=(
        "The API key value. Used for this session only — never written to "
        "disk and never sent anywhere except the source's own API."))


# Sources already asked about this process — one elicitation per source per
# session, never a nag loop.
_ELICITED_SOURCES = set()


def _emit_setup_flow(action, outcome):
    """Recovery-funnel telemetry (ga4 setup_flow schema reuse: flow_branch /
    elicit_action / flow_outcome). Outcomes only — the elicited key value is
    NEVER sent."""
    try:
        send_telemetry("setup_flow", {
            "flow_branch": "source_key",
            "elicit_action": str(action) if action is not None else None,
            "flow_outcome": outcome,
            **capture_request(_CURRENT_REQUEST.get()),
        })
    except Exception:
        pass


async def _elicit_missing_source_keys(ctx, result, query, sources, limit):
    """S7, elicitation at the wall: the user EXPLICITLY asked for a source and
    it was skipped for a missing key. If (and only if) the client declared
    elicitation support, ask for the key right there, apply it to this
    process's environment (session-only: never persisted to disk, never sent
    to telemetry), and retry the original search once. Clients without
    elicitation get the S3 brief exactly as before. Any failure returns the
    original result unchanged."""
    from .sources import search_all

    try:
        key_skips = [e for e in (result.get("skipped") or [])
                     if isinstance(e, dict) and e.get("reason") == "key_required"
                     and e.get("source") in sources
                     and e.get("source") not in _ELICITED_SOURCES]
        if not key_skips:
            return result
        if not capture_request(_CURRENT_REQUEST.get()).get("client_supports_elicitation"):
            return result

        applied = []
        for entry in key_skips:
            name = entry["source"]
            _ELICITED_SOURCES.add(name)
            env_var, signup = _source_key_facts(name)
            try:
                r = await ctx.elicit(
                    f"The {name} source you asked for needs a free API key and "
                    f"was skipped. Paste your {env_var} value to use {name} for "
                    f"THIS session only — it is never saved to disk and never "
                    f"leaves this machine except to call {name} itself. Get one "
                    f"free at {signup}. Decline to search without {name}.",
                    _SourceApiKey,
                )
            except Exception:
                # Client advertised elicitation but the ask failed — behave as
                # a non-supporting client (the S3 brief is already in place).
                _emit_setup_flow(None, "elicit_unsupported")
                return result
            action = getattr(r, "action", None)
            if action != "accept" or getattr(r, "data", None) is None:
                _emit_setup_flow(action, "paused")
                continue
            value = (r.data.api_key or "").strip()
            if not value:
                _emit_setup_flow(action, "invalid_input")
                continue
            os.environ[env_var] = value  # session-only; process env, no disk
            applied.append(name)

        if not applied:
            return result
        retry = search_all(query, sources, limit)
        _apply_key_briefs(retry)
        still_skipped = {e.get("source") for e in (retry.get("skipped") or [])}
        for name in applied:
            _emit_setup_flow("accept",
                             "fixed" if name not in still_skipped else "still_broken")
        return retry
    except Exception:
        return result


@mcp.tool(title="Search free music",
          description="Search free/royalty-free music across multiple sources",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=True))
async def search_music(query: str, sources: list[str] | None = None,
                       limit: int = 10, intent: str = None,
                       ctx: Context = None) -> dict:
    """Search free/royalty-free music across multiple sources.

    Args:
        query: what kind of music (e.g. "medieval tavern ambient", "epic
            cinematic trailer", "lo-fi beats").
        sources: optional subset of source names (see list_sources).
            Defaults to all configured sources.
        limit: max results to return (default 10).
        intent: Short plain-English description of what the user is trying to
            learn/accomplish. E.g. "calm background music for a podcast
            intro", "CC0 sound effects for a game jam".

    Returns:
        hits: unified list of tracks with title, artist, license,
            license_url, audio_url, page_url, attribution and source.
        skipped: sources that were unavailable (missing API key or error).

    If hits is empty or skipped is non-empty, read the 'interpreting-errors'
    skill (skills_list, then skill_read) before retrying.
    """
    limit = max(1, min(int(limit), 50))
    result = await _search_with_progress(ctx, query, sources, limit)
    _apply_key_briefs(result)
    if sources and ctx is not None:
        result = await _elicit_missing_source_keys(ctx, result, query, sources, limit)
    return result


@mcp.tool(title="List music sources",
          description="List every music source the server can search, with "
                      "license families and key requirements",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=False))
async def list_sources() -> list[dict]:
    """List every music source the server can search, with license families,
    whether an API key is needed, and whether it is currently configured."""
    from .sources import list_sources as _list

    return _list()


# --- skills: updatable knowledge, fetched at runtime from this repo ---

# Pinned to this repo by design — never configurable.
_SKILLS_RAW_URL = "https://raw.githubusercontent.com/surendranb/music-mcp/main/skills/{name}.md"
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"  # repo checkout fallback
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# Known skills (fallback when no local skills/ dir is present, e.g. wheel installs).
_BUNDLED_SKILLS = {
    "interpreting-errors": "How to read this server's error shapes (skipped "
                           "sources, key_required, unknown-source errors, "
                           "empty hits) and recover.",
}


def _local_skills():
    """{name: description} from the repo skills/ dir when present."""
    skills = {}
    try:
        if _SKILLS_DIR.is_dir():
            for md_file in sorted(_SKILLS_DIR.glob("*.md")):
                desc = ""
                try:
                    for line in md_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip()
                            break
                except Exception:
                    pass
                skills[md_file.stem] = desc
    except Exception:
        pass
    return skills


def _fetch_skill_content(key):
    """(content | None, fetch_ok) for a validated skill name: GitHub raw fetch
    first (updatable knowledge, reaches the fleet), local repo copy fallback.
    Shared by the skill_read tool and the skill:// resources (S5) — one source
    of truth, identical bytes on both surfaces."""
    content = None
    fetch_ok = False
    try:
        req = urllib.request.Request(
            _SKILLS_RAW_URL.format(name=key),
            headers={"User-Agent": f"music-mcp/{MCP_SERVER_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8")
        fetch_ok = True
    except Exception:
        pass

    if content is None:
        # offline / fetch failure: bundled local copy when packaging allows
        try:
            local = _SKILLS_DIR / f"{key}.md"
            if local.is_file():
                content = local.read_text(encoding="utf-8")
        except Exception:
            pass

    return content, fetch_ok


@mcp.tool(title="List skills",
          description="List available skills (guidance playbooks) for using "
                      "this server well — read one with skill_read",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=False))
async def skills_list() -> dict:
    """List available skills: short guidance documents for a model using this
    server (e.g. how to interpret error shapes and recover). Call this when a
    search fails, returns empty hits, or skips sources, then fetch the full
    skill with skill_read(name)."""
    merged = dict(_BUNDLED_SKILLS)
    for skill_name, desc in _local_skills().items():
        if desc or skill_name not in merged:
            merged[skill_name] = desc or merged.get(skill_name, "")
    return {"skills": [{"name": n, "description": d} for n, d in sorted(merged.items())]}


@mcp.tool(title="Read a skill",
          description="Fetch the full content of one skill by name (from "
                      "skills_list) — guidance on error recovery and effective use",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=True))
async def skill_read(name: str) -> dict:
    """Fetch the full markdown content of one skill by name.

    Args:
        name: skill name from skills_list (e.g. "interpreting-errors").

    Returns:
        name + content on success, or an error message with next steps.

    Read 'interpreting-errors' whenever search_music returns empty hits,
    skipped sources, or an error you do not understand.
    """
    key = (name or "").strip().lower().removesuffix(".md")
    if not _SKILL_NAME_RE.match(key):
        return {"error": f"Invalid skill name {name!r}. "
                         "Call skills_list to see available skills."}

    content, fetch_ok = _fetch_skill_content(key)

    send_telemetry("skill_read", {"skill_name": key, "fetch_ok": fetch_ok})

    if content is None:
        return {"error": f"Skill '{key}' is unavailable right now (fetch failed "
                         "and no local copy). Call skills_list for available "
                         "skills, or proceed without it."}
    return {"name": key, "content": content}


# --- S5: skills mirrored as MCP resources (skill://<name>) ---
# Same content as skill_read (GitHub fetch, local fallback), discoverable via
# resources/list without a tool call. Pull-only: free until a client reads one.


def _register_skill_resources():
    try:
        skills = dict(_BUNDLED_SKILLS)
        for skill_name, desc in _local_skills().items():
            if desc or skill_name not in skills:
                skills[skill_name] = desc or skills.get(skill_name, "")
        for skill_name in sorted(skills):
            if not _SKILL_NAME_RE.match(skill_name):
                continue
            uri = f"skill://{skill_name}"
            desc = skills[skill_name] or f"music-mcp skill: {skill_name}"

            def _make_reader(key, res_uri):
                def _read_skill() -> str:
                    content, fetch_ok = _fetch_skill_content(key)
                    try:
                        send_telemetry("resource_read", {
                            "resource_uri": res_uri,
                            "skill_name": key,
                            "fetch_ok": fetch_ok,
                            **capture_request(_CURRENT_REQUEST.get()),
                        })
                    except Exception:
                        pass
                    if content is None:
                        raise ValueError(
                            f"Skill '{key}' is unavailable right now (fetch "
                            "failed and no local copy). Use the skills_list "
                            "tool for available skills.")
                    return content

                _read_skill.__name__ = f"skill_resource_{key.replace('-', '_')}"
                return _read_skill

            mcp.resource(uri, name=skill_name, title=f"Skill: {skill_name}",
                         description=desc, mime_type="text/markdown")(
                _make_reader(skill_name, uri))
    except Exception:
        pass


_register_skill_resources()


# --- S6: workflow prompts (pull-only, user-invokable in client UIs) ---
# Each prompt teaches the model this server's real quirks: intent capture,
# license/attribution relay, keyless-vs-keyed sources, and the
# interpreting-errors skill on failure.


def _emit_prompt_used(prompt_name, has_args):
    try:
        send_telemetry("prompt_used", {
            "prompt_name": prompt_name,
            "has_args": bool(has_args),
            **capture_request(_CURRENT_REQUEST.get()),
        })
    except Exception:
        pass


@mcp.prompt(name="music-for-a-video", title="Music for a video",
            description="Find license-safe background music for a video, "
                        "with the exact attribution the user must credit.")
def music_for_a_video(mood: str, duration: str = "") -> str:
    """Find background music for a video by mood and target duration."""
    _emit_prompt_used("music-for-a-video", bool(mood or duration))
    length = duration or "any length"
    return (
        f"Find background music for a video. Mood: {mood}. Target length: {length}.\n\n"
        "1. Call list_sources first — keyless sources (internet_archive, "
        "wikimedia_commons, incompetech) always work; jamendo/freesound need keys.\n"
        f"2. Call search_music with a descriptive genre/mood query built from "
        f"'{mood}' (e.g. 'epic cinematic trailer', 'calm acoustic ambient') — "
        "never song or artist names. Pass intent='background music for a video, "
        f"mood: {mood}, length: {length}'.\n"
        f"3. Prefer tracks whose duration (seconds) is close to {length}.\n"
        "4. Present the top 3 to the user, each with: title, artist, duration, "
        "page_url and audio_url links, the license, and the attribution string "
        "VERBATIM — the user must paste that credit into the video description.\n"
        "5. CC BY / CC BY-SA make that credit mandatory; CC0 does not, but "
        "crediting is still good practice.\n"
        "6. If hits are empty or sources were skipped, read the "
        "'interpreting-errors' skill (skills_list → skill_read) before retrying."
    )


@mcp.prompt(name="sfx-for-a-game", title="SFX for a game",
            description="Find sound effects and loops for a game, preferring "
                        "CC0, with credits-screen attribution when needed.")
def sfx_for_a_game(sounds: str = "") -> str:
    """Find game sound effects; `sounds` describes what is needed."""
    _emit_prompt_used("sfx-for-a-game", bool(sounds))
    what = sounds or "the sounds the game needs"
    return (
        f"Find sound effects for a game: {what}.\n\n"
        "1. freesound is the main SFX source and needs a free API key. Call "
        "list_sources; if freesound is not configured, give the user the exact "
        "steps from the skipped hint (env var MUSIC_MCP_FREESOUND_TOKEN, free "
        "at freesound.org/apiv2/apply) and continue with the other sources "
        "meanwhile.\n"
        "2. Search one sound at a time with short concrete queries ('sword "
        "clash', '8-bit jump', 'rain loop'). Pass intent='sound effects for a "
        f"game: {what}'.\n"
        "3. Prefer CC0 picks (no credit needed in the shipped game). Any CC BY "
        "pick requires an entry in the game's credits screen — relay its "
        "attribution string VERBATIM.\n"
        "4. Give the user page_url + audio_url links plus license and "
        "attribution for every pick.\n"
        "5. Empty hits or skipped sources → read the 'interpreting-errors' "
        "skill (skills_list → skill_read) before retrying."
    )


@mcp.prompt(name="podcast-bed", title="Podcast bed",
            description="Find a calm, loopable intro/outro/background bed for "
                        "a podcast, with show-notes attribution.")
def podcast_bed(tone: str = "") -> str:
    """Find a podcast background bed; `tone` sets the feel."""
    _emit_prompt_used("podcast-bed", bool(tone))
    feel = tone or "calm"
    return (
        f"Find an intro/outro/background bed for a podcast. Tone: {feel}.\n\n"
        "1. Good beds are calm, loopable, non-distracting instrumentals. "
        f"Search with genre queries like '{feel} instrumental loop' or 'lo-fi "
        f"ambient bed' — never song or artist names. Pass intent='podcast "
        f"background bed, tone: {feel}'.\n"
        "2. incompetech (no key needed, CC BY) is strong for beds; jamendo "
        "adds many CC tracks when configured — check list_sources.\n"
        "3. Present 3 candidates with page_url + audio_url links, duration, "
        "and license.\n"
        "4. For CC BY tracks the attribution line must go into the show notes "
        "VERBATIM — give it to the user exactly as returned.\n"
        "5. Empty hits or skipped sources → read the 'interpreting-errors' "
        "skill (skills_list → skill_read) before retrying."
    )


def main():
    send_telemetry("mcp_started", {})
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

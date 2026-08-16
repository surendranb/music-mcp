# AGENTS.md — Codebase Operational Guide for AI Agents

> **Context, architecture, file map, and execution commands for AI coding agents (Claude Code, Cursor, Codex, Gemini, Antigravity, OpenCode, Aider) working on `music-mcp`.**

---

## 1. Codebase Overview

- **Language & Runtime**: Python 3.10+ (`mcp` FastMCP, `httpx`, `pydantic`).
- **Package Name**: `free-music-library-mcp` (PyPI) / `free-music-library-mcp` (NPM thin wrapper).
- **Core Function**: Searchable catalog of 100,000+ royalty-free and Creative Commons music tracks across multiple open archives (Internet Archive, Wikimedia, Incompetech, Jamendo, Freesound) with automated legal attribution formatting.

---

## 2. Directory & File Map

```
music-mcp/
├── music_mcp/
│   ├── server.py              # FastMCP server, tools (search_tracks, get_attribution, search_by_mood_genre)
│   ├── telemetry.py           # Edge Schema v2 telemetry client
│   ├── catalogs/
│   │   └── incompetech.json   # Embedded offline catalog of Kevin MacLeod CC-BY tracks
│   └── sources/
│       ├── base.py            # Abstract BaseSource interface for audio providers
│       ├── internet_archive.py# Internet Archive Netlabels & Live Music API connector
│       ├── jamendo.py         # Jamendo open audio API connector
│       ├── freesound.py       # Freesound Creative Commons audio API connector
│       ├── wikimedia.py       # Wikimedia Commons audio API connector
│       └── curated.py         # Curated verified CC-BY / Public Domain collection
├── npm/                       # Thin Node.js CLI launcher
│   ├── bin/index.js           # Subprocess wrapper spawning uvx free-music-library-mcp
│   └── package.json           # NPM package metadata
├── tests/                     # Unit and integration test suite
│   ├── test_server.py         # FastMCP tools tests
│   └── test_sources.py        # Music provider API tests
├── pyproject.toml             # Python packaging metadata (free-music-library-mcp)
├── smithery.yaml              # Smithery.ai marketplace configuration
├── server.json                # Official MCP registry specification
├── gemini-extension.json      # Google Gemini / Antigravity extension manifest
├── .claude-plugin/            # Claude Code plugin manifests (plugin.json, marketplace.json)
└── .well-known/ai-plugin.json # OpenAI / ChatGPT Actions manifest
```

---

## 3. Development & Testing Commands

```bash
# Install dependencies in editable mode
uv sync || pip install -e ".[dev]"

# Run the MCP server locally in stdio mode
uv run python -m music_mcp.server

# Run the test suite
uv run pytest tests/ -v

# Run linting
uv run ruff check .
```

---

## 4. Tool Implementation Invariants & Gotchas

1. **Attribution Integrity (`get_attribution`)**:
   - CC-BY attribution strings must strictly format Title, Artist, Source, License Name, and License URL according to Creative Commons legal requirements.
2. **Audio Stream URL Verification**:
   - Ensure direct audio links returned in `get_track_details` are playable MP3/OGG streams with proper Content-Type headers.
3. **Offline Fallback**:
   - If external APIs (Internet Archive, Jamendo) experience timeouts, `music_mcp/catalogs/incompetech.json` serves as the deterministic offline catalog.

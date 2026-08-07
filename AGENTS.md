# music-mcp

Why: Searchable catalog of free/royalty-free music for AI agents — Internet Archive, Wikimedia Commons, Jamendo, Freesound, Incompetech. Every result carries license + attribution.

Links: gh: surendranb/music-mcp · worker: https://music-mcp-install-telemetry.reachsuren.workers.dev · PyPI: free-music-library-mcp · npm: free-music-library-mcp

Status: active · Linear: Music MCP (SUR-253..258)

<!-- SUR-218: project notes auto-generated 2026-08-06 -->

## Architecture

- Python MCP server (mcp 2.x `MCPServer`), tools: `search_music`, `list_sources`
- Sources: 4 live adapters (`music_mcp/sources/`) + baked catalogs (`music_mcp/catalogs/*.json`, built by `scripts/build_catalogs.py`)
- Telemetry: anonymous PostHog via separate Cloudflare Worker (`workers/install-telemetry/`) — same project as deprecated remote server, opt-out via `MUSIC_MCP_TELEMETRY=false`
- Distribution: PyPI (OIDC) + npm bridge (`npm/`), CI/CD-only via GitHub Releases
- Deprecated legacy: old remote-http Hono worker (D1/Vectorize/SSE) — archived in git history, removed from tree

## Conventions

- House pattern: `google-analytics-mcp` (telemetry.py, gateway worker, npm bridge, server.json schema 2025-12-11)
- Key config: `MUSIC_MCP_JAMENDO_CLIENT_ID`, `MUSIC_MCP_FREESOUND_TOKEN` (both optional)
- Attribution is mandatory in every tool result — never drop `license`/`attribution` fields

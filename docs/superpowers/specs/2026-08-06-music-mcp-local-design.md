# Music MCP — Local stdio server design

SUR-253..258 · 2026-08-06 · Pivot from Cloudflare Worker remote MCP (deprecated: `src/index.ts`, D1, Vectorize, SSE) to a local stdio MCP server.

## Outcome

"Music MCP looks like: an MCP server that gives any agent a searchable catalog of the most extensive list of free/open-source/royalty-free music sources, measured by: N live API sources + N baked catalogs, every result carrying license + attribution, installed via `uvx music-mcp`."

## Architecture

Python/FastMCP (house pattern: GA4/GSC/Wikipedia). Monorepo mirroring `google-analytics-mcp`:

```
music-mcp/
├── pyproject.toml            # name "music-mcp", script "music-mcp-server"
├── server.json               # io.github.surendranb/music-mcp
├── music_mcp/
│   ├── server.py             # FastMCP app, tools
│   ├── telemetry.py          # anonymous PostHog via gateway (GA4 pattern)
│   ├── sources/
│   │   ├── base.py           # Source ABC: search() -> list[TrackHit]
│   │   ├── internet_archive.py   # advancedsearch.php + metadata, no key
│   │   ├── jamendo.py            # v3.0 API, free client_id (MUSIC_MCP_JAMENDO_CLIENT_ID)
│   │   ├── freesound.py          # apiv2, free token (MUSIC_MCP_FREESOUND_TOKEN)
│   │   ├── wikimedia.py          # Commons MediaWiki API, no key
│   │   └── curated.py            # baked catalogs: incompetech, audionautix,
│   │                             # scottbuckley, freepd, joshwoodward (JSON in package)
│   └── catalogs/*.json       # baked indexes (title/artist/url/license only)
├── npm/                      # npx bridge -> uvx (bin: music-mcp, music-mcp-server)
├── gemini-extension/
├── Formula/
├── workers/install-telemetry/   # /e ingest, /go/<surface>, /install.sh, / landing
├── .github/workflows/        # release.yml (PyPI+npm via CI/CD), package-checks.yml
└── tests/
```

## Tools

- `search_music(query, sources?, limit?)` — aggregate across sources, unified hit: `id, title, artist, album, duration, license, license_url, audio_url, source, attribution`. attribution = ready-to-paste credit string per source rules.
- `list_sources()` — every source with license family, key requirement, live-vs-baked.

## Source matrix

| Source | Type | Access | License families |
|---|---|---|---|
| Internet Archive | live API, no key | netlabels + freemusicarchive collections | CC0 / CC BY / PD |
| Jamendo | live API, free client_id | v3.0 tracks search | CC BY / CC BY-SA / CC BY-NC-SA / CC BY-ND |
| Freesound | live API, free token | apiv2 search (music category) | CC0 / CC BY / CC BY-NC |
| Wikimedia Commons | live API, no key | MediaWiki API file search | CC / PD |
| Incompetech (Kevin MacLeod) | baked catalog | ~2,000 tracks | CC BY 4.0 |
| Audionautix | baked catalog | ~1,400 tracks | CC BY 4.0 |
| Scott Buckley | baked catalog | ~400 tracks | CC BY 4.0 |
| FreePD | baked catalog | ~500 tracks | CC0 |
| Josh Woodward | baked catalog | ~1,000 songs | CC BY 4.0 |

Baked = finite, license-clean, no API; ship index (metadata + direct audio URL) inside the package. Live = queried at runtime; adapters skip gracefully when their key is missing. No embedded audio anywhere — results are pointers + attribution.

## Telemetry (Phase 2, SUR-256)

Port of GA4 `telemetry.py` + gateway worker:

- `~/.music_mcp/installation_id` UUID; `server_first_install` on first run
- events: `mcp_started`, `server_first_install`, `tool_executed`, `tools_listed`, `package_download`
- props: `mcp_server_name: "music-mcp"`, version, `agent_name`/`actor_type`, `run_context`, `discovery_channel`, `session_id`, `install_id`
- opt-out precedence: `MUSIC_MCP_TELEMETRY=false` > `DISABLE_TELEMETRY` > `DO_NOT_TRACK` > `NO_TELEMETRY`
- zero PII: no queries, no paths, no shell commands, no audio
- gateway: **separate** Cloudflare Worker (new worker, own `workers/install-telemetry/wrangler.toml`), **same PostHog project/key** (`phc_Aik6H3pf5P9dPBrWLjd6N3wzsVAD6tJnmmEhFwW8Pzsi` from existing vars). Deployed to workers.dev by default; custom domain `music-mcp.builditwithai.xyz` added via `wrangler domains add` (zone already on account) or manual DNS step. `/e` strips IP, stamps coarse geo (CF country/city), tags unknown events, truncates >900KB, honors DNT, forwards to PostHog. Deprecated `src/index.ts` worker (music.builditwithai.xyz) is untouched until archived.

## Distribution (Phase 3, SUR-254)

- PyPI `music-mcp`, console script `music-mcp-server`, deps `mcp>=2.0.0,<3`
- npm `music-mcp`, bin spawns `uvx --from music-mcp music-mcp-server` (GA4 bridge verbatim pattern)
- `server.json` schema 2025-12-11, name `io.github.surendranb/music-mcp`
- GitHub Release → OIDC trusted publishing to PyPI + npm publish (CI/CD only)
- `gemini-extension/` manifest + `Formula/music-mcp.rb` (formula deferred)

## Config

| Env | Purpose | Required |
|---|---|---|
| MUSIC_MCP_JAMENDO_CLIENT_ID | Jamendo free key | no |
| MUSIC_MCP_FREESOUND_TOKEN | Freesound free token | no |
| MUSIC_MCP_TELEMETRY=false | opt-out | no |

Missing keys → that source skipped at runtime, listed in `list_sources` output as "key required".

## Verification

- `pytest` — unit tests for adapters (mocked HTTP), baked catalog integrity (every row has url+license), attribution rendering
- live smoke: `uvx music-mcp` runs, `search_music` returns real hits from IA (no key) + baked catalogs
- `mcp dev` / Claude Desktop manual config check
- telemetry: run with `MUSIC_MCP_TELEMETRY` unset → gateway receives `mcp_started` (verified via worker logs)

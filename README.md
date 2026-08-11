# Music MCP 🎵

[![PyPI version](https://img.shields.io/pypi/v/free-music-library-mcp)](https://pypi.org/project/free-music-library-mcp/)
[![PyPI downloads](https://img.shields.io/pypi/dm/free-music-library-mcp)](https://pypi.org/project/free-music-library-mcp/)
[![npm version](https://img.shields.io/npm/v/free-music-library-mcp)](https://www.npmjs.com/package/free-music-library-mcp)
[![npm downloads](https://img.shields.io/npm/dm/free-music-library-mcp)](https://www.npmjs.com/package/free-music-library-mcp)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Model Context Protocol server that gives AI agents a **searchable catalog of the most extensive list of free, open-source, royalty-free music sources**. Search once, get licensed tracks with ready-to-paste attribution from multiple catalogs — no embedded audio, no API keys required for the default sources.

## Sources

| Source | Access | License families |
|---|---|---|
| [Internet Archive](https://archive.org) — netlabels + Free Music Archive collections | free, no key | CC0 / CC BY / Public Domain |
| [Wikimedia Commons](https://commons.wikimedia.org) | free, no key | CC BY / CC BY-SA / CC0 / PD |
| [Incompetech](https://incompetech.com) — full Kevin MacLeod catalog, 1,400+ tracks | baked in, no key | CC BY 4.0 |
| [Jamendo](https://developer.jamendo.com) | free client ID | CC BY / CC BY-SA / CC BY-NC-SA / CC BY-ND |
| [Freesound](https://freesound.org/apiv2/apply) | free token | CC0 / CC BY / CC BY-NC |

Every result carries `license`, `license_url`, `audio_url` and a ready-to-paste `attribution` string — the credit you must include, verbatim.

## Quickstart

```bash
# 1-line installer: installs uv + music-mcp, then wires it into the
# agents you already have (Claude Code, Claude Desktop, Cursor, Gemini CLI)
curl -fsSL "https://music-mcp-install-telemetry.reachsuren.workers.dev/?src=readme" | bash

# or any of:
uvx free-music-library-mcp
npx free-music-library-mcp
pip install free-music-library-mcp
```

### Claude Code

```bash
claude mcp add --transport stdio music-mcp -- uvx --from free-music-library-mcp music-mcp-server
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "music-mcp": {
      "command": "uvx",
      "args": ["--from", "music-mcp", "music-mcp-server"]
    }
  }
}
```

### Cursor

MCP settings → Add: `uvx --from free-music-library-mcp music-mcp-server` (or use the [1-click install](https://music-mcp-install-telemetry.reachsuren.workers.dev/) page).

### Gemini CLI

```bash
gemini config add music-mcp "uvx --from free-music-library-mcp music-mcp-server"
```

## Usage

| Tool | What it does |
|---|---|
| `search_music(query, sources?, limit?)` | Search across all configured sources: "medieval tavern ambient", "epic cinematic trailer", "lo-fi beats" |
| `list_sources()` | Show every source, its license families, and whether a key is needed |

Example agent conversation: *"Find a royalty-free ambient track for a podcast intro and give me the attribution."*

## Optional: enable Jamendo & Freesound

These two sources cover hundreds of thousands of additional CC tracks. Both keys are free:

```bash
export MUSIC_MCP_JAMENDO_CLIENT_ID="your-free-client-id"   # developer.jamendo.com
export MUSIC_MCP_FREESOUND_TOKEN="your-free-token"          # freesound.org/apiv2/apply
```

Sources without keys are skipped automatically and reported in `skipped` in the search result.

## Telemetry & Privacy

Music MCP collects **anonymous usage telemetry** (like GA4 MCP and other sibling servers): a random installation UUID, agent name, OS, and event counts (`mcp_started`, `tool_executed`, ...). It goes through a Cloudflare Worker gateway that strips IPs and honors Do-Not-Track. **No PII, no search queries, no local paths, no audio content** — ever.

Opt out any time:

```bash
export MUSIC_MCP_TELEMETRY=false
# or
export DO_NOT_TRACK=1
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
pytest
python -m music_mcp
```

Baked catalogs are generated from verified public listings:

```bash
python scripts/build_catalogs.py   # refreshes music_mcp/catalogs/*.json
```

## License

Apache-2.0. The music itself is licensed by each source — always include the attribution string the server returns.

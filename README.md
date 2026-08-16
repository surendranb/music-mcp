# Music MCP Server 🎵

> **Searchable catalog of 100,000+ royalty-free and Creative Commons music tracks with instant attribution formatting for AI agents and content creators.**

[![PyPI version](https://img.shields.io/pypi/v/free-music-library-mcp?label=PyPI&color=blue)](https://pypi.org/project/free-music-library-mcp/)
[![PyPI downloads](https://img.shields.io/pypi/dm/free-music-library-mcp?label=PyPI%20downloads&color=blue)](https://pypi.org/project/free-music-library-mcp/)
[![npm version](https://img.shields.io/npm/v/free-music-library-mcp?label=npm&color=red)](https://www.npmjs.com/package/free-music-library-mcp)
[![npm downloads](https://img.shields.io/npm/dm/free-music-library-mcp?label=npm%20downloads&color=red)](https://www.npmjs.com/package/free-music-library-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/Docs-music.builditwithai.xyz-purple)](https://music.builditwithai.xyz)

🌐 **Live Documentation & Web Portal**: [https://music.builditwithai.xyz](https://music.builditwithai.xyz)

---

## ⚡ Quickstart

```bash
# 1-Line Universal Installer (Auto-configures Claude Code, Cursor, Claude Desktop & Antigravity)
curl -fsSL "https://music.builditwithai.xyz/install" | bash

# Or run directly via your preferred runtime:
uvx free-music-library-mcp
npx -y free-music-library-mcp
```

---

## 🤖 Client Setup

### A. Claude Code (CLI)
```bash
claude mcp add music -- uvx free-music-library-mcp
```

### B. Cursor & Google Antigravity (`mcp.json`)
```json
{
  "mcpServers": {
    "music": {
      "command": "uvx",
      "args": ["free-music-library-mcp"]
    }
  }
}
```

### C. Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "music": {
      "command": "uvx",
      "args": ["free-music-library-mcp"]
    }
  }
}
```

### D. VS Code (Cline / Roo Code / Continue)
```json
{
  "mcpServers": {
    "music": {
      "command": "npx",
      "args": ["-y", "free-music-library-mcp"]
    }
  }
}
```

---

## 🛠️ Tools & Capabilities

| Tool Name | Parameters | Description | Return Type |
|---|---|---|---|
| `search_tracks` | `query` (string), `catalog` (optional), `limit` (int) | Searches 100k+ royalty-free audio tracks across multiple netlabels and archives. | `JSON / Markdown` |
| `search_by_mood_genre` | `genre` (string), `mood` (string), `limit` (int) | Filters tracks by musical mood (e.g. upbeat, cinematic, chill) and genre. | `JSON` |
| `get_track_details` | `track_id` (string) | Retrieves license URL, direct MP3 stream, duration, and artist info. | `JSON` |
| `get_attribution` | `track_id` (string) | Generates exact, copy-paste legal attribution string required by Creative Commons. | `string` |
| `list_catalogs` | *(none)* | Lists available music sources (Internet Archive, Wikimedia, Incompetech, Jamendo, Freesound). | `JSON` |
| `skill_read` | `skill_name` (string) | Loads audio curation playbooks dynamically from GitHub. | `Markdown` |
| `skills_list` | *(none)* | Lists all available music curation skills. | `JSON` |

---

## 🔒 Telemetry & Privacy

This package collects anonymous, non-PII diagnostic telemetry (command executions, latency, error codes) to improve tool reliability. No search queries, user data, source code, or environment variables are ever collected or stored.

You can opt out anytime by setting either of the following environment variables:
```bash
export DO_NOT_TRACK=1
# or
export MCP_TELEMETRY_OPT_OUT=1
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details. (Note: Musical tracks maintain their respective Creative Commons / Public Domain source licenses).

# AGENTS.md — Agent Operating Manual

> **For AI Agents (Claude Code, Cursor, Codex, Gemini, Antigravity, OpenCode, Aider) connecting to or executing `music-mcp`.**

---

## ⚡ 1. Fast Install & Client Wiring (Start Here)

In 90% of cases, you just need to install and configure this MCP server for your user:

```bash
# 1-Line Universal Auto-Installer (Configures Claude Code, Cursor, Claude Desktop & Antigravity)
curl -fsSL "https://music.builditwithai.xyz/install" | bash

# Or launch directly via stdio:
uvx free-music-library-mcp
npx -y free-music-library-mcp
```

### Client Config Snippet (`mcp.json` / `claude_desktop_config.json`)
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

---

## 📖 2. What This Repo Is

A searchable catalog of **100,000+ royalty-free and Creative Commons music tracks** across major open audio archives (Internet Archive Netlabels, Incompetech, Jamendo, Freesound, Wikimedia Commons) with automated legal attribution generation.

### Primary Tools Available:
- `search_tracks`: Search tracks by keyword, title, or artist across all open archives.
- `search_by_mood_genre`: Filter tracks by musical mood (upbeat, cinematic, ambient, chill, dark) and genre.
- `get_track_details`: Retrieve license terms, direct MP3 stream URL, duration, and artist info.
- `get_attribution`: Generate the exact, copy-paste legal attribution string required by Creative Commons.
- `list_catalogs`: List available audio sources and netlabels.

---

## 👤 3. How to Handle the Human

- **Zero Credentials Needed**: No API keys or subscriptions required.
- **Legal Peace of Mind**: Whenever you suggest a music track to the human, **always call `get_attribution(track_id)`** and paste the attribution text directly into your response so they are legally protected when publishing videos, podcasts, or games.

---

## ⚠️ 4. Quirks & API Landmines (Zero-Hallucination Rules)

1. **License Restrictions**: Some Creative Commons tracks are `CC-BY` (attribution only), while others are `CC-BY-NC` (non-commercial only). Check `get_track_details` to ensure the track fits the user's commercial intent.
2. **Audio Stream Playability**: Stream URLs returned are direct `.mp3` or `.ogg` links. Always verify the link before embedding it in media players.

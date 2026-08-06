---
name: music-mcp
description: Find free, royalty-free music for any project — search_music aggregates Internet Archive, Wikimedia Commons, Jamendo, Freesound, and the Incompetech catalog; every result carries license + attribution.
---

# Music MCP

Music MCP helps users find music they can legally use. Use it whenever the
user needs background music, a jingle, a podcast intro, game audio, or any
track for a project.

## Workflow

1. Call `search_music` with a mood/genre description (e.g. "medieval tavern
   ambient", "epic cinematic trailer", "lo-fi beats chill").
2. If no results satisfy, call `list_sources` to see which sources are
   available (Jamendo and Freesound need free API keys), then retry or
   broaden the query.
3. ALWAYS present the `attribution` string with any track you recommend —
   it is the credit the user must include, verbatim. Show `license` and
   `license_url` too.

## Rules

- Never present a track without its license and attribution.
- Never claim a track is "free to use commercially" unless the license says
  so (CC BY / CC0 / CC BY-SA permit commercial use; CC BY-NC does not).
- Prefer tracks with direct `audio_url` (downloadable) over page-only links.

# Ideal User Research — music-mcp

Date: 2026-08-06 · Status: draft, pre-release · Linear: SUR-258 (launch prep)

## Summary

music-mcp is a searchable catalog of free/royalty-free music for AI agents —
one aggregated search over Internet Archive, Wikimedia Commons, Jamendo,
Freesound, and Incompetech, where every result carries its license and
attribution. This doc maps who needs that, what hurts them, and how the
server answers each pain.

## Ideal users

| Persona | What they do | Why they need licensed music |
|---|---|---|
| **AI-assisted content creators** | Short-form video (Reels/Shorts/TikTok), YouTube, podcasts | Every AI video/podcast pipeline hits the same wall: finding music that is free AND legally safe to use AND attributable |
| **Indie game devs / game jams** | Prototypes, jam builds, itch.io releases | Jam deadlines have zero time for license archaeology |
| **AI-native builders** | Agents that produce video/audio assets (video makers, podcast generators) | Their toolchains hallucinate tracks or hard-code 3 generic "royalty-free" MP3s |

Secondary: web devs and product builders who ship AI features that need
ambient/background audio and want it license-safe.

## Challenges (verified pains)

1. **LLMs hallucinate music.** Ask a model for "epic orchestral track" and it
   invents plausible-sounding titles and URLs that 404 or don't exist. No
   model has a reliable index of real, downloadable, licensed tracks.
2. **License risk is invisible until it isn't.** CC-BY vs CC-BY-NC vs CC0
   confusion, attribution requirements missed, copyright strikes and
   demonetization are the failure mode. Creators know they "should" care but
   the friction of checking per-track rights kills the habit.
3. **The good sources are fragmented.** Archive.org, Wikimedia, Jamendo,
   Freesound, Kevin MacLeod's catalog each have different APIs, different
   auth, different result shapes, different license vocabularies. Manual
   hunting across five sites is the status quo.
4. **Results aren't agent-usable.** Search results designed for humans are
   HTML pages; agents need structured data (title/artist/license/audio URL/
   attribution) they can act on without scraping.

## How music-mcp answers each

| Pain | Answer |
|---|---|
| Hallucinated tracks | Real search over 5 live catalogs; every hit has a real `audio_url` + `page_url` — verifiable, not invented |
| License risk | `license`, `license_url`, and `attribution` are mandatory fields on every result; license family stated per source; no track ever returned without them |
| Fragmented sources | One `search_music` tool, one result schema, one `list_sources` tool to inspect what's available and whether keys are needed |
| Agent-unusable results | Native MCP tool output: structured JSON an agent can feed straight into a downloader/editor/attribution renderer |

## Market context

- MCP server directories are crowded with media/asset servers (500+ "media"
  category on getagentictools.com; short-video makers, voice tools, etc.).
- No dedicated royalty-free-music-search MCP server found in the directories
  checked — the niche is open.
- Distribution channels to target at launch: MCP directories (Glama,
  PulseMCP, mcp.so), Anthropic registry, Claude-focused marketplaces
  (claudemarketplaces.com has significant traffic), and the "music for my
  AI video" build-in-public angle on X/LinkedIn.

## Positioning

One line: **"The music source of truth for AI agents — real tracks, real
licenses, real attribution."**

Differentiators: (1) license + attribution are enforced, never optional;
(2) multiple key-free sources work out of the box; (3) agent-first output.

## Decisions this informs (before first release)

- Dogfood the server in real harnesses (Claude Code/Desktop/Cursor/Gemini)
  and confirm telemetry flows — already in progress (e2e suite green).
- Make install a single fire-and-forget command (next step, after release
  basics).
- Point distribution content at the creator personas above, not generic
  "MCP server" copy.

---
title: Interpreting music-mcp errors
description: How to read this server's error shapes (skipped sources, key_required, unknown-source errors, empty hits) and recover.
---

# Interpreting music-mcp errors

This server rarely hard-fails. Most "errors" arrive inside a successful
`search_music` result. Read the shapes below before retrying anything.

## 1. `skipped` entries in a search_music result

`search_music` returns `{"hits": [...], "skipped": [...]}`. Each `skipped`
entry names a source that could not be searched this time:

- `{"source": "...", "reason": "key_required", "hint": "..."}` — the source
  needs an API key that is not configured. NOT retryable by you. The `hint`
  names the exact env var the user must set:
  - `jamendo` → `MUSIC_MCP_JAMENDO_CLIENT_ID` (free at developer.jamendo.com)
  - `freesound` → `MUSIC_MCP_FREESOUND_TOKEN` (free at freesound.org/apiv2/apply)
  Tell the user once, then search without that source. The keyless sources
  (`internet_archive`, `wikimedia_commons`, `incompetech`) always work.
- `{"source": "...", "reason": "error", "detail": "..."}` — that source's
  upstream API failed (network, timeout, 5xx). Transient. Retry once without
  that source, or just use the hits you already have.

`skipped` being non-empty does NOT mean the search failed — `hits` can still
be full. Only mention skipped sources to the user if hits are thin.

## 2. Tool call fails with "unknown source(s): ..."

You passed a `sources` value this server does not know. The error lists the
valid names. Use exactly: `internet_archive`, `wikimedia_commons`, `jamendo`,
`freesound`, `incompetech` — or call `list_sources` and copy the `name`
fields. Do not guess variants like "archive" or "wikimedia".

## 3. Empty `hits` with nothing skipped

The query matched nothing. Recover by broadening, not repeating:
- Use genre/mood words ("epic cinematic", "lo-fi beats", "medieval ambient")
  rather than song or artist names.
- Drop the `sources` filter so all configured sources are searched.
- Raise `limit` (max 50).

## 4. skill_read errors

- "Invalid skill name" — use a name exactly as returned by `skills_list`.
- "unavailable right now" — the fetch failed and no local copy exists.
  Proceed without the skill; do not retry in a loop.

## 5. What never to do

- Never invent `license` or `attribution` values. Every hit carries both;
  relay them verbatim.
- Never retry an identical failing call more than once — change the query,
  the sources, or stop and tell the user what is blocked.

# SPDX-License-Identifier: Apache-2.0

"""Freesound API v2: CC loops and sounds, free token."""

import os

import requests

from .base import DEFAULT_HEADERS, Source, TrackHit, UnconfiguredError

API_URL = "https://freesound.org/apiv2/search/text/"


class FreesoundSource(Source):
    name = "freesound"
    display_name = "Freesound"
    description = ("CC-licensed music loops and sounds (filtered to mp3), "
                   "preview URLs included, full downloads need the free API token")
    license_family = "CC0 / CC BY / CC BY-NC"
    requires_key = True
    key_hint = "MUSIC_MCP_FREESOUND_TOKEN (free at freesound.org/apiv2/apply)"

    def configured(self) -> bool:
        return bool(os.getenv("MUSIC_MCP_FREESOUND_TOKEN"))

    def search(self, query: str, limit: int) -> list[TrackHit]:
        token = os.getenv("MUSIC_MCP_FREESOUND_TOKEN")
        if not token:
            raise UnconfiguredError(self.key_hint)
        r = requests.get(API_URL, params={
            "query": query,
            "token": token,
            "filter": "type:mp3",
            "fields": "id,name,username,license,previews,url,duration",
            "page_size": str(max(limit, 1)),
        }, timeout=10, headers=DEFAULT_HEADERS)
        r.raise_for_status()
        results = r.json().get("results", [])

        hits = []
        for s in results:
            lic = s.get("license") or "See sound page"
            title = s.get("name") or "Untitled"
            artist = s.get("username") or "Unknown artist"
            previews = s.get("previews") or {}
            hits.append(TrackHit(
                source=self.name,
                title=title,
                artist=artist,
                duration=s.get("duration"),
                license=lic,
                license_url=f"https://freesound.org/docs/api/attribution.html",
                audio_url=previews.get("preview-hq-mp3", ""),
                page_url=s.get("url", ""),
                attribution=f"{title} — {artist} (Freesound, {lic})",
                extra={"freesound_id": s.get("id")},
            ))
        return hits

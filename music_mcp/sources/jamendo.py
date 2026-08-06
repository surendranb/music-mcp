# SPDX-License-Identifier: Apache-2.0

"""Jamendo: v3.0 API, free client_id, hundreds of thousands of CC tracks."""

import os
import re

import requests

from .base import DEFAULT_HEADERS, Source, TrackHit, UnconfiguredError

API_URL = "https://api.jamendo.com/v3.0/tracks/"


def _license_name(ccurl: str) -> str:
    if not ccurl:
        return "CC"
    m = re.search(r"licenses/([\w-]+)/([\d.]+)", ccurl)
    if m:
        spdx = {"by": "CC BY", "by-sa": "CC BY-SA", "by-nc-sa": "CC BY-NC-SA", "by-nd": "CC BY-ND"}.get(
            m.group(1), f"CC {m.group(1)}")
        return f"{spdx} {m.group(2)}"
    return "CC"


class JamendoSource(Source):
    name = "jamendo"
    display_name = "Jamendo"
    description = ("hundreds of thousands of Creative Commons tracks with streaming "
                   "URLs and commercial-use filtering (CC BY / CC BY-SA)")
    license_family = "CC BY / CC BY-SA / CC BY-NC-SA / CC BY-ND"
    requires_key = True
    key_hint = "MUSIC_MCP_JAMENDO_CLIENT_ID (free at developer.jamendo.com)"

    def configured(self) -> bool:
        return bool(os.getenv("MUSIC_MCP_JAMENDO_CLIENT_ID"))

    def search(self, query: str, limit: int) -> list[TrackHit]:
        client_id = os.getenv("MUSIC_MCP_JAMENDO_CLIENT_ID")
        if not client_id:
            raise UnconfiguredError(self.key_hint)
        r = requests.get(API_URL, params={
            "client_id": client_id,
            "search": query,
            "limit": str(max(limit, 1)),
            "include": "musicinfo",
            "format": "json",
        }, timeout=10, headers=DEFAULT_HEADERS)
        r.raise_for_status()
        results = r.json().get("results", [])

        hits = []
        for t in results:
            lic = _license_name(t.get("license_ccurl", ""))
            title = t.get("name") or "Untitled"
            artist = t.get("artist_name") or "Unknown artist"
            hits.append(TrackHit(
                source=self.name,
                title=title,
                artist=artist,
                album=t.get("album_name") or None,
                duration=t.get("duration"),
                license=lic,
                license_url=t.get("license_ccurl", "") or "https://www.jamendo.com/legal/licenses",
                audio_url=t.get("audio", ""),
                page_url=t.get("shareurl", "") or f"https://www.jamendo.com/track/{t.get('id')}",
                attribution=f"{title} — {artist} ({lic}), via Jamendo",
                extra={"jamendo_id": t.get("id"), "image": t.get("image", "")},
            ))
        return hits

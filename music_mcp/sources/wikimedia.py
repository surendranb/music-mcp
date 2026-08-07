# SPDX-License-Identifier: Apache-2.0

"""Wikimedia Commons: audio files via the MediaWiki API, key-free."""

import re

import requests

from .base import DEFAULT_HEADERS, Source, TrackHit

API_URL = "https://commons.wikimedia.org/w/api.php"


def _strip_html(value: str) -> str:
    s = re.sub(r"<[^>]+>", "", value or "")
    return s.replace("&nbsp;", " ").strip()


def _clean_file_url(url: str) -> str:
    return url.split("?")[0] if "?" in url else url


class WikimediaSource(Source):
    name = "wikimedia_commons"
    display_name = "Wikimedia Commons"
    description = ("CC-licensed and public-domain audio files on Wikimedia Commons "
                   "(classical, ambient, field recordings, loops)")
    license_family = "CC BY / CC BY-SA / CC0 / Public Domain"
    requires_key = False

    def search(self, query: str, limit: int) -> list[TrackHit]:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:audio {query}",
            "gsrnamespace": "6",
            "gsrlimit": str(max(limit, 1)),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "format": "json",
        }
        r = requests.get(API_URL, params=params, timeout=10, headers=DEFAULT_HEADERS)
        r.raise_for_status()
        pages = (r.json().get("query", {}).get("pages", {}) or {})

        hits = []
        for page in pages.values():
            ii = page.get("imageinfo", [{}])[0] if page.get("imageinfo") else {}
            meta = ii.get("extmetadata", {})
            lic = _strip_html(meta.get("LicenseShortName", {}).get("value", ""))
            lic_url = _strip_html(meta.get("LicenseUrl", {}).get("value", ""))
            artist = _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown artist"
            duration = meta.get("Duration", {}).get("value")
            try:
                duration_sec = sum(
                    int(p) * 60 ** i for i, p in enumerate(reversed(duration.split(":")))) if duration else None
            except (ValueError, AttributeError):
                duration_sec = None
            title = page.get("title", "").replace("File:", "")
            hits.append(TrackHit(
                source=self.name,
                title=title,
                artist=artist,
                duration=duration_sec,
                license=lic or "See file page",
                license_url=lic_url or f"https://commons.wikimedia.org/wiki/{page.get('title', '')}",
                audio_url=_clean_file_url(ii.get("url", "")),
                page_url=f"https://commons.wikimedia.org/wiki/{page.get('title', '')}",
                attribution=f"{title} — {artist} (Wikimedia Commons, {lic or 'see file page'})",
            ))
        return hits

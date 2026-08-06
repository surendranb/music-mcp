# SPDX-License-Identifier: Apache-2.0

"""Baked curated catalogs: finite, license-clean sources without a public API.
The indexes ship inside the package (music_mcp/catalogs/*.json) and are built
by scripts/build_catalogs.py — metadata + direct audio URL only, no audio."""

import json
import re
from pathlib import Path

from .base import Source, TrackHit

CATALOGS_DIR = Path(__file__).parent.parent / "catalogs"

_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


class CuratedSource(Source):
    """One baked catalog. catalog_file is the JSON filename inside catalogs/."""

    catalog_file: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    license_family: str = ""
    requires_key: bool = False

    def __init__(self):
        if not self.catalog_file:
            raise ValueError("CuratedSource needs catalog_file")
        with open(CATALOGS_DIR / self.catalog_file, encoding="utf-8") as f:
            self._data = json.load(f)
        self._tracks = self._data["tracks"]
        self._license = self._data.get("license", "")
        self._license_url = self._data.get("license_url", "")
        self._attribution_note = self._data.get("attribution_note", "")

    def search(self, query: str, limit: int) -> list[TrackHit]:
        q_tokens = _tokenize(query)

        def score(track: dict) -> int:
            strong = " ".join(str(track.get(k, "")) for k in
                              ("title", "artist", "feel", "genre"))
            weak = " ".join(str(track.get(k, "")) for k in
                            ("instruments", "description"))
            s = 2 * len(_tokenize(strong) & q_tokens) + len(_tokenize(weak) & q_tokens)
            if s == 0 and not q_tokens:
                s = 1  # empty query: return catalog order
            return s

        if q_tokens:
            scored = sorted(self._tracks, key=score, reverse=True)
            scored = [t for t in scored if score(t) > 0][:limit]
        else:
            scored = self._tracks[:limit]

        hits = []
        for t in scored:
            title = t.get("title", "Untitled")
            artist = t.get("artist", self._data.get("artist", "Unknown artist"))
            hits.append(TrackHit(
                source=self.name,
                title=title,
                artist=artist,
                duration=t.get("duration"),
                license=self._license,
                license_url=self._license_url,
                audio_url=t.get("audio_url", ""),
                page_url=t.get("page_url", ""),
                attribution=f"{title} — {artist} ({self._license}{self._attribution_note})",
                extra={k: t[k] for k in ("isrc", "genre", "feel", "bpm", "uploaded")
                       if k in t},
            ))
        return hits


class IncompetechSource(CuratedSource):
    catalog_file = "incompetech.json"
    name = "incompetech"
    display_name = "Incompetech (Kevin MacLeod)"
    description = ("the full Kevin MacLeod royalty-free catalog: 2,000+ tracks "
                   "from medieval taverns to cinematic trailer music")
    license_family = "CC BY 4.0 (attribution required)"

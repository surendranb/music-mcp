#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

"""Build baked catalogs (music_mcp/catalogs/*.json) from verified public
listings. Re-run to refresh: python scripts/build_catalogs.py

Only sources with a machine-readable, license-clean listing are included.
Sites behind bot protection or JS-only apps are skipped, not fabricated:
  - audionautix (403 bot protection)  - not scraped
  - scottbuckley (JS player app)      - not scraped
  - freepd (JS app, no listing route) - not scraped
  - joshwoodward (403 bot protection) - not scraped
"""

import json
import re
import sys
import urllib.parse
from pathlib import Path

import requests

OUT_DIR = Path(__file__).parent.parent / "music_mcp" / "catalogs"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

INCOMPETECH = {
    "source": "incompetech",
    "artist": "Kevin MacLeod",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "attribution_note": ", via incompetech.com",
    "page_base": "https://incompetech.com/music/royalty-free/",
    "audio_base": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/",
    "listing": "https://incompetech.com/music/royalty-free/pieces.json",
}


def _seconds(length: str) -> float | None:
    m = re.match(r"(\d+):(\d+):(\d+)", length or "")
    if m:
        h, mm, s = map(int, m.groups())
        seconds = float(h * 3600 + mm * 60 + s)
        return seconds if seconds > 0 else None
    return None


def build_incompetech() -> dict:
    r = requests.get(INCOMPETECH["listing"], timeout=20, headers={"User-Agent": UA})
    r.raise_for_status()
    pieces = r.json()
    tracks = []
    for p in pieces:
        filename = urllib.parse.quote(p.get("filename", ""))
        audio_url = INCOMPETECH["audio_base"] + filename if p.get("filename") else ""
        track = {
            "title": p.get("title", ""),
            "duration": _seconds(p.get("length", "")),
            "isrc": p.get("isrc"),
            "genre": p.get("genre"),
            "feel": p.get("feel"),
            "bpm": p.get("bpm"),
            "instruments": p.get("instruments"),
            "description": p.get("description"),
            "uploaded": p.get("uploaded"),
            "audio_url": audio_url,
            "page_url": INCOMPETECH["page_base"],
        }
        tracks.append(track)
    tracks.sort(key=lambda t: t["title"].lower())
    return {
        "source": INCOMPETECH["source"],
        "artist": INCOMPETECH["artist"],
        "license": INCOMPETECH["license"],
        "license_url": INCOMPETECH["license_url"],
        "attribution_note": INCOMPETECH["attribution_note"],
        "track_count": len(tracks),
        "tracks": tracks,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = build_incompetech()
    (OUT_DIR / "incompetech.json").write_text(
        json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"incompetech: {len(catalog['tracks'])} tracks -> music_mcp/catalogs/incompetech.json")


if __name__ == "__main__":
    sys.exit(main())

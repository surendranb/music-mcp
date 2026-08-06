# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from music_mcp.sources.curated import IncompetechSource

CATALOGS = Path(__file__).parent.parent / "music_mcp" / "catalogs"


def _tracks():
    data = json.loads((CATALOGS / "incompetech.json").read_text(encoding="utf-8"))
    return data, data["tracks"]


def test_catalog_structure():
    data, tracks = _tracks()
    assert data["license"] == "CC BY 4.0"
    assert data["license_url"].startswith("https://creativecommons.org/")
    assert len(tracks) > 1000
    for t in tracks[:500]:
        assert t["title"]
        assert t["audio_url"].startswith("https://incompetech.com/music/royalty-free/mp3-royaltyfree/")
        assert t["audio_url"].endswith(".mp3")
        assert t["duration"] is None or t["duration"] > 0


def test_catalog_urls_unique():
    _, tracks = _tracks()
    urls = [t["audio_url"] for t in tracks]
    assert len(urls) == len(set(urls))


def test_catalog_search_relevant():
    src = IncompetechSource()
    hits = src.search("medieval tavern lute", 3)
    assert hits, "no hits for known track"
    assert hits[0].attribution.startswith("The Britons")
    assert hits[0].license == "CC BY 4.0"
    assert hits[0].license_url.startswith("https://creativecommons.org/")
    assert hits[0].duration == 307.0


def test_empty_query_returns_catalog_order():
    src = IncompetechSource()
    hits = src.search("", 2)
    assert len(hits) == 2

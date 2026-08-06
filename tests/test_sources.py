# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from music_mcp.sources.internet_archive import InternetArchiveSource, _license_name
from music_mcp.sources.wikimedia import WikimediaSource

IA_RESPONSE = {
    "response": {"docs": [
        {"identifier": "abc123", "title": "Cool Beats", "creator": "DJ Netlabel",
         "licenseurl": "https://creativecommons.org/licenses/by/3.0/"},
        {"identifier": "def456", "title": "No License Track"},
    ]}
}

IA_META = {"files": [{"name": "Cool Beats.mp3", "format": "VBR MP3"}]}
IA_META_EMPTY = {"files": [{"name": "cover.jpg", "format": "JPEG"}]}


def test_ia_search_maps_hits():
    with mock.patch("music_mcp.sources.internet_archive.requests.get") as get:
        get.return_value.json.side_effect = [
            IA_RESPONSE,          # advancedsearch
            IA_META,              # metadata abc123
            IA_META_EMPTY,        # metadata def456 (no audio file)
        ]
        hits = InternetArchiveSource().search("beats", 2)
    assert len(hits) == 2
    first, second = hits
    assert first.source == "internet_archive"
    assert first.audio_url == "https://archive.org/download/abc123/Cool Beats.mp3"
    assert first.license == "CC BY 3.0"
    assert "Internet Archive" in first.attribution
    assert second.audio_url == ""


def test_license_name_mapping():
    assert _license_name("https://creativecommons.org/licenses/by-sa/4.0/") == "CC BY-SA 4.0"
    assert _license_name("https://creativecommons.org/publicdomain/zero/1.0/") == "CC0 / Public Domain"
    assert _license_name("") == "See item page"


def test_wikimedia_search_maps_hits():
    pages = {
        "1": {"title": "File:Example - Ambient.mp3",
              "imageinfo": [{
                  "url": "https://upload.wikimedia.org/x/Example.mp3?utm_source=x",
                  "extmetadata": {
                      "Artist": {"value": '<a href="#">Jane Doe</a>'},
                      "LicenseShortName": {"value": "CC BY-SA 4.0"},
                      "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                      "Duration": {"value": "2:30"},
                  },
              }]}
    }
    with mock.patch("music_mcp.sources.wikimedia.requests.get") as get:
        get.return_value.json.return_value = {"query": {"pages": pages}}
        hits = WikimediaSource().search("ambient", 1)
    assert len(hits) == 1
    h = hits[0]
    assert h.title == "Example - Ambient.mp3"
    assert h.artist == "Jane Doe"
    assert h.duration == 150.0
    assert h.audio_url == "https://upload.wikimedia.org/x/Example.mp3"
    assert h.license == "CC BY-SA 4.0"

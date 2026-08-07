# SPDX-License-Identifier: Apache-2.0

"""Internet Archive: netlabels + Free Music Archive collections, key-free."""

import re
from concurrent.futures import ThreadPoolExecutor

import requests

from .base import DEFAULT_HEADERS, Source, TrackHit

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
COLLECTIONS = ["netlabels", "freemusicarchive"]
AUDIO_EXTS = (".mp3", ".flac", ".ogg", ".m4a", ".wav", ".opus")


def _license_name(licenseurl: str) -> str:
    if not licenseurl:
        return "See item page"
    m = re.search(r"licenses/([\w-]+)/([\d.]+)", licenseurl)
    if m:
        spdx = {"by": "CC BY", "by-sa": "CC BY-SA", "by-nc": "CC BY-NC",
                "by-nc-sa": "CC BY-NC-SA", "by-nd": "CC BY-ND", "by-nc-nd": "CC BY-NC-ND"}.get(
            m.group(1), f"CC {m.group(1)}")
        return f"{spdx} {m.group(2)}"
    if "publicdomain" in licenseurl or "zero" in licenseurl:
        return "CC0 / Public Domain"
    return "See item page"


def _fetch_audio_url(identifier: str, timeout: float = 6.0) -> str | None:
    try:
        meta = requests.get(METADATA_URL.format(identifier=identifier),
                            timeout=timeout, headers=DEFAULT_HEADERS).json()
        for f in meta.get("files", []):
            name = (f.get("name") or "").lower()
            fmt = (f.get("format") or "").lower()
            if name.endswith(AUDIO_EXTS) or fmt in ("mp3", "flac", "ogg vorbis", "m4a", "wav", "opus"):
                return f"https://archive.org/download/{identifier}/{f['name']}"
    except Exception:
        pass
    return None


class InternetArchiveSource(Source):
    name = "internet_archive"
    display_name = "Internet Archive"
    description = ("netlabels + Free Music Archive collections: netlabel releases and "
                   "CC-licensed music from the dead FMA site, preserved on archive.org")
    license_family = "CC0 / CC BY / Public Domain"
    requires_key = False

    def search(self, query: str, limit: int) -> list[TrackHit]:
        collection_q = " OR ".join(f"collection:{c}" for c in COLLECTIONS)
        params = {
            "q": f"({query}) AND ({collection_q}) AND mediatype:audio",
            "fl[]": ["identifier", "title", "creator", "licenseurl"],
            "rows": str(max(limit, 1)),
            "output": "json",
        }
        r = requests.get(SEARCH_URL, params=params, timeout=10, headers=DEFAULT_HEADERS)
        r.raise_for_status()
        docs = r.json()["response"]["docs"]

        audio_urls = {}
        if docs:
            with ThreadPoolExecutor(max_workers=min(len(docs), 8)) as pool:
                for ident, url in zip(docs, pool.map(lambda d: _fetch_audio_url(d["identifier"]), docs)):
                    if url:
                        audio_urls[ident["identifier"]] = url

        hits = []
        for doc in docs:
            ident = doc["identifier"]
            title = doc.get("title") or ident
            artist = doc.get("creator") or "Unknown artist"
            license_url = doc.get("licenseurl", "")
            lic = _license_name(license_url)
            hits.append(TrackHit(
                source=self.name,
                title=title,
                artist=artist,
                license=lic,
                license_url=license_url or "https://archive.org/details/" + ident,
                audio_url=audio_urls.get(ident, ""),
                page_url="https://archive.org/details/" + ident,
                attribution=f"{title} — {artist} (Internet Archive, {lic})",
            ))
        return hits

# SPDX-License-Identifier: Apache-2.0

"""Source registry: everything search_music can query."""

from .base import Source, TrackHit, UnconfiguredError
from .curated import IncompetechSource
from .freesound import FreesoundSource
from .internet_archive import InternetArchiveSource
from .jamendo import JamendoSource
from .wikimedia import WikimediaSource

SOURCES: dict[str, Source] = {
    s.name: s for s in (
        InternetArchiveSource(),
        WikimediaSource(),
        JamendoSource(),
        FreesoundSource(),
        IncompetechSource(),
    )
}


def get_source(name: str) -> Source | None:
    return SOURCES.get(name)


def list_sources() -> list[dict]:
    return [s.status() for s in SOURCES.values()]


def search_all(query: str, sources: list[str] | None = None, limit: int = 10) -> dict:
    """Aggregate search. Returns {hits: [...], skipped: [...]} — skipped lists
    sources that failed or are unconfigured, so callers can explain."""
    names = sources or list(SOURCES.keys())
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)}. Known: {', '.join(SOURCES)}")

    hits: list[TrackHit] = []
    skipped: list[dict] = []
    per_source_limit = max(limit, 1)
    for name in names:
        src = SOURCES[name]
        if not src.configured():
            skipped.append({"source": name, "reason": "key_required",
                            "hint": src.key_hint})
            continue
        try:
            hits.extend(src.search(query, per_source_limit))
        except UnconfiguredError as e:
            skipped.append({"source": name, "reason": "key_required", "hint": str(e)})
        except Exception as e:
            skipped.append({"source": name, "reason": "error", "detail": str(e)[:200]})

    hits.sort(key=lambda h: (h.source, h.title.lower()))
    return {"hits": [h.to_dict() for h in hits[:limit]], "skipped": skipped}

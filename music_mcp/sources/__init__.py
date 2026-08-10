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


def search_all(query: str, sources: list[str] | None = None, limit: int = 10,
               on_source=None) -> dict:
    """Aggregate search. Returns {hits: [...], skipped: [...]} — skipped lists
    sources that failed or are unconfigured, so callers can explain.

    on_source, when given, is called after each source finishes:
    on_source(name, hit_count, skipped_reason, index, total). Callback
    exceptions are swallowed — progress can never affect a search.
    """
    names = sources or list(SOURCES.keys())
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        # Two-audience error brief (version tag: server.BRIEF_UNKNOWN_SOURCE):
        # what happened, retrying won't help, numbered recovery for the model.
        raise ValueError(
            f"unknown source(s): {', '.join(unknown)}. Retrying with the same "
            f"name won't help — this server only knows: {', '.join(SOURCES)}. "
            "Do this: 1) Call list_sources to see every valid source name. "
            "2) Retry search_music with names copied exactly from that list, "
            "or omit 'sources' entirely to search all of them."
        )

    hits: list[TrackHit] = []
    skipped: list[dict] = []
    per_source_limit = max(limit, 1)
    total = len(names)
    for index, name in enumerate(names, 1):
        src = SOURCES[name]
        added = 0
        reason = None
        if not src.configured():
            reason = "key_required"
            skipped.append({"source": name, "reason": reason,
                            "hint": src.key_hint})
        else:
            try:
                found = src.search(query, per_source_limit)
                hits.extend(found)
                added = len(found)
            except UnconfiguredError as e:
                reason = "key_required"
                skipped.append({"source": name, "reason": reason, "hint": str(e)})
            except Exception as e:
                reason = "error"
                skipped.append({"source": name, "reason": reason, "detail": str(e)[:200]})
        if on_source is not None:
            try:
                on_source(name, added, reason, index, total)
            except Exception:
                pass

    hits.sort(key=lambda h: (h.source, h.title.lower()))
    return {"hits": [h.to_dict() for h in hits[:limit]], "skipped": skipped}

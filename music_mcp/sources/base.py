# SPDX-License-Identifier: Apache-2.0

"""Source abstraction: every music source implements search() and returns
TrackHit rows with license + attribution."""

from dataclasses import dataclass, asdict, field

# Descriptive UA: Wikimedia Commons and some peers 403 default library UAs.
DEFAULT_HEADERS = {
    "User-Agent": "music-mcp/0.1.0 (MCP server; contact: reachsuren@gmail.com)"
}


class UnconfiguredError(Exception):
    """Raised by a live source whose API key is not set."""


@dataclass
class TrackHit:
    source: str
    title: str
    artist: str
    album: str | None = None
    duration: float | None = None  # seconds
    license: str = ""
    license_url: str = ""
    audio_url: str = ""
    page_url: str = ""
    attribution: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class Source:
    """Base class. Subclasses set the class attributes and implement search()."""

    name: str = ""
    display_name: str = ""
    description: str = ""
    license_family: str = ""  # human summary: "CC0 / CC BY / PD" etc
    requires_key: bool = False
    key_hint: str = ""  # env var name when requires_key

    def configured(self) -> bool:
        return True

    def search(self, query: str, limit: int) -> list[TrackHit]:
        raise NotImplementedError

    def status(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "license_family": self.license_family,
            "requires_key": self.requires_key,
            "key_hint": self.key_hint if (self.requires_key and not self.configured()) else None,
            "configured": self.configured(),
        }

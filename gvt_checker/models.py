"""Data model for a single classified ad."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Listing:
    """A single search result from gebrauchte-veranstaltungstechnik.de."""

    ad_id: str
    title: str
    url: str
    description: str
    price: float | None
    price_text: str
    posted: date | None
    location: str
    image_url: str | None
    commercial: bool

    @property
    def haystack(self) -> str:
        """Lowercased text used for include/exclude/regex matching."""
        return f"{self.title}\n{self.description}".lower()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["posted"] = self.posted.isoformat() if self.posted else None
        return data

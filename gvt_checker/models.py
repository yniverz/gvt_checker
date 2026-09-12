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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Listing | None":
        """Rebuild a listing from :meth:`to_dict`; ``None`` if the data is broken."""
        raw_date = data.get("posted")
        try:
            posted = date.fromisoformat(raw_date) if isinstance(raw_date, str) else None
            raw_price = data.get("price")
            return cls(
                ad_id=str(data["ad_id"]),
                title=str(data.get("title", "")),
                url=str(data.get("url", "")),
                description=str(data.get("description", "")),
                price=float(raw_price) if raw_price is not None else None,
                price_text=str(data.get("price_text", "")),
                posted=posted,
                location=str(data.get("location", "")),
                image_url=data.get("image_url") or None,
                commercial=bool(data.get("commercial", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None

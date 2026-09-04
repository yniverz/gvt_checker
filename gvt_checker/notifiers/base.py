"""Notifier interface plus shared message formatting."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Listing


class NotifyError(RuntimeError):
    """Raised when a notification could not be delivered."""


def format_listing(listing: Listing) -> str:
    """Human readable one-block summary of a listing (plain text)."""
    price = listing.price_text or "kein Preis"
    seller = "gewerblich" if listing.commercial else "privat"
    posted = listing.posted.strftime("%d.%m.%Y") if listing.posted else "?"
    parts = [
        listing.title,
        f"{price} | {posted} | {listing.location or '?'} | {seller}",
        listing.url,
    ]
    return "\n".join(parts)


class Notifier(ABC):
    """Callback target invoked with the listings that are new since last run."""

    name: str = "notifier"

    @abstractmethod
    def send(self, watch_name: str, listings: list[Listing]) -> None:
        """Deliver ``listings`` found by the watch called ``watch_name``."""

    def close(self) -> None:  # pragma: no cover - optional hook
        """Release resources held by the notifier."""

"""Notifier interface plus shared message formatting."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Listing


class NotifyError(RuntimeError):
    """Raised when a notification could not be delivered."""


#: A listing showed up for the first time.
EVENT_NEW = "new"
#: A previously seen listing is gone from the search results (sold / offline).
EVENT_GONE = "gone"

_EVENT_LABELS = {EVENT_NEW: "neue Treffer", EVENT_GONE: "verschwundene Anzeigen"}


def event_label(event: str) -> str:
    """German wording for an event kind, used in message headers/subjects."""
    return _EVENT_LABELS.get(event, event)


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
    """Callback target invoked with the listings that changed since last run."""

    name: str = "notifier"

    @abstractmethod
    def send(self, watch_name: str, listings: list[Listing], event: str = EVENT_NEW) -> None:
        """Deliver ``listings`` found by the watch called ``watch_name``.

        ``event`` is :data:`EVENT_NEW` for freshly discovered ads and
        :data:`EVENT_GONE` for ads that vanished from the search results.
        """

    def close(self) -> None:  # pragma: no cover - optional hook
        """Release resources held by the notifier."""

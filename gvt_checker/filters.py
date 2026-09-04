"""Mask/filter logic applied to scraped listings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Listing


@dataclass
class ListingFilter:
    """Decides whether a listing is interesting.

    ``include_words``/``exclude_words`` are matched case-insensitively against
    title + description. ``include_mode`` controls whether *all* or *any* of the
    include words must be present.
    """

    include_words: list[str] = field(default_factory=list)
    exclude_words: list[str] = field(default_factory=list)
    include_mode: str = "any"
    regex: str | None = None
    exclude_regex: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    allow_missing_price: bool = True

    _regex: re.Pattern[str] | None = field(init=False, default=None, repr=False)
    _exclude_regex: re.Pattern[str] | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.include_mode not in ("any", "all"):
            raise ValueError("include_mode must be 'any' or 'all'")
        self.include_words = [w.lower() for w in self.include_words if w]
        self.exclude_words = [w.lower() for w in self.exclude_words if w]
        flags = re.IGNORECASE | re.DOTALL
        self._regex = re.compile(self.regex, flags) if self.regex else None
        self._exclude_regex = (
            re.compile(self.exclude_regex, flags) if self.exclude_regex else None
        )

    def matches(self, listing: Listing) -> bool:
        text = listing.haystack

        if self.include_words:
            hits = (word in text for word in self.include_words)
            if not (all(hits) if self.include_mode == "all" else any(hits)):
                return False

        if any(word in text for word in self.exclude_words):
            return False

        if self._regex and not self._regex.search(text):
            return False

        if self._exclude_regex and self._exclude_regex.search(text):
            return False

        if self.min_price is not None or self.max_price is not None:
            if listing.price is None:
                return self.allow_missing_price
            if self.min_price is not None and listing.price < self.min_price:
                return False
            if self.max_price is not None and listing.price > self.max_price:
                return False

        return True

    def apply(self, listings: list[Listing]) -> list[Listing]:
        return [listing for listing in listings if self.matches(listing)]

"""Log the new listings to stdout / the logger."""

from __future__ import annotations

import logging

from ..models import Listing
from .base import EVENT_NEW, Notifier, format_listing

log = logging.getLogger(__name__)


class ConsoleNotifier(Notifier):
    name = "console"

    def __init__(self, use_logger: bool = True) -> None:
        self.use_logger = use_logger

    def send(self, watch_name: str, listings: list[Listing], event: str = EVENT_NEW) -> None:
        kind = "new" if event == EVENT_NEW else "disappeared"
        header = f"[{watch_name}] {len(listings)} {kind} listing(s)"
        body = "\n\n".join(format_listing(listing) for listing in listings)
        if self.use_logger:
            log.info("%s\n%s", header, body)
        else:
            print(f"{header}\n{body}", flush=True)

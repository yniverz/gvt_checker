"""Generic JSON webhook notifier (Discord, Slack, n8n, Home Assistant, ...)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from ..models import Listing
from .base import EVENT_NEW, Notifier, NotifyError, format_listing

log = logging.getLogger(__name__)


class WebhookNotifier(Notifier):
    """POSTs ``{"watch": ..., "event": ..., "count": ..., "text": ..., "listings": [...]}``."""

    name = "webhook"

    def __init__(
        self,
        url: str,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
        verify_tls: bool = True,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("webhook url must be an http(s) URL")
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.session = requests.Session()

    def _payload(self, watch_name: str, listings: list[Listing], event: str) -> dict[str, Any]:
        return {
            "watch": watch_name,
            "event": event,
            "count": len(listings),
            "text": "\n\n".join(format_listing(listing) for listing in listings),
            "listings": [listing.to_dict() for listing in listings],
        }

    def send(self, watch_name: str, listings: list[Listing], event: str = EVENT_NEW) -> None:
        try:
            response = self.session.request(
                self.method,
                self.url,
                json=self._payload(watch_name, listings, event),
                headers=self.headers,
                timeout=self.timeout,
                verify=self.verify_tls,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NotifyError(f"webhook call failed: {exc}") from exc

    def close(self) -> None:
        self.session.close()

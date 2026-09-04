"""Telegram bot notifier (Bot API ``sendMessage``)."""

from __future__ import annotations

import html
import logging
import time

import requests

from ..models import Listing
from .base import Notifier, NotifyError

log = logging.getLogger(__name__)

API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4000


class TelegramNotifier(Notifier):
    """Sends one HTML formatted message per new listing.

    ``token`` and ``chat_id`` are normally injected from environment variables
    via ``${TELEGRAM_BOT_TOKEN}`` placeholders in the config file.
    """

    name = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str | int,
        timeout: float = 20.0,
        disable_preview: bool = False,
        max_per_run: int = 20,
    ) -> None:
        if not token or not str(chat_id):
            raise ValueError("telegram notifier needs both 'token' and 'chat_id'")
        self.token = str(token)
        self.chat_id = str(chat_id)
        self.timeout = timeout
        self.disable_preview = disable_preview
        self.max_per_run = max_per_run
        self.session = requests.Session()

    def _format(self, watch_name: str, listing: Listing) -> str:
        esc = html.escape
        price = esc(listing.price_text or "kein Preis")
        posted = listing.posted.strftime("%d.%m.%Y") if listing.posted else "?"
        seller = "gewerblich" if listing.commercial else "privat"
        snippet = esc(listing.description)[:400]
        text = (
            f"\U0001f50e <b>{esc(watch_name)}</b>\n"
            f"<a href=\"{esc(listing.url)}\">{esc(listing.title)}</a>\n"
            f"\U0001f4b6 <b>{price}</b> \u00b7 \U0001f4c5 {posted}\n"
            f"\U0001f4cd {esc(listing.location or '?')} \u00b7 {seller}"
        )
        if snippet:
            text += f"\n\n{snippet}"
        return text[:MAX_MESSAGE_LEN]

    def _post(self, text: str) -> None:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": self.disable_preview,
        }
        try:
            response = self.session.post(
                API_TEMPLATE.format(token=self.token), json=payload, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise NotifyError(f"telegram request failed: {exc}") from exc
        if response.status_code != 200:
            # Never echo the token; response bodies from Telegram do not contain it.
            raise NotifyError(f"telegram API returned {response.status_code}: {response.text[:300]}")

    def send(self, watch_name: str, listings: list[Listing]) -> None:
        batch = listings[: self.max_per_run]
        for index, listing in enumerate(batch):
            self._post(self._format(watch_name, listing))
            if index + 1 < len(batch):
                time.sleep(1.0)  # stay below Telegram's ~30 msg/s limit
        if len(listings) > len(batch):
            self._post(f"\u2026 und {len(listings) - len(batch)} weitere Treffer f\u00fcr {html.escape(watch_name)}.")

    def close(self) -> None:
        self.session.close()

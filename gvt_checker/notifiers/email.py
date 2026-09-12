"""SMTP e-mail notifier."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from ..models import Listing
from .base import EVENT_NEW, Notifier, NotifyError, event_label, format_listing

log = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    """Sends a single digest mail containing every changed listing."""

    name = "email"

    def __init__(
        self,
        host: str,
        to: str | list[str],
        sender: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        security: str = "starttls",
        timeout: float = 30.0,
        subject_prefix: str = "[GVT]",
    ) -> None:
        security = security.lower()
        if security not in ("starttls", "ssl", "none"):
            raise ValueError("security must be one of 'starttls', 'ssl', 'none'")
        self.host = host
        self.port = int(port)
        self.recipients = [to] if isinstance(to, str) else list(to)
        self.sender = sender
        self.username = username
        self.password = password
        self.security = security
        self.timeout = timeout
        self.subject_prefix = subject_prefix

    def _build(self, watch_name: str, listings: list[Listing], event: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = (
            f"{self.subject_prefix} {len(listings)} {event_label(event)}: {watch_name}"
        )
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        body = "\n\n".join(format_listing(listing) for listing in listings)
        if event != EVENT_NEW:
            body = (
                "Diese Anzeigen sind nicht mehr in den Suchergebnissen "
                "(verkauft oder offline genommen):\n\n" + body
            )
        message.set_content(body, charset="utf-8")
        return message

    def send(self, watch_name: str, listings: list[Listing], event: str = EVENT_NEW) -> None:
        message = self._build(watch_name, listings, event)
        context = ssl.create_default_context()
        try:
            if self.security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout, context=context
                )
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with server:
                if self.security == "starttls":
                    server.starttls(context=context)
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"sending mail failed: {exc}") from exc

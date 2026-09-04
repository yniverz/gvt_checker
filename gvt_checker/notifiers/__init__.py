"""Notification backends.

Every notifier implements :class:`Notifier` and is created from a plain dict
coming out of the YAML config via :func:`build_notifier`.
"""

from __future__ import annotations

from typing import Any

from .base import Notifier, NotifyError
from .console import ConsoleNotifier
from .email import EmailNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier

_REGISTRY: dict[str, type[Notifier]] = {
    "console": ConsoleNotifier,
    "telegram": TelegramNotifier,
    "webhook": WebhookNotifier,
    "email": EmailNotifier,
}


def build_notifier(spec: dict[str, Any]) -> Notifier:
    """Instantiate a notifier from ``{"type": "telegram", ...options}``."""
    options = dict(spec)
    kind = str(options.pop("type", "")).strip().lower()
    if kind not in _REGISTRY:
        raise ValueError(
            f"unknown notifier type {kind!r}; available: {', '.join(sorted(_REGISTRY))}"
        )
    name = options.pop("name", kind)
    notifier = _REGISTRY[kind](**options)
    notifier.name = str(name)
    return notifier


__all__ = [
    "Notifier",
    "NotifyError",
    "ConsoleNotifier",
    "EmailNotifier",
    "TelegramNotifier",
    "WebhookNotifier",
    "build_notifier",
]

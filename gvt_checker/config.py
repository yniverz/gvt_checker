"""YAML configuration loading with ``${ENV_VAR}`` expansion."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .filters import ListingFilter
from .notifiers import Notifier, build_notifier
from .scraper import VALID_ORDERS

log = logging.getLogger(__name__)

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_FALSY = {"0", "false", "no", "off", "", "none", "null"}


class ConfigError(ValueError):
    """Raised when the configuration file is invalid."""


def _as_bool(value: Any, default: bool = True) -> bool:
    """Interpret YAML booleans *and* env-expanded strings like ``"false"``."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _FALSY
    return bool(value)


def _expand(value: Any) -> Any:
    """Recursively replace ``${VAR}`` / ``${VAR:-default}`` with env values."""
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            name, default = match.group(1), match.group(2)
            env = os.environ.get(name)
            if env is None:
                if default is None:
                    raise ConfigError(f"environment variable {name} is referenced but not set")
                return default
            return env

        return _ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item) for item in value]
    return value


@dataclass
class Watch:
    """One keyword search plus its mask and notification targets."""

    name: str
    keyword: str
    listing_filter: ListingFilter
    notifier_names: list[str]
    order: str = "dDESC"
    notify_on_first_run: bool = False
    notify_on_disappear: bool = False
    enabled: bool = True


@dataclass
class AppConfig:
    watches: list[Watch]
    notifiers: dict[str, Notifier]
    interval_seconds: int = 900
    jitter_seconds: int = 60
    state_file: Path = Path("state.json")
    request_timeout: float = 30.0
    log_level: str = "INFO"
    delay_between_watches: float = 3.0
    default_notifier_names: list[str] = field(default_factory=list)
    test_on_startup: bool = False
    test_notifier_names: list[str] = field(default_factory=list)
    error_notifier_names: list[str] = field(default_factory=list)

    def close(self) -> None:
        for notifier in self.notifiers.values():
            notifier.close()


def _build_filter(raw: dict[str, Any]) -> ListingFilter:
    known = {
        "include_words",
        "exclude_words",
        "include_mode",
        "regex",
        "exclude_regex",
        "min_price",
        "max_price",
        "allow_missing_price",
    }
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown filter option(s): {', '.join(sorted(unknown))}")
    try:
        return ListingFilter(**raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid filter: {exc}") from exc


def load_config(path: str | os.PathLike[str]) -> AppConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ConfigError(f"cannot read config {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")
    raw = _expand(raw)

    notifiers: dict[str, Notifier] = {}
    defined: set[str] = set()
    raw_notifiers = raw.get("notifiers") or {}
    if not isinstance(raw_notifiers, dict):
        raise ConfigError("'notifiers' must be a mapping of name -> settings")
    for name, spec in raw_notifiers.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"notifier {name!r} must be a mapping")
        defined.add(str(name))
        if not _as_bool(spec.get("enabled")):
            log.debug("notifier %r is disabled", name)
            continue
        spec = {key: value for key, value in spec.items() if key != "enabled"}
        try:
            notifier = build_notifier({**spec, "name": name})
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"notifier {name!r}: {exc}") from exc
        notifiers[str(name)] = notifier

    defaults = raw.get("default_notifiers") or list(notifiers)
    if isinstance(defaults, str):
        defaults = [defaults]
    defaults = [str(d) for d in defaults]
    unknown_defaults = [d for d in defaults if d not in defined]
    if unknown_defaults:
        raise ConfigError(
            f"default_notifiers references undefined notifier(s): {', '.join(unknown_defaults)}"
        )
    defaults = [d for d in defaults if d in notifiers]

    raw_watches = raw.get("watches") or []
    if not isinstance(raw_watches, list) or not raw_watches:
        raise ConfigError("'watches' must be a non-empty list")

    watches: list[Watch] = []
    for index, entry in enumerate(raw_watches):
        if not isinstance(entry, dict):
            raise ConfigError(f"watch #{index + 1} must be a mapping")
        keyword = str(entry.get("keyword", "")).strip()
        if not keyword:
            raise ConfigError(f"watch #{index + 1} is missing 'keyword'")
        name = str(entry.get("name") or keyword)
        order = str(entry.get("order", "dDESC"))
        if order not in VALID_ORDERS:
            raise ConfigError(f"watch {name!r}: order must be one of {', '.join(VALID_ORDERS)}")

        targets = entry.get("notifiers", defaults)
        if isinstance(targets, str):
            targets = [targets]
        targets = [str(t) for t in targets]
        missing = [t for t in targets if t not in defined]
        if missing:
            raise ConfigError(
                f"watch {name!r} references undefined notifier(s): {', '.join(missing)}"
            )
        # Disabled notifiers are silently dropped so a single env flag can turn
        # a backend off without editing every watch.
        targets = [t for t in targets if t in notifiers]
        if not targets:
            log.warning("watch %r has no enabled notifier - matches will only be logged", name)

        raw_filter = entry.get("filter") or {}
        if not isinstance(raw_filter, dict):
            raise ConfigError(f"watch {name!r}: 'filter' must be a mapping")

        watches.append(
            Watch(
                name=name,
                keyword=keyword,
                listing_filter=_build_filter(raw_filter),
                notifier_names=targets,
                order=order,
                notify_on_first_run=_as_bool(entry.get("notify_on_first_run"), default=False),
                notify_on_disappear=_as_bool(entry.get("notify_on_disappear"), default=False),
                enabled=_as_bool(entry.get("enabled")),
            )
        )

    test_targets = raw.get("test_notifiers") or list(notifiers)
    if isinstance(test_targets, str):
        # Allow "mail,telegram" so it can come straight from a single env var.
        test_targets = [part.strip() for part in test_targets.split(",") if part.strip()]
    test_targets = [str(t) for t in test_targets]
    unknown_test = [t for t in test_targets if t not in defined]
    if unknown_test:
        raise ConfigError(
            f"test_notifiers references undefined notifier(s): {', '.join(unknown_test)}"
        )
    test_targets = [t for t in test_targets if t in notifiers]

    error_targets = raw.get("error_notifiers") or defaults
    if isinstance(error_targets, str):
        error_targets = [part.strip() for part in error_targets.split(",") if part.strip()]
    error_targets = [str(t) for t in error_targets]
    unknown_error = [t for t in error_targets if t not in defined]
    if unknown_error:
        raise ConfigError(
            f"error_notifiers references undefined notifier(s): {', '.join(unknown_error)}"
        )
    error_targets = [t for t in error_targets if t in notifiers]

    return AppConfig(
        watches=watches,
        notifiers=notifiers,
        interval_seconds=int(raw.get("interval_seconds", 900)),
        jitter_seconds=int(raw.get("jitter_seconds", 60)),
        state_file=Path(str(raw.get("state_file", "state.json"))),
        request_timeout=float(raw.get("request_timeout", 30.0)),
        log_level=str(raw.get("log_level", "INFO")).upper(),
        delay_between_watches=float(raw.get("delay_between_watches", 3.0)),
        default_notifier_names=defaults,
        test_on_startup=_as_bool(raw.get("test_on_startup"), default=False),
        test_notifier_names=test_targets,
        error_notifier_names=error_targets,
    )

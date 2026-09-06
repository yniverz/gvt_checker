"""JSON-backed store of already-seen ad ids, so we only notify once."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class SeenStore:
    """Per-watch set of ad ids that have already triggered a notification."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read state file %s (%s) - starting fresh", self.path, exc)
            return
        if isinstance(raw, dict):
            self._data = {
                str(name): entry for name, entry in raw.items() if isinstance(entry, dict)
            }

    def _watch(self, watch: str) -> dict[str, Any]:
        return self._data.setdefault(watch, {"seen": [], "last_run": None})

    def known_ids(self, watch: str) -> set[str]:
        return set(self._watch(watch).get("seen", []))

    def is_first_run(self, watch: str) -> bool:
        return self._watch(watch).get("last_run") is None

    def mark_seen(self, watch: str, ad_ids: list[str], max_entries: int = 5000) -> None:
        entry = self._watch(watch)
        seen: list[str] = list(entry.get("seen", []))
        known = set(seen)
        seen.extend(ad_id for ad_id in ad_ids if ad_id not in known)
        entry["seen"] = seen[-max_entries:]
        entry["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def save(self) -> None:
        try:
            self._write(self.path)
        except OSError as exc:
            fallback = self._fallback_path()
            if fallback is None:
                raise
            log.error(
                "cannot write state to %s (%s) - falling back to %s; "
                "point state_file/GVT_STATE_FILE at a writable directory",
                self.path,
                exc,
                fallback,
            )
            self._write(fallback)
            self.path = fallback

    def _write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write so a crash mid-save cannot corrupt the state file.
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _fallback_path(self) -> Path | None:
        """Writable location to use when the configured path is not writable."""
        candidates: list[Path] = []
        # systemd StateDirectory= first, then XDG, then tmp as a last resort.
        state_dir = os.environ.get("STATE_DIRECTORY")
        if state_dir:
            # STATE_DIRECTORY may be a colon separated list.
            candidates.append(Path(state_dir.split(":")[0]))
        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            candidates.append(Path(xdg_state, "gvt-checker"))
        candidates.append(Path(tempfile.gettempdir(), "gvt-checker"))

        for directory in candidates:
            candidate = directory / self.path.name
            if candidate == self.path:
                continue
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            if os.access(directory, os.W_OK):
                return candidate
        return None

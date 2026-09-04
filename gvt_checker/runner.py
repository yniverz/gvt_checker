"""Check loop: scrape -> filter -> diff against state -> notify."""

from __future__ import annotations

import logging
import random
import signal
import threading
import time
from datetime import date

from .config import AppConfig, Watch
from .models import Listing
from .notifiers import NotifyError
from .scraper import BASE_URL, GvtClient, ScrapeError
from .state import SeenStore

log = logging.getLogger(__name__)

TEST_WATCH_NAME = "Selbsttest"


def _test_listing() -> Listing:
    """Synthetic listing used for the startup self-test."""
    return Listing(
        ad_id="0",
        title="Testbenachrichtigung von gvt-checker",
        url=f"{BASE_URL}/",
        description=(
            "Wenn du das liest, funktioniert dieser Benachrichtigungskanal. "
            "Diese Nachricht wird beim Start gesendet, weil test_on_startup aktiv ist."
        ),
        price=0.0,
        price_text="0\u20ac",
        posted=date.today(),
        location="-",
        image_url=None,
        commercial=False,
    )


class Runner:
    def __init__(self, config: AppConfig, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run
        self.client = GvtClient(timeout=config.request_timeout)
        self.store = SeenStore(config.state_file)
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def install_signal_handlers(self) -> None:
        """Handle SIGINT/SIGTERM so `docker stop` shuts the loop down cleanly."""
        def handler(signum: int, _frame: object) -> None:
            log.info("received signal %s - shutting down", signum)
            self.request_stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, handler)

    def _notify(self, watch: Watch, listings: list[Listing]) -> bool:
        """Dispatch to every notifier of the watch. Returns True if all succeeded."""
        ok = True
        for name in watch.notifier_names:
            notifier = self.config.notifiers[name]
            try:
                notifier.send(watch.name, listings)
            except NotifyError as exc:
                ok = False
                log.error("notifier %r failed for watch %r: %s", name, watch.name, exc)
            except Exception:  # noqa: BLE001 - one bad notifier must not kill the loop
                ok = False
                log.exception("notifier %r crashed for watch %r", name, watch.name)
        return ok

    def send_startup_test(self, force: bool = False) -> bool:
        """Send one test message through the configured test notifiers.

        Enabled via ``test_on_startup`` in the config (``GVT_TEST_ON_STARTUP``)
        or the ``--test-notify`` CLI flag. Never blocks startup on failure.
        """
        if not force and not self.config.test_on_startup:
            return True

        targets = self.config.test_notifier_names
        if not targets:
            log.warning("startup test requested but no notifier is enabled")
            return False

        log.info("sending startup test notification via: %s", ", ".join(targets))
        listing = _test_listing()
        ok = True
        for name in targets:
            try:
                self.config.notifiers[name].send(TEST_WATCH_NAME, [listing])
                log.info("startup test via %r: OK", name)
            except NotifyError as exc:
                ok = False
                log.error("startup test via %r failed: %s", name, exc)
            except Exception:  # noqa: BLE001 - a broken channel must not stop the daemon
                ok = False
                log.exception("startup test via %r crashed", name)
        return ok

    def check_watch(self, watch: Watch) -> list[Listing]:
        """Run one watch once and return the newly discovered listings."""
        try:
            listings = self.client.search(watch.keyword, order=watch.order)
        except ScrapeError as exc:
            log.error("watch %r: %s", watch.name, exc)
            return []

        matched = watch.listing_filter.apply(listings)
        known = self.store.known_ids(watch.name)
        first_run = self.store.is_first_run(watch.name)
        new = [listing for listing in matched if listing.ad_id not in known]

        log.info(
            "watch %r: %d hits, %d after filter, %d new%s",
            watch.name,
            len(listings),
            len(matched),
            len(new),
            " (first run)" if first_run else "",
        )

        if not new:
            self.store.mark_seen(watch.name, [])
            return []

        if first_run and not watch.notify_on_first_run:
            log.info(
                "watch %r: seeding state with %d listing(s), not notifying", watch.name, len(new)
            )
            self.store.mark_seen(watch.name, [listing.ad_id for listing in new])
            return new

        if self.dry_run:
            log.info("dry-run: would notify about %d listing(s) for %r", len(new), watch.name)
            return new

        # Only remember ads whose notification actually went out, so a transient
        # Telegram/SMTP outage does not silently swallow a hit.
        if self._notify(watch, new):
            self.store.mark_seen(watch.name, [listing.ad_id for listing in new])
        else:
            log.warning("watch %r: keeping %d listing(s) unseen for retry", watch.name, len(new))
        return new

    def run_once(self) -> int:
        total = 0
        active = [watch for watch in self.config.watches if watch.enabled]
        for index, watch in enumerate(active):
            if self._stop.is_set():
                break
            total += len(self.check_watch(watch))
            if index + 1 < len(active) and self.config.delay_between_watches > 0:
                self._stop.wait(self.config.delay_between_watches)
        if not self.dry_run:
            self.store.save()
        return total

    def run_forever(self) -> None:
        interval = max(30, self.config.interval_seconds)
        log.info(
            "starting loop: %d watch(es), every %ds (+ up to %ds jitter)",
            len(self.config.watches),
            interval,
            self.config.jitter_seconds,
        )
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.run_once()
            except Exception:  # noqa: BLE001 - keep the daemon alive
                log.exception("unexpected error during check cycle")
            elapsed = time.monotonic() - started
            sleep_for = max(5.0, interval - elapsed)
            if self.config.jitter_seconds > 0:
                sleep_for += random.uniform(0, self.config.jitter_seconds)
            log.debug("sleeping %.0fs", sleep_for)
            self._stop.wait(sleep_for)
        log.info("loop stopped")

    def close(self) -> None:
        self.client.close()
        self.config.close()

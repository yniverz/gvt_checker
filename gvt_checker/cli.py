"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import ConfigError, load_config
from .notifiers.base import format_listing
from .runner import Runner
from .scraper import GvtClient

DEFAULT_CONFIG = os.environ.get("GVT_CONFIG", "config.yaml")
DEFAULT_ENV_FILE = os.environ.get("GVT_ENV_FILE", ".env")


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger().setLevel(getattr(logging, level, logging.INFO))
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gvt-checker",
        description="Watch gebrauchte-veranstaltungstechnik.de for new matching ads.",
    )
    parser.add_argument(
        "-c", "--config", default=DEFAULT_CONFIG, help=f"config file (default: {DEFAULT_CONFIG})"
    )
    parser.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE,
        help=f"dotenv file with secrets (default: {DEFAULT_ENV_FILE}); real environment wins",
    )
    parser.add_argument("--log-level", help="override log_level from the config")
    parser.add_argument(
        "--test-notify",
        action="store_true",
        help="send a test notification on startup (same as test_on_startup: true)",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="run the periodic check loop (default)")

    once = sub.add_parser("once", help="run a single check cycle and exit")
    once.add_argument(
        "--dry-run", action="store_true", help="do not notify and do not persist state"
    )

    sub.add_parser("test-notify", help="send a test notification and exit")

    search = sub.add_parser("search", help="ad-hoc search, prints results (ignores state)")
    search.add_argument("keyword")
    search.add_argument("--order", default="dDESC")
    search.add_argument("--limit", type=int, default=20)

    sub.add_parser("check-config", help="validate the config file and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"

    # Load .env if present. override=False so real environment variables
    # (Docker/Portainer stack env) always take precedence over the file.
    env_file = Path(args.env_file)
    env_loaded = env_file.is_file() and load_dotenv(env_file, override=False)

    if command == "search":
        _setup_logging(args.log_level or "INFO")
        client = GvtClient()
        try:
            listings = client.search(args.keyword, order=args.order)
        finally:
            client.close()
        print(f"{len(listings)} hit(s) for {args.keyword!r}\n")
        for listing in listings[: args.limit]:
            print(format_listing(listing))
            print()
        return 0

    # Configure logging before the config is parsed so warnings during loading
    # are formatted consistently; the level is refined afterwards.
    _setup_logging(args.log_level or "INFO")
    log = logging.getLogger(__name__)
    if env_loaded:
        log.info("loaded environment from %s", env_file)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log.error("config error: %s", exc)
        return 2

    _setup_logging(args.log_level or config.log_level)

    if command == "check-config":
        log.info(
            "config OK: %d watch(es), notifiers: %s",
            len(config.watches),
            ", ".join(sorted(config.notifiers)) or "none",
        )
        config.close()
        return 0

    runner = Runner(config, dry_run=getattr(args, "dry_run", False))
    try:
        if command == "test-notify":
            return 0 if runner.send_startup_test(force=True) else 1
        runner.send_startup_test(force=args.test_notify)
        if command == "once":
            runner.run_once()
        else:
            runner.install_signal_handlers()
            runner.run_forever()
    finally:
        runner.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

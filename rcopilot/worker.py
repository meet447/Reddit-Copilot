"""Autonomous worker loop for Reddit Copilot."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from rcopilot.config import AppConfig
from rcopilot.pipeline import run_once
from rcopilot.store import Store

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def run_forever(
    config: AppConfig,
    store: Store,
    stop_event: threading.Event | None = None,
    config_path: str | None = None,
) -> None:
    """Run fetch+draft+schedule loop until *stop_event* is set."""
    store.ensure_schema()
    interval = config.worker.interval_seconds

    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("Worker stopping")
            break

        try:
            counts = run_once(config, store, config_path=config_path)
            logger.info(
                "Worker cycle complete: fetched=%d drafted=%d posted=%d",
                counts["fetched"],
                counts["drafted"],
                counts["posted"],
            )
        except Exception:
            logger.exception("Worker cycle failed")

        if stop_event is not None and stop_event.is_set():
            break

        if stop_event is not None:
            if stop_event.wait(timeout=interval):
                logger.info("Worker stopping")
                break
        else:
            time.sleep(interval)

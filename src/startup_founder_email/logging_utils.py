"""Logging helpers for the command-line interface."""

from __future__ import annotations

import logging


def configure_logging() -> None:
    """Configure a readable default logger for the application."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

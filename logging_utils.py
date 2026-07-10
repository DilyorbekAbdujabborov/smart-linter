"""Project-wide logging setup.

A single ``configure_logging`` call wires up a consistent, human-readable
format. Every module obtains its logger via ``get_logger(__name__)`` so log
lines are namespaced by module -- making it easy to route/filter later
(e.g. shipping to a central log stack in production).
"""

from __future__ import annotations

import logging

from config import settings

_CONFIGURED = False

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%H:%M:%S"


def configure_logging() -> None:
    """Configure the root logger once, using the configured log level."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=_FORMAT,
        datefmt=_DATEFMT,
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger, ensuring logging is configured."""
    configure_logging()
    return logging.getLogger(name)

# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Logging helpers.

In intuitive terms, this is the future home of project-wide logging setup so
individual modules do not all invent their own logging patterns.

Who touches this:
- people configuring diagnostics or runtime verbosity

Who this touches:
- the standard logging module
"""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger."""
    return logging.getLogger(name)

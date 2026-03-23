# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Configuration loading helpers.

In intuitive terms, this module is the narrow place where YAML config files are
turned into Python dictionaries before the rest of the pipeline consumes them.

Who touches this:
- CLI and runner code
- people evolving config schema

Who this touches:
- the filesystem
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_config(config_path: str | Path) -> dict:
    """Load a YAML config file into a dictionary."""
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    data["config_path"] = str(path)
    return data

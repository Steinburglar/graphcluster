# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""LAMMPS-facing I/O helpers.

This module is the place to isolate LAMMPS-specific concerns such as dump-file
quirks, units, or future Allegro-adjacent edge sources.

Who touches this:
- people integrating LAMMPS data formats

Who this touches:
- the trajectory reader and future engine-specific adapters
"""

from __future__ import annotations

from pathlib import Path


def describe_lammps_input(path: str | Path) -> str:
    """Return a lightweight description of a LAMMPS input path."""
    return f"LAMMPS input: {Path(path)}"

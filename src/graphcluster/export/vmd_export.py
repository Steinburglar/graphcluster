# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""VMD-oriented export helpers.

In intuitive terms, this module is for visualization-oriented export formats
that other external tools can consume.

Who touches this:
- people integrating VMD or similar visualization export paths

Who this touches:
- frame bundles or visualization payloads
"""

from __future__ import annotations

from pathlib import Path


def export_vmd(output_path: str | Path, payload: object) -> Path:
    """Return the path that would be written by a future VMD exporter."""
    _ = payload
    return Path(output_path)

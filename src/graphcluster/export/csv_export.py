# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""CSV export helpers.

In intuitive terms, this module is for writing machine-readable outputs such as
per-frame or per-atom partition data.

Who touches this:
- export and reporting code

Who this touches:
- frame bundles or partition objects
"""

from __future__ import annotations

from pathlib import Path


def export_csv(output_path: str | Path, payload: object) -> Path:
    """Return the path that would be written by a future CSV exporter."""
    _ = payload
    return Path(output_path)

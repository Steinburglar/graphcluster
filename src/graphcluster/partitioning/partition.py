# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Per-frame partition objects.

In intuitive terms, this is the clustering result for one frame. The same class
can represent a raw local partition or a tracked/synchronized partition,
depending on the metadata.

Who touches this:
- partitioners
- cluster tracking
- bundling, visualization, export, and trajectory-level analysis

Who this touches:
- nothing directly; it is a project-owned result object
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Partition:
    """Store cluster labels for one frame."""

    frame_index: int
    labels: list[int]
    kind: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)

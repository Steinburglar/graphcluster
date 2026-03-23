# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Backend-independent visualization payloads.

In intuitive terms, this object is the handoff between the domain model and a
viewer backend. It should contain only the data needed to draw what the user
wants to inspect.

Who touches this:
- visualizers and viewer adapters

Who this touches:
- frame bundles
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..bundle.frame_bundle import FrameBundle


@dataclass
class VisualizationPayload:
    """Store the minimum information needed to visualize a frame bundle."""

    frame_index: int
    positions: Any | None = None
    labels: list[int] = field(default_factory=list)

    @classmethod
    def from_bundle(cls, bundle: FrameBundle) -> "VisualizationPayload":
        """Create a payload from a frame bundle."""
        return cls(
            frame_index=bundle.frame.index,
            positions=bundle.frame.positions,
            labels=list(bundle.partition.labels),
        )

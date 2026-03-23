# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Canonical sparse weighted graph container.

In intuitive terms, this is the graph version of a frame: one timestep's
connectivity and weights in the representation the partitioner expects.

Who touches this:
- graph builders
- partitioners
- bundling and visualization code when edge display is needed

Who this touches:
- nothing else directly; it should stay a plain domain object
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SparseWeightedGraph:
    """Represent one sparse weighted graph for one frame."""

    frame_index: int
    adjacency: Any | None = None
    directed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

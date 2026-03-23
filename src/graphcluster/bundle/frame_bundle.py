# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Lightweight per-frame bundle object.

In intuitive terms, this is the convenient object downstream code wants: one
place to get a frame, its graph, and its tracked partition together, without
mutating the frame itself or relying on hidden trajectory-wide views.

Who touches this:
- the top-level runner
- visualization and export code
- trajectory-level storage layers

Who this touches:
- frame, graph, and partition objects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..graph.sparse_graph import SparseWeightedGraph
from ..io.frame import Frame
from ..partitioning.partition import Partition


@dataclass
class FrameBundle:
    """Tie together the per-frame objects emitted by the main loop."""

    frame: Frame
    graph: SparseWeightedGraph
    partition: Partition
    local_partition: Partition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Algorithm selection for local graph partitioning.

In intuitive terms, this module hides the details of which clustering method is
being used so the partitioner can stay small.

Who touches this:
- people adding actual clustering algorithms

Who this touches:
- the partitioner
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..graph.sparse_graph import SparseWeightedGraph


class PartitionAlgorithm(Protocol):
    """Protocol for one-frame clustering algorithms."""

    def run(
        self,
        graph: SparseWeightedGraph,
        initial_labels: list[int] | None = None,
    ) -> list[int]:
        """Return local labels for a graph."""


@dataclass
class PlaceholderPartitionAlgorithm:
    """Very small stand-in algorithm used while the scaffold is being built."""

    def run(
        self,
        graph: SparseWeightedGraph,
        initial_labels: list[int] | None = None,
    ) -> list[int]:
        _ = initial_labels
        size = graph.metadata.get("num_nodes", 0)
        return [0 for _ in range(size)]


def build_algorithm(config: dict) -> PartitionAlgorithm:
    """Build the configured local partitioning algorithm."""
    _ = config
    return PlaceholderPartitionAlgorithm()

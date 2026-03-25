# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Local partitioning step for one frame.

In intuitive terms, this class is responsible for producing the raw clustering
result for a single graph. It may use the previous tracked partition as a warm
start, but it does not itself synchronize cluster identities across time.

Who touches this:
- people integrating clustering algorithms
- the top-level runner

Who this touches:
- sparse graph objects
- partitioning algorithms
- local partition result objects
"""

from __future__ import annotations

from dataclasses import dataclass

from ..graph.sparse_graph import SparseWeightedGraph
from .algorithms import build_algorithm
from .partition import Partition


@dataclass
class Partitioner:
    """Compute a raw local partition for one graph."""

    config: dict

    @classmethod
    def from_config(cls, config: dict) -> "Partitioner":
        """Build a partitioner from config."""
        return cls(config=config)

    def partition_local(
        self,
        graph: SparseWeightedGraph,
        previous_tracked_partition: Partition | None = None,
    ) -> Partition:
        """Produce the local, unsynchronized partition for one frame."""
        partition_config = self.config.get("partition", {})
        algorithm = build_algorithm(partition_config)
        warm_start = partition_config.get("warm_start", False)
        initial_labels = None
        if (
            warm_start
            and previous_tracked_partition is not None
            and len(previous_tracked_partition.labels) == graph.metadata.get("num_nodes", 0)
        ):
            initial_labels = previous_tracked_partition.labels
        labels = algorithm.run(graph, initial_labels=initial_labels)
        return Partition(
            frame_index=graph.frame_index,
            labels=labels,
            kind="local",
            metadata={"warm_started": initial_labels is not None},
        )

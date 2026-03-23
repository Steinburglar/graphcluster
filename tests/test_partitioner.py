# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for local partitioning behavior.

These tests focus on interface and orchestration expectations rather than real
clustering quality.
"""

from graphcluster.graph.sparse_graph import SparseWeightedGraph
from graphcluster.partitioning.partition import Partition
from graphcluster.partitioning.partitioner import Partitioner


def test_partitioner_marks_local_partition_kind() -> None:
    partitioner = Partitioner.from_config({"partition": {"warm_start": False}})
    graph = SparseWeightedGraph(frame_index=1, metadata={"num_nodes": 3})
    partition = partitioner.partition_local(graph)
    assert partition.kind == "local"
    assert partition.frame_index == 1


def test_partitioner_notes_when_warm_start_was_used() -> None:
    partitioner = Partitioner.from_config({"partition": {"warm_start": True}})
    graph = SparseWeightedGraph(frame_index=2, metadata={"num_nodes": 2})
    previous = Partition(frame_index=1, labels=[1, 1], kind="tracked")
    partition = partitioner.partition_local(graph, previous_tracked_partition=previous)
    assert partition.metadata["warm_started"] is True

# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for local partitioning behavior.

These tests focus on interface and orchestration expectations rather than real
clustering quality.
"""

import pytest
from scipy import sparse

from graphcluster.graph.sparse_graph import SparseWeightedGraph
from graphcluster.partitioning import algorithms
from graphcluster.partitioning.partition import Partition
from graphcluster.partitioning.partitioner import Partitioner


def test_partitioner_marks_local_partition_kind() -> None:
    partitioner = Partitioner.from_config(
        {"partition": {"algorithm": "placeholder", "warm_start": False}}
    )
    graph = SparseWeightedGraph(frame_index=1, metadata={"num_nodes": 3})
    partition = partitioner.partition_local(graph)
    assert partition.kind == "local"
    assert partition.frame_index == 1


def test_partitioner_notes_when_warm_start_was_used() -> None:
    partitioner = Partitioner.from_config(
        {"partition": {"algorithm": "placeholder", "warm_start": True}}
    )
    graph = SparseWeightedGraph(frame_index=2, metadata={"num_nodes": 2})
    previous = Partition(frame_index=1, labels=[1, 1], kind="tracked")
    partition = partitioner.partition_local(graph, previous_tracked_partition=previous)
    assert partition.metadata["warm_started"] is True


def test_leiden_partitioner_finds_disconnected_communities() -> None:
    adjacency = sparse.csr_matrix(
        [
            [0.0, 1.0, 1.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            [1.0, 1.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
            [0.0, 0.0, 0.0, 1.0, 0.0, 1.0],
            [0.0, 0.0, 0.0, 1.0, 1.0, 0.0],
        ]
    )
    graph = SparseWeightedGraph(
        frame_index=0,
        adjacency=adjacency,
        metadata={"num_nodes": 6},
    )
    partitioner = Partitioner.from_config(
        {"partition": {"algorithm": "leiden", "objective": "modularity"}}
    )
    partition = partitioner.partition_local(graph)

    left = {partition.labels[i] for i in [0, 1, 2]}
    right = {partition.labels[i] for i in [3, 4, 5]}
    assert len(left) == 1
    assert len(right) == 1
    assert left != right


def test_leiden_partitioner_passes_compressed_warm_start_membership(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePartition:
        membership = [0, 0, 1, 1]

    def fake_run_leiden_partition(**kwargs):
        captured.update(kwargs)
        return FakePartition.membership

    monkeypatch.setattr(algorithms, "run_leiden_partition", fake_run_leiden_partition)

    adjacency = sparse.csr_matrix(
        [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
    )
    graph = SparseWeightedGraph(
        frame_index=2,
        adjacency=adjacency,
        metadata={"num_nodes": 4},
    )
    previous = Partition(frame_index=1, labels=[10, 10, 20, 20], kind="tracked")
    partitioner = Partitioner.from_config(
        {"partition": {"algorithm": "leiden", "warm_start": True}}
    )
    partition = partitioner.partition_local(graph, previous_tracked_partition=previous)

    assert partition.metadata["warm_started"] is True
    assert captured["initial_membership"] == [0, 0, 1, 1]


def test_leiden_partitioner_forwards_resolution_parameter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_leiden_partition(**kwargs):
        captured.update(kwargs)
        return [0, 0, 1, 1]

    monkeypatch.setattr(algorithms, "run_leiden_partition", fake_run_leiden_partition)

    adjacency = sparse.csr_matrix(
        [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
    )
    graph = SparseWeightedGraph(
        frame_index=0,
        adjacency=adjacency,
        metadata={"num_nodes": 4},
    )
    partitioner = Partitioner.from_config(
        {
            "partition": {
                "algorithm": "leiden",
                "objective": "cpm",
                "resolution": 0.1,
            }
        }
    )

    partition = partitioner.partition_local(graph)

    assert partition.labels == [0, 0, 1, 1]
    assert captured["partition_kwargs"]["resolution_parameter"] == pytest.approx(0.1)

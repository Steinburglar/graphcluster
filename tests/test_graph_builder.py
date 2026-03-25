# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for graph building.

These tests describe the intended contract for turning frames into sparse graph
objects. They are meant to protect the graph-construction seam as real logic is
added.
"""

import pytest
from scipy import sparse

from graphcluster.graph.graph_builder import GraphBuilder
from graphcluster.io.frame import Frame


def test_graph_builder_uses_trajectory_source_by_default() -> None:
    builder = GraphBuilder.from_config(
        {"graph": {"cutoff": 1.5, "kernel": "binary"}}
    )
    graph = builder.build(
        Frame(
            index=2,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
            atom_types=["Ga", "Ga", "Pt"],
        )
    )
    assert graph.frame_index == 2
    assert graph.metadata["source"] == "trajectory"
    assert graph.metadata["num_nodes"] == 3
    assert graph.metadata["num_edges"] == 1
    assert graph.metadata["kernel"] == "binary"
    assert sparse.issparse(graph.adjacency)
    assert graph.adjacency[0, 1] == pytest.approx(1.0)
    assert graph.adjacency[0, 2] == pytest.approx(0.0)


def test_graph_builder_can_switch_to_allegro_source() -> None:
    builder = GraphBuilder.from_config({"graph": {"source": "allegro"}})
    graph = builder.build(Frame(index=4, positions=[[1.0, 0.0, 0.0]], atom_types=["Pt"]))
    assert graph.metadata["source"] == "allegro"


def test_graph_builder_can_use_distance_kernel() -> None:
    builder = GraphBuilder.from_config(
        {"graph": {"cutoff": 2.0, "kernel": "distance"}}
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.25, 0.0, 0.0]],
            atom_types=["Ga", "Pt"],
        )
    )
    assert graph.adjacency[0, 1] == pytest.approx(1.25)


def test_graph_builder_can_resolve_auto_cutoff_from_input_metadata() -> None:
    builder = GraphBuilder.from_config(
        {
            "input": {"cutoff_radius": 1.6},
            "graph": {"cutoff": "auto", "kernel": "binary"},
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["Ga", "Pt"],
        )
    )
    assert graph.metadata["cutoff"] == pytest.approx(1.6)
    assert graph.adjacency[0, 1] == pytest.approx(1.0)

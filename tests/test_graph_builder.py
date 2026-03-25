# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for graph building.

These tests describe the intended contract for turning frames into sparse graph
objects. They are meant to protect the graph-construction seam as real logic is
added.
"""

from graphcluster.graph.graph_builder import GraphBuilder
from graphcluster.io.frame import Frame


def test_graph_builder_uses_trajectory_source_by_default() -> None:
    builder = GraphBuilder.from_config({"graph": {}})
    graph = builder.build(Frame(index=2, positions=[[0.0, 0.0, 0.0]], atom_types=["Ga"]))
    assert graph.frame_index == 2
    assert graph.metadata["source"] == "trajectory"
    assert graph.metadata["num_nodes"] == 1


def test_graph_builder_can_switch_to_allegro_source() -> None:
    builder = GraphBuilder.from_config({"graph": {"source": "allegro"}})
    graph = builder.build(Frame(index=4, positions=[[1.0, 0.0, 0.0]], atom_types=["Pt"]))
    assert graph.metadata["source"] == "allegro"

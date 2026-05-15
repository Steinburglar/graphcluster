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
    graph = builder.build(
        Frame(
            index=4,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["Pt", "Pt"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 1], [1, 0]],
                    "allegro_edge_energies": [-0.2, -0.3],
                }
            },
        )
    )
    assert graph.metadata["source"] == "allegro"
    assert sparse.issparse(graph.adjacency)
    assert graph.metadata["num_edges"] == 1
    assert graph.adjacency[0, 1] == pytest.approx(0.5)


def test_graph_builder_sums_directed_allegro_edge_energies_into_symmetric_weights() -> None:
    builder = GraphBuilder.from_config({"graph": {"source": "allegro"}})
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            atom_types=["Ga", "Pt", "Pt"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 1], [1, 0], [1, 2], [2, 1]],
                    "allegro_edge_energies": [-0.4, -0.1, 0.2, -0.3],
                }
            },
        )
    )
    assert graph.metadata["source"] == "allegro"
    assert graph.adjacency[0, 1] == pytest.approx(0.5)
    assert graph.adjacency[1, 0] == pytest.approx(0.5)
    assert graph.adjacency[1, 2] == pytest.approx(0.3)
    assert graph.adjacency[2, 1] == pytest.approx(0.3)
    assert graph.adjacency[0, 2] == pytest.approx(0.0)


def test_graph_builder_can_use_scaled_allegro_edge_energies() -> None:
    builder = GraphBuilder.from_config(
        {"graph": {"source": "allegro", "energy_field": "scaled"}}
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["Ga", "Pt"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 1], [1, 0]],
                    "allegro_edge_raw_energies": [-100.0, -100.0],
                    "allegro_edge_scaled_energies": [-0.2, -0.3],
                }
            },
        )
    )
    assert graph.adjacency[0, 1] == pytest.approx(0.5)


def test_graph_builder_ignores_positive_and_self_allegro_edges() -> None:
    builder = GraphBuilder.from_config({"graph": {"source": "allegro"}})
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["Ga", "Pt"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 0], [0, 1], [1, 0]],
                    "allegro_edge_energies": [-1.0, 0.2, 0.1],
                }
            },
        )
    )
    assert graph.metadata["num_edges"] == 0
    assert graph.adjacency.nnz == 0


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
    assert graph.metadata["cutoff_source"] == "input.cutoff_radius"
    assert graph.adjacency[0, 1] == pytest.approx(1.0)


def test_graph_builder_can_resolve_auto_cutoff_from_frame_metadata() -> None:
    builder = GraphBuilder.from_config(
        {
            "graph": {"cutoff": "auto", "kernel": "binary"},
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.1, 0.0, 0.0]],
            atom_types=["Ga", "Pt", "Pt"],
            metadata={"ase_info": {"pair_cutoff": 1.75}},
        )
    )
    assert graph.metadata["cutoff"] == pytest.approx(1.75)
    assert graph.metadata["cutoff_source"] == "frame.metadata.ase_info.pair_cutoff"
    assert graph.adjacency[0, 1] == pytest.approx(1.0)
    assert graph.adjacency[0, 2] == pytest.approx(0.0)


def test_graph_builder_can_use_gaussian_kernel() -> None:
    builder = GraphBuilder.from_config(
        {
            "graph": {
                "cutoff": 2.0,
                "kernel": {"name": "gaussian", "sigma": 0.5},
            }
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["Ga", "Pt"],
        )
    )
    assert graph.metadata["kernel"] == "gaussian"
    assert graph.adjacency[0, 1] == pytest.approx(0.1353352832366127)


def test_graph_builder_gaussian_kernel_has_cutoff_scaled_default_sigma() -> None:
    builder = GraphBuilder.from_config(
        {
            "graph": {
                "cutoff": 3.0,
                "kernel": "gaussian",
            }
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["Ga", "Pt"],
        )
    )
    assert graph.adjacency[0, 1] == pytest.approx(0.6065306597126334)

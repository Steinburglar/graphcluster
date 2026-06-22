# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for graph building.

These tests describe the intended contract for turning frames into sparse graph
objects. They are meant to protect the graph-construction seam as real logic is
added.
"""

from pathlib import Path

import pytest
from scipy import sparse

from graphcluster.graph.allegro_edges import estimate_allegro_edge_scale
from graphcluster.graph.graph_builder import GraphBuilder
from graphcluster.io.frame import Frame

FOUNDATION_ALLEGRO_TRAJ = Path(
    "/n/home12/lsteinberger/systems/hpt/data/trajectories/annotated_allegro_edges/"
    "hpt_600k_allegro_edges.traj"
)


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


def test_graph_builder_can_use_signed_shifted_sum_for_allegro_edges() -> None:
    builder = GraphBuilder.from_config(
        {
            "graph": {
                "source": "allegro",
                "energy_field": "scaled",
                "energy_to_weight": "signed_shifted_sum",
                "species_shifts": {"H": -4.0, "Pt": -2.0},
                "avg_num_neighbors": 2.0,
            }
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["H", "Pt"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 1], [1, 0]],
                    "allegro_edge_scaled_energies": [-0.2, -0.3],
                }
            },
        )
    )
    # Each directed contribution uses -(E + shift/avg_nbr):
    # H->Pt: -(-0.2 + -4/2) = 2.2
    # Pt->H: -(-0.3 + -2/2) = 1.3
    # undirected sum = 3.5
    assert graph.adjacency[0, 1] == pytest.approx(3.5)
    assert graph.adjacency[1, 0] == pytest.approx(3.5)


def test_graph_builder_keeps_negative_weights_in_signed_shifted_sum() -> None:
    builder = GraphBuilder.from_config(
        {
            "graph": {
                "source": "allegro",
                "energy_field": "scaled",
                "energy_to_weight": "signed_shifted_sum",
                "species_shifts": {"H": 0.0, "Pt": 0.0},
                "avg_num_neighbors": 1.0,
            }
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["H", "Pt"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 1], [1, 0]],
                    "allegro_edge_scaled_energies": [0.2, 0.3],
                }
            },
        )
    )
    # contributions = -0.2 and -0.3 => undirected = -0.5
    assert graph.adjacency[0, 1] == pytest.approx(-0.5)
    assert graph.adjacency[1, 0] == pytest.approx(-0.5)


def test_graph_builder_signed_shifted_sum_uses_chemical_symbols_for_lookup() -> None:
    builder = GraphBuilder.from_config(
        {
            "graph": {
                "source": "allegro",
                "energy_field": "scaled",
                "energy_to_weight": "signed_shifted_sum",
                "species_shifts": {"H": -4.0, "Pt": -2.0},
                "avg_num_neighbors": {"H": 2.0, "Pt": 2.0},
            }
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=[2, 1],
            chemical_symbols=["Pt", "H"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 1], [1, 0]],
                    "allegro_edge_scaled_energies": [-0.2, -0.3],
                }
            },
        )
    )
    assert graph.adjacency[0, 1] == pytest.approx(3.5)


def test_allegro_edge_scale_uses_percentile_and_budget() -> None:
    frame_a = Frame(
        index=0,
        positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        atom_types=["Ga", "Pt"],
        metadata={
            "ase_info": {
                "allegro_edge_indices": [[0, 1], [1, 0]],
                "allegro_edge_energies": [-1.0, -9.0],
            }
        },
    )
    frame_b = Frame(
        index=1,
        positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        atom_types=["Ga", "Pt"],
        metadata={
            "ase_info": {
                "allegro_edge_indices": [[0, 1], [1, 0]],
                "allegro_edge_energies": [-100.0, -200.0],
            }
        },
    )

    scale = estimate_allegro_edge_scale(
        [frame_a, frame_b],
        {
            "kind": "allegro",
            "energy_field": "raw",
            "allegro_scaling": {"percentile": 50.0, "sample_edge_budget": 2},
        },
    )

    assert scale == pytest.approx(5.0)


def test_graph_builder_applies_allegro_edge_scale() -> None:
    builder = GraphBuilder.from_config(
        {
            "graph": {
                "source": "allegro",
                "energy_field": "raw",
                "allegro_edge_scale": 4.0,
            }
        }
    )
    graph = builder.build(
        Frame(
            index=0,
            positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            atom_types=["Ga", "Pt"],
            metadata={
                "ase_info": {
                    "allegro_edge_indices": [[0, 1], [1, 0]],
                    "allegro_edge_energies": [-1.0, -3.0],
                }
            },
        )
    )
    assert graph.metadata["allegro_edge_scale"] == pytest.approx(4.0)
    assert graph.adjacency[0, 1] == pytest.approx(1.0)


def test_allegro_scaling_reduces_weight_magnitude() -> None:
    frame = Frame(
        index=0,
        positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        atom_types=["Ga", "Pt"],
        metadata={
            "ase_info": {
                "allegro_edge_indices": [[0, 1], [1, 0]],
                "allegro_edge_energies": [-1.0, -9.0],
            }
        },
    )
    scale = estimate_allegro_edge_scale(
        [frame],
        {
            "kind": "allegro",
            "energy_field": "raw",
            "allegro_scaling": {
                "percentile": 50.0,
                "sample_edge_budget": 2,
            },
        },
    )
    unscaled_graph = GraphBuilder.from_config({"graph": {"source": "allegro"}}).build(frame)
    scaled_graph = GraphBuilder.from_config(
        {
            "graph": {
                "source": "allegro",
                "energy_field": "raw",
                "allegro_edge_scale": scale,
            }
        }
    ).build(frame)

    assert scale == pytest.approx(5.0)
    assert scaled_graph.adjacency[0, 1] == pytest.approx(unscaled_graph.adjacency[0, 1] / 5.0)
    assert float(scaled_graph.adjacency.max()) < float(unscaled_graph.adjacency.max())


def test_foundation_allegro_edge_scaling_reduces_real_weights() -> None:
    try:
        from ase.io import read
    except ImportError:  # pragma: no cover
        pytest.skip("ASE required for trajectory regression test.")

    atoms = read(str(FOUNDATION_ALLEGRO_TRAJ), index=0)
    frame = Frame(
        index=0,
        positions=atoms.get_positions(),
        atom_types=atoms.get_chemical_symbols(),
        metadata={"ase_info": dict(atoms.info)},
    )

    scale = estimate_allegro_edge_scale(
        [frame],
        {
            "kind": "allegro",
            "energy_field": "raw",
            "allegro_scaling": {
                "percentile": 99.5,
                "sample_edge_budget": 200000,
            },
        },
    )
    unscaled_graph = GraphBuilder.from_config({"graph": {"source": "allegro"}}).build(frame)
    scaled_graph = GraphBuilder.from_config(
        {
            "graph": {
                "source": "allegro",
                "energy_field": "raw",
                "allegro_edge_scale": scale,
            }
        }
    ).build(frame)

    assert scale > 1.0
    assert float(scaled_graph.adjacency.max()) < float(unscaled_graph.adjacency.max())
    assert scaled_graph.metadata["num_edges"] == unscaled_graph.metadata["num_edges"]


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

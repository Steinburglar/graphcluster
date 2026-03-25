# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Trajectory-derived edge building hooks.

This module owns geometry-based graph construction for ordinary trajectory
inputs. The current implementation is intentionally simple:
- one distance cutoff
- one configurable edge-weight kernel
- sparse weighted adjacency output

The design is meant to stay open to future kernels such as smoother radial
functions or model-derived edge energies without changing the rest of the
pipeline.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree

from ..io.frame import Frame


def build_trajectory_adjacency(
    frame: Frame,
    graph_config: dict,
    input_config: dict | None = None,
) -> sparse.csr_matrix:
    """Build a cutoff-based sparse weighted adjacency matrix for one frame."""
    positions = np.asarray(frame.positions, dtype=float)
    num_nodes = len(positions)
    if num_nodes == 0:
        return sparse.csr_matrix((0, 0), dtype=float)
    if num_nodes == 1:
        return sparse.csr_matrix((1, 1), dtype=float)

    cutoff = resolve_cutoff_radius(frame, graph_config, input_config=input_config)
    kernel_name, kernel_config = resolve_kernel_config(graph_config)

    shifted_positions = positions.copy()
    box_lengths = extract_orthorhombic_box_lengths(frame)
    use_periodic_box = box_lengths is not None and np.all(box_lengths > 0)
    if use_periodic_box and frame.cell_origin is not None:
        shifted_positions = shifted_positions - np.asarray(frame.cell_origin, dtype=float)
        shifted_positions = np.mod(shifted_positions, box_lengths)

    tree = cKDTree(shifted_positions, boxsize=box_lengths if use_periodic_box else None)
    pairs = tree.query_pairs(cutoff, output_type="ndarray")
    if len(pairs) == 0:
        return sparse.csr_matrix((num_nodes, num_nodes), dtype=float)

    distances = pairwise_distances(shifted_positions, pairs, box_lengths if use_periodic_box else None)
    weights = compute_kernel_weights(distances, kernel_name, kernel_config)

    rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
    cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
    data = np.concatenate([weights, weights])
    adjacency = sparse.coo_matrix((data, (rows, cols)), shape=(num_nodes, num_nodes))
    return adjacency.tocsr()


def resolve_cutoff_radius(
    frame: Frame,
    graph_config: dict,
    input_config: dict | None = None,
) -> float:
    """Resolve the distance cutoff radius to use for graph construction."""
    _ = frame
    cutoff = graph_config.get("cutoff")
    if cutoff is None:
        raise ValueError(
            "Trajectory graph construction requires graph.cutoff to be set, or "
            "graph.cutoff: auto with an input cutoff source available."
        )
    if isinstance(cutoff, str):
        if cutoff != "auto":
            raise ValueError(f"Unsupported cutoff specifier: {cutoff!r}")
        input_config = input_config or {}
        for key in ("cutoff_radius", "neighbor_cutoff", "pair_cutoff"):
            value = input_config.get(key)
            if value is not None:
                return float(value)
        raise ValueError(
            "graph.cutoff was set to 'auto', but no supported input cutoff metadata "
            "was found. Try setting graph.cutoff explicitly or providing "
            "input.cutoff_radius."
        )
    return float(cutoff)


def resolve_kernel_config(graph_config: dict) -> tuple[str, dict]:
    """Resolve the configured edge-weight kernel name and parameters."""
    kernel = graph_config.get("kernel", "distance")
    if isinstance(kernel, str):
        return kernel, {}
    if isinstance(kernel, dict):
        return str(kernel.get("name", "distance")), dict(kernel)
    raise ValueError(f"Unsupported graph.kernel value: {kernel!r}")


def extract_orthorhombic_box_lengths(frame: Frame) -> np.ndarray | None:
    """Return orthorhombic cell lengths when available, else ``None``."""
    if frame.box is None:
        return None
    box = np.asarray(frame.box, dtype=float)
    if box.shape == (3,):
        return box
    if box.shape != (3, 3):
        return None
    if not np.allclose(box, np.diag(np.diag(box))):
        return None
    return np.diag(box)


def pairwise_distances(
    positions: np.ndarray,
    pairs: np.ndarray,
    box_lengths: np.ndarray | None,
) -> np.ndarray:
    """Compute pair distances, optionally using orthorhombic minimum-image PBC."""
    deltas = positions[pairs[:, 1]] - positions[pairs[:, 0]]
    if box_lengths is not None:
        deltas = deltas - box_lengths * np.round(deltas / box_lengths)
    return np.linalg.norm(deltas, axis=1)


def compute_kernel_weights(
    distances: np.ndarray,
    kernel_name: str,
    kernel_config: dict,
) -> np.ndarray:
    """Convert pair distances into edge weights using the configured kernel."""
    if kernel_name == "binary":
        return np.ones_like(distances, dtype=float)
    if kernel_name == "distance":
        return distances.astype(float)
    if kernel_name == "inverse_distance":
        epsilon = float(kernel_config.get("epsilon", 1.0e-12))
        return 1.0 / np.maximum(distances, epsilon)
    if kernel_name == "smooth_inverse_distance":
        epsilon = float(kernel_config.get("epsilon", 1.0e-12))
        cutoff = float(kernel_config["cutoff"])
        safe_distances = np.maximum(distances, epsilon)
        smooth_cutoff = 0.5 * (np.cos(math.pi * distances / cutoff) + 1.0)
        return smooth_cutoff / safe_distances
    raise ValueError(
        "Unsupported graph kernel "
        f"{kernel_name!r}. Supported kernels are binary, distance, "
        "inverse_distance, and smooth_inverse_distance."
    )

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
    edges_config: dict,
    source_config: dict | None = None,
) -> sparse.csr_matrix:
    """Build a cutoff-based sparse weighted adjacency matrix for one frame."""
    positions = np.asarray(frame.positions, dtype=float)
    num_nodes = len(positions)
    if num_nodes == 0:
        return sparse.csr_matrix((0, 0), dtype=float)
    if num_nodes == 1:
        return sparse.csr_matrix((1, 1), dtype=float)

    cutoff = resolve_cutoff_radius(frame, edges_config, source_config=source_config)
    kernel_name, kernel_config = resolve_kernel_config(edges_config)
    kernel_config = materialize_kernel_config(kernel_name, kernel_config, cutoff=cutoff)

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
    edges_config: dict,
    source_config: dict | None = None,
) -> float:
    """Resolve the distance cutoff radius to use for graph construction."""
    return resolve_cutoff_spec(frame, edges_config, source_config=source_config)[0]


def resolve_cutoff_spec(
    frame: Frame,
    edges_config: dict,
    source_config: dict | None = None,
) -> tuple[float, str]:
    """Resolve the cutoff radius and record where it came from."""
    cutoff = edges_config.get("cutoff")
    if cutoff is None:
        raise ValueError(
            "Geometry-based edge construction requires edges.cutoff to be set, or "
            "edges.cutoff: auto with a source cutoff available."
        )
    if isinstance(cutoff, str):
        if cutoff != "auto":
            raise ValueError(f"Unsupported cutoff specifier: {cutoff!r}")
        inferred_cutoff = infer_recorded_cutoff_radius(frame, source_config=source_config)
        if inferred_cutoff is not None:
            return inferred_cutoff
        raise ValueError(
            "edges.cutoff was set to 'auto', but no supported source cutoff metadata "
            "was found in the frame metadata or source config. Try setting "
            "edges.cutoff explicitly or providing a recorded cutoff such as "
            "source.cutoff_radius."
        )
    return float(cutoff), "edges.cutoff"


def resolve_kernel_config(edges_config: dict) -> tuple[str, dict]:
    """Resolve the configured geometry edge-weight kernel and parameters."""
    kernel_name = str(edges_config.get("kind", "distance"))
    kernel_config = dict(edges_config)
    return kernel_name, kernel_config


def materialize_kernel_config(
    kernel_name: str,
    kernel_config: dict,
    *,
    cutoff: float,
) -> dict:
    """Fill in kernel defaults that depend on the resolved cutoff."""
    resolved = dict(kernel_config)
    resolved.setdefault("cutoff", float(cutoff))
    if kernel_name in {"gaussian", "gaussian_distance"}:
        resolved.setdefault("sigma", float(cutoff) / 3.0)
    return resolved


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
    if kernel_name in {"gaussian", "gaussian_distance"}:
        sigma = float(kernel_config["sigma"])
        if sigma <= 0:
            raise ValueError("Gaussian graph kernel requires sigma > 0.")
        return np.exp(-(distances**2) / (2.0 * sigma**2))
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
        "gaussian, inverse_distance, and smooth_inverse_distance."
    )


def infer_recorded_cutoff_radius(
    frame: Frame,
    source_config: dict | None = None,
) -> tuple[float, str] | None:
    """Best-effort cutoff inference from recorded frame metadata or source config."""
    frame_match = find_first_metadata_value(frame.metadata, CUTOFF_METADATA_KEYS)
    if frame_match is not None:
        path, value = frame_match
        return float(value), f"frame.metadata.{path}"

    source_config = source_config or {}
    source_match = find_first_metadata_value(source_config, CUTOFF_METADATA_KEYS)
    if source_match is not None:
        path, value = source_match
        return float(value), f"source.{path}"
    return None


def find_first_metadata_value(
    metadata: dict | None,
    keys: tuple[str, ...],
    *,
    prefix: str = "",
) -> tuple[str, float] | None:
    """Recursively find the first numeric metadata value whose key matches."""
    if not isinstance(metadata, dict):
        return None

    for key in keys:
        value = metadata.get(key)
        numeric_value = coerce_positive_float(value)
        if numeric_value is not None:
            return f"{prefix}{key}", numeric_value

    for key, value in metadata.items():
        if not isinstance(value, dict):
            continue
        match = find_first_metadata_value(value, keys, prefix=f"{prefix}{key}.")
        if match is not None:
            return match
    return None


def coerce_positive_float(value: object) -> float | None:
    """Return a positive float when the value looks like one, else ``None``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if numeric_value <= 0:
        return None
    return numeric_value


CUTOFF_METADATA_KEYS = (
    "cutoff",
    "cutoff_radius",
    "neighbor_cutoff",
    "pair_cutoff",
    "edge_cutoff",
    "rcut",
    "r_cut",
    "r_max",
)

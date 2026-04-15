# Date: 2026-03-27
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Build graph edges from exported Allegro edge metadata.

This module intentionally consumes *recorded* model-derived edge data rather
than trying to reproduce Allegro graph semantics from geometry alone.

Current expected source:
- an ASE-readable trajectory whose ``Atoms.info`` contains the exported keys
  written by the separate ``allegro_ase_edge_export`` package

Current weight semantics:
- Allegro edge energies are directed
- positive energies are ignored
- negative energies become bond strengths via ``abs(energy)``
- the undirected graph weight for a pair is the sum of both directed
  contributions ``E_ij`` and ``E_ji`` after that transformation

This makes the resulting adjacency suitable for the current Leiden graph path,
which expects a symmetric weighted graph.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy import sparse

from ..io.frame import Frame

EDGE_ENERGIES_INFO_KEY = "allegro_edge_energies"
EDGE_INDICES_INFO_KEY = "allegro_edge_indices"


def build_allegro_adjacency(frame: Frame, graph_config: dict) -> sparse.csr_matrix:
    """Build a symmetric sparse adjacency from exported Allegro edge metadata."""
    _ = graph_config
    num_nodes = len(frame.positions)
    if num_nodes == 0:
        return sparse.csr_matrix((0, 0), dtype=float)
    if num_nodes == 1:
        return sparse.csr_matrix((1, 1), dtype=float)

    ase_info = extract_allegro_metadata(frame)
    edge_index = np.asarray(ase_info[EDGE_INDICES_INFO_KEY], dtype=int)
    edge_energy = np.asarray(ase_info[EDGE_ENERGIES_INFO_KEY], dtype=float).reshape(-1)

    edge_index = normalize_edge_index(edge_index)
    validate_edge_payload(edge_index=edge_index, edge_energy=edge_energy, num_nodes=num_nodes)

    undirected_weights = combine_directed_edge_energies(
        edge_index=edge_index,
        edge_energy=edge_energy,
    )
    if not undirected_weights:
        return sparse.csr_matrix((num_nodes, num_nodes), dtype=float)

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for (source, target), weight in undirected_weights.items():
        if weight <= 0:
            continue
        rows.extend([source, target])
        cols.extend([target, source])
        data.extend([weight, weight])

    if not data:
        return sparse.csr_matrix((num_nodes, num_nodes), dtype=float)
    adjacency = sparse.coo_matrix((data, (rows, cols)), shape=(num_nodes, num_nodes))
    return adjacency.tocsr()


def extract_allegro_metadata(frame: Frame) -> dict:
    """Return the metadata dict that should contain exported Allegro edge arrays."""
    metadata = frame.metadata or {}
    if EDGE_INDICES_INFO_KEY in metadata and EDGE_ENERGIES_INFO_KEY in metadata:
        return metadata

    ase_info = metadata.get("ase_info")
    if isinstance(ase_info, dict):
        if EDGE_INDICES_INFO_KEY in ase_info and EDGE_ENERGIES_INFO_KEY in ase_info:
            return ase_info

    raise ValueError(
        "graph.source='allegro' requires exported edge metadata in the input frame. "
        f"Expected {EDGE_INDICES_INFO_KEY!r} and {EDGE_ENERGIES_INFO_KEY!r} in "
        "frame.metadata or frame.metadata['ase_info']."
    )


def normalize_edge_index(edge_index: np.ndarray) -> np.ndarray:
    """Normalize edge indices to shape ``(num_edges, 2)``."""
    if edge_index.ndim != 2:
        raise ValueError(
            "Exported Allegro edge indices must be a rank-2 array shaped like "
            "(num_edges, 2) or (2, num_edges)."
        )
    if edge_index.shape[1] == 2:
        return edge_index
    if edge_index.shape[0] == 2:
        return edge_index.T
    raise ValueError(
        "Exported Allegro edge indices must be shaped like (num_edges, 2) or "
        f"(2, num_edges), got {tuple(edge_index.shape)}."
    )


def validate_edge_payload(
    *,
    edge_index: np.ndarray,
    edge_energy: np.ndarray,
    num_nodes: int,
) -> None:
    """Validate basic consistency of the exported edge arrays."""
    if edge_index.shape[0] != edge_energy.shape[0]:
        raise ValueError(
            "Exported Allegro edge arrays must have the same number of rows. "
            f"Got {edge_index.shape[0]} edges but {edge_energy.shape[0]} energies."
        )
    if edge_index.size == 0:
        return
    min_index = int(edge_index.min())
    max_index = int(edge_index.max())
    if min_index < 0 or max_index >= num_nodes:
        raise ValueError(
            "Exported Allegro edge indices are out of bounds for the frame. "
            f"Valid node indices are [0, {num_nodes - 1}], got [{min_index}, {max_index}]."
        )


def combine_directed_edge_energies(
    *,
    edge_index: np.ndarray,
    edge_energy: np.ndarray,
) -> dict[tuple[int, int], float]:
    """Collapse directed edge energies into undirected bond strengths.

    Current semantics are intentionally simple:
    - positive energies contribute nothing
    - negative energies contribute ``abs(energy)``
    - both directions accumulate onto the same undirected pair
    """
    undirected_weights: dict[tuple[int, int], float] = defaultdict(float)
    for (source, target), energy in zip(edge_index, edge_energy, strict=True):
        if source == target or energy >= 0:
            continue
        pair = tuple(sorted((int(source), int(target))))
        undirected_weights[pair] += abs(float(energy))
    return dict(undirected_weights)

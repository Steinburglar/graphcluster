# Date: 2026-03-27
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Build graph edges from exported Allegro edge metadata.

This module intentionally consumes *recorded* model-derived edge data rather
than trying to reproduce Allegro graph semantics from geometry alone.

Current expected source:
- an ASE-readable trajectory whose ``Atoms.info`` contains the exported keys
  written by the separate ``allegro_annotate`` package

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
EDGE_RAW_ENERGIES_INFO_KEY = "allegro_edge_raw_energies"
EDGE_SCALED_ENERGIES_INFO_KEY = "allegro_edge_scaled_energies"
EDGE_INDICES_INFO_KEY = "allegro_edge_indices"


def build_allegro_adjacency(frame: Frame, edges_config: dict) -> sparse.csr_matrix:
    """Build a symmetric sparse adjacency from exported Allegro edge metadata."""
    num_nodes = len(frame.positions)
    if num_nodes == 0:
        return sparse.csr_matrix((0, 0), dtype=float)
    if num_nodes == 1:
        return sparse.csr_matrix((1, 1), dtype=float)

    ase_info = extract_allegro_metadata(frame)
    edge_index = np.asarray(ase_info[EDGE_INDICES_INFO_KEY], dtype=int)
    edge_energy_key = resolve_edge_energy_key(ase_info, edges_config)
    edge_energy = np.asarray(ase_info[edge_energy_key], dtype=float).reshape(-1)

    edge_index = normalize_edge_index(edge_index)
    validate_edge_payload(edge_index=edge_index, edge_energy=edge_energy, num_nodes=num_nodes)

    energy_to_weight = str(edges_config.get("energy_to_weight", "abs_negative_sum"))
    undirected_weights = combine_directed_edge_energies(
        edge_index=edge_index,
        edge_energy=edge_energy,
        energy_to_weight=energy_to_weight,
        frame=frame,
        edges_config=edges_config,
    )
    if not undirected_weights:
        return sparse.csr_matrix((num_nodes, num_nodes), dtype=float)

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    allow_negative_weights = energy_to_weight == "signed_shifted_sum"
    for (source, target), weight in undirected_weights.items():
        if weight == 0:
            continue
        if not allow_negative_weights and weight <= 0:
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
    if EDGE_INDICES_INFO_KEY in metadata and _has_any_edge_energy(metadata):
        return metadata

    ase_info = metadata.get("ase_info")
    if isinstance(ase_info, dict):
        if EDGE_INDICES_INFO_KEY in ase_info and _has_any_edge_energy(ase_info):
            return ase_info

    raise ValueError(
        "edges.kind='allegro' requires source.path to be an Allegro-annotated "
        "trajectory with exported edge metadata. "
        f"Expected {EDGE_INDICES_INFO_KEY!r} and an Allegro edge energy field in "
        "frame.metadata or frame.metadata['ase_info']."
    )


def _has_any_edge_energy(metadata: dict) -> bool:
    return any(
        key in metadata
        for key in (
            EDGE_RAW_ENERGIES_INFO_KEY,
            EDGE_SCALED_ENERGIES_INFO_KEY,
            EDGE_ENERGIES_INFO_KEY,
        )
    )


def resolve_edge_energy_key(ase_info: dict, edges_config: dict) -> str:
    """Return selected Allegro edge-energy info key."""
    energy_field = str(edges_config.get("energy_field", "raw"))
    if energy_field == "raw":
        if EDGE_RAW_ENERGIES_INFO_KEY in ase_info:
            return EDGE_RAW_ENERGIES_INFO_KEY
        if EDGE_ENERGIES_INFO_KEY in ase_info:
            return EDGE_ENERGIES_INFO_KEY
        raise ValueError(
            "edges.energy_field='raw' requires "
            f"{EDGE_RAW_ENERGIES_INFO_KEY!r} or legacy {EDGE_ENERGIES_INFO_KEY!r}."
        )
    if energy_field == "scaled":
        if EDGE_SCALED_ENERGIES_INFO_KEY in ase_info:
            return EDGE_SCALED_ENERGIES_INFO_KEY
        raise ValueError(
            "edges.energy_field='scaled' requires "
            f"{EDGE_SCALED_ENERGIES_INFO_KEY!r} in Allegro-annotated frame metadata."
        )
    raise ValueError(
        "Unsupported edges.energy_field "
        f"{energy_field!r}. Supported values are ['raw', 'scaled']."
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
    energy_to_weight: str,
    frame: Frame,
    edges_config: dict,
) -> dict[tuple[int, int], float]:
    """Collapse directed edge energies into undirected bond strengths.

    Current semantics are intentionally simple:
    - positive energies contribute nothing
    - negative energies contribute ``abs(energy)``
    - both directions accumulate onto the same undirected pair
    """
    undirected_weights: dict[tuple[int, int], float] = defaultdict(float)
    for (source, target), energy in zip(edge_index, edge_energy, strict=True):
        if source == target:
            continue
        contribution = convert_energy_to_weight(
            float(energy),
            energy_to_weight,
            source=int(source),
            frame=frame,
            edges_config=edges_config,
        )
        if contribution == 0:
            continue
        pair = tuple(sorted((int(source), int(target))))
        undirected_weights[pair] += contribution
    return dict(undirected_weights)


def convert_energy_to_weight(
    energy: float,
    energy_to_weight: str,
    *,
    source: int,
    frame: Frame,
    edges_config: dict,
) -> float:
    """Convert one directed Allegro edge energy into a graph weight."""
    if energy_to_weight == "abs_negative_sum":
        return abs(energy) if energy < 0 else 0.0
    if energy_to_weight == "signed_shifted_sum":
        shift_term = _source_shift_per_edge(
            source=source,
            frame=frame,
            edges_config=edges_config,
        )
        return -(energy + shift_term)
    raise ValueError(
        "Unsupported edges.energy_to_weight "
        f"{energy_to_weight!r}. Supported values are ['abs_negative_sum', 'signed_shifted_sum']."
    )


def _source_shift_per_edge(*, source: int, frame: Frame, edges_config: dict) -> float:
    species_shifts = edges_config.get("species_shifts")
    if not isinstance(species_shifts, dict):
        raise ValueError(
            "edges.energy_to_weight='signed_shifted_sum' requires "
            "edges.species_shifts mapping species->shift."
        )
    atom_types = frame.atom_types
    if atom_types is None:
        raise ValueError(
            "edges.energy_to_weight='signed_shifted_sum' requires frame.atom_types."
        )
    if source < 0 or source >= len(atom_types):
        raise ValueError(f"Source atom index {source} out of bounds for atom_types.")

    species = _source_species_label(frame, source)
    shift = _lookup_species_value(
        species_map=species_shifts,
        species=species,
        field_name="edges.species_shifts",
        frame=frame,
    )
    avg_num_neighbors = edges_config.get("avg_num_neighbors")
    if avg_num_neighbors is None:
        return shift
    if isinstance(avg_num_neighbors, dict):
        denom = _lookup_species_value(
            species_map=avg_num_neighbors,
            species=species,
            field_name="edges.avg_num_neighbors",
            frame=frame,
        )
    else:
        denom = float(avg_num_neighbors)
    if denom <= 0:
        raise ValueError("edges.avg_num_neighbors must be positive.")
    return shift / denom


def _source_species_label(frame: Frame, source: int) -> str:
    if frame.chemical_symbols is not None and source < len(frame.chemical_symbols):
        return str(frame.chemical_symbols[source])
    assert frame.atom_types is not None
    return str(frame.atom_types[source])


def _lookup_species_value(
    *,
    species_map: dict,
    species: str,
    field_name: str,
    frame: Frame,
) -> float:
    if species in species_map:
        return float(species_map[species])
    species_key = str(species)
    if species_key in species_map:
        return float(species_map[species_key])

    available = ", ".join(sorted(str(key) for key in species_map))
    raise ValueError(
        f"{field_name} is missing a value for source species {species!r}. "
        f"Available keys: [{available}]. "
        "If your trajectory carries raw integer atom types, provide source.type_map "
        "so graphcluster can resolve chemical symbols."
    )

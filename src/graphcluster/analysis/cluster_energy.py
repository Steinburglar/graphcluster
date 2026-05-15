# Date: 2026-05-13
"""Per-cluster Allegro pre-energy and reconstructed model-energy summaries.

This module works directly from the raw directed Allegro edge outputs stored on
the input frames. Those exported ``edge_energy`` values are pre-scale,
pre-shift edge contributions. They are useful model-internal signals, but they
are not yet postprocessed per-atom energies in physical model output units.

All ownership conventions here follow Allegro's source/central-atom picture:
one directed edge contribution belongs to the first index of the exported edge
pair, not to both incident atoms.
"""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import Any, Sequence

import numpy as np

from ..bundle.frame_bundle import FrameBundle
from ..graph.allegro_edges import (
    EDGE_ENERGIES_INFO_KEY,
    EDGE_INDICES_INFO_KEY,
    extract_allegro_metadata,
    normalize_edge_index,
    validate_edge_payload,
)


def compute_cluster_raw_allegro_energies(
    bundle: FrameBundle,
) -> list[dict[str, Any]]:
    """Return source-owned raw directed Allegro pre-energy summaries."""

    labels = list(bundle.partition.labels)
    num_nodes = len(labels)
    if len(bundle.frame.positions) != num_nodes:
        raise ValueError(
            "Cluster energy tracking requires one tracked label per atom. "
            f"Got {num_nodes} labels for {len(bundle.frame.positions)} atoms in "
            f"frame {bundle.frame.index}."
        )

    raw_metadata = extract_allegro_metadata(bundle.frame)
    edge_index = np.asarray(raw_metadata[EDGE_INDICES_INFO_KEY], dtype=int)
    edge_energy = np.asarray(raw_metadata[EDGE_ENERGIES_INFO_KEY], dtype=float).reshape(-1)
    edge_index = normalize_edge_index(edge_index)
    validate_edge_payload(edge_index=edge_index, edge_energy=edge_energy, num_nodes=num_nodes)

    cluster_sizes = _count_cluster_sizes(labels)
    internal_energy: dict[int, float] = defaultdict(float)
    external_energy: dict[int, float] = defaultdict(float)

    for (source, target), energy in zip(edge_index, edge_energy, strict=True):
        source_index = int(source)
        target_index = int(target)
        if source_index == target_index:
            continue
        source_cluster = labels[source_index]
        target_cluster = labels[target_index]
        if source_cluster == target_cluster:
            internal_energy[source_cluster] += float(energy)
            continue
        external_energy[source_cluster] += float(energy)

    return [
        _build_raw_cluster_energy_record(
            cluster_id=cluster_id,
            size=cluster_sizes[cluster_id],
            internal_energy=float(internal_energy.get(cluster_id, 0.0)),
            external_energy=float(external_energy.get(cluster_id, 0.0)),
        )
        for cluster_id in sorted(cluster_sizes)
    ]


def compute_cluster_reconstructed_model_energies(
    bundle: FrameBundle,
    *,
    species_scales: dict[str, float] | None = None,
    species_shifts: dict[str, float] | None = None,
    avg_num_neighbors: float | dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return source-owned cluster energies reconstructed after model postprocessing.

    Reconstruction follows Allegro ownership convention:
    - each directed edge contribution belongs to its source/central atom
    - internal/external edge buckets are accumulated per owner atom
    - per-atom edge sums are then normalized like ``EdgewiseReduce``
    - species-dependent scales and shifts are applied afterward
    """

    labels = list(bundle.partition.labels)
    num_nodes = len(labels)
    if len(bundle.frame.positions) != num_nodes:
        raise ValueError(
            "Cluster energy reconstruction requires one tracked label per atom. "
            f"Got {num_nodes} labels for {len(bundle.frame.positions)} atoms in "
            f"frame {bundle.frame.index}."
        )

    raw_metadata = extract_allegro_metadata(bundle.frame)
    edge_index = np.asarray(raw_metadata[EDGE_INDICES_INFO_KEY], dtype=int)
    edge_energy = np.asarray(raw_metadata[EDGE_ENERGIES_INFO_KEY], dtype=float).reshape(-1)
    edge_index = normalize_edge_index(edge_index)
    validate_edge_payload(edge_index=edge_index, edge_energy=edge_energy, num_nodes=num_nodes)

    species_labels = _resolve_species_labels(bundle)
    cluster_sizes = _count_cluster_sizes(labels)
    atom_internal_pre = np.zeros(num_nodes, dtype=float)
    atom_external_pre = np.zeros(num_nodes, dtype=float)

    for (source, target), energy in zip(edge_index, edge_energy, strict=True):
        source_index = int(source)
        target_index = int(target)
        if source_index == target_index:
            continue
        if labels[source_index] == labels[target_index]:
            atom_internal_pre[source_index] += float(energy)
        else:
            atom_external_pre[source_index] += float(energy)

    normalized_internal = _normalize_owner_edge_sums(
        atom_edge_sums=atom_internal_pre,
        species_labels=species_labels,
        avg_num_neighbors=avg_num_neighbors,
    )
    normalized_external = _normalize_owner_edge_sums(
        atom_edge_sums=atom_external_pre,
        species_labels=species_labels,
        avg_num_neighbors=avg_num_neighbors,
    )

    scale_by_species = _normalize_species_map(
        species_map=species_scales or {},
        field_name="species_scales",
    )
    shift_by_species = _normalize_species_map(
        species_map=species_shifts or {},
        field_name="species_shifts",
    )
    atom_scales = np.asarray(
        [scale_by_species.get(species_label, 1.0) for species_label in species_labels],
        dtype=float,
    )
    atom_shifts = np.asarray(
        [shift_by_species.get(species_label, 0.0) for species_label in species_labels],
        dtype=float,
    )

    atom_internal_model = normalized_internal * atom_scales
    atom_external_model = normalized_external * atom_scales

    cluster_internal_model: dict[int, float] = defaultdict(float)
    cluster_external_model: dict[int, float] = defaultdict(float)
    cluster_shift_energy: dict[int, float] = defaultdict(float)

    for atom_index, cluster_id in enumerate(labels):
        cluster_internal_model[cluster_id] += float(atom_internal_model[atom_index])
        cluster_external_model[cluster_id] += float(atom_external_model[atom_index])
        cluster_shift_energy[cluster_id] += float(atom_shifts[atom_index])

    return [
        _build_reconstructed_cluster_energy_record(
            cluster_id=cluster_id,
            size=cluster_sizes[cluster_id],
            internal_model_energy=float(cluster_internal_model.get(cluster_id, 0.0)),
            external_model_energy=float(cluster_external_model.get(cluster_id, 0.0)),
            shift_energy=float(cluster_shift_energy.get(cluster_id, 0.0)),
        )
        for cluster_id in sorted(cluster_sizes)
    ]


def frame_has_raw_allegro_edges(bundle: FrameBundle) -> bool:
    """Return whether the bundle's frame carries raw Allegro edge arrays."""
    metadata = bundle.frame.metadata or {}
    if EDGE_INDICES_INFO_KEY in metadata and EDGE_ENERGIES_INFO_KEY in metadata:
        return True
    ase_info = metadata.get("ase_info")
    return isinstance(ase_info, dict) and (
        EDGE_INDICES_INFO_KEY in ase_info and EDGE_ENERGIES_INFO_KEY in ase_info
    )


def _count_cluster_sizes(labels: list[int]) -> dict[int, int]:
    """Count atoms per tracked cluster."""
    sizes: dict[int, int] = {}
    for label in labels:
        sizes[label] = sizes.get(label, 0) + 1
    return sizes


def _build_raw_cluster_energy_record(
    *,
    cluster_id: int,
    size: int,
    internal_energy: float,
    external_energy: float,
) -> dict[str, Any]:
    """Build one per-cluster raw pre-energy record with size-normalized fields."""
    combined_energy = internal_energy + external_energy
    size_float = float(size)
    return {
        "cluster_id": cluster_id,
        "size": size,
        "energy_kind": "raw_pre_energy",
        "internal_energy": internal_energy,
        "external_energy": external_energy,
        "combined_energy": combined_energy,
        "internal_energy_per_atom": internal_energy / size_float,
        "external_energy_per_atom": external_energy / size_float,
        "combined_energy_per_atom": combined_energy / size_float,
    }


def _resolve_species_labels(bundle: FrameBundle) -> list[str]:
    """Return one species label per atom."""
    frame = bundle.frame
    if frame.chemical_symbols is not None:
        return [str(label) for label in frame.chemical_symbols]
    if frame.atom_types is not None:
        return [str(label) for label in frame.atom_types]
    raise ValueError(
        "Cluster energy analysis requires frame.chemical_symbols or frame.atom_types "
        f"to be available in frame {frame.index}."
    )


def _normalize_species_map(
    *,
    species_map: dict[str, float],
    field_name: str,
) -> dict[str, float]:
    """Normalize species-value mapping into string-keyed float dict."""
    return {str(key): float(value) for key, value in species_map.items()}


def _normalize_owner_edge_sums(
    *,
    atom_edge_sums: np.ndarray,
    species_labels: Sequence[str],
    avg_num_neighbors: float | dict[str, float] | None,
) -> np.ndarray:
    """Apply Allegro `EdgewiseReduce` normalization to per-owner edge sums."""
    if avg_num_neighbors is None:
        return atom_edge_sums / sqrt(2.0)

    if isinstance(avg_num_neighbors, (int, float)):
        normalization = np.full(atom_edge_sums.shape[0], 1.0 / sqrt(float(avg_num_neighbors)))
    elif isinstance(avg_num_neighbors, dict):
        normalized_map = _normalize_species_map(
            species_map=avg_num_neighbors,
            field_name="avg_num_neighbors",
        )
        normalization = np.asarray(
            [1.0 / sqrt(normalized_map.get(species_label, 1.0)) for species_label in species_labels],
            dtype=float,
        )
    else:
        raise TypeError(
            "cluster_energy.model_energy_reconstruction.avg_num_neighbors must be a float "
            "or species-keyed dict."
        )
    return atom_edge_sums * normalization / sqrt(2.0)


def _build_reconstructed_cluster_energy_record(
    *,
    cluster_id: int,
    size: int,
    internal_model_energy: float,
    external_model_energy: float,
    shift_energy: float,
) -> dict[str, Any]:
    """Build one per-cluster postprocessed model-energy record."""
    combined_model_energy = internal_model_energy + external_model_energy + shift_energy
    size_float = float(size)
    return {
        "cluster_id": cluster_id,
        "size": size,
        "energy_kind": "reconstructed_model_energy",
        "internal_model_energy": internal_model_energy,
        "external_model_energy": external_model_energy,
        "shift_energy": shift_energy,
        "combined_model_energy": combined_model_energy,
        "internal_model_energy_per_atom": internal_model_energy / size_float,
        "external_model_energy_per_atom": external_model_energy / size_float,
        "shift_energy_per_atom": shift_energy / size_float,
        "combined_model_energy_per_atom": combined_model_energy / size_float,
    }

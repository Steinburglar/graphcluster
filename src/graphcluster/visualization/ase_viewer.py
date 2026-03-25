# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""ASE-backed visualization adapter.

In intuitive terms, this module is where ASE can be used as a convenient V1
viewer without leaking ASE objects into the rest of the project.

Who touches this:
- people experimenting with ASE-based visualization

Who this touches:
- visualization payloads
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .payload import VisualizationPayload


def payload_to_ase_atoms(payload: VisualizationPayload):
    """Convert a visualization payload into an ASE ``Atoms`` object."""
    from ase import Atoms

    payload.validate()
    positions = np.asarray(payload.positions, dtype=float)
    if payload.cell_origin is not None:
        positions = positions - np.asarray(payload.cell_origin, dtype=float)
    num_atoms = len(positions)
    symbols = _resolve_ase_symbols(payload, num_atoms)
    atoms = Atoms(symbols=symbols, positions=positions)
    if payload.box is not None:
        atoms.set_cell(payload.box)
        atoms.set_pbc(True)

    tracked_labels = np.asarray(payload.labels, dtype=int)
    atoms.new_array("cluster_label", tracked_labels)
    atoms.set_tags(_labels_to_tags(payload.labels))

    if payload.local_labels is not None:
        atoms.new_array("local_cluster_label", np.asarray(payload.local_labels, dtype=int))

    if payload.atom_types is not None and _atom_types_are_ints(payload.atom_types):
        atoms.new_array("raw_atom_type", np.asarray(payload.atom_types, dtype=int))
    if payload.chemical_symbols is not None:
        atoms.info["chemical_symbols"] = list(payload.chemical_symbols)

    atoms.info["frame_index"] = payload.frame_index
    atoms.info["partition_kind"] = payload.metadata.get("partition_kind", "tracked")
    if payload.cell_origin is not None:
        atoms.info["cell_origin"] = np.asarray(payload.cell_origin, dtype=float).tolist()
    if payload.time is not None:
        atoms.info["time"] = payload.time
    return atoms


def view_with_ase(payload: VisualizationPayload, *, viewer: str | None = None):
    """Open one payload in an ASE viewer."""
    from ase.visualize import view

    atoms = payload_to_ase_atoms(payload)
    return view(atoms, viewer=viewer)


@dataclass
class AseTrajectoryWriter:
    """Append visualization payloads to one ASE-readable trajectory artifact."""

    output_path: Path
    written_frames: list[int] = field(default_factory=list)
    _trajectory: object | None = field(default=None, init=False, repr=False)

    def write_payload(self, payload: VisualizationPayload) -> Path:
        """Append a payload to the configured trajectory artifact."""
        from ase.io import write

        if self._trajectory is None:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self._trajectory = True
        atoms = payload_to_ase_atoms(payload)
        write(
            self.output_path,
            atoms,
            format="extxyz",
            append=bool(self.written_frames),
        )
        self.written_frames.append(payload.frame_index)
        return self.output_path

    def close(self) -> None:
        """Close the underlying trajectory file handle."""
        self._trajectory = None


def _atom_types_are_ints(atom_types) -> bool:
    """Return whether atom types can be stored as an integer ASE array."""
    return all(isinstance(value, (int, np.integer)) for value in atom_types)


def _labels_to_tags(labels: list[int]) -> list[int]:
    """Map arbitrary tracked labels to small positive ASE tags."""
    ordered_labels = sorted(set(labels))
    mapping = {label: index + 1 for index, label in enumerate(ordered_labels)}
    return [mapping[label] for label in labels]


def _resolve_ase_symbols(payload: VisualizationPayload, num_atoms: int) -> list[str]:
    """Choose the ASE element symbols to use for display."""
    if payload.chemical_symbols is not None:
        return [str(symbol) for symbol in payload.chemical_symbols]
    return ["H"] * num_atoms

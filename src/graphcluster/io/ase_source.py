# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""ASE-backed trajectory source.

This module isolates all ASE-specific trajectory loading details. The rest of
project code should interact with project-owned ``Frame`` objects, not ASE
``Atoms`` objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
from ase.io import iread

from .frame import Frame


@dataclass
class ASETrajectorySource:
    """Read frames through ASE and convert them into project ``Frame`` objects."""

    trajectory_path: str
    start: int = 0
    stop: int | None = None
    stride: int = 1
    format: str | None = None
    source_config: dict | None = None

    def _ase_format(self) -> str | None:
        path = Path(self.trajectory_path)
        if self.format:
            return self.format
        suffix = path.suffix.lower()
        if suffix == ".bin":
            return "lammps-dump-binary"
        if suffix == ".xyz":
            return "xyz"
        if suffix == ".extxyz":
            return "extxyz"
        if suffix == ".traj":
            return "traj"
        return None

    def _ase_kwargs(self) -> dict:
        fmt = self._ase_format()
        kwargs: dict = {"index": slice(self.start, self.stop, self.stride)}
        if fmt is not None:
            kwargs["format"] = fmt
        if fmt == "lammps-dump-binary":
            kwargs["colnames"] = ["id", "type", "x", "y", "z"]
        return kwargs

    def _frame_from_atoms(self, index: int, atoms) -> Frame:
        atom_types, chemical_symbols = self._resolve_species_labels(atoms)
        metadata = self._build_frame_metadata(atoms)
        cell_origin = resolve_cell_origin(atoms, metadata)
        return Frame(
            index=index,
            positions=atoms.get_positions(),
            box=atoms.get_cell(),
            cell_origin=cell_origin,
            time=None,
            atom_types=atom_types,
            chemical_symbols=chemical_symbols,
            metadata=metadata,
        )

    def _resolve_species_labels(self, atoms) -> tuple[list[int | str] | None, list[str] | None]:
        """Resolve raw source labels and display symbols for one ASE frame."""
        if "type" in atoms.arrays:
            atom_types = atoms.arrays["type"].tolist()
            return atom_types, self._resolve_chemical_symbols(atom_types)

        chemical_symbols = [str(symbol) for symbol in atoms.get_chemical_symbols()]
        if not chemical_symbols:
            return None, None
        return list(chemical_symbols), list(chemical_symbols)

    def _build_frame_metadata(self, atoms) -> dict:
        """Collect source metadata that may be useful later in the pipeline."""
        metadata = {
                "source": "ase",
                "trajectory_path": self.trajectory_path,
                "num_atoms": len(atoms),
            }
        if atoms.info:
            metadata["ase_info"] = normalize_metadata_value(dict(atoms.info))
        return metadata

    def _resolve_chemical_symbols(
        self,
        atom_types: list[int | str] | None,
    ) -> list[str] | None:
        """Resolve raw atom types into chemical symbols when a mapping is provided."""
        if atom_types is None:
            return None
        source_config = self.source_config or {}
        raw_type_map = source_config.get("type_map")
        if not raw_type_map:
            return None

        type_map = {str(key): str(value) for key, value in raw_type_map.items()}
        chemical_symbols: list[str] = []
        for atom_type in atom_types:
            key = str(atom_type)
            if key not in type_map:
                raise ValueError(
                    "source.type_map was provided, but no chemical symbol mapping exists "
                    f"for raw atom type {atom_type!r}."
                )
            chemical_symbols.append(type_map[key])
        return chemical_symbols

    def __iter__(self) -> Iterator[Frame]:
        for selected_offset, atoms in enumerate(iread(self.trajectory_path, **self._ase_kwargs())):
            # Preserve absolute source frame index for progress logs and artifacts.
            index = self.start + selected_offset * self.stride
            yield self._frame_from_atoms(index, atoms)


def infer_ase_format(path: str) -> str | None:
    """Infer the ASE format for a path from its suffix."""
    suffix = Path(path).suffix.lower()
    if suffix == ".bin":
        return "lammps-dump-binary"
    if suffix == ".xyz":
        return "xyz"
    if suffix == ".extxyz":
        return "extxyz"
    if suffix == ".traj":
        return "traj"
    return None


def normalize_metadata_value(value):
    """Convert ASE metadata into plain Python containers when practical."""
    if isinstance(value, dict):
        return {str(key): normalize_metadata_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_metadata_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def resolve_cell_origin(atoms, metadata: dict) -> np.ndarray | None:
    """Resolve cell origin from ASE celldisp or recorded metadata fallback."""
    cell_origin = atoms.get_celldisp()
    if cell_origin is not None:
        cell_origin = np.asarray(cell_origin, dtype=float).reshape(-1)
        if np.any(cell_origin):
            return cell_origin

    ase_info = metadata.get("ase_info")
    if isinstance(ase_info, dict) and "cell_origin" in ase_info:
        fallback = np.asarray(ase_info["cell_origin"], dtype=float).reshape(-1)
        if fallback.size == 3:
            return fallback
    return cell_origin

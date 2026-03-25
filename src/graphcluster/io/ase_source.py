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
    input_config: dict | None = None

    def _ase_format(self) -> str | None:
        path = Path(self.trajectory_path)
        if self.format:
            return self.format
        if path.suffix == ".bin":
            return "lammps-dump-binary"
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
        atom_types = None
        if "type" in atoms.arrays:
            atom_types = atoms.arrays["type"].tolist()
        chemical_symbols = self._resolve_chemical_symbols(atom_types)
        cell_origin = atoms.get_celldisp()
        if cell_origin is not None:
            cell_origin = cell_origin.reshape(-1)
        return Frame(
            index=index,
            positions=atoms.get_positions(),
            box=atoms.get_cell(),
            cell_origin=cell_origin,
            time=None,
            atom_types=atom_types,
            chemical_symbols=chemical_symbols,
            metadata={
                "source": "ase",
                "trajectory_path": self.trajectory_path,
                "num_atoms": len(atoms),
            },
        )

    def _resolve_chemical_symbols(
        self,
        atom_types: list[int | str] | None,
    ) -> list[str] | None:
        """Resolve raw atom types into chemical symbols when a mapping is provided."""
        if atom_types is None:
            return None
        input_config = self.input_config or {}
        raw_type_map = input_config.get("type_map")
        if not raw_type_map:
            return None

        type_map = {str(key): str(value) for key, value in raw_type_map.items()}
        chemical_symbols: list[str] = []
        for atom_type in atom_types:
            key = str(atom_type)
            if key not in type_map:
                raise ValueError(
                    "input.type_map was provided, but no chemical symbol mapping exists "
                    f"for raw atom type {atom_type!r}."
                )
            chemical_symbols.append(type_map[key])
        return chemical_symbols

    def __iter__(self) -> Iterator[Frame]:
        for index, atoms in enumerate(
            iread(self.trajectory_path, **self._ase_kwargs()),
            start=self.start,
        ):
            yield self._frame_from_atoms(index, atoms)

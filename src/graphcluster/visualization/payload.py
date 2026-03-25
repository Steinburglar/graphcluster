# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Backend-independent visualization payloads.

In intuitive terms, this object is the handoff between project-owned data and a
viewer backend. It should contain only the information needed to draw what the
user wants to inspect, regardless of where that information came from.

Important design note:
- ``VisualizationPayload`` is the common visualization contract
- today it is built during the live pipeline from a ``FrameBundle``
- later it may also be built from a heavier saved artifact via a dedicated
  reader/adapter
- viewer backends should operate on payloads, not care which upstream source
  produced them

Who touches this:
- visualizers and viewer adapters
- future post-run artifact readers that need to construct view-ready data

Who this touches:
- frame bundles today
- possibly heavier persisted artifacts later
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from ..bundle.frame_bundle import FrameBundle


@dataclass
class VisualizationPayload:
    """Store the minimum information needed to visualize one frame.

    This object is intentionally a view model rather than a canonical scientific
    storage object. The same payload shape should be reusable whether it is
    derived from in-memory pipeline objects during debugging or from a future
    heavier post-run artifact.
    """

    frame_index: int
    positions: Any | None = None
    box: Any | None = None
    cell_origin: Any | None = None
    time: float | None = None
    atom_types: Sequence[str | int] | None = None
    chemical_symbols: Sequence[str] | None = None
    labels: list[int] = field(default_factory=list)
    local_labels: list[int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Check that per-atom arrays agree with the coordinate count."""
        num_atoms = len(self.positions) if self.positions is not None else 0
        if self.cell_origin is not None and len(self.cell_origin) != 3:
            raise ValueError(
                f"Expected a 3-vector cell origin, got {self.cell_origin} in frame "
                f"{self.frame_index}."
            )
        if len(self.labels) != num_atoms:
            raise ValueError(
                f"Expected one tracked label per atom, got {len(self.labels)} labels for "
                f"{num_atoms} atoms in frame {self.frame_index}."
            )
        if self.local_labels is not None and len(self.local_labels) != num_atoms:
            raise ValueError(
                f"Expected one local label per atom, got {len(self.local_labels)} labels for "
                f"{num_atoms} atoms in frame {self.frame_index}."
            )
        if self.atom_types is not None and len(self.atom_types) != num_atoms:
            raise ValueError(
                f"Expected one atom type per atom, got {len(self.atom_types)} atom types for "
                f"{num_atoms} atoms in frame {self.frame_index}."
            )
        if self.chemical_symbols is not None and len(self.chemical_symbols) != num_atoms:
            raise ValueError(
                "Expected one chemical symbol per atom, got "
                f"{len(self.chemical_symbols)} symbols for {num_atoms} atoms in frame "
                f"{self.frame_index}."
            )

    @classmethod
    def from_bundle(cls, bundle: FrameBundle) -> "VisualizationPayload":
        """Create a payload from a frame bundle.

        This is the current live/debug construction path. A future production
        workflow may add an additional construction path from a heavier saved
        artifact without changing the downstream viewer backends.
        """
        payload = cls(
            frame_index=bundle.frame.index,
            positions=bundle.frame.positions,
            box=bundle.frame.box,
            cell_origin=bundle.frame.cell_origin,
            time=bundle.frame.time,
            atom_types=bundle.frame.atom_types,
            chemical_symbols=bundle.frame.chemical_symbols,
            labels=list(bundle.partition.labels),
            local_labels=(
                list(bundle.local_partition.labels)
                if bundle.local_partition is not None
                else None
            ),
            metadata={
                "frame_metadata": dict(bundle.frame.metadata),
                "bundle_metadata": dict(bundle.metadata),
                "graph_metadata": dict(bundle.graph.metadata),
                "partition_kind": bundle.partition.kind,
            },
        )
        payload.validate()
        return payload

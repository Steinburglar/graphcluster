# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Project-owned frame object.

In intuitive terms, this is one timestep of MD data in a form the rest of the
pipeline can depend on without touching ASE or another external library
directly.

Who touches this:
- loader and adapter code
- graph building code
- bundling and visualization code

Who this touches:
- nobody directly; it is a simple data carrier
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(slots=True)
class Frame:
    """Carry the raw per-frame data the pipeline needs."""

    index: int
    positions: Any
    box: Any | None = None
    cell_origin: Any | None = None
    time: float | None = None
    atom_types: Sequence[str | int] | None = None
    chemical_symbols: Sequence[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

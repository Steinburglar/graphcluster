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

from .payload import VisualizationPayload


def view_with_ase(payload: VisualizationPayload) -> VisualizationPayload:
    """Placeholder ASE viewer hook that currently returns the payload unchanged."""
    return payload

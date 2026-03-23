# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Allegro-derived edge building hooks.

This module exists to keep future model-derived edge extraction clearly
separated from ordinary geometry-based graph construction.

Who touches this:
- people integrating Allegro or deeper LAMMPS edge data

Who this touches:
- the graph builder
"""

from __future__ import annotations

from ..io.frame import Frame


def build_allegro_adjacency(frame: Frame, graph_config: dict) -> object | None:
    """Return a placeholder adjacency representation for model-derived edges."""
    _ = graph_config
    return {"frame_index": frame.index, "source": "allegro"}

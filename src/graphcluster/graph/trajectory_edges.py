# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Trajectory-derived edge building hooks.

This module is where geometry-based rules will eventually live: cutoffs,
nearest-neighbor rules, or similar per-frame edge construction logic.

Who touches this:
- people implementing trajectory-driven graph construction

Who this touches:
- the graph builder
"""

from __future__ import annotations

from ..io.frame import Frame


def build_trajectory_adjacency(frame: Frame, graph_config: dict) -> object | None:
    """Return a placeholder adjacency representation for a frame."""
    _ = graph_config
    return {"frame_index": frame.index, "source": "trajectory"}

# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""I/O layer for trajectory and simulation data."""

from .frame import Frame
from .trajectory_reader import TrajectoryReader

__all__ = ["Frame", "TrajectoryReader"]

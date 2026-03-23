# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Top-level package for graphcluster.

This package is the project-owned API surface. Most internal development should
stay inside subpackages rather than adding broad exports here too early.
"""

from .runner import TrajectoryPartitionRunner

__all__ = ["TrajectoryPartitionRunner"]

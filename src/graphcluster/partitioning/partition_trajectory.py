# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Append-only in-memory partition trajectory store.

In intuitive terms, this is the small-run / test helper for keeping tracked
partitions in memory. The core runtime path is now streaming and should not be
understood as materializing one of these objects by default for large
trajectories.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .partition import Partition


@dataclass
class PartitionTrajectory:
    """Store partitions in frame order."""

    partitions: list[Partition] = field(default_factory=list)

    def append(self, partition: Partition) -> None:
        """Append a tracked partition."""
        self.partitions.append(partition)

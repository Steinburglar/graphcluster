# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Append-only partition trajectory store.

In intuitive terms, this module is where the project can keep a trajectory-level
log of tracked partition results without forcing the whole pipeline to keep all
state in memory.

Who touches this:
- the runner and trajectory-level analysis

Who this touches:
- partition objects
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

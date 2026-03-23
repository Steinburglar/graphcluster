# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Online frame-to-frame partition synchronization.

In intuitive terms, this class makes the current frame's cluster IDs line up
with the previous tracked frame. It is not responsible for trajectory-level
lifetime analysis.

Who touches this:
- the top-level runner
- people implementing temporal label synchronization

Who this touches:
- local partitions
- tracked partitions
- tracking state
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..partitioning.partition import Partition
from .tracking_state import TrackingState


@dataclass
class ClusterTracker:
    """Synchronize local partitions into tracked partitions."""

    config: dict
    state: TrackingState = field(default_factory=TrackingState)

    @classmethod
    def from_config(cls, config: dict) -> "ClusterTracker":
        """Build a tracker from config."""
        return cls(config=config)

    def previous_partition(self) -> Partition | None:
        """Return the previous tracked partition, if any."""
        return self.state.previous_tracked_partition

    def synchronize(self, local_partition: Partition) -> Partition:
        """Convert a local partition into a tracked partition.

        The scaffold preserves labels as-is and marks the partition as tracked.
        Real logic can later replace this with overlap-based synchronization.
        """
        tracked = Partition(
            frame_index=local_partition.frame_index,
            labels=list(local_partition.labels),
            kind="tracked",
            metadata={
                **local_partition.metadata,
                "synchronized_from_previous": self.state.previous_tracked_partition is not None,
            },
        )
        self.state.previous_tracked_partition = tracked
        return tracked

# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Online state carried by the cluster tracker.

In intuitive terms, this is the small amount of memory the tracker needs from
the previous step to keep labels consistent as the main loop moves forward.

Who touches this:
- the cluster tracker

Who this touches:
- tracked partitions
"""

from __future__ import annotations

from dataclasses import dataclass

from ..partitioning.partition import Partition


@dataclass
class TrackingState:
    """Hold the minimal previous tracked state for online synchronization."""

    previous_tracked_partition: Partition | None = None

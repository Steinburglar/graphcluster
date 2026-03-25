# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Online frame-to-frame tracking layer."""

from .cluster_tracker import ClusterTracker
from .metadata import ClusterMatchRecord, TrackingFrameMetadata
from .tracking_state import TrackingState

__all__ = [
    "ClusterMatchRecord",
    "ClusterTracker",
    "TrackingFrameMetadata",
    "TrackingState",
]

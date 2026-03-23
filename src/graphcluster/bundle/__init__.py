# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Per-frame and trajectory-level bundle objects."""

from .bundle_trajectory import BundleTrajectory
from .frame_bundle import FrameBundle

__all__ = ["BundleTrajectory", "FrameBundle"]

# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Trajectory-level store for per-frame bundles.

In intuitive terms, this is an optional place to keep emitted timestep results
in order when the caller wants a processed trajectory view.

Who touches this:
- the runner
- trajectory-level analysis or export paths

Who this touches:
- frame bundle objects
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .frame_bundle import FrameBundle


@dataclass
class BundleTrajectory:
    """Store bundles in frame order."""

    bundles: list[FrameBundle] = field(default_factory=list)

    def append(self, bundle: FrameBundle) -> None:
        """Append a bundle."""
        self.bundles.append(bundle)

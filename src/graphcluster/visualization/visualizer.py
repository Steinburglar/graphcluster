# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Project-level visualization coordinator.

In intuitive terms, this is the place where frame bundles are converted into a
backend-independent payload and optionally passed to a viewer backend.

Who touches this:
- the runner
- people wiring in actual viewer backends

Who this touches:
- frame bundles
- visualization payloads
- backend adapters such as ASE viewers
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..bundle.frame_bundle import FrameBundle
from .payload import VisualizationPayload


@dataclass
class Visualizer:
    """Consume frame bundles and prepare them for visualization."""

    consumed_payloads: list[VisualizationPayload] = field(default_factory=list)

    def consume(self, bundle: FrameBundle) -> VisualizationPayload:
        """Convert a bundle into a visualization payload."""
        payload = VisualizationPayload.from_bundle(bundle)
        self.consumed_payloads.append(payload)
        return payload

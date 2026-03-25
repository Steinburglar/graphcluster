# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Project-level visualization coordinator.

In intuitive terms, this is the place where project-owned data is turned into a
backend-independent visualization payload and optionally passed to a viewer
backend.

Important design note:
- today the visualizer constructs payloads during the live pipeline from
  ``FrameBundle`` objects, which is useful for debugging
- later, a separate post-run artifact reader may construct the same payload
  shape from a heavier saved file
- viewer backends should stay reusable across both paths

Who touches this:
- the runner
- people wiring in actual viewer backends
- future post-run visualization loaders/adapters

Who this touches:
- frame bundles today
- visualization payloads
- backend adapters such as ASE viewers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..bundle.frame_bundle import FrameBundle
from .ase_viewer import AseTrajectoryWriter, view_with_ase
from .payload import VisualizationPayload


@dataclass
class Visualizer:
    """Consume live pipeline objects and prepare them for visualization.

    This class currently owns the in-run construction path from ``FrameBundle``
    to ``VisualizationPayload``. That should be understood as one payload
    source, not the only payload source the project may ever support.
    """

    enabled: bool = False
    backend: str = "none"
    mode: str = "collect"
    output_path: Path | None = None
    every_n: int = 1
    consumed_payloads: list[VisualizationPayload] = field(default_factory=list)
    written_artifacts: list[Path] = field(default_factory=list)
    _writer: AseTrajectoryWriter | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_config(cls, config: dict) -> "Visualizer":
        """Build a visualizer from config."""
        visualization_config = config.get("visualization", {})
        enabled = visualization_config.get("enabled", False)
        backend = visualization_config.get("backend", "none")
        mode = visualization_config.get("mode", "collect")
        every_n = max(1, int(visualization_config.get("every_n", 1)))
        output_path = _resolve_output_path(config, visualization_config)
        return cls(
            enabled=enabled,
            backend=backend,
            mode=mode,
            output_path=output_path,
            every_n=every_n,
        )

    def consume(self, bundle: FrameBundle) -> VisualizationPayload:
        """Convert a bundle into a visualization payload."""
        payload = VisualizationPayload.from_bundle(bundle)
        self.consumed_payloads.append(payload)
        if not self.enabled:
            return payload
        if (len(self.consumed_payloads) - 1) % self.every_n != 0:
            return payload
        if self.backend == "ase" and self.mode == "traj":
            writer = self._ensure_writer()
            artifact_path = writer.write_payload(payload)
            if artifact_path not in self.written_artifacts:
                self.written_artifacts.append(artifact_path)
        elif self.backend == "ase" and self.mode == "view":
            view_with_ase(payload)
        return payload

    def finalize(self) -> None:
        """Flush and close any backend-specific visualization resources."""
        if self._writer is not None:
            self._writer.close()

    def _ensure_writer(self) -> AseTrajectoryWriter:
        """Create the ASE trajectory writer lazily."""
        if self.output_path is None:
            raise ValueError(
                "ASE trajectory visualization requires visualization.output_path "
                "or output.directory to be set."
            )
        if self._writer is None:
            self._writer = AseTrajectoryWriter(self.output_path)
        return self._writer


def _resolve_output_path(config: dict, visualization_config: dict) -> Path | None:
    """Resolve the artifact path for visualization outputs."""
    explicit_path = visualization_config.get("output_path")
    if explicit_path:
        return Path(explicit_path)

    output_config = config.get("output", {})
    output_directory = output_config.get("directory")
    if output_directory:
        return Path(output_directory) / "visualization.extxyz"

    if visualization_config.get("enabled", False):
        return Path("outputs") / "visualization.extxyz"
    return None

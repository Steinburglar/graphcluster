# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Streaming visualization artifact recording.

In intuitive terms, this class consumes transient ``FrameBundle`` objects during
the main pipeline and records a viewer-friendly artifact without retaining the
whole trajectory in memory. A future post-run reader may still reconstruct the
same payload shape from saved data, but the core runtime model is streaming.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..bundle.frame_bundle import FrameBundle
from .ase_viewer import AseTrajectoryWriter, view_with_ase
from .payload import VisualizationPayload


@dataclass
class Visualizer:
    """Consume transient frame bundles and record visualization artifacts."""

    enabled: bool = False
    backend: str = "none"
    mode: str = "collect"
    output_path: Path | None = None
    every_n: int = 1
    write_batch_size: int = 1
    retain_payloads: bool = False
    consumed_payloads: list[VisualizationPayload] = field(default_factory=list)
    written_artifacts: list[Path] = field(default_factory=list)
    _pending_payloads: list[VisualizationPayload] = field(default_factory=list, init=False, repr=False)
    _frames_seen: int = field(default=0, init=False, repr=False)
    _writer: AseTrajectoryWriter | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_config(cls, config: dict) -> "Visualizer":
        """Build a visualizer from config."""
        artifacts_config = config.get("artifacts", {})
        visualization_config = artifacts_config.get("visualization", {})
        enabled = visualization_config.get("enabled", False)
        backend = visualization_config.get("backend", "none")
        mode = visualization_config.get("mode", "collect")
        every_n = max(1, int(visualization_config.get("every_n", 1)))
        write_batch_size = max(1, int(visualization_config.get("write_batch_size", 1)))
        output_path = _resolve_output_path(artifacts_config, visualization_config)
        return cls(
            enabled=enabled,
            backend=backend,
            mode=mode,
            output_path=output_path,
            every_n=every_n,
            write_batch_size=write_batch_size,
            retain_payloads=(mode == "collect"),
        )

    def consume(self, bundle: FrameBundle) -> VisualizationPayload:
        """Convert a bundle into a visualization payload and stream it onward."""
        payload = VisualizationPayload.from_bundle(bundle)
        if self.retain_payloads:
            self.consumed_payloads.append(payload)
        if not self.enabled:
            return payload
        if self._frames_seen % self.every_n != 0:
            self._frames_seen += 1
            return payload
        if self.backend == "ase" and self.mode == "traj":
            self._pending_payloads.append(payload)
            if len(self._pending_payloads) >= self.write_batch_size:
                self._flush_pending_payloads()
        elif self.backend == "ase" and self.mode == "view":
            view_with_ase(payload)
        self._frames_seen += 1
        return payload

    def finalize(self) -> None:
        """Flush and close any backend-specific visualization resources."""
        self._flush_pending_payloads()
        if self._writer is not None:
            self._writer.close()

    def _ensure_writer(self) -> AseTrajectoryWriter:
        """Create the ASE trajectory writer lazily."""
        if self.output_path is None:
            raise ValueError(
                "ASE trajectory visualization requires visualization.output_path "
                "or artifacts.directory to be set."
            )
        if self._writer is None:
            self._writer = AseTrajectoryWriter(self.output_path)
        return self._writer

    def _flush_pending_payloads(self) -> None:
        """Write buffered payloads to the visualization artifact."""
        if not self._pending_payloads:
            return
        writer = self._ensure_writer()
        artifact_path = writer.write_payloads(self._pending_payloads)
        if artifact_path not in self.written_artifacts:
            self.written_artifacts.append(artifact_path)
        self._pending_payloads.clear()


def _resolve_output_path(artifacts_config: dict, visualization_config: dict) -> Path | None:
    """Resolve the artifact path for visualization outputs."""
    explicit_path = visualization_config.get("output_path")
    if explicit_path:
        return Path(explicit_path)

    output_directory = artifacts_config.get("directory")
    if output_directory:
        return Path(output_directory) / "visualization.extxyz"

    if visualization_config.get("enabled", False):
        return Path("outputs") / "visualization.extxyz"
    return None

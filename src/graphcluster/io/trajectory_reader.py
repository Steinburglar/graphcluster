# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Backend-agnostic trajectory reader facade.

In intuitive terms, this is the public reader object the rest of the project
should use. It selects a backend-specific source, but its iteration logic does
not depend on ASE, MDAnalysis, or any other concrete backend directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from .ase_source import ASETrajectorySource
from .frame import Frame


def infer_trajectory_format(path: str, explicit_format: str | None = None) -> str | None:
    """Infer the trajectory format when the caller did not specify one."""
    if explicit_format:
        return explicit_format
    suffix = Path(path).suffix.lower()
    if suffix == ".bin":
        return "lammps-dump-binary"
    if suffix == ".xyz":
        return "xyz"
    if suffix == ".extxyz":
        return "extxyz"
    if suffix == ".traj":
        return "traj"
    return None


@dataclass
class TrajectoryReader:
    """Public facade for streaming frames from different backends."""

    trajectory_path: str
    start: int = 0
    stop: int | None = None
    stride: int = 1
    format: str | None = None
    backend: str | None = None
    input_config: dict | None = None
    _source: Iterable[Frame] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.backend = self.backend or "ase"
        self.format = infer_trajectory_format(self.trajectory_path, self.format)
        self._source = self._build_source()

    def _build_source(self) -> Iterable[Frame]:
        """Build the backend-specific source used by this reader."""
        if self.backend == "ase":
            return ASETrajectorySource(
                trajectory_path=self.trajectory_path,
                start=self.start,
                stop=self.stop,
                stride=self.stride,
                format=self.format,
                input_config=self.input_config,
            )
        raise ValueError(f"Unsupported trajectory backend: {self.backend}")

    @classmethod
    def from_config(cls, config: dict) -> "TrajectoryReader":
        """Build a reader from config."""
        frames = config.get("frames", {})
        input_config = config.get("input", {})
        trajectory_path = input_config.get("trajectory")
        if not trajectory_path:
            raise ValueError("TrajectoryReader requires input.trajectory in the config.")
        return cls(
            trajectory_path=str(trajectory_path),
            start=frames.get("start", 0),
            stop=frames.get("stop"),
            stride=frames.get("stride", 1),
            format=input_config.get("format"),
            backend=input_config.get("backend"),
            input_config=input_config,
        )

    @property
    def source(self) -> Iterable[Frame]:
        """Expose the backend-specific source for testing and debugging."""
        return self._source

    def __iter__(self) -> Iterator[Frame]:
        yield from self._source

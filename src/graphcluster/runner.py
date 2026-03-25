# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Top-level coordinator for the streaming partitioning pipeline.

In intuitive terms, this file owns the forward pass over the trajectory while
keeping the in-memory working set bounded:

1. load one frame
2. build one graph
3. partition and track one frame
4. package a transient frame bundle
5. hand that bundle to artifact writers
6. discard the transient bundle unless collection was explicitly requested

This streaming model is the core runtime path for both small debug runs and
large MD trajectories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analysis.lifecycle_recorder import ClusterLifecycleRecorder
from .bundle.frame_bundle import FrameBundle
from .graph.graph_builder import GraphBuilder
from .io.trajectory_reader import TrajectoryReader
from .partitioning.partitioner import Partitioner
from .tracking.cluster_tracker import ClusterTracker
from .utils.config import load_config
from .visualization.visualizer import Visualizer


@dataclass
class TrajectoryRunResult:
    """Summarize the outputs of one trajectory-processing run."""

    frames_processed: int = 0
    visualization_artifacts: list[Path] = field(default_factory=list)
    analysis_artifact: Path | None = None
    collected_bundles: list[FrameBundle] = field(default_factory=list)


@dataclass
class TrajectoryPartitionRunner:
    """Coordinate one full partitioning pass over a trajectory.

    This class is the main owner of the runtime loop. It should stay focused on
    orchestration rather than doing parsing, graph math, or analysis itself.
    """

    config: dict
    reader: TrajectoryReader
    graph_builder: GraphBuilder
    partitioner: Partitioner
    tracker: ClusterTracker
    lifecycle_recorder: ClusterLifecycleRecorder
    visualizer: Visualizer = field(default_factory=Visualizer)

    @classmethod
    def from_config_path(cls, config_path: str | Path) -> "TrajectoryPartitionRunner":
        """Create a runner from a config file path."""
        config = load_config(config_path)
        return cls(
            config=config,
            reader=TrajectoryReader.from_config(config),
            graph_builder=GraphBuilder.from_config(config),
            partitioner=Partitioner.from_config(config),
            tracker=ClusterTracker.from_config(config),
            lifecycle_recorder=ClusterLifecycleRecorder.from_config(config),
            visualizer=Visualizer.from_config(config),
        )

    def run(self, *, collect_bundles: bool = False) -> TrajectoryRunResult:
        """Run the streaming pipeline and return artifact locations and counts."""
        collected_bundles: list[FrameBundle] = []
        frames_processed = 0
        try:
            for frame in self.reader:
                graph = self.graph_builder.build(frame)
                local_partition = self.partitioner.partition_local(
                    graph,
                    previous_tracked_partition=self.tracker.previous_partition(),
                )
                tracked_partition = self.tracker.synchronize(local_partition)
                bundle = FrameBundle(
                    frame=frame,
                    graph=graph,
                    partition=tracked_partition,
                    local_partition=local_partition,
                )
                if collect_bundles:
                    collected_bundles.append(bundle)
                self.lifecycle_recorder.consume(bundle)
                self.visualizer.consume(bundle)
                frames_processed += 1
        finally:
            analysis_artifact = self.lifecycle_recorder.finalize()
            self.visualizer.finalize()
        return TrajectoryRunResult(
            frames_processed=frames_processed,
            visualization_artifacts=list(self.visualizer.written_artifacts),
            analysis_artifact=analysis_artifact,
            collected_bundles=collected_bundles,
        )

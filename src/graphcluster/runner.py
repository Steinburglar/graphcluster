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
from typing import Callable

from .allegro_annotation import prepare_allegro_input
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
    annotation_artifact: Path | None = None
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

    def run(
        self,
        *,
        collect_bundles: bool = False,
        progress: bool = False,
        progress_every: int = 1,
        progress_callback: Callable[[str], None] | None = None,
    ) -> TrajectoryRunResult:
        """Run the streaming pipeline and return artifact locations and counts."""
        collected_bundles: list[FrameBundle] = []
        frames_processed = 0
        emit_progress = progress_callback or print
        effective_progress_every = max(int(progress_every), 1)

        if progress:
            emit_progress(
                "Starting graphcluster run: "
                f"trajectory={self.reader.trajectory_path}, "
                f"format={self.reader.format or 'auto'}, "
                f"backend={self.reader.backend}, "
                f"collect_bundles={collect_bundles}"
            )
        preparation = prepare_allegro_input(
            self.config,
            progress_callback=emit_progress if progress else None,
        )
        if preparation.annotation_performed:
            self._switch_effective_trajectory(preparation.effective_trajectory_path)
            if progress:
                emit_progress(
                    "Using Allegro-annotated trajectory: "
                    f"{preparation.effective_trajectory_path}"
                )
        if preparation.stop_after_annotation:
            if progress:
                emit_progress(
                    "Stopping after Allegro edge annotation as requested by "
                    "allegro.mode=annotate_only."
                )
            return TrajectoryRunResult(
                frames_processed=0,
                visualization_artifacts=[],
                analysis_artifact=None,
                annotation_artifact=preparation.annotation_artifact,
                collected_bundles=[],
            )
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
                if progress and (
                    frames_processed == 1 or frames_processed % effective_progress_every == 0
                ):
                    emit_progress(
                        "Processed frame "
                        f"{frame.index} ({frames_processed} total): "
                        f"nodes={graph.metadata.get('num_nodes')}, "
                        f"edges={graph.metadata.get('num_edges', 'n/a')}, "
                        f"clusters={len(set(tracked_partition.labels))}"
                    )
        finally:
            analysis_artifact = self.lifecycle_recorder.finalize()
            self.visualizer.finalize()
        if progress:
            visualization_paths = [str(path) for path in self.visualizer.written_artifacts]
            emit_progress(
                "Finished graphcluster run: "
                f"frames_processed={frames_processed}, "
                f"visualization_artifacts={visualization_paths}, "
                f"analysis_artifact={analysis_artifact}"
            )
        return TrajectoryRunResult(
            frames_processed=frames_processed,
            visualization_artifacts=list(self.visualizer.written_artifacts),
            analysis_artifact=analysis_artifact,
            annotation_artifact=preparation.annotation_artifact,
            collected_bundles=collected_bundles,
        )

    def _switch_effective_trajectory(self, trajectory_path: str) -> None:
        """Rebuild the reader around a new effective input trajectory path."""
        previous_path = self.reader.trajectory_path
        previous_format = self.reader.format
        self.config.setdefault("input", {})["trajectory"] = str(trajectory_path)
        self.config["input"]["cell_origin_reference_trajectory"] = str(previous_path)
        if previous_format is not None:
            self.config["input"]["cell_origin_reference_format"] = previous_format
        self.reader = TrajectoryReader.from_config(self.config)

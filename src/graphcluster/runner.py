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
from time import perf_counter
from typing import Callable

from .allegro_annotation import prepare_allegro_input
from .analysis.lifecycle_recorder import ClusterLifecycleRecorder
from .bundle.frame_bundle import FrameBundle
from .graph.graph_builder import GraphBuilder
from .io.trajectory_reader import TrajectoryReader, infer_trajectory_format
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
    startup_timings: dict[str, float] = field(default_factory=dict)
    run_timings: dict[str, float] = field(default_factory=dict)


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
    startup_timings: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_config_path(cls, config_path: str | Path) -> "TrajectoryPartitionRunner":
        """Create a runner from a config file path."""
        startup_started = perf_counter()
        startup_timings: dict[str, float] = {}

        phase_started = perf_counter()
        config = load_config(config_path)
        startup_timings["load_config"] = perf_counter() - phase_started

        phase_started = perf_counter()
        reader = TrajectoryReader.from_config(config)
        startup_timings["reader_init"] = perf_counter() - phase_started

        phase_started = perf_counter()
        graph_builder = GraphBuilder.from_config(config)
        startup_timings["graph_builder_init"] = perf_counter() - phase_started

        phase_started = perf_counter()
        partitioner = Partitioner.from_config(config)
        startup_timings["partitioner_init"] = perf_counter() - phase_started

        phase_started = perf_counter()
        tracker = ClusterTracker.from_config(config)
        startup_timings["tracker_init"] = perf_counter() - phase_started

        phase_started = perf_counter()
        lifecycle_recorder = ClusterLifecycleRecorder.from_config(config)
        startup_timings["lifecycle_recorder_init"] = perf_counter() - phase_started

        phase_started = perf_counter()
        visualizer = Visualizer.from_config(config)
        startup_timings["visualizer_init"] = perf_counter() - phase_started
        startup_timings["startup_total"] = perf_counter() - startup_started

        return cls(
            config=config,
            reader=reader,
            graph_builder=graph_builder,
            partitioner=partitioner,
            tracker=tracker,
            lifecycle_recorder=lifecycle_recorder,
            visualizer=visualizer,
            startup_timings=startup_timings,
        )

    def run(
        self,
        *,
        collect_bundles: bool = False,
        progress: bool = False,
        progress_every: int = 1,
        progress_callback: Callable[[str], None] | None = None,
        profile: bool | None = None,
    ) -> TrajectoryRunResult:
        """Run the streaming pipeline and return artifact locations and counts."""
        collected_bundles: list[FrameBundle] = []
        frames_processed = 0
        emit_progress = progress_callback or print
        effective_progress_every = max(int(progress_every), 1)
        profiling_enabled = self._profiling_enabled(profile)
        run_started = perf_counter()
        run_timings = {
            "prepare_allegro_input": 0.0,
            "switch_effective_reader": 0.0,
            "read_frame": 0.0,
            "graph_build": 0.0,
            "partition_local": 0.0,
            "track_partition": 0.0,
            "analysis_consume": 0.0,
            "visualization_consume": 0.0,
            "finalize_analysis": 0.0,
            "finalize_visualization": 0.0,
        }

        if progress:
            emit_progress(
                "Starting graphcluster run: "
                f"trajectory={self.reader.trajectory_path}, "
                f"format={self.reader.format or 'auto'}, "
                f"backend={self.reader.backend}, "
                f"collect_bundles={collect_bundles}"
            )
            if profiling_enabled:
                emit_progress(
                    "Profiling startup: "
                    f"{format_timing_summary(self.startup_timings, order=STARTUP_TIMING_ORDER)}"
                )

        phase_started = perf_counter()
        preparation = prepare_allegro_input(
            self.config,
            progress_callback=emit_progress if progress else None,
        )
        run_timings["prepare_allegro_input"] += perf_counter() - phase_started
        if preparation.annotation_performed:
            phase_started = perf_counter()
            self._switch_effective_trajectory(preparation.effective_trajectory_path)
            run_timings["switch_effective_reader"] += perf_counter() - phase_started
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
                if profiling_enabled:
                    completed_run_timings = dict(run_timings)
                    completed_run_timings["run_total"] = perf_counter() - run_started
                    emit_progress(
                        "Profiling runtime: "
                        f"{format_timing_summary(completed_run_timings, order=RUN_TIMING_ORDER)}"
                    )
            return TrajectoryRunResult(
                frames_processed=0,
                visualization_artifacts=[],
                analysis_artifact=None,
                annotation_artifact=preparation.annotation_artifact,
                collected_bundles=[],
                startup_timings=dict(self.startup_timings),
                run_timings=completed_run_timings if profiling_enabled else dict(run_timings),
            )
        analysis_artifact: Path | None = None
        try:
            frame_iterator = iter(self.reader)
            while True:
                phase_started = perf_counter()
                try:
                    frame = next(frame_iterator)
                except StopIteration:
                    break
                run_timings["read_frame"] += perf_counter() - phase_started

                phase_started = perf_counter()
                graph = self.graph_builder.build(frame)
                run_timings["graph_build"] += perf_counter() - phase_started

                phase_started = perf_counter()
                local_partition = self.partitioner.partition_local(
                    graph,
                    previous_tracked_partition=self.tracker.previous_partition(),
                )
                run_timings["partition_local"] += perf_counter() - phase_started

                phase_started = perf_counter()
                tracked_partition = self.tracker.synchronize(local_partition)
                run_timings["track_partition"] += perf_counter() - phase_started
                bundle = FrameBundle(
                    frame=frame,
                    graph=graph,
                    partition=tracked_partition,
                    local_partition=local_partition,
                )
                if collect_bundles:
                    collected_bundles.append(bundle)
                phase_started = perf_counter()
                self.lifecycle_recorder.consume(bundle)
                run_timings["analysis_consume"] += perf_counter() - phase_started
                phase_started = perf_counter()
                self.visualizer.consume(bundle)
                run_timings["visualization_consume"] += perf_counter() - phase_started
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
            phase_started = perf_counter()
            analysis_artifact = self.lifecycle_recorder.finalize()
            run_timings["finalize_analysis"] += perf_counter() - phase_started
            phase_started = perf_counter()
            self.visualizer.finalize()
            run_timings["finalize_visualization"] += perf_counter() - phase_started
        completed_run_timings = dict(run_timings)
        completed_run_timings["run_total"] = perf_counter() - run_started
        if progress:
            visualization_paths = [str(path) for path in self.visualizer.written_artifacts]
            emit_progress(
                "Finished graphcluster run: "
                f"frames_processed={frames_processed}, "
                f"visualization_artifacts={visualization_paths}, "
                f"analysis_artifact={analysis_artifact}"
            )
            if profiling_enabled:
                emit_progress(
                    "Profiling runtime: "
                    f"{format_timing_summary(completed_run_timings, order=RUN_TIMING_ORDER)}"
                )
        return TrajectoryRunResult(
            frames_processed=frames_processed,
            visualization_artifacts=list(self.visualizer.written_artifacts),
            analysis_artifact=analysis_artifact,
            annotation_artifact=preparation.annotation_artifact,
            collected_bundles=collected_bundles,
            startup_timings=dict(self.startup_timings),
            run_timings=completed_run_timings,
        )

    def _switch_effective_trajectory(self, trajectory_path: str) -> None:
        """Rebuild the reader around a derived runtime trajectory artifact."""
        source_input = dict(self.config.get("input", {}))
        allegro_output_format = self.config.get("allegro", {}).get("output_format")
        source_input["cell_origin_reference_trajectory"] = self.reader.trajectory_path
        if self.reader.format is not None:
            source_input["cell_origin_reference_format"] = self.reader.format
        effective_format = infer_trajectory_format(
            str(trajectory_path),
            explicit_format=allegro_output_format,
        )
        self.reader = TrajectoryReader(
            trajectory_path=str(trajectory_path),
            start=self.reader.start,
            stop=self.reader.stop,
            stride=self.reader.stride,
            format=effective_format,
            backend=self.reader.backend,
            input_config=source_input,
        )

    def _profiling_enabled(self, profile: bool | None) -> bool:
        """Resolve whether profiling output should be enabled for this run."""
        if profile is not None:
            return bool(profile)
        profiling_config = self.config.get("profiling", {})
        return bool(profiling_config.get("enabled", False))


STARTUP_TIMING_ORDER = (
    "startup_total",
    "load_config",
    "reader_init",
    "graph_builder_init",
    "partitioner_init",
    "tracker_init",
    "lifecycle_recorder_init",
    "visualizer_init",
)

RUN_TIMING_ORDER = (
    "run_total",
    "prepare_allegro_input",
    "switch_effective_reader",
    "read_frame",
    "graph_build",
    "partition_local",
    "track_partition",
    "analysis_consume",
    "visualization_consume",
    "finalize_analysis",
    "finalize_visualization",
)


def format_timing_summary(
    timings: dict[str, float],
    *,
    order: tuple[str, ...],
) -> str:
    """Format a stable timing summary for progress output."""
    parts: list[str] = []
    for key in order:
        if key not in timings:
            continue
        parts.append(f"{key}={timings[key]:.3f}s")
    for key in sorted(timings):
        if key in order:
            continue
        parts.append(f"{key}={timings[key]:.3f}s")
    return ", ".join(parts)

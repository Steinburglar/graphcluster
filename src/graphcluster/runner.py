# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Top-level coordinator for the trajectory partitioning pipeline.

In intuitive terms, this file plays the role that a trainer loop would play in
an ML project. It owns the forward pass over the trajectory:

1. load a frame
2. build a graph
3. partition it
4. synchronize labels against the previous tracked frame
5. package the result into a frame bundle
6. hand the bundle to visualization or export

Who touches this:
- people changing overall pipeline ordering or orchestration

Who this touches:
- I/O, graph building, partitioning, tracking, bundling, and visualization
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .bundle.frame_bundle import FrameBundle
from .graph.graph_builder import GraphBuilder
from .io.trajectory_reader import TrajectoryReader
from .partitioning.partitioner import Partitioner
from .tracking.cluster_tracker import ClusterTracker
from .utils.config import load_config
from .visualization.visualizer import Visualizer


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
            visualizer=Visualizer.from_config(config),
        )

    def run(self) -> list[FrameBundle]:
        """Run the scaffold pipeline and return emitted bundles."""
        bundles: list[FrameBundle] = []
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
                bundles.append(bundle)
                self.visualizer.consume(bundle)
        finally:
            self.visualizer.finalize()
        return bundles

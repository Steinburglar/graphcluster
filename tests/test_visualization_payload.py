# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for visualization payload creation.

These tests protect the backend-independent visualization handoff object.
"""

from graphcluster.bundle.frame_bundle import FrameBundle
from graphcluster.graph.sparse_graph import SparseWeightedGraph
from graphcluster.io.frame import Frame
from graphcluster.partitioning.partition import Partition
from graphcluster.visualization.payload import VisualizationPayload


def test_visualization_payload_can_be_built_from_bundle() -> None:
    bundle = FrameBundle(
        frame=Frame(index=5, positions=[[0.0, 0.0, 0.0]]),
        graph=SparseWeightedGraph(frame_index=5),
        partition=Partition(frame_index=5, labels=[2], kind="tracked"),
    )
    payload = VisualizationPayload.from_bundle(bundle)
    assert payload.frame_index == 5
    assert payload.labels == [2]

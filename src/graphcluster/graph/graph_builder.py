# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Build per-frame sparse weighted graphs.

In intuitive terms, this is the translation step from raw frame data to the
graph object the partitioner understands.

Who touches this:
- people deciding how frames become weighted graphs
- the top-level runner

Who this touches:
- frame objects
- graph containers
- edge-construction helpers
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy import sparse

from ..io.frame import Frame
from .allegro_edges import build_allegro_adjacency
from .sparse_graph import SparseWeightedGraph
from .trajectory_edges import (
    build_trajectory_adjacency,
    resolve_cutoff_spec,
    resolve_kernel_config,
)


@dataclass
class GraphBuilder:
    """Assemble a sparse weighted graph from a frame."""

    config: dict

    @classmethod
    def from_config(cls, config: dict) -> "GraphBuilder":
        """Build a graph builder from config."""
        return cls(config=config)

    def build(self, frame: Frame) -> SparseWeightedGraph:
        """Create the canonical graph object for a frame."""
        edges_config = self.config.get("edges", {})
        source_config = self.config.get("source", {})
        edge_kind = str(edges_config.get("kind", "binary"))
        uses_allegro_edges = edge_kind == "allegro"
        if uses_allegro_edges:
            adjacency = build_allegro_adjacency(frame, edges_config)
        else:
            adjacency = build_trajectory_adjacency(
                frame,
                edges_config,
                source_config=source_config,
            )
        num_nodes = len(frame.positions)
        metadata = {
            "source": "allegro" if uses_allegro_edges else "trajectory",
            "edge_kind": edge_kind,
            "num_nodes": num_nodes,
        }
        if sparse.issparse(adjacency):
            metadata["num_edges"] = int(
                adjacency.nnz // (1 if edges_config.get("directed", False) else 2)
            )
        if not uses_allegro_edges:
            cutoff, cutoff_source = resolve_cutoff_spec(
                frame,
                edges_config,
                source_config=source_config,
            )
            metadata["cutoff"] = cutoff
            metadata["cutoff_source"] = cutoff_source
            metadata["kernel"] = resolve_kernel_config(edges_config)[0]
        return SparseWeightedGraph(
            frame_index=frame.index,
            adjacency=adjacency,
            directed=edges_config.get("directed", False),
            metadata=metadata,
        )

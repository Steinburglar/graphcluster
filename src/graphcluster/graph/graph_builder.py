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
        if "edges" in config:
            return cls(config=config)
        graph_config = dict(config.get("graph") or {})
        if not graph_config:
            return cls(config=config)
        normalized = dict(config)
        edges_config = dict(graph_config)
        source = edges_config.pop("source", None)
        if source == "allegro":
            edges_config["kind"] = "allegro"
        elif source is not None:
            edges_config["kind"] = str(source)
        if "kernel" in edges_config:
            kernel = edges_config.pop("kernel")
            if isinstance(kernel, dict):
                edges_config.update(kernel)
                edges_config["kind"] = str(kernel.get("name", "distance"))
                edges_config.pop("name", None)
            else:
                edges_config["kind"] = kernel
        normalized["edges"] = edges_config
        if "input" in normalized and "source" not in normalized:
            source_config = dict(normalized["input"])
            source_config["_cutoff_source_prefix"] = "input"
            normalized["source"] = source_config
        return cls(config=normalized)

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
        else:
            if "allegro_edge_scale" in edges_config:
                metadata["allegro_edge_scale"] = float(edges_config["allegro_edge_scale"])
            if edges_config.get("allegro_scaling"):
                metadata["allegro_scaling"] = dict(edges_config["allegro_scaling"])
        return SparseWeightedGraph(
            frame_index=frame.index,
            adjacency=adjacency,
            directed=edges_config.get("directed", False),
            metadata=metadata,
        )

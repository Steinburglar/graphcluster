# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Algorithm selection for local graph partitioning.

The current implementation keeps the partitioner small while supporting both a
placeholder scaffold algorithm and a real Leiden-based clustering path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import igraph
import leidenalg
from scipy import sparse

from ..graph.sparse_graph import SparseWeightedGraph


class PartitionAlgorithm(Protocol):
    """Protocol for one-frame clustering algorithms."""

    def run(
        self,
        graph: SparseWeightedGraph,
        initial_labels: list[int] | None = None,
    ) -> list[int]:
        """Return local labels for a graph."""


@dataclass
class PlaceholderPartitionAlgorithm:
    """Very small stand-in algorithm used while the scaffold is being built."""

    def run(
        self,
        graph: SparseWeightedGraph,
        initial_labels: list[int] | None = None,
    ) -> list[int]:
        _ = initial_labels
        size = graph.metadata.get("num_nodes", 0)
        return [0 for _ in range(size)]


@dataclass
class LeidenPartitionAlgorithm:
    """Leiden-based local graph partitioner."""

    config: dict

    def run(
        self,
        graph: SparseWeightedGraph,
        initial_labels: list[int] | None = None,
    ) -> list[int]:
        """Run Leiden on a sparse weighted graph."""
        adjacency = graph.adjacency
        if not sparse.issparse(adjacency):
            raise TypeError(
                "Leiden partitioning requires SparseWeightedGraph.adjacency to be a "
                "scipy sparse matrix."
            )

        num_nodes = adjacency.shape[0]
        if num_nodes == 0:
            return []
        if adjacency.nnz == 0:
            return list(range(num_nodes))

        igraph_graph, weights = scipy_sparse_to_igraph(adjacency, directed=graph.directed)
        partition_type = resolve_partition_type(self.config)
        initial_membership = compress_membership(initial_labels, num_nodes)
        partition_kwargs = build_leiden_partition_kwargs(self.config)
        membership = run_leiden_partition(
            igraph_graph=igraph_graph,
            partition_type=partition_type,
            weights=weights,
            initial_membership=initial_membership,
            partition_kwargs=partition_kwargs,
            n_iterations=int(self.config.get("n_iterations", 2)),
            seed=self.config.get("seed"),
        )
        return [int(label) for label in membership]


def build_algorithm(config: dict) -> PartitionAlgorithm:
    """Build the configured local partitioning algorithm."""
    algorithm_name = config.get("algorithm", "placeholder")
    if algorithm_name == "placeholder":
        return PlaceholderPartitionAlgorithm()
    if algorithm_name == "leiden":
        return LeidenPartitionAlgorithm(config=config)
    raise ValueError(f"Unsupported partition.algorithm: {algorithm_name}")


def scipy_sparse_to_igraph(
    adjacency: sparse.spmatrix,
    directed: bool,
) -> tuple[igraph.Graph, list[float]]:
    """Convert a SciPy sparse adjacency matrix into an igraph graph."""
    csr = adjacency.tocsr()
    upper = csr if directed else sparse.triu(csr, k=1, format="coo")
    if directed:
        coo = csr.tocoo()
    else:
        coo = upper
    edges = list(zip(coo.row.tolist(), coo.col.tolist()))
    weights = coo.data.astype(float).tolist()
    igraph_graph = igraph.Graph(n=csr.shape[0], edges=edges, directed=directed)
    return igraph_graph, weights


def resolve_partition_type(config: dict):
    """Resolve the configured Leiden objective/partition type."""
    objective = config.get("objective", "rb_configuration")
    partition_types = {
        "modularity": leidenalg.ModularityVertexPartition,
        "rb_configuration": leidenalg.RBConfigurationVertexPartition,
        "cpm": leidenalg.CPMVertexPartition,
        "rber": leidenalg.RBERVertexPartition,
        "significance": leidenalg.SignificanceVertexPartition,
        "surprise": leidenalg.SurpriseVertexPartition,
    }
    if objective not in partition_types:
        raise ValueError(
            "Unsupported partition objective "
            f"{objective!r}. Supported objectives are {sorted(partition_types)}."
        )
    return partition_types[objective]


def build_leiden_partition_kwargs(config: dict) -> dict:
    """Build keyword arguments for the chosen Leiden partition type."""
    objective = config.get("objective", "rb_configuration")
    kwargs: dict = {}
    resolution = config.get("resolution")
    if resolution is not None and objective in {"rb_configuration", "cpm"}:
        kwargs["resolution_parameter"] = float(resolution)
    return kwargs


def compress_membership(
    labels: list[int] | None,
    num_nodes: int,
) -> list[int] | None:
    """Compress arbitrary community labels into dense memberships for Leiden."""
    if labels is None:
        return None
    if len(labels) != num_nodes:
        return None
    mapping: dict[int, int] = {}
    membership: list[int] = []
    next_label = 0
    for label in labels:
        if label not in mapping:
            mapping[label] = next_label
            next_label += 1
        membership.append(mapping[label])
    return membership


def run_leiden_partition(
    *,
    igraph_graph: igraph.Graph,
    partition_type,
    weights: list[float],
    initial_membership: list[int] | None,
    partition_kwargs: dict,
    n_iterations: int,
    seed: int | None,
) -> list[int]:
    """Run the Leiden optimizer and return community memberships."""
    partition = leidenalg.find_partition(
        igraph_graph,
        partition_type,
        initial_membership=initial_membership,
        weights=weights,
        n_iterations=n_iterations,
        seed=seed,
        **partition_kwargs,
    )
    return list(partition.membership)

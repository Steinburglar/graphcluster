# graphcluster

`graphcluster` is an early-stage Python project for graph clustering on
molecular dynamics trajectories.

The project is being built around a simple idea: read a trajectory, turn each
frame into a sparse weighted graph, partition that graph, keep cluster IDs
consistent over time, and make the results easy to visualize and export.

For a denser project checkpoint aimed at AI assistants, see
[context.md](/n/home12/lsteinberger/graphcluster/context.md). For the longer
archived design discussion, see
[codex_convo.md](/n/home12/lsteinberger/graphcluster/codex_convo.md).

## Status

This repository is still in the scaffolding / architecture phase.

What exists now:
- a package-owned core object model (`Frame`, `SparseWeightedGraph`, `Partition`, `FrameBundle`)
- an online tracking vs trajectory-analysis split in the design
- a working ASE-backed trajectory reader path for the toy LAMMPS binary dataset
- a real cutoff-based sparse graph builder with configurable edge-weight kernels
- a Leiden-based local partitioning path with optional warm starts
- a streaming runtime that writes visualization and lifecycle-report artifacts without keeping the full trajectory in memory
- a growing test suite around the current scaffold

## Current design

The current processing model is:

`Frame -> SparseWeightedGraph -> LocalPartition -> TrackedPartition -> FrameBundle`

Across time:

`TrackedPartition(t-1) + LocalPartition(t) -> ClusterTracker -> TrackedPartition(t)`

Across a full run:

`TrajectoryReader -> transient FrameBundle -> visualization artifact writer + lifecycle report recorder`

Key design choices:
- the core stays package-owned rather than built directly on ASE / OVITO / MDAnalysis objects
- sparse weighted graphs are the default graph representation
- tracking happens online in the main forward pass
- trajectory-level cluster analysis is separate from frame-to-frame tracking
- visualization is treated as a first-class part of the workflow
- the runtime is streaming-first; in-memory trajectory collection is debug-only

## Current IO direction

The IO layer is currently organized around:
- `TrajectoryReader` as the public, backend-agnostic facade
- backend-specific sources such as `ASETrajectorySource`
- conversion into project-owned `Frame` objects at the boundary

ASE is the current default backend because it is a practical starting point, but
internal code should not depend directly on ASE objects.

Current ASE-backed trajectory formats exercised in the project:
- LAMMPS binary dumps via `lammps-dump-binary`
- ordinary XYZ trajectories via `xyz`

## Toy dataset

The current toy dataset used by the tests is a LAMMPS binary dump in
`tests/data/`.

This is important because one of the project's concrete goals is to support MD
trajectory inputs of exactly this kind.

## Repository shape

High-level structure:
- `src/graphcluster/` for library code
- `tests/` for the scaffold test suite and toy data
- `context.md` for compact AI-facing project context
- `codex_convo.md` for the archived design discussion

## Environment Setup

The recommended setup is:
1. create or activate a mamba environment
2. install the project into that environment with `pip`

Example:

```bash
mamba create -n graphcluster python=3.10 pip -y
mamba activate graphcluster
cd /n/home12/lsteinberger/graphcluster
python -m pip install -e '.[dev,vis]'
```

If you already have a lab environment such as `nequip311`, you can use that
instead:

```bash
mamba activate nequip311
cd /n/home12/lsteinberger/graphcluster
python -m pip install -e '.[dev,vis]'
```

This install path does three useful things:
- it reads the dependency metadata from `pyproject.toml`
- it installs the package in editable mode so local source edits are picked up
- it exposes the console scripts `graphcluster` and `graphcluster-view-ase`

You can verify the environment with:

```bash
which python
which graphcluster
which graphcluster-view-ase
python -c "import graphcluster, ase, scipy, yaml, matplotlib; print('graphcluster environment ok')"
```

Then a debug run should work as:

```bash
graphcluster configs/toy_debug.yaml
graphcluster-view-ase outputs/toy_debug/visualization.extxyz --mode summary
```

### Why Not Just Use Mamba Alone?

`mamba` manages environments and Conda packages, but `pyproject.toml` is Python
package metadata. In practice, the normal workflow is:
- use `mamba` to create and activate the environment
- use `pip install -e ...` inside that environment to install the project from
  `pyproject.toml`

So `mamba` is still part of the setup, but it does not usually consume
`pyproject.toml` directly the way `pip` does.

If you wanted a fully Conda-native setup, the repository would typically also
need an `environment.yml` or similar lock/setup file.

## Style

The lab generally uses Google-style docstrings and comments.

For now, some scaffold files still contain more explanatory comments than a
finished codebase normally would. That is intentional while the architecture is
still being established. Over time, the README and code comments should become
cleaner and more concise.

## Near-term focus

The next development steps are likely to be:
- expand the different edge-weight kernels available in graph construction
- improve tracking and the statistics derived from tracked partitions
- improve and add report data access and report visualizations

## Partition Tuning

Leiden settings are controlled from the `partition:` block in the config. For
the currently supported objectives, `resolution` can be used to make communities
coarser or finer:

```yaml
partition:
  algorithm: leiden
  objective: cpm
  resolution: 0.05
  warm_start: true
```

Notes:
- `modularity` ignores `resolution`
- `rb_configuration` and `cpm` use `resolution`
- lower `resolution` tends to merge communities
- higher `resolution` tends to split them

For graph weights, `kernel: binary` or an inverse-distance-style kernel is
usually a more natural community-detection default than `kernel: distance`,
because Leiden interprets larger weights as stronger connections.

Current graph-kernel support includes:
- `binary`
- `distance`
- `gaussian`
- `inverse_distance`
- `smooth_inverse_distance`

The graph builder also supports a separate source path:
- `graph.source: trajectory` builds edges from geometry
- `graph.source: allegro` consumes exported Allegro edge arrays from ASE
  trajectory metadata

For the current Allegro path, the expected ASE metadata keys are:
- `allegro_edge_indices`
- `allegro_edge_energies`

Current Allegro-to-graph semantics are intentionally simple:
- exported Allegro edges are treated as directed inputs
- positive edge energies are ignored
- negative edge energies become bond strengths via `abs(energy)`
- the undirected Leiden graph weight is the sum of both directions

So if `E_ij = -0.2` and `E_ji = -0.3`, the final undirected graph edge weight
is `0.5`.

`gaussian` uses the common ML-style radial form
`exp(-d^2 / (2 sigma^2))`. You can configure it explicitly:

```yaml
graph:
  cutoff: 3.5
  kernel:
    name: gaussian
    sigma: 1.0
```

If `sigma` is omitted, it currently defaults to `cutoff / 3`.

`graph.cutoff: auto` now tries to infer a cutoff in this order:
- recorded per-frame metadata loaded from the trajectory source
- nested source metadata such as ASE-carried `atoms.info`
- fallback input metadata such as `input.cutoff_radius`

This is still best-effort. Ordinary LAMMPS dump trajectories often do not carry
their neighbor or pair cutoff explicitly, so some runs will still need the
cutoff provided in config.

## Runtime Artifacts

The runtime is organized around transient `FrameBundle`s. The runner streams one
bundle at a time into artifact writers instead of collecting the whole
trajectory by default.

The two main first-class outputs are:
- a viewer-friendly trajectory artifact
- a lifecycle report artifact

The visualization artifact can be enabled like this:

```yaml
visualization:
  enabled: true
  backend: ase
  mode: traj
  write_batch_size: 10
  output_path: outputs/debug/visualization.extxyz
```

The lifecycle report artifact can be enabled like this:

```yaml
analysis:
  enabled: true
  write_batch_size: 10
  output_path: outputs/debug/cluster_lifecycle_report.jsonl
```

Both writers support `write_batch_size` so we can trade off write frequency
against transient in-memory buffering.

## Allegro Pre-Annotation

`graphcluster` can now optionally orchestrate an Allegro edge-annotation step
before the normal clustering pipeline begins. This is meant for the workflow:
- start from a raw trajectory that does not yet contain exported edge energies
- run a compiled Allegro ASE calculator over those frames
- write a new ASE trajectory containing the normal frame data plus
  `allegro_*` edge metadata
- continue directly into the graph clustering pipeline

This is controlled through an optional top-level `allegro:` block:

```yaml
input:
  backend: ase
  format: lammps-dump-binary
  trajectory: /path/to/raw_trajectory.bin

graph:
  source: allegro

allegro:
  mode: annotate_if_missing
  compiled_model: /path/to/compiled_model.nequip.pt2
  annotated_trajectory_path: outputs/allegro_run/allegro_edges.traj
  device: cuda
  raw_type_map:
    1: Ga
    2: Pt
```

Supported `allegro.mode` values are:
- `disabled`
- `require_precomputed`
- `annotate_if_missing`
- `annotate_always`
- `annotate_only`

Important semantics:
- the annotation step writes a new derived ASE trajectory file; it does not
  modify the original input trajectory in place
- the derived file contains both the usual atomic trajectory information and
  exported `allegro_*` edge metadata in `Atoms.info`
- when annotation is enabled and the mode continues the run, `graphcluster`
  automatically switches its effective input to that derived trajectory

The report artifact can later be loaded without rerunning clustering:

```python
from graphcluster.analysis.lifecycle_report import ClusterLifecycleReport

report = ClusterLifecycleReport.from_path("outputs/debug/cluster_lifecycle_report.jsonl")
print(report.summary)
print(report.get_births()[:5])
```

There is also a starter notebook for this workflow at
[`notebooks/inspect_lifecycle_report.ipynb`](/n/home12/lsteinberger/graphcluster/notebooks/inspect_lifecycle_report.ipynb).

The important architectural ideas are:
- `FrameBundle` is the transient in-memory handoff between core pipeline steps
- visualization and reporting are persistent artifact sinks, not reasons to keep
  the whole trajectory in RAM
- later, post-run readers can consume those artifacts without rerunning the full
  graph-partitioning pipeline

If the input trajectory uses raw type IDs such as LAMMPS `type`, you can supply
an optional source-level mapping so the visualizer can display real chemical
symbols while still preserving the raw type labels:

```yaml
input:
  trajectory: path/to/trajectory.bin
  type_map:
    1: Ga
    2: Pt
```

Current semantics:
- `atom_types` preserve the raw labels from the input source
- `chemical_symbols` are an optional interpreted view derived from `input.type_map`
- ASE display should use `chemical_symbols` when available
- the current ASE artifact keeps only the meaningful extra per-atom arrays:
  `cluster_label`, `local_cluster_label`, and `raw_atom_type`
- on the first frame, tracked `cluster_label` now preserves the local partition
  labels instead of renumbering them

You can then inspect the artifact with:

```bash
graphcluster-view-ase outputs/debug/visualization.extxyz --mode summary
graphcluster-view-ase outputs/debug/visualization.extxyz --mode gui --frame 0
graphcluster-view-ase outputs/debug/visualization.extxyz --mode png --frame 0 --output outputs/debug/frame0.png
```

The GUI path is intended for manual debugging. The trajectory artifact itself is
the stable, testable output of the pipeline.

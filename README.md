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
- a growing test suite around the current scaffold

## Current design

The current processing model is:

`Frame -> SparseWeightedGraph -> LocalPartition -> TrackedPartition -> FrameBundle`

Across time:

`TrackedPartition(t-1) + LocalPartition(t) -> ClusterTracker -> TrackedPartition(t)`

Key design choices:
- the core stays package-owned rather than built directly on ASE / OVITO / MDAnalysis objects
- sparse weighted graphs are the default graph representation
- tracking happens online in the main forward pass
- trajectory-level cluster analysis is separate from frame-to-frame tracking
- visualization is treated as a first-class part of the workflow

## Current IO direction

The IO layer is currently organized around:
- `TrajectoryReader` as the public, backend-agnostic facade
- backend-specific sources such as `ASETrajectorySource`
- conversion into project-owned `Frame` objects at the boundary

ASE is the current default backend because it is a practical starting point, but
internal code should not depend directly on ASE objects.

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
- continue improving the real IO path
- start building graph construction on top of `Frame`
- keep the tests anchored to the toy dataset as functionality grows

## Debug Visualization

The pipeline now supports an ASE-backed debug visualization artifact path. A
run can write an ASE trajectory file by adding:

```yaml
visualization:
  enabled: true
  backend: ase
  mode: traj
  output_path: outputs/debug/visualization.extxyz
```

The important architectural idea is that `VisualizationPayload` is the common
backend-independent view model. Right now it is constructed during the live
pipeline from `FrameBundle`, which is useful for debugging. In a more finished
workflow, the same payload shape may also be constructed later from a heavier
saved artifact, then handed into the same viewer/export backends.

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

You can then inspect the artifact with:

```bash
graphcluster-view-ase outputs/debug/visualization.extxyz --mode summary
graphcluster-view-ase outputs/debug/visualization.extxyz --mode gui --frame 0
graphcluster-view-ase outputs/debug/visualization.extxyz --mode png --frame 0 --output outputs/debug/frame0.png
```

The GUI path is intended for manual debugging. The trajectory artifact itself is
the stable, testable output of the pipeline.

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

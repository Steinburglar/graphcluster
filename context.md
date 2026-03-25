# graphcluster context

This file is an AI-facing checkpoint for the project. Its purpose is to give a
new LLM assistant enough compact context to continue useful work without having
to reconstruct the architecture from the full design conversation.

## Project goal

`graphcluster` is an early-stage Python project for graph clustering on
molecular dynamics trajectories.

The long-term idea is:
- read an MD trajectory or other pairwise edge data
- build a sparse weighted graph for each frame
- partition that graph
- keep cluster identities temporally consistent across frames
- analyze lifetimes, births, deaths, splits, and merges
- visualize and export the results

The project is not meant to be tied internally to one specific MD ecosystem.
Packages such as ASE, MDAnalysis, and OVITO should live at the boundaries as
loaders, adapters, or visualization backends.

## Core design principles

1. Keep the scientific core package-owned.
   Internal code should operate on project-owned objects such as `Frame`,
   `SparseWeightedGraph`, `Partition`, and `FrameBundle`, not on ASE / OVITO /
   MDAnalysis objects.

2. Use adapters at the boundaries.
   External packages should be used to load and visualize data, but the core
   pipeline should not depend on their internal data models.

3. Prefer sparse weighted graphs.
   A dense similarity matrix should not be the central abstraction.

4. Separate online tracking from trajectory-level analysis.
   Tracking is a frame-to-frame synchronization step in the main forward pass.
   Lifetime / split / merge analysis is a separate later step.

5. Keep the architecture readable.
   The user explicitly dislikes overbuilt, ceremonious code. Readability and
   explicitness are important constraints.

## Current scientific assumptions

- Nodes are atoms.
- Edges carry one scalar value.
- Graphs are undirected for now.
- Graphs are sparse by default.
- Partitioning happens frame by frame.
- Tracking happens online in the same forward pass.
- Trajectory-level analysis is separate.
- Visualization is first-class, not just export.
- Future edge sources may come from Allegro deep in a LAMMPS workflow.

## Current high-level pipeline

Per frame:

`Frame -> SparseWeightedGraph -> LocalPartition -> TrackedPartition -> FrameBundle`

Across time:

`TrackedPartition(t-1) + LocalPartition(t) -> ClusterTracker -> TrackedPartition(t)`

Across a full run:

`TrajectoryReader -> graph builder -> partitioner -> tracker -> transient FrameBundle -> artifact writers`

Current artifact writers:
- ASE visualization writer
- lifecycle report recorder

Important runtime point:
- the runner is now streaming-first
- `FrameBundle` is the transient in-memory unit
- the runtime should not materialize a whole frame-bundle trajectory by default
- in-memory trajectory collections are debug/test helpers, not the core model

## Object model

### Per-frame core objects

- `Frame`
  Canonical project-owned representation of one MD timestep.
  Current fields:
  - `index`
  - `positions`
  - `box`
  - `cell_origin`
  - `time`
  - `atom_types`
  - `chemical_symbols`
  - `metadata`

  Notes:
  - `Frame` was intentionally simplified.
  - There is currently no `atom_ids` field.
  - Atom identity is implicitly row index for now.

- `SparseWeightedGraph`
  Canonical per-frame graph object.

- `Partition`
  One frame's cluster assignment. Conceptually there is a difference between a
  raw local partition and a tracked partition, but the current scaffold uses one
  class with metadata / `kind`.

- `FrameBundle`
  Lightweight per-frame object bundling a frame, its graph, and its tracked
  partition. It exists because downstream tasks such as visualization need them
  together, but `Frame` itself should not carry graph or partition state.

- `VisualizationPayload`
  Backend-independent visualization handoff.
  Current live/debug construction path: derived from a `FrameBundle`.
  Intended future production path: may also be derived from a heavier saved
  artifact via a dedicated reader/adapter.

### Trajectory-level objects

- `TrajectoryReader`
  Public facade for reading frames.

- `PartitionTrajectory`
  Append-only in-memory store of tracked partitions for small runs and tests.
  Not the core runtime output.

- `ClusterTracker`
  Online frame-to-frame ID synchronizer.

- `ClusterLifecycleRecorder`
  Streaming writer that records trajectory-level lifecycle data into a report
  artifact during the run.

- `ClusterLifecycleAnalyzer`
  Lightweight in-memory helper for small/offline analysis.

- `ClusterLifecycleReport`
  User-facing report object loaded from the lifecycle report artifact.

- `TrajectoryPartitionRunner`
  Top-level coordinator of the main loop.

## Important temporal design decisions

1. Tracking is not the same as analysis.
   - Tracking = making frame `t` IDs consistent with frame `t-1`
   - Analysis = computing cluster lifetimes / splits / merges over a trajectory

2. Tracking should happen in the same forward pass.
   The design should avoid a second labeling pass over already emitted objects.

3. `FrameBundle` should be complete when emitted.
   It should not be a half-filled object waiting for future-derived information,
   but it is also not intended to be retained for the whole trajectory by
   default.

4. If future view-like behavior is needed for memory efficiency, it should use
   explicit references / handles rather than hidden shared-state magic.

## Current IO design

The IO layer was recently refactored toward a lighter architecture.

Current state:
- `TrajectoryReader` is a backend-agnostic facade.
- `ASETrajectorySource` is the current concrete backend worker.
- `TrajectoryReader.__iter__()` delegates to the backend-specific source.
- Format inference is simple and local.
- The public reader is intentionally not tied directly to ASE internals.

An earlier, more abstract base-source layer existed and was removed because it
felt like too much code for the current stage.

### Current implementation details

- Default backend: `ase`
- Format inference: `.bin -> lammps-dump-binary`
- The toy LAMMPS binary is read through ASE with explicit columns:
  - `id type x y z`

### Important ASE / LAMMPS detail

ASE can read the toy LAMMPS binary if given the correct format and columns, but
ASE maps LAMMPS type IDs `1` and `2` to chemical symbols like `H` and `He`,
which is misleading for the Ga/Pt toy system.

Current decision:
- preserve the raw LAMMPS `type` values in `Frame.atom_types`
- do not treat ASE's inferred chemical symbols as true species
- a real type-to-species mapping can be added later if source metadata becomes
  available

Current implemented extension:
- the input config may optionally provide `input.type_map`
- if present, the reader preserves raw source labels in `atom_types` and also
  resolves a parallel `chemical_symbols` list for visualization use
- `atom_types` should be treated as source truth; `chemical_symbols` is the
  interpreted display-friendly view

## Current implementation reality

The project is still early-stage, but the core forward path is now real enough
to be debugged end to end:
- trajectory reading is real
- cutoff-based graph construction is real
- Leiden local partitioning is real
- overlap-based tracking is real
- visualization artifact writing is real
- lifecycle report recording is real

Still simplified / early:
- graph kernels are still basic and cutoff handling is still simple
- tracking heuristics are useful but not yet scientifically mature
- in-memory `ClusterLifecycleAnalyzer` is still minimal compared with the new
  streaming report recorder
- report visualization and plotting are still very early

### Recently resolved scaffold gap

A previous scaffold bug caused the end-to-end runner path to emit empty
partition label lists because graph node count was not being propagated into
graph metadata. That specific issue was fixed by propagating node count through
the graph object. The scientific middle of the pipeline is still placeholder
logic, but the live debug path now preserves the intended one-label-per-atom
shape.

## Config support: actual vs planned

Supported in the runtime today:
- `input.trajectory`
- `input.backend` optional
- `input.format` optional
- `frames.start`
- `frames.stop`
- `frames.stride`
- `graph.source`
- `graph.cutoff`
- `graph.kernel`
- `partition.warm_start`
- `partition.algorithm`
- `partition.objective`
- `partition.resolution`
- `tracking.*`
- `visualization.*`
- `analysis.*`

Present in example configs but not meaningfully implemented yet:
- `input.topology`
- `graph.mode`
- `output.*`

## Canonical adjacency direction

The intended direction is:
- canonical wrapper: `SparseWeightedGraph`
- canonical payload: `scipy.sparse` matrix
- likely construction format: COO
- likely consumption format: CSR

This is still design intent, not a frozen contract.

## Partition / tracking invariants

The intended tracked-partition semantics are:
- one integer cluster label per atom in frame row order
- same tracked label across frames means "same tracked cluster identity" as
  best as the tracker can determine
- splits / merges / births / deaths should be represented in tracking metadata
  and trajectory-level analysis, not by breaking the one-label-per-atom rule

Current label policy:
- one label per atom in row order is the intended contract
- on the first frame, tracked labels now preserve the local partition labels
  rather than being renumbered for visualization/reporting convenience
- there is currently no sentinel value contract for noise / unassigned atoms
- if needed later, `-1` is the most natural future choice, but it is not yet a
  project-level guarantee

## Metadata stability

Only explicit object fields should currently be treated as stable contract.
Most `metadata` dictionary keys should be treated as best-effort and unstable
unless later promoted into documented API.

Examples:
- stable: dataclass fields on `Frame`, `Partition`, `FrameBundle`, etc.
- unstable for now: many ad hoc `metadata` keys used for scaffolding/debugging

## Visualization payload design

`VisualizationPayload` should be treated as the common visualization contract.

Current path:
- live pipeline objects (`FrameBundle`) -> `VisualizationPayload` -> viewer/export backend

Intended future path:
- heavier saved artifact -> dedicated visualization reader/adapter -> `VisualizationPayload` -> same viewer/export backend

Design implication:
- viewer backends should depend on the payload, not on whether the payload came
  from a live pipeline object or a post-run artifact
- the current in-run construction path is for debugging convenience, not a
  statement that visualization payloads must always be produced during the run
- the current ASE artifact stores the meaningful extra per-atom arrays only:
  `cluster_label`, `local_cluster_label`, and `raw_atom_type`
- older redundant convenience data such as ASE `tags` has been removed

## Examples and docs status

The YAML examples mix:
- keys that work today
- keys that reflect future intended config shape

So the example YAMLs should currently be treated as design sketches, not as
fully runnable supported configs.

## Testing state

The repository includes a growing scaffold test suite.

Current toy dataset:
- `tests/data/Ga80Pt20_129_773K_ss_1.all.bin`

Important testing behavior:
- the default toy dataset is configured in `tests/conftest.py`
- tests can later swap datasets through a fixture-level helper
- current tests confirm that the toy LAMMPS binary can be read and converted
  into `Frame` objects

At the latest checkpoint, the suite was green with 32 passing tests.

## Tooling and environment notes

- The user has a `nequip311` mamba environment.
- Project dependencies and `pytest` were installed there.
- Tests are run with `mamba run -n nequip311 pytest -q`.
- There have been intermittent sandbox / `bwrap` issues in this session, so
  repo edits were sometimes done through escalated shell commands.

## Documentation split

There are now three documentation layers:
- `README.md`: human-facing project readme
- `context.md`: AI-facing compact checkpoint
- `codex_convo.md`: long archival design conversation

This split was intentional and should be preserved.

## Style guidance

- Prefer Google-style docstrings and comments going forward because that is the
  lab default.
- The current scaffold still contains more explanatory comments than a mature
  codebase would normally have.
- That was intentional while architecture was still being established.
- Later cleanup passes should shorten comments and focus them on intent,
  invariants, and non-obvious decisions.

## Things intentionally not settled yet

These are still open design areas and should not be assumed solved:
- exact graph construction strategy for real production use
- exact partitioning algorithms to support first
- species / type mapping beyond raw LAMMPS type IDs
- visualization backend strategy beyond the ASE-first prototype direction
- detailed export formats
- backend support beyond ASE
- how Allegro-derived edge data will enter the pipeline
- whether residue/coarse-grained views should be first-class later

## Immediate next priorities

The next important milestones are:
- expand the different edge-weight kernels available in graph construction
- improve tracking and the statistics derived from tracked partitions
- improve and add report data access and report visualizations

## Guidance for future AI assistants

If continuing this project, prefer the following:
- keep the core package-owned and backend-agnostic
- preserve the online tracking vs later analysis split
- preserve `FrameBundle` as a complete emitted object
- avoid reintroducing heavy abstractions unless a second backend or real use
  case truly needs them
- keep readability high; the user is sensitive to code becoming too abstract or
  ceremonious too early
- when in doubt, bias toward simple, explicit, inspectable code

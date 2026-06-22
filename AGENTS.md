# graphcluster Agent Guide

`graphcluster` clusters atoms in MD trajectories by building one sparse
weighted graph per frame, partitioning it, tracking cluster IDs online, and
writing streaming artifacts.

This file is canonical agent context. Keep it current when code behavior,
architecture, config schema, dependencies, workflows, or open tasks change.

## Current State

Project stage: early but runnable. Main path works for small/debug runs:

```text
TrajectoryReader -> Frame -> GraphBuilder -> SparseWeightedGraph -> Partitioner -> LocalPartition -> ClusterTracker -> TrackedPartition -> FrameBundle -> artifact writers
```

Implemented:

- ASE-backed trajectory source.
- Project-owned `Frame` boundary object.
- Sparse SciPy adjacency via `SparseWeightedGraph`.
- Cutoff geometry graph construction.
- Kernels: `binary`, `distance`, `gaussian`, `gaussian_distance`, `inverse_distance`, `smooth_inverse_distance`.
- Allegro edge consumption from pre-annotated ASE metadata.
- Leiden local partitioning through `igraph`/`leidenalg`.
- Optional warm start from previous tracked partition.
- Online overlap-based tracking.
- Streaming ASE visualization artifact writer.
- Streaming JSONL lifecycle report recorder.
- Raw Allegro per-cluster energy summaries.
- First-pass reaction candidate ranking from reconstructed cluster energy deltas.

Still early:

- config logic still needs cleanup
- tracking heuristics need scientific validation
- lifecycle report plotting/data access still thin
- by-cluster local energy tracking needs refinement
- profiling/optimization pass pending
- more runner + analysis integration tests needed

## Design Principles

- Core uses package-owned objects, not ASE/OVITO/MDAnalysis objects.
- External packages live at IO/visualization/annotation boundaries.
- Sparse weighted graphs are default; avoid dense `O(N^2)` core data.
- Tracking and analysis stay separate.
- Runtime is streaming-first; do not retain whole trajectory unless caller asks.
- Keep code explicit and readable; avoid ceremony before real backend pressure exists.
- Visualization and reports are first-class outputs, not afterthoughts.
- Metadata dict keys are mostly unstable unless promoted into documented fields.

## Core Objects

- `Frame`: canonical per-frame data. Fields: `index`, `positions`, `box`, `cell_origin`, `time`, `atom_types`, `chemical_symbols`, `metadata`.
- `SparseWeightedGraph`: per-frame sparse graph wrapper. Canonical payload is SciPy sparse adjacency.
- `Partition`: one label per atom. `kind` distinguishes `local` vs `tracked`.
- `FrameBundle`: transient complete timestep result: frame, graph, tracked partition, local partition.
- `TrajectoryReader`: backend-agnostic frame stream facade.
- `ClusterTracker`: online previous-frame/current-frame ID synchronizer.
- `ClusterLifecycleRecorder`: streaming JSONL report writer.
- `ClusterLifecycleReport`: post-run report reader.
- `VisualizationPayload`: backend-neutral visualization handoff.

Important invariant: `FrameBundle` is complete when emitted. Do not mutate old
bundles later with future trajectory knowledge.

## Config Schema

Canonical schema is:

```yaml
source:
  backend: ase
  format: lammps-dump-binary
  path: tests/data/Ga80Pt20_129_773K_ss_1.all.bin
  type_map:
    1: Ga
    2: Pt
  cutoff_radius: 3.5

selection:
  start: 0
  stop: 3
  stride: 1

edges:
  kind: binary
  cutoff: 3.5
  directed: false

partition:
  algorithm: leiden
  objective: cpm
  resolution: 0.05
  warm_start: true
  n_iterations: 2
  seed: 123

tracking:
  enabled: true
  overlap_metric: jaccard
  match_threshold: 0.5
  event_threshold: 0.1

artifacts:
  directory: outputs/toy_debug_v2
  visualization:
    enabled: true
    backend: ase
    mode: traj
    every_n: 1
    write_batch_size: 10
  lifecycle_report:
    enabled: true
    write_batch_size: 10

profiling:
  enabled: false
```

`src/graphcluster/utils/config.py` requires `source.path`. Legacy docs/configs
used `input`, `frames`, `graph`, `visualization`, `analysis`, and `output`.
Some compatibility paths remain in `GraphBuilder`, but new docs/configs should
use canonical schema.

## CLI

`pyproject.toml` exposes:

- `graphcluster = graphcluster.cli:main`
- `graphcluster-view-ase = graphcluster.view_ase_artifact:main`

`graphcluster` args:

- positional `config`
- optional `--profile`

No standalone Allegro annotation CLI exists in current `src/graphcluster`.
Historical docs mentioning `annotate-allegro` or `allegro-annotate-trajectory`
describe external/old workflow, not current package entrypoints.

## IO

Current backend: `ase` only.

Format inference:

- `.bin` -> `lammps-dump-binary`
- `.xyz` -> `xyz`
- `.extxyz` -> `extxyz`
- `.traj` -> `traj`

LAMMPS binary read uses columns:

```text
id type x y z
```

Species semantics:

- If ASE frame has `type` array, raw values become `Frame.atom_types`.
- `source.type_map` maps raw values to `Frame.chemical_symbols`.
- If no `type` array exists, ASE chemical symbols populate both labels.
- Treat `atom_types` as source truth; `chemical_symbols` as display/species view.

`Frame.cell_origin` comes from ASE `celldisp` or metadata `ase_info.cell_origin`.

## Graph Construction

Geometry edge path:

- `edges.kind` names kernel.
- `edges.cutoff` required unless `edges.cutoff: auto` can infer metadata.
- PBC support is orthorhombic only through `scipy.spatial.cKDTree(boxsize=...)`.
- Non-orthorhombic boxes currently fall back to nonperiodic distances.

Supported geometry kernels:

- `binary`: weight `1`.
- `distance`: weight = distance. Caution: larger distance becomes stronger edge for Leiden.
- `gaussian` / `gaussian_distance`: `exp(-d^2 / (2 sigma^2))`; default `sigma = cutoff / 3`.
- `inverse_distance`: `1 / max(distance, epsilon)`.
- `smooth_inverse_distance`: cosine cutoff divided by safe distance.

`edges.cutoff: auto` searches `Frame.metadata` and `source` recursively for:

- `cutoff`
- `cutoff_radius`
- `neighbor_cutoff`
- `pair_cutoff`
- `edge_cutoff`
- `rcut`
- `r_cut`
- `r_max`

## Allegro Edge Consumption

Allegro path consumes recorded metadata only. It does not call NequIP/Allegro.

Required metadata:

- `allegro_edge_indices`
- `allegro_edge_raw_energies` or legacy `allegro_edge_energies`
- `allegro_edge_scaled_energies` when `edges.energy_field: scaled`

Metadata may live directly in `Frame.metadata` or nested in
`Frame.metadata["ase_info"]`.

Config:

```yaml
edges:
  kind: allegro
  energy_field: raw
  energy_to_weight: abs_negative_sum
  allegro_scaling:
    percentile: 99.5
    sample_edge_budget: 200000
```

Semantics:

- Edge inputs are directed.
- `abs_negative_sum`: positive energy contributes `0`; negative energy
  contributes `abs(energy)`.
- Directed pair contributions sum onto sorted undirected atom pair.
- Graph output is symmetric CSR.
- `allegro_scaling` samples prefix frames, computes percentile of absolute
  non-self edge magnitudes, and divides weights by that scale.

Alternate `signed_shifted_sum` exists:

- contribution = `-(energy + source_shift_per_edge)`
- requires `edges.species_shifts`
- optional `edges.avg_num_neighbors`
- may produce negative weights, allowed only for this mode

## Partitioning

`src/graphcluster/partitioning/algorithms.py` supports:

- `placeholder`
- `leiden`

Leiden objectives:

- `modularity`
- `rb_configuration`
- `cpm`
- `rber`
- `significance`
- `surprise`

`resolution` passes only to `rb_configuration` and `cpm`.
`n_iterations` defaults to `2`.
`seed` is passed through to `leidenalg.find_partition`.

If adjacency has zero edges, Leiden path returns one singleton cluster per atom.

## Tracking

`ClusterTracker` does online ID synchronization only.

Supported overlap metrics:

- `jaccard`
- `f1`
- `precision`
- `recall`
- `intersection`

Algorithm:

1. group atom indices by cluster label
2. compute overlap stats between previous tracked clusters and current local clusters
3. use Hungarian assignment to maximize selected overlap score
4. accept assignment if score >= `tracking.match_threshold`
5. otherwise allocate new tracked cluster ID
6. record births, deaths, split candidates, merge candidates

First frame preserves local labels as tracked labels.

## Lifecycle Report

Config:

```yaml
artifacts:
  directory: outputs/run
  lifecycle_report:
    enabled: true
    write_batch_size: 10
```

Default path: `<artifacts.directory>/cluster_lifecycle_report.jsonl`.
Fallback when enabled with no directory/path: `outputs/cluster_lifecycle_report.jsonl`.

Report records:

- header record
- per-frame records: cluster sizes, changed atoms, births/deaths/splits/merges, match details
- summary record: frame count, atom count, tracked clusters, event totals, lifetimes, atom switch counts

Cluster energy config:

```yaml
artifacts:
  lifecycle_report:
    enabled: true
    cluster_energy:
      enabled: true
      source: allegro_raw
      require_available: true
      model_energy_reconstruction:
        enabled: true
        species_scales:
          Ga: 1.0
          Pt: 1.0
        species_shifts:
          Ga: 0.0
          Pt: 0.0
        avg_num_neighbors:
          Ga: 12
          Pt: 12
    reaction_tracking:
      enabled: true
      top_n_frames: 10
      required_species: [Pt]
```

Current reaction tracking uses raw frame-to-frame delta of reconstructed cluster
model energy. It keeps top-N scored frames and can require species presence.

## Visualization

Config:

```yaml
artifacts:
  directory: outputs/run
  visualization:
    enabled: true
    backend: ase
    mode: traj
    every_n: 1
    write_batch_size: 10
```

Default path: `<artifacts.directory>/visualization.extxyz`.
Fallback when enabled with no directory/path: `outputs/visualization.extxyz`.

Supported modes:

- `traj`: stream ASE-readable trajectory artifact.
- `view`: open ASE viewer during run.
- `collect`: retain payloads in memory; debug only.

Stable per-atom arrays in ASE artifact:

- `cluster_label`
- `local_cluster_label`
- `raw_atom_type`

Use `graphcluster-view-ase` for summary, GUI, or PNG.

## Runtime Notes

`TrajectoryPartitionRunner.run()`:

- reads one frame at a time
- builds one graph
- partitions one graph
- tracks current partition
- creates one transient `FrameBundle`
- sends bundle to lifecycle recorder and visualizer
- discards bundle unless `collect_bundles=True`

Profiling buckets:

- startup: `load_config`, `reader_init`, `allegro_edge_scaling`, `graph_builder_init`, `partitioner_init`, `tracker_init`, `lifecycle_recorder_init`, `visualizer_init`
- run: `read_frame`, `graph_build`, `partition_local`, `track_partition`, `analysis_consume`, `visualization_consume`, finalizers

## Tests

Run:

```bash
pytest -q
```

FAS RC known-good path:

```bash
mamba run -n nequip311 pytest -q
```

Toy data:

```text
tests/data/Ga80Pt20_129_773K_ss_1.all.bin
```

## Development Rules

- Prefer `configs/toy_debug_v2.yaml` for current schema smoke tests.
- Do not treat older configs as authoritative if code disagrees.
- Check actual code before resolving doc drift.
- Preserve streaming behavior for large trajectories.
- Do not reintroduce runner-side Allegro annotation or hidden input switching.
- Keep `ClusterTracker` separate from lifecycle analysis.
- Keep ASE-specific logic inside IO/visualization modules.
- Keep `Frame`, graph, partition, and bundle objects backend-neutral.
- Use Google-style docstrings for new Python code.
- Add focused tests when changing shared behavior.
- On FAS RC, avoid serious computation on login nodes. Use compute nodes for heavy runs.

## Open Work

- Refactor config normalization. Current compatibility layer is uneven.
- Update stale example configs to canonical schema.
- Improve by-cluster local energy tracking.
- Add report plotting/data access helpers.
- Profile graph build, Leiden partitioning, and artifact writing.
- Add integration tests for lifecycle report + analysis edge cases.
- Validate tracking thresholds and event interpretation on real systems.
- Decide long-term external Allegro annotation workflow and document exact tool/repo once stable.

## Historical Docs

Old `CODEX.md`, `TODO.md`, and `context.md` were collapsed into this file plus
`README.md`. Long design conversation remains in Git history; do not recreate
parallel root docs unless user asks.

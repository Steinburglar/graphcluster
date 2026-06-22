# graphcluster

`graphcluster` clusters atoms in molecular dynamics trajectories by converting
each frame into a sparse weighted graph, partitioning that graph, tracking
cluster IDs across time, and writing inspectable artifacts.

Current runtime path:

```text
Frame -> SparseWeightedGraph -> LocalPartition -> TrackedPartition -> artifacts
```

Across frames:

```text
TrackedPartition(t-1) + LocalPartition(t) -> ClusterTracker -> TrackedPartition(t)
```

Status: early-stage, but main debug path is real. ASE trajectory reading,
cutoff graph construction, Leiden partitioning, overlap tracking, ASE
visualization output, lifecycle report output, and Allegro-edge consumption all
exist.

## Install

Use Python 3.10+.

```bash
cd /n/home12/lsteinberger/code/graphcluster
python -m pip install -e '.[dev,vis]'
```

Installed console scripts:

```bash
graphcluster --help
graphcluster-view-ase --help
```

On FAS RC, the known-good lab environment is usually:

```bash
export PATH=/n/holylabs/kozinsky_lab/Users/lsteinberger/conda/envs/nequip311/bin:$PATH
export CONDA_PREFIX=/n/holylabs/kozinsky_lab/Users/lsteinberger/conda/envs/nequip311
python -m pip install -e '.[dev,vis]'
```

## Run

Minimal current config:

```yaml
source:
  backend: ase
  format: lammps-dump-binary
  path: tests/data/Ga80Pt20_129_773K_ss_1.all.bin
  type_map:
    1: Ga
    2: Pt

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

tracking:
  enabled: true
  overlap_metric: jaccard
  match_threshold: 0.5

artifacts:
  directory: outputs/toy_debug_v2
  visualization:
    enabled: true
    backend: ase
    mode: traj
    write_batch_size: 10
  lifecycle_report:
    enabled: true
    write_batch_size: 10

profiling:
  enabled: false
```

Run toy config:

```bash
graphcluster configs/toy_debug_v2.yaml
```

Run with timing output:

```bash
graphcluster --profile configs/toy_debug_v2.yaml
```

Inspect visualization artifact:

```bash
graphcluster-view-ase outputs/toy_debug_v2/visualization.extxyz --mode summary
graphcluster-view-ase outputs/toy_debug_v2/visualization.extxyz --mode png --frame 0 --output outputs/toy_debug_v2/frame0.png
```

## Config

Canonical top-level keys:

- `source`: trajectory backend, path, format, type mapping, optional cutoff metadata.
- `selection`: frame `start`, `stop`, `stride`.
- `edges`: graph edge source/kernel/weights.
- `partition`: local partition algorithm and hyperparameters.
- `tracking`: online ID synchronization settings.
- `artifacts`: visualization and lifecycle report sinks.
- `profiling`: optional timing output.

Legacy docs/configs used `input`, `frames`, `graph`, `visualization`, `analysis`,
and `output`. Some compatibility remains in code, but new configs should use
the canonical schema above.

## Trajectory IO

Current backend: `ase`.

Format inference:

- `.bin` -> `lammps-dump-binary`
- `.xyz` -> `xyz`
- `.extxyz` -> `extxyz`
- `.traj` -> `traj`

For LAMMPS binary dumps, ASE reads columns:

```text
id type x y z
```

`source.type_map` maps raw atom types to chemical symbols for visualization and
species-aware analysis. Raw labels stay in `Frame.atom_types`; interpreted
symbols go to `Frame.chemical_symbols`.

## Edge Kinds

Geometry-derived edges use `edges.cutoff` and `edges.kind` as kernel name:

- `binary`
- `distance`
- `gaussian`
- `gaussian_distance`
- `inverse_distance`
- `smooth_inverse_distance`

Examples:

```yaml
edges:
  kind: gaussian
  cutoff: 3.5
  sigma: 1.0
```

```yaml
edges:
  kind: smooth_inverse_distance
  cutoff: auto
  epsilon: 1.0e-12
```

`edges.cutoff: auto` searches frame/source metadata for keys such as `cutoff`,
`cutoff_radius`, `neighbor_cutoff`, `pair_cutoff`, `r_cut`, or `r_max`. Ordinary
trajectory dumps often lack this metadata, so explicit cutoff is safer.

## Partitioning

Supported `partition.algorithm` values:

- `placeholder`: puts all atoms in cluster `0`.
- `leiden`: real Leiden graph partitioning via `igraph` and `leidenalg`.

Supported Leiden objectives:

- `modularity`
- `rb_configuration`
- `cpm`
- `rber`
- `significance`
- `surprise`

`resolution` is passed only for `rb_configuration` and `cpm`; `modularity`
ignores it. `warm_start: true` uses previous tracked labels as Leiden initial
membership when sizes match.

## Tracking

`ClusterTracker` synchronizes frame-local labels into persistent tracked IDs.
It uses overlap between previous tracked clusters and current local clusters.

Supported `tracking.overlap_metric` values:

- `jaccard`
- `f1`
- `precision`
- `recall`
- `intersection`

Tracking metadata records births, deaths, split candidates, merge candidates,
and per-cluster match diagnostics. This is online ID synchronization, not final
trajectory analysis.

## Artifacts

If `artifacts.directory` is set, default outputs are:

- `visualization.extxyz`
- `cluster_lifecycle_report.jsonl`

Explicit output paths override defaults:

```yaml
artifacts:
  directory: outputs/run
  visualization:
    enabled: true
    backend: ase
    mode: traj
    output_path: outputs/run/custom.extxyz
  lifecycle_report:
    enabled: true
    output_path: outputs/run/custom_report.jsonl
```

Visualization output stores ASE-readable frames with useful arrays such as:

- `cluster_label`
- `local_cluster_label`
- `raw_atom_type`

Lifecycle report is JSONL:

- header record
- one frame record per consumed frame
- final summary record with cluster lifetimes and aggregate event counts

Load report:

```python
from graphcluster.analysis.lifecycle_report import ClusterLifecycleReport

report = ClusterLifecycleReport.from_path("outputs/toy_debug_v2/cluster_lifecycle_report.jsonl")
print(report.summary)
```

## Allegro Edges

`graphcluster` consumes pre-annotated Allegro edge metadata. It does not run
NequIP/Allegro annotation itself in current source tree.

Expected metadata keys in frame metadata or `Atoms.info`:

- `allegro_edge_indices`
- `allegro_edge_raw_energies` or legacy `allegro_edge_energies`
- `allegro_edge_scaled_energies` when `edges.energy_field: scaled`

Example:

```yaml
source:
  backend: ase
  format: traj
  path: /path/to/allegro_edges.traj
  type_map:
    1: Ga
    2: Pt

selection:
  start: 0
  stop: 100
  stride: 1

edges:
  kind: allegro
  energy_field: raw
  energy_to_weight: abs_negative_sum
  allegro_scaling:
    percentile: 99.5
    sample_edge_budget: 200000

partition:
  algorithm: leiden
  objective: cpm
  resolution: 0.08
  warm_start: true

artifacts:
  directory: outputs/allegro_run
  visualization:
    enabled: true
    backend: ase
    mode: traj
  lifecycle_report:
    enabled: true
```

Weight semantics:

- exported Allegro edges are directed inputs
- `abs_negative_sum`: positive energies ignored; negative energies become
  `abs(energy)` bond strengths
- both directions sum onto one undirected graph edge
- optional `allegro_scaling` samples prefix frames, computes chosen percentile
  of absolute edge magnitudes, and divides graph weights by that scale

Alternate `edges.energy_to_weight: signed_shifted_sum` exists for species-shift
experiments and requires `edges.species_shifts`; `edges.avg_num_neighbors` may
also be supplied.

Cluster energy tracking can use raw Allegro edge metadata even when clustering
uses geometry edges, as long as source frames carry annotations.

## Tests

```bash
pytest -q
```

On FAS RC with `nequip311`:

```bash
mamba run -n nequip311 pytest -q
```

Toy data lives at:

```text
tests/data/Ga80Pt20_129_773K_ss_1.all.bin
```

## Repository Layout

- `src/graphcluster/io`: trajectory readers and `Frame`.
- `src/graphcluster/graph`: sparse graph containers and edge builders.
- `src/graphcluster/partitioning`: partition objects and algorithms.
- `src/graphcluster/tracking`: online cluster ID synchronization.
- `src/graphcluster/analysis`: lifecycle reports and cluster energy analysis.
- `src/graphcluster/visualization`: visualization payloads and ASE writer.
- `src/graphcluster/runner.py`: streaming pipeline coordinator.
- `configs`: examples and debug configs.
- `tests`: unit/integration tests plus toy trajectory.

For agent-facing architecture and development rules, see `AGENTS.md`.

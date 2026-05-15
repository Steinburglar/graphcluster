# Refactor Plan: Split Allegro Annotation From Graph Clustering

## Decision

Separate Allegro edge annotation from normal graph clustering.

`graphcluster` should cluster exactly one source trajectory. It should not
generate derived trajectories, switch inputs mid-run, or probe multiple files to
decide what to do. Allegro annotation should become separate CLI workflow that
creates an annotated trajectory artifact first.

This favors clarity over one-command convenience. At current project stage,
that is right tradeoff.

## Target Workflow

Step 1: annotate raw trajectory.

```bash
annotate-allegro \
  --input /path/to/raw.xyz \
  --input-format xyz \
  --compiled-model /path/to/model.nequip.pt2 \
  --output /path/to/allegro_edges.traj \
  --output-format traj \
  --device cuda
```

Step 2: cluster annotated trajectory.

```bash
graphcluster /path/to/allegro_cluster.yaml --profile
```

For Allegro clustering, config source points directly at annotated artifact:

```yaml
source:
  backend: ase
  format: traj
  path: /path/to/allegro_edges.traj

selection:
  start: 0
  stop: 100
  stride: 1

edges:
  kind: allegro
  energy_to_weight: abs_negative_sum

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

## Desired End State

`graphcluster`:

- reads one file from `source.path`
- builds edges from that file
- partitions and tracks clusters
- writes artifacts
- never runs Allegro annotation
- never switches to an "effective" trajectory
- never reads raw and annotated trajectories in lockstep

`annotate-allegro`:

- reads raw trajectory
- runs compiled Allegro model
- writes ASE-readable annotated artifact
- owns all model/device/type-map options

## Config Changes

Remove from clustering config:

- `preprocess`
- `preprocess.edge_annotation`
- `mode: annotate_if_missing`
- `mode: annotate_always`
- `mode: annotate_only`
- `mode: require_precomputed`

Keep clustering schema:

- `source`
- `selection`
- `edges`
- `partition`
- `tracking`
- `artifacts`
- `profiling`

For `edges.kind: allegro`, require `source.path` to already be annotated. Fail
early if first frame lacks:

- `allegro_edge_indices`
- `allegro_edge_energies`

## Code Refactor Plan

1. Add standalone annotation CLI.

New file:

- `src/graphcluster/annotate_allegro_cli.py`

New console script:

- `annotate-allegro`

CLI args:

- `--input`
- `--input-format`
- `--compiled-model`
- `--output`
- `--output-format`
- `--device`
- `--start`
- `--stop`
- `--stride`
- repeated `--raw-type-map KEY=VALUE`
- repeated `--species-to-model-type-map KEY=VALUE`

2. Remove inline annotation from runner.

Delete runner use of:

- `prepare_allegro_input`
- `_switch_effective_trajectory`
- `trajectory_has_cell_origin`
- `switch_effective_reader` timing bucket

Runner should construct reader once and iterate it.

3. Remove or shrink `allegro_annotation.py`.

Options:

- delete module if new CLI fully replaces it
- or keep tiny helpers for parsing maps / invoking external annotator

No module function should decide clustering input.

4. Simplify reader.

Remove `reference_path` logic if it only exists for annotation handoff.

Target:

- `TrajectoryReader` reads `source.path`
- `ASETrajectorySource` reads one ASE trajectory
- no paired source/reference iteration

5. Tighten Allegro edge validation.

In `graphcluster.graph.allegro_edges`, improve error:

`edges.kind='allegro' requires source.path to point at Allegro-annotated trajectory with allegro_edge_indices and allegro_edge_energies.`

Optional: validate first frame before main loop so failure occurs before long
run starts.

6. Update docs and configs.

Update:

- `README.md`
- `context.md`
- `configs/toy_debug_v2.yaml`
- H/Pt Allegro config

Docs should show two-command workflow.

## Test Plan

Add tests:

- `annotate-allegro` passes CLI args to annotator helper
- map args parse correctly
- normal geometry clustering still works
- Allegro clustering works from pre-annotated `.traj`
- `edges.kind: allegro` with raw/non-annotated source fails clearly
- profiling output no longer includes annotation timing buckets

Remove tests:

- `annotate_if_missing`
- `annotate_always`
- `annotate_only`
- `require_precomputed`
- runner input switching
- artifact reuse inside runner
- reference trajectory fallback caused by annotation handoff

## Migration For H/Pt

New workflow:

1. Run `annotate-allegro` once to create:

`/n/home12/lsteinberger/systems/hpt/data/trajectories/annotated_allegro_edges/hpt_600k_allegro_edges.traj`

2. Set H/Pt Allegro clustering config:

```yaml
source:
  backend: ase
  format: traj
  path: /n/home12/lsteinberger/systems/hpt/data/trajectories/annotated_allegro_edges/hpt_600k_allegro_edges.traj
```

3. Run:

```bash
graphcluster --profile /n/home12/lsteinberger/systems/hpt/analysis/cluster/hpt_600k_allegro.yaml
```

Expected profiling improvement:

- no `prepare_allegro_input`
- no raw XYZ probe
- no raw XYZ reference reread
- main cost becomes reading annotated `.traj`, graph build, partition

## Why This Better

- one command = one job
- no hidden preprocessing
- no surprise file switching
- no giant raw XYZ probe during clustering
- easier profiling
- easier scientific debugging
- annotated artifacts reusable across many cluster configs

Main cost: user runs two commands. Worth it.

## Implementation Status

Initial split implemented:

- added `annotate-allegro`
- removed runner-side annotation and input switching
- simplified ASE source to read one trajectory
- updated H/Pt Allegro config to point directly at annotated `.traj`
- added tests for standalone CLI and preannotated Allegro clustering

Still useful follow-up:

- update README examples
- audit any older side configs outside this repo that still mention `preprocess`

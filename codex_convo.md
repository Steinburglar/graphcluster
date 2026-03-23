Lucas Steinberger
03/13/2024
MIR

This is a work in progress Repository, containing code that allows one to run graph clustering algorithms on molecular dynamics tranjectories. it is designed from the start to be able to integrate with visualizing software at the back end.

The main data entry should be either a trajectory file, containing positions from md simulations, or perhaps a a list of similarity matrices, representing pairwise distance, energies, or some other 1D metric between atoms.

The main output should be a partition of the graph. the repo should also probably have its own visualization tools, but it should also be designed to be able to export the partition in a format that can be read by other software.


The structure I have in mind is as follows:


Data:
- Trajectory files (e.g. .xtc, .dcd, .trr)
- (optional) list of similarity matrices (e.g. .csv, .npy) for each frame, representing pairwise distances, energies, or some other 1D metric between atoms.

The reason we might want to have similarity matrices as input is that sometimes we might want to cluster based on some specific metric that isnt present on its own in the trajectory file. For example, we might want to cluster based on edge energies predicted by allegro, which would require pulling those energies from the simulation data.

either way, whatever we get will get converted into a similarity matrix, which will be the main data structure we work with for clustering.


These frames will get passed into a Partitioner object, which will be responsible for running the clustering algorithms. The Partitioner will be customizable to run different clustering algorithms, with different hyperparameters, and it will also be designed to be able to run on different backends (e.g. CPU, GPU, distributed computing). It will output a partition of the graph, which is a mapping of each node (atom) to a cluster label. There may also be some metadata passed with the partition, such as the number of clusters, the size of each cluster, etc, as well as all the relevant parameters used to make that partition.

Finally, there should be some Analyze tools, which can take in the partition and visualize it or some calculable data about it. this should probably be done in combination with some visualization software, such as VMD or PyMOL, but it should also be designed to be able to export the partition in a format that can be read by other software. For example, we might want to export the partition as a .csv file, where each row represents an atom and its corresponding cluster label. We might also want to export some visual representation of the partition, such as a color-coded structure file that can be loaded into VMD or PyMOL.

im not clear on what the main acess point to this pipeline should be. there should probably be a command line tool we can call, but also jupyter notebooks may be appropriate for development and testing. There should definitly be a config file, like config.yaml, that specifies the appropriate parameters of the run. a non exhaustive list of parameters that should be included in the config file are:
- input file paths (trajectory files, similarity matrices)
- clustering algorithm to use (e.g kmeans, leiden, spectral clustering, etc)
- hyperparameters for the clustering algorithm (e.g. number of clusters, resolution parameter, etc)
- output file paths (for the partition, visualizations, etc)


Is it a good Idea to build factory functions to build the Partitioner and Analyzer objects based on the config file?

Here are some firther breakdowns of hopw the partitioner class/module might work. 

Partitioner class:
 - Overarching class, responsible for running the clustering algorithms on the input data, and returning a partition.

    Data typoes used by the Partitioner:
   - SimilarityMatrix: a sparse, 2D array representing pairwise similarities between atoms. Can create a class that acts as a wrapper for this fundamental structure.
   - Partition: a mapping of each node (atom) to a cluster label. Can create a class that acts as a wrapper for this fundamental structure, and also contains metadata about the partition (e.g. number of clusters, size of each cluster, etc).
   - ClusteringAlgorithm: an abstract class that defines the interface core for clustering algorithms. Each specific clustering algorithm (e.g. kmeans, leiden, spectral clustering) will be a subclass of this abstract class, and will implement the specific logic for that algorithm.

What do you think so far? what needs to be flushed out, and what might a good directory structure be?

## Codex review

This is a strong starting outline. The high-level decomposition into input handling, partitioning, and downstream analysis/export makes sense, and it is a good sign that you are already thinking about configuration and visualization interoperability.

The biggest thing that needs to be flushed out is the exact scientific object being clustered. Right now there are a few possible interpretations:

- each frame becomes a graph over atoms, and you cluster atoms within that frame
- each trajectory becomes a time series of graphs, and you want partitions per frame
- you want temporally consistent communities across frames, not just independent framewise partitions

Those are meaningfully different problems, and the design will change depending on which one you want. In particular, if you want to compare partitions across frames, you will likely need some notion of temporal label alignment or cluster tracking, because cluster IDs from most algorithms are arbitrary from run to run.

I would also be careful about making a dense similarity matrix the universal core representation. For molecular systems, pairwise atom-atom data scales as `O(N^2)` per frame, which gets expensive very quickly. That may still be fine for some systems, but as a default design it can become a bottleneck in both memory and I/O. A better abstraction might be something more general like a graph representation that can be backed by:

- a sparse adjacency matrix
- an edge list with weights
- a k-nearest-neighbor graph
- a dense matrix only when the problem size is small enough

That gives you more flexibility and keeps the core architecture from being locked to the heaviest possible representation.

One thing that seems overlooked right now is topology. In MD workflows, a trajectory file by itself is often not enough. You may also need a topology or structure file such as `.pdb`, `.gro`, `.psf`, or similar, depending on the toolchain. If the nodes are atoms, residues, or coarse-grained sites, that should be explicit early, because it affects graph construction, export, and visualization.

Relatedly, there are a few preprocessing choices that will probably matter a lot and deserve first-class treatment in the design:

- atom or residue selection
- frame slicing / stride
- periodic boundary conditions
- alignment or superposition before computing geometry-based metrics
- unit conventions
- optional coarse-graining from atoms to residues / groups

Those details can change the graph substantially, so they should probably live in the config rather than being hidden inside implementation code.

On the algorithm side, I would avoid grouping everything under "graph clustering" unless the method actually operates on graphs. `leiden` and spectral clustering fit naturally, but `kmeans` is a bit different: it usually operates on feature vectors or embeddings, not directly on a graph. That does not mean you should exclude it, but it may be cleaner to represent the pipeline as:

`input -> graph construction -> optional embedding / feature extraction -> partitioning -> analysis / export`

That structure lets you support both true graph-native algorithms and feature-based clustering methods without muddying the interface.

For the `Partitioner`, I think the concept is reasonable, but I would not make it too heavyweight too early. A good best-practice direction is:

- keep algorithms behind a small common interface
- make the orchestration layer thin
- keep config validation separate from execution
- avoid mixing backend concerns directly into the core domain objects at the start

In other words, CPU/GPU/distributed support is worth planning for, but I would not let that shape the whole architecture before you know where the actual bottlenecks are. It is usually better to separate "what algorithm runs" from "how the computation is executed."

On your factory-function question: yes, a factory or registry approach is a good idea, especially for building algorithms, graph constructors, analyzers, and exporters from config. I would prefer a registry-based design over one giant factory with many `if/elif` branches, because it scales better as the number of algorithms grows. If you eventually validate config into structured objects, that becomes even cleaner.

I would also be cautious about introducing wrapper classes for everything. A `Partition` object with metadata is very likely useful. A `SimilarityMatrix` wrapper may or may not be worth it. If a wrapper enforces invariants, carries provenance, or standardizes conversions, it is helpful. If it mostly duplicates what `numpy` or `scipy.sparse` already gives you, it may add complexity without much payoff. My instinct would be:

- `Partition`: yes, likely worthwhile
- `ClusteringAlgorithm` interface: yes
- matrix/graph wrapper: only if it adds real value beyond the underlying array/sparse type

For the analysis side, I would separate analysis from visualization/export. That usually stays cleaner over time. For example:

- analysis computes statistics, comparisons, quality metrics, temporal stability, etc.
- export writes machine-readable outputs
- visualization adapters generate files or annotations for tools like VMD or PyMOL

That separation will make the codebase easier to test and easier to extend.

A few additional things I think you may have to deal with that are not yet called out explicitly:

- reproducibility: random seeds, config capture, versioned outputs
- performance: caching, chunked processing, and not loading an entire long trajectory into memory at once
- output schema: whether partitions are per-frame, per-atom, per-residue, and how metadata is stored
- evaluation: how you will decide whether a partition is "good" for your scientific use case
- interoperability: whether you want to center the project around `MDAnalysis`, `mdtraj`, `NetworkX`, `igraph`, `scipy`, or some mix
- testing: small toy systems and fixed expected outputs will be very important here

I also think the main entrypoint question is worth settling early. My recommendation would be:

- a CLI is the primary reproducible entrypoint
- notebooks are for exploration, prototyping, and demos
- the core pipeline stays importable as a Python library

That tends to give the cleanest balance between usability and maintainability.

Finally, I would expand the config concept a bit. In addition to the items you listed, I would expect the config to eventually include:

- topology / structure inputs
- node definition (`atom`, `residue`, or custom group)
- preprocessing options
- graph construction parameters
- frame range / stride
- random seed
- output format choices
- logging / run metadata

## Proposed repository structure

```text
graphcluster/
├── README.md
├── pyproject.toml
├── configs/
│   ├── default.yaml
│   ├── data/
│   │   ├── trajectory.yaml
│   │   └── similarity_matrices.yaml
│   ├── graph/
│   │   ├── distances.yaml
│   │   ├── contacts.yaml
│   │   └── energies.yaml
│   ├── partition/
│   │   ├── leiden.yaml
│   │   ├── spectral.yaml
│   │   └── kmeans.yaml
│   ├── analysis/
│   │   ├── summary.yaml
│   │   └── temporal_stability.yaml
│   └── export/
│       ├── csv.yaml
│       ├── npz.yaml
│       └── vmd.yaml
├── src/
│   └── graphcluster/
│       ├── __init__.py
│       ├── cli.py
│       ├── pipeline/
│       │   ├── run.py
│       │   └── context.py
│       ├── io/
│       │   ├── trajectories.py
│       │   ├── topology.py
│       │   ├── matrices.py
│       │   └── outputs.py
│       ├── preprocessing/
│       │   ├── selection.py
│       │   ├── alignment.py
│       │   ├── pbc.py
│       │   └── coarse_grain.py
│       ├── graph/
│       │   ├── builders.py
│       │   ├── representations.py
│       │   └── features.py
│       ├── partitioning/
│       │   ├── base.py
│       │   ├── registry.py
│       │   ├── leiden.py
│       │   ├── spectral.py
│       │   └── kmeans.py
│       ├── analysis/
│       │   ├── summary.py
│       │   ├── quality.py
│       │   └── temporal.py
│       ├── export/
│       │   ├── csv.py
│       │   ├── npz.py
│       │   ├── pymol.py
│       │   └── vmd.py
│       ├── models/
│       │   ├── partition.py
│       │   ├── metadata.py
│       │   └── run_config.py
│       └── utils/
│           ├── logging.py
│           └── validation.py
├── notebooks/
│   ├── exploratory_analysis.ipynb
│   └── prototype_pipeline.ipynb
├── tests/
│   ├── conftest.py
│   ├── test_graph_builders.py
│   ├── test_partitioning.py
│   ├── test_pipeline.py
│   └── data/
│       └── toy_system/
├── examples/
│   ├── sample_configs/
│   └── demo_outputs/
└── docs/
    ├── architecture.md
    ├── config.md
    └── algorithms.md
```

If you want a lighter first version, I would simplify it to the following conceptual layout:

- `configs/` for run configuration
- `src/graphcluster/io/` for reading trajectories, topologies, and matrices
- `src/graphcluster/graph/` for graph construction
- `src/graphcluster/partitioning/` for clustering algorithms and interfaces
- `src/graphcluster/analysis/` for statistics and evaluation
- `src/graphcluster/export/` for VMD/PyMOL/CSV-style outputs
- `tests/` for small deterministic test cases
- `notebooks/` only for experiments, not core functionality

I think that version will scale well while still keeping responsibilities clean.

## Follow-up answers

### On graph construction before feature extraction

This is a good question, and I should be more precise here. In your setting, "graph construction" and "feature extraction" are not always cleanly separate steps.

If your nodes are atoms, then the first part of graph construction is easy: the nodes already exist once you decide which atoms are included.

The harder part is the edges. There are a few different possibilities:

- the graph is fully connected, and every atom pair gets an edge
- the graph uses a cutoff, so atoms only get an edge if they are close enough
- the graph follows some known structure, like bonded neighbors
- the graph is built from a k-nearest-neighbor rule

Once you pick one of those rules, you have the graph connectivity. After that, you can attach a scalar value to each edge, such as:

- distance
- interaction energy
- similarity score
- some other scalar derived from the frame

In that version of the pipeline, graph construction comes first, and feature extraction means "compute the value that lives on each existing edge."

But there is also another case, and I think this may be closer to what you have in mind. Sometimes the quantity you compute is itself what determines whether an edge exists. For example:

- compute all pairwise distances
- only keep edges where the distance is below a cutoff

In that case, you do need to compute some pairwise quantity before the final graph is fully defined. So the more accurate pipeline for your project may be:

`raw trajectory -> pairwise scalar quantity -> choose which edges exist -> build weighted graph -> partition`

So I would revise what I said earlier as follows: for your use case, it is probably better to think in terms of:

- node definition
- pairwise quantity computation
- graph construction from that quantity
- optional extra edge/node features
- partitioning

That fits your "edges are 1D things" idea much better.

### On atom types

I think it is completely reasonable not to distinguish atom types at first.

If your immediate scientific question is about partitioning based on geometry or edge energies, then atom identity may not be necessary for a first working version. You can treat all atoms as nodes and store atom type only as optional metadata later.

A simple way to think about it is:

- required now: node index, edge scalar, frame identity
- optional later: atom type, residue name, residue index, chain, etc.

That keeps the first version focused. If later you want atom type to matter, there are a few ways it could enter:

- as node metadata for analysis and coloring
- as a filter when selecting which atoms are included
- as an extra feature used by some algorithms
- as a rule affecting graph construction

So I would not force atom types into the core design yet unless you already know you need them.

### On the config layout

Yes, for actual usage I agree with you: there should usually be one config per run.

What I was suggesting with the `configs/` subfolders was not "many configs must be provided to run the program." I was suggesting a way to organize reusable config pieces or templates if the project grows.

There are basically two reasonable levels here:

#### Simple version

Have one file per run, for example:

- `configs/run1.yaml`
- `configs/test_leiden.yaml`
- `configs/energy_based_partition.yaml`

Each one contains everything needed for that run. This is the simplest and probably the best place for you to start.

#### More modular version

You still have one config per run, but that run config is assembled from reusable pieces, such as:

- a default data section
- a specific graph-building section
- a specific clustering section
- a specific export section

That is useful when you start repeating yourself across many experiments.

So yes, your interpretation is right: I was suggesting default/boilerplate sections for different types of runs, not saying that one run should require many separate files unless you want that behavior.

If I were optimizing for a clean beginner-friendly first version, I would do this:

- start with one YAML file per run
- keep the schema very explicit
- only split into reusable config sections later if you notice lots of duplication

### On what I meant about the `Partitioner` class

What I was trying to say is: the `Partitioner` should probably do one main job, and not become the place where every project concern gets stuffed together.

In beginner-friendly terms, I would think of it like this:

- input handling reads files
- preprocessing prepares the data
- graph construction builds the graph
- the `Partitioner` runs a clustering method on that graph
- analysis/export deal with the result afterward

So the `Partitioner` should mainly be the piece that says:

"I have a graph, I know which algorithm to use, and I will return a partition."

What I do **not** want the `Partitioner` to become is something that also:

- reads trajectory files
- validates the whole config
- decides output folder structure
- handles visualization
- manages every CPU/GPU/distributed detail directly
- stores lots of unrelated state

That is what I meant by not making it too heavyweight.

Here is the same idea in more concrete terms.

#### 1. Keep algorithms behind a small common interface

This just means each clustering algorithm should look similar from the outside.

For example, even if the internal math is very different, you want to be able to think:

- Leiden takes a graph and returns labels
- spectral clustering takes a graph and returns labels
- some future method takes a graph and returns labels

That way the `Partitioner` can call any of them in the same general way.

#### 2. Make the orchestration layer thin

"Orchestration layer" just means the piece that coordinates the steps.

A thin `Partitioner` might:

- receive a graph
- receive algorithm settings
- create the right algorithm object
- run it
- package the result into a `Partition`

That is enough. It does not need to own the entire pipeline.

#### 3. Keep config validation separate from execution

This means:

- one part of the program checks whether the config makes sense
- another part of the program actually runs the clustering

This separation helps a lot because it makes debugging easier. If something fails, you can tell whether:

- the config was invalid
- the data was invalid
- the clustering step failed

instead of having everything mixed together in one big class.

#### 4. Avoid baking backend concerns into the core class too early

What I meant here is: do not design the whole `Partitioner` around CPU/GPU/distributed execution from day one unless you already need it.

It is fine to leave room for that later. But for a first version, it is usually better if the `Partitioner` is mostly about the scientific task, not the hardware task.

So instead of saying:

"the `Partitioner` is responsible for clustering, GPU scheduling, distributed communication, memory management, data loading, and export"

I would rather say:

"the `Partitioner` is responsible for turning a graph into a partition, and some lower-level utilities may later help specific algorithms run efficiently"

### A simpler design I think fits your current project

Based on what you clarified, I think the cleanest first mental model is:

`trajectory or pairwise data -> edge scalar computation -> graph builder -> clustering algorithm -> Partition object -> analysis/export`

And in plain terms:

- atoms are the nodes
- edges carry one scalar value
- atom type is optional metadata, not a core requirement
- one config file per run is enough to start
- the `Partitioner` should stay focused on "run clustering on a graph and return labels"

I think that is a strong and practical V1 design.

## More follow-up answers

### On the temporal component, warm starts, and meaningful labels

Yes, I think using the previous frame's partition as the starting guess for the next frame is a very good idea.

There are really two separate goals here:

- use the old partition to help compute the new one
- keep labels stable and meaningful across time

Those are related, but they are not the same problem.

#### 1. Warm-starting the next partition

This means:

- cluster frame `t`
- take that partition
- use it as the initial guess for frame `t+1`

That is a sensible approach because consecutive MD frames are usually similar, so the previous partition contains useful information.

This is also supported by some graph clustering tooling. For example, `python-igraph` exposes Leiden with an `initial_membership` argument, which is exactly the kind of hook you would want for warm starts: [python-igraph Leiden docs](https://python.igraph.org/en/latest/api/igraph.community.html). The `leidenalg` package also exposes lower-level optimisation routines and temporal/multiplex support: [leidenalg GitHub](https://github.com/vtraag/leidenalg), [leidenalg multiplex/temporal docs](https://leidenalg.readthedocs.io/en/latest/multiplex.html).

One thing to be careful about: warm starts can make the method "sticky." That can be good if you want temporal smoothness, but it can also make the algorithm slow to notice a real structural change. So I would probably treat this as a tunable design choice, not something always forced on.

#### 2. Keeping labels meaningful across frames

This is the harder part, because community labels coming out of clustering algorithms are usually arbitrary. Label `3` at frame `t` does not automatically mean the same thing as label `3` at frame `t+1`.

The cleanest practical approach is to separate:

- the algorithm's raw community IDs for a single frame
- your own persistent cluster track IDs across time

In other words, the clustering algorithm gives you a frame-local partition, and then you run a second step that says:

"Which new cluster is the continuation of which old cluster?"

For your problem, a good V1 label-tracking strategy would be:

1. cluster frame `t`
2. cluster frame `t+1`, possibly warm-started from frame `t`
3. compute overlap between old and new clusters
4. match old clusters to new clusters using an overlap score
5. assign persistent track IDs based on that matching

The overlap score could be something simple like:

- number of shared atoms
- Jaccard overlap
- overlap normalized by old cluster size or new cluster size

Then you can detect events like:

- continuation: one old cluster matches one new cluster strongly
- split: one old cluster matches several new clusters
- merge: several old clusters match one new cluster
- birth: a new cluster has no strong parent
- death: an old cluster has no strong child

I think this "cluster track" idea is more important than trying to force the raw labels themselves to stay stable.

#### 3. A stronger future option: temporal community detection instead of pure frame-by-frame clustering

If you eventually want the time dimension to be part of the optimisation itself, not just a post-processing step, then a better long-term approach is temporal or multilayer community detection.

The basic idea is:

- each MD frame is one graph slice
- the same atom in adjacent frames is connected by a temporal coupling edge
- the optimisation balances within-frame clustering with between-frame consistency

This is attractive because it naturally encourages label continuity over time. The `leidenalg` docs explicitly describe multiplex and temporal community detection over multiple time slices: [leidenalg temporal docs](https://leidenalg.readthedocs.io/en/latest/multiplex.html).

If I were trying to build this project in stages, I would probably do:

- V1: frame-by-frame clustering + warm start + overlap-based label tracking
- V2: temporal/multislice clustering for stronger consistency

That gives you a path that starts simple but still points toward a more principled temporal model.

#### 4. One modeling recommendation

I would explicitly distinguish in the design between:

- `partition`: the cluster assignment for one frame
- `cluster_tracks`: the correspondence of clusters across frames

That will make the temporal logic much easier to reason about.

### On what "graph construction" means here

You are right to push on this, because "graph construction" is a vague phrase unless we say exactly what is being constructed.

In your project, for a single frame, I think graph construction just means:

- decide which atoms are the nodes
- decide which atom pairs should have edges
- decide what scalar value each edge gets
- store that result in a graph-friendly format

Since your nodes are atoms and your edges carry one scalar value, graph construction is basically "build the edge set and its weights."

So for your setting, the phrase "edge construction" or "neighbor graph construction" might actually be clearer than the more abstract phrase "graph construction."

Some concrete possibilities are:

#### Option A: bonded graph

- nodes = atoms
- edges = bonded atom pairs from topology / bond list
- edge value = bond distance, bond energy, force, etc.

This is especially natural if your data already contains a meaningful bond network.

#### Option B: cutoff graph

- nodes = atoms
- edges = atom pairs within some distance cutoff
- edge value = distance, transformed similarity, interaction energy, etc.

This is common in MD-style neighborhood analysis and is much cheaper than all-pairs.

#### Option C: k-nearest-neighbor graph

- nodes = atoms
- edges = each atom connects to its `k` nearest neighbors
- edge value = some scalar for those pairs

This can help keep the graph sparse and roughly uniform in degree.

#### Option D: imported edge list

- nodes = atoms
- edges = whatever pair list is already produced by your simulation or preprocessing
- edge value = the scalar stored for that pair

This may actually be the cleanest path if LAMMPS or some post-processing step can already export the pairwise quantities you care about.

So in plain terms: graph construction is not some extra mysterious stage. It is just the step where you decide which pairs of atoms count as connected for clustering, and what number lives on each connection.

### On whether a dataloader is needed

Yes, I think some kind of streaming reader is probably needed.

I might not call it a "dataloader" at first unless you want an ML-style interface. But conceptually, yes: you probably want a component that iterates through a trajectory frame-by-frame or chunk-by-chunk without loading the whole thing into memory.

For a first version, I think a good abstraction would be something like a `TrajectoryReader` or `FrameIterator` that yields:

- frame index / time
- atom positions
- box / periodic boundary info
- topology or bond info if available
- optional auxiliary per-edge or per-atom data

Then downstream code can build the graph for that frame and cluster it.

This matters because MD trajectories can get large very quickly, and you probably do **not** want the default behavior to be:

- load every frame
- build every graph
- hold everything in memory

A streaming design gives you:

- lower memory use
- easier chunked processing
- easier caching later
- a cleaner place to add stride, frame ranges, and subsampling

So yes, I think this is something you may have overlooked slightly, and it is important.

### Existing code worth checking for LAMMPS post-processing

I checked current docs, and I do think there is existing tooling you can build on, even if I did **not** find an obvious off-the-shelf package that already does exactly "temporal graph community detection on LAMMPS trajectories with label tracking."

Here are the pieces that look most relevant:

#### 1. MDAnalysis

[MDAnalysis](https://docs.mdanalysis.org/2.8.0/documentation_pages/coordinates/LAMMPS.html) can read LAMMPS DATA, DCD, and dump files, and its docs show the normal frame-iteration pattern over `u.trajectory`. This looks like a strong candidate for the data access layer of your project.

Why it looks useful here:

- good fit for frame-by-frame streaming
- Python-native
- built around analysis workflows
- already understands LAMMPS trajectory formats

One detail to watch: its LAMMPS docs note that units may need to be specified explicitly, because they cannot always be autodetected from the files.

#### 2. LAMMPS local bond output

If your edge scalar is something like bond distance or bond energy, LAMMPS itself may already be able to export much of what you need. The current docs for [`compute bond/local`](https://docs.lammps.org/compute_bond_local.html) show that it can output values such as `dist`, `engpot`, and `force`, and the [`dump local`](https://docs.lammps.org/dump.html) docs show how to write those local bond quantities to file.

That is important because it suggests you may not need to reconstruct every edge quantity from scratch in Python if LAMMPS can emit it directly.

#### 3. OVITO

[OVITO](https://docs.ovito.org/reference/pipelines/modifiers/cluster_analysis.html) is worth checking both for visualization and as a baseline post-processing tool.

Two reasons it stands out:

- it already has built-in cluster analysis based on distance or bond connectivity
- its Python docs show loading a LAMMPS data file plus trajectory, and even loading varying bond topology from a `dump local` file with bond length and energy columns: [OVITO LoadTrajectoryModifier example](https://docs.ovito.org/python/modules/ovito_modifiers.html)

I do **not** think OVITO replaces your project, because its built-in cluster analysis is more like connected-component clustering than general weighted graph community detection. But it looks very useful for:

- inspection
- visualization
- exporting baseline cluster assignments
- prototyping around LAMMPS bond/local output

#### 4. freud

[freud](https://freud.readthedocs.io/en/nanobind/modules/cluster.html) is also worth looking at. It is very strong on simulation-box geometry, neighbor finding, and clustering over neighbor networks.

I would think of freud mainly as helpful for:

- neighbor finding
- cutoff graph construction
- periodic boundary handling

Like OVITO, it is not the same as a full weighted community-detection framework, but it could save you work on the geometric side of graph construction.

#### 5. Pizza.py

[Pizza.py](https://lammps.github.io/pizza/doc/Manual.html) is older, but it is still explicitly documented as a collection of pre- and post-processing tools for LAMMPS. I would treat it as "worth knowing exists," though my guess is that MDAnalysis and OVITO are more likely to be the strongest foundations for a new project in Python.

### My current best guess

My current best guess is:

- use MDAnalysis or a similar library as the trajectory-reading layer
- optionally use LAMMPS `compute bond/local` + `dump local` when your edge quantities already exist inside the simulation
- use OVITO as a visualization / sanity-check companion
- build the actual temporal partition + label-tracking logic yourself, because that still seems to be the gap

So I do think there is reuse available, but I also think your project is still justified because the exact combination of:

- MD trajectory input
- graph/community partitioning
- temporal warm starts
- persistent cluster identity tracking

does not seem to be neatly covered by one existing tool.

## Light structure revision

### On whether the cluster tracker should take a trajectory of partitions

Yes, I think your instinct is right.

A cluster tracker should not really be thought of as something that only makes sense on one partition. Persistent cluster IDs only become meaningful when you compare partitions across multiple frames.

So I would think of the temporal pieces like this:

- `Partition`: cluster labels for one frame
- `PartitionTrajectory`: an ordered list of `Partition` objects across frames
- `ClusterTracker`: logic that takes partitions across time and assigns persistent cluster IDs / events
- `ClusterTracks`: the tracked result across the trajectory

In practice, the tracker does not necessarily need the **entire** trajectory all at once. It could operate incrementally:

- read frame `t`
- compute partition `t`
- compare it to partition `t-1`
- update persistent IDs

That is probably the best way to handle large trajectories.

So I would say:

- conceptually, tracking belongs to a trajectory of partitions
- computationally, it can be implemented online, one frame at a time

That keeps the logic correct without forcing everything into memory.

### On the core graph structure

Agreed. If the graph is sparse by nature, then the core graph structure should be a sparse weighted matrix.

More specifically, I think the default internal representation should be something like:

- sparse adjacency / weight matrix
- one frame at a time
- undirected for now
- weighted by your scalar edge quantity

And depending on the library choices, it may also be useful to support a paired edge-list view for interoperability, but the canonical internal object should be the sparse weighted graph representation.

That means the earlier "dense similarity matrix" language should now really be replaced with:

- sparse weighted adjacency matrix
- optionally symmetric for undirected graphs
- derived from trajectory geometry, LAMMPS local outputs, or future Allegro-derived edge data

I think that is a much better fit for your problem.

### Revised light repository structure

With the new concerns in mind, this is the light structure I would recommend now:

```text
graphcluster/
├── README.md
├── pyproject.toml
├── configs/
│   ├── example.yaml
│   └── lammps_allegro_example.yaml
├── src/
│   └── graphcluster/
│       ├── __init__.py
│       ├── cli.py
│       ├── pipeline.py
│       ├── io/
│       │   ├── trajectory_reader.py
│       │   ├── frame.py
│       │   └── lammps.py
│       ├── graph/
│       │   ├── sparse_graph.py
│       │   ├── graph_builder.py
│       │   ├── trajectory_edges.py
│       │   └── allegro_edges.py
│       ├── partitioning/
│       │   ├── partitioner.py
│       │   ├── algorithms.py
│       │   ├── partition.py
│       │   └── partition_trajectory.py
│       ├── tracking/
│       │   ├── cluster_tracker.py
│       │   └── cluster_tracks.py
│       ├── export/
│       │   ├── csv_export.py
│       │   └── vmd_export.py
│       └── utils/
│           ├── config.py
│           └── logging.py
├── tests/
│   ├── test_graph_builder.py
│   ├── test_partitioner.py
│   ├── test_cluster_tracker.py
│   └── data/
│       └── toy_system/
└── notebooks/
    └── prototype.ipynb
```

### What each part means now

- `io/trajectory_reader.py`
  Streaming frame reader. This should avoid loading the full MD trajectory into memory.

- `io/frame.py`
  A frame-level data object containing the minimum information needed downstream, such as frame index, time, positions, and box information.

- `io/lammps.py`
  LAMMPS-specific readers and helpers. This is also a natural place to later support data coming from deeper in the simulation stack.

- `graph/sparse_graph.py`
  The core graph data structure for one frame: a sparse weighted adjacency matrix plus graph metadata.

- `graph/graph_builder.py`
  Builds the sparse graph for one frame from whichever edge source is selected.

- `graph/trajectory_edges.py`
  Computes edge weights from standard trajectory-derived quantities like distances, cutoffs, or neighbor rules.

- `graph/allegro_edges.py`
  Placeholder for the longer-term path where edge weights come from Allegro-related data pulled out of the LAMMPS workflow.

- `partitioning/partition.py`
  One frame's partition and metadata.

- `partitioning/partition_trajectory.py`
  A trajectory-level container for ordered partitions. Even if you process online, this is still a useful conceptual object.

- `partitioning/partitioner.py`
  The component that takes one sparse weighted graph, optionally takes the previous partition as a warm start, and produces a new partition.

- `tracking/cluster_tracker.py`
  Temporal label matching logic across partitions.

- `tracking/cluster_tracks.py`
  Persistent cluster identities and temporal events such as continuation, split, merge, birth, and death.

- `pipeline.py`
  The high-level control flow, something like:

  `read frame -> build sparse graph -> partition -> track IDs -> save/export`

### How I would think about the data flow now

For one frame:

`Frame -> SparseWeightedGraph -> Partition`

Across time:

`Partition(t-1) + Partition(t) -> ClusterTracker -> updated ClusterTracks`

Across the whole run:

`TrajectoryReader -> frame stream -> graph builder -> partitioner -> tracker -> exporters`

### Why this version seems like the right "light" one

I think this keeps the project small while still making room for the parts that actually matter for your idea:

- sparse weighted graphs are first-class
- temporal tracking is first-class
- warm starts are easy to support
- streaming data access is built in from the start
- there is an explicit place for future Allegro/LAMMPS-derived edge sources

That feels like the cleanest V1 architecture to me.

## More thoughts on endpoints: loading, visualization, and the main processing loop

I agree with your instinct here: the most important thing to build next is probably not the middle of the algorithm stack, but the two ends of the system:

- a reliable way to stream MD frames in
- a reliable way to visualize a frame together with a partition

That will let you start testing the project as a real tool much earlier.

### On warm start vs tracking

I think the conclusion here is still:

- warm start and cluster tracking are distinct concerns
- they are related enough that we may want to preserve some warm-start metadata
- but this does **not** force a major redesign right now

The tracker still has access to a trajectory of partitions, which is the most important thing. If later we decide that warm-start lineage information is useful, we can add that as metadata on the `Partition` object without changing the overall architecture much.

So I do **not** think we need to redesign around that immediately. I think the right move is to keep the modular design and come back to richer temporal metadata once we have real data flowing through the system.

### Is ASE a good enough starting platform?

I think the answer is: yes, ASE is a good enough starting platform, but probably not the final answer for every part of the project.

Why ASE seems like a good V1 choice:

- your lab already uses it, so it is likely to fit existing habits and infrastructure
- ASE has a very convenient `Atoms` object, which is a good common structure for frame-level geometry
- ASE has trajectory support and simple iteration patterns through `ase.io.trajectory.Trajectory`
- ASE has built-in visualization entrypoints through `ase.visualize.view(...)` and `ase-gui`
- ASE can interface with external viewers such as VMD and NGLView, not just its own GUI
- ASE has code for reading LAMMPS dump files in `ase.io.lammpsrun`

Relevant docs:

- ASE trajectory docs: https://ase-lib.org/ase/io/trajectory.html
- ASE visualization docs: https://ase-lib.org/ase/visualize/visualize
- ASE GUI docs: https://ase-lib.org/ase/gui/gui.html
- ASE LAMMPS dump reader source/docs: https://ase-lib.org/_modules/ase/io/lammpsrun.html

So if the question is:

"Can ASE get us to the point where we can load frames, inspect them, and start prototyping partition overlays?"

then I think the answer is yes.

But I would still be a little cautious about making ASE the only long-term foundation.

Why I would be cautious:

- ASE is a very good atomistic structure platform, but it is not primarily an MD trajectory analysis framework
- for LAMMPS-centric trajectory reading and MD analysis workflows, MDAnalysis is more specialized
- for visualization and rendering of simulation data, OVITO is much stronger and more flexible

Relevant docs:

- MDAnalysis LAMMPS trajectory docs: https://docs.mdanalysis.org/2.8.0/documentation_pages/coordinates/LAMMPS.html
- OVITO rendering docs: https://www.ovito.org/docs/current/python/introduction/rendering.html
- OVITO LAMMPS integration docs: https://www.ovito.org/docs/current/python/modules/ovito_io_lammps.html

So my current recommendation would be:

- use ASE as a very reasonable V1 platform for prototyping frame objects and simple visualization
- keep the internal `Frame` abstraction independent of ASE so we can later swap readers if needed
- be open to using MDAnalysis for loading and OVITO for richer visualization if ASE starts to feel limiting

In other words: ASE is a good place to start, but I would not tightly bind the whole project to ASE-specific objects everywhere.

### What I would actually do for V1

If we want a practical, low-friction start, I would do this:

- loader prototype: ASE-backed
- visualizer prototype: ASE-backed
- internal interfaces: library-agnostic

That means:

- the loader may internally produce `ase.Atoms` objects at first
- the visualizer may internally use `ase.visualize.view(...)` or an ASE-friendly notebook viewer
- but the rest of the project should talk to our own `Frame` and `Partition` objects

That keeps development fast while preserving the freedom to replace pieces later.

### Should the dataloader be a generator?

Yes, I think it should behave like a generator or at least like a Python iterable.

The important design property is:

- you can loop over frames one at a time
- you do not need to hold the full trajectory in memory

So conceptually I would want something like:

- `for frame in frame_source: ...`

That is the right default for MD trajectories.

### Should we base it on PyTorch `DataLoader` design?

I would say: borrow the good ideas, but do **not** literally build on top of PyTorch `DataLoader` as the base abstraction.

What is worth borrowing from PyTorch:

- dataset / iterable separation
- lazy loading
- clean iteration API
- optional future hooks for batching, workers, or prefetching

What I would avoid copying too literally:

- training-oriented naming
- assumptions about batching being the default
- assumptions about shuffling
- a heavy dependency on PyTorch if the project itself is not fundamentally a PyTorch project

This project is not training a model. It is processing a trajectory in order. That means the most natural base abstraction is probably something like:

- `FrameSource`
- `TrajectoryReader`
- `FrameIterator`

rather than `Dataset` + `DataLoader` in the PyTorch sense.

So my recommendation would be:

- implement a simple iterable reader first
- keep the API Pythonic and streaming-oriented
- only add worker/prefetch ideas later if performance demands it

### What should touch the dataloader?

I think you are exactly right to ask this in "trainer" terms, because there really is an analogous coordinating object here. It is just not a trainer.

I would introduce a top-level object with a name like:

- `TrajectoryPartitionRunner`
- `PartitionPipeline`
- `RunEngine`

Of those, I think `TrajectoryPartitionRunner` or `PartitionPipeline` are the clearest.

Its job would be to coordinate the main loop:

1. ask the frame source for the next frame
2. convert that frame into a graph
3. run partitioning on the graph
4. update temporal tracking
5. send results to visualization and/or export

That is very similar in spirit to a trainer loop, except the loop is over frames instead of optimization steps.

So the structure would be something like:

- `TrajectoryReader` yields `Frame`
- `GraphBuilder` turns `Frame` into `SparseWeightedGraph`
- `Partitioner` turns `SparseWeightedGraph` into `Partition`
- `ClusterTracker` links `Partition` objects across time
- `Visualizer` or `Exporter` consumes `Frame + Partition + ClusterTracks`
- `TrajectoryPartitionRunner` coordinates the whole flow

That gives the project a clear "owner" of the computational loop.

### I think the visualizer deserves first-class status

The more I think about it, the more I think the visualizer should be treated as a first-class component in the architecture, not just an afterthought under export.

Because for your workflow, visualization is not just presentation. It is part of development and validation. You will likely need to visually inspect whether a partition is scientifically sensible.

So I would probably refine the architecture slightly to include:

- `visualization/`

separate from:

- `export/`

That lets you support both:

- quick interactive development views
- durable file export for other tools

### My current recommendation

If I had to choose a V1 path right now, I would do this:

- use ASE as the first loading and visualization platform because it is already familiar and likely low-friction
- keep the core project interfaces independent of ASE
- design the data source as a simple iterable / generator, not a PyTorch `DataLoader`
- introduce a top-level `TrajectoryPartitionRunner` to own the main processing loop
- split visualization from export in the architecture

That feels like the best balance of:

- speed of getting started
- lab compatibility
- clean software structure
- flexibility for later migration to stronger MD-specific tooling if needed

One more practical thought: if visualization quality becomes important quickly, I suspect the eventual pairing may be:

- ASE or MDAnalysis for getting frames into Python
- OVITO or VMD-facing export for looking at partitions

But for day-one development, ASE still looks like a very reasonable place to begin.

## More thoughts on how `Frame`, `Graph`, and `Partition` should relate

I think this is an important design question, and I agree with your concern.

Right now we have three core per-frame objects:

- `Frame`
- `SparseWeightedGraph`
- `Partition`

They all refer to the same physical timestep, so it is natural to want them tied together somehow. But I do **not** think the right answer is to make `Frame` directly own the graph and partition.

### Why I would avoid putting graph/partition inside `Frame`

I think making `Frame` carry a graph and partition would create a few problems:

- it mixes raw input data with derived results
- it makes the `Frame` object depend on later pipeline stages
- it encourages partially filled mutable objects
- it becomes unclear what counts as a "complete" frame

And I agree with your instinct that initializing a frame with an empty partition and then filling it later is probably not a good design. That usually leads to confusing object lifecycles and makes debugging harder.

So my answer is:

- `Frame` should stay a clean, project-owned representation of one timestep's raw or lightly processed MD data
- `SparseWeightedGraph` should stay a derived object
- `Partition` should stay a derived object

### But they still need to be tied together somehow

Yes. I think the right answer is to introduce a fourth object that ties them together without collapsing them into each other.

Something like:

- `FrameRecord`
- `FrameBundle`
- `FrameResult`

I think `FrameRecord` is a nice neutral name.

Its job would be:

- point to the `Frame`
- point to the `SparseWeightedGraph`
- point to the `Partition`
- optionally point to tracking / visualization metadata

So instead of:

- making `Frame` mutable and gradually filled in

I would prefer:

- create a `Frame`
- derive a `SparseWeightedGraph`
- derive a `Partition`
- package them into a `FrameRecord`

That is much cleaner.

### Why this helps visualization

This is exactly the kind of case where a bundle object is useful.

A visualizer usually needs:

- atom positions / box / metadata from `Frame`
- labels or cluster IDs from `Partition`
- maybe graph edges too, if you want to visualize connections

That means the visualizer does not really want "a frame" or "a partition" alone. It wants a per-timestep analysis bundle.

So I think a visualizer should probably consume either:

- `FrameRecord`

or

- a `VisualizationPayload` derived from `FrameRecord`

depending on how backend-independent we want the API to be.

### What happens to `PartitionTrajectory`?

I think this is where your thought about rethinking `PartitionTrajectory` is exactly right.

`PartitionTrajectory` is still a sensible concept if all you care about is the sequence of partitions. But it may be too narrow to be the main trajectory-level object.

Because in practice, over time, you may want access to:

- the frame
- the graph
- the partition
- the persistent cluster IDs
- visualization metadata

all together for each timestep.

So I think the more useful main trajectory-level concept may be something like:

- `TrajectoryRecords`
- `FrameRecordSequence`
- `ProcessedTrajectory`

where each element is a `FrameRecord`.

Then `PartitionTrajectory` can either:

- remain as a lightweight helper view over just the partitions

or

- disappear entirely if it is not actually useful in practice

My current instinct is:

- keep `PartitionTrajectory` only if there is a real algorithmic use for "just the partitions"
- otherwise, the main iterable container should be something like `TrajectoryRecords`

### A concrete design I currently like

Per-frame core objects:

- `Frame`
- `SparseWeightedGraph`
- `Partition`
- `FrameRecord`

Trajectory-level objects:

- `TrajectoryReader`
- `TrajectoryPartitionRunner`
- `TrajectoryRecords`
- `ClusterTracks`

And the lifecycle would look like:

1. `TrajectoryReader` yields a `Frame`
2. `GraphBuilder` makes a `SparseWeightedGraph`
3. `Partitioner` makes a `Partition`
4. `TrajectoryPartitionRunner` packages them into a `FrameRecord`
5. `ClusterTracker` updates temporal identities using the sequence of records or their partitions
6. `Visualizer` / `Exporter` consume `FrameRecord` or derived payloads

That gives you:

- modularity
- no confusing half-filled `Frame` objects
- a natural input object for visualization
- a natural trajectory-level iterable of processed timesteps

### My current conclusion

I do **not** think `Frame` should directly carry a graph and partition.

I **do** think the project should have a higher-level per-frame bundle object, probably something like `FrameRecord`, that ties together:

- the frame
- the graph
- the partition
- optional tracking / visualization metadata

And I think the trajectory-level iterable should probably move in that direction too:

- not just `PartitionTrajectory`
- but something more like `TrajectoryRecords`, which stores or streams `FrameRecord` objects

That seems like the cleanest compromise between:

- keeping the domain objects separate
- and acknowledging that downstream tasks, especially visualization, often need them together

## More thoughts on `PartitionTrajectory`, `FrameBundle`, syncing, and views

I think this is exactly the right place to drill deeper, because this is where a clean architecture can either stay understandable or become very confusing.

There are really three separate questions hiding inside this:

- when does cluster tracking happen relative to building the per-frame bundle?
- what exactly is the role of `PartitionTrajectory`?
- should `FrameBundle` own data, or just be a view into other structures?

### 1. I think tracking should happen in the same forward pass

I agree with your concern about "two processes going in different directions." I think that would get hard to debug very quickly.

The cleanest control flow is probably a single forward stream:

1. load frame `t`
2. build graph `t`
3. compute raw partition `t`
4. run tracking against the previous tracked state
5. produce the final synced/tracked partition `t`
6. emit the per-frame bundle for downstream use

So I would **not** think of it as:

- first build a trajectory of unsynced frame bundles
- then run a second pass that matches partitions later

That is possible, but it creates exactly the "two processes" problem you are worried about.

Instead, I think each timestep should become "fully processed enough" before it is emitted downstream.

That means the bundle for frame `t` should already contain:

- the raw local partition result
- the tracked / synced cluster identity information

So there is only one temporal direction:

- forward in time

That feels much easier to reason about and debug.

### 2. This suggests two notions of partition

I think the easiest way to keep this clear is to explicitly distinguish:

- `LocalPartition`
  the direct output of the clustering algorithm on frame `t`

- `TrackedPartition`
  the local partition plus persistent cluster IDs after tracking/syncing

You may or may not want separate classes for these, but conceptually the distinction helps a lot.

Because then the step ordering becomes:

- partitioner creates the local partition
- tracker augments or transforms it into the tracked partition
- `FrameBundle` contains the tracked result, and may optionally retain the raw local labels too

This makes the meaning of "synced" very explicit.

### 3. What should `PartitionTrajectory` be?

I think this is where the earlier design was still a little fuzzy.

My current refined instinct is:

- `PartitionTrajectory` should **not** be the main engine of the system
- it should be an append-only trajectory-level record of partition results
- in a streaming setting, it should be backed by a store or log, not assumed to be fully in memory

In other words, I would treat `PartitionTrajectory` as more like:

- a sequential archive / access layer for partitions across frames

not:

- the thing from which all live objects are magically viewed

That distinction matters.

If you try to make every per-frame object just a window into some giant underlying trajectory structure, the design can become clever in a way that is hard to debug.

### 4. On `FrameBundle` as a view vs a real object

I think the best compromise is:

- `FrameBundle` should be a **real lightweight object**
- but its fields may contain handles or references rather than massive copied arrays

So not:

- a purely virtual "view" with lots of hidden indexing magic

and not:

- a deep copy of everything

Instead:

- `FrameBundle` is a normal explicit object
- it has a stable `frame_index`
- it contains the small metadata and references needed for downstream work
- large payloads can be held by reference or loaded lazily if necessary

That is usually the sweet spot between efficiency and debuggability.

I would strongly avoid a design where a bundle is only understandable if you know how three different trajectory containers are indexed internally.

That kind of design can be efficient, but it often becomes fragile and confusing unless the problem absolutely demands it.

### 5. A safer "view" pattern

If we do want view-like behavior, I think the best practice is to make it explicit and boring.

For example, a `FrameBundle` could contain:

- `frame_index`
- `frame_ref`
- `graph_ref`
- `partition_ref`
- `tracked_partition_ref`

where each `*_ref` is an explicit handle into a store, cache, or trajectory backend.

Then if needed, the bundle can expose methods like:

- `load_frame()`
- `load_graph()`
- `load_partition()`

That is much easier to debug than implicit magic views.

So if we use views, I would make them explicit reference objects, not hidden shared-state windows.

### 6. I think there should be a distinction between "live processing objects" and "trajectory stores"

This is the big refinement I think makes everything cleaner.

There are two different architectural roles:

#### Live processing objects

These are used while the pipeline is actively stepping through frames:

- `Frame`
- `SparseWeightedGraph`
- `LocalPartition`
- `TrackedPartition`
- `FrameBundle`

These are about one timestep at a time.

#### Trajectory stores / logs

These are the append-only or queryable histories:

- `FrameStore`
- `GraphStore`
- `PartitionTrajectory`
- `BundleTrajectory`
- `ClusterTracks`

These are about persistence and lookup across time.

Once you separate those two roles, the design gets much clearer.

Then a `FrameBundle` does not have to pretend to be the whole trajectory. It is just the current processed timestep object.

And a trajectory-level store does not need to pretend to be the live per-frame object. It is just where history lives.

### 7. A concrete design I currently like

Processing order:

1. `TrajectoryReader` yields `Frame`
2. `GraphBuilder` builds `SparseWeightedGraph`
3. `Partitioner` computes `LocalPartition`
4. `ClusterTracker` matches it against prior tracked state and produces `TrackedPartition`
5. `TrajectoryPartitionRunner` packages the current timestep into a `FrameBundle`
6. stores are optionally updated
7. visualization/export consume the `FrameBundle`

So the `FrameBundle` for frame `t` contains something like:

- the frame or frame reference
- the graph or graph reference
- the tracked partition
- optionally the raw local partition
- any lightweight metadata useful for visualization

And separately you may have:

- `PartitionTrajectory`
  an append-only store of tracked partitions, indexed by frame

- `GraphTrajectory`
  optional append-only store of graphs, indexed by frame

- `BundleTrajectory`
  optional append-only store of `FrameBundle` objects or bundle refs

### 8. What I would avoid for V1

For V1, I would avoid:

- a deeply interdependent set of trajectory-wide view objects
- hidden lazy coupling between three different indexed stores
- a design where the same bundle can silently mean "raw partition" in one place and "tracked partition" in another

Those are the things that tend to become hard to debug.

### 9. My current conclusion

I think the cleanest version is:

- rename `FrameRecord` to `FrameBundle`
- keep `FrameBundle` as a real, explicit, lightweight per-frame object
- run tracking before the bundle is emitted, so each emitted bundle is already temporally synced
- treat `PartitionTrajectory` as an append-only store/log of tracked partitions, not the master hidden backing structure for everything
- if you need views, make them explicit references/handles rather than magical shared windows

So the main flow becomes:

`Frame -> Graph -> LocalPartition -> TrackedPartition -> FrameBundle`

and then:

`FrameBundle -> visualization/export`

while trajectory-level stores are updated on the side as needed.

That feels efficient enough, much easier to debug, and still compatible with large trajectories that cannot live fully in memory.

## More thoughts on `ClusterTracker` vs trajectory-level cluster analysis

Yes, I think this is the right refinement.

The current design had started to overload "cluster tracking" with two different meanings:

- frame-to-frame ID synchronization
- whole-trajectory analysis of lifetimes, splits, deaths, merges, and so on

Those should really be separated.

### 1. What tracking actually is

I agree with your phrasing:

- tracking happens in the main loop
- tracking is the step of making the current frame's cluster IDs match the previous frame's IDs
- tracking is local in time, meaning it only needs the previous tracked state and the current local partition

That is a very clean design.

So `ClusterTracker` should really be thought of as:

- a frame-to-frame identity synchronizer

not:

- a global trajectory analysis object

This also makes the warm-start relationship much clearer. The partitioner can use the previous tracked partition as a warm start, and then the tracker can use the previous tracked partition plus the new local partition to align IDs. That is all still one forward pass.

### 2. What the trajectory-level object should be

Then yes, I think the trajectory-level concept you are describing is something more like:

- `ClusterTrajectoryAnalyzer`
- `ClusterHistoryAnalyzer`
- `ClusterLifecycleAnalyzer`

I think `ClusterLifecycleAnalyzer` is probably the clearest.

Its job is not to assign IDs. Its job is to analyze what happened over time after IDs have already been synchronized.

That means it should answer questions like:

- how long did cluster `k` live?
- when did a cluster first appear?
- when did it disappear?
- did it split?
- did it merge?
- how stable was its membership over time?

That is a trajectory-level derived analysis layer.

### 3. What should live in `FrameBundle`

I think the clean answer is:

- `FrameBundle` should contain the results that are *ready at that frame*
- not later trajectory-wide analysis that requires seeing the future

So it is totally fine for `FrameBundle` to contain:

- the tracked partition for that frame
- maybe some local tracking metadata relative to the previous frame

such as:

- which previous cluster each current cluster matched to
- overlap scores
- whether a local split/merge was detected relative to the previous frame

because those are outputs of the current-step tracker.

But it should **not** contain:

- final lifetime statistics
- "this cluster dies three frames later"
- whole-trajectory summaries

because that would indeed recreate the old problem of an object waiting to be filled in later.

So I think the rule should be:

- `FrameBundle` may contain per-frame and previous-frame-relative tracking outputs
- trajectory-wide lifecycle analysis belongs elsewhere

### 4. This suggests a cleaner three-layer split

I think the design now wants three distinct temporal layers:

#### Layer A: per-frame partitioning

- input: `Frame`, `SparseWeightedGraph`
- output: `LocalPartition`

#### Layer B: online frame-to-frame synchronization

- input: previous `TrackedPartition`, current `LocalPartition`
- output: current `TrackedPartition` plus local tracking metadata

This is the true "tracking" step.

#### Layer C: trajectory-level analysis

- input: stream or store of tracked partitions / frame bundles
- output: lifetime statistics, split/merge histories, cluster event summaries

This is not tracking. This is analysis.

I think that decomposition is much clearer.

### 5. Naming refinement I now like

I would now consider renaming:

- `ClusterTracker`
  keep this name for the frame-to-frame ID synchronizer

- `ClusterTracks`
  this name now feels ambiguous and maybe should change

I think better names might be:

- `TrackingState`
  the online state used by the tracker while stepping through frames

or:

- `TrackedPartitionStore`
  if it is mainly a trajectory-level store of tracked partitions

and then separately:

- `ClusterLifecycleAnalyzer`
- `ClusterLifecycleReport`

for the trajectory-level analysis layer.

That removes the ambiguity around the old `ClusterTracks` name.

### 6. How this avoids the old design flaw

The old flaw would be:

- emit a frame object
- later mutate it with information that was not available when it was emitted

The new design avoids that because:

- tracking information is available immediately during the forward pass
- trajectory-level lifecycle analysis is stored in its own analysis object/report

So a `FrameBundle` is complete when emitted.

Later, if you run lifecycle analysis, it produces:

- a separate `ClusterLifecycleReport`

not:

- a retroactively modified `FrameBundle`

That keeps object lifetimes clean.

### 7. A concrete design I currently like

Main loop:

1. `TrajectoryReader` yields `Frame`
2. `GraphBuilder` builds `SparseWeightedGraph`
3. `Partitioner` computes `LocalPartition`
4. `ClusterTracker` synchronizes IDs against previous tracked state and returns `TrackedPartition`
5. `TrajectoryPartitionRunner` emits a `FrameBundle`

After or during the run:

6. `TrackedPartitionStore` or `PartitionTrajectory` stores tracked partitions
7. `ClusterLifecycleAnalyzer` consumes the trajectory of tracked partitions or frame bundles
8. `ClusterLifecycleReport` provides lifetime/split/merge analysis

### 8. My current conclusion

I think the best refinement is:

- `ClusterTracker` = online frame-to-frame ID synchronization
- `TrackedPartition` = the synced partition for one frame
- `FrameBundle` = one complete timestep result, emitted after tracking
- `PartitionTrajectory` or `TrackedPartitionStore` = trajectory-level record of tracked partitions
- `ClusterLifecycleAnalyzer` = trajectory-level analysis over the tracked results
- `ClusterLifecycleReport` = the analysis output

That preserves the good part of the current design:

- one forward pass
- no second pass for label assignment
- no mutating old bundles later

while still giving you a clean place to compute trajectory-level science.

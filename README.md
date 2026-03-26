# AvidaMT

AvidaMT is the research software built and used for the journal article "Division of Labor Promotes the Entrenchment of Multicellularity" by Peter L. Conlin, Heather J. Goldsby, Eric Libby, Katherine G. Skocelas, William C. Ratcliff, Charles Ofria, and Benjamin Kerr. Much of the text below is repeated from the methods for this paper.


## Dependencies

- [ealib-modern](https://github.com/kgskocelas/ealib-modern) — a modernized fork of the EALib C++ evolutionary algorithm library
- Boost ≥ 1.80 and CMake ≥ 3.14 (installed automatically via Homebrew on macOS, or via the Lmod module system on the MSU HPCC)

See [INSTALL.md](INSTALL.md) for full setup instructions.


## How It Works

AvidaMT is a command-line program for conducting computational evolution experiments examining the conditions that promote the entrenchment of multicellularity and its mechanistic basis. First, the program reads in an extensive, user-defined set of environmental and organismal conditions. Next, it evolves a population of digital organisms under these conditions, recording the organisms' activity, reproduction, and line of descent. This process is highly resource-intensive and designed to be run on a high-performance computing cluster.

Expanding on the digital evolution software [Avida](https://en.wikipedia.org/wiki/Avida_(software)), AvidaMT's digital organisms are composed of either a single lower-level unit (which we refer to as a "unicell") or multiple lower-level units (a "multicell"). Each cell's genome is a program consisting of a set of instructions that encode all cell-level behaviors including metabolic activities and self-replication. Cells can acquire new functionality if genomic mutations appropriately modify the underlying instructions. There are nine types of metabolic functions, each corresponding to a binary-logic task (such as calculating the bitwise OR of two values). Any organism with at least one cell performing one of the nine metabolic functions can acquire resources, which are necessary for reproduction.

When a cell replicates within a multicellular organism, it can result in one of two possible outcomes: propagule production or tissue accretion. Propagule production initiates a new organism. It occurs when the daughter of a reproducing cell departs from the parent organism and randomly replaces another organism within the population to grow an offspring. Tissue accretion does this growth. It occurs when the daughter of a reproducing cell remains in the same body (multicell) as its parent cell. Each form of cellular reproduction is specified by distinct instructions in the cell's genome. Unicellular organisms express instructions for propagule production, but not tissue accretion. A transition to multicellularity begins when mutations to a unicellular organism result in the expression of tissue accretion instructions, while retaining propagule production.

An additional distinction between unicells and multicells is the capacity for coordination. Cells within a multicell can use messaging instructions to communicate with their immediate neighbors or coordinate behaviors including terminal differentiation into a "propagule-ineligible" state. Cells in this state can divide via tissue accretion (producing propagule-ineligible daughter cells), but only propagule-eligible cells can initiate new organisms.


## Installing AvidaMT

See [INSTALL.md](INSTALL.md) for instructions covering macOS (Homebrew) and the MSU HPCC.


## Using AvidaMT

After building, all executables are in the `build/` directory.

| Executable              | Description                     |
|-------------------------|---------------------------------|
| `avida-logic9`          | Logic-9 baseline experiment     |
| `mt_lr_gls`             | Major transitions (GLS)         |
| `mt_lr_gls_dol_control` | Major transitions (DOL control) |
| `ts_mt`                 | Task-switching experiment       |

**Run with a config file:**
```bash
./build/mt_lr_gls -c etc/major_transitions.cfg
```

**Override a config value on the command line:**
```bash
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.gls.and_mutation_mult=6
```

**Continue from a checkpoint:**
```bash
./build/mt_lr_gls -l /path/to/checkpoint-1000000.xml
```

**Run analysis on a checkpoint:**
```bash
./build/mt_lr_gls -l /path/to/checkpoint-1000000.xml \
  --analyze lod_dol \
  --ea.analysis.input.filename /path/to/lod-1000000.xml
```

Available analysis tools for `mt_lr_gls` and `mt_lr_gls_dol_control`: `lod_dol`, `lod_entrench`, `lod_size`, `lod_entrench_add`, `lod_entrench_add_start_stop`, `lod_fitness_combo`, `lod_knockouts_capabilities`, `lod_report_gs`.

> **Note:** `ts_mt` does not share config options with `mt_lr_gls` and `mt_lr_gls_dol_control`.
> Do not use `major_transitions.cfg` with `ts_mt`; pass `ts_mt`-specific options directly or
> use a dedicated config file.


## DOI

References to AvidaMT should be pointed to our DOI on Zenodo: https://doi.org/10.5281/zenodo.15066421

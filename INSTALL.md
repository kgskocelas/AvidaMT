# Installing AvidaMT

- [macOS (Homebrew)](#macos-homebrew)
- [MSU HPCC](#msu-hpcc)

---

## macOS (Homebrew)

These instructions cover a native macOS install using Homebrew and the modern CMake-based build system.

---

## Prerequisites

- macOS with [Homebrew](https://brew.sh) installed
- Xcode Command Line Tools (`xcode-select --install`)

---

## Step 1 — Install dependencies

```bash
brew install boost cmake
```

This installs a modern Boost (1.87.0 or later) and CMake. No manual Boost configuration is needed — CMake finds it automatically.

---

## Step 2 — Clone the repositories

AvidaMT depends on **ealib-modern**, which must be cloned as a sibling directory (both repos live inside the same parent folder).

```bash
mkdir -p ~/Code && cd ~/Code
git clone https://github.com/kgskocelas/ealib-modern.git ealib-modern
git clone https://github.com/kgskocelas/AvidaMT.git AvidaMT
```

Confirm the layout looks like this:

```
Code/
├── ealib-modern/
└── AvidaMT/
```

> **Why side by side?** AvidaMT's `CMakeLists.txt` pulls in ealib-modern via
> `add_subdirectory(../ealib-modern …)`, so the relative path must be correct.

---

## Step 3 — Configure

```bash
cd AvidaMT
cmake -B build -S .
```

Expected output (Boost version may differ):

```
-- Found Boost: 1.87.0 (serialization iostreams regex system filesystem
                          program_options timer chrono)
-- Found ZLIB: ...
-- Configuring done
-- Build files have been written to: .../AvidaMT/build
```

You may see a harmless policy warning about `CMP0167` from ealib-modern's `FindBoost` call — this can be ignored.

---

## Step 4 — Build

```bash
cmake --build build -- -j$(sysctl -n hw.logicalcpu)
```

All four executables will be compiled into `build/`:

| Executable              | Description                        |
|-------------------------|------------------------------------|
| `avida-logic9`          | Logic-9 baseline experiment        |
| `mt_lr_gls`             | Major transitions (GLS)            |
| `mt_lr_gls_dol_control` | Major transitions (DOL control)    |
| `ts_mt`                 | Task-switching experiment          |

---

## Step 5 — Verify

Run a quick smoke test for each executable (5 updates, fixed seed):

```bash
./build/avida-logic9 -c etc/logic9.cfg --ea.run.updates=5 --ea.rng.seed=42
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.run.updates=5 --ea.rng.seed=42
./build/mt_lr_gls_dol_control -c etc/major_transitions.cfg --ea.run.updates=5 --ea.rng.seed=42
```

Each should print the active configuration followed by per-update statistics and exit cleanly.

> **Note:** `ts_mt` does not accept `ea.gls.*` options, so `major_transitions.cfg` cannot
> be used with it directly. Pass `ts_mt`-specific options on the command line or provide a
> custom config file.

---

## Troubleshooting

**Boost not found**
If CMake cannot locate Boost, set `BOOST_ROOT` explicitly:
```bash
cmake -B build -S . -DBOOST_ROOT=$(brew --prefix boost)
```

**`ealib-modern` not found**
Verify that `ealib-modern/` and `AvidaMT/` are in the same parent directory. The relative path `../ealib-modern` in `CMakeLists.txt` must resolve correctly.

**Compiler errors about C++ standard library headers**
Make sure Xcode Command Line Tools are up to date:
```bash
xcode-select --install
softwareupdate --all --install --force
```

---

## MSU HPCC

These instructions are for the Michigan State University High Performance Computing Center (HPCC), which uses the Lmod module system. CMake and Boost are available as pre-built modules — no manual Boost compilation is needed.

> **You need an HPCC account.** If you do not have one, request access through ICER at https://icer.msu.edu before starting.

### Step 1 — Connect and move to a development node

Log in to the HPCC and request a development node so that compilation does not run on the shared login node:

```bash
ssh <netid>@hpcc.msu.edu
dev --time=01:00:00
```

### Step 2 — Check available Boost modules

```bash
module spider Boost
```

Look for a result like `Boost/1.83.0-GCC-13.2.0` (a full Boost library, not `Boost.Python/`). Note the exact version string — you will need it in the next step.

### Step 3 — Load modules

Load a compatible set of GCC, CMake, and Boost. Use the version numbers you found in Step 2. For example:

```bash
module purge
module load GCC/13.2.0
module load CMake/3.27.6-GCCcore-13.2.0
module load Boost/1.83.0-GCC-13.2.0
```

`module purge` clears any previously loaded modules to avoid version conflicts.

Verify:
```bash
cmake --version   # should print 3.14 or newer
```

### Step 4 — Clone the repositories

AvidaMT and ealib-modern must be cloned as sibling directories inside the same parent folder.

```bash
cd $HOME
git clone https://github.com/kgskocelas/ealib-modern.git ealib-modern
git clone https://github.com/kgskocelas/AvidaMT.git AvidaMT
```

Confirm the layout:
```
$HOME/
├── ealib-modern/
└── AvidaMT/
```

### Step 5 — Configure and build

```bash
cd $HOME/AvidaMT
cmake -B build -S .
cmake --build build -- -j$(nproc)
```

The build will take a few minutes. When it finishes, the four executables are in `build/`:

| Executable              | Description                     |
|-------------------------|---------------------------------|
| `avida-logic9`          | Logic-9 baseline experiment     |
| `mt_lr_gls`             | Major transitions (GLS)         |
| `mt_lr_gls_dol_control` | Major transitions (DOL control) |
| `ts_mt`                 | Task-switching experiment       |

### Step 6 — Verify

```bash
./build/avida-logic9 -c etc/logic9.cfg --ea.run.updates=5 --ea.rng.seed=42
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.run.updates=5 --ea.rng.seed=42
```

Each should print the active configuration and run 5 updates cleanly.

### Step 7 — Save your module setup

Modules are reset at the end of each login session. Save the current setup so you can restore it quickly:

```bash
module save avidamt-build
```

In future sessions, restore it before building or running experiments:

```bash
module restore avidamt-build
```

### Running experiments via SLURM

Full AvidaMT experiments are computationally expensive and must be submitted as batch jobs, not run on a login or development node. A minimal SLURM job script looks like:

```bash
#!/bin/bash
#SBATCH --job-name=mt_lr_gls
#SBATCH --time=24:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm-%j.out

module restore avidamt-build
cd $HOME/AvidaMT
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.rng.seed=$SLURM_ARRAY_TASK_ID
```

Submit with:
```bash
sbatch --array=1-30 run_mt.sb
```

The `--array` flag runs 30 independent replicates, each with a different random seed derived from `$SLURM_ARRAY_TASK_ID`.

### Troubleshooting (HPCC)

**Boost not found at configure time**
Make sure the Boost module is loaded (`module list`). If it is loaded but CMake still cannot find it, set `BOOST_ROOT` explicitly:
```bash
cmake -B build -S . -DBOOST_ROOT=$EBROOTBOOST
```
`$EBROOTBOOST` is set automatically by the Lmod Boost module.

**`ealib-modern` not found**
Verify that `ealib-modern/` and `AvidaMT/` share the same parent directory. The relative path `../ealib-modern` in `CMakeLists.txt` must resolve correctly.

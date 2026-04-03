# Installing AvidaMT

- [macOS (Homebrew)](#macos-homebrew)
- [MSU HPCC](#msu-hpcc)

---

## macOS (Homebrew)

These instructions cover a native macOS install using Homebrew and the modern CMake-based build system.

These instructions have been verified on:

| Component      | Version                        |
|----------------|--------------------------------|
| macOS          | Ventura 13.7.8 (Intel x86_64)  |
| Xcode          | 15.2 (Apple Clang 15.0.0)      |
| Homebrew Boost | 1.87.0                         |
| CMake          | 4.3.0                          |

---

### Step 1: Prerequisites

Install the Xcode Command Line Tools (skip if already installed):

```bash
xcode-select --install
```

Install [Homebrew](https://brew.sh), then use it to install CMake and Boost:

```bash
brew install cmake boost
```

This installs a modern Boost (1.87.0 or later) and CMake. No manual Boost configuration is needed — CMake finds it automatically.

---

## Step 2 — Clone the repositories

AvidaMT depends on **ealib-modern**, which must be cloned as a sibling directory (both repos live inside the same parent folder).

```bash
mkdir Avida && cd Avida
git clone https://github.com/kgskocelas/ealib-modern.git ealib-modern
git clone https://github.com/kgskocelas/AvidaMT.git AvidaMT
```

Confirm the layout looks like this:

```
Avida/
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

---

## Step 4 — Build

```bash
cmake --build build --parallel
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

Run all commands from inside `AvidaMT/`. Each test runs in its own subdirectory so output files don't overwrite each other.

```bash
mkdir -p verify/logic9
(cd verify/logic9 && ../../build/avida-logic9 -c ../../etc/logic9.cfg --ea.run.updates=5 --ea.rng.seed=42)
echo $?   # should print 0
```

```bash
mkdir -p verify/mt_lr_gls
(cd verify/mt_lr_gls && ../../build/mt_lr_gls -c ../../etc/major_transitions.cfg --ea.run.updates=100 --ea.rng.seed=42)
echo $?   # should print 0; creates tasks.dat, mt_gls.dat, dol.dat
```

```bash
mkdir -p verify/mt_lr_gls_dol_control
(cd verify/mt_lr_gls_dol_control && ../../build/mt_lr_gls_dol_control -c ../../etc/major_transitions.cfg --ea.run.updates=100 --ea.rng.seed=42)
echo $?   # should print 0; creates tasks.dat, mt_gls.dat
```

```bash
mkdir -p verify/ts_mt
(cd verify/ts_mt && ../../build/ts_mt -c ../../etc/ts_mt.cfg --ea.run.updates=100 --ea.rng.seed=42)
echo $?   # should print 0; creates tasks.dat, ts.dat, mt.dat
```

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
mkdir Avida && cd Avida
git clone https://github.com/kgskocelas/ealib-modern.git ealib-modern
git clone https://github.com/kgskocelas/AvidaMT.git AvidaMT
```

Confirm the layout:
```
$HOME/
├── Avida
├──── ealib-modern/
└──── AvidaMT/
```

### Step 5 — Configure and build

```bash
cd $HOME/Avida/AvidaMT
cmake -B build -S .
cmake --build build --parallel
```

The build will take a few minutes. When it finishes, the four executables are in `build/`:

| Executable              | Description                     |
|-------------------------|---------------------------------|
| `avida-logic9`          | Logic-9 baseline experiment     |
| `mt_lr_gls`             | Major transitions (GLS)         |
| `mt_lr_gls_dol_control` | Major transitions (DOL control) |
| `ts_mt`                 | Task-switching experiment       |

### Step 6 — Verify

Run from inside `$HOME/Avida/AvidaMT/`. Use the [same verification steps as local installation](#step-5--verify).

### Step 7 — Save your module setup

Modules are reset at the end of each login session. Save the current setup so you can restore it quickly:

```bash
module save avidamt
```

In future sessions, restore it before building or running experiments:

```bash
module restore avidamt
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

module restore avidamt
cd $HOME/AvidaMT
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.rng.seed=$SLURM_ARRAY_TASK_ID
```

### Troubleshooting (HPCC)

**Boost not found at configure time**
Make sure the Boost module is loaded (`module list`). If it is loaded but CMake still cannot find it, set `BOOST_ROOT` explicitly:
```bash
cmake -B build -S . -DBOOST_ROOT=$EBROOTBOOST
```
`$EBROOTBOOST` is set automatically by the Lmod Boost module.

**`ealib-modern` not found**
Verify that `ealib-modern/` and `AvidaMT/` share the same parent directory. The relative path `../ealib-modern` in `CMakeLists.txt` must resolve correctly.

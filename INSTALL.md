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
mkdir -p ~/Avida && cd ~/Avida
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

Data files are written to the **current working directory**. The commands below run each test inside its own subdirectory so the output files from different executables do not overwrite each other. Run all commands from inside `AvidaMT/`.

---

### Test 1 — avida-logic9

```bash
mkdir -p verify/logic9
(cd verify/logic9 && ../../build/avida-logic9 -c ../../etc/logic9.cfg --ea.run.updates=5 --ea.rng.seed=42)
```

`avida-logic9` does not write data files. Confirm it ran correctly:

- No crash or error message appears in the terminal.
- The output includes the active configuration (key–value pairs) followed by per-update progress.
- Check the exit code immediately after: `echo $?` should print `0`.

---

### Test 2 — mt_lr_gls

```bash
mkdir -p verify/mt_lr_gls
(cd verify/mt_lr_gls && ../../build/mt_lr_gls -c ../../etc/major_transitions.cfg --ea.run.updates=100 --ea.rng.seed=42)
```

Three data files are written to `verify/mt_lr_gls/`. Open each with any text editor or `cat`:

**`tasks.dat`** — counts of each logic task performed across the entire population, recorded once every 100 updates. The file should contain a header line followed by exactly one data row. The first column of that row should be `100` (the update number).

```
update not nand and ornot or andnot nor xor equals
100    0   0    0   0      0  0       0   0   0
```

(Task counts may be 0 at update 100; the key checks are that the file exists, has two lines, and the `update` column reads `100`.)

**`mt_gls.dat`** — multicell replication and germ/soma statistics, recorded every 100 updates. Columns include `update`, `mean_multicell_size`, `mean_pop_num`, `num_orgs`, and many others. Check:
- One header line followed by one data row with `update = 100`.
- `num_orgs` > 0 (population is alive and running).
- `mean_multicell_size` > 0 (cells are present inside each multicell).

**`dol.dat`** — division-of-labor statistics, recorded every 100 updates. Columns: `update mean_shannon_sum mean_shannon_norm mean_active_pop mean_pop_count`. Check:
- One header line followed by one data row with `update = 100`.
- `mean_pop_count` > 0.

---

### Test 3 — mt_lr_gls_dol_control

```bash
mkdir -p verify/mt_lr_gls_dol_control
(cd verify/mt_lr_gls_dol_control && ../../build/mt_lr_gls_dol_control -c ../../etc/major_transitions.cfg --ea.run.updates=100 --ea.rng.seed=42)
```

`mt_lr_gls_dol_control` does not write `dol.dat`. Check:

**`tasks.dat`** — same checks as Test 2 (header + one row with `update = 100`).

**`mt_gls.dat`** — same checks as Test 2 (`num_orgs > 0`, `mean_multicell_size > 0`).

---

### Test 4 — ts_mt

`ts_mt` does not accept the `[ea.gls]` options present in `major_transitions.cfg`. Use `etc/ts_mt.cfg` instead (the same parameters minus that section):

```bash
mkdir -p verify/ts_mt
(cd verify/ts_mt && ../../build/ts_mt -c ../../etc/ts_mt.cfg --ea.run.updates=100 --ea.rng.seed=42)
```

Three data files are written to `verify/ts_mt/`. Check:

**`tasks.dat`** — same checks as Test 2.

**`ts.dat`** — task-switching statistics, recorded every 100 updates. Columns: `update sub_pop_size pop_size mean ts`. Check:
- One header line followed by one data row with `update = 100`.
- `sub_pop_size` equals the configured metapopulation size (`1000` by default).
- `pop_size` > 0.

**`mt.dat`** — multicell replication summary, recorded every 100 updates. Columns: `update mean_rep_time mean_res mean_multicell_size replication_count mean_generation`. Check:
- One header line followed by one data row with `update = 100`.
- `mean_multicell_size` > 0.

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

Data files are written to the current working directory. Run each test from its own subdirectory (from inside `$HOME/AvidaMT/`):

**avida-logic9** — no data files; verify via exit code and stdout only.

```bash
mkdir -p verify/logic9
(cd verify/logic9 && ../../build/avida-logic9 -c ../../etc/logic9.cfg --ea.run.updates=5 --ea.rng.seed=42)
echo $?   # should print 0
```

**mt_lr_gls** — writes `tasks.dat`, `mt_gls.dat`, and `dol.dat` to the output directory.

```bash
mkdir -p verify/mt_lr_gls
(cd verify/mt_lr_gls && ../../build/mt_lr_gls -c ../../etc/major_transitions.cfg --ea.run.updates=100 --ea.rng.seed=42)
```

**mt_lr_gls_dol_control** — writes `tasks.dat` and `mt_gls.dat` (no `dol.dat`).

```bash
mkdir -p verify/mt_lr_gls_dol_control
(cd verify/mt_lr_gls_dol_control && ../../build/mt_lr_gls_dol_control -c ../../etc/major_transitions.cfg --ea.run.updates=100 --ea.rng.seed=42)
```

**ts_mt** — use `etc/ts_mt.cfg` (not `major_transitions.cfg`); writes `tasks.dat`, `ts.dat`, and `mt.dat`.

```bash
mkdir -p verify/ts_mt
(cd verify/ts_mt && ../../build/ts_mt -c ../../etc/ts_mt.cfg --ea.run.updates=100 --ea.rng.seed=42)
```

For each data file: open it with `cat` or a text editor and confirm a header line is present followed by one data row whose `update` column reads `100`. See the macOS **Step 5 — Verify** section above for the full list of per-file checks.

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

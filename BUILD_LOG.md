# AvidaMT Build Log — ealib-modern Migration

**Started:** 2026-03-25
**Goal:** Compile and test AvidaMT against ealib-modern (modern Boost / CMake build system)

---

## Background

- AvidaMT originally used Boost.Build (Jamroot / b2) and referenced `../ealib/libea`
- ealib-modern replaced Boost.Build with CMake (see `../ealib-modern/MODERNIZATION_NOTES.md`)
- AvidaMT must be migrated from Jamroot to CMake so it can consume ealib-modern's targets

---

## Step 1 — Create CMakeLists.txt for AvidaMT

AvidaMT's `Jamroot` defines four executables:

| Target name              | Source file                      |
|--------------------------|----------------------------------|
| `avida-logic9`           | `src/logic9.cpp`                 |
| `mt_lr_gls_dol_control`  | `src/mt_lr_gls_dol_control.cpp`  |
| `mt_lr_gls`              | `src/mt_lr_gls.cpp`              |
| `ts_mt`                  | `src/ts_mt.cpp`                  |

Each links against `libea_runner` (which transitively pulls in `libea_cmdline`, `libea`, Boost, zlib).

**Action:** Created `CMakeLists.txt` at AvidaMT project root that:
- Uses `add_subdirectory(../ealib-modern ealib-modern)` to pull in ealib-modern
- Applies the same global compile definitions as ealib-modern
  (`BOOST_BIND_GLOBAL_PLACEHOLDERS`, `BOOST_PARAMETER_MAX_ARITY=7`,
  `BOOST_GEOMETRY_EMPTY_INPUT_NO_THROW`)
- Adds `include` and `src` dirs for AvidaMT's own headers
- Defines the four executables, each linked privately against `libea_runner`

---

## Step 2 — CMake Configure

```bash
cmake -B build -S .
```

**Result:** Success (no errors, one policy warning about CMP0167 from ealib-modern's
`FindBoost` call — harmless on this Boost 1.87.0 install).

```
-- Found Boost: 1.87.0 (serialization iostreams regex system filesystem
                          program_options timer chrono)
-- Found ZLIB: 1.2.12
-- Configuring done (2.9s)
-- Build files have been written to: /Users/kgskocelas/Lab/Code/AvidaMT/build
```

---

## Step 3 — Build

```bash
cmake --build build -- -j4
```

**Result:** All targets built cleanly.

```
[ 10%] Built target libea_cmdline
[ 17%] Built target libea_runner
[ 20%] Building CXX object CMakeFiles/mt_lr_gls.dir/src/mt_lr_gls.cpp.o
[ 24%] Building CXX object CMakeFiles/mt_lr_gls_dol_control.dir/...
[ 27%] Building CXX object CMakeFiles/ts_mt.dir/src/ts_mt.cpp.o
[ 31%] Building CXX object CMakeFiles/avida-logic9.dir/src/logic9.cpp.o
[ 34%] Built target avida-logic9
[ 41%] Built target ts_mt
[ 48%] Built target mt_lr_gls_dol_control
[ 55%] Built target mt_lr_gls
```

Warnings only (no errors):
- `std::binary_function` and `std::unary_function` deprecated in C++11 (in ealib headers)
- `std::random_shuffle` deprecated in C++14 (in ealib headers)

These are pre-existing in ealib's source and do not affect correctness.

Binary sizes:

| Executable              | Size    |
|-------------------------|---------|
| `avida-logic9`          | 7.5 MB  |
| `mt_lr_gls`             | 15.5 MB |
| `mt_lr_gls_dol_control` | 14.6 MB |
| `ts_mt`                 | 14.6 MB |

---

## Step 4 — Testing

### avida-logic9
```bash
./build/avida-logic9 -c etc/logic9.cfg --ea.run.updates=5 --ea.rng.seed=42
```
**Result:** Exit 0. Configuration printed correctly, ran 5 updates.

### mt_lr_gls
```bash
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.run.updates=5 --ea.rng.seed=42
```
**Result:** Exit 0. Configuration printed correctly, ran 5 updates.

### mt_lr_gls_dol_control
```bash
./build/mt_lr_gls_dol_control -c etc/major_transitions.cfg --ea.run.updates=5 --ea.rng.seed=42
```
**Result:** Exit 0. Configuration printed correctly, ran 5 updates.

### ts_mt (initial failure → diagnosed → fixed config)

First attempt using `major_transitions.cfg` failed:
```
Caught exception: Unrecognized options were found in: etc/major_transitions.cfg:
    ea.gls.task_mutation_per_site_p, ea.gls.not_mutation_mult, ...
```
**Diagnosis:** `ts_mt` is the task-switching experiment and does not register
`ea.gls.*` options (those belong to `mt_lr_gls`/`mt_lr_gls_dol_control`).
The shared config file is not compatible with `ts_mt`. This is expected
behavior — not a build regression.

Second attempt (passing ts_mt-specific options directly) also revealed:
```
Assertion failed: ((get<SPATIAL_X>(ea) * get<SPATIAL_Y>(ea)) <= get<POPULATION_SIZE>(ea))
```
**Diagnosis:** `ea.population.size` must be ≥ `ea.environment.x × ea.environment.y`.
With x=5, y=5, population_size must be ≥ 25.

Final test (correct parameters):
```bash
./build/ts_mt \
  --ea.environment.x=5 --ea.environment.y=5 \
  --ea.metapopulation.size=10 --ea.population.size=25 \
  --ea.representation.size=100 --ea.scheduler.time_slice=30 \
  --ea.scheduler.resource_slice=30 \
  --ea.mutation.site.p=0.0 --ea.mutation.insertion.p=0.0 --ea.mutation.deletion.p=0.0 \
  --ea.mutation.uniform_integer.min=0 --ea.mutation.uniform_integer.max=38 \
  --ea.run.updates=50 --ea.rng.seed=42 --ea.run.epochs=1 \
  --ea.ts.task_switching_cost=0 --ea.ts.germ_mutation_per_site_p=0.01 \
  --ea.ts.res_initial_amount=100 --ea.ts.res_inflow_amount=1 \
  --ea.ts.res_outflow_fraction=0.01 --ea.ts.res_fraction_consumed=0.05 \
  --ea.res.group_rep_threshold=500 --ea.mt.cost_start_update=0 \
  --ea.statistics.recording.period=10
```
**Result:** Exit 0. Ran 50 updates cleanly.

---

## Summary

| Item                     | Status  |
|--------------------------|---------|
| CMake migration          | Done    |
| Boost 1.87.0 (Homebrew)  | Found automatically |
| ealib-modern integration | Working |
| avida-logic9 build       | ✓       |
| mt_lr_gls build          | ✓       |
| mt_lr_gls_dol_control build | ✓    |
| ts_mt build              | ✓       |
| avida-logic9 test        | ✓       |
| mt_lr_gls test           | ✓       |
| mt_lr_gls_dol_control test | ✓     |
| ts_mt test               | ✓       |

**No source code changes were required.** Only a new `CMakeLists.txt` was added to
replace the Jamroot-based build system.

---

## Notes

- `ts_mt` does not accept `ea.gls.*` options — do not use `major_transitions.cfg`
  with it; pass ts-specific options directly or create a `ts_mt.cfg`.
- The `ea.population.size` must be ≥ `ea.environment.x × ea.environment.y` for
  digital evolution experiments (this is an existing runtime assertion).
- Old b2 build: `b2` binary exists at `/usr/local/bin/b2` but `ealib` Jamfiles
  cannot find `/boost` (the old build system no longer works — this is expected,
  it's exactly why ealib-modern was created).

---

## Step 5 — Write INSTALL.md (2026-03-25)

Created `INSTALL.md` with macOS (Homebrew) installation instructions:
- Install `boost` and `cmake` via Homebrew
- Clone `ealib-modern` and `AvidaMT` as siblings
- Configure with `cmake -B build -S .`
- Build with `cmake --build build -- -j$(sysctl -n hw.logicalcpu)`
- Smoke-test all four executables

Instructions were verified by running a clean build from scratch (deleted `build/` and reconfigured) and re-running all three smoke tests — all passed.

---

## Step 6 — Remove old build system and IDE files (2026-03-25)

Removed files that were committed to the repo but are no longer needed after the CMake migration:

| File / Directory         | Reason removed                          |
|--------------------------|-----------------------------------------|
| `Jamroot`                | Old Boost.Build file, replaced by CMakeLists.txt |
| `bin/config.log`         | b2 configure log                        |
| `bin/project-cache.jam`  | b2 project cache                        |
| `bin/clang-darwin-10.0/` | Old b2-compiled binary and object file  |
| `etc/avida4.xcconfig`    | Xcode build configuration, no longer used |
| `mt2.xcodeproj/`         | Old Xcode project                       |
| `mt2.xcworkspace/`       | Old Xcode workspace                     |
| `math/.DS_Store`         | macOS metadata file                     |

Also deleted untracked run-artifact files that had accumulated in the repo root (`checkpoint-5.xml`, `lod-5.xml`, `dol.dat`, `mt_gls.dat`, `mt_gls_detail.dat`, `tasks.dat`). These are now covered by `.gitignore` patterns (`checkpoint-*.xml`, `lod-*.xml`, `*.dat`).

---

## Step 8 — Verify and fix "Using AvidaMT" section in README.md (2026-03-25)

Ran each command in the README's "Using AvidaMT" section to verify accuracy.

### Commands tested

**Run with config file** — passed:
```bash
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.run.updates=5 --ea.rng.seed=1
```

**Override a config value** — passed (confirmed `ea.gls.and_mutation_mult` changed from 1 to 6 in active config output):
```bash
./build/mt_lr_gls -c etc/major_transitions.cfg --ea.gls.and_mutation_mult=6 --ea.run.updates=5 --ea.rng.seed=1
```

**Continue from checkpoint** — needed investigation first.

Ran a 10-update experiment to discover what checkpoint files are actually produced. Found that the framework saves:
- `checkpoint-{N}.xml` — full EA state (≈45 MB for this config)
- `lod-{N}.xml` — line-of-descent file

The README had used `.xml.gz` in the checkpoint path placeholder. While the loader supports `.gz` files, the default output is uncompressed `.xml`. Updated the placeholder to `.xml` to match actual behavior.

Tested resume:
```bash
./build/mt_lr_gls -l checkpoint-10.xml --ea.run.updates=5 --ea.rng.seed=1
```
**Result:** Loaded cleanly, continued from update 10.

**Run analysis** — failed, then diagnosed and fixed.

The README had `--analyze lod_fitness`. Read `src/mt_lr_gls.cpp` and found `lod_fitness` is commented out in `gather_tools()` (line 290). Running it produced:
```
Caught exception: bad argument: Could not find analysis tool: lod_fitness
```

The registered analysis tools for `mt_lr_gls` are:
`lod_dol`, `lod_entrench`, `lod_size`, `lod_entrench_add`, `lod_entrench_add_start_stop`, `lod_fitness_combo`, `lod_knockouts_capabilities`, `lod_report_gs`.

Read `src/lod_knockouts_fitness.h` to confirm `lod_dol` reads the LOD file via `--ea.analysis.input.filename` (the same flag the README used). Updated the README to use `lod_dol` and added the list of available tools.

### Changes made to README.md

| Item | Before | After | Reason |
|------|--------|-------|--------|
| Checkpoint path extension | `checkpoint-1000000.xml.gz` | `checkpoint-1000000.xml` | Default output is uncompressed |
| LOD path extension | `lod-1000000.xml.gz` | `lod-1000000.xml` | Default output is uncompressed |
| Analysis tool name | `lod_fitness` | `lod_dol` | `lod_fitness` is not registered; causes fatal error |
| Available tools | (not listed) | Listed all 8 registered tools | Help users know what tools exist |

---

## Step 7 — Update README.md and add HPCC instructions to INSTALL.md (2026-03-25)

### README.md

- `Dependencies` — removed references to old ealib (dknoester) and Boost 1.71.0; now lists ealib-modern and Boost ≥ 1.80
- `Installing AvidaMT` — replaced the old b2/Singularity install walkthrough with a one-line pointer to `INSTALL.md`
- `Using AvidaMT` — replaced inline prose with a table of executables and labeled command blocks; corrected all binary paths from `./mt_lr_gls` to `./build/mt_lr_gls`

### INSTALL.md

Added `## MSU HPCC` section covering:
- Login and requesting a development node (`dev --time=01:00:00`)
- Finding a compatible Boost module with `module spider Boost`
- Loading GCC, CMake, and Boost modules (`module purge` + `module load`)
- Cloning ealib-modern and AvidaMT as siblings under `$HOME`
- Configure (`cmake -B build -S .`) and build (`cmake --build build -- -j$(nproc)`)
- Smoke-test verification commands
- Saving the module setup with `module save avidamt-build` for future sessions
- A minimal SLURM array job script for running experiment replicates
- HPCC-specific troubleshooting (`$EBROOTBOOST` for Boost path override)

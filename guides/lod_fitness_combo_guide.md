# LOD Fitness Combo Analysis Guide
### The `004e` unicellular revertant fitness assay — what it is, how the code works, and how to replicate it

---

## What This Analysis Is

This is the **unicellular revertant fitness assay** described in Section B of `EXPERIMENT RUNS AND SETTINGS SUMMARY.txt`. It answers:

> *If you take a multicellular organism and force it back to unicellular life, how fit is it? Does this fitness decline as the organism spends more time evolving as a multicell?*

If unicellular revertants are less fit later in evolution than they were at the moment of the transition to multicellularity, that is evidence of **entrenchment** — the organism has become dependent on its multicellular lifestyle.

The analysis is run via the AvidaMT binary (`mt_lr_gls`) using the built-in analysis tool `lod_fitness_combo`, implemented in `AvidaMT/src/lod_knockouts_fitness.h`.

---

## Inputs Required

For each of the 65 evolved multicellular replicates (seeds listed below), you need two files from the end of the evolutionary run:

| File | What it is |
|------|-----------|
| `checkpoint-1000000.xml.gz` | Serialized population state at update 1,000,000 |
| `lod-1000000.xml.gz` | Line of Descent file, written during the run |

**Heather's originals are at:** `/mnt/research/devolab/mt/mt_clean/002/a_$SEED/`

If you are re-running from your own evolutionary runs, LOD files are only written if the LOD flag was enabled. See the `entrenchment_exp_guide.md` section on LOD Reruns.

---

## The 65 Multicellular Seeds

```
3002, 3017, 3019, 3024, 3038, 3046, 3056, 3074, 3081, 3097,
3100, 3102, 3111, 3150, 3158, 3181, 3186, 3227, 3257, 3312,
3323, 3335, 3358, 3362, 3366, 3383, 3411, 3416, 3430, 3447,
3451, 3486, 3493, 3497, 4032, 4048, 4057, 4068, 4076, 4077,
4097, 4122, 4140, 4170, 4175, 4178, 4217, 4218, 4222, 4234,
4243, 4254, 4271, 4278, 4308, 4310, 4320, 4355, 4357, 4360,
4367, 4387, 4456, 4480, 4493
```

---

## The Four Experimental Conditions

Four separate SLURM batch jobs are required per seed. The key parameters that vary are which LOD timepoint to analyze and whether mutations are on during the fitness assay.

| SLURM script | `EXPER` name | `lod_timepoint_to_analyze` | `lod_analysis_mutations_off` | Purpose |
|---|---|---|---|---|
| `run.sbatch` | `fitness_end` | `1` (final ancestor) | `0` (mutations ON) | Revertant fitness at end of evolution, with mutation |
| `run_no_mut.sbatch` | `fitness_end_no_mut` | `1` (final ancestor) | `1` (mutations OFF) | Revertant fitness at end, no mutation (basal genotype fitness) |
| `run_trans.sbatch` | `fitness_trans` | `0` (transition point) | `0` (mutations ON) | Revertant fitness at the transition to multicellularity |
| `run_trans_c.sbatch` | `fitness_trans_4178` | `60` (specific step) | `0` (mutations ON) | Special re-run for seed 4178 only — transition was at LOD step 60 |

`run_trans_b.sbatch` was just a retry for seeds 3150 and 4048 from the `fitness_trans` run (same parameters, different `--array`).

---

## Command Structure

```bash
./mt_lr_gls \
  -l /path/to/checkpoint-1000000.xml.gz \
  --analyze lod_fitness_combo \
  --ea.analysis.input.filename /path/to/lod-1000000.xml.gz \
  --ea.mt.lod_timepoint_to_analyze=<0, 1, or N> \
  --ea.mt.lod_analysis_reps=100 \
  --ea.mt.lod_analysis_mutations_off=<0 or 1> \
  --ea.mt.track_details=<0 or 1> \
  --ea.mt.only_mc=0
```

The executable needs to be in a directory alongside a `config/` folder containing `ramp.cfg`. The SLURM jobs set this up by creating a per-seed working directory and copying `config/*` into it.

**Heather's output directories:** `/mnt/gs18/scratch/users/hjg/004e_new/{EXPER}_{SEED}/`

---

## How `lod_timepoint_to_analyze` Works

Source: `AvidaMT/src/lod_knockouts_fitness.h`, lines 157–181

```
0  → walk the LOD forward from the beginning until the first
     ancestor with more than 2 cells — this is the transition
     point to multicellularity

1  → jump directly to the final ancestor at the end of the LOD

N  → walk the LOD forward exactly N steps from the beginning
     (used for seed 4178, where lod_timepoint_to_analyze=60)
```

---

## What the Code Does (Step by Step)

### Phase 1: Multicell fitness assay (100 reps)

For each of 100 replicate assays:
1. Creates a fresh metapopulation (`METAPOPULATION_SIZE=100`)
2. Seeds it with the LOD ancestor's founder genome
3. Runs until either `metapop.size() >= 32` OR `cur_update >= 50000`
4. Writes one `mc` row to `lod_fitness.dat`

The `50000` cap is the timeout — any row with `time_to_fill == 50000` means the multicell failed to fill.

### Phase 2: Unicellular revertant generation and fitness assay

For every position in the 100-instruction genome × every instruction in the ISA (indices 0–38, so ~39 × 100 = ~3,900 single-locus mutants):

**Step A — Viability check (always run with zero mutations):**
- Substitutes instruction `q` at position `z` into the founder genome
- Runs the single organism for up to 10,000 updates waiting for `DIVIDE_REMOTE`
- If `population.size() < 2` after replication → this mutant is a **unicellular revertant**
- If it timed out → inviable, skip

**Step B — Growth assay (100 reps, only for viable unicell revertants):**
- For each of 100 reps:
  - Creates a fresh metapopulation (`METAPOPULATION_SIZE=32`)
  - Seeds it with the unicell mutant genome
  - If `mutations_off=1`, sets `TASK_MUTATION_PER_SITE_P=0`
  - Runs until either `metapop.size() >= 32` OR `cur_update >= 50000`
  - Writes one `uni` row to `lod_fitness.dat`

> **Important:** The viability check (Step A) always uses zero mutations regardless of the `mutations_off` flag. The `mutations_off` flag only controls Step B (the growth assay replicates).

---

## Output Files

Each per-seed job directory produces these files:

### `lod_fitness.dat`
One row per replicate trial. Contains both `mc` (multicell) and `uni` (unicell revertant) rows.

| Column | Description |
|--------|-------------|
| `timepoint` | 0 = transition, 1 = final |
| `mc_or_uni` | `"mc"` or `"uni"` |
| `count` | For `mc`: always 0. For `uni`: index of this unicell revertant (its position in the genome scan) |
| `iteration` | Replicate number (0–99) |
| `time_to_fill` | Updates to fill the population; 50000 = timed out (inviable) |
| `workload` | Total task executions across all cells in the final population |
| `num_org` | Number of multicells (groups) in the metapopulation at end |
| `total_cells` | Total number of cells across all multicells at end |

### `lod_fit_summary.dat`
One summary row per job.

| Column | Description |
|--------|-------------|
| `timepoint` | 0 or 1 |
| `num_unicell_revertants` | Total number of single-locus mutants that produced a unicell (viable + inviable) |
| `num_viable_unicells` | Unicell revertants that replicated before timeout |
| `num_inviable_unicells` | Unicell revertants that timed out |
| `update` | Birth update of the LOD ancestor being analyzed |

> **Schema note:** The notebook analysis (`004e_combine_lod_full_fitness.ipynb`) references a 5th column called `num_inviable_ineligible_unicells`. This column **does not exist in the current code**. The version Heather ran had a slightly different schema. The current code produces 5 columns including `update`; the notebook was written against a version with 6 columns. You will need to update the notebook's column references if you are reading from newly generated data.

### `multicell_detail.dat` and `unicell_detail.dat`
Per-cell detail files written only when `track_details=1`. These contain per-cell task counts, workload, germ/soma status, resources, and genome sequence for every cell in every replicate. These files are very large. `run_no_mut.sbatch` uses `track_details=0` to skip them.

---

## Resource and Time Estimates

From Heather's SLURM scripts:

| Condition | Time limit | Memory |
|---|---|---|
| `fitness_end` | 30 hours | 5 GB |
| `fitness_end_no_mut` | 4 hours | 5 GB |
| `fitness_trans` | 75 hours | 5 GB |
| `fitness_trans_4178` | 30 hours | 5 GB |

The `fitness_trans` condition takes longer because the LOD ancestor at the transition is earlier (less evolved), so the genomes are less efficient and take more updates per replicate.

---

## Post-Processing: The Notebook

**File:** `Heather's Scripts/004e_combine_lod_full_fitness.ipynb`

Heather's `dirname` was `/Users/hjg/Desktop/research/mt/var-clean/004e/`. Change this to wherever you download the data.

### What the notebook does

**From `lod_fitness.dat` (loaded into `df`, `df1`, `df2`):**

1. Loads all 65 seeds × 4 conditions into DataFrames
2. Filters unicell rows to `total_cells <= 32` and `time_to_fill != 50000`
3. For each replicate, classifies every unicell revertant as:
   - **"low fidelity – high workload"**: workload > 0 (performs tasks but is slower)
   - **"high fidelity – low workload"**: workload == 0 (lost task performance)
4. Plots stacked bar chart of these categories across all 65 replicates

**From `lod_fit_summary.dat` (loaded into `full_df`):**

1. Loads both `fitness_end` and `fitness_trans` summary files
2. Compares `num_unicell_revertants` and `num_viable_unicells` between the two timepoints
3. Runs Wilcoxon rank-sum tests

### Key output CSVs

| File | Contents |
|------|----------|
| `lod_fitness_final_filtered.csv` | Combined `lod_fitness.dat` data from `fitness_end` condition |
| `lod_fitness_summary.csv` | Combined `lod_fit_summary.dat` from both timepoints |
| `004_time_diff.csv` | Per-replicate time between transition and final timepoints |

---

## Fitness Calculation

From the notebook's `calc_fitness()` function:

```
fitness = mean(time_to_fill_uni) / mean(time_to_fill_mc)
```

A ratio > 1 means the unicell revertant fills a population more slowly than the multicell — the multicell is fitter than its unicellular form. Higher ratios indicate greater entrenchment.

---

## Relationship to the `lod_fitness_combo` C++ Tool

The analysis tool is registered in `AvidaMT/src/mt_lr_gls.cpp`:

```cpp
add_tool<ealib::analysis::lod_fitness_combo>(this);  // line 310
```

The full implementation is in `AvidaMT/src/lod_knockouts_fitness.h`, starting at line 42. The metadata keys it reads from the config/command line are declared at lines 27–34:

```cpp
LIBEA_MD_DECL(ANALYSIS_LOD_TIMEPOINT_TO_ANALYZE, "ea.mt.lod_timepoint_to_analyze", int);
LIBEA_MD_DECL(ANALYSIS_LOD_REPS,                 "ea.mt.lod_analysis_reps",         int);
LIBEA_MD_DECL(ANALYSIS_MUTATIONS_OFF,            "ea.mt.lod_analysis_mutations_off", int);
LIBEA_MD_DECL(ONLY_MC,                           "ea.mt.only_mc",                   int);
// also uses TRACK_DETAILS ("ea.mt.track_details") declared in gls.h
```

The `--analyze lod_fitness_combo` flag on the command line is what invokes this tool instead of running a normal evolutionary simulation.

---

## Other Analysis Tools in the Same File

`lod_knockouts_fitness.h` also contains these tools (all registered and callable via `--analyze <name>`):

| Tool name | What it does |
|-----------|-------------|
| `lod_entrench` | Entrenchment stability assay using `TISSUE_ACCRETION_MULT` cost sweeps |
| `lod_entrench_add` | Same but using `TISSUE_ACCRETION_ADD` cost, doubling each step |
| `lod_entrench_add_start_stop` | Walks the full LOD and measures entrenchment at each step; works backwards from high cost |
| `lod_dol` | Measures division of labor at a LOD timepoint over 5 replication events |
| `lod_task_switching_dol` | Like `lod_dol` but adds task-switching and Shannon mutual information metrics |
| `lod_report_gs` | Reports germ/soma composition and fitness at every LOD step |
| `lod_size` | Reports multicell size, germ count, and workload at every LOD step |

> **Note:** `lod_task_switching_dol` is implemented in this file but is **not registered** in `mt_lr_gls.cpp`'s `gather_tools()`. It cannot be called from the command line without adding `add_tool<ealib::analysis::lod_task_switching_dol>(this)` and recompiling.

---

## Replication Checklist

- [ ] Locate or regenerate checkpoint and LOD files for all 65 seeds
- [ ] Build `mt_lr_gls` from current AvidaMT + ealib-modern (see `INSTALL.md`)
- [ ] Copy executable and `ramp.cfg` into a `config/` folder in your experiment directory
- [ ] Update SLURM scripts: paths, `--array`, `--mail-user`, output directory, time limits
- [ ] Run `fitness_end` condition (65 seeds, 30 hrs each)
- [ ] Run `fitness_end_no_mut` condition (65 seeds, 4 hrs each)
- [ ] Run `fitness_trans` condition (65 seeds, 75 hrs each — seed 4178 needs special handling)
- [ ] Run `fitness_trans_4178` separately with `lod_timepoint_to_analyze=60`
- [ ] Download all output directories to local machine
- [ ] Update `dirname` in `004e_combine_lod_full_fitness.ipynb` to point at your data
- [ ] Note the `num_inviable_ineligible_unicells` column discrepancy and update notebook if needed

---

## Verifying and Packaging Output

After all four conditions finish on the HPCC, verify the output before downloading or archiving.

### Step 1 — Verify with `4_verify_growth_assay.py`

Copy the script to the experiment directory on the HPCC (or run it from wherever the `fitness_end_SEED/` directories live):

```bash
python3 4_verify_growth_assay.py /path/to/experiment/dir
```

Seeds and the log prefix are auto-detected. The script will:
- Check that all four conditions were run on the same seed set
- Report complete / incomplete / missing tallies per condition
- List every problem found for each incomplete seed
- Scan slurm log files for error keywords (time limit, OOM, crash, etc.)
- Print a ready-to-paste `#SBATCH --array=` line for any seeds that need to be rerun

Rerun any failed seeds, then re-verify until all four conditions are clean.

### Step 2 — Tar all four conditions into one archive

Edit `BASE_DIR` and `OUTPUT_NAME` at the top of `5_tar_growth_assay.sbatch`, then submit it from the experiment directory:

```bash
sbatch 5_tar_growth_assay.sbatch
```

Before compressing, the script deletes all `*.log` files and the AvidaMT executable from each seed's `config/` folder. It then tars all four condition folders (`fitness_end_*/`, `fitness_end_no_mut_*/`, `fitness_trans_*/`, `fitness_trans_no_mut_*/`) into a single `{OUTPUT_NAME}.tar.gz` using pigz for parallel compression. Check the `tar_growth_assay_{jobID}.log` it generates — a successful run ends with a `Done at` line.

### Step 3 — Move the archive to the home results folder

Move the `.tar.gz` file to your designated results directory alongside other experiment archives:

```bash
mv {OUTPUT_NAME}.tar.gz ~/path/to/results/
```

---

## Extending 004e to Other Treatments

### Which executables support `lod_fitness_combo`

`lod_fitness_combo` is registered in **all three AvidaMT executables**:

| Executable | Treatment | Mutagenesis during assay (when mutations ON) |
|---|---|---|
| `mt_lr_gls` | Main / dirty work | Standard dirty work (`task_mutagenesis`) — damage goes to performing cell |
| `mt_lr_gls_dol_control` | Distributed dirt | Distributed dirt (`task_mutagenesis_control2`) — damage goes to least-damaged cell |
| `ts_mt` | Task switching | No dirty-work mutagenesis in this executable |

The mutagenesis mechanism is baked into the executable, so the fitness assay automatically replicates the conditions of the original evolutionary experiment for each treatment.

---

### Distributed Dirt

**Background:** The original distributed dirt base runs had a bug — mutations were being discarded rather than distributed to other cells, so the treatment was not actually functioning as designed. The base runs and LOD generation have been fully redone with the bug fixed. All analysis must be run against the new corrected data; Heather's folder 20 data is invalid.

**Template:** Use Heather's folder 20 sbatch files (`07 - Distributed Dirt/`) as the structural template — they have the correct executable, flags, and condition breakdown. Update seeds, paths, and `track_details` as described below.

**Conditions to run** (adapted from folder 20, with `track_details` matching what 4e_new did for dirty work):

| Script | `track_details` | Change from Heather's folder 20 |
|---|---|---|
| `fitness_end` | **1** | flip from 0 — needed for multicell_detail.dat and unicell_detail.dat |
| `fitness_trans` | **1** | flip from 0 — same reason |
| `fitness_end_no_mut` | 0 | no change |
| `fitness_trans_no_mut` | 0 | no change |

**Why `track_details=1` matters here:** Peter specifically needs `multicell_detail.dat` for distributed dirt to assess whether the treatment is functioning as designed and to remake Figs 6A and 6B with experimental data. `unicell_detail.dat` provides the matching data for the unicell revertants. Neither file is generated when `track_details=0`.

**Seeds and paths:** use your new MC seeds from the corrected rerun and point paths to your new checkpoint and LOD files — not to `mt_clean/009/` which is Heather's old buggy data.

---

### Task Switching

`lod_fitness_combo` is registered in `ts_mt` and can be invoked the same way. However, the task-switching ISA is meaningfully different from the main treatment:

| Instruction | `mt_lr_gls` / `mt_lr_gls_dol_control` | `ts_mt` |
|---|---|---|
| `become_soma` | yes | no |
| `if_germ` / `if_soma` | yes | no |
| `if_res_more_than_thresh` / `if_res_less_than_thresh` | yes | no |
| `bc_msg_check_task` | yes | no |
| `get_xy` | no | yes |
| Germ/soma differentiation | yes | no |
| Dirty-work mutagenesis | yes | no |

Two consequences:

1. **The mutation scan covers a smaller ISA.** `lod_fitness_combo` iterates over all instructions in the ISA, so fewer instructions = fewer single-locus mutants tested per genome position.

2. **The biological meaning of "unicell revertant" is different.** The revertant check (`population.size() < 2`) still works mechanically, but task-switching organisms never had germ/soma differentiation to lose in the first place. Whether this assay is the right measurement for task-switching organisms is a scientific question to resolve with Peter before running it.

---

## Summary: Does Running the Adapted Analysis Cover What Peter Needs?

For the distributed dirt treatment specifically: **yes**, running the adapted folder 20 sbatch files with `track_details=1` on end and trans covers everything Peter asked for. Genome length is not a variable in this experiment — the ancestor genome is fixed at 100 instructions and indels are off, so there is nothing to measure.

| Request | Covered? | Notes |
|---|---|---|
| Single dominant genotype isolation | Yes | LOD founder approach uses one genotype throughout |
| `multicell_detail.dat` for distributed dirt | Yes | `fitness_end` and `fitness_trans` with `track_details=1` |
| `unicell_detail.dat` for unicell revertants | Yes | Produced alongside `multicell_detail.dat` when `track_details=1` |
| Distributed dirt through the full analysis process | Yes | Adapted folder 20 sbatch files against corrected rerun data |

---

## Not Yet Addressed

**Task switching** — Peter asked for task switching to be taken through the same full analysis process. This is a separate experiment and has not been addressed. See the Task Switching section above for relevant caveats about ISA differences before running.

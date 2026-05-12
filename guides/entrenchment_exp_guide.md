# Entrenchment Experiment Guide
### For running and managing experiments and analyses

**Trello board:** https://trello.com/invite/b/69d5c86148e87c90bbbe8210/ATTI76dc0d5e80e55f92bea0e21c7b1c32374EF95B51/entrenchment

**Two Jupyter notebooks from Heather** will be sent separately alongside this guide. They are the only analysis scripts I have that are not on the HPCC.

---

## HPCC Access & Support

Log into the HPCC graphical interface (Open OnDemand) at:
**https://ondemand.hpcc.msu.edu/**

- **User documentation:** https://docs.icer.msu.edu/
- **Virtual help desk:** Monday and Thursday, 1–2 PM via Microsoft Teams (no appointment needed) — https://docs.icer.msu.edu/virtual_help_desk/
- **Submit a support ticket:** https://contact.icer.msu.edu
- **Check storage/file quota:** type `quota` in the terminal

---

## Key Directories

| Path | What's there |
|------|-------------|
| `/mnt/research/devolab/mt/mt_clean` | Heather's original data, sbatch files, and cfg files. The README vaguely explains what each folder number contains experiment-wise. |
| `/mnt/ufs18/nodr/home/kgs/` | Where new experiment directories go. Use this for any experiment not yet started. |
| `/mnt/gs21/scratch/groups/devolab/Avida4` | Contains all LODs, Python analysis scripts and the experiment setup script. |
| `/mnt/research/devolab/Avida4` | AvidaMT and ealib-modern repos. |
| `/mnt/research/devolab/entrenchment-revision-data` | Where tar files go when sending data to Peter — navigate into the correct experiment folder, then condition subfolder |

> ⚠️ **Growth and stability assays must run on `/mnt/ufs18/nodr/home/kgs/`.** These assays generate an enormous number of files (millions of small `.dat` files across all seeds and conditions). The scratch directories and home directory have a 1M–1.0M file quota that these assays will blow through. The `nodr` filesystem has a 26.2M file quota, which is large enough to handle them.

> ⚠️ **Watch the `nodr` space quota.** Run `quota` on the HPCC regularly while assays are running. The `nodr` filesystem has a 512G space limit and growth/stability assay output can fill it — if you go over quota, jobs will silently fail mid-run with no error in the log (output files will be incomplete or empty). If you see many seeds failing without any SLURM error patterns in the logs, check `quota` first.

---

## Compiling AvidaMT

**Repos:**
- AvidaMT: https://github.com/kgskocelas/AvidaMT
- ealib-modern: https://github.com/kgskocelas/ealib-modern

Follow the `INSTALL.md` in the AvidaMT repo for both HPCC and local build instructions.

> ⚠️ **Important:** Every time you recompile, Linux permissions reset and you will need to redo `chmod` for devolab group access (unless you know how to fix this issue for us!)

> ⚠️ **If your code changes don't seem to be showing up on the HPCC after pushing to git:** you probably forgot to do a `git pull` in *both* `ealib-modern` *and* `AvidaMT`.

> ⚠️ **Never link directly to the executable in the build directory.** If you do, you won't be able to make any code changes while jobs are running. Instead, always copy the executable you need into the `config/` folder of your experiment directory (see below).

---

## Setting Up a New Experiment

### Step 1: Get Heather's files

In `/mnt/research/devolab/mt/mt_clean`, find the folder corresponding to the experiment you want to replicate (the README there explains the folder contents). Download all the `.sbatch` files and the cfg file from it. The cfg file is always at `config/ramp.cfg` within each experiment folder.

### Step 2: Reconstruct Heather's config

Heather's sbatch files contain the original execution command, which looks something like:

```
./mt_lr_gls_dol_control -c ramp.cfg --ea.rng.seed $SEED --ea.ts.germ_mutation_per_site_p=0.01 --ea.gls.nand_mutation_mult=0 --ea.run.updates=1000000 --ea.mt.cost_start_update=1000000 --ea.mt.tissue_accretion_mult=0
```

From this:
1. **Take note of the executable name** — it will be one of: `mt_lr_gls`, `mt_lr_gls_dol_control`, or `ts_mt`
2. **Move all `--` arguments** (except `-c ramp.cfg` and `--ea.rng.seed $SEED`) into `ramp.cfg`. These command-line arguments were overwriting cfg values, so they represent the actual experiment parameters as Heather ran them.

> ⚠️ **Important:** The task switching (ts_mt) executable uses a different base config (ts_mt.cfg in the AvidaMT repo) than the other executables, so be sure to only use other task switching configs to base future TS configs off of. (Runs will crash if you don't, not generate bad data.)

You now have Heather's cfg as she actually ran it.

### Step 3: Reconcile with the modern config

Take a recently used sbatch file and duplicate it. This modern `ramp.cfg` contains all current parameters, including ones that didn't exist in Heather's time. For every parameter that appears in **both** Heather's cfg and your modern cfg, overwrite the modern value with Heather's value. Then review every parameter that exists **only** in the modern cfg and intentionally set each one to the value you want for your experiment.

### Step 4: Prepare your sbatch file

Open a recently used sbatch file to use as your reference. The setup script in Step 5 creates an empty placeholder sbatch — you'll fill that in using this as your template. Make sure to update:

1. **Header comments** so you know what this script is for
2. **`--time` and `--mem`** to match what Heather used in her sbatch (her files are your starting point for resource estimates)
3. **Alert email address**
4. **`--array=`** to the range of seeds you want to run
5. **Executable line** to use the executable name from Heather's command
6. **File locations** the correct locations for your executable and ramp.cfg

### Step 5: Set up the experiment directory on the HPCC

Navigate to `/mnt/ufs18/nodr/home/kgs/` (for any experiment not yet started — see HPCC Access note above). Run the setup script to create the standard two-phase directory structure:

```bash
bash /mnt/gs21/scratch/groups/devolab/Avida4/analysis-scripts/0_new_experiment_setup.sh your-experiment-name
```

This creates:

```
your-experiment-name/
├── your-experiment-name-uni/          Phase 1 — base run, all 1000 seeds
│   ├── config/
│   │   └── ramp.cfg                   
│   ├── your-experiment-name-base-run.sbatch
│   ├── 1_summarize_run_data.py
├── your-experiment-name-multi/        Phase 2 — MC seeds only, LOD recording on
│   ├── config/
│   │   └── ramp.cfg                   
│   ├── your-experiment-name-rerun-mcs-w-lod-on.sbatch
│   ├── 1_summarize_run_data.py
├── 2_data_verify_and_cleanup.sh       
├── 3_tar_uni_and_multi_folders.sbatch
└── README.md
```

Each subdirectory also gets a `README.md` with a setup checklist. The setup script automatically sets devolab group ownership and read/write permissions on everything it creates.

### Step 6: Set up the uni folder for the base run

Copy the executable from `/mnt/gs21/scratch/groups/devolab/Avida4/executables-to-copy-into-config` into `your-experiment-name-uni/config/`. Then fill in `your-experiment-name-uni/config/ramp.cfg` with your Phase 1 settings (from Steps 2–3; `record_lod` should be 0 or absent). This is the config the base 1000-seed run will use.

Next, fill in `your-experiment-name-uni/your-experiment-name-base-run.sbatch`. Using the OnDemand web portal's built-in graphical file editor (very handy for this) or your prefered editor, update all file paths to point to your uni directory and the executable in its config folder. Do a full read-through to catch anything else referencing the old experiment — names, output directories, etc.

---

## Submitting Jobs

### Test submission

First, open `ramp.cfg` and temporarily set `updates` to 5. A clean way to do this (easy to undo) is to comment out the real value inline:

```text
updates=5 #1000000
```

Then submit with `--array=0` to run just one seed:

```bash
sbatch --array=0 your_sbatch_file.sbatch
```

It may take up to ~10 minutes for the job to move from pending to running, but once it starts it will finish quickly given only 5 updates.

### Verifying a successful test

After the test run, check for:
1. A new folder named `your_experiment_name_1000` containing the expected output files (use Heather's corresponding folder as a reference for what should be there)
2. A log file at the same level as your sbatch — it should have no warnings or errors.
3. Flock-generated `.lock` and `.txt` files

### Full submission

Once the test looks good, remove all files created by the test run, then submit the full array:

```bash
sbatch your_sbatch_file.sbatch
```

> 💡 **Queue tip:** You can submit up to 1,000 jobs at a time, but only 500 jobs can run simultaneously on a user's account. Keep your queue at 499 or fewer so there's always at least one slot is free for test submissions like this.

### Delegating to another user's queue

You can pass the sbatch to someone else to run on their queue by sending them the directory the sbatch is in and directions. If you do:
- Write down their HPCC username and which experiment they're running
- You only need the job number if something crashes (it will be in the crash email) — their username is sufficient for normal monitoring
- To check status of jobs on someone else's account: `squeue -u [username]`

### Checking job details after a job has disappeared from the queue

If jobs are gone from the queue but something went wrong and you need to debug, use `sacct` to look up job accounting information even after a job has ended or crashed:

```bash
sacct -j [jobID] --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,CPUTime
```

---

## Debugging Failed Runs

### First: check the log files

Log files are the first place to look when something goes wrong. The most common issues you'll see there are runs that exceeded wall time or ran out of memory.

For more detailed diagnostics, add the sbatch directive that separates stderr into its own `.err` file. This generates twice as many files but gives you more information about what happened during the run.

### Fast failures (jobs that end in 1–10 seconds)

Almost always one of two things:
1. A filepath issue (the job can't find something)
2. A Linux permissions issue. The job needs:
   - Read and execute permission on the executable
   - Read permission on `ramp.cfg` and any other config files
   - Write and execute permission on the output directory

### Crashes after running for hours (no timeout/OOM in logs)

Use the `.err` log — it's a runtime issue and the error log will give you much more to go on (segfaults, etc.).

If that fails, recompile AvidaMT in debug mode with AddressSanitizer:

```bash
cd $HOME/Avida/AvidaMT
module purge
module load GCC/13.2.0
module load CMake/3.27.6-GCCcore-13.2.0
module load Boost/1.83.0-GCC-13.2.0
cmake -B build-debug -S . \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_CXX_FLAGS="-fsanitize=address" \
    -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address"
cmake --build build-debug --parallel
```

Copy the resulting executable (e.g. `build-debug/mt_lr_gls`) into your experiment's `config/` folder and resubmit the crashing job. It will run slower, but when it crashes the `.err` log (make sure you've turned it on in the SBATCH) will include a full call stack showing exactly where the failure occurred.

---

## A Note on Flock

I use Flock in the sbatch files to generate resource usage summaries for the runs. A few things to know:

- **The lock file is exclusive.** If a `.lock` file from a previous run still exists in a directory, any new job trying to use that directory will crash. This is intentional — it prevents accidental duplicate runs. If you're rerunning inside an already-used directory, delete the old flock files first.
- **Flock is not collecting experiment data.** It only tracks resource usage information (useful for estimating time/memory for resubmissions). It is safe to disable if you don't need/want it.
- **To run two people's jobs simultaneously in the same directory** (e.g., one person runs seeds 0–499, another runs 500–999), just comment out all the flock-related lines in the sbatch. Nothing scientifically important will be lost.

---

## Analysis Scripts

Kate's data processing scripts live in `/mnt/gs21/scratch/groups/devolab/Avida4/processing-scripts`. Each script has a matching README. The setup script (`0_new_experiment_setup.sh`) copies the right scripts into the right places automatically when you create a new experiment. Modify your experiment's copies however you'd like.

The full workflow in order: **script 0 → base runs → script 1 (uni) → LOD reruns → script 1 (multi) → script 2 → script 3.**

### 0. `new_experiment_setup.sh` — create the standard directory structure

Run this once from `/mnt/gs21/scratch/groups/devolab/Avida4` when starting a new experiment:

```bash
bash /mnt/gs21/scratch/groups/devolab/Avida4/analysis-scripts/0_new_experiment_setup.sh your-experiment-name
```

Creates the full two-phase directory tree, with each phase subdirectory getting its own `config/` folder (with a placeholder `ramp.cfg`), a placeholder sbatch file, and script 1. Also copies and pre-fills scripts 2–3 into the top-level folder, and writes a `README.md` in each folder. See Step 5 of Setting Up a New Experiment for the resulting structure.

### 1. `summarize_run_data.py` — analyze results after base runs (run from uni folder)

This is the main script to run after the base runs complete. It reads dat files, log files, and `resource_usage_summary.txt` (if present from flock), then prints a complete action plan telling you exactly what to do next — with copy-paste `#SBATCH` lines.

Before running, open the script and set the configuration block at the top:

```python
DAT_FILE_NAME        = "mt_gls.dat"    # dat file to read in each seed folder
TARGET_FINAL_UPDATE  = 999900          # runs not ending on this update are marked failed
MC_THRESHOLD         = 2.0             # mean_multicell_size >= this → MC = T
MAX_WORKERS          = None            # None = use all available CPU cores
```

- Use `mt_gls.dat` for the `mt_lr_gls` and `mt_lr_gls_dol_control` executables
- Use `mt.dat` for the `ts_mt` executable
- These dat files are human-readable — open one to confirm the column names if needed

Navigate to the uni directory and run:

```bash
python3 1_summarize_run_data.py
```

The script runs in parallel and does not need to be submitted via sbatch.

**What it writes:**

- `summary_<dat>.csv` — one row per seed with: `seed`, `folder`, `final_update`, `mean_multicell_size`, `failed`, `MC`
- `next-array.txt` — `#SBATCH --array=`, `--time`, and `--mem` lines for whichever batch the script recommends next (rerun of failed seeds, or LOD rerun of MC seeds)

**What it prints — the action plan:**

The script classifies every seed and prints up to three action sections. Each section is only shown when the higher-priority ones are clear — fix crashes before rerunning, and finish reruns before LOD.

- **Action A — Debug seeds that crashed:** seeds that exited with an ERROR (not a SLURM resource limit). Highest priority — do not rerun for data collection until the crash is diagnosed. Includes MC=T seeds that crashed (their LOD is blocked until fixed). Instructions for getting a stack trace via `.err` logs and AddressSanitizer are printed.

- **Action B — Rerun failed non-MC seeds:** seeds where MC=F and the run was cut short by SLURM (timeout, OOM, or cancelled). Only shown when no crashes are outstanding. Includes per-seed details (failure reason, how far it got, elapsed time, peak memory) and recommended `--time`/`--mem` values extrapolated from actual resource data with a 1.5x safety buffer.

- **Action C — LOD reruns:** all MC=T seeds that are not crashed. Only shown when Actions A and B are both clear. For each, it tells you whether it completed cleanly or was cut short by a resource limit. Includes recommended `--time` and `--mem` values computed from observed run data multiplied by a LOD overhead factor (1.8x time, 3x memory — based on ~1.2x raw LOD overhead with a 1.5x safety buffer, since LOD runs accumulate founder copies in RAM and write large XML lineage files per epoch).

> **Key distinction:** MC=T seeds that were cut short by SLURM (timeout or OOM) do **not** need to be base-rerun. The LOD run will cover them — you just need to give the LOD run enough time and memory. The script accounts for this when computing LOD resource recommendations.

### LOD Reruns — set up and submit the multi phase

We collect Lines of Descent (LODs) by rerunning completed experiments from scratch with `record_lod=1` set in the cfg file. No recompile is needed — `record_lod` is a config parameter supported by all three executables (`mt_lr_gls`, `mt_lr_gls_dol_control`, `ts_mt`).

To set up a LOD rerun:

1. Fill in `your-experiment-name-multi/config/ramp.cfg` (set `record_lod=1`) and copy the executable into that `config/` folder
2. Fill in `your-experiment-name-rerun-mcs-w-lod-on.sbatch` with the `--array` value from `your-experiment-name-uni/next-array.txt`
3. Update the time and memory allotted in the sbatch if necessary (use the `--time` and `--mem` lines from `next-array.txt` as your starting point)
4. Submit

> **Important efficiency note:** If a run timed out or ran out of memory but evolved multicellularity (`MC=T`), you do not necessarily need to rerun it just to get it to completion. If you already know you'll need the LOD for that run, the LOD rerun will cover it — just make sure to give the rerun enough time and memory to finish.

After the LOD reruns complete, run script 1 again from inside the **multi** folder. If everything finished cleanly, it will print only summary counts with no action items, and you can move on to script 2.

### 2. `data_verify_and_cleanup.sh` — merge and clean up uni + multi folders

Run this after both the uni run phase and the LOD rerun phase are complete. It combines the two experiment directories and cleans up each folder.

Run from the experiment parent directory (e.g. `your-experiment-name/`). If you used the setup script, the `UNI_DIR` and `MULTI_DIR` variables at the top are already pre-filled with your directory names. Otherwise, edit them manually.

Always do a **dry run first** — it reports every action without making any changes. Then run with `--delete` to apply:

```bash
# Dry run — reports what would happen, changes nothing
./data_verify_and_cleanup.sh

# Apply all changes once the dry run output looks correct
./data_verify_and_cleanup.sh --delete
```

The script runs 5 steps in sequence:

**Step 1 — Verify seed coverage:** Confirms the union of both folders forms exactly 1000 consecutive seeds with no gaps. Aborts if the check fails.

**Step 2 — Remove overlapping uni folders:** Deletes any uni folder whose seed also exists in the multi folder. Before deleting, it checks that every file in the uni folder also exists in the corresponding multi folder — mismatches are skipped and flagged instead of deleted.

**Step 3 — Clean up per-seed folders:** For each remaining seed folder: deletes `lod-*.xml` (uni only), gzips any uncompressed `*.xml`, and deletes `ramp.cfg`. Compression uses `pigz -p 8` if available, otherwise falls back to `gzip`.

**Step 4 — Remove log files and flock lock files:** Deletes all `*.log` files and `*.lock` files from both phase directories. Flock `.txt` files (resource usage summaries) are left in place — remove them manually before tarring if you don't want them included.

**Step 5 — Remove executables, scripts, READMEs, and next-array.txt:** Deletes the AvidaMT executable from each phase's `config/` folder (`mt_lr_gls`, `mt_lr_gls_dol_control`, or `ts_mt` — `ramp.cfg` is left in place), plus `1_summarize_run_data.py`, `README.md`, and `next-array.txt` from both phase directories.

### 3. `tar_uni_and_multi_folders.sbatch` — compress both phase folders for Peter

Run this from the experiment parent directory after `data_verify_and_cleanup.sh` is complete:

```bash
sbatch 3_tar_uni_and_multi_folders.sbatch
```

If you used the setup script, `BASE_DIR` and `PREFIX` at the top are already pre-filled. Otherwise edit them:

```bash
BASE_DIR="/path/to/your/experiment-name"
PREFIX="your-experiment-name"
```

Tars `{PREFIX}-uni/` and `{PREFIX}-multi/` simultaneously using `pigz -p 4`. Output is `{PREFIX}-uni.tar.gz` and `{PREFIX}-multi.tar.gz` in `BASE_DIR`. The job is allocated 8 hours and 8 cores — check the `tar_compress_{jobID}.log` it generates to confirm both folders finished.

---

## Growth Assay (lod_fitness_combo)

After the LOD reruns are complete and verified, run the growth assay analysis. Refer to `guides/lod_fitness_combo_guide.md` for full details on setup and what each condition does. The steps here cover verifying the output and packaging it for transfer.

### Verifying and Packaging Output

After all four conditions finish on the HPCC, verify the output before downloading or archiving.

**Step 1 — Verify with `4_verify_growth_assay.py`**

Run the script from the directory containing the `fitness_end_SEED/` etc. folders:

```bash
python3 4_verify_growth_assay.py /path/to/experiment/dir
```

Seeds and the log prefix are auto-detected. The script checks that all four conditions ran on the same seed set, reports complete / incomplete / missing tallies per condition, scans Slurm log files for errors, and prints a ready-to-paste `#SBATCH --array=` line for any seeds that need to be rerun. Rerun any failed seeds and re-verify until all four conditions are clean.

**Step 2 — Tar all four conditions into one archive**

Edit `BASE_DIR` and `OUTPUT_NAME` at the top of `5_tar_growth_assay.sbatch`, then submit it from the experiment directory:

```bash
sbatch 5_tar_growth_assay.sbatch
```

Before compressing, the script deletes all `*.log` files and the AvidaMT executable from each seed's `config/` folder. It then tars all four condition folders (`fitness_end_*/`, `fitness_end_no_mut_*/`, `fitness_trans_*/`, `fitness_trans_no_mut_*/`) into a single `{OUTPUT_NAME}.tar.gz` using pigz for parallel compression. Check the `tar_growth_assay_{jobID}.log` it generates — a successful run ends with a `Done at` line.

**Step 3 — Move the archive to the results folder**

Move the `.tar.gz` file to `/mnt/research/devolab/entrenchment-revision-data/{experiment}/{condition}/` alongside the uni and multi tars:

```bash
mv {OUTPUT_NAME}.tar.gz /mnt/research/devolab/entrenchment-revision-data/{experiment}/{condition}/
```

---

## Stability Assay (lod_entrench_add)

After the LOD reruns are complete and verified, run the stability assay analysis. This uses the `--analyze lod_entrench_add` mode of `mt_lr_gls`, which re-enters the saved run state from the checkpoint and LOD files — no `ramp.cfg` is needed.

**How the binary works:** One call with `--ea.mt.tissue_accretion_add=1` runs all 12 costs (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048) internally, doubling each time until reaching 4096. You do **not** call it once per cost — a single call covers all of them. Output files (`lod_entrench_all.dat`, `lod_entrench_final.dat`) are opened in **overwrite mode**, so running the binary again in the same directory destroys all prior output. Note also that `--ea.run.updates` has no effect on the analysis; `max_update = 200000` is hardcoded inside the function and the config value is ignored.

The assay runs at two timepoints (transition and final). One directory is created per seed per timepoint, containing output from all 12 costs:

```
your-experiment-dir/
├── final_entrench_1/        ← seed 1, final timepoint, all 12 costs
├── final_entrench_2/
├── trans_entrench_1/        ← seed 1, transition timepoint, all 12 costs
├── trans_entrench_2/
└── ...
```

This matches Heather's `008b` data structure.

### Step 1 — Prepare the sbatch files

The sbatch files are in `hpcc_scripts/` in the AvidaMT repo:

- `trans_stability.sbatch` — timepoint 0 (transition)
- `final_stability.sbatch` — timepoint 1 (final)

Copy both to your experiment directory on the HPCC, then open each one and update:

- `--array=` — seed range to run
- `--time=168:00:00` — 168 hours is the ICER 7-day maximum; use this as your baseline since the analysis can be slow
- `WORKDIR` — path to your experiment directory on `nodr`
- `EXE` — path to your copied executable
- `LOD_DIR` — path pattern to your multi (LOD rerun) folders

### Step 2 — Submit

```bash
sbatch trans_stability.sbatch
sbatch final_stability.sbatch
```

Each array job creates one `{tp}_entrench_{seed}/` folder and makes a single binary call that internally runs all 12 costs in order. The job is done when the binary exits.

> ⚠️ **Run on `nodr`.** Stability assays write many small `.dat` files — use `/mnt/ufs18/nodr/home/kgs/` as your `WORKDIR`, not scratch.

### Step 3 — Monitor and verify

While jobs are running or after they finish, run `6_parse_stability_logs.py` from the directory containing the log files to see which costs each seed completed and which timed out:

```bash
python3 6_parse_stability_logs.py /path/to/log/dir
```

After all jobs finish, run `7_verify_stability_assay.py` from the directory containing the `trans_entrench_N/` and `final_entrench_N/` folders:

```bash
python3 7_verify_stability_assay.py /path/to/experiment/dir
```

Seeds are auto-detected. The script checks both conditions (trans and final), confirms all 12 costs are present in each seed's dat files, scans Slurm log files for errors, and prints a ready-to-paste `#SBATCH --array=` line for any seeds that need to be rerun. For incomplete seeds it also prints the resume cost (`--ea.mt.tissue_accretion_add=<next_cost>`).

Pass `--condition trans` or `--condition final` to check only one timepoint. Pass `--delete-failed` to remove incomplete seed directories so they can be cleanly rerun.

### Handling seeds that time out mid-run

If a seed times out before all 12 costs complete:

1. Identify the resume cost — `6_parse_stability_logs.py` reports the last completed cost per seed, and `7_verify_stability_assay.py` prints the exact `--ea.mt.tissue_accretion_add=<next_cost>` flag to use.
2. Resubmit that seed with `--ea.mt.tissue_accretion_add=<next_cost>` into a **new directory** (e.g., `final_entrench_1_resume/`). Do not reuse the original directory — calling the binary there again would overwrite the existing output.
3. After the resume run finishes, **manually concatenate** the partial dat files from both directories (original + resume) before running `7_verify_stability_assay.py` or any downstream analysis. This is the same approach Heather Goldsby used for the original experiment.

### Step 4 — Package for transfer

After all seeds are verified complete, use `8_tar_stability_assay.sbatch` to compress the output:

```bash
sbatch 8_tar_stability_assay.sbatch
```

Edit `BASE_DIR` and `OUTPUT_NAME` at the top before submitting.

---

## Cleanup

Keeping things tidy matters because the HPCC has both storage and file count limits (`quota` to check).

- **Failed run directories** each contain a copy of the executable that is only deleted upon successful completion. A batch of failed runs can eat disk space fast. Once you're done investigating them, `rm -rf` the failed run directories.
- **Old flock files** must be removed before rerunning in an already-used directory, or the new jobs will crash.
- **Log files** are only useful for debugging. Once you no longer need them, delete them — they count against the file quota and have no other value.

---

## Sending Data to Peter

1. Move tar files to `/mnt/research/devolab/entrenchment-revision-data/{experiment}/{condition}/` — navigate into the correct experiment folder, then select or create the experimental condition subfolder if needed (e.g. the pop-regulation experiment has a `limit-1200/` folder where both the uni and multi tars generated with a cell limit of 1200 live).

2. Let Peter know the files are there. Peter has access to everything under `/mnt/research/devolab/entrenchment-revision-data/`, but the system doesn't notify him when files are added, so you need to tell him manually.

> ⚠️ **Do not delete any data just because Peter confirmed he received the tar.** That does not mean he has saved it somewhere safe. Make sure you and Peter explicitly agree together that the data can be deleted from the HPCC before removing anything you don't want gone forever.

---

## R Analysis

Peter has all the R scripts. Coordinate with him on who will run what. Note that some of his scripts took **weeks** to run on his laptop — for those, it may make sense to run them on the HPCC instead.

---

## Using AI Tools for HPCC Work

A few things that have worked well:

- **Claude Code** is helpful for writing and debugging Slurm scripts. Tell it you're using Slurm on the MSU HPCC and ask it to check ICER's documentation. It tends to over-engineer things if you don't tell it to just debug, and it struggles with file paths (faster to fix those yourself). 
- **Pasting error logs and crash output into Claude** (mentioning MSU HPCC for context) can help diagnose issues.
- **Claude is good at writing custom Python data scrapers** if you give it an example `.dat` file from one seed's run and ask it to write a script that scrapes matching data from all runs. You can screenshot the OnDemand file browser to give it the folder structure.
- **Claude and ChatGPT both work well at quickly parsing human-readable resource usage logs** such as the resource_usage_summary.txt and the terminal readout from sacct `sacct -j [jobID] --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,CPUTime`

## Using Claude Code CLI for AvidaMT Dev

It seems to work best when I launch it from the folder than contains both the AvidaMT and ealib-modern directories and start by telling it "AvidaMT is a software program that heavily relies on the ealib-modern library."

---

## HPCC Usernames

To check someone's jobs: `squeue -u [username]`

| Name | Username |
|------|----------|
| Kate | kgs |
| Karen | suzuekar |
| Thad | greine30 |
| Siddharth | unnithan |

Note: Karen, Thad, and Siddharth are all experienced HPCC users and can help with questions if I'm not available.

---

## Current Experiments

| Experiment | Status | Account |
|------------|--------|---------|
| distributed-dirt | Running growth assays | Kate |
| distributed-dirt more seeds | running | Thad |
| task-switching | Running growth assays | Kate |
| base-exp-w-indels | Running growth assays | Kate |
| pop-regulation | Setting up stability assays | Kate |

---

## Known Problems

1. Linux permissions were not automatically inherited from the devolab slack space like I thought, so all but the most recent data is locked to the person who ran it's account until you have them run chmod (unless you have permission as PI that I don't know about). I'm so sorry. The `umask 0002` at the top of the sbatch files now should be correcting this issue, but I haven't had time to check.

2. I think we may start running into storage space issues soon. I do not know the best way to navigate that, which is why this guide only lists other places we can put data. The safest move would be to talk to ICER about what they recommend (explain our specific situation with needing multiple people to be able to run jobs, download data, etc.)

3. Decoding Heather's README explaining which experiment each of her folders contains is still a work in progress. Below is what Peter and I think is the steps we will need and their associated file numbers, but know we could be wrong.

---

## Which of Heather's Folders I Think You'll Need

Note: I haven't found any useful task switching folders of Heather's. I cobbled that together myself from her old paper and the codebase.

The key thing here is that what Peter talks about like analysis scripts are often actually long runs on the HPCC using Avida. Heather wrote the analysis tools into it then either uncommented them as needed & recompiled or has them called via command line, as you'll see in the sbatch files.

- That includes things like generating LOD files, multicell_detail.dat files, growth assays, etc.
- If the sbatch looks like nothing different is happening, but you see different files were generated, or files were populated that weren't on the base run, that's a sign it's the uncommented and recompiled route.

### Main treatment

| Folder | Contents |
| ------ | -------- |
| 1 | overall runs — this is what the 01_w_indel folder's runs are replicating but with indels |
| 2 | lods of runs that achieved multicellularity — will need to do this on the MC indels |
| 4 | mutational assessment |
| 004e | genome collection and detail for multicells — if Peter asks you to generate multicell_detail.dat files, this is where I've seen them |
| 8 | entrench - addition |
| 10 | dol - measure population |

### Distributed dirt controls

| Folder | Contents |
| ------ | -------- |
| 7 | dol control - distributed dirty |
| 9 | dol control - actual lods - distributed dirty |
| 14 | dol control - measure entrenchment add (008) - distributed dirty |
| 16 | controls - entrench add (Meeting Note: likely deprecated) |
| 20 | dol control - distributed dirty - growth assay |

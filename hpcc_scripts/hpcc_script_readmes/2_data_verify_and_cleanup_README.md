# Experiment Cleanup

## Overview

Experiments are run in two phases:

**Phase 1 — Uni runs** (`{experiment-name}-uni/`)
All 1000 seeds are run with LOD tracking disabled.

**Phase 2 — Multi runs** (`{experiment-name}-multi/`)
Only the seeds that evolved multicellularity are rerun, this time with LOD tracking enabled.

Once both phases are complete, `data_verify_and_cleanup.sh` is used to merge and clean up the two folders.

If you used `0_new_experiment_setup.sh` to create your experiment, the `UNI_DIR` and `MULTI_DIR` variables at the top of this script are already pre-filled with the correct names. Otherwise, edit them manually:

```bash
UNI_DIR="your-experiment-uni"
MULTI_DIR="your-experiment-multi"
```

---

## What the script does

**Step 1 — Verify seed coverage**
Confirms that the union of seeds across both folders forms exactly 1000 consecutive seeds with no gaps or duplicates. The script aborts if this check fails.

**Step 2 — Remove overlapping uni folders**
Deletes any uni folder whose seed also has a completed run in the multi folder. Before deleting, it verifies that every file present in the uni folder also exists by name in the corresponding multi folder — if anything is missing, that folder is skipped and flagged with a warning rather than deleted.

**Step 3 — Clean up both folders**
For all remaining experiment folders:

| Action | Uni | Multi |
| --- | --- | --- |
| Delete `lod-*.xml` | ✓ | — |
| Gzip `*.xml` | ✓ | ✓ |
| Delete `ramp.cfg` | ✓ | ✓ |

Compression uses `pigz -p 8` if available, otherwise falls back to `gzip`.

**Step 4 — Remove log files and flock lock files**
Deletes all `*.log` files and `*.lock` files from both phase directories. Flock `.txt` files (resource usage summaries) are left in place — remove them manually before tarring if you don't want them included.

**Step 5 — Remove executables, scripts, READMEs, and next-array.txt**
Deletes the AvidaMT executables (`mt_lr_gls`, `mt_lr_gls_dol_control`, `ts_mt`) from `config/` in both phase directories — `config/ramp.cfg` is left intact. Also deletes `1_summarize_run_data.py`, `README.md`, and `next-array.txt` from both phase directories.

---

## Usage

Run the script from the directory that **contains** both phase folders (the experiment parent directory).

```bash
# Dry run first — reports every action, changes nothing
./data_verify_and_cleanup.sh

# Apply all changes once the dry run output looks correct
./data_verify_and_cleanup.sh --delete
```

Always do a dry run first and check the output before running with `--delete`.

---

## Expected directory structure

```text
your-experiment/                         ← run script from here
├── your-experiment-uni/
│   ├── your_exp_1000/
│   ├── your_exp_1001/
│   └── ...
├── your-experiment-multi/
│   ├── your_exp_lod_1004/
│   ├── your_exp_lod_1009/
│   └── ...
└── data_verify_and_cleanup.sh
```

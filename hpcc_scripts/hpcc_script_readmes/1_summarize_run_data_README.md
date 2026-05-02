# summarize_run_data.py

Scans the current directory for experiment folders, reads the last line of a specified `.dat` file in each one, and writes a summary CSV.

---

## Setup

No install needed — uses only Python standard library. Python 3.10+ required.

---

## Configuration

Open the script and edit the block at the top:

```python
DAT_FILE_NAME       = "mt_gls.dat"   # name of the dat file to read in each folder
TARGET_FINAL_UPDATE = 999900          # runs not ending on this update are marked failed
MC_THRESHOLD        = 2.0             # mean_multicell_size >= this → MC = T
MAX_WORKERS         = None            # None = use all available CPU cores
```

---

## Usage

Navigate to the directory containing your experiment folders, then run:

```bash
python summarize_run_data.py
```

The script will find any folder whose name **ends in 4 digits** (e.g. `dist_dirt_0042`, `run_0001`). It does not care what the folder name starts with.

---

## Output

**`summary_<dat_file_name>.csv`** (e.g. `summary_mt_gls.csv`) — written to the current directory, opens directly in Excel.

| Column | Description |
|---|---|
| `seed` | Trailing 4-digit number from the folder name |
| `folder` | Full folder name |
| `final_update` | Last update value in the dat file |
| `mean_multicell_size` | Last mean_multicell_size value |
| `failed` | `T` if final_update ≠ TARGET_FINAL_UPDATE |
| `MC` | `T` if mean_multicell_size ≥ MC_THRESHOLD |

Any folders with missing or unreadable dat files are skipped and reported in the terminal after the run.

**`next-array.txt`** — written to the current directory when there are seeds that need reruns (Action B) or LOD reruns (Action C). Contains `#SBATCH` directives ready to paste into your sbatch file:

```
#SBATCH --array=1004,1009,1017

#SBATCH --time=4:00:00
#SBATCH --mem=8G

# Resource recommendations (multipliers: 1.8x time, 3x memory)
# Time:   worst case observed: 2h13m00s (seed 1009)
#         × 1.8 LOD factor = 4h00m00s
# Memory: max observed peak: 2714 MB (seed 1004)
#         × 3x LOD factor = 8142 MB
```

The time and memory values are computed from `resource_usage_summary.txt` if it is present, otherwise placeholders (`???`) are written and must be filled in manually before submitting.

---

## Action plan

After printing the CSV summary, the script prints an action plan and writes `next-array.txt`. There are three possible actions, printed only when applicable:

**Action A — Debug seeds that crashed**
Seeds that failed with an ERROR (not a SLURM resource limit). These need to be diagnosed before anything else — the script does not write `next-array.txt` when Action A is the only outstanding task.

**Action B — Rerun failed non-MC seeds**
Seeds that did not evolve multicellularity but were cut short by SLURM (timeout, OOM, or cancelled). Writes `next-array.txt` with recommended `--time` and `--mem` based on observed resource usage × 1.5x buffer.

**Action C — LOD reruns for MC seeds**
Seeds that evolved multicellularity, to be rerun with `record_lod=1`. Writes `next-array.txt` with recommended `--time` and `--mem` based on observed resource usage × 1.8x time and 3x memory. MC seeds that crashed (ERROR) are excluded from the array and flagged separately. MC seeds that failed due to SLURM limits are included — they did not finish their base run but the LOD run will cover them.

Actions are prioritized: A must be resolved before B or C are printed. B must be resolved before C is printed.

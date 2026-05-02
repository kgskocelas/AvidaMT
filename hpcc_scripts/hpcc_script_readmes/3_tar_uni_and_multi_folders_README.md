# tar_uni_and_multi_folders.sbatch — Parallel tar.gz Compression

Compresses a `{PREFIX}-multi` and `{PREFIX}-uni` folder pair simultaneously using parallel gzip.

## Setup

1. The `BASE_DIR` and `PREFIX` variables at the top of the script are pre-filled by `0_new_experiment_setup.sh`. If you created your experiment with that script, no edits are needed. Otherwise, open the file and set them manually:
   ```bash
   BASE_DIR="/path/to/your/experiment"
   PREFIX="your-experiment-name"
   ```
   For example, if your folders are `/data/exp1-multi` and `/data/exp1-uni`, set `BASE_DIR="/data/exp1"` and `PREFIX="exp1"`.

2. The `.sbatch` file is placed in `BASE_DIR` by the setup script. Submit it from that directory:
   ```bash
   cd /path/to/your/experiment
   sbatch 3_tar_uni_and_multi_folders.sbatch
   ```

## Output

- `{PREFIX}-multi.tar.gz` and `{PREFIX}-uni.tar.gz` will appear in `BASE_DIR`
- A log file `tar_compress_{jobID}.log` will also be created there

## Checking the Log

A successful run looks like:
```
Starting compression of exp1-multi and exp1-uni at Mon Apr 21 09:00:00 EDT 2026
Done at Mon Apr 21 10:23:45 EDT 2026
```

Both lines must be present. If the log ends at `Starting compression...` with no `Done`, the job timed out or was killed. If there are any `tar:` or `pigz:` error lines between them, something went wrong with that folder.
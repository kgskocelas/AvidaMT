#!/bin/bash --login
#SBATCH --job-name=tar_sa
#SBATCH --time=08:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=8
#SBATCH --output=tar_sa_%j.log

# ── EDIT THESE TWO LINES EACH TIME ──────────────────────────────────────────
BASE_DIR="/mnt/ufs18/nodr/home/kgs/pop-regulation"
OUTPUT_NAME="stability-assay"
# ────────────────────────────────────────────────────────────────────────────

cd "$BASE_DIR"

echo "Cleaning up before compression at $(date)"

# Delete log files, python scripts, and shell scripts
find . -name "*.log" -o -name "*.py" -o -name "*.sh" | xargs rm -f

echo "Starting compression of stability assays into ${OUTPUT_NAME}.tar.gz at $(date)"

tar -I "pigz -p 8" -cf "${OUTPUT_NAME}.tar.gz" .

echo "Done at $(date)"

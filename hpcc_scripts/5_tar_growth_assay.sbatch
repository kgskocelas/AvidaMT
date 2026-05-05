#!/bin/bash --login
#SBATCH --job-name=tar_ga
#SBATCH --time=08:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=8
#SBATCH --output=tar_ga_%j.log

# ── EDIT THESE TWO LINES EACH TIME ──────────────────────────────────────────
BASE_DIR="/mnt/ufs18/nodr/home/kgs/dist-dirt-growth-assays/seeds-1000-1999"
OUTPUT_NAME="dist-dirt-growth-assay"
# ────────────────────────────────────────────────────────────────────────────

cd "$BASE_DIR"

echo "Cleaning up before compression at $(date)"

# Delete config folder, log files, and python scripts
rm -rf config/
find . -name "*.log" -o -name "*.py" -o -name "*.sh" | xargs rm -f

echo "Starting compression of growth assays into ${OUTPUT_NAME}.tar.gz at $(date)"

tar -I "pigz -p 8" -cf "${OUTPUT_NAME}.tar.gz" .

echo "Done at $(date)"

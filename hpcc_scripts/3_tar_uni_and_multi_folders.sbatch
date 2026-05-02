#!/bin/bash
#SBATCH --job-name=tar_compress
#SBATCH --time=08:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=8
#SBATCH --output=tar_compress_%j.log

# ── EDIT THESE TWO LINES EACH TIME ──────────────────────────────────────────
BASE_DIR="/mnt/gs21/scratch/groups/devolab/Avida4/pop-regulation"
PREFIX="pop-regulation"
# ────────────────────────────────────────────────────────────────────────────

cd "$BASE_DIR"

echo "Starting compression of ${PREFIX}-multi and ${PREFIX}-uni at $(date)"

tar -I "pigz -p 4" -cf "${PREFIX}-multi.tar.gz" "${PREFIX}-multi/" &
tar -I "pigz -p 4" -cf "${PREFIX}-uni.tar.gz"   "${PREFIX}-uni/"   &

wait

echo "Done at $(date)"

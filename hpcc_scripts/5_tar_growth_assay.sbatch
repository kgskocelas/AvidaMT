#!/bin/bash
#SBATCH --job-name=tar_growth_assay
#SBATCH --time=08:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=8
#SBATCH --output=tar_growth_assay_%j.log

# ── EDIT THESE TWO LINES EACH TIME ──────────────────────────────────────────
BASE_DIR="/mnt/gs21/scratch/groups/devolab/Avida4/pop-regulation"
OUTPUT_NAME="pop-regulation-growth-assay"
# ────────────────────────────────────────────────────────────────────────────

cd "$BASE_DIR"

echo "Starting compression of growth assay conditions into ${OUTPUT_NAME}.tar.gz at $(date)"

tar -I "pigz -p 8" -cf "${OUTPUT_NAME}.tar.gz" \
    fitness_end_*/ \
    fitness_end_no_mut_*/ \
    fitness_trans_*/ \
    fitness_trans_no_mut_*/

echo "Done at $(date)"

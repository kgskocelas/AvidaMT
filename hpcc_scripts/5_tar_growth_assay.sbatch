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

echo "Cleaning up before compression at $(date)"

# Delete log files
find fitness_end_*/ fitness_end_no_mut_*/ fitness_trans_*/ fitness_trans_no_mut_*/ \
    -maxdepth 1 -name "*.log" -delete

# Delete executables from config/ folders
find fitness_end_*/ fitness_end_no_mut_*/ fitness_trans_*/ fitness_trans_no_mut_*/ \
    -maxdepth 2 -path "*/config/*" \
    \( -name "mt_lr_gls" -o -name "mt_lr_gls_dol_control" -o -name "ts_mt" \) \
    -delete

echo "Starting compression of growth assay conditions into ${OUTPUT_NAME}.tar.gz at $(date)"

tar -I "pigz -p 8" -cf "${OUTPUT_NAME}.tar.gz" \
    fitness_end_*/ \
    fitness_end_no_mut_*/ \
    fitness_trans_*/ \
    fitness_trans_no_mut_*/

echo "Done at $(date)"

#!/bin/bash
# 6_generate_stability_assay_sbatchs.sh
# Generates 2 sbatch files (one per timepoint: trans and final).
# Each sbatch uses a SLURM array over seeds; within each job all 12
# costs run sequentially into the same {tp}_entrench_{seed}/ folder,
# matching the output structure in Heather's mt_clean/008b/ data.

SEEDS="1023,1045,1051,1058,1091,1116,1148,1177,1205,1218,1252,1253,1270,1293,1313,1328,1333,1377,1400,1409,1426,1440,1513,1554,1603,1612,1627,1688,1700,1709,1724,1736,1749,1752,1767,1793,1798,1858,1891,1909,1950,1955,1980,1981"

COSTS=(1 2 4 8 16 32 64 128 256 512 1024 2048)

mkdir -p complete_entrenchment_scripts

for TIMEPOINT in 0 1; do
    if [ $TIMEPOINT -eq 0 ]; then
        TP_NAME="trans"
    else
        TP_NAME="final"
    fi

    FILENAME="${TP_NAME}_stability.sbatch"
    FILEPATH="complete_entrenchment_scripts/$FILENAME"

    cat > "$FILEPATH" <<EOF
#!/bin/bash --login
#SBATCH --job-name=${TP_NAME}_entrench
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=kgs@msu.edu
#SBATCH --ntasks=1
#SBATCH --mem=5gb
#SBATCH --time=24:00:00
#SBATCH --output=${TP_NAME}_%A_%a.log
#SBATCH --array=$SEEDS

newgrp devolab

umask 0002

set -euo pipefail

pwd; hostname; date

WORKDIR=/mnt/ufs18/nodr/home/kgs/pop-regulation
EXE=/mnt/ufs18/nodr/home/kgs/executables/mt_lr_gls

SEED=\${SLURM_ARRAY_TASK_ID}
EXPER="${TP_NAME}_entrench_\${SEED}"
RUN_DIR="\${WORKDIR}/\${EXPER}"

[[ -x "\${EXE}" ]] || { echo "Missing or non-executable \${EXE}" >&2; exit 1; }

rm -rf "\${RUN_DIR}"
mkdir "\${RUN_DIR}"
cp "\${EXE}" "\${RUN_DIR}/"
cd "\${RUN_DIR}"

module purge
module load GCC/13.2.0
module load Boost/1.83.0-GCC-13.2.0
module load util-linux/2.39-GCCcore-13.2.0

echo "Running stability (entrenchment) analysis"
echo "  Seed: \$SEED"
echo "  Timepoint: $TIMEPOINT ($TP_NAME)"

LOD_DIR=/mnt/gs21/scratch/groups/devolab/Avida4/pop-regulation/pop-regulation-multi/pr_lod_\${SEED}

for COST in ${COSTS[*]}; do
    echo "  Cost: \$COST"
    ./mt_lr_gls \\
        -l "\${LOD_DIR}/checkpoint-1000000.xml.gz" \\
        --analyze lod_entrench_add \\
        --ea.analysis.input.filename "\${LOD_DIR}/lod-1000000.xml.gz" \\
        --ea.mt.lod_analysis_reps=3 \\
        --ea.mt.tissue_accretion_add=\$COST \\
        --ea.mt.cost_start_update=0 \\
        --ea.mt.lod_timepoint_to_analyze=$TIMEPOINT
done

date
EOF

    chmod g+rwx "$FILEPATH"
    echo "Created: $FILEPATH"
done

echo ""
echo "Generated scripts in complete_entrenchment_scripts/"
echo ""
echo "To submit both timepoints:"
echo "  sbatch complete_entrenchment_scripts/trans_entrench.sbatch"
echo "  sbatch complete_entrenchment_scripts/final_entrench.sbatch"

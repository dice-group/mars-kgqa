#!/bin/sh
set -eu
# Sample usage: sbatch -N 1 -n 1 -c 128 -t 336:00:00 --partition hugemem --hugememssd=combined --exclusive --mail-user=$USER_EMAIL --mail-type=BEGIN,END,FAIL load_wikidata_ntzst.sh
# or: sbatch -N 1 -n 1 -c 128 -t 00:05:00 --partition hugemem --hugememssd=combined --exclusive --mail-user=$USER_EMAIL --mail-type=BEGIN,END,FAIL load_wikidata_ntzst.sh
module load lib/zstd/1.5.7-GCCcore-14.3.0

# CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" # does not work for the first slurm script
CUR_SCRIPT_DIR="/scratch/hpc-prf-merlin/nikit/tools/tentris_wd/"

DS_ROOT="/scratch/hpc-prf-merlin/nikit/datasets"

DS_FILENAME="main_wd22012026.nt.zst"
TENTRIS_DB_NAME="wikidata_main_22012026_db"

#DS_FILENAME="sample_main_wd22012026.nt.zst"
#TENTRIS_DB_NAME="wikidata_sample_main_22012026_db"

# Copy the file to memory
TENTRIS_LOCSSD_PATH=$LOCAL_SSD_ALL/tentris_wd_load/

mkdir -p $TENTRIS_LOCSSD_PATH
echo "copying data to SSD.."
cp -r tentris_installation $TENTRIS_LOCSSD_PATH
cp "${DS_ROOT}/${DS_FILENAME}" $LOCAL_SSD_ALL
echo "copy to SSD complete, starting loading.."

cd $TENTRIS_LOCSSD_PATH/tentris_installation

zstdcat "${LOCAL_SSD_ALL}/${DS_FILENAME}" | ./tentris -s $TENTRIS_DB_NAME load --force-no-snapshot --format n-triples

echo "loading complete, copying back the files.."
cp -r $TENTRIS_LOCSSD_PATH/tentris_installation/$TENTRIS_DB_NAME $CUR_SCRIPT_DIR
cp .tentris-debug-log.json $CUR_SCRIPT_DIR/.${TENTRIS_DB_NAME}.tentris-debug-log.json
echo "finished copying data, exiting.."

# To test stuff: srun -N 1 -n 1 -c 128 -t 00:30:00 --partition hugemem --hugememssd=combined --exclusive --pty bash

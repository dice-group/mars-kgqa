#!/bin/bash
set -eu

module load lang/Python/3.13.1-GCCcore-14.2.0
module load system/CUDA/13.0.0
module load tools/Apptainer/1.3.5-GCCcore-13.3.0 # otus only # make sure the cache directories are set right
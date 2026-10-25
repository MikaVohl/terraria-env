#!/bin/bash

cd ~/Projects/RL-scaleff
export PYTHONPATH=$PWD/python TERRARIA_LITE_LIB=$PWD/perf/v7/build-lw2/libterraria.so HIP_VISIBLE_DEVICES=3
CMD=$(head -1 ~/sff/s512/logs/ff_t512c32d2-1801.log | cut -d' ' -f3- | sed 's#--out [^ ]*#--out /home/mvohl/sff/repro/t512-1801#')
mkdir -p ~/sff/repro
~/Projects/RL/.venv/bin/python -u ~/sff/dbg/nan_repro.py $CMD > ~/sff/repro/t512-1801.log 2>&1

#!/bin/bash
# Scan the RK3576 debug port.
#
# No payload is uploaded. With no SD card inserted, SDMMC0_DET_L is high and
# the SoC presents the debug port by default -- see README.md.
#
#   scan.sh              enumerate DP and APs
#   scan.sh "mdw 0x0 8"  run openocd commands against a mem_ap target
set -u
P="${PYTHON:-python3}"
cd "$(dirname "$0")"
echo "board: $($P ../maskrom/tools/usbcheck.py)"
if [ $# -eq 0 ]; then
    exec openocd -c "set SPEED 500" -f oocd/dap.cfg
fi
args=()
for c in "$@"; do args+=(-c "$c"); done
exec openocd -c "set SPEED 500" -f oocd/mem.cfg "${args[@]}" -c shutdown

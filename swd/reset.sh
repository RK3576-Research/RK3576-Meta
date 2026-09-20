#!/bin/bash
# Return the board to maskrom over SWD.
#
# Writes the boot-mode magic and triggers a global soft reset through the
# MEM-AP. Needs only the debug port, so it recovers a board that is hung and
# no longer answering maskrom -- which is when recovery is actually needed.
#
# Uploading maskrom/payload/reboot_to_maskrom.bin does the same thing, but
# requires maskrom to be working, so it cannot recover a hung board.
set -u
P="${PYTHON:-python3}"
cd "$(dirname "$0")"
echo "before: $($P ../maskrom/tools/usbcheck.py)"
openocd -c "set SPEED 1000" -f oocd/mem.cfg \
    -c "mww 0x26026200 0xEF08A53C" \
    -c "mww 0x27200C08 0x0000FDB9" \
    -c shutdown >/dev/null 2>&1
for _ in $(seq 1 30); do
    sleep 1
    $P ../maskrom/tools/usbcheck.py >/dev/null 2>&1 && break
done
echo "after:  $($P ../maskrom/tools/usbcheck.py)"

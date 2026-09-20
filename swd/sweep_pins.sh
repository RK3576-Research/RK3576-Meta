#!/bin/bash
# Find which adapter pin the target's GPIO2_A3 is wired to.
#
# A pin counts as connected only if the target follows it in BOTH directions.
# Driving low and accepting a low reading is not evidence: a floating input
# reads whatever it likes, which is how the first version of this sweep
# "found" all four pins connected at once (run 0049).
#
# The answer is encoded in re-enumeration timing -- fast means the target read
# LOW, slow means HIGH -- so a negative result costs no power cycle.
P="${PYTHON:-python3}"
cd "$(dirname "$0")"
addr() { lsusb -d 2207: 2>/dev/null | sed -E 's/.*Device ([0-9]+).*/\1/'; }

read_pin() {   # $1 = level to drive, $2 = bit; echoes LOW or HIGH as seen by target
  $P tools/ftdi_drive.py "$1" "$2" >/dev/null
  local B t N
  B=$(addr)
  timeout 20 $P ../maskrom/tools/rkusb.py --upload 471 payload/probe_a3_timed.bin >/dev/null 2>&1
  t=0
  for i in $(seq 1 20); do
    sleep 1; t=$i
    N=$(addr); [ -n "$N" ] && [ "$N" != "$B" ] && break
  done
  [ "$t" -le 5 ] && echo LOW || echo HIGH
}

for bit in 0 1 2 3; do
  name=$(case $bit in 0) echo "TCK/SWCLK";; 1) echo "TDI/DO";; 2) echo "TDO/DI";; 3) echo "TMS";; esac)
  st=$($P ../maskrom/tools/usbcheck.py)
  case "$st" in LIVE*) ;; *) echo "bit $bit ($name): board not ready ($st)"; continue;; esac
  lo=$(read_pin 0 $bit); sleep 2
  hi=$(read_pin 1 $bit); sleep 2
  if [ "$lo" = LOW ] && [ "$hi" = HIGH ]; then
    verdict="CONNECTED -- follows both ways"
  else
    verdict="not connected (floating)"
  fi
  echo "bit $bit ($name): driven low -> $lo, driven high -> $hi   $verdict"
done

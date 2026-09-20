#!/bin/bash
# Hunt for the payload's beacon across every serial port and plausible baud.
#
# Only useful against a payload that prints on a loop. A one-shot banner
# cannot be hunted for: by the time you try the second baud it has been and
# gone, and "wrong baud" is indistinguishable from "payload never ran".
#
# Prints a hex preview as well as text, because a baud mismatch produces
# framing garbage rather than silence -- and garbage is itself the useful
# signal that something IS transmitting on that pin.
BAUDS="${BAUDS:-1500000 115200 921600 1152000 250000 57600}"
SECS="${SECS:-2}"
found=0
for p in /dev/ttyUSB*; do
    [ -c "$p" ] || continue
    for b in $BAUDS; do
        if ! stty -F "$p" "$b" raw -echo -echoe -echok 2>/dev/null; then
            echo "$p @ $b : stty REFUSED this baud"
            continue
        fi
        rm -f /tmp/hunt.bin
        timeout "$SECS" cat "$p" > /tmp/hunt.bin 2>/dev/null
        n=$(stat -c%s /tmp/hunt.bin 2>/dev/null || echo 0)
        if [ "$n" -gt 0 ]; then
            found=1
            echo "=== $p @ $b : $n bytes ==="
            head -c 200 /tmp/hunt.bin | cat -v
            echo
            echo "  hex: $(head -c 32 /tmp/hunt.bin | xxd -p | tr -d '\n')"
        else
            echo "$p @ $b : silent"
        fi
    done
done
[ "$found" = 0 ] && echo "NOTHING on any port at any baud"
exit 0

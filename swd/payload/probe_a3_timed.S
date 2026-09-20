// Continuity on GPIO2_A3, answered in TIME rather than by hanging.
//
// The earlier probes encode NO as an infinite loop, which costs a power cycle
// every time the answer is no -- unworkable for sweeping several adapter pins
// to find which one is actually connected.
//
// This one always reboots, but *when* it reboots is the answer:
//     pin LOW  -> reboot immediately        (~1 s to re-enumerate)
//     pin HIGH -> reboot after a long wait  (~12 s to re-enumerate)
// The host times the re-enumeration and reads the bit off the clock.
        .arch armv8-a
        .section .text
        .global _start
#include "reboot.inc"
_start:
        movz    x0, #0x2604, lsl #16
        movk    x0, #0x4040
        movz    w1, #0x0000
        movk    w1, #0xFF00, lsl #16        // GPIO2_A2/A3 -> function 0
        str     w1, [x0]
        dsb     sy

        movz    x22, #0x2AE2, lsl #16
        movz    w1, #0x0000
        movk    w1, #0x000C, lsl #16        // both inputs
        str     w1, [x22, #8]
        dsb     sy

        movz    x9, #0x0008, lsl #16        // settle
1:      subs    x9, x9, #1
        b.ne    1b

        ldr     w2, [x22, #0x70]            // EXT_PORT
        tbz     w2, #3, 2f                  // low -> reboot now

        movz    w23, #32                    // high -> stall ~10s (0.319s per unit, measured run 0052)
3:      movz    x9, #0x0017, lsl #16
1:      subs    x9, x9, #1
        b.ne    1b
        subs    w23, w23, #1
        b.ne    3b
2:      REBOOT_TO_MASKROM

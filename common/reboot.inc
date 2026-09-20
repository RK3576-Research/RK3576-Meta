// Return the board to maskrom.
//
//   PMU1_GRF OS_REG0   0x26026200 <- 0xEF08A53C   BOOT_BROM_DOWNLOAD
//   CRU GLB_SRST_FST   0x27200C08 <- 0x0000FDB9
//
// Values from U-Boot boot_mode.h and cru_rk3576.h.
//
// This is a soft reset. It does not clear pin muxing; see maskrom/README.md.
.macro REBOOT_TO_MASKROM
        movz    x0, #0x2602, lsl #16
        movk    x0, #0x6200
        movz    w1, #0xA53C
        movk    w1, #0xEF08, lsl #16
        str     w1, [x0]
        dsb     sy
        movz    x0, #0x2720, lsl #16
        movk    x0, #0x0C08
        movz    w1, #0xFDB9
        str     w1, [x0]
        dsb     sy
99:     b       99b
.endm

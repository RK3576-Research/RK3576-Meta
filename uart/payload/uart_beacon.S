// UART0 beacon. Muxes uart0m0, configures the controller, transmits on a
// loop, then returns the board to maskrom.
//
// Output appears on the board console adapter at 1500000 8N1.
// Register sources and rationale: uart/README.md

        .arch armv8-a
        .section .text
        .global _start
#include "reboot.inc"

#define UART        0x2AD40000
#define THR         0x00
#define DLH         0x04
#define FCR         0x08
#define LCR         0x0C
#define LSR         0x14
#define SRR         0x88          // DesignWare: bit0 UR, bit1 RFR, bit2 XFR
#define SFE         0x98          // DesignWare: shadow FIFO enable
#define LSR_THRE    5

.macro WR32 addr, val
        movz    x1, #((\addr) >> 16), lsl #16
        movk    x1, #((\addr) & 0xFFFF)
        movz    w0, #((\val) & 0xFFFF)
        movk    w0, #((\val) >> 16), lsl #16
        str     w0, [x1]
.endm

_start:
        WR32    0x272003F0, 0x07FF0300      // SCLK_UART0: mux 3 = xin24m, div 1
        WR32    0x27200834, 0x04000000      // PCLK_UART0 gate, 0 = enabled
        WR32    0x27200838, 0x00200000      // SCLK_UART0 gate, 0 = enabled
        WR32    0x26042010, 0x00FF0099      // GPIO0_D4/D5 -> func 9; 0 at reset
        dsb     sy

        movz    x19, #(UART >> 16), lsl #16

        // Reset controller and both FIFOs, then wait. Writes issued while the
        // reset is in progress are lost.
        mov     w0, #0x07
        str     w0, [x19, #SRR]
        mov     w0, #0x00
        str     w0, [x19, #SRR]
        movz    x9, #0x2000
1:      subs    x9, x9, #1
        b.ne    1b

        mov     w0, #0x83                   // DLAB
        str     w0, [x19, #LCR]
        mov     w0, #0x01                   // DLL 1: 24 MHz / 16 = 1500000
        str     w0, [x19, #THR]
        mov     w0, #0x00
        str     w0, [x19, #DLH]
        mov     w0, #0x03                   // 8N1
        str     w0, [x19, #LCR]
        mov     w0, #0x07                   // enable and clear FIFOs
        str     w0, [x19, #FCR]
        mov     w0, #0x01
        str     w0, [x19, #SFE]
        dsb     sy

        movz    w24, #40
3:      adr     x20, msg
        bl      puts
        movz    x9, #0x0017, lsl #16        // ~0.32 s
1:      subs    x9, x9, #1
        b.ne    1b
        subs    w24, w24, #1
        b.ne    3b

        REBOOT_TO_MASKROM

// Bounded. An unmuxed, unclocked or still-resetting UART never asserts THRE,
// and an unbounded wait hangs the payload before it does anything.
putc:   movz    w3, #0x4000
1:      ldr     w1, [x19, #LSR]
        tbnz    w1, #LSR_THRE, 2f
        subs    w3, w3, #1
        b.ne    1b
        ret
2:      str     w0, [x19, #THR]
        ret

puts:   mov     x6, x30
1:      ldrb    w0, [x20], #1
        cbz     w0, 2f
        bl      putc
        b       1b
2:      mov     x30, x6
        ret

        .section .rodata
msg:    .asciz  "<<<RK3576_UART_BEACON>>> uart0m0, 1500000 8N1\r\n"

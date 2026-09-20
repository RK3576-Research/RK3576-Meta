// Return the board to maskrom. Nothing else.
        .arch armv8-a
        .section .text
        .global _start
#include "reboot.inc"
_start:
        REBOOT_TO_MASKROM

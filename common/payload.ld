/* Flat image: byte 0 is the entry point.
 *
 * The maskrom loads a slot-0x471 image into SRAM and branches to its first
 * byte. Default lld layout links high and page-aligns .rodata, which
 * objcopy -O binary turns into tens of kilobytes of zeros.
 */
ENTRY(_start)
SECTIONS
{
    . = 0;
    .text : {
        *(.text._start)
        *(.text*)
        *(.rodata*)
        *(.data*)
    }
    .bss (NOLOAD) : { *(.bss*) *(COMMON) }
    ASSERT(SIZEOF(.bss) == 0, "payload has .bss but nothing zeroes it")
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.debug*) }
}

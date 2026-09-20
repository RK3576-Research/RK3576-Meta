# Provenance

Every fact in this repository comes from one of four sources. None comes from
Rockchip's proprietary binaries.

| tag | source | copyright status |
|---|---|---|
| `[TRM]` | RK3576 Technical Reference Manual, public | facts |
| `[BSP]` | Rockchip BSP kernel and U-Boot, GPL-2.0 | register addresses and constants are facts, not expression |
| `[MANUAL]` | EVB1 and OK3576-C hardware manuals, public | facts |
| `[MEASURED]` | observed on hardware with a debug probe | original measurement |

## Code

- All payloads, tools and configuration files in this repository are original.
- `maskrom/tools/rkusb.py` implements the Rockchip USB download protocol from
  its wire behaviour. It contains no Rockchip code.
- No code is copied from GPL-2.0 sources, so no GPL obligation attaches.
  Register addresses, bit positions and magic constants cited from U-Boot
  headers are facts about hardware.

## Licence rationale

- MIT.
- Facts are not copyrightable. Citing `BOOT_BROM_DOWNLOAD = 0xEF08A53C` from a
  GPL-2.0 header does not make a work a derivative of that header, in the same
  way that citing a measured voltage does not.
- Had code been copied, GPL-2.0 would apply. None was.

## Explicitly excluded

The following are **not** present in this repository and must not be added:

- Rockchip proprietary binaries, including any `rk3576_ddr_*.bin`.
- Disassembly, decompilation or execution traces of those binaries.
- Register values obtained by observing those binaries run.

Rockchip's binary licence prohibits reverse engineering. This repository
neither contains nor depends on any product of it.

## Measured facts

The following were established by measurement on an EVB1 and are original:

| fact | method |
|---|---|
| SWD DPIDR `0x2ba01477`, AP0 IDR `0x24770002` | OpenOCD enumeration |
| `IOCGRF_MISC_CON` bit 1 must be cleared for SWD | register write, then DP enumeration |
| core runs at ~9.5M instructions/sec in maskrom | timed loop against USB re-enumeration |
| upload error codes do not indicate failure | EP0 liveness before and after upload |
| Tigard buffers prevent adapter-side continuity testing | target-side pin sweep, both directions |
| `uart0m0` and `jtagm1` contend on GPIO0_D4/D5 | pin mux tables plus observed console loss |

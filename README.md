# RK3576 low-level access

Tooling and reference material for maskrom, SWD and UART access on Rockchip
RK3576. Verified on a reference EVB1.

No vendor tools are required. The Rockchip USB download protocol is
reimplemented from scratch in `maskrom/tools/rkusb.py` using libusb via
ctypes. `rkdeveloptool` is not used.

No part of this repository is derived from Rockchip's proprietary binaries.
See [PROVENANCE.md](PROVENANCE.md).

## Contents

| directory | contents |
|---|---|
| [maskrom/](maskrom/) | entering USB download mode, uploading payloads, writing payloads |
| [swd/](swd/) | debug port access, OpenOCD configuration, continuity testing |
| [uart/](uart/) | debug console, pin muxing, the SWD pin conflict |

## Verified configuration

| item | value |
|---|---|
| SoC | RK3576 |
| board | EVB1 (OK3576-C uses the same JTAG header pinout) |
| probe | Tigard V1.1, FT2232H, USB `0403:6010` |
| probe mode | SWD |
| probe I/O | VTGT, referenced to board VCC |
| host | Linux, OpenOCD 0.12.0, Python 3 stdlib only |
| maskrom USB ID | `2207:350e` |
| SWD DPIDR | `0x2ba01477` (ARM ADIv5 SW-DP) |
| AP 0 IDR | `0x24770002` (ARM MEM-AP, AMBA AHB) |

## Common failures

`cannot read IDR` from OpenOCD. Only three things decide this:

- SWDIO must connect to the adapter's **TDI** pin. OpenOCD's ftdi driver does
  not drive TMS in SWD mode. This is the most common cause.
- The probe must be in SWD mode, not JTAG mode.
- An SD card must not be inserted. The JTAG pins are the SD-card pins, and
  `SDMMC0_DET_L` selects between the two in hardware.

No payload or register write is required. With no card inserted, the SoC
presents the debug port by default.

Silent UART:

- UART0's default mux (`uart0m0`) and `jtagm1` are the same two pins. A probe
  attached to those pins will contend with the serial adapter.

Upload reports `LIBUSB_ERROR_NO_DEVICE`, `TIMEOUT` or `IO`:

- Expected. All three indicate success. See [maskrom/](maskrom/).

Results that do not reproduce after a power cycle:

- The software return-to-maskrom is a soft reset and does not clear pin
  muxing. State carries between payloads. Power-cycle between trials when
  comparing register sequences.

## Licence

MIT. All code here is original. Register addresses, bit positions and magic
constants are cited from public documentation and from GPL-2.0 U-Boot headers,
but those are facts about hardware rather than copyrightable expression, so
they impose no licence obligation. No code is copied from GPL sources.

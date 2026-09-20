# MaskROM

MaskROM is the RK3576 USB download mode. It enumerates as `2207:350e` and
accepts code over a vendor control transfer.

## Entering maskrom

| method | procedure | notes |
|---|---|---|
| button | hold `MASKROM` while applying power | EVB1 has one, beside the SD socket |
| boot flash | ground SPI flash CLK or DATA at power-on | ROM falls back when no valid image is found |
| software | write boot-mode magic, then global soft reset | no physical access required |

Software method:

| register | address | value |
|---|---|---|
| `PMU1_GRF OS_REG0` | `0x26026200` | `0xEF08A53C` |
| `CRU GLB_SRST_FST` | `0x27200C08` | `0x0000FDB9` |

- `BOOT_BROM_DOWNLOAD` = `0xEF08A53C` — U-Boot `arch/arm/include/asm/arch-rockchip/boot_mode.h`
- `RK3576_GLB_SRST_FST` = `0xc08` — U-Boot `arch/arm/include/asm/arch-rockchip/cru_rk3576.h`

`payload/reboot_to_maskrom.S` implements this in 48 bytes.

Any payload ending with the `REBOOT_TO_MASKROM` macro from `payload/reboot.inc`
returns the board to maskrom when it finishes. A payload that spins instead
requires a power cycle before the next upload.

### The soft reset does not clear SoC state

- `GLB_SRST_FST` is a soft reset. It does not restore all peripheral state.
- Pin muxing set by a payload **survives** it. A subsequent payload that
  writes no registers at all can still find the debug port enabled.
- Any experiment that compares register sequences is therefore invalid unless
  the board is **fully power-cycled between trials**.
- This is a property of the convenience, not a defect: the same mechanism that
  removes the need to touch the board also carries state between runs.

## Uploading

```sh
tools/rkusb.py --list
tools/rkusb.py --upload 471 payload/your.bin
```

| slot | purpose |
|---|---|
| `0x471` | first stage, conventionally DDR init |
| `0x472` | second stage loader |

- Images have no header. Byte 0 is the entry point.
- The ROM runs a `0x471` image on receipt.
- If that image returns rather than hanging, the ROM continues servicing USB
  and accepts a `0x472` image.
- The two-stage sequence is how DRAM is initialised before a second payload
  runs.

## Upload errors do not indicate failure

The upload reports one of:

```
LIBUSB_ERROR_NO_DEVICE
LIBUSB_ERROR_TIMEOUT
LIBUSB_ERROR_IO
```

- All three indicate success.
- The ROM executes a `0x471` download on receipt and stops servicing USB
  before acknowledging the control transfer.
- The host observes the device disappearing mid-request.
- The exit code carries no information about whether the payload ran.

Determine success from endpoint 0 instead:

```sh
tools/usbcheck.py      # LIVE before upload, STALE after = payload ran
```

## `lsusb` does not indicate liveness

- When a payload takes over, the kernel retains the device node until
  something attempts to use it.
- `lsusb -v` reads cached descriptors and continues to succeed.
- A board that enumerated once and then stopped responding is
  indistinguishable from a working one by `lsusb` alone.
- Only a live control transfer distinguishes them. `tools/usbcheck.py` issues
  one.

## Writing payloads

```sh
../common/build.sh payload/your.S
```

- Builds with clang and lld to a flat binary.
- `common/payload.ld` places `.text._start` first and removes alignment padding.
  Default lld layout plus `objcopy -O binary` produces tens of kilobytes of
  zeros.

Environment characteristics:

| property | value | consequence |
|---|---|---|
| instruction rate | ~9.5M/s, measured | a `subs`/`b.ne` loop of `0x170000` iterations takes 0.319 s, not ~1 s |
| stack | provided by ROM, valid on entry | payloads may push immediately |
| UART | not muxed by the ROM | see below |

- Delay loops calibrated by assuming 24 MHz produce windows roughly three
  times shorter than intended.
- A payload that prints before doing its work can hang in `putc` if the UART
  is unmuxed or contended, because `THRE` never asserts. Bound the wait or
  omit UART output.

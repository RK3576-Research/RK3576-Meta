# SWD

RK3576 exposes a 2-pin SWD debug port. 4-wire JTAG is not available: TDI and
TDO are not brought out to the board header.

The board header is labelled TCK/TMS because SWD reuses those SoC pins. The
probe must be in SWD mode, not JTAG mode.

## Verified result

```
Info : SWD DPIDR 0x2ba01477
AP 0 IDR = 0x24770002
```

| field | value | meaning |
|---|---|---|
| DPIDR | `0x2ba01477` | ARM ADIv5 SW-DP, designer `0x23B` (ARM) |
| AP 0 IDR | `0x24770002` | ARM MEM-AP, class MEM-AP, type 2 = AMBA AHB |

The AHB MEM-AP provides memory access without a CPU target. This matters
because the vendor tree describes these pins as the Cortex-M0 debug ports
rather than the Cortex-A cluster's.

## Wiring

Board JTAG header, EVB1 §3.25 (OK3576-C identical):

```
PIN1: VCC    PIN2: TMS    PIN3: TCK    PIN4: GND
```

| Tigard pin | Board pin | Signal |
|---|---|---|
| TDI | PIN2 (TMS) | SWDIO |
| TCK | PIN3 (TCK) | SWCLK |
| GND | PIN4 | ground |
| VTGT | PIN1 (VCC) | I/O voltage reference |

- SWDIO connects to the adapter's **TDI** pin, not its TMS pin.
- OpenOCD's ftdi driver transmits SWDIO on TDI and samples it on TDO. It does
  not drive TMS in SWD mode.
- Board-TMS to adapter-TMS is electrically connected and functionally inert.
  It measures as a good wire.
- Tigard's mode switch combines DI and DO into SWDIO on **CORTEX header pin
  2** only, not on the separately labelled TMS breakout pin.

## Probe configuration

| switch | position |
|---|---|
| mode | SWD |
| voltage | VTGT with PIN1 wired, or 3V3 with PIN1 unconnected |

- Do not use both. On 3V3 the Tigard drives VTGT as an output; wiring it to
  board VCC connects two supplies.

Verify the mode switch electrically:

```sh
tools/ftdi_tietest.py
```

| output | meaning |
|---|---|
| `TDO follows TDI ... ARE tied` | SWD mode |
| `NOT tied` | JTAG mode; DI and DO are not combined |

## SD card

The JTAG pins are the SD-card pins. From `rk3576-pinctrl.dtsi`:

| function | pins | mux |
|---|---|---|
| `sdmmc0_bus4` | GPIO2_A2 (d2), GPIO2_A3 (d3) | 1 |
| `jtagm0_pins` | GPIO2_A2 (tck), GPIO2_A3 (tms) | 9 |

- An inserted card drives these lines and adds the socket's pull-ups.
- SWD will not function with a card present.
- The EVB1 manual states this in a single line in §3.25.

## Bring-up

No payload is required. With the board in maskrom and nothing uploaded:

```sh
./scan.sh                      # enumerate DP and APs
./scan.sh "mdw 0x00000000 8"   # read BootROM
./scan.sh "dump_image /tmp/sram.bin 0x3fe70000 0x80000"
```

Verified from a cold boot with no upload of any kind, confirming afterwards
that endpoint 0 was still live and therefore that nothing had executed.

### Requirements

Only three things decide whether the debug port answers:

| requirement | detail |
|---|---|
| wiring | SWDIO on the adapter's **TDI** pin, not TMS |
| probe mode | SWD, verified with `tools/ftdi_tietest.py` |
| SD card | must be absent |

The SD card requirement is the mux selection. `SDMMC0_DET_L` arbitrates the
pin group in hardware — low selects SDMMC, **high selects JTAG, and high is
the default**. With no card in the socket, the SoC presents the debug port
without software involvement.

## Registers: what is not needed, and what breaks it

An earlier version of this document specified four register writes as
necessary. **None of them are.** Measured from a cold boot:

| payload | writes | result |
|---|---|---|
| none uploaded at all | — | DP answers |
| `v_nothing` | none | DP answers |

The four writes were: `IOCGRF_MISC_CON` bit 1, the `jtagm0` IOMUX,
`TOP_CRU_GATE_CON19`, and `TOP_CRU_SOFTRST_CON19`. They are harmless but
redundant on a board with no SD card inserted.

### `SYS_GRF_SOC_CON7` removes the debug port

| value written | result |
|---|---|
| `0x00` | DP stops answering |
| `0x08` | DP stops answering |
| `0x10` | DP stops answering |

- Every value tried takes away a working debug port, including the two U-Boot
  documents as selecting the PMU-MCU (`0x08`) and BUS-MCU (`0x10`).
- **Do not write this register** when using SWD on these pins.
- U-Boot writes it only when attaching a debugger to a Cortex-M0, and those
  code paths are commented out in the vendor tree.

This result is unaffected by the state-persistence caveat below: removing a
working debug port is evidence regardless of how it came to be working.

### State survives the soft reset

- `CRU_GLB_SRST_FST`, used by payloads to return to maskrom, does not clear
  pin muxing.
- Comparisons between register sequences are invalid unless the board is
  fully power-cycled between trials — including unplugging the USB-C data
  cable, which can back-feed enough to prevent a full reset.
- This is how the incorrect four-register claim survived initial testing.

## Recovering a hung board

A payload that hangs leaves the board unable to accept another upload:
maskrom's endpoint 0 stops answering, so the usual
`reboot_to_maskrom` payload cannot be delivered.

```sh
./reset.sh
```

- Writes the boot-mode magic and triggers a global soft reset through the
  MEM-AP.
- Uses only the debug port, so it works when maskrom does not.
- Verified by uploading a four-byte payload that branches to itself: endpoint
  0 goes stale, and this returns the board to live maskrom.

No physical access is required, so hardware iteration does not stall on a
hung payload.

## Continuity testing

The adapter cannot be used to check its own wiring:

- Tigard's output buffers are always enabled and push-pull.
- The FT2232H reads its own buffer output, not the target.
- Driving a target GPIO against those buffers creates contention rather than
  measuring it.

Test in the opposite direction — the adapter holds a level, the target reads
it:

```sh
./sweep_pins.sh
```

- Reports which adapter pin each target pin follows.
- Requires the target to follow in **both** directions.
- A floating input reading low while driven low is not evidence. A sweep that
  only drives low reports every pin as connected.

## Files

| path | contents |
|---|---|
| `scan.sh` | scan the debug port; no payload needed |
| `reset.sh` | return a hung board to maskrom over SWD |
| `sweep_pins.sh` | continuity, measured from the target side |
| `oocd/tigard-swd.cfg` | adapter config; stock `tigard.cfg` omits `SWD_EN` and refuses SWD |
| `oocd/dap.cfg` | enumerate DP and APs |
| `oocd/mem.cfg` | `mem_ap` target for `mdw` and `dump_image` |
| `tools/ftdi_tietest.py` | mode switch verification |
| `tools/ftdi_drive.py` | hold one adapter pin at a level |

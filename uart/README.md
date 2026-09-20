# UART

RK3576 UART0 is the debug console. It is a Synopsys DesignWare 8250.

| property | value | source |
|---|---|---|
| base | `0x2AD40000` | `rk3576.dtsi`, `uart0: serial@2ad40000` |
| compatible | `rockchip,rk3576-uart`, `snps,dw-apb-uart` | `rk3576.dtsi` |
| `reg-shift` | 2 | `rk3576.dtsi` |
| `reg-io-width` | 4 | `rk3576.dtsi` |
| default mux | `uart0m0_xfer` | `rk3576.dtsi` `pinctrl-0` |
| EVB1 console | `earlycon=uart8250,mmio32,0x2ad40000` | `rk3576-evb1-v10-dv.dts` |

## Verified

Vendor DDR binary and U-Boot SPL, captured over the FT232R at 1500000 8N1:

```
DDR e10b4dfeaf wesley.yao 26/04/29-09:42:15,fwver: v1.13
LPDDR5, 2736MHz
channel[0] BW=16 Col=10 Bk=16 CS0 Row=16 CS1 Row=16 CS=2 Die BW=16 Size=4096MB
Manufacturer ID:0xff
U-Boot SPL next-dev-ga27a89c5fa1-260227 #lxh (Mar 02 2026 - 14:55:45), fwver: v1.09
Ram size: c0000000
```

`payload/uart_beacon.S`, transmitting on a loop:

```
<<<RK3576_UART_BEACON>>> uart0m0, 1500000 8N1
```

## Pin muxing

| function | pins | mux |
|---|---|---|
| `uart0m0` | GPIO0_D4 (tx), GPIO0_D5 (rx) | 9 |
| `uart0m1` | GPIO2_A0 (rx), GPIO2_A1 (tx) | 9 |
| `jtagm1` | GPIO0_D4 (tck), GPIO0_D5 (tms) | 10 |
| `jtagm0` | GPIO2_A2 (tck), GPIO2_A3 (tms) | 9 |

IOMUX registers:

| mux | register | address | value |
|---|---|---|---|
| `uart0m0` | `GPIO0D_IOMUX_SEL_H` | `0x26042010` | `0x00FF0099` |
| `uart0m1` | `GPIO2A_IOMUX_SEL_L` | `0x26044040` | `0x00FF0099` |

Addresses are derived from the BSP pinctrl bank table, which is relative to
`ioc_grf` at `0x26040000`:

```
RK3576_PIN_BANK(0, "gpio0", 0, 0x8, 0x2004, 0x200C)
RK3576_PIN_BANK(2, "gpio2", 0x4040, 0x4048, 0x4050, 0x4058)
```

- The four offsets are the iomux bases for groups A, B, C and D.
- Each group has `_L` (pins 0–3) and `_H` (pins 4–7), four bytes apart.
- GPIO0 group D is at `0x200C`, so D4–D7 are at `0x26040000 + 0x2010`.
- Independently corroborated: the vendor DDR binary writes `0x26042010` with
  `0x000f0009` then `0x00f00090`, setting D4 and D5 to function 9.

- MaskROM does not mux the UART pins. A payload that programs the UART
  controller without muxing writes into a controller whose pins are connected
  to nothing.

## UART0_M0 and jtagm1 share pins

- `uart0m0` and `jtagm1` are the same two SoC pins, GPIO0_D4 and GPIO0_D5.
- Function 9 selects UART, function 10 selects JTAG.
- The two cannot be used simultaneously on this mux.
- A debug probe attached to those pins drives them continuously and will
  contend with a serial adapter.

This is also the mechanism behind Rockchip's documented "force JTAG" feature,
which switches the pins to JTAG when UART RX is held. Rockchip's release notes
for the RK3576 DDR binary record:

> "Increased force jtag time to 1 second — Individual boards with problematic
> uart hardware design will be switched to jtag mode"

- A floating or driven-low RX line can therefore silently disable the console.

## Which mux the console uses

Measured from a cold boot, reading before and after the vendor binary runs:

| register | at reset | after vendor binary |
|---|---|---|
| `0x26042010` GPIO0D_H | `0x00000000` | `0x00000099` |
| `0x26044040` GPIO2A_L | `0x00009900` | `0x00009900` |

- The console is **`uart0m0`**, GPIO0_D4/D5. The vendor binary muxes it; the
  reset state does not.
- `0x26044040` reads `0x9900` at reset, meaning GPIO2_A2/A3 are already
  `jtagm0`. That is why SWD needs no payload — see [../swd/](../swd/).
- Do not mux both UART0 options at once. UART0 then drives two pin pairs and
  listens on two, and the controller receives its own transmission, visible as
  `RBR` returning the character just sent.

## Clocks

| clock | register | bit |
|---|---|---|
| `PCLK_UART0` | `CLKGATE_CON13` `0x27200834` | 10 |
| `SCLK_UART0` | `CLKGATE_CON14` `0x27200838` | 5 |
| `SCLK_UART0` mux/div | `CLKSEL_CON60` `0x272003F0` | mux 10:8, div 7:0 |

- `RK3576_CLKGATE_CON(x) = x*4 + 0x800`, `RK3576_CLKSEL_CON(x) = x*4 + 0x300`
  — BSP `clk.h`.
- Gates are write-masked and active-high: write 0 to the bit to enable.
- `clk_uart_p = { gpll, cpll, aupll, xin24m, ... }`, so mux index **3** is the
  24 MHz crystal. Divider 0 divides by 1.
- 24 MHz reference with UART divisor 1 gives 1500000 baud.

## Controller init

| step | register | offset | value |
|---|---|---|---|
| 1 | `SRR` | `0x88` | `0x07` — reset UART and both FIFOs |
| 2 | `SRR` | `0x88` | `0x00` |
| 3 | — | — | **settle delay** |
| 4 | `LCR` | `0x0C` | `0x83` — DLAB set |
| 5 | `DLL` | `0x00` | `0x01` |
| 6 | `DLH` | `0x04` | `0x00` |
| 7 | `LCR` | `0x0C` | `0x03` — 8N1, DLAB clear |
| 8 | `FCR` | `0x08` | `0x07` — enable and clear FIFOs |
| 9 | `SFE` | `0x98` | `0x01` — shadow FIFO enable |

- `SRR` and `SFE` are DesignWare shadow registers, not part of the 8250.
- **Step 3 is required.** The reset is not instantaneous and writes issued
  during it are lost. The symptom is `LCR` reading back `0x00` and the
  transmitter never asserting `THRE`, while every clock, mux and select
  register reads correct.

## Diagnosing over SWD

Read the controller while a payload holds the core:

| register | address | healthy |
|---|---|---|
| `LCR` | `0x2AD4000C` | `0x03` |
| `LSR` | `0x2AD40014` | `0x60` — THRE and TEMT |
| `USR` | `0x2AD4007C` | `0x06` — TX FIFO empty |

- `LCR = 0x00` means the init did not take; see step 3.
- `LSR` bit 0 set means data was received. If it is the character just sent,
  both UART0 mux options are enabled.

## `/dev/ttyUSB*` numbering is not stable

- The Tigard and the FT232R swapped device numbers between runs in a single
  session.
- Identify adapters by USB ID, not device number.

## Finding the console

```sh
./uart_hunt.sh
```

- Sweeps every `/dev/ttyUSB*` against six candidate baud rates.
- Prints a hex preview as well as text: a baud mismatch produces framing
  garbage rather than silence, and garbage indicates something is
  transmitting.
- Requires a payload that transmits repeatedly. A one-shot banner cannot be
  hunted for, because it has already been sent by the time the second baud is
  tried.

`payload/uart_beacon.S` muxes both UART0 options, programs the controller, and
transmits on a loop, then returns the board to maskrom.

## `putc` can hang a payload

```asm
1:  ldr  w1, [x19, #UART_LSR]
    tbz  w1, #LSR_THRE, 1b
```

- If the UART is unmuxed or contended, `THRE` never asserts and this loop does
  not terminate.
- A payload that prints before doing its work will never do its work.
- Bound the wait, or omit UART output from payloads whose function matters
  more than their logging.

## Files

| path | contents |
|---|---|
| `uart_hunt.sh` | port and baud sweep |
| `payload/uart_beacon.S` | muxes both UART0 options and transmits on a loop |

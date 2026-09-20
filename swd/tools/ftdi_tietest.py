#!/usr/bin/env python3
"""Are the Tigard's TDI and TDO pins tied together?

OpenOCD's ftdi driver does SWD by driving SWDIO out on TDI and sampling it on
TDO, which only works if the two are joined externally. Adapters intended for
SWD do that with a series resistor on the board. Whether Tigard does decides
which header pin the SWDIO lead belongs on, so it is worth measuring rather
than believing a comment.

Method: drive TDI (bit 1) as an output, low, and read TDO (bit 2). If they are
tied, TDO follows to 0. If they are independent, TDO stays high on its
pull-up. Then repeat driving high, to rule out a pin that reads 0 regardless.
"""


import ctypes
import sys
import time

VID, PID = 0x0403, 0x6010
TIGARD_MPSSE_INTERFACE = 2          # FTDI wIndex: 1 = channel A, 2 = channel B

SIO_RESET = 0x00
SIO_SET_BITMODE = 0x0B
SIO_SET_LATENCY_TIMER = 0x09
BITMODE_RESET = 0x00
BITMODE_MPSSE = 0x02

REQ_OUT = 0x40                       # vendor, host->device, device recipient
REQ_IN = 0xC0

WATCH_SECONDS = 4.0

PIN_NAMES = ["TCK/SWCLK", "TDI", "TDO", "TMS/SWDIO",
             "GPIOL0(nTRST)", "GPIOL1(nSRST)", "GPIOL2", "GPIOL3"]


class DeviceDescriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8), ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16), ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8), ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8), ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16), ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8), ("iProduct", ctypes.c_uint8),
        ("iSerialNumber", ctypes.c_uint8), ("bNumConfigurations", ctypes.c_uint8),
    ]


def main() -> int:
    lib = ctypes.CDLL("libusb-1.0.so.0")

    # Every pointer-taking entry point needs explicit argtypes: without them
    # ctypes assumes C int and silently truncates 64-bit handles, which
    # segfaults rather than erroring.
    lib.libusb_init.argtypes = [ctypes.c_void_p]
    lib.libusb_get_device_list.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))]
    lib.libusb_get_device_list.restype = ctypes.c_ssize_t
    lib.libusb_get_device_descriptor.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(DeviceDescriptor)]
    lib.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_close.argtypes = [ctypes.c_void_p]
    for fn in ("libusb_detach_kernel_driver", "libusb_attach_kernel_driver",
               "libusb_claim_interface", "libusb_release_interface"):
        getattr(lib, fn).argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_control_transfer.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16,
        ctypes.c_uint16, ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint]
    lib.libusb_bulk_transfer.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_int,
        ctypes.POINTER(ctypes.c_int), ctypes.c_uint]

    ctx = ctypes.c_void_p()
    lib.libusb_init(ctypes.byref(ctx))

    lst = ctypes.POINTER(ctypes.c_void_p)()
    n = lib.libusb_get_device_list(ctx, ctypes.byref(lst))
    handle = ctypes.c_void_p()
    for i in range(n):
        desc = DeviceDescriptor()
        lib.libusb_get_device_descriptor(lst[i], ctypes.byref(desc))
        if (desc.idVendor, desc.idProduct) == (VID, PID):
            if lib.libusb_open(lst[i], ctypes.byref(handle)) != 0:
                print("libusb_open failed", file=sys.stderr)
                return 1
            break
    else:
        print(f"no {VID:04x}:{PID:04x} found", file=sys.stderr)
        return 2

    iface = TIGARD_MPSSE_INTERFACE - 1
    lib.libusb_detach_kernel_driver(handle, iface)
    if lib.libusb_claim_interface(handle, iface) != 0:
        print("claim_interface failed", file=sys.stderr)
        return 1

    def ctrl(req, value):
        return lib.libusb_control_transfer(
            handle, REQ_OUT, req, value, TIGARD_MPSSE_INTERFACE, None, 0, 1000)

    ctrl(SIO_RESET, 0)                      # reset the channel
    ctrl(SIO_RESET, 1)                      # purge RX
    ctrl(SIO_RESET, 2)                      # purge TX
    ctrl(SIO_SET_LATENCY_TIMER, 1)          # 1 ms, or short replies never flush
    ctrl(SIO_SET_BITMODE, (BITMODE_RESET << 8) | 0x00)
    ctrl(SIO_SET_BITMODE, (BITMODE_MPSSE << 8) | 0x00)   # mode<<8 | dirmask; 0 = all inputs
    time.sleep(0.2)

    # MPSSE 0x81 = "read data bits, low byte". Every pin is an input, so the
    # reply is whatever the outside world is holding the lines at.
    def read_low():
        out = (ctypes.c_ubyte * 1)(0x81)
        wrote = ctypes.c_int()
        lib.libusb_bulk_transfer(handle, 0x04, out, 1, ctypes.byref(wrote), 1000)
        deadline = time.time() + 0.5
        while time.time() < deadline:
            buf = (ctypes.c_ubyte * 64)()
            got = ctypes.c_int()
            lib.libusb_bulk_transfer(handle, 0x83, buf, 64, ctypes.byref(got), 500)
            if got.value > 2:
                return buf[got.value - 1]
        return None

    def set_low(value, direction):
        # MPSSE 0x80 = set data bits low byte: value, direction (1 = output)
        out = (ctypes.c_ubyte * 3)(0x80, value, direction)
        wrote = ctypes.c_int()
        lib.libusb_bulk_transfer(handle, 0x04, out, 3, ctypes.byref(wrote), 1000)
        time.sleep(0.05)

    TDI, TDO = 1, 2
    results = {}
    for drive in (0, 1):
        # TDI output at `drive`, everything else input
        set_low((drive << TDI), (1 << TDI))
        v = read_low()
        results[drive] = v
        if v is None:
            print(f"drive TDI={drive}: no sample")
        else:
            print(f"drive TDI={drive}: low byte 0x{v:02X}  "
                  f"TDI reads {(v >> TDI) & 1}, TDO reads {(v >> TDO) & 1}")
    set_low(0x00, 0x00)

    ctrl(SIO_SET_BITMODE, (BITMODE_RESET << 8) | 0x00)
    lib.libusb_release_interface(handle, iface)
    lib.libusb_attach_kernel_driver(handle, iface)
    lib.libusb_close(handle)

    lo, hi = results.get(0), results.get(1)
    if lo is None or hi is None:
        print("\ninconclusive: MPSSE did not return samples")
        return 1
    tdo_lo, tdo_hi = (lo >> TDO) & 1, (hi >> TDO) & 1
    print()
    if tdo_lo == 0 and tdo_hi == 1:
        print("VERDICT: TDO follows TDI. They ARE tied together on the adapter,")
        print("         so SWDIO is on the TDI/TDO net and either pin carries it.")
        return 0
    if tdo_lo == 1 and tdo_hi == 1:
        print("VERDICT: TDO stayed high while TDI was driven low. NOT tied.")
        print("         SWDIO needs TDI and TDO joined externally, or wired to TDI")
        print("         with TDO left on the same node at the target.")
        return 1
    print(f"VERDICT: unclear -- TDO read {tdo_lo} then {tdo_hi}.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Drive TCK low and LEAVE it driven, so the target can read it.

The motion test failed backwards: Tigard's buffers are always-on outputs, so
the adapter cannot observe a target-driven pin. But that same property makes
the reverse test work. Have the ADAPTER drive a known level and have the
TARGET read it -- no contention, because only one side is driving.

This deliberately does NOT reset the MPSSE on exit. The pin must stay driven
while the next payload runs and samples it.

Usage: ftdi_drive.py [0|1] [bit]   level, and which low-byte pin
           bit 0 = TCK/SWCLK, bit 1 = TDI/DO which is SWDIO in SWD mode
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
    import sys as _s
    level = int(_s.argv[1]) if len(_s.argv) > 1 else 0
    bit = int(_s.argv[2]) if len(_s.argv) > 2 else 0
    # bit 0 = TCK/SWCLK, bit 1 = TDI/DO which carries SWDIO in SWD mode
    out = (ctypes.c_ubyte * 3)(0x80, (level & 1) << bit, 1 << bit)
    wrote = ctypes.c_int()
    lib.libusb_bulk_transfer(handle, 0x04, out, 3, ctypes.byref(wrote), 1000)
    time.sleep(0.05)
    name = {0: "TCK/SWCLK", 1: "TDI/DO (SWDIO)"}.get(bit, f"bit{bit}")
    print(f"{name} held at {level}; MPSSE left active so it stays driven")
    lib.libusb_close(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

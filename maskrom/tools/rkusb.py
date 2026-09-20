#!/usr/bin/env python3
"""Minimal Rockchip maskrom USB client.

Contains no Rockchip code and runs no Rockchip binary: it drives libusb-1.0
directly through ctypes, which is stdlib. pyusb is not required.

The wire protocol was derived by reading rkdeveloptool's RKComm.cpp and
crc.cpp, then reimplemented here. Three details are easy to get wrong and all
three produce a silent USB timeout rather than an error:

  1. The slot number goes in **wIndex**, not wValue:
         control_transfer(0x40, 0x0C, wValue=0, wIndex=0x471, data, len)
  2. The checksum is *not* standard CRC-16/CCITT. It inits to 0xFFFF and,
     for every set bit in the data byte, XORs the polynomial into the
     register after the shift. See rk_crc_ccitt().
  3. Payload length mod 4096 has two special cases: 4095 pads with one zero
     byte, 4094 requires a trailing 1-byte "pend" transfer after the data.

Usage:
    ./rkusb.py --list
    ./rkusb.py --upload 471 payload.bin
"""

import argparse
import ctypes
import sys

ROCKCHIP_VID = 0x2207

REQ_TYPE_VENDOR_OUT = 0x40
REQ_CODE_UPLOAD = 0x0C
CHUNK = 4096
POLY_CCITT = 0x1021


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


def load_libusb() -> ctypes.CDLL:
    lib = ctypes.CDLL("libusb-1.0.so.0")
    lib.libusb_init.argtypes = [ctypes.c_void_p]
    lib.libusb_get_device_list.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))]
    lib.libusb_get_device_list.restype = ctypes.c_ssize_t
    lib.libusb_get_device_descriptor.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(DeviceDescriptor)]
    lib.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_close.argtypes = [ctypes.c_void_p]
    lib.libusb_get_bus_number.argtypes = [ctypes.c_void_p]
    lib.libusb_get_bus_number.restype = ctypes.c_uint8
    lib.libusb_get_device_address.argtypes = [ctypes.c_void_p]
    lib.libusb_get_device_address.restype = ctypes.c_uint8
    for fn in ("libusb_detach_kernel_driver", "libusb_attach_kernel_driver",
               "libusb_claim_interface", "libusb_release_interface",
               "libusb_kernel_driver_active"):
        getattr(lib, fn).argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_control_transfer.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16,
        ctypes.c_uint16, ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint]
    lib.libusb_error_name.argtypes = [ctypes.c_int]
    lib.libusb_error_name.restype = ctypes.c_char_p
    return lib


def rk_crc_ccitt(data: bytes) -> int:
    """Rockchip's checksum. Note this is NOT CRC-16/CCITT despite the name.

    Standard CCITT folds the data bit into the register before shifting. This
    variant shifts first, then XORs the whole polynomial in whenever the data
    bit is set — a different function with different results.
    """
    crc = 0xFFFF
    for ch in data:
        bit = 0x80
        while bit:
            if crc & 0x8000:
                crc = ((crc << 1) & 0xFFFF) ^ POLY_CCITT
            else:
                crc = (crc << 1) & 0xFFFF
            if ch & bit:
                crc ^= POLY_CCITT
            bit >>= 1
    return crc


def build_frame(image: bytes) -> tuple[bytes, bool]:
    """Apply the length fixups, append the checksum, report pend-packet need."""
    send_pend = False
    body = bytearray(image)

    remainder = len(body) % CHUNK
    if remainder == 4095:
        body.append(0)              # pad to 4096 so the CRC covers a whole chunk
    elif remainder == 4094:
        send_pend = True

    crc = rk_crc_ccitt(bytes(body))
    body.append((crc >> 8) & 0xFF)  # big-endian
    body.append(crc & 0xFF)
    return bytes(body), send_pend


# rkdeveloptool blocks indefinitely here. That is wrong for a diagnostic tool:
# a maskrom that enumerates but never services the download request then hangs
# the host process instead of reporting anything, and "it hung" is a far worse
# observation to write in a log than "it timed out after N seconds".
XFER_TIMEOUT_MS = 5000


def upload(lib, handle, slot: int, image: bytes) -> None:
    if slot not in (0x471, 0x472):
        raise ValueError("slot must be 0x471 or 0x472")

    payload, send_pend = build_frame(image)

    sent = 0
    while sent < len(payload):
        piece = payload[sent:sent + CHUNK]
        buf = (ctypes.c_ubyte * len(piece)).from_buffer_copy(piece)
        n = lib.libusb_control_transfer(
            handle, REQ_TYPE_VENDOR_OUT, REQ_CODE_UPLOAD,
            0, slot,                       # wValue = 0, wIndex = slot
            buf, len(piece), XFER_TIMEOUT_MS)
        if n < 0:
            raise OSError(f"control transfer failed at offset {sent}: "
                          f"{lib.libusb_error_name(n).decode()}")
        if n != len(piece):
            raise OSError(f"short write at offset {sent}: {n}/{len(piece)}")
        sent += len(piece)
        print(f"\r  uploaded {sent}/{len(payload)} bytes", end="", file=sys.stderr)
    print(file=sys.stderr)

    if send_pend:
        fill = (ctypes.c_ubyte * 1)(0)
        lib.libusb_control_transfer(
            handle, REQ_TYPE_VENDOR_OUT, REQ_CODE_UPLOAD, 0, slot, fill, 1,
            XFER_TIMEOUT_MS)


def find_devices(lib, ctx):
    lst = ctypes.POINTER(ctypes.c_void_p)()
    count = lib.libusb_get_device_list(ctx, ctypes.byref(lst))
    if count < 0:
        raise OSError("libusb_get_device_list failed")
    found = []
    for i in range(count):
        dev = lst[i]
        desc = DeviceDescriptor()
        if lib.libusb_get_device_descriptor(dev, ctypes.byref(desc)) != 0:
            continue
        if desc.idVendor == ROCKCHIP_VID:
            found.append((dev, lib.libusb_get_bus_number(dev),
                          lib.libusb_get_device_address(dev), desc.idProduct))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--upload", nargs=2, metavar=("SLOT", "FILE"))
    args = ap.parse_args()

    lib = load_libusb()
    ctx = ctypes.c_void_p()
    if lib.libusb_init(ctypes.byref(ctx)) != 0:
        print("libusb_init failed", file=sys.stderr)
        return 1

    devices = find_devices(lib, ctx)
    if not devices:
        print(f"no Rockchip device (VID {ROCKCHIP_VID:#06x}) found", file=sys.stderr)
        return 2
    for _dev, bus, addr, pid in devices:
        print(f"bus {bus:03d} dev {addr:03d}  {ROCKCHIP_VID:04x}:{pid:04x}")

    if args.list or not args.upload:
        return 0

    raw = args.upload[0].lower().removeprefix("0x")
    slot = int(raw, 16)
    image = open(args.upload[1], "rb").read()

    dev, _bus, _addr, pid = devices[0]
    handle = ctypes.c_void_p()
    if lib.libusb_open(dev, ctypes.byref(handle)) != 0:
        print("libusb_open failed (permissions?)", file=sys.stderr)
        return 1

    # A vendor-class kernel driver may be bound to interface 0; the maskrom
    # ignores EP0 traffic while another driver owns the interface.
    if lib.libusb_kernel_driver_active(handle, 0) == 1:
        lib.libusb_detach_kernel_driver(handle, 0)
    lib.libusb_claim_interface(handle, 0)

    print(f"uploading {len(image)} bytes to slot {slot:#05x} on "
          f"{ROCKCHIP_VID:04x}:{pid:04x}", file=sys.stderr)
    try:
        upload(lib, handle, slot, image)
        print("done", file=sys.stderr)
    finally:
        lib.libusb_release_interface(handle, 0)
        lib.libusb_close(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

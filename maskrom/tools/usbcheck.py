#!/usr/bin/env python3
"""Is the Rockchip device actually alive, or just a stale kernel entry?

`lsusb` showing the device proves nothing. When a payload takes over the CPU
the board stops servicing USB, but the kernel keeps the device node until
something tries to use it -- so a dead board looks identical to a live one,
and `lsusb -v` keeps working because it reads cached descriptors.

The only honest test is a live request. Exit 0 if EP0 answers, 1 if not.
"""
import ctypes, sys

L = ctypes.CDLL("libusb-1.0.so.0")
L.libusb_get_device_list.restype = ctypes.c_ssize_t
L.libusb_get_device_list.argtypes = [ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))]
L.libusb_init.argtypes = [ctypes.c_void_p]
L.libusb_control_transfer.restype = ctypes.c_int
L.libusb_control_transfer.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8,
                                      ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p,
                                      ctypes.c_uint16, ctypes.c_uint32]

class D(ctypes.Structure):
    _fields_ = [("bLength", ctypes.c_uint8), ("bDescriptorType", ctypes.c_uint8),
                ("bcdUSB", ctypes.c_uint16), ("bDeviceClass", ctypes.c_uint8),
                ("bDeviceSubClass", ctypes.c_uint8), ("bDeviceProtocol", ctypes.c_uint8),
                ("bMaxPacketSize0", ctypes.c_uint8), ("idVendor", ctypes.c_uint16),
                ("idProduct", ctypes.c_uint16), ("bcdDevice", ctypes.c_uint16),
                ("iManufacturer", ctypes.c_uint8), ("iProduct", ctypes.c_uint8),
                ("iSerialNumber", ctypes.c_uint8), ("bNumConfigurations", ctypes.c_uint8)]
L.libusb_get_device_descriptor.argtypes = [ctypes.c_void_p, ctypes.POINTER(D)]
L.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]

ctx = ctypes.c_void_p(); L.libusb_init(ctypes.byref(ctx))
lst = ctypes.POINTER(ctypes.c_void_p)()
n = L.libusb_get_device_list(ctx, ctypes.byref(lst))
for i in range(n):
    d = D()
    if L.libusb_get_device_descriptor(lst[i], ctypes.byref(d)) != 0:
        continue
    if d.idVendor == 0x2207:
        h = ctypes.c_void_p()
        if L.libusb_open(lst[i], ctypes.byref(h)) != 0:
            print("present but cannot open"); sys.exit(1)
        buf = (ctypes.c_ubyte * 18)()
        r = L.libusb_control_transfer(h, 0x80, 0x06, 0x0100, 0, buf, 18, 1000)
        # bcdUSB 0x0200 = maskrom, 0x0201 = loader, per rkdeveloptool
        mode = {0x0200: "maskrom", 0x0201: "loader"}.get(d.bcdUSB, f"{d.bcdUSB:#06x}")
        if r == 18:
            print(f"LIVE ({mode})"); sys.exit(0)
        print(f"STALE ({mode}) -- EP0 did not answer (r={r})"); sys.exit(1)
print("ABSENT"); sys.exit(2)

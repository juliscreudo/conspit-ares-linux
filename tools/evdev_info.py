#!/usr/bin/env python3
"""Inspecao read-only de um device evdev: nome, eixos (com fuzz/flat) e
capacidades de force feedback. Nao carrega nem dispara nenhum efeito.
"""
import fcntl
import struct
import sys

EV_ABS, EV_FF = 0x03, 0x15

FF_EFFECTS = {
    0x50: "FF_RUMBLE", 0x51: "FF_PERIODIC", 0x52: "FF_CONSTANT",
    0x53: "FF_SPRING", 0x54: "FF_FRICTION", 0x55: "FF_DAMPER",
    0x56: "FF_INERTIA", 0x57: "FF_RAMP", 0x58: "FF_SQUARE",
    0x59: "FF_TRIANGLE", 0x5A: "FF_SINE", 0x5B: "FF_SAW_UP",
    0x5C: "FF_SAW_DOWN", 0x5D: "FF_CUSTOM", 0x60: "FF_GAIN",
    0x61: "FF_AUTOCENTER",
}

ABS_NAMES = {
    0x00: "ABS_X", 0x01: "ABS_Y", 0x02: "ABS_Z", 0x03: "ABS_RX",
    0x04: "ABS_RY", 0x05: "ABS_RZ", 0x06: "ABS_THROTTLE",
    0x07: "ABS_RUDDER", 0x08: "ABS_WHEEL", 0x09: "ABS_GAS",
    0x0A: "ABS_BRAKE", 0x10: "ABS_HAT0X", 0x11: "ABS_HAT0Y",
}


def ioc(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (ord(typ) << 8) | nr


IOC_READ = 2


def get_name(fd):
    buf = bytearray(256)
    fcntl.ioctl(fd, ioc(IOC_READ, "E", 0x06, 256), buf)
    return buf.split(b"\x00")[0].decode()


def get_bits(fd, ev, nbits=1024):
    nbytes = (nbits + 7) // 8
    buf = bytearray(nbytes)
    n = fcntl.ioctl(fd, ioc(IOC_READ, "E", 0x20 + ev, nbytes), buf)
    return [i for i in range(n * 8) if buf[i // 8] >> (i % 8) & 1]


def get_absinfo(fd, axis):
    buf = bytearray(24)
    fcntl.ioctl(fd, ioc(IOC_READ, "E", 0x40 + axis, 24), buf)
    return struct.unpack("iiiiii", buf)  # value min max fuzz flat resolution


def main():
    path = sys.argv[1]
    with open(path, "rb") as f:
        fd = f.fileno()
        print(f"device: {path}")
        print(f"nome:   {get_name(fd)}")

        try:
            axes = get_bits(fd, EV_ABS, 64)
        except OSError:
            axes = []
        if axes:
            print("\neixos (ABS):")
            print(f"  {'eixo':<14}{'valor':>10}{'min':>10}{'max':>10}"
                  f"{'fuzz':>7}{'flat':>7}{'res':>6}")
            for a in axes:
                v, lo, hi, fuzz, flat, res = get_absinfo(fd, a)
                name = ABS_NAMES.get(a, f"ABS_{a:#04x}")
                warn = "   <-- fuzz/flat ruins" if (fuzz or flat) else ""
                print(f"  {name:<14}{v:>10}{lo:>10}{hi:>10}"
                      f"{fuzz:>7}{flat:>7}{res:>6}{warn}")

        try:
            ff = get_bits(fd, EV_FF, 128)
        except OSError:
            ff = []
        if ff:
            buf = bytearray(4)
            fcntl.ioctl(fd, ioc(IOC_READ, "E", 0x84, 4), buf)
            slots = struct.unpack("i", buf)[0]
            print(f"\nforce feedback: SIM ({slots} slots simultaneos)")
            for b in ff:
                print(f"  {FF_EFFECTS.get(b, hex(b))}")
        else:
            print("\nforce feedback: NAO exposto neste device")


if __name__ == "__main__":
    main()

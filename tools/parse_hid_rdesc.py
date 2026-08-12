#!/usr/bin/env python3
"""Parser minimo de HID report descriptor, focado em identificar a
Physical Interface Device (PID) usage page usada para force feedback.
"""
import sys

USAGE_PAGES = {
    0x01: "Generic Desktop",
    0x02: "Simulation",
    0x06: "Generic Device",
    0x07: "Keyboard",
    0x08: "LED",
    0x09: "Button",
    0x0C: "Consumer",
    0x0F: "PID (Physical Interface Device)",
    0xFF00: "Vendor-defined",
}

PID_USAGES = {
    0x01: "Physical Interface Device",
    0x20: "Set Effect Report",
    0x21: "Effect Block Index",
    0x25: "Effect Type",
    0x26: "ET Constant Force",
    0x27: "ET Ramp",
    0x28: "ET Custom Force Data",
    0x30: "ET Square",
    0x31: "ET Sine",
    0x32: "ET Triangle",
    0x33: "ET Sawtooth Up",
    0x34: "ET Sawtooth Down",
    0x40: "ET Spring",
    0x41: "ET Damper",
    0x42: "ET Inertia",
    0x43: "ET Friction",
    0x50: "Duration",
    0x5A: "Set Envelope Report",
    0x5F: "Set Condition Report",
    0x6E: "Set Periodic Report",
    0x73: "Set Constant Force Report",
    0x74: "Set Ramp Force Report",
    0x77: "Effect Operation Report",
    0x78: "Op Effect Start",
    0x7A: "Op Effect Stop",
    0x89: "PID Block Free Report",
    0x8D: "Device Gain Report",
    0x96: "PID Device Control",
    0x97: "DC Enable Actuators",
    0x98: "DC Disable Actuators",
    0x9A: "DC Device Reset",
    0xA0: "Create New Effect Report",
    0xAB: "Set Custom Force Report",
    0xB0: "PID Block Load Report",
    0xB1: "PID Pool Report",
}

GENERIC_DESKTOP = {
    0x04: "Joystick", 0x05: "Game Pad", 0x30: "X", 0x31: "Y", 0x32: "Z",
    0x33: "Rx", 0x34: "Ry", 0x35: "Rz", 0x36: "Slider", 0x37: "Dial",
    0x38: "Wheel", 0x39: "Hat Switch",
}

MAIN_TAGS = {0x08: "Input", 0x09: "Output", 0x0B: "Feature",
             0x0A: "Collection", 0x0C: "End Collection"}
GLOBAL_TAGS = {0x00: "Usage Page", 0x01: "Logical Min", 0x02: "Logical Max",
               0x03: "Physical Min", 0x04: "Physical Max", 0x05: "Unit Exp",
               0x06: "Unit", 0x07: "Report Size", 0x08: "Report ID",
               0x09: "Report Count", 0x0A: "Push", 0x0B: "Pop"}
LOCAL_TAGS = {0x00: "Usage", 0x01: "Usage Min", 0x02: "Usage Max"}


def parse(data):
    i = 0
    page = None
    depth = 0
    out = []
    report_ids = set()
    pages_seen = set()
    pid_usages = set()
    while i < len(data):
        b = data[i]
        i += 1
        size = b & 0x03
        size = 4 if size == 3 else size
        typ = (b >> 2) & 0x03
        tag = (b >> 4) & 0x0F
        val = 0
        for k in range(size):
            val |= data[i + k] << (8 * k)
        i += size

        if typ == 1:  # Global
            name = GLOBAL_TAGS.get(tag, f"tag{tag:x}")
            if tag == 0x00:
                page = val
                pages_seen.add(val)
                out.append(f"{'  '*depth}Usage Page: 0x{val:04x} "
                            f"({USAGE_PAGES.get(val, '?')})")
                continue
            if tag == 0x08:
                report_ids.add(val)
            out.append(f"{'  '*depth}{name}: {val}")
        elif typ == 2:  # Local
            name = LOCAL_TAGS.get(tag, f"tag{tag:x}")
            desc = ""
            if page == 0x0F:
                desc = f" ({PID_USAGES.get(val, '?')})"
                pid_usages.add(val)
            elif page == 0x01:
                desc = f" ({GENERIC_DESKTOP.get(val, '?')})"
            out.append(f"{'  '*depth}{name}: 0x{val:02x}{desc}")
        else:  # Main
            name = MAIN_TAGS.get(tag, f"tag{tag:x}")
            if tag == 0x0C:
                depth = max(0, depth - 1)
                out.append(f"{'  '*depth}End Collection")
            elif tag == 0x0A:
                out.append(f"{'  '*depth}Collection ({val})")
                depth += 1
            else:
                out.append(f"{'  '*depth}{name} (0x{val:02x})")
    return out, report_ids, pages_seen, pid_usages


def main():
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    out, rids, pages, pid_usages = parse(data)
    if "-v" in sys.argv:
        print("\n".join(out))
        print()
    print(f"tamanho: {len(data)} bytes")
    print(f"report IDs: {sorted(rids)}")
    print("usage pages: " + ", ".join(
        f"0x{p:04x}({USAGE_PAGES.get(p, '?')})" for p in sorted(pages)))
    if 0x0F in pages:
        print("\n>>> PID FFB PRESENTE. Efeitos/relatorios declarados:")
        for u in sorted(pid_usages):
            n = PID_USAGES.get(u)
            if n:
                print(f"    0x{u:02x}  {n}")
    else:
        print("\n>>> Nenhuma PID usage page: sem FFB padrao USB neste descritor.")


if __name__ == "__main__":
    main()

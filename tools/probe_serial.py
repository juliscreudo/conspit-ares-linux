#!/usr/bin/env python3
"""Sonda read-only da interface CDC serial da Conspit Ares.

Envia apenas consultas (`?`) e info (`!`) do protocolo de comandos do
OpenFFBoard. Nenhuma escrita (`=`), nenhum comando de calibracao.
Ver https://github.com/Ultrawipf/OpenFFBoard/wiki/Commands
"""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM2"

# Somente leitura. A ordem vai do mais generico para o mais especifico.
PROBES = [
    "?",
    "help",
    "sys.0.id?",
    "sys.id?",
    "sys.0.help",
    "sys.0.lsactive?",
    "sys.0.lsmain?",
    "sys.0.lscmd?",
    "sys.0.swver?",
    "sys.0.hwtype?",
    "sys.0.heapfree?",
    "sys.0.vint?",
    "axis.0.power?",
    "axis.0.esgain?",
    "axis.0.drvtype?",
    "axis.0.pos?",
    "fx.0.effects?",
    "sys.0.id!",
]


def drain(ser, wait=0.3):
    time.sleep(wait)
    buf = b""
    while ser.in_waiting:
        buf += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return buf


def main():
    ser = serial.Serial()
    ser.port = PORT
    ser.baudrate = 115200  # irrelevante em CDC, mas precisa de um valor
    ser.timeout = 0.2
    ser.write_timeout = 2
    ser.open()
    print(f"# aberto {PORT} (dtr={ser.dtr} rts={ser.rts})")

    boot = drain(ser, 0.6)
    if boot:
        print(f"# banner espontaneo: {boot!r}")
    else:
        print("# nenhum banner espontaneo")

    for cmd in PROBES:
        ser.reset_input_buffer()
        ser.write((cmd + "\n").encode())
        ser.flush()
        resp = drain(ser, 0.35)
        shown = resp.decode("utf-8", "replace").strip() if resp else "<SEM RESPOSTA>"
        print(f"{cmd:<20} -> {shown}")

    ser.close()


if __name__ == "__main__":
    main()

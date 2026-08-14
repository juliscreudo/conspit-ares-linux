#!/usr/bin/env python3
"""Observa a posicao do volante nos dois canais ao mesmo tempo, so lendo.

  - evdev  (/dev/input/event*): o que o kernel Linux enxerga
  - hidraw (/dev/hidraw*):      os relatorios HID crus, que e' de onde o
                                ConspitLink sob Wine tira os dados

Serve pra separar "o dado nao existe" de "o dado existe mas nao chega no
app". Ler qualquer um dos dois nao atrapalha quem mais estiver lendo:
cada open recebe sua propria copia dos relatorios. Pode rodar com o
ConspitLink aberto.

    python3 tools/hid_watch.py          # 12s
    python3 tools/hid_watch.py 20       # 20s

GIRE O VOLANTE durante a captura.
"""
import fcntl
import glob
import os
import select
import struct
import sys
import time
from collections import defaultdict

VID, PID = 0x3514, 0x0301
EV_ABS, ABS_X = 0x03, 0x00


def achar_hidraw():
    """Localiza o /dev/hidraw da base pelo VID/PID (os numeros mudam a cada
    reenumeracao do kernel, entao nunca fixar hidrawN)."""
    for caminho in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(caminho, "device", "uevent")) as f:
                uevent = f.read()
        except OSError:
            continue
        for linha in uevent.splitlines():
            if not linha.startswith("HID_ID="):
                continue
            # HID_ID=0003:00003514:00000301 -- comparar como numero, nao como
            # texto: os campos vem com zeros a esquerda de largura variavel.
            p = linha.split("=", 1)[1].split(":")
            try:
                if len(p) == 3 and int(p[1], 16) == VID and int(p[2], 16) == PID:
                    return "/dev/" + os.path.basename(caminho)
            except ValueError:
                continue
    return None


def achar_evdev():
    achados = glob.glob("/dev/input/by-id/usb-CONSPIT_CONSPIT_ARES_*-event-joystick")
    return achados[0] if achados else None


def ler_abs_x(fd):
    buf = bytearray(24)
    fcntl.ioctl(fd, (2 << 30) | (24 << 16) | (ord("E") << 8) | (0x40 + ABS_X), buf)
    return struct.unpack("iiiiii", buf)[0]


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

    dev_hid = achar_hidraw()
    dev_ev = achar_evdev()
    if not dev_hid and not dev_ev:
        sys.exit("base nao encontrada. Ela esta ligada?")

    fd_hid = fd_ev = None
    if dev_hid:
        try:
            fd_hid = os.open(dev_hid, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            print(f"!! sem permissao para ler {dev_hid} -- instale "
                  f"udev/70-conspit.rules")
    if dev_ev:
        try:
            fd_ev = os.open(dev_ev, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            print(f"!! sem permissao para ler {dev_ev}")

    print(f"hidraw : {dev_hid or '(indisponivel)'}")
    print(f"evdev  : {dev_ev or '(indisponivel)'}")
    print(f"\n>>> GIRE O VOLANTE agora, por {dur:.0f} segundos <<<\n")

    x_min, x_max, x_eventos = None, None, 0
    contagem = defaultdict(int)
    minimo = defaultdict(lambda: defaultdict(lambda: 255))
    maximo = defaultdict(lambda: defaultdict(lambda: 0))
    tamanho = {}

    if fd_ev is not None:
        try:
            v = ler_abs_x(fd_ev)
            x_min = x_max = v
        except OSError:
            pass

    fds = [f for f in (fd_hid, fd_ev) if f is not None]
    t0 = time.monotonic()
    while time.monotonic() - t0 < dur:
        r, _, _ = select.select(fds, [], [], 0.3)
        for f in r:
            try:
                dados = os.read(f, 4096)
            except (BlockingIOError, OSError):
                continue
            if not dados:
                continue
            if f == fd_hid:
                rid = dados[0]
                contagem[rid] += 1
                tamanho[rid] = len(dados)
                for i, b in enumerate(dados):
                    if b < minimo[rid][i]:
                        minimo[rid][i] = b
                    if b > maximo[rid][i]:
                        maximo[rid][i] = b
            else:
                # struct input_event: 2x long (time), u16 type, u16 code, s32 value
                tam = struct.calcsize("llHHi")
                for off in range(0, len(dados) - tam + 1, tam):
                    _, _, tipo, cod, val = struct.unpack("llHHi",
                                                         dados[off:off + tam])
                    if tipo == EV_ABS and cod == ABS_X:
                        x_eventos += 1
                        x_min = val if x_min is None else min(x_min, val)
                        x_max = val if x_max is None else max(x_max, val)

    for f in fds:
        os.close(f)

    print("=" * 62)
    print("KERNEL (evdev ABS_X) -- o volante realmente girou?")
    if fd_ev is None:
        print("   nao lido")
    elif x_eventos == 0:
        print("   NENHUM evento de eixo. O volante nao girou, ou o kernel")
        print("   nao esta recebendo a posicao.")
    else:
        print(f"   {x_eventos} eventos, faixa {x_min} .. {x_max} "
              f"(amplitude {x_max - x_min})")

    print("\nHIDRAW -- a posicao esta nos relatorios HID crus?")
    if not contagem:
        print("   nenhum relatorio recebido")
    for rid in sorted(contagem):
        n = contagem[rid]
        print(f"   report ID {rid} (0x{rid:02x}): {n} relatorios "
              f"({n/dur:.0f}/s), {tamanho[rid]} bytes")
        variaveis = [i for i in range(tamanho[rid])
                     if maximo[rid][i] != minimo[rid][i]]
        if not variaveis:
            print("      nenhum byte mudou")
            continue
        print(f"      {len(variaveis)} bytes mudaram, nos offsets:")
        linha = "      "
        for i in variaveis:
            linha += f" [{i}]{minimo[rid][i]}..{maximo[rid][i]}"
            if len(linha) > 88:
                print(linha)
                linha = "      "
        if linha.strip():
            print(linha)
    print("=" * 62)


if __name__ == "__main__":
    main()

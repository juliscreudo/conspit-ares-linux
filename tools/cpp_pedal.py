#!/usr/bin/env python3
"""Configura os pedais CPP.LITE nativamente no Linux, sem Wine e sem o app.

A calibracao dos pedais NAO fica no PC: ela e' gravada na propria pedaleira.
O ConspitLink e' so uma GUI por cima de um canal HID vendor, e esse canal
esta acessivel nativamente (a regra udev/70-conspit.rules ja da o ACL).
Este utilitario fala o mesmo protocolo -- ver docs/protocolo-cpp-lite.md.

    tools/cpp_pedal.py ler
    tools/cpp_pedal.py monitorar
    tools/cpp_pedal.py calibrar acelerador min
    tools/cpp_pedal.py calibrar acelerador max

⚠️ `calibrar` ESCREVE na pedaleira. As demais ferramentas deste repo sao
deliberadamente read-only; esta e' a excecao, junto com o cpp_hid_shim.py.
`ler` e `monitorar` nao escrevem nada.

Como a calibracao funciona (capturado do proprio app em 2026-08-14):
o comando NAO carrega valor -- `$setvaluex0` manda a pedaleira gravar a
leitura ATUAL do sensor como minimo daquele eixo. Ou seja, a posicao fisica
do pedal no instante do comando e' o que conta. Por isso `calibrar` avisa e
mostra a leitura antes de mandar.
"""
import argparse
import glob
import os
import select
import struct
import sys
import time

VID, PID = 0x3514, 0x0005
REPORT_VENDOR = 2          # canal de comandos (2a top-level collection)
REPORT_POSICAO = 1         # relatorio de posicao dos tres pedais
TAM = 64                   # 1 byte de report ID + 63 de payload

# Nome do pedal -> (letra do protocolo, indice do campo no relatorio de
# posicao). A letra veio da captura do app: clicar MIN/MAX no acelerador
# emitiu "$setvaluex0"/"$setvaluex1", entao x = acelerador, medido e nao
# inferido. A ordem dos campos e' a do descritor HID (Rx, Y, Z).
PEDAIS = {
    "acelerador": ("x", 0),
    "freio":      ("y", 1),
    "embreagem":  ("z", 2),
}

CONSULTAS = [
    "$version",
    "$getPWM1", "$getPWM2", "$getPWM3",
    "$gselect1", "$gselect2", "$gselect3",
    "$gdlinex", "$gdliney", "$gdlinez",
    "$getlimity", "$getbarlimit",
]


def achar_hidraw():
    """Acha o /dev/hidraw REAL da pedaleira pelo modalias.

    Ignora devices virtuais: com o cpp_hid_shim.py no ar existem DOIS
    hidraw com este VID/PID, e os numeros de hidrawN mudam a cada
    reenumeracao do kernel -- nunca fixar hidraw12 em lugar nenhum.
    """
    alvo = ("v%08Xp%08X" % (VID, PID)).lower()
    for caminho in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        dev = os.path.realpath(os.path.join(caminho, "device"))
        if "/devices/virtual/" in dev:
            continue
        try:
            with open(os.path.join(caminho, "device", "modalias")) as f:
                if alvo in f.read().strip().lower():
                    return "/dev/" + os.path.basename(caminho)
        except OSError:
            continue
    return None


def moldar(cmd):
    p = cmd.encode("ascii")
    if len(p) > TAM - 1:
        raise ValueError("comando longo demais: %r" % cmd)
    return bytes([REPORT_VENDOR]) + p + b"\x00" * (TAM - 1 - len(p))


def texto(dados):
    return dados[1:].split(b"\x00", 1)[0].decode("ascii", "replace")


def drenar(fd, limite=200):
    """Descarta o pendente. LIMITADO de proposito: a pedaleira transmite
    relatorios de posicao sem parar, entao "while tiver dado" nunca sai."""
    for _ in range(limite):
        if not select.select([fd], [], [], 0.02)[0]:
            return
        try:
            os.read(fd, 256)
        except OSError:
            return


def perguntar(fd, cmd, espera=0.6):
    """Manda um comando de consulta e devolve a resposta, ou None."""
    os.write(fd, moldar(cmd))
    fim = time.time() + espera
    while time.time() < fim:
        if not select.select([fd], [], [], 0.05)[0]:
            continue
        try:
            d = os.read(fd, 256)
        except OSError:
            continue
        if d and d[0] == REPORT_VENDOR:
            return texto(d)
    return None


def posicao(fd, espera=1.0):
    """Leitura crua dos tres pedais (0-4095), na ordem do descritor."""
    fim = time.time() + espera
    while time.time() < fim:
        if not select.select([fd], [], [], 0.05)[0]:
            continue
        try:
            d = os.read(fd, 256)
        except OSError:
            continue
        if d and d[0] == REPORT_POSICAO and len(d) >= 7:
            return [struct.unpack_from("<H", d, 1 + i * 2)[0] for i in range(3)]
    return None


def cmd_ler(fd, args):
    print("%-14s %s" % ("comando", "resposta"))
    print("-" * 46)
    for c in CONSULTAS:
        r = perguntar(fd, c)
        print("%-14s %s" % (c, r if r is not None else "(sem resposta)"))
    return 0


def cmd_monitorar(fd, args):
    """Mostra a leitura crua dos pedais. Serve para conferir a calibracao:
    depois de calibrar, o pedal solto deve marcar perto de 0 e o pedal no
    batente perto de 4095."""
    print("leitura crua dos pedais (Ctrl-C para sair)\n")
    print("  %-12s %-12s %-12s" % ("acelerador", "freio", "embreagem"))
    try:
        while True:
            p = posicao(fd)
            if p:
                print("\r  %-12d %-12d %-12d" % (p[0], p[1], p[2]),
                      end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()
    return 0


def cmd_calibrar(fd, args):
    letra, campo = PEDAIS[args.pedal]
    extremo = "0" if args.extremo == "min" else "1"
    cmd = "$setvalue%s%s" % (letra, extremo)

    p = posicao(fd)
    atual = p[campo] if p else None
    print("pedal    : %s (eixo %s do protocolo)" % (args.pedal, letra))
    print("extremo  : %s" % args.extremo)
    print("leitura  : %s" % (atual if atual is not None else "(sem leitura)"))
    print("comando  : %s" % cmd)
    print()
    print("⚠️  A pedaleira grava a leitura ATUAL do sensor. Confira que o")
    if args.extremo == "min":
        print("    pedal esta SOLTO antes de confirmar.")
    else:
        print("    pedal esta PISADO ATE O BATENTE antes de confirmar.")

    if not args.sim:
        try:
            if input("\nconfirmar? [s/N] ").strip().lower() not in ("s", "y"):
                print("cancelado.")
                return 1
        except EOFError:
            print("cancelado (sem terminal; use --sim para nao perguntar).")
            return 1

    os.write(fd, moldar(cmd))
    # o comando nao tem resposta -- fire and forget, como o app faz
    time.sleep(0.2)
    p = posicao(fd)
    print("enviado. leitura agora: %s"
          % (p[campo] if p else "(sem leitura)"))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Configura os pedais CPP.LITE sem o ConspitLink.")
    ap.add_argument("--dev", help="/dev/hidraw da pedaleira (padrao: achar)")
    sub = ap.add_subparsers(dest="acao", required=True)

    sub.add_parser("ler", help="mostra a configuracao gravada (read-only)")
    sub.add_parser("monitorar", help="leitura crua dos pedais (read-only)")

    c = sub.add_parser("calibrar", help="grava min/max de um pedal (ESCREVE)")
    c.add_argument("pedal", choices=sorted(PEDAIS))
    c.add_argument("extremo", choices=["min", "max"])
    c.add_argument("--sim", action="store_true", help="nao pedir confirmacao")

    args = ap.parse_args()

    dev = args.dev or achar_hidraw()
    if not dev:
        print("pedaleira CPP.LITE (%04x:%04x) nao encontrada." % (VID, PID),
              file=sys.stderr)
        return 1
    try:
        fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    except PermissionError:
        print("sem permissao em %s." % dev, file=sys.stderr)
        print("  sudo cp udev/70-conspit.rules /etc/udev/rules.d/",
              file=sys.stderr)
        print("  sudo udevadm control --reload-rules && sudo udevadm trigger",
              file=sys.stderr)
        return 1

    try:
        drenar(fd)
        return {"ler": cmd_ler,
                "monitorar": cmd_monitorar,
                "calibrar": cmd_calibrar}[args.acao](fd, args)
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
